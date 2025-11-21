import datetime as dt
import time
import tkinter as tk
from tkinter import font as tkfont
from pathlib import Path

from .db import connect, current_mode, daily_totals
from .core import ensure_rollover, ensure_mode
from .logging_setup import get_logger
from .config import ASSET_ICON


def _fmt(sec: float) -> str:
    sec = int(round(sec))
    h, m, s = sec // 3600, (sec % 3600) // 60, sec % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


class RoundedButton(tk.Canvas):
    """Minimal rounded button implemented on a Canvas."""
    def __init__(self, master, textvariable, command, radius=12, padx=14, pady=8, **kwargs):
        self.bg_fill = kwargs.pop("bg_fill", "#22c55e")
        self.fg_fill = kwargs.pop("fg_fill", "#0b1f10")
        self.command = command
        self.textvariable = textvariable
        self.radius = radius
        self.padx = padx
        self.pady = pady
        self.font = tkfont.Font(master=master, family="Segoe UI", size=11, weight="bold")
        super().__init__(master, highlightthickness=0, bd=0, bg=kwargs.get("bg", "#0f172a"))
        self.textvariable.trace_add("write", lambda *args: self._draw())
        self.bind("<Button-1>", self._on_click)
        self.bind("<Configure>", lambda e: self._draw())
        self._draw()

    def _rounded_rect(self, x1, y1, x2, y2, r, fill):
        # Draw a rounded rectangle using arcs and rectangles
        self.create_arc(x1, y1, x1 + 2 * r, y1 + 2 * r, start=90, extent=90, outline="", fill=fill)
        self.create_arc(x2 - 2 * r, y1, x2, y1 + 2 * r, start=0, extent=90, outline="", fill=fill)
        self.create_arc(x1, y2 - 2 * r, x1 + 2 * r, y2, start=180, extent=90, outline="", fill=fill)
        self.create_arc(x2 - 2 * r, y2 - 2 * r, x2, y2, start=270, extent=90, outline="", fill=fill)
        self.create_rectangle(x1 + r, y1, x2 - r, y2, outline="", fill=fill)
        self.create_rectangle(x1, y1 + r, x2, y2 - r, outline="", fill=fill)

    def set_style(self, bg_fill: str, fg_fill: str):
        self.bg_fill = bg_fill
        self.fg_fill = fg_fill
        self._draw()

    def _draw(self):
        self.delete("all")
        text = self.textvariable.get()
        txt_w = self.font.measure(text)
        txt_h = self.font.metrics("linespace")
        w = txt_w + self.padx * 2
        h = txt_h + self.pady * 2
        self.config(width=w, height=h)
        self._rounded_rect(0, 0, w, h, self.radius, self.bg_fill)
        self.create_text(w / 2, h / 2, text=text, fill=self.fg_fill, font=self.font)

    def _on_click(self, _event):
        if self.command:
            self.command()


class ControlApp:
    """Small GUI to show current session time and toggle active/pause."""

    def __init__(self):
        self.logger = get_logger("tt.control")
        self.con = connect()
        self._closed = False

        ensure_rollover(self.con, self.logger)

        self.root = tk.Tk()
        self.root.title("TimeTracker Control")
        self.root.configure(bg="#0f172a")
        self.root.resizable(False, False)
        self.root.geometry("380x200")
        try:
            icon_path = Path(ASSET_ICON)
            if icon_path.is_file():
                self.root.iconbitmap(default=str(icon_path))
        except Exception:
            # optional icon; safe to ignore failure
            pass

        container = tk.Frame(self.root, bg="#0f172a", padx=16, pady=16)
        container.pack(fill=tk.BOTH, expand=True)

        top_bar = tk.Frame(container, bg="#0f172a")
        top_bar.pack(fill=tk.X, pady=(0, 10))

        heading = tk.Label(
            top_bar,
            text="TimeTracker",
            fg="#93c5fd",
            bg="#0f172a",
            font=("Segoe UI Semibold", 12),
            anchor="w",
        )
        heading.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.status_badge = tk.Label(
            top_bar,
            text="",
            fg="#0f172a",
            bg="#22c55e",
            font=("Segoe UI", 9, "bold"),
            padx=10,
            pady=4,
        )
        self.status_badge.pack(side=tk.RIGHT)

        self.status_var = tk.StringVar()
        self.status_label = tk.Label(
            container,
            textvariable=self.status_var,
            font=("Segoe UI", 20, "bold"),
            fg="#e5e7eb",
            bg="#0f172a",
            pady=12,
        )
        self.status_label.pack(fill=tk.X)

        btn_frame = tk.Frame(container, pady=8, bg="#0f172a")
        btn_frame.pack()
        self.toggle_text = tk.StringVar()
        self.toggle_btn = RoundedButton(
            btn_frame,
            textvariable=self.toggle_text,
            command=self.on_toggle,
            bg=btn_frame["bg"],
        )
        self.toggle_btn.pack(side=tk.LEFT, padx=6)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._tick()

    def _active_today_sec(self) -> int:
        today = dt.date.today().isoformat()
        rows = daily_totals(self.con, today, now_ts=time.time())
        if rows:
            return int(rows[0][1] or 0)
        return 0

    def _tick(self):
        if self._closed:
            return
        try:
            ensure_rollover(self.con, self.logger)
            secs = self._active_today_sec()
            mode = current_mode(self.con) or "none"
            self.status_var.set(f"Timp activ azi: {_fmt(secs)}   (status: {mode})")
            self._apply_mode_style(mode)
        except Exception:
            self.logger.exception("Tick/update failed")
        finally:
            self.root.after(1000, self._tick)

    def _apply_mode_style(self, mode: str):
        if mode == "active":
            self.toggle_text.set("Stop")
            self.toggle_btn.set_style(bg_fill="#22c55e", fg_fill="#0b1f10")
            self.status_badge.configure(text="ACTIVE", bg="#22c55e", fg="#0b1f10")
        else:
            self.toggle_text.set("Resume")
            self.toggle_btn.set_style(bg_fill="#ef4444", fg_fill="#ffffff")
            self.status_badge.configure(text="PAUSED", bg="#ef4444", fg="#ffffff")

    def on_toggle(self):
        try:
            ensure_rollover(self.con, self.logger)
            mode = current_mode(self.con)
            if mode == "active":
                ensure_mode(self.con, "pause", self.logger)
            else:
                ensure_mode(self.con, "active", self.logger)
        except Exception:
            self.logger.exception("Failed to toggle mode")

    def on_close(self):
        self._closed = True
        try:
            self.con.close()
        except Exception:
            self.logger.exception("Failed to close DB connection")
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def run():
    ControlApp().run()
