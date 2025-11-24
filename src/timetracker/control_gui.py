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
        # tkfont.Font expects `root`, not `master` (Python 3.12/Windows is strict)
        self.font = tkfont.Font(root=master, family="Segoe UI", size=11, weight="bold")
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
        self._last_rows = []

        ensure_rollover(self.con, self.logger)

        self.root = tk.Tk()
        self.root.title("TimeTracker Control")
        self.root.configure(bg="#0f172a")
        self.root.resizable(True, True)
        self.root.geometry("560x720")
        self.root.minsize(360, 380)
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

        self.status_time_var = tk.StringVar()
        status_row = tk.Frame(container, bg="#0f172a", pady=8)
        status_row.pack(fill=tk.X)
        status_inner = tk.Frame(status_row, bg="#0f172a")
        status_inner.pack(anchor="center")
        tk.Label(
            status_inner,
            text="Active today:",
            font=("Segoe UI", 20, "bold"),
            fg="#e5e7eb",
            bg="#0f172a",
        ).pack(side=tk.LEFT)
        self.status_time_label = tk.Label(
            status_inner,
            textvariable=self.status_time_var,
            font=("Segoe UI", 20, "bold"),
            fg="#e5e7eb",
            bg="#0f172a",
            padx=8,
        )
        self.status_time_label.pack(side=tk.LEFT)
        self.reminder_var = tk.StringVar()
        self.reminder_frame = tk.Frame(container, bg="#0f172a")
        self.reminder_inner = tk.Frame(self.reminder_frame, bg="#0f172a")
        self.reminder_inner.pack(anchor="center")
        self.reminder_label = tk.Label(
            self.reminder_inner,
            textvariable=self.reminder_var,
            font=("Segoe UI", 10),
            fg="#0a0a0a",
            bg="#ffffff",
            padx=14,
            pady=8,
            bd=1,
            relief="solid",
        )
        self.reminder_label.pack(side=tk.LEFT)
        self.mode_var = tk.StringVar()
        self.mode_label = tk.Label(
            container,
            textvariable=self.mode_var,
            font=("Segoe UI", 11),
            fg="#cbd5e1",
            bg="#0f172a",
            pady=2,
        )
        self.mode_label.pack(fill=tk.X)

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

        # Dashboard container (chart + table)
        self.dashboard_frame = tk.Frame(container, bg="#0f172a", pady=10)
        self.dashboard_frame.pack(fill=tk.BOTH, expand=True)

        # Chart block
        self.chart_heading = tk.Label(
            self.dashboard_frame,
            text="Last 7 days chart (active vs pause)",
            font=("Segoe UI Semibold", 10),
            fg="#cbd5e1",
            bg="#0f172a",
            anchor="w",
            pady=4,
        )
        self.chart_heading.pack(fill=tk.X)
        self.chart_canvas = tk.Canvas(
            self.dashboard_frame,
            height=180,
            bg="#0b1224",
            highlightthickness=0,
        )
        self.chart_canvas.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        self.chart_canvas.bind("<Configure>", lambda _e: self._draw_chart(self._last_rows))

        # Table block
        self.dashboard_heading = tk.Label(
            self.dashboard_frame,
            text="Table (last 7 days)",
            font=("Segoe UI Semibold", 10),
            fg="#cbd5e1",
            bg="#0f172a",
            anchor="w",
            pady=4,
        )
        self.dashboard_heading.pack(fill=tk.X)
        self.dashboard_body = tk.Frame(self.dashboard_frame, bg="#0f172a")
        self.dashboard_body.pack(fill=tk.BOTH, expand=True)

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
            # Highlight only the time in red if over 7 hours
            self.status_time_var.set(_fmt(secs))
            self.status_time_label.configure(fg="#ef4444" if secs > 7 * 3600 else "#e5e7eb")
            if secs > 7 * 3600:
                self.reminder_var.set("🙂 Take a short break and relax.")
                if not self.reminder_frame.winfo_ismapped():
                    self.reminder_frame.pack(fill=tk.X, pady=(2, 6), before=self.mode_label)
            else:
                self.reminder_var.set("")
                if self.reminder_frame.winfo_ismapped():
                    self.reminder_frame.pack_forget()
            self.mode_var.set(f"Status: {mode}")
            self._apply_mode_style(mode)
            self._update_dashboard()
        except Exception:
            self.logger.exception("Tick/update failed")
        finally:
            self.root.after(1000, self._tick)

    def _apply_mode_style(self, mode: str):
        if mode == "active":
            self.toggle_text.set("Stop")
            self.toggle_btn.set_style(bg_fill="#ef4444", fg_fill="#0b1f10")
            self.status_badge.configure(text="ACTIVE", bg="#22c55e", fg="#0b1f10")
        else:
            self.toggle_text.set("Resume")
            self.toggle_btn.set_style(bg_fill="#22c55e", fg_fill="#ffffff")
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

    def _weekly_rows(self):
        now_ts = time.time()
        today = dt.date.today()
        start_day = today - dt.timedelta(days=6)
        days = [start_day + dt.timedelta(days=i) for i in range(7)]

        try:
            raw = self.con.execute(
                """
                SELECT day,
                       SUM(CASE WHEN kind='active' THEN (COALESCE(end_ts, ?) - start_ts) ELSE 0 END) AS active_sec,
                       SUM(CASE WHEN kind='pause'  THEN (COALESCE(end_ts, ?) - start_ts) ELSE 0 END) AS pause_sec
                FROM sessions
                WHERE day >= ?
                GROUP BY day
                ORDER BY day DESC
                """,
                (now_ts, now_ts, start_day.isoformat()),
            ).fetchall()
        except Exception:
            self.logger.exception("Failed to load weekly rows")
            raw = []

        by_day = {d: (a or 0, p or 0) for d, a, p in raw}
        rows = []
        for d in days:
            iso = d.isoformat()
            wd = d.weekday()  # 0=Mon ... 6=Sun
            active_sec, pause_sec = by_day.get(iso, (0, 0))
            # Show Sat/Sun only if active time exceeds 15 minutes
            if wd >= 5 and active_sec <= 15 * 60:
                continue
            rows.append(
                {
                    "iso": iso,
                    "label": d.strftime("%a %d"),
                    "active": active_sec,
                    "pause": pause_sec,
                }
            )
        return rows

    def _update_dashboard(self):
        for child in self.dashboard_body.winfo_children():
            child.destroy()
        rows = sorted(self._weekly_rows(), key=lambda r: r["iso"], reverse=True)
        self._last_rows = rows

        self._draw_chart(rows)

        if not rows:
            tk.Label(
                self.dashboard_body,
                text="No recent records.",
                font=("Segoe UI", 10),
                fg="#94a3b8",
                bg="#0f172a",
                anchor="w",
            ).pack(fill=tk.X)
            return
        header = tk.Frame(self.dashboard_body, bg="#0f172a")
        header.pack(fill=tk.X, pady=(0, 2))
        for txt, w in (("Day", 10), ("Active", 12), ("Pause", 12)):
            tk.Label(
                header,
                text=txt,
                width=w,
                font=("Segoe UI Semibold", 10),
                fg="#e2e8f0",
                bg="#0f172a",
                anchor="w",
            ).pack(side=tk.LEFT, padx=(0, 8))
        for item in rows:
            row = tk.Frame(self.dashboard_body, bg="#0f172a")
            row.pack(fill=tk.X, pady=1)
            tk.Label(
                row,
                text=item["label"],
                width=10,
                font=("Segoe UI", 10),
                fg="#cbd5e1",
                bg="#0f172a",
                anchor="w",
            ).pack(side=tk.LEFT, padx=(0, 8))
            tk.Label(
                row,
                text=_fmt(item["active"]),
                width=12,
                font=("Segoe UI", 10),
                fg="#22c55e",
                bg="#0f172a",
                anchor="w",
            ).pack(side=tk.LEFT, padx=(0, 8))
            tk.Label(
                row,
                text=_fmt(item["pause"]),
                width=12,
                font=("Segoe UI", 10),
                fg="#f87171",
                bg="#0f172a",
                anchor="w",
            ).pack(side=tk.LEFT)

    def _draw_chart(self, rows):
        c = self.chart_canvas
        c.delete("all")
        if not rows:
            c.create_text(
                10,
                20,
                anchor="w",
                fill="#94a3b8",
                font=("Segoe UI", 10),
                text="No data for the last 7 days.",
            )
            return
        width = int(c.winfo_width() or 420)
        height = int(c.winfo_height() or 180)
        margin = 28
        bar_width = 16
        gap = 14
        max_val = max(max(r["active"], r["pause"]) for r in rows) or 1
        scale = (height - margin * 2) / max_val
        group_w = 2 * bar_width + gap
        x = margin
        # Reverse order so newest days render on the right (left -> older, right -> newer)
        for r in reversed(rows):
            # Active bar
            h_active = r["active"] * scale
            h_pause = r["pause"] * scale
            c.create_rectangle(
                x,
                height - margin - h_active,
                x + bar_width,
                height - margin,
                fill="#22c55e",
                width=0,
            )
            c.create_rectangle(
                x + bar_width + 4,
                height - margin - h_pause,
                x + 2 * bar_width + 4,
                height - margin,
                fill="#f87171",
                width=0,
            )
            c.create_text(
                x + bar_width - 2,
                height - margin + 12,
                anchor="e",
                fill="#cbd5e1",
                font=("Segoe UI", 9),
                text=r["label"],
            )
            x += group_w

        # Legend
        legend_y = 12
        c.create_rectangle(margin, legend_y - 6, margin + 12, legend_y + 6, fill="#22c55e", width=0)
        c.create_text(margin + 16, legend_y, anchor="w", fill="#cbd5e1", font=("Segoe UI", 9), text="Active")
        c.create_rectangle(margin + 70, legend_y - 6, margin + 82, legend_y + 6, fill="#f87171", width=0)
        c.create_text(margin + 86, legend_y, anchor="w", fill="#cbd5e1", font=("Segoe UI", 9), text="Pause")


def run():
    ControlApp().run()
