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
    manual_login: bool = False
    manual_login_timeout_ms: int = 300_000
    browser_channel: str | None = None
    export_dir: Path = Path("exports")
    request_delay_ms: int = 300

    @classmethod
    def from_env(
        cls,
        headed_override: bool = False,
        overrides: dict[str, str] | None = None,
        manual_login: bool = False,
    ) -> "Config":
        project_dir = Path(__file__).resolve().parent
        load_dotenv(project_dir / ".env")
        load_dotenv()

        values = overrides or {}

        def value(name: str, default: str = "") -> str:
            if name in values:
                return values[name]
            return os.getenv(name, default)

        username = value("UNI_USERNAME").strip()
        password = value("UNI_PASSWORD")
        # With manual login the user signs in in the visible browser window;
        # no credentials are needed or stored.
        if not manual_login and not username:
            raise ConfigError("Benutzername fehlt.")
        if not manual_login and not password:
            raise ConfigError("Passwort fehlt.")

        export_dir = Path(value("EXPORT_DIR", "exports"))
        if not export_dir.is_absolute():
            export_dir = project_dir / export_dir

        download_dir_value = value("DOWNLOAD_DIR", "downloads")
        download_dir = Path(download_dir_value)
        if not download_dir.is_absolute():
            download_dir = project_dir / download_dir

        failed_file_value = os.getenv("FAILED_DOWNLOADS_FILE", "failed_downloads.txt")
        failed_file = Path(failed_file_value)
        if not failed_file.is_absolute():
            failed_file = project_dir / failed_file

        login_url = value("LOGIN_URL").strip() or None
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
            headless=False
            if headed_override or manual_login
            else _env_bool("HEADLESS", True),
            login_timeout_ms=_env_int("LOGIN_TIMEOUT_MS", 30_000),
            page_timeout_ms=_env_int("PAGE_TIMEOUT_MS", 30_000),
            download_timeout_ms=_env_int("DOWNLOAD_TIMEOUT_MS", 120_000),
            download_dir=download_dir.resolve(),
            failed_downloads_file=failed_file.resolve(),
            manual_login=manual_login,
            manual_login_timeout_ms=_env_int("MANUAL_LOGIN_TIMEOUT_MS", 300_000),
            browser_channel=value("BROWSER_CHANNEL").strip() or None,
            export_dir=export_dir.resolve(),
            request_delay_ms=_env_int("REQUEST_DELAY_MS", 300),
        )
