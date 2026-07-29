from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


class ConfigError(ValueError):
    pass


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"{name} muss true oder false sein.")


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ConfigError(f"{name} muss eine ganze Zahl sein.") from exc
    if parsed <= 0:
        raise ConfigError(f"{name} muss größer als 0 sein.")
    return parsed


@dataclass(frozen=True)
class Config:
    username: str
    password: str
    login_url: str | None
    username_selector: str
    password_selector: str
    login_button_selector: str
    logged_in_selector: str | None
    login_success_url_pattern: str | None
    headless: bool
    login_timeout_ms: int
    page_timeout_ms: int
    download_timeout_ms: int
    download_dir: Path
    failed_downloads_file: Path

    @classmethod
    def from_env(cls, headed_override: bool = False) -> "Config":
        project_dir = Path(__file__).resolve().parent
        load_dotenv(project_dir / ".env")
        load_dotenv()

        username = os.getenv("UNI_USERNAME", "").strip()
        password = os.getenv("UNI_PASSWORD", "")
        if not username:
            raise ConfigError("UNI_USERNAME fehlt in der .env-Datei.")
        if not password:
            raise ConfigError("UNI_PASSWORD fehlt in der .env-Datei.")

        download_dir_value = os.getenv("DOWNLOAD_DIR", "downloads")
        download_dir = Path(download_dir_value)
        if not download_dir.is_absolute():
            download_dir = project_dir / download_dir

        failed_file_value = os.getenv("FAILED_DOWNLOADS_FILE", "failed_downloads.txt")
        failed_file = Path(failed_file_value)
        if not failed_file.is_absolute():
            failed_file = project_dir / failed_file

        login_url = os.getenv("LOGIN_URL", "").strip() or None
        logged_in_selector = os.getenv("LOGGED_IN_SELECTOR", "").strip() or None
        success_pattern = os.getenv("LOGIN_SUCCESS_URL_PATTERN", "").strip() or None

        return cls(
            username=username,
            password=password,
            login_url=login_url,
            username_selector=os.getenv(
                "USERNAME_SELECTOR", 'input[name="username"]'
            ),
            password_selector=os.getenv(
                "PASSWORD_SELECTOR", 'input[name="password"]'
            ),
            login_button_selector=os.getenv(
                "LOGIN_BUTTON_SELECTOR", 'button[type="submit"]'
            ),
            logged_in_selector=logged_in_selector,
            login_success_url_pattern=success_pattern,
            headless=False if headed_override else _env_bool("HEADLESS", True),
            login_timeout_ms=_env_int("LOGIN_TIMEOUT_MS", 30_000),
            page_timeout_ms=_env_int("PAGE_TIMEOUT_MS", 30_000),
            download_timeout_ms=_env_int("DOWNLOAD_TIMEOUT_MS", 120_000),
            download_dir=download_dir.resolve(),
            failed_downloads_file=failed_file.resolve(),
        )
