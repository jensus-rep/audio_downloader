from __future__ import annotations

import re
import time
from collections.abc import Iterable
from typing import Callable
from urllib.parse import parse_qs, urldefrag, urljoin, urlparse

from playwright.sync_api import (
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
)

from config import Config


AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg"}


class LoginError(RuntimeError):
    pass


class AudioCrawler:
    def __init__(
        self, context: BrowserContext, config: Config, log: Callable[[str], None] = print
    ) -> None:
        self.context = context
        self.config = config
        self.log = log
        self.page = context.new_page()
        self.page.set_default_timeout(config.page_timeout_ms)
        self.network_audio_urls: set[str] = set()
        self.page.on("response", self._capture_audio_response)

    def collect_audio_urls(self, target_url: str) -> list[str]:
        self.log("Oeffne Zielseite")
        self._open_authenticated_target(target_url)

        self._wait_for_dynamic_content()
        dom_urls = self._extract_dom_urls()
        audio_urls = {
            url for url in dom_urls if self._looks_like_audio_url(url)
        } | self.network_audio_urls
        return sorted(audio_urls)

    def collect_course_audio_urls(self, target_url: str) -> list[str]:
        self.log("Oeffne Kursuebersicht")
        self._open_authenticated_target(target_url)
        self._wait_for_dynamic_content()

        course_id = self._course_id_from_url(target_url)
        section_urls = self._extract_course_section_urls(course_id)
        pages = [urldefrag(target_url).url, *section_urls]
        pages = list(dict.fromkeys(pages))
        self.log(f"{len(section_urls)} Kursabschnitte gefunden")

        audio_urls: set[str] = set()
        for index, page_url in enumerate(pages, start=1):
            self.log(f"Durchsuche Kursseite {index} von {len(pages)}")
            self.network_audio_urls.clear()
            self._goto(self.page, page_url)
            if self._login_form_visible(self.page):
                raise LoginError(
                    "Die Sitzung ist beim Durchsuchen des Kurses abgelaufen."
                )
            self._wait_for_dynamic_content()
            dom_urls = self._extract_dom_urls()
            audio_urls.update(
                url for url in dom_urls if self._looks_like_audio_url(url)
            )
            audio_urls.update(self.network_audio_urls)

        return sorted(audio_urls)

    def open_authenticated(self, target_url: str) -> Page:
        """Open target_url with a logged-in session and return the crawler page."""
        self._open_authenticated_target(target_url)
        self._wait_for_dynamic_content()
        return self.page

    def _open_authenticated_target(self, target_url: str) -> None:
        self._goto(self.page, target_url)

        if self._login_form_visible(self.page) and self.config.manual_login:
            self._wait_for_manual_login(self.page)
            self._goto(self.page, target_url)
        elif self._login_form_visible(self.page):
            self._login(self.page)
            self._goto(self.page, target_url)
        elif not self._is_logged_in(self.page) and self.config.login_url:
            self.log("Oeffne Login-Seite")
            self._goto(self.page, self.config.login_url)
            if self._login_form_visible(self.page):
                self._login(self.page)
            elif not self._is_logged_in(self.page):
                raise LoginError(
                    "Auf der konfigurierten Login-Seite wurde kein Login-Formular "
                    "gefunden. Bitte die Login-Einstellungen prüfen."
                )
            self._goto(self.page, target_url)

        if self._login_form_visible(self.page):
            raise LoginError(
                "Die Zielseite zeigt nach dem Login weiterhin ein Login-Formular."
            )

    def _extract_course_section_urls(self, course_id: str | None) -> list[str]:
        target_origin = urlparse(self.page.url).netloc
        urls: set[str] = set()
        for element in self.page.locator('a[href*="/course/section.php"]').all():
            value = element.get_attribute("href")
            if not value:
                continue
            absolute = urldefrag(urljoin(self.page.url, value)).url
            parsed = urlparse(absolute)
            if parsed.netloc != target_origin:
                continue
            if course_id:
                linked_course_id = parse_qs(parsed.query).get("courseid", [None])[0]
                if linked_course_id and linked_course_id != course_id:
                    continue
            urls.add(absolute)
        return sorted(urls)

    @staticmethod
    def _course_id_from_url(url: str) -> str | None:
        return parse_qs(urlparse(url).query).get("id", [None])[0]

    def _login(self, page: Page) -> None:
        self.log("Login erforderlich, melde an")
        username = self._first_existing_locator(
            page,
            "#username",
            'input[name="username"]',
            'input[autocomplete="username"]',
            self.config.username_selector,
        )
        password = self._first_existing_locator(
            page,
            "#password",
            'input[name="password"]',
            'input[autocomplete="current-password"]',
            self.config.password_selector,
        )
        button = self._first_existing_locator(
            page,
            "#loginbtn",
            'button[type="submit"]',
            'input[type="submit"]',
            self.config.login_button_selector,
        )
        if username is None or password is None or button is None:
            raise LoginError(
                "Login-Felder oder Login-Button wurden nicht gefunden. "
                "Bitte die Login-Einstellungen prüfen."
            )

        try:
            username.evaluate(
                """(element, value) => {
                    element.value = value;
                    element.dispatchEvent(new Event("input", {bubbles: true}));
                    element.dispatchEvent(new Event("change", {bubbles: true}));
                }""",
                self.config.username,
            )
            password.evaluate(
                """(element, value) => {
                    element.value = value;
                    element.dispatchEvent(new Event("input", {bubbles: true}));
                    element.dispatchEvent(new Event("change", {bubbles: true}));
                }""",
                self.config.password,
            )
            button.evaluate(
                """button => {
                    const form = button.form;
                    if (!form) {
                        throw new Error("Login form missing");
                    }
                    if (typeof form.requestSubmit === "function") {
                        form.requestSubmit(button);
                    } else {
                        form.submit();
                    }
                }"""
            )
            page.wait_for_url(
                lambda url: "/login/" not in url,
                timeout=self.config.login_timeout_ms,
                wait_until="domcontentloaded",
            )
        except PlaywrightTimeoutError as exc:
            raise LoginError(
                "Zeitüberschreitung beim Login. Bitte URL und Einstellungen prüfen."
            ) from exc
        except Exception as exc:
            raise LoginError(f"Login-Formular konnte nicht bedient werden: {exc}") from exc

        if self._login_form_visible(page):
            raise LoginError(
                "Das Login-Formular ist weiterhin sichtbar. Zugangsdaten oder "
                "Einstellungen prüfen."
            )
        if (
            self.config.login_success_url_pattern
            and not re.search(self.config.login_success_url_pattern, page.url)
        ):
            raise LoginError(
                "Die URL nach dem Login entspricht nicht LOGIN_SUCCESS_URL_PATTERN."
            )
        if self.config.logged_in_selector and not self._is_logged_in(page):
            raise LoginError("LOGGED_IN_SELECTOR wurde nach dem Login nicht gefunden.")
        self.log("Login erfolgreich")

    def _wait_for_manual_login(self, page: Page) -> None:
        self.log("Bitte im geöffneten Browserfenster anmelden; das Tool wartet")
        deadline = time.monotonic() + self.config.manual_login_timeout_ms / 1000
        while time.monotonic() < deadline:
            page.wait_for_timeout(1_000)
            try:
                if "/login/" not in page.url and not self._login_form_visible(page):
                    self.log("Anmeldung erkannt")
                    return
            except Exception:
                continue
        raise LoginError("Keine Anmeldung im Browserfenster innerhalb der Wartezeit.")

    def _login_form_visible(self, page: Page) -> bool:
        username = self._first_existing_locator(
            page,
            "#username",
            'input[name="username"]',
            'input[autocomplete="username"]',
            self.config.username_selector,
        )
        password = self._first_existing_locator(
            page,
            "#password",
            'input[name="password"]',
            'input[autocomplete="current-password"]',
            self.config.password_selector,
        )
        return username is not None and password is not None

    def _is_logged_in(self, page: Page) -> bool:
        if not self.config.logged_in_selector:
            return False
        return self._visible(page, self.config.logged_in_selector)

    @staticmethod
    def _visible(page: Page, selector: str) -> bool:
        try:
            return page.locator(selector).first.is_visible(timeout=1_500)
        except Exception:
            return False

    @staticmethod
    def _first_existing_locator(page: Page, *selectors: str):
        seen: set[str] = set()
        for selector in selectors:
            if not selector or selector in seen:
                continue
            seen.add(selector)
            try:
                locator = page.locator(selector).first
                if locator.count() > 0:
                    return locator
            except Exception:
                continue
        return None

    def _goto(self, page: Page, url: str) -> None:
        try:
            page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=self.config.page_timeout_ms,
            )
        except PlaywrightTimeoutError as exc:
            raise RuntimeError(f"Zeitueberschreitung beim Oeffnen von {url}") from exc

    def _wait_for_dynamic_content(self) -> None:
        try:
            self.page.wait_for_load_state(
                "networkidle", timeout=min(self.config.page_timeout_ms, 10_000)
            )
        except PlaywrightTimeoutError:
            pass

    def _extract_dom_urls(self) -> set[str]:
        attributes: Iterable[tuple[str, str]] = (
            ("a[href]", "href"),
            ("audio[src]", "src"),
            ("source[src]", "src"),
            ("[data-src]", "data-src"),
        )
        urls: set[str] = set()
        for selector, attribute in attributes:
            for element in self.page.locator(selector).all():
                value = element.get_attribute(attribute)
                if value:
                    urls.add(urljoin(self.page.url, value))
        return urls

    def _capture_audio_response(self, response: object) -> None:
        try:
            content_type = response.headers.get("content-type", "").lower()
            if content_type.startswith("audio/"):
                self.network_audio_urls.add(response.url)
        except Exception:
            pass

    @staticmethod
    def _looks_like_audio_url(url: str) -> bool:
        path = urlparse(url).path.lower()
        return any(path.endswith(extension) for extension in AUDIO_EXTENSIONS)
