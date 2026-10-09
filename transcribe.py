"""Transkribiert Audio-Dateien mit Azure AI Speech (Fast Transcription).

Aufruf:
    python transcribe.py <audio-ordner> --out <ziel-ordner> --resource <name> --resource-group <rg>

Der Schlüssel wird zur Laufzeit über die Azure CLI gelesen (`az login` vorausgesetzt) oder aus
AZURE_SPEECH_KEY und AZURE_SPEECH_ENDPOINT übernommen. Er wird weder gespeichert noch ausgegeben.

Je Datei entstehen <name>.json (Rohantwort) und <name>.md. Zusätzlich fasst transcripts.json alle
Transkripte als Liste {number, title, text} zusammen, im selben Format wie frühere Importe.
Bereits transkribierte Dateien werden übersprungen.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import requests

API_VERSION = "2024-11-15"
AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".ogg", ".mp4", ".webm"}
SEGMENT_SECONDS = 25


def azure_credentials(resource: str | None, group: str | None) -> tuple[str, str]:
    key = os.getenv("AZURE_SPEECH_KEY")
    endpoint = os.getenv("AZURE_SPEECH_ENDPOINT")
    if key and endpoint:
        return endpoint.rstrip("/"), key
    if not resource or not group:
        raise SystemExit("Bitte --resource und --resource-group angeben oder AZURE_SPEECH_KEY/-ENDPOINT setzen.")
    az = "az.cmd" if os.name == "nt" else "az"
    endpoint = subprocess.run(
        [az, "cognitiveservices", "account", "show", "-n", resource, "-g", group, "--query", "properties.endpoint", "-o", "tsv"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    key = subprocess.run(
        [az, "cognitiveservices", "account", "keys", "list", "-n", resource, "-g", group, "--query", "key1", "-o", "tsv"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    return endpoint.rstrip("/"), key


def transcribe_file(path: Path, endpoint: str, key: str, locale: str) -> dict:
    url = f"{endpoint}/speechtotext/transcriptions:transcribe?api-version={API_VERSION}"
    definition = {"locales": [locale], "profanityFilterMode": "None"}
    response = None
    for attempt in range(4):
        try:
            with path.open("rb") as audio:
                response = requests.post(
                    url,
                    headers={"Ocp-Apim-Subscription-Key": key},
                    files={"audio": (path.name, audio), "definition": (None, json.dumps(definition), "application/json")},
                    timeout=1800,
                )
        except requests.exceptions.ConnectionError as exc:
            if attempt == 3:
                raise RuntimeError(f"Verbindung abgebrochen: {exc}") from exc
            time.sleep(10 * (attempt + 1))
            continue
        if response.status_code == 429 or response.status_code >= 500:
            time.sleep(10 * (attempt + 1))
            continue
        if not response.ok:
            raise RuntimeError(f"HTTP {response.status_code}: {response.text[:300]}")
        return response.json()
    raise RuntimeError(f"HTTP {response.status_code if response is not None else '–'} nach mehreren Versuchen")


def stamp(milliseconds: int) -> str:
    seconds = int(milliseconds // 1000)
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def segments(result: dict) -> list[tuple[int, str]]:
    """Group recognized phrases into paragraphs of about SEGMENT_SECONDS."""
    grouped: list[tuple[int, str]] = []
    start, texts = None, []
    for phrase in result.get("phrases", []):
        offset = int(phrase.get("offsetMilliseconds", 0))
        if start is None:
            start = offset
        texts.append(phrase.get("text", "").strip())
        ends_sentence = texts[-1].endswith((".", "?", "!"))
        if offset + int(phrase.get("durationMilliseconds", 0)) - start >= SEGMENT_SECONDS * 1000 and ends_sentence:
            grouped.append((start, " ".join(t for t in texts if t)))
            start, texts = None, []
    if texts:
        grouped.append((start or 0, " ".join(t for t in texts if t)))
    return grouped


def render(number: int, title: str, path: Path, result: dict) -> str:
    parts = segments(result)
    duration = int(result.get("durationMilliseconds", 0))
    characters = sum(len(text) for _, text in parts)
    file_id = "az_" + hashlib.sha1(path.name.encode("utf-8")).hexdigest()[:12]
    lines = [
        f"## {number:02d}. {title}",
        "",
        f"`{path.name}` · `{file_id}` · {stamp(duration)} · {len(parts)} Segmente · {characters:,} Zeichen".replace(",", "."),
        "",
    ]
    for offset, text in parts:
        lines += [f"**[{stamp(offset)}]** {text}", ""]
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("audio_dir", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--resource")
    parser.add_argument("--resource-group")
    parser.add_argument("--locale", default="de-DE")
    parser.add_argument("--only", nargs="*", help="Nur Dateien, deren Name einen dieser Texte enthält")
    args = parser.parse_args()

    files = sorted(p for p in args.audio_dir.iterdir() if p.suffix.lower() in AUDIO_SUFFIXES)
    if args.only:
        files = [p for p in files if any(part.lower() in p.name.lower() for part in args.only)]
    if not files:
        print("Keine Audio-Dateien gefunden.")
        return 1
    args.out.mkdir(parents=True, exist_ok=True)
    endpoint, key = azure_credentials(args.resource, args.resource_group)

    collected, failures = [], []
    for number, path in enumerate(files, start=1):
        title = path.stem.replace("_", " ").strip()
        raw_path = args.out / f"{path.stem}.json"
        if raw_path.exists():
            result = json.loads(raw_path.read_text(encoding="utf-8"))
            print(f"[{number}/{len(files)}] vorhanden: {path.name}")
        else:
            print(f"[{number}/{len(files)}] transkribiere: {path.name}", flush=True)
            try:
                result = transcribe_file(path, endpoint, key, args.locale)
            except Exception as exc:
                failures.append(path.name)
                print(f"    fehlgeschlagen: {exc}")
                continue
            raw_path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
        text = render(number, title, path, result)
        (args.out / f"{path.stem}.md").write_text(text, encoding="utf-8")
        collected.append({"number": str(number), "title": title, "text": text})
    (args.out / "transcripts.json").write_text(json.dumps(collected, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Fertig: {len(collected)} Transkripte, {len(failures)} fehlgeschlagen. Ordner: {args.out}")
    for name in failures:
        print(f"    offen: {name}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
