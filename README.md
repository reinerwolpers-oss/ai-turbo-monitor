# AI Turbo Monitor 1.0

Installierbare iPhone-Web-App (PWA) mit TTWO-Überwachung, EMA 9/21, RSI 14, Knock-out-Abstand und ntfy-Benachrichtigungen.

## 1. GitHub Repository

Neues **öffentliches** Repository `ai-turbo-monitor` erstellen. Den Inhalt dieses ZIP-Archivs ins Stammverzeichnis hochladen, **einschließlich `.github/workflows/monitor.yml`**. Am einfachsten: ZIP lokal entpacken und mit Git committen/pushen, damit der versteckte `.github`-Ordner erhalten bleibt. Alternativ die Dateien über GitHub einzeln hochladen und die Workflow-Datei unter dem exakten Pfad erstellen.

## 2. Secrets und Variables

GitHub → Repository → Settings → Secrets and variables → Actions.

Unter **Secrets**:
- `NTFY_TOPIC` = bestehendes privates ntfy-Topic (nicht ins Repository schreiben!)
- `NTFY_TOKEN` = optional, nur bei authentifiziertem ntfy-Server nötig

Unter **Variables**:
- `KNOCKOUT_USD` = `213.47` (vor Nutzung mit Emittentenangaben aktualisieren)
- `WARN_PCT` = `7`
- `CRITICAL_PCT` = `3`
- `NTFY_SERVER` = `https://ntfy.sh` (nur ändern, wenn eigener Server)

## 3. Action testen

Repository → Actions → **AI Turbo Monitor** → **Run workflow**. Nach Abschluss unter `data/latest.json` die Kursdaten prüfen. Falls ein Fehler auftritt, Action-Protokoll lesen. Der Datenanbieter ist inoffiziell und kann Daten verzögert liefern oder zeitweise ausfallen. GitHub-Schedules können verspätet oder ausgelassen werden; keine Echtzeitgarantie.

**ntfy-Test:** Eine Risikowarnung wird nur bei neuem Eintritt in die Warnzone ausgelöst. Um die Zustellung unabhängig vom aktuellen Kurs zu testen, den folgenden manuellen Befehl lokal mit deinem Topic verwenden:
`curl -d 'AI Turbo Monitor Test' https://ntfy.sh/DEIN_TOPIC`
Bei authentifiziertem Server zusätzlich einen Bearer-Token nutzen. Das Topic nicht öffentlich teilen.

## 4. GitHub Pages

Settings → Pages → Build and deployment → Deploy from a branch → `main` / `(root)` → Save. Danach die veröffentlichte URL öffnen: `https://DEIN-NAME.github.io/ai-turbo-monitor/`.

Auf dem iPhone in **Safari** öffnen → Teilen → **Zum Home-Bildschirm** → Hinzufügen.

## 5. Wichtige Grenzen

- Die Zertifikatsposition (327,70 €, +10,42 %, Hebel 17,72) stammt aus Screenshots und ist **nicht live**.
- Die KO-Schwelle 213,47 USD ist ebenfalls ein Screenshot-Wert und muss laufend gegen die offiziellen Produktdaten geprüft werden.
- Die App berechnet den KO-Abstand aus dem Aktienkurs, nicht aus einem Zertifikatskurs.
- RSI und EMA beruhen auf 5-Minuten-Kerzen; Signale sind keine Handelsempfehlung.
- Die Anzeige aktualisiert bei geöffneter App minütlich die zuletzt veröffentlichte JSON-Datei; das Backend ist auf 5 Minuten geplant, aber nicht garantiert.
- Ohne aktiven GitHub-Actions-Workflow und Datenquelle gibt es keine laufenden Updates oder Push-Warnungen.
- GitHub Pages und das Repository sind öffentlich; **niemals Secrets in Code oder JSON schreiben**.
- Bei Ausfall der Datenquelle oder der Action gibt es möglicherweise **keine Warnung**. Das ist kein verlässlicher Stop-Loss-Ersatz.
- Öffentliche Repositories mit häufigen automatisch erzeugten Commits sind technisch einfach, aber erzeugen viel Git-Historie. Für längeren Betrieb kann man einen externen Datenspeicher ergänzen.
