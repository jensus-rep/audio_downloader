from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from playwright.sync_api import sync_playwright

from config import Config, ConfigError
from course_export import CourseExporter, ExportSummary
from crawler import AudioCrawler, LoginError
from downloader import AudioDownloader, DownloadSummary


LogFn = Callable[[str], None]


@dataclass(frozen=True)
class RunOptions:
    url: str
    course_wide: bool = False
    headed: bool = False
    config_overrides: dict[str, str] | None = None
    # "audio" downloads audio files; "export" records the whole course.
    mode: str = "audio"
    manual_login: bool = False
    with_media: bool = False


@dataclass(frozen=True)
class RunResult:
    summary: DownloadSummary | ExportSummary | None
    config_error: str | None = None
    login_error: str | None = None
    unexpected_error: str | None = None


def run_download_job(options: RunOptions, log: LogFn = print) -> RunResult:
    try:
        config = Config.from_env(
            headed_override=options.headed,
            overrides=options.config_overrides,
            manual_login=options.manual_login,
        )
    except ConfigError as exc:
        return RunResult(summary=None, config_error=str(exc))

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=config.headless, channel=config.browser_channel
            )
            context = browser.new_context(accept_downloads=True)

            try:
                if options.mode == "export":
                    exporter = CourseExporter(
                        context=context, config=config, log=log, with_media=options.with_media
                    )
                    summary = exporter.export_course(options.url)
                    summary.print(log=log)
                    return RunResult(summary=summary)

                crawler = AudioCrawler(context=context, config=config, log=log)
                if options.course_wide:
                    audio_urls = crawler.collect_course_audio_urls(options.url)
                else:
                    audio_urls = crawler.collect_audio_urls(options.url)

                if not audio_urls:
                    log("Keine Audio-Dateien gefunden.")
                    return RunResult(
                        summary=DownloadSummary(
                            found=0,
                            downloaded=0,
                            skipped=0,
                            failed=0,
                            download_dir=config.download_dir,
                        )
                    )

                log(f"{len(audio_urls)} Audio-Links gefunden")
                downloader = AudioDownloader(context=context, config=config, log=log)
                summary = downloader.download_all(audio_urls)
                summary.print(log=log)
                return RunResult(summary=summary)
            finally:
                context.close()
                browser.close()
    except LoginError as exc:
        return RunResult(summary=None, login_error=str(exc))
    except Exception as exc:
        return RunResult(summary=None, unexpected_error=str(exc))
