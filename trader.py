"""AI Daily Trader 1.0: market-day signal scanner, NOT an order execution bot."""
import json
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pandas_market_calendars as mcal
import requests
import yfinance as yf

SYMBOLS = [s.strip().upper() for s in os.getenv('SYMBOLS', 'NVDA,AMD,MSFT,TSLA,AAPL,SPCX,TTWO').split(',') if s.strip()]
NTFY_TOPIC = os.getenv('NTFY_TOPIC', '').strip()
NTFY_SERVER = os.getenv('NTFY_SERVER', 'https://ntfy.sh').rstrip('/')
SEND_NO_SIGNALS = os.getenv('SEND_NO_SIGNALS', 'false').lower() == 'true'


def completed_session_today():
    now = datetime.now(ZoneInfo('America/New_York'))
    today = now.date()
    schedule = mcal.get_calendar('NYSE').schedule(start_date=today, end_date=today)
    if schedule.empty:
        print(f'{today}: NYSE geschlossen, keine Analyse.')
        return None
    if now < schedule['market_close'].iloc[0]:
        print(f'{today}: NYSE-Handelstag noch nicht abgeschlossen, keine Analyse.')
        return None
    return today


def calculate(ticker, session_date):
    data = yf.Ticker(ticker).history(period='6mo', interval='1d', auto_adjust=True)
    if data.empty or 'Close' not in data:
        raise ValueError('Keine historischen Schlusskurse verfügbar')

    # Yahoo may include a row for a session after the one being scanned.
    close = data.loc[data.index.date <= session_date, 'Close'].sort_index()
    if close.empty:
        raise ValueError(f'Keine Schlusskurse bis zum {session_date} verfügbar')
    last_data_date = close.index[-1].date()
    if last_data_date != session_date:
        raise ValueError(f'Schlusskurs am {session_date} fehlt (letzte Zeile: {last_data_date})')

    close = pd.to_numeric(close, errors='coerce')
    close = close.where(np.isfinite(close) & (close > 0))
    if pd.isna(close.iloc[-1]):
        raise ValueError(f'Ungültiger Schlusskurs am {session_date}')
    close = close.dropna()
    if len(close) < 60:
        raise ValueError(f'Zu wenige gültige Tageskurse: {len(close)} von mindestens 60')

    ma20 = close.rolling(20).mean().iloc[-1]
    ma50 = close.rolling(50).mean().iloc[-1]
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    loss = -delta.clip(upper=0).ewm(alpha=1/14, adjust=False).mean()
    rs = gain.iloc[-1] / max(loss.iloc[-1], 1e-12)
    rsi = float(100 - (100 / (1 + rs)))
    last = float(close.iloc[-1]); previous = float(close.iloc[-2])
    # Illustrative rules only, not validated trading signals or personalized advice.
    if last > ma20 > ma50 and 50 <= rsi <= 68 and last > previous:
        signal = 'BEOBACHTEN: möglicher LONG-Einstieg'
    elif last < ma20 and rsi < 45:
        signal = 'WARNUNG: schwacher Trend / Ausstieg prüfen'
    else:
        signal = 'KEIN HANDELSSIGNAL'
    return {'symbol': ticker, 'last_close_usd': round(last, 2), 'ma20_usd': round(float(ma20), 2), 'ma50_usd': round(float(ma50), 2), 'rsi14': round(rsi, 1), 'signal': signal, 'last_data_date': last_data_date.isoformat()}


def send_push(message):
    if not NTFY_TOPIC:
        print('ntfy deaktiviert (NTFY_TOPIC fehlt)')
        return
    response = requests.post(f'{NTFY_SERVER}/{NTFY_TOPIC}', data=message.encode('utf-8'), headers={'Title': 'AI Daily Trader 1.0', 'Tags': 'chart_with_upwards_trend'}, timeout=15)
    response.raise_for_status()


def main():
    session_date = completed_session_today()
    if session_date is None:
        return
    date = session_date.isoformat()
    results = []
    errors = []
    for symbol in SYMBOLS:
        try:
            results.append(calculate(symbol, session_date))
        except Exception as exc:
            errors.append(f'{symbol}: {exc}')
    output = {'date_new_york': date, 'mode': 'SIGNALS_ONLY_NO_REAL_ORDERS', 'results': results, 'errors': errors, 'generated_at_utc': datetime.now(timezone.utc).isoformat()}
    os.makedirs('output', exist_ok=True)
    with open('output/latest.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(json.dumps(output, ensure_ascii=False, indent=2))
    selected = [r for r in results if r['signal'] != 'KEIN HANDELSSIGNAL']
    if selected or errors or SEND_NO_SIGNALS:
        lines = [f'AI Daily Trader | {date} | NUR SIGNAL / KEINE ORDERS']
        lines += [f"{r['symbol']}: {r['signal']} | Schlusskurs ${r['last_close_usd']} | RSI {r['rsi14']} | Daten: {r['last_data_date']}" for r in (selected or results)]
        lines += [f'FEHLER: {e}' for e in errors]
        lines.append('Indikatoren können falsch liegen. Kurse sind verzögert; nie blind handeln.')
        send_push('\n'.join(lines))
    if errors and not results:
        raise SystemExit('Alle Kursabrufe fehlgeschlagen; siehe Log und ntfy.')

if __name__ == '__main__':
    main()
