import json, os, pathlib, datetime, requests
import pandas as pd
import yfinance as yf

ROOT=pathlib.Path(__file__).parent
DATA=ROOT/'data'/'latest.json'
STATE=ROOT/'data'/'alert_state.json'
SYMBOL='TTWO'
KO=float(os.getenv('KNOCKOUT_USD') or '213.47')
WARN=float(os.getenv('WARN_PCT') or '7')
CRITICAL=float(os.getenv('CRITICAL_PCT') or '3')

def send(title,message,priority='default',tag='warning'):
    topic=os.getenv('NTFY_TOPIC','').strip()
    if not topic:return
    server=os.getenv('NTFY_SERVER','https://ntfy.sh').rstrip('/')
    headers={'Title':title,'Priority':priority,'Tags':tag}
    token=os.getenv('NTFY_TOKEN','').strip()
    if token:headers['Authorization']='Bearer '+token
    requests.post(f'{server}/{topic}',data=message.encode(),headers=headers,timeout=15).raise_for_status()

def main():
    if CRITICAL<=0 or WARN<=CRITICAL:raise ValueError('WARN_PCT muss größer als CRITICAL_PCT > 0 sein')
    ticker=yf.Ticker(SYMBOL)
    df=ticker.history(period='5d',interval='5m',auto_adjust=True,prepost=False)
    if df.empty or len(df)<30:raise RuntimeError('Nicht genügend 5-Minuten-Kursdaten')
    closes=df['Close'].dropna().astype(float)
    # EMA 9/21, Wilder RSI 14 auf Schlusskursen der 5-Minuten-Kerzen
    ema9=closes.ewm(span=9,adjust=False).mean()
    ema21=closes.ewm(span=21,adjust=False).mean()
    diff=closes.diff();gain=diff.clip(lower=0);loss=-diff.clip(upper=0)
    avg_gain=gain.ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    avg_loss=loss.ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    ag=float(avg_gain.iloc[-1]);al=float(avg_loss.iloc[-1]);rsi=100 if al==0 and ag>0 else (50 if al==0 else 100-100/(1+ag/al))
    price=float(closes.iloc[-1]);pct=(price-KO)/price*100
    trend='Bullisch' if ema9.iloc[-1]>ema21.iloc[-1] else 'Bärisch'
    crossed_up=ema9.iloc[-2]<=ema21.iloc[-2] and ema9.iloc[-1]>ema21.iloc[-1]
    crossed_down=ema9.iloc[-2]>=ema21.iloc[-2] and ema9.iloc[-1]<ema21.iloc[-1]
    signals=[]
    if crossed_up:signals.append('EMA 9 kreuzt EMA 21 nach oben')
    if crossed_down:signals.append('EMA 9 kreuzt EMA 21 nach unten')
    if rsi>=70:signals.append('RSI überkauft (≥70)')
    elif rsi<=30:signals.append('RSI überverkauft (≤30)')
    if not signals:signals=['Kein neues EMA-Kreuz; '+trend.lower()+'er EMA-Trend']
    asof=closes.index[-1].to_pydatetime().isoformat()
    payload={'symbol':SYMBOL,'price':round(price,4),'knockout':KO,'distance_pct':round(pct,3),'ema9':round(float(ema9.iloc[-1]),4),'ema21':round(float(ema21.iloc[-1]),4),'rsi':round(rsi,2),'trend':trend,'signal':' · '.join(signals),'asof':asof,'source':'Yahoo Finance über yfinance (inoffiziell; ggf. verzögert)','interval':'5m','history':[round(float(x),3) for x in closes.tail(60)]}
    DATA.parent.mkdir(exist_ok=True)
    DATA.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
    previous=json.loads(STATE.read_text()) if STATE.exists() else {}
    zone='KO' if price<=KO else 'critical' if pct<=CRITICAL else 'warning' if pct<=WARN else 'normal'
    candle=asof
    notifications=[]
    # Warnung nur beim Eintritt in neue Risikostufe; Kreuz nur einmal je Kerze
    if zone!=previous.get('zone') and zone!='normal':
        notifications.append(('KO-ALARM' if zone=='KO' else 'Turbo Risiko '+zone.upper(),f'TTWO {price:.2f} USD | KO {KO:.2f} USD | Abstand {pct:.2f}%','urgent' if zone in ('KO','critical') else 'high'))
    if (crossed_up or crossed_down) and previous.get('cross_candle')!=candle:
        notifications.append(('EMA Signal TTWO',signals[0]+' | Kurs '+f'{price:.2f} USD','default'))
    # Zustellfehler nicht verschweigen: Action wird fehlschlagen und kann erneut gestartet werden.
    for title,msg,priority in notifications:send(title,msg,priority)
    STATE.write_text(json.dumps({'zone':zone,'cross_candle':candle if (crossed_up or crossed_down) else previous.get('cross_candle')},indent=2)+'\n')
    print(json.dumps({'price':price,'ko_distance_pct':pct,'zone':zone,'alerts':len(notifications),'asof':asof}))

if __name__=='__main__':main()
