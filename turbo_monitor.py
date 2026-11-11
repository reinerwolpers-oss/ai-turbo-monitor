"""Read-only monitor for DE000FB00U40. No orders. Fail closed on stale data."""
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas_market_calendars as mcal
import requests
import yfinance as yf

ISIN = 'DE000FB00U40'
WKN = 'FB00U4'
POSITION = 232
ENTRY_EUR = 1.023
TARGET_BID_EUR = 1.40
REFERENCE_KO_USD = 213.4700  # Reference only; open-end KO barriers can change.
NY = ZoneInfo('America/New_York')


def parse_timestamp(raw):
    if not isinstance(raw, str):
        raise ValueError('timestamp must be ISO 8601 with timezone')
    result = datetime.fromisoformat(raw.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('timestamp has no timezone')
    return result.astimezone(timezone.utc)


def positive_number(value):
    n = float(value)
    if not math.isfinite(n) or n <= 0:
        raise ValueError('price must be finite and positive')
    return n


def fetch_issuer_quote(now):
    """Only a user-provided, authorized JSON endpoint. Never guess a bid from TTWO."""
    url = os.getenv('TURBO_QUOTE_URL', '').strip()
    if not url:
        return None, 'Kein zertifizierter Zertifikat-Geldkurs-Feed konfiguriert (TURBO_QUOTE_URL fehlt).'
    if not url.startswith('https://'):
        return None, 'TURBO_QUOTE_URL muss HTTPS verwenden.'
    headers = {}
    if os.getenv('TURBO_QUOTE_TOKEN'):
        headers['Authorization'] = f"Bearer {os.environ['TURBO_QUOTE_TOKEN']}"
    try:
        response = requests.get(url, headers=headers, timeout=12)
        response.raise_for_status()
        obj = response.json()
        if not isinstance(obj, dict) or obj.get('isin') != ISIN or obj.get('currency') != 'EUR':
            raise ValueError('ISIN/currency mismatch or invalid JSON')
        ts = parse_timestamp(obj.get('timestamp'))
        age = (now - ts).total_seconds()
        if age < -120 or age > 300:
            raise ValueError(f'outdated / future quote (age {age:.0f}s)')
        bid = positive_number(obj.get('bid_eur'))
        result = {'bid_eur': bid, 'timestamp_utc': ts.isoformat(), 'source': str(obj.get('source') or 'Configured HTTPS quote feed')[:90]}
        if 'ko_usd' in obj:
            result['ko_usd'] = positive_number(obj['ko_usd'])
        return result, None
    except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
        return None, f'Zertifikat-Quote ungültig/fehlt: {exc}'


def get_underlying(now):
    data = yf.Ticker('TTWO').history(period='1d', interval='1m', auto_adjust=False, prepost=False)
    if data.empty:
        raise ValueError('TTWO intraday data unavailable')
    index = data.index[-1].to_pydatetime()
    if index.tzinfo is None:
        raise ValueError('TTWO feed timestamp lacks timezone')
    ts = index.astimezone(timezone.utc)
    age = (now - ts).total_seconds()
    if age < -120 or age > 600:
        raise ValueError(f'TTWO quote stale: {age/60:.1f} minutes')
    price = positive_number(data['Close'].iloc[-1])
    return {'price_usd': price, 'timestamp_utc': ts.isoformat(), 'age_seconds': round(age)}


def is_regular_market_session(now):
    ny_now = now.astimezone(NY)
    calendar = mcal.get_calendar('NYSE')
    schedule = calendar.schedule(start_date=ny_now.date(), end_date=ny_now.date())
    if schedule.empty:
        return False
    row = schedule.iloc[0]
    return row['market_open'].to_pydatetime() <= now <= row['market_close'].to_pydatetime()


def evaluate(underlying, quote):
    """Return warnings. KO comparison is indicative, not a confirmed live barrier unless quote supplies it."""
    alerts = []
    ko = quote['ko_usd'] if quote and 'ko_usd' in quote else REFERENCE_KO_USD
    ko_verified = bool(quote and 'ko_usd' in quote)
    diff_pct = (underlying['price_usd'] / ko - 1) * 100 if underlying else None
    if diff_pct is not None:
        source_note = 'Feed-Barriere' if ko_verified else 'REFERENZ-Barriere (nicht live verifiziert)'
        if diff_pct <= 0:
            alerts.append(f'KRITISCH: TTWO bei/unter {source_note} {ko:.4f} USD. Knock-out bereits möglich! Unbedingt Emittentenstatus prüfen.')
        elif diff_pct < 3:
            alerts.append(f'KRITISCH: nur {diff_pct:.2f}% Abstand zur {source_note} {ko:.4f} USD!')
        elif diff_pct < 5:
            alerts.append(f'WARNUNG: nur {diff_pct:.2f}% Abstand zur {source_note} {ko:.4f} USD.')
    if quote and quote['bid_eur'] >= TARGET_BID_EUR:
        alerts.append(f'ZIEL ERREICHT: geprüfter Zertifikat-GELDKURS {quote["bid_eur"]:.3f} EUR >= {TARGET_BID_EUR:.2f} EUR. Verkauf nur manuell prüfen.')
    return alerts, diff_pct, ko, ko_verified


def push(message):
    topic = os.getenv('NTFY_TOPIC', '').strip()
    if not topic:
        print('ntfy nicht konfiguriert: Meldung nur im Log')
        return
    base = os.getenv('NTFY_SERVER', 'https://ntfy.sh').rstrip('/')
    if not base.startswith('https://'):
        raise ValueError('NTFY_SERVER must use HTTPS')
    resp = requests.post(f'{base}/{topic}', data=message.encode('utf-8'), headers={'Title': 'Take-Two Turbo FB00U4', 'Tags': 'warning'}, timeout=15)
    resp.raise_for_status()


def run(now=None):
    now = now or datetime.now(timezone.utc)
    
    if os.getenv("TURBO_TEST_ALERT") == "true":
        message = (
            "TESTALARM - KEIN ECHTES HANDELSSIGNAL\n"
            "Take-Two Turbo FB00U4\n"
            "ISIN: DE000FB00U40\n"
            "SIMULATION: Knock-out-Abstand unter 5 %\n"
            "Dies ist nur ein technischer Push-Test.\n"
            "Keine automatische Order."
        )
        push(message)
        print("TESTALARM erfolgreich an ntfy gesendet")
        return {"status": "TEST_ALERT_SENT"}

    result = {'time_utc': now.isoformat(), 'isin': ISIN, 'wkn': WKN, 'shares': POSITION, 'entry_eur': ENTRY_EUR,
              'target_bid_eur': TARGET_BID_EUR, 'reference_ko_usd': REFERENCE_KO_USD,
              'mode': 'ALERTS_ONLY_NO_ORDERS', 'alerts': [], 'errors': []}
    if not is_regular_market_session(now):
        result['status'] = 'OUTSIDE_US_REGULAR_SESSION'
    else:
        result['status'] = 'CHECKED'
        try:
            underlying = get_underlying(now)
            result['underlying'] = underlying
        except Exception as exc:
            underlying = None
            result['errors'].append(f'TTWO kein aktueller Kurs: {exc}')
        quote, quote_error = fetch_issuer_quote(now)
        if quote_error:
            result['errors'].append(quote_error)
        if quote:
            result['certificate_quote'] = quote
        alerts, gap, ko, verified = evaluate(underlying, quote)
        result['alerts'] = alerts
        result['ko_gap_pct'] = gap
        result['ko_barrier_usd_used'] = ko
        result['ko_barrier_live_verified'] = verified
        if not verified:
            result['errors'].append('KO-Barriere nur Referenzwert; regelmäßige Anpassung möglich.')
        # Data problems are prominent, not hidden as silence or presumed target hit.
        if alerts or result['errors'] or os.getenv('TURBO_SEND_OK', 'false').lower() == 'true':
            lines = [f'Turbo {WKN} | {now.astimezone(NY):%Y-%m-%d %H:%M} New York | NUR WARNUNGEN']
            if underlying:
                lines.append(f'TTWO: {underlying["price_usd"]:.2f} USD (Zeit: {underlying["timestamp_utc"]})')
            if quote:
                lines.append(f'Zertifikat GELD: {quote["bid_eur"]:.3f} EUR (Zeit: {quote["timestamp_utc"]})')
            lines += alerts or ['Kein Kursalarm aus auswertbaren Daten.']
            lines += [f'DATENHINWEIS: {e}' for e in result['errors']]
            lines.append('Keine automatische Order. Knock-out und Datenverzögerung beachten.')
            push('\n'.join(lines))
    Path('output').mkdir(exist_ok=True)
    Path('output/turbo_latest.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == '__main__':
    run()
