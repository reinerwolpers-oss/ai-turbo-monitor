import json
import os
import pathlib
import requests
import pandas as pd
import yfinance as yf

ROOT = pathlib.Path(__file__).parent
DATA_DIR = ROOT / "data"
LEGACY = DATA_DIR / "latest.json"
MULTI = DATA_DIR / "assets_latest.json"
STATE = DATA_DIR / "alert_state_v11.json"  # Preserve existing alert history
CONFIG = ROOT / "assets.json"


def send(title, message, priority="default"):
    topic = os.getenv("NTFY_TOPIC", "").strip()
    if not topic:
        raise RuntimeError("NTFY_TOPIC fehlt; Push-Nachricht nicht gesendet")
    server = os.getenv("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    headers = {"Title": title, "Priority": priority, "Tags": "warning"}
    token = os.getenv("NTFY_TOKEN", "").strip()
    if token:
        headers["Authorization"] = "Bearer " + token
    response = requests.post(
        f"{server}/{topic}", data=message.encode("utf-8"),
        headers=headers, timeout=15
    )
    response.raise_for_status()


def notify_data_errors(errors, previous, next_state):
    """Warnung bei neuen API-Fehlern, Entwarnung nach Behebung."""
    old_errors = set(previous.get("_api_errors", []))
    current_errors = set(errors)

    new_errors = current_errors - old_errors

    if new_errors:
        send(
            "AI Turbo Monitor: API-Fehler",
            "Kursdaten konnten nicht geladen werden:\n"
            + "\n".join(sorted(new_errors)),
            "high"
        )

    if old_errors and not current_errors:
        send(
            "AI Turbo Monitor: Entwarnung",
            "Alle zuvor gemeldeten Kursdatenfehler sind behoben.",
            "default"
        )

    next_state["_api_errors"] = sorted(current_errors)


def analyze(asset):
    symbol = asset["symbol"]
    df = yf.Ticker(symbol).history(period="5d", interval="5m", auto_adjust=True, prepost=False)
    if df.empty:
        raise RuntimeError("Keine Kursdaten")
    closes = df["Close"].dropna().astype(float)
    if len(closes) < 30:
        raise RuntimeError("Zu wenige 5-Minuten-Kerzen")
    e9 = closes.ewm(span=9, adjust=False).mean()
    e21 = closes.ewm(span=21, adjust=False).mean()
    change = closes.diff()
    gains = change.clip(lower=0)
    losses = -change.clip(upper=0)
    ag = float(gains.ewm(alpha=1/14, adjust=False, min_periods=14).mean().iloc[-1])
    al = float(losses.ewm(alpha=1/14, adjust=False, min_periods=14).mean().iloc[-1])
    rsi = 100 if al == 0 and ag > 0 else (50 if al == 0 else 100 - 100 / (1 + ag/al))
    price = float(closes.iloc[-1])
    up = bool(e9.iloc[-2] <= e21.iloc[-2] and e9.iloc[-1] > e21.iloc[-1])
    down = bool(e9.iloc[-2] >= e21.iloc[-2] and e9.iloc[-1] < e21.iloc[-1])
    trend = "Bullisch" if e9.iloc[-1] > e21.iloc[-1] else "Bärisch"
    signals = []
    if up:
        signals.append("EMA 9 kreuzt EMA 21 nach oben")
    if down:
        signals.append("EMA 9 kreuzt EMA 21 nach unten")
    if rsi >= 70:
        signals.append("RSI überkauft (≥70)")
    elif rsi <= 30:
        signals.append("RSI überverkauft (≤30)")
    if not signals:
        signals.append("Kein neues EMA-Kreuz; " + trend.lower() + "er EMA-Trend")
    result = {
        "id": asset["id"], "name": asset["name"], "symbol": symbol,
        "type": asset["type"], "price": round(price, 4),
        "ema9": round(float(e9.iloc[-1]), 4), "ema21": round(float(e21.iloc[-1]), 4),
        "rsi": round(rsi, 2), "trend": trend, "signal": " · ".join(signals),
        "asof": closes.index[-1].isoformat(),
        "source": "Yahoo Finance über yfinance (inoffiziell; ggf. verzögert)",
        "interval": "5m", "history": [round(float(x), 3) for x in closes.tail(60)]
    }
    if asset["type"] == "turbo":
        if asset.get("direction") != "long":
            raise ValueError("Version 1.3 unterstützt nur Long-Turbos")
        ko = float(asset["knockout_usd"])
        warn = float(asset.get("warning_pct", 7))
        critical = float(asset.get("critical_pct", 3))
        if not (ko > 0 and warn > critical > 0):
            raise ValueError("Ungültige KO- oder Warnschwellen")
        pct = (price - ko) / price * 100
        zone = "KO" if price <= ko else "critical" if pct <= critical else "warning" if pct <= warn else "normal"
        result.update({
            "isin": asset.get("isin"), "knockout": ko,
            "distance_pct": round(pct, 3), "zone": zone,
            "warning_pct": warn, "critical_pct": critical,
            "knockout_note": asset.get("knockout_note", "")
        })
    else:
        result["zone"] = "normal"
    return result, up, down


def rsi_zone(rsi):
    if rsi >= 70:
        return "overbought"
    if rsi <= 30:
        return "oversold"
    return "normal"


def main():
    
    if os.getenv("TEST_NTFY", "0") == "1":
        if not os.getenv("NTFY_TOPIC", "").strip():
            raise RuntimeError("NTFY_TOPIC fehlt: Testnachricht nicht gesendet")

        send(
            "AI Turbo Monitor Test",
            "Test erfolgreich: GitHub Actions kann ntfy-Nachrichten versenden.",
            "default"
        )
        print("ntfy-Testnachricht erfolgreich versendet")
        return

    assets = json.loads(CONFIG.read_text(encoding="utf-8"))["assets"]
    if not assets:
        raise ValueError("Keine Wertpapiere konfiguriert")
    ids = [a["id"] for a in assets]
    if len(set(ids)) != len(ids):
        raise ValueError("Doppelte Asset-IDs")
    DATA_DIR.mkdir(exist_ok=True)
    previous = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    next_state = dict(previous)
    results, errors = [], []
    alerts = 0
    for asset in assets:
        if not asset.get("enabled", True):
            continue
        key = asset["id"]
        try:
            result, up, down = analyze(asset)
            results.append(result)
            old = previous.get(key, {})
            state = dict(old)
            zone = result["zone"]
            candle = result["asof"]
            rzone = rsi_zone(result["rsi"])
            # State is saved after each successful send, even if a later send fails.
            # If a send fails, its state is not advanced and it can be retried.
            if asset["type"] == "turbo" and zone != "normal" and zone != state.get("zone"):
                send(
                    f"{asset['symbol']} Turbo {zone.upper()}",
                    f"{asset['name']} | {result['price']:.2f} USD | KO {result['knockout']:.2f} USD | Abstand {result['distance_pct']:.2f}% | ISIN {asset.get('isin', '')}",
                    "urgent" if zone in ("KO", "critical") else "high"
                )
                alerts += 1
                state["zone"] = zone
                next_state[key] = dict(state)
                STATE.write_text(json.dumps(next_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            else:
                state["zone"] = zone
            if (up or down) and state.get("cross_candle") != candle:
                direction = "AUFWÄRTS" if up else "ABWÄRTS"
                send(
                    f"EMA {direction}: {asset['symbol']}",
                    f"{asset['name']} | EMA 9/21 Kreuz ({direction}) | Kurs {result['price']:.2f} USD | Kerze {candle} | Technisches Signal, keine Handelsempfehlung",
                    "default"
                )
                alerts += 1
                state["cross_candle"] = candle
                next_state[key] = dict(state)
                STATE.write_text(json.dumps(next_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            if rzone != "normal" and rzone != state.get("rsi_zone"):
                label = "ÜBERKAUFT" if rzone == "overbought" else "ÜBERVERKAUFT"
                send(
                    f"RSI {label}: {asset['symbol']}",
                    f"{asset['name']} | RSI 14: {result['rsi']:.1f} | Kurs {result['price']:.2f} USD | {candle} | Technisches Signal, keine Handelsempfehlung",
                    "default"
                )
                alerts += 1
            state["rsi_zone"] = rzone
            next_state[key] = state
            STATE.write_text(json.dumps(next_state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except Exception as exc:
            errors.append(f"{key}: {exc}")
            print(f"ERROR {key}: {exc}")
    
    notify_data_errors(errors, previous, next_state)

    if not results:
        STATE.write_text(
            json.dumps(next_state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8"
        )
        raise RuntimeError(
            "Keine gültigen Kursdaten: " + "; ".join(errors)
        )

    MULTI.write_text(json.dumps({"version": "1.3", "assets": results, "errors": errors}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ttwo = next((r for r in results if r["id"] == "ttwo-turbo"), None)
    if ttwo:
        LEGACY.write_text(json.dumps(ttwo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"assets_ok": len(results), "errors": errors, "alerts": alerts}, ensure_ascii=False))
    if errors:
        raise RuntimeError("Teilweise fehlgeschlagen: " + "; ".join(errors))



if __name__ == "__main__":
    if os.getenv("TEST_NTFY") == "1":
        send(
            "AI Turbo Monitor 1.3 TEST",
            "Dies ist eine Testnachricht. "
            "Keine echte Kauf- oder Verkaufsempfehlung.",
            "default"
        )
        print("NTFY_TEST_OK")
    else:
        main()
  
