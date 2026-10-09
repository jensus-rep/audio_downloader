# Geschützter Uni-Audio-Downloader

Dieses Python-Tool öffnet eine Kurs- oder Podcast-Seite mit Playwright,
meldet sich mit lokal hinterlegten Uni-Zugangsdaten an und lädt verlinkte
MP3-, WAV-, M4A- und OGG-Dateien in den Ordner `downloads`.

Zusätzlich kann es einen Moodle-Kurs **vollständig erfassen**: Es legt ein
Inventar aller Aktivitäten an und speichert Texte, Dateien und Verweise auf
Medien, damit beim Lernen keine Inhalte übersehen werden (siehe
[Kurs vollständig erfassen](#kurs-vollständig-erfassen)).

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

Unter Windows kann die Anwendung nach der Installation auch per Doppelklick
auf `Audio-Downloader starten.bat` geöffnet werden.

In der Oberfläche werden Kurs-URL, Zugangsdaten und Download-Ordner direkt
eingegeben. Die Zugangsdaten werden dabei nur für den aktuellen Lauf verwendet
und nicht von der Anwendung gespeichert. Eine vorhandene lokale `.env` dient
weiterhin als optionale Vorbelegung.

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

## Kurs vollständig erfassen

```powershell
python main.py --export --manual-login "https://moodle.example.com/course/view.php?id=301"
```

Mit `--manual-login` öffnet sich ein Browserfenster; du meldest dich dort
selbst an, und das Tool arbeitet danach mit dieser Sitzung weiter.
Zugangsdaten werden dafür weder benötigt noch gespeichert. Ohne den Schalter
gilt die Anmeldung über `.env` wie beim Audio-Download. In der Oberfläche
heißt der Modus „Kurs erfassen“.

Das Tool geht die Kursseite und alle Abschnitte durch und behandelt jede
Aktivität nach ihrem Typ:

| Typ | Was erfasst wird |
| --- | --- |
| Textfeld (`label`), Abschnittsbeschreibung | Text direkt von der Kursseite |
| Seite, H5P, Glossar, Wiki | Text der Seite als Markdown, eingebettete Medien als Verweis |
| Buch | alle Kapitel über die Druckansicht |
| Datei, Verzeichnis | Dateien herunterladen; Text aus PDF, PowerPoint und Word ziehen |
| Link | Zieladresse |
| Test, Abgabe, Forum, Lektion, SCORM, Umfrage u. a. | **nur gelistet, nie geöffnet** |

Tests und andere Aktivitäten, die beim Öffnen einen Versuch starten oder etwas
speichern könnten, werden bewusst nicht aufgerufen. Das schützt zum Beispiel
einen Abschlusstest, der nur einmal geöffnet werden darf. Das Tool sendet nur
GET-Anfragen und folgt keinen Links aus dem Kurs heraus.

Ergebnis in `exports/kurs-<id>/`:

- `inventar.md`: Übersicht aller Aktivitäten nach Abschnitt, LV-Nummern mit
  Lücken, nicht erfasste Aktivitäten und gefundene Medien
- `inventar.json`: dieselben Daten maschinenlesbar
- `texte/`: ein Markdown-Text je Aktivität, `00_abschnitte.md` mit den
  Abschnittsbeschreibungen, `texte/dateien/` mit dem Text der Dateien
- `dateien/`: heruntergeladene Dateien
- `medien/`: Audio und Video, nur mit `--with-media`

Mit `--with-media` holt das Tool außerdem für eingebettete **Vimeo-Videos** in der angemeldeten Sitzung die
deutschen Untertitel (`medien/vimeo_<id>_<titel>.vtt`) oder, wenn es keine gibt, die Tonspur (`.m4a`). Die Übersicht
steht in `medien/vimeo.json`. Eingebettete Videos sind meist nur aus dem Kurs heraus abspielbar; deshalb geschieht das
auf der Kursseite selbst. Externe YouTube-Videos werden nur gelistet.

## Transkribieren

```powershell
.\.venv\Scripts\python transcribe.py exports\kurs-<id>\medien --out <zielordner> --resource <azure-ressource> --resource-group <gruppe>
```

Audio und Video gehen an Azure AI Speech (Fast Transcription, de-DE); der Schlüssel wird zur Laufzeit über die Azure
CLI gelesen (`az login`) oder aus `AZURE_SPEECH_KEY`/`AZURE_SPEECH_ENDPOINT` übernommen und nie gespeichert. Untertitel
(`.vtt`) werden ohne Azure umgewandelt. Je Datei entsteht ein Markdown-Transkript mit Zeitmarken `[mm:ss]`, dazu
`transcripts.json`. Bereits transkribierte Dateien werden übersprungen.

Wie daraus Lernkarten und Testaufgaben im Second Brain werden, beschreibt `tools/lernpaket/README.md` im Repo
`second-brain`.

Tests laufen gegen einen nachgebauten Kurs auf localhost:

```powershell
.\.venv\Scripts\python -m unittest discover -s tests
```

## Konfiguration

| Variable | Standard | Bedeutung |
| --- | --- | --- |
| `HEADLESS` | `true` | Browser unsichtbar starten |
| `LOGIN_TIMEOUT_MS` | `30000` | Login-Timeout in Millisekunden |
| `PAGE_TIMEOUT_MS` | `30000` | Seiten-Timeout in Millisekunden |
| `DOWNLOAD_TIMEOUT_MS` | `120000` | Download-Timeout in Millisekunden |
| `DOWNLOAD_DIR` | `downloads` | Zielordner |
| `FAILED_DOWNLOADS_FILE` | `failed_downloads.txt` | Fehlerprotokoll |
| `EXPORT_DIR` | `exports` | Zielordner für „Kurs erfassen“ |
| `REQUEST_DELAY_MS` | `300` | Pause zwischen zwei Seitenaufrufen |
| `MANUAL_LOGIN_TIMEOUT_MS` | `300000` | Wartezeit für die Anmeldung im Browserfenster |
| `BROWSER_CHANNEL` | leer | `chrome` nutzt ein installiertes Chrome statt Playwright-Chromium |

## Grenzen

- Captchas und Mehrfaktor-Anmeldungen werden nicht automatisiert.
- Audio-Endpunkte ohne Dateiendung werden nur erkannt, wenn die Seite sie beim
  Laden bereits als `audio/*`-Netzwerkantwort abruft.
- Bei Single-Sign-on-Seiten können abweichende Selektoren oder zusätzliche
  reguläre Login-Schritte erforderlich sein.
