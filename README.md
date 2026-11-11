# AI Daily Trader 1.0

Eine **Signal-App**, kein Echtgeld-Trading-Bot. Prüft NYSE-Handelstage, analysiert NVDA, AMD, MSFT, TSLA, AAPL, SPCX (SpaceX) und TTWO (Take-Two Interactive) anhand von täglichen Schlusskursen und verschickt optional ntfy-Push-Nachrichten. Enthält **keine Brokeranbindung** und **keine Orderfunktion**. Die Regeln sind **nicht backgetestet** und keine Kaufempfehlungen. „AI“ ist ein Produktname, es wird derzeit **kein KI-Modell** verwendet.

## GitHub Actions Einrichtung

1. Neues privates GitHub-Repository erstellen oder die Dateien in dein bestehendes Repository übernehmen. Beim Übernehmen die `.github/workflows/daily-trader.yml` beachten; sie ist ein eigener Workflow.
2. Repository-Dateien inklusive `.github/workflows/daily-trader.yml` hochladen.
3. Unter `Settings > Secrets and variables > Actions > New repository secret` einen Secret `NTFY_TOPIC` mit dem **reinen Themennamen** deiner bestehenden ntfy-Verbindung anlegen. Niemals Geheimnisse im Code speichern.
4. `Actions > AI Daily Trader signals > Run workflow` zum Test ausführen.
5. Unter `Actions` sind Protokolle und das JSON-Ergebnis als Artefakt zu finden.

## Zeit

Geplant: 21:15 UTC Montag–Freitag, entsprechend 22:15 Uhr in deutscher Winterzeit und 23:15 Uhr in Sommerzeit. Der Lauf ist nach dem regulären US-Börsenschluss. GitHub-Schedules können sich verzögern; Feiertage werden übersprungen. Historische Tagesdaten sind keine Echtzeit-Quotes. Sollte ein Kursanbieter noch nicht aktualisiert haben, kann der angegebene Schlusskurs vom Vortag stammen; stets `last_data_date` prüfen.

## Signalregeln (nur Demonstration)

- Beobachten LONG: Schlusskurs > SMA20 > SMA50, RSI14 von 50 bis 68, aktueller Schlusskurs über Vortag.
- Warnung: Schlusskurs unter SMA20 und RSI14 unter 45.
- Sonst kein Signal.

Diese Regeln sagen **nicht** zuverlässig Gewinne voraus. Auch wenn es ein Signal gibt, erfolgt **nie ein Trade**. Keine Hebelprodukte empfohlen.

## Lokal testen

```bash
pip install -r requirements.txt
python trader.py
```

Optional: `NTFY_TOPIC` als Umgebungsvariable setzen. Der Bot schreibt `output/latest.json`.

## Vor echtem Handel notwendig

Backtest ohne Lookahead, Out-of-sample-Test, Paper-Trading, Transaktionskosten & Spreads, Risikolimits, Order-Statusabgleich, Authentifizierung für eine offizielle Broker-API, Kill-Switch, Logging, Datenqualitätsprüfungen und gesonderte Aktivierung erst nach ausführlicher Prüfung.

## Erweiterung: SpaceX und Take-Two

- `SPCX` ist die seit Juni 2026 börsennotierte SpaceX-Stammaktie.
- `TTWO` ist die Take-Two-Interactive-Stammaktie. **Dies ist nicht der Kurs eines Take-Two-Long-Turbo-Zertifikats.** Ein Hebelprodukt benötigt eine eigene ISIN/WKN, eigene Kursdaten und eigenständige Risikoregeln.
- Bei fehlenden Kursdaten erscheint ein Fehler im JSON/ntfy-Report; der Bot erfindet keinen Kurs.
- Prüfe Kursdatum und Datenanbieter vor jeder manuellen Entscheidung.

## Version 1.2: Turbo-Warnmonitor FB00U4 (ISIN DE000FB00U40)

**Keine echten Orders.** `turbo_monitor.py` und `.github/workflows/turbo-monitor.yml` ergänzen die bestehende Aktienanalyse. Beide Workflows laufen getrennt.

- Position: **232** Stück, Einstand **1,023 €**, gewünschter Ziel-**Geldkurs** **1,40 €**.
- Long-Turbo auf **TTWO**, Knock-out **213,4700 USD** als **Referenzwert vom 11.11.2026**. Eine Open-End-KO-Barriere kann sich verändern. **Keine aktuelle Barriere verifiziert**, solange der Quote-Feed keine `ko_usd` liefert. Die App kennzeichnet das explizit.
- Prüft in den regulären US-Börsenzeiten die zeitliche Aktualität von TTWO-Minutenkursen (<= 10 Min), berechnet einen indikativen Abstand zur KO-Barriere und meldet Unterschreiten von **5 %** oder **3 %** sowie Kurs unter/bei der Barriere. Ein bereits erfolgter Knock-out kann nicht durch diese Überwachung verhindert oder zuverlässig erkannt werden.
- **Ziel 1,40 €** wird **nur** geprüft, wenn ein autorisierter, aktueller **Zertifikat-Geldkurs** als EUR-Wert vorliegt. Ohne Feed **keine erfundene Preiswarnung**. Es gibt bewusst keine direkte, unbestätigte HTML-Preis-Scraping-Lösung.
- GitHub Actions plant alle 30 Min US-Handelszeiten. **Nicht sekündlich / nicht garantiert pünktlich / kein Stop-Loss-Ersatz.** Bei kritischem Abstand kann pro Lauf erneut eine Warnung erscheinen. Kein persistenter Benachrichtigungs-Deduplizierer.

### Einrichtung

1. Neue Dateien `turbo_monitor.py` und `.github/workflows/turbo-monitor.yml` ins **bestehende** GitHub-Repository übertragen, ursprüngliche Dateien erhalten.
2. `Settings > Secrets and variables > Actions`: bestehendes `NTFY_TOPIC` verwenden. Es enthält ausschließlich den ntfy-Themennamen.
3. Optional: `TURBO_QUOTE_URL` als Secret einer von dir autorisierten HTTPS-JSON-Datenquelle setzen, die den **handelsfähigen Geldkurs des Zertifikats** liefert. Bei Bedarf `TURBO_QUOTE_TOKEN` als weiteres Secret setzen. Ohne Quelle gibt es keine 1,40-€-Prüfung.
4. `Actions > Take-Two Turbo FB00U4 warnings > Run workflow` starten. Bei geschlossenem NYSE-Handel wird nur `OUTSIDE_US_REGULAR_SESSION` protokolliert. Im Handel werden die Daten geprüft und ggf. Push gesendet.
5. Die JSON-Ergebnisse als GitHub-Artifact `turbo-warning-*` ansehen. Bei Datenfehlern erscheinen deutliche Hinweise statt vermeintlicher Entwarnung.

Erwartetes JSON der **optionalen** HTTPS-Quote-API (Felder sind verbindlich, `ko_usd` optional):

```json
{
  "isin": "DE000FB00U40",
  "currency": "EUR",
  "bid_eur": 1.40,
  "timestamp": "2026-11-11T15:00:00+00:00",
  "source": "Authorized issuer quote feed",
  "ko_usd": 213.47
}
```

Der Zeitstempel muss innerhalb der letzten 5 Minuten liegen, die ISIN muss exakt passen. Ein Geldkurs ist nicht garantiert handelbar und kann zwischen Hinweis und manueller Order ändern. Quote-Feed **nicht** nur anhand dieses Beispiels als aktuell einstufen.
