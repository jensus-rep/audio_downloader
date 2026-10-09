"""End-to-end test of the course export against a small fake Moodle course.

Run with:  .venv\\Scripts\\python -m unittest discover -s tests
Set BROWSER_CHANNEL=chrome to use an installed Chrome instead of Playwright's Chromium.
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from course_export import is_safe_to_open, lv_number, slug  # noqa: E402
from runner import RunOptions, run_download_job  # noqa: E402


def activity(cmid: int, modtype: str, name: str, href: str | None, extra: str = "") -> str:
    link = f'<a class="aalink" href="{href}"><span class="instancename">{name}<span class="accesshide"> Typ</span></span></a>' if href else f'<span class="instancename">{name}</span>'
    return f'<li class="activity modtype_{modtype}" id="module-{cmid}"><div class="activityname">{link}</div>{extra}</li>'


COURSE = f"""<!doctype html><html><head><title>Kurs: Agiles Testen</title></head><body>
<div class="page-header-headings"><h1>Agiles Testen</h1></div>
<div role="main"><ul class="topics">
<li class="section course-section" id="section-0" data-number="0"><h3 class="sectionname">Allgemeines</h3>
 <div class="summary"><div class="summarytext">Willkommen im Kurs. Prüfung am Ende.</div></div>
 <ul class="section">
  {activity(100, "label", "LV5 Einführung", None, '<div class="contentwithoutlink">LV5: Agile Werte. Das Manifest hat vier Werte.</div>')}
  {activity(103, "quiz", "Abschlusstest", "/mod/quiz/view.php?id=103")}
 </ul></li>
<li class="section course-section" id="section-1" data-number="1"><h3 class="sectionname"><a href="/course/section.php?id=11">Woche 1</a></h3></li>
</ul></div></body></html>"""

SECTION_1 = f"""<!doctype html><html><head><title>Woche 1</title></head><body><div role="main"><ul>
<li class="section course-section" id="section-1" data-number="1"><h3 class="sectionname">Woche 1</h3>
 <ul class="section">
  {activity(101, "page", "LV6 Sprint Planning", "/mod/page/view.php?id=101")}
  {activity(102, "resource", "Folien Sprint", "/mod/resource/view.php?id=102")}
  {activity(104, "url", "Scrum Guide", "/mod/url/view.php?id=104")}
  {activity(105, "book", "Handbuch Rollen", "/mod/book/view.php?id=105")}
  {activity(106, "folder", "Material", "/mod/folder/view.php?id=106")}
  {activity(107, "assign", "Hausarbeit", None, '<div class="availabilityinfo">Nicht verfügbar, bis Woche 2 abgeschlossen ist</div>')}
 </ul></li></ul></div></body></html>"""

PAGE_101 = """<!doctype html><html><head><title>LV6</title></head><body><nav>Navigation</nav>
<div role="main"><h2>Sprint Planning</h2><p>Das Team legt das Sprint-Ziel fest.</p>
<ul><li>Was wird geliefert?</li><li>Wie wird es umgesetzt?</li></ul>
<table><tr><th>Rolle</th><th>Aufgabe</th></tr><tr><td>Product Owner</td><td>priorisiert</td></tr></table>
<iframe src="https://video.example.org/embed/42"></iframe></div></body></html>"""

BOOK_PRINT = """<!doctype html><html><head><title>Buch</title></head><body><div role="main">
<h1>Handbuch Rollen</h1><h2>Kapitel 1: Product Owner</h2><p>Der Product Owner maximiert den Wert des Produkts und verantwortet das Product Backlog.</p>
<h2>Kapitel 2: Scrum Master</h2><p>Der Scrum Master verantwortet die Wirksamkeit des Scrum Teams und beseitigt Hindernisse, die den Fortschritt bremsen.</p>
</div></body></html>"""

FOLDER_106 = """<!doctype html><html><head><title>Material</title></head><body><div role="main">
<a href="/pluginfile.php/9/mod_folder/content/0/Leitfaden.docx">Leitfaden.docx</a></div></body></html>"""


def make_pdf(text: str) -> bytes:
    stream = f"BT /F1 18 Tf 72 720 Td ({text}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % number + body + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for offset in offsets:
        out.write(b"%010d 00000 n \n" % offset)
    out.write(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref))
    return out.getvalue()


def make_docx(text: str) -> bytes:
    from docx import Document

    document = Document()
    document.add_paragraph(text)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


class FakeMoodle(BaseHTTPRequestHandler):
    hits: list[str] = []
    files: dict[str, tuple[str, bytes]] = {}

    def log_message(self, *args) -> None:  # keep test output quiet
        pass

    def do_GET(self) -> None:
        FakeMoodle.hits.append(self.path)
        html = {
            "/course/view.php?id=7": COURSE,
            "/course/section.php?id=11": SECTION_1,
            "/mod/page/view.php?id=101": PAGE_101,
            "/mod/book/tool/print/index.php?id=105": BOOK_PRINT,
            "/mod/folder/view.php?id=106": FOLDER_106,
        }.get(self.path)
        if html is not None:
            return self._send(200, "text/html; charset=utf-8", html.encode("utf-8"))
        if self.path == "/mod/resource/view.php?id=102&redirect=1":
            return self._redirect("/pluginfile.php/8/mod_resource/content/1/Sprint-Folien.pdf")
        if self.path == "/mod/url/view.php?id=104&redirect=1":
            return self._redirect("https://scrumguides.org/scrum-guide.html")
        if self.path in FakeMoodle.files:
            content_type, body = FakeMoodle.files[self.path]
            return self._send(200, content_type, body)
        self._send(404, "text/html", b"<h1>Nicht gefunden</h1>")

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, location: str) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()


class HelperTests(unittest.TestCase):
    def test_lv_number(self) -> None:
        self.assertEqual(lv_number("LV12 – Produktvision"), 12)
        self.assertEqual(lv_number("Folien", "LV 05 Kickoff"), 5)
        self.assertIsNone(lv_number("Video A – Digitale Tools"))

    def test_slug(self) -> None:
        self.assertEqual(slug("LV13 – Design Thinking: Nutzer verstehen"), "lv13-design-thinking-nutzer-verstehen")

    def test_never_open_quiz_or_foreign_hosts(self) -> None:
        self.assertFalse(is_safe_to_open("https://moodle.example/mod/quiz/view.php?id=1", "moodle.example"))
        self.assertFalse(is_safe_to_open("https://other.example/x", "moodle.example"))
        self.assertFalse(is_safe_to_open("https://moodle.example/login/logout.php?sesskey=1", "moodle.example"))
        self.assertTrue(is_safe_to_open("https://moodle.example/mod/page/view.php?id=1", "moodle.example"))


class CourseExportTest(unittest.TestCase):
    def test_export_course(self) -> None:
        FakeMoodle.hits = []
        FakeMoodle.files = {
            "/pluginfile.php/8/mod_resource/content/1/Sprint-Folien.pdf": ("application/pdf", make_pdf("Sprint Review zeigt das Inkrement")),
            "/pluginfile.php/9/mod_folder/content/0/Leitfaden.docx": (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                make_docx("Definition of Done gilt für jedes Inkrement."),
            ),
        }
        server = ThreadingHTTPServer(("127.0.0.1", 0), FakeMoodle)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with tempfile.TemporaryDirectory() as tmp:
                logs: list[str] = []
                result = run_download_job(
                    RunOptions(
                        url=f"{base}/course/view.php?id=7",
                        mode="export",
                        config_overrides={
                            # Never touch the real login page from a local .env.
                            "LOGIN_URL": "",
                            "UNI_USERNAME": "test",
                            "UNI_PASSWORD": "test",
                            "EXPORT_DIR": tmp,
                            "BROWSER_CHANNEL": os.getenv("BROWSER_CHANNEL", ""),
                        },
                    ),
                    log=logs.append,
                )
                self.assertIsNone(result.unexpected_error, "\n".join(logs))
                self.assertIsNone(result.login_error)
                root = Path(tmp) / "kurs-7"
                inventory = json.loads((root / "inventar.json").read_text(encoding="utf-8"))
                by_name = {a["name"]: a for a in inventory["activities"]}

                self.assertEqual(len(by_name), 8, sorted(by_name))
                self.assertEqual(result.summary.lv_numbers, [5, 6])
                self.assertFalse(any("/mod/quiz/" in hit for hit in FakeMoodle.hits), "Quiz must never be requested")
                self.assertEqual(by_name["Abschlusstest"]["status"], "nicht geöffnet")

                label = (root / by_name["LV5 Einführung"]["text_file"]).read_text(encoding="utf-8")
                self.assertIn("vier Werte", label)
                page = (root / by_name["LV6 Sprint Planning"]["text_file"]).read_text(encoding="utf-8")
                self.assertIn("## Sprint Planning", page)
                self.assertIn("- Was wird geliefert?", page)
                self.assertIn("| Product Owner | priorisiert |", page)
                self.assertNotIn("Navigation", page)
                self.assertIn("https://video.example.org/embed/42", json.dumps(by_name["LV6 Sprint Planning"]["media"]))

                resource = by_name["Folien Sprint"]
                self.assertEqual(resource["status"], "datei")
                pdf_text = (root / resource["file_texts"][0]).read_text(encoding="utf-8")
                self.assertIn("Sprint Review zeigt das Inkrement", pdf_text)

                folder = by_name["Material"]
                docx_text = (root / folder["file_texts"][0]).read_text(encoding="utf-8")
                self.assertIn("Definition of Done", docx_text)

                self.assertEqual(by_name["Scrum Guide"]["external_links"], ["https://scrumguides.org/scrum-guide.html"])
                book = (root / by_name["Handbuch Rollen"]["text_file"]).read_text(encoding="utf-8")
                self.assertIn("Kapitel 2: Scrum Master", book)
                self.assertEqual(by_name["Hausarbeit"]["status"], "nicht geöffnet")

                report = (root / "inventar.md").read_text(encoding="utf-8")
                self.assertIn("Gefunden: 5, 6", report)
                self.assertIn("Im Kurs nicht vorhanden (zwischen 1 und 6): 1, 2, 3, 4", report)
                self.assertIn("Willkommen im Kurs", (root / "texte" / "00_abschnitte.md").read_text(encoding="utf-8"))
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
