from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import unquote, urlparse

from playwright.sync_api import (
    BrowserContext,
    Error as PlaywrightError,
    TimeoutError as PlaywrightTimeoutError,
)

from config import Config


CONTENT_TYPE_EXTENSIONS = {
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/ogg": ".ogg",
}
INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


@dataclass
class DownloadSummary:
    found: int
    downloaded: int
    skipped: int
    failed: int
    download_dir: Path

    def print(self, log: Callable[[str], None] = print) -> None:
        log("")
        log("Zusammenfassung")
        log(f"Gefundene Audio-Dateien: {self.found}")
        log(f"Erfolgreich heruntergeladen: {self.downloaded}")
        log(f"Uebersprungen: {self.skipped}")
        log(f"Fehlgeschlagen: {self.failed}")
        log(f"Download-Ordner: {self.download_dir}")


class AudioDownloader:
    def __init__(
        self, context: BrowserContext, config: Config, log: Callable[[str], None] = print
    ) -> None:
        self.context = context
        self.config = config
        self.log = log
        self.config.download_dir.mkdir(parents=True, exist_ok=True)

    def download_all(self, urls: list[str]) -> DownloadSummary:
        downloaded = 0
        skipped = 0
        failures: list[str] = []

        for index, url in enumerate(urls, start=1):
            self.log(f"Lade Datei {index} von {len(urls)} herunter")
            try:
                result = self._download_one(url, index)
                if result == "skipped":
                    skipped += 1
                    self.log("Datei existiert bereits, ueberspringe")
                else:
                    self.log(f"Download abgeschlossen: {result.name}")
                    downloaded += 1
            except Exception as exc:
                failures.append(url)
                self.log(f"Download fehlgeschlagen: {exc}")

        self._write_failures(failures)
        return DownloadSummary(
            found=len(urls),
            downloaded=downloaded,
            skipped=skipped,
            failed=len(failures),
            download_dir=self.config.download_dir,
        )

    def _download_one(self, url: str, index: int) -> Path | str:
        response = self.context.request.get(
            url,
            timeout=self.config.download_timeout_ms,
            fail_on_status_code=False,
        )
        content_type = response.headers.get("content-type", "")
        content_disposition = response.headers.get("content-disposition", "")
        if response.ok and self._is_downloadable_response(
            url, content_type, content_disposition
        ):
            filename = self._filename_for(
                url=url,
                index=index,
                content_disposition=content_disposition,
                content_type=content_type,
            )
            destination = self.config.download_dir / filename
            if destination.exists():
                return "skipped"
            self._write_atomic(destination, response.body())
            return destination

        return self._download_with_browser(url, index, response.status)

    def _download_with_browser(
        self, url: str, index: int, request_status: int
    ) -> Path | str:
        page = self.context.new_page()
        downloads: list[object] = []
        page.on("download", downloads.append)

        try:
            response = None
            try:
                response = page.goto(
                    url,
                    wait_until="commit",
                    timeout=self.config.download_timeout_ms,
                )
            except (PlaywrightError, PlaywrightTimeoutError):
                pass

            if downloads:
                download = downloads[0]
                filename = self._sanitize_filename(
                    download.suggested_filename
                    or self._filename_for(url=url, index=index)
                )
                destination = self.config.download_dir / filename
                if destination.exists():
                    download.cancel()
                    return "skipped"
                download.save_as(destination)
                return destination

            if response and response.ok and self._is_downloadable_response(
                url,
                response.headers.get("content-type", ""),
                response.headers.get("content-disposition", ""),
            ):
                filename = self._filename_for(
                    url=url,
                    index=index,
                    content_disposition=response.headers.get(
                        "content-disposition", ""
                    ),
                    content_type=response.headers.get("content-type", ""),
                )
                destination = self.config.download_dir / filename
                if destination.exists():
                    return "skipped"
                self._write_atomic(destination, response.body())
                return destination

            status = response.status if response else request_status
            raise RuntimeError(f"HTTP-Status {status}; Browser-Fallback ohne Erfolg")
        finally:
            page.close()

    @staticmethod
    def _is_downloadable_response(
        url: str, content_type: str, content_disposition: str
    ) -> bool:
        media_type = content_type.split(";", maxsplit=1)[0].strip().lower()
        if media_type.startswith("audio/"):
            return True
        if "attachment" in content_disposition.lower():
            return True
        if media_type in {"text/html", "application/xhtml+xml"}:
            return False
        return Path(urlparse(url).path).suffix.lower() in {
            ".mp3",
            ".wav",
            ".m4a",
            ".ogg",
        }

    def _filename_for(
        self,
        url: str,
        index: int,
        content_disposition: str = "",
        content_type: str = "",
    ) -> str:
        disposition_name = self._filename_from_content_disposition(
            content_disposition
        )
        url_name = Path(unquote(urlparse(url).path)).name
        filename = disposition_name or url_name

        extension = self._extension_from_content_type(content_type)
        if not filename or "." not in filename:
            filename = f"audio_{index:03d}{extension or '.mp3'}"
        elif extension and Path(filename).suffix.lower() not in {
            ".mp3",
            ".wav",
            ".m4a",
            ".ogg",
        }:
            filename = f"{filename}{extension}"

        return self._sanitize_filename(filename)

    @staticmethod
    def _filename_from_content_disposition(header: str) -> str | None:
        utf8_match = re.search(
            r"filename\*\s*=\s*UTF-8''([^;]+)", header, flags=re.IGNORECASE
        )
        if utf8_match:
            return unquote(utf8_match.group(1).strip().strip('"'))
        basic_match = re.search(
            r'filename\s*=\s*(?:"([^"]+)"|([^;]+))',
            header,
            flags=re.IGNORECASE,
        )
        if basic_match:
            return (basic_match.group(1) or basic_match.group(2)).strip()
        return None

    @staticmethod
    def _extension_from_content_type(content_type: str) -> str:
        media_type = content_type.split(";", maxsplit=1)[0].strip().lower()
        return CONTENT_TYPE_EXTENSIONS.get(media_type, "")

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        filename = unicodedata.normalize(
            "NFC", AudioDownloader._repair_mojibake(filename)
        )
        cleaned = INVALID_FILENAME_CHARS.sub("_", filename).strip().rstrip(". ")
        if not cleaned:
            return "audio.mp3"
        if cleaned.split(".", maxsplit=1)[0].upper() in {
            "CON",
            "PRN",
            "AUX",
            "NUL",
            *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10)),
        }:
            cleaned = f"_{cleaned}"
        return cleaned[:240]

    @staticmethod
    def _repair_mojibake(value: str) -> str:
        if not any(marker in value for marker in ("Ã", "Â", "Ì", "â")):
            return value
        try:
            repaired = value.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return value
        return repaired

    @staticmethod
    def _write_atomic(destination: Path, content: bytes) -> None:
        temporary = destination.with_name(f"{destination.name}.part")
        temporary.write_bytes(content)
        temporary.replace(destination)

    def _write_failures(self, failures: list[str]) -> None:
        self.config.failed_downloads_file.parent.mkdir(parents=True, exist_ok=True)
        if failures:
            self.config.failed_downloads_file.write_text(
                "\n".join(failures) + "\n", encoding="utf-8"
            )
            self.log(f"Fehlgeschlagene URLs: {self.config.failed_downloads_file}")
        elif self.config.failed_downloads_file.exists():
            self.config.failed_downloads_file.unlink()
