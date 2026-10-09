from __future__ import annotations

import argparse
import sys

from runner import RunOptions, run_download_job


def configure_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Lädt Audio-Dateien aus einer zugriffsgeschützten Webseite herunter."
    )
    parser.add_argument("url", nargs="?", help="URL der Kurs- oder Podcast-Seite")
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Browser sichtbar starten (hilfreich beim Anpassen der Selektoren)",
    )
    parser.add_argument(
        "--course-wide",
        action="store_true",
        help="Alle Moodle-Abschnitte des Kurses nach Audio-Dateien durchsuchen",
    )
    parser.add_argument(
        "--export",
        action="store_true",
        help="Ganzen Kurs erfassen: Inventar, Texte, Dateien und Medienverweise",
    )
    parser.add_argument(
        "--manual-login",
        action="store_true",
        help="Im sichtbaren Browserfenster selbst anmelden; keine Zugangsdaten nötig",
    )
    parser.add_argument(
        "--with-media",
        action="store_true",
        help="Beim Erfassen auch Audio- und Videodateien aus dem Kurs herunterladen",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Kleines Desktop-Interface starten",
    )
    return parser.parse_args()


def main() -> int:
    configure_console_encoding()
    args = parse_args()

    if args.gui:
        from gui import launch_gui

        launch_gui()
        return 0

    if not args.url:
        print("Bitte eine URL angeben oder --gui verwenden.", file=sys.stderr)
        return 2

    result = run_download_job(
        RunOptions(
            url=args.url,
            course_wide=args.course_wide,
            headed=args.headed,
            mode="export" if args.export else "audio",
            manual_login=args.manual_login,
            with_media=args.with_media,
        ),
        log=print,
    )

    if result.config_error:
        print(f"Konfigurationsfehler: {result.config_error}", file=sys.stderr)
        return 2
    if result.login_error:
        print(f"Login fehlgeschlagen: {result.login_error}", file=sys.stderr)
        return 3
    if result.unexpected_error:
        print(f"Unerwarteter Fehler: {result.unexpected_error}", file=sys.stderr)
        return 1
    return 1 if result.summary and result.summary.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
