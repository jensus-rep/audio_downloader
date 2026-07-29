# Geschützter Uni-Audio-Downloader

Dieses Python-Tool öffnet eine Kurs- oder Podcast-Seite mit Playwright,
meldet sich mit lokal hinterlegten Uni-Zugangsdaten an und lädt verlinkte
MP3-, WAV-, M4A- und OGG-Dateien in den Ordner `downloads`.

Das Tool umgeht keine Zugriffsbeschränkungen. Es darf ausschließlich für
Inhalte verwendet werden, auf die der verwendete Account regulär zugreifen
darf. Captchas, Mehrfaktor-Anmeldung und andere Schutzmechanismen werden nicht
umgangen.

## Installation

Python 3.10 oder neuer wird empfohlen.

```powershell
cd audio_downloader
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
```

Unter macOS oder Linux wird die virtuelle Umgebung so aktiviert:

```bash
source .venv/bin/activate
```

## Einrichtung der `.env`

Die Beispieldatei kopieren:

```powershell
Copy-Item .env.example .env
```

Danach `.env` anpassen:

```dotenv
UNI_USERNAME=meinekennung
UNI_PASSWORD=meinpasswort
LOGIN_URL=https://uni.example.com/login
USERNAME_SELECTOR=input[name="username"]
PASSWORD_SELECTOR=input[name="password"]
LOGIN_BUTTON_SELECTOR=button[type="submit"]
```

Die Datei `.env` ist in `.gitignore` eingetragen und darf nicht in ein
Repository eingecheckt werden. Zugangsdaten werden ausschließlich lokal an
die konfigurierte Uni-Seite übermittelt.

### Login-Selektoren

Die drei Selektoren müssen zur Login-Seite passen:

- `USERNAME_SELECTOR`: Eingabefeld für die Kennung
- `PASSWORD_SELECTOR`: Passwortfeld
- `LOGIN_BUTTON_SELECTOR`: Absende-Button

Optional kann `LOGGED_IN_SELECTOR` auf ein Element gesetzt werden, das nur
nach erfolgreichem Login sichtbar ist, beispielsweise einen Logout-Link.
`LOGIN_SUCCESS_URL_PATTERN` kann zusätzlich die URL nach dem Login prüfen.

Falls die Selektoren zunächst untersucht werden müssen, kann der Browser
sichtbar gestartet werden:

```powershell
python main.py --headed "https://uni.example.com/kurs/podcastseite"
```

## Start

```powershell
python main.py "https://uni.example.com/kurs/podcastseite"
```

Um alle Moodle-Abschnitte eines Kurses zu durchsuchen:

```powershell
python main.py --course-wide "https://uni.example.com/course/view.php?id=301"
```

GUI starten:

```powershell
python main.py --gui
```

Oder direkt:

```powershell
python gui.py
```

Das Tool:

1. öffnet zunächst die Zielseite,
2. erkennt dort ein Login-Formular oder öffnet die konfigurierte Login-URL,
3. meldet sich mit den Werten aus `.env` an,
4. sammelt Audio-Links aus Links, Audio-/Source-Elementen und geladenen
   Audio-Netzwerkantworten,
5. lädt die Dateien mit der authentifizierten Browser-Session herunter,
6. überspringt bereits existierende Dateien und
7. zeigt eine Zusammenfassung an.

Einzelne Fehler stoppen den Gesamtlauf nicht. Fehlgeschlagene URLs werden in
`failed_downloads.txt` geschrieben.

## Konfiguration

| Variable | Standard | Bedeutung |
| --- | --- | --- |
| `HEADLESS` | `true` | Browser unsichtbar starten |
| `LOGIN_TIMEOUT_MS` | `30000` | Login-Timeout in Millisekunden |
| `PAGE_TIMEOUT_MS` | `30000` | Seiten-Timeout in Millisekunden |
| `DOWNLOAD_TIMEOUT_MS` | `120000` | Download-Timeout in Millisekunden |
| `DOWNLOAD_DIR` | `downloads` | Zielordner |
| `FAILED_DOWNLOADS_FILE` | `failed_downloads.txt` | Fehlerprotokoll |

## Grenzen

- Captchas und Mehrfaktor-Anmeldungen werden nicht automatisiert.
- Audio-Endpunkte ohne Dateiendung werden nur erkannt, wenn die Seite sie beim
  Laden bereits als `audio/*`-Netzwerkantwort abruft.
- Bei Single-Sign-on-Seiten können abweichende Selektoren oder zusätzliche
  reguläre Login-Schritte erforderlich sein.
