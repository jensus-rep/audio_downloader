from __future__ import annotations

import os
import threading
import tkinter as tk
from pathlib import Path
from queue import Empty, Queue
from tkinter import filedialog, messagebox, ttk
from urllib.parse import urlparse

from dotenv import dotenv_values

from runner import RunOptions, run_download_job


class AudioDownloaderApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Audio Downloader")
        self.root.geometry("980x720")
        self.root.minsize(860, 620)

        self.queue: Queue[tuple[str, object]] = Queue()
        self.running = False
        saved = dotenv_values(Path(__file__).resolve().parent / ".env")

        self.url_var = tk.StringVar()
        self.username_var = tk.StringVar(value=saved.get("UNI_USERNAME") or "")
        self.password_var = tk.StringVar(value=saved.get("UNI_PASSWORD") or "")
        self.login_url_var = tk.StringVar(value=saved.get("LOGIN_URL") or "")
        self.course_wide_var = tk.BooleanVar(value=True)
        self.headed_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Bereit")
        self.summary_var = tk.StringVar(value="Noch kein Lauf gestartet")
        self.download_dir_var = tk.StringVar(
            value=str(
                Path(__file__).resolve().parent
                / (saved.get("DOWNLOAD_DIR") or "downloads")
            )
        )

        self._build_ui()
        self.root.after(100, self._poll_queue)

    def _build_ui(self) -> None:
        self.root.configure(bg="#0f172a")
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("Root.TFrame", background="#0f172a")
        style.configure("Panel.TFrame", background="#111827")
        style.configure(
            "Title.TLabel",
            background="#0f172a",
            foreground="#f8fafc",
            font=("Segoe UI", 20, "bold"),
        )
        style.configure(
            "Subtitle.TLabel",
            background="#0f172a",
            foreground="#94a3b8",
            font=("Segoe UI", 10),
        )
        style.configure(
            "PanelTitle.TLabel",
            background="#111827",
            foreground="#f8fafc",
            font=("Segoe UI", 12, "bold"),
        )
        style.configure(
            "PanelText.TLabel",
            background="#111827",
            foreground="#e5e7eb",
            font=("Segoe UI", 10),
        )
        style.configure(
            "TCheckbutton",
            background="#111827",
            foreground="#e5e7eb",
            font=("Segoe UI", 10),
        )
        style.configure("TButton", padding=8)

        outer = ttk.Frame(self.root, style="Root.TFrame", padding=18)
        outer.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(outer, style="Root.TFrame")
        header.pack(fill=tk.X, pady=(0, 16))
        ttk.Label(header, text="Audio Downloader", style="Title.TLabel").pack(
            anchor=tk.W
        )
        ttk.Label(
            header,
            text="Kursseiten durchsuchen, Audio-Dateien sammeln und Downloads direkt im selben Fenster steuern.",
            style="Subtitle.TLabel",
        ).pack(anchor=tk.W, pady=(4, 0))

        body = ttk.Frame(outer, style="Root.TFrame")
        body.pack(fill=tk.BOTH, expand=True)
        body.columnconfigure(0, weight=2)
        body.columnconfigure(1, weight=3)
        body.rowconfigure(0, weight=1)

        left = ttk.Frame(body, style="Panel.TFrame", padding=16)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        right = ttk.Frame(body, style="Panel.TFrame", padding=16)
        right.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

        ttk.Label(left, text="Quelle", style="PanelTitle.TLabel").pack(anchor=tk.W)
        ttk.Label(
            left,
            text="Kurs-URL oder einzelne Seite",
            style="PanelText.TLabel",
        ).pack(anchor=tk.W, pady=(14, 6))
        ttk.Entry(left, textvariable=self.url_var).pack(fill=tk.X)

        ttk.Label(left, text="Anmeldung", style="PanelTitle.TLabel").pack(
            anchor=tk.W, pady=(18, 6)
        )
        ttk.Label(left, text="Benutzername", style="PanelText.TLabel").pack(
            anchor=tk.W
        )
        ttk.Entry(left, textvariable=self.username_var).pack(fill=tk.X, pady=(4, 8))
        ttk.Label(left, text="Passwort", style="PanelText.TLabel").pack(anchor=tk.W)
        ttk.Entry(left, textvariable=self.password_var, show="•").pack(
            fill=tk.X, pady=(4, 8)
        )
        ttk.Label(
            left, text="Login-URL (optional)", style="PanelText.TLabel"
        ).pack(anchor=tk.W)
        ttk.Entry(left, textvariable=self.login_url_var).pack(fill=tk.X, pady=(4, 0))

        ttk.Checkbutton(
            left, text="Kursweit durchsuchen", variable=self.course_wide_var
        ).pack(anchor=tk.W, pady=(16, 0))
        ttk.Checkbutton(
            left, text="Browser sichtbar starten", variable=self.headed_var
        ).pack(anchor=tk.W, pady=(6, 0))

        ttk.Label(left, text="Download-Ordner", style="PanelText.TLabel").pack(
            anchor=tk.W, pady=(14, 6)
        )
        folder_row = ttk.Frame(left, style="Panel.TFrame")
        folder_row.pack(fill=tk.X)
        ttk.Entry(folder_row, textvariable=self.download_dir_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        ttk.Button(folder_row, text="Auswählen …", command=self.choose_download_dir).pack(
            side=tk.LEFT, padx=(8, 0)
        )

        buttons = ttk.Frame(left, style="Panel.TFrame")
        buttons.pack(fill=tk.X, pady=(20, 10))

        self.start_button = ttk.Button(
            buttons, text="Download starten", command=self.start_download
        )
        self.start_button.pack(side=tk.LEFT)
        ttk.Button(
            buttons, text="Download-Ordner oeffnen", command=self.open_download_dir
        ).pack(side=tk.LEFT, padx=(10, 0))

        ttk.Label(left, text="Status", style="PanelTitle.TLabel").pack(
            anchor=tk.W, pady=(18, 6)
        )
        ttk.Label(left, textvariable=self.status_var, style="PanelText.TLabel").pack(
            anchor=tk.W
        )

        ttk.Label(left, text="Zusammenfassung", style="PanelTitle.TLabel").pack(
            anchor=tk.W, pady=(18, 6)
        )
        ttk.Label(
            left,
            textvariable=self.summary_var,
            style="PanelText.TLabel",
            justify=tk.LEFT,
            wraplength=320,
        ).pack(anchor=tk.W)

        ttk.Label(right, text="Live-Log", style="PanelTitle.TLabel").pack(anchor=tk.W)

        log_frame = ttk.Frame(right, style="Panel.TFrame")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(12, 0))
        self.log_text = tk.Text(
            log_frame,
            wrap=tk.WORD,
            bg="#0b1220",
            fg="#e5e7eb",
            insertbackground="#e5e7eb",
            relief=tk.FLAT,
            highlightthickness=1,
            highlightbackground="#334155",
        )
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=scroll.set)

    def start_download(self) -> None:
        if self.running:
            return

        url = self.url_var.get().strip()
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            messagebox.showerror(
                "Ungültige URL", "Bitte eine vollständige http(s)-URL angeben."
            )
            return
        if not self.username_var.get().strip() or not self.password_var.get():
            messagebox.showerror(
                "Anmeldung fehlt", "Bitte Benutzername und Passwort eingeben."
            )
            return

        self.running = True
        self.start_button.configure(state=tk.DISABLED)
        self.status_var.set("Lauf gestartet")
        self.summary_var.set("Warte auf Ergebnis")
        self._append_log(f"Starte fuer: {url}")

        options = RunOptions(
            url=url,
            course_wide=self.course_wide_var.get(),
            headed=self.headed_var.get(),
            config_overrides={
                "UNI_USERNAME": self.username_var.get().strip(),
                "UNI_PASSWORD": self.password_var.get(),
                "LOGIN_URL": self.login_url_var.get().strip(),
                "DOWNLOAD_DIR": self.download_dir_var.get().strip(),
            },
        )

        def worker() -> None:
            result = run_download_job(options, log=self._queue_log)
            self.queue.put(("result", result))

        threading.Thread(target=worker, daemon=True).start()

    def _queue_log(self, message: str) -> None:
        self.queue.put(("log", message))

    def _append_log(self, message: str) -> None:
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "log" and isinstance(payload, str):
                    self._append_log(payload)
                elif kind == "result":
                    self._handle_result(payload)
        except Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _handle_result(self, payload: object) -> None:
        self.running = False
        self.start_button.configure(state=tk.NORMAL)

        config_error = getattr(payload, "config_error", None)
        login_error = getattr(payload, "login_error", None)
        unexpected_error = getattr(payload, "unexpected_error", None)
        summary = getattr(payload, "summary", None)

        if config_error:
            text = str(config_error)
            self.status_var.set("Konfiguration fehlerhaft")
            self.summary_var.set(text)
            messagebox.showerror("Konfigurationsfehler", text)
            return
        if login_error:
            text = str(login_error)
            self.status_var.set("Login fehlgeschlagen")
            self.summary_var.set(text)
            messagebox.showerror("Login fehlgeschlagen", text)
            return
        if unexpected_error:
            text = str(unexpected_error)
            self.status_var.set("Fehler")
            self.summary_var.set(text)
            messagebox.showerror("Unerwarteter Fehler", text)
            return
        if summary is None:
            self.status_var.set("Keine Daten")
            return

        self.status_var.set("Abgeschlossen")
        self.download_dir_var.set(str(summary.download_dir))
        self.summary_var.set(
            f"Gefunden: {summary.found}\n"
            f"Heruntergeladen: {summary.downloaded}\n"
            f"Uebersprungen: {summary.skipped}\n"
            f"Fehlgeschlagen: {summary.failed}"
        )
        if summary.failed == 0:
            messagebox.showinfo("Fertig", "Der Lauf ist abgeschlossen.")

    def open_download_dir(self) -> None:
        path = self.download_dir_var.get().strip()
        if not path:
            path = str(Path(__file__).resolve().parent / "downloads")
        if os.path.isdir(path):
            os.startfile(path)
        else:
            messagebox.showerror("Fehler", f"Ordner nicht gefunden: {path}")

    def choose_download_dir(self) -> None:
        selected = filedialog.askdirectory(
            title="Download-Ordner auswählen",
            initialdir=self.download_dir_var.get() or str(Path.home()),
        )
        if selected:
            self.download_dir_var.set(selected)

    def run(self) -> None:
        self.root.mainloop()


def launch_gui() -> None:
    AudioDownloaderApp().run()


if __name__ == "__main__":
    launch_gui()
