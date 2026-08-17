from __future__ import annotations

import calendar
import math
import json
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.error
import urllib.parse
import urllib.request
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, simpledialog, ttk
from typing import Any, Callable
from uuid import uuid4

from PIL import Image, ImageDraw, ImageOps, ImageTk

from ..assets import AssetStore, MAP_CANVAS_HEIGHT, MAP_CANVAS_WIDTH, MAP_CANVAS_SIZE
from ..board import WorldBoardRepository
from ..campaigns import format_game_world_date
from ..paths import PROJECT_ROOT, RUNTIME_DIRECTORY
from ..preferences import Preferences
from ..windowing import GAME_BOARD_ICON, apply_window_icon, configure_windows_app_id, maximize_window
from .storage import GameBoardRepository


DATE_DISPLAY_FORMAT = "%d %b %Y"
GAME_DATETIME_DISPLAY_FORMAT = "%d %b %Y  %H:%M"
GAME_DATETIME_RE = re.compile(
    r"^(?P<year>-?[1-9]\d*)-(?P<month>\d{2})-(?P<day>\d{2})T"
    r"(?P<hour>\d{2}):(?P<minute>\d{2})$"
)
BOARD_TOKEN_SCREEN_SIZES = (0, 0, 0, 0, 0, 0, 68, 64)
BOARD_OVERVIEW_DOT_SIZES = (12, 11, 10, 9, 8, 7, 0, 0)
BOARD_LABEL_FONT_SIZES = (11, 11, 10, 10, 9, 9, 9, 8)


def format_date_display(value: date) -> str:
    """Format dates consistently for the Headmaster-facing interface."""

    return value.strftime(DATE_DISPLAY_FORMAT)


def format_stored_date(value: Any, fallback: str = "Not set") -> str:
    """Display an ISO date or timestamp without exposing storage formatting."""

    if not value:
        return fallback
    try:
        return format_date_display(date.fromisoformat(str(value)[:10]))
    except ValueError:
        return str(value)


def _display_historical_year(year: int) -> str:
    return f"{abs(year)} BCE" if year < 0 else str(year)


def _next_historical_year(year: int, direction: int) -> int:
    candidate = year + direction
    return direction if candidate == 0 else candidate


@dataclass(frozen=True, order=True)
class HistoricalDateTime:
    """A small proleptic Gregorian value for years Python's datetime cannot hold."""

    year: int
    month: int
    day: int
    hour: int = 0
    minute: int = 0

    def __post_init__(self) -> None:
        if self.year == 0 or not 1 <= self.month <= 12:
            raise ValueError("Game World Date must use a real historical year and month")
        if not 1 <= self.day <= calendar.monthrange(self.year, self.month)[1]:
            raise ValueError("Game World Date contains an invalid day")
        if not 0 <= self.hour <= 23 or not 0 <= self.minute <= 59:
            raise ValueError("Game World Date contains an invalid 24-hour time")

    def replace(self, **changes: int) -> HistoricalDateTime:
        changes.pop("second", None)
        changes.pop("microsecond", None)
        return HistoricalDateTime(
            changes.get("year", self.year),
            changes.get("month", self.month),
            changes.get("day", self.day),
            changes.get("hour", self.hour),
            changes.get("minute", self.minute),
        )

    def isoformat(self, timespec: str = "minutes") -> str:
        del timespec
        year = f"-{abs(self.year):04d}" if self.year < 0 else f"{self.year:04d}"
        return f"{year}-{self.month:02d}-{self.day:02d}T{self.hour:02d}:{self.minute:02d}"

    def strftime(self, pattern: str) -> str:
        if pattern == "%H:%M":
            return f"{self.hour:02d}:{self.minute:02d}"
        if pattern == "%M":
            return f"{self.minute:02d}"
        raise ValueError(f"Unsupported historical date format: {pattern}")

    def date(self) -> tuple[int, int, int]:
        return self.year, self.month, self.day

    def __add__(self, delta: timedelta) -> HistoricalDateTime:
        if not isinstance(delta, timedelta):
            return NotImplemented
        total_minutes = self.hour * 60 + self.minute + int(delta.total_seconds() // 60)
        day_delta, minute_of_day = divmod(total_minutes, 24 * 60)
        value = self
        direction = 1 if day_delta >= 0 else -1
        for _ in range(abs(day_delta)):
            value = _shift_historical_day(value, direction)
        return value.replace(hour=minute_of_day // 60, minute=minute_of_day % 60)

    def __sub__(self, delta: timedelta) -> HistoricalDateTime:
        if not isinstance(delta, timedelta):
            return NotImplemented
        return self + (-delta)


GameDateTime = datetime | HistoricalDateTime


def _shift_historical_day(value: HistoricalDateTime, direction: int) -> HistoricalDateTime:
    if direction > 0:
        if value.day < calendar.monthrange(value.year, value.month)[1]:
            return value.replace(day=value.day + 1)
        if value.month < 12:
            return value.replace(month=value.month + 1, day=1)
        return value.replace(year=_next_historical_year(value.year, 1), month=1, day=1)
    if value.day > 1:
        return value.replace(day=value.day - 1)
    if value.month > 1:
        month = value.month - 1
        return value.replace(month=month, day=calendar.monthrange(value.year, month)[1])
    year = _next_historical_year(value.year, -1)
    return value.replace(year=year, month=12, day=31)


def parse_game_datetime(value: str) -> GameDateTime:
    match = GAME_DATETIME_RE.fullmatch(value.strip())
    if not match:
        raise ValueError("Game World Date must use YYYY-MM-DD and HH:MM")
    parts = {key: int(raw) for key, raw in match.groupdict().items()}
    if parts["year"] > 0:
        return datetime(**parts)
    return HistoricalDateTime(**parts)


def format_game_datetime(value: GameDateTime) -> str:
    if isinstance(value, datetime):
        return value.strftime(GAME_DATETIME_DISPLAY_FORMAT)
    month = calendar.month_abbr[value.month]
    return (
        f"{value.day:02d} {month} {_display_historical_year(value.year)}  "
        f"{value.hour:02d}:{value.minute:02d}"
    )


def format_stored_game_datetime(value: Any, fallback: str = "Not set") -> str:
    if not value:
        return fallback
    try:
        return format_game_datetime(parse_game_datetime(str(value)))
    except ValueError:
        return str(value)


def shift_game_calendar(
    value: GameDateTime,
    *,
    years: int = 0,
    months: int = 0,
    days: int = 0,
) -> GameDateTime:
    """Shift the in-world calendar, clamping dates such as 29 February safely."""
    historical = HistoricalDateTime(
        value.year, value.month, value.day, value.hour, value.minute
    )
    shifted = historical
    direction = 1 if days >= 0 else -1
    for _ in range(abs(days)):
        shifted = _shift_historical_day(shifted, direction)
    astronomical_year = shifted.year if shifted.year > 0 else shifted.year + 1
    month_index = astronomical_year * 12 + shifted.month - 1 + months + years * 12
    target_astronomical_year, zero_month = divmod(month_index, 12)
    target_year = (
        target_astronomical_year
        if target_astronomical_year > 0
        else target_astronomical_year - 1
    )
    target_month = zero_month + 1
    target_day = min(shifted.day, calendar.monthrange(target_year, target_month)[1])
    if target_year > 0:
        return datetime(
            target_year, target_month, target_day, shifted.hour, shifted.minute
        )
    return shifted.replace(year=target_year, month=target_month, day=target_day)


def directional_minute_snap(
    value: GameDateTime, minute: int, direction: int
) -> GameDateTime:
    """Find the nearest :MM occurrence at or before/after the current game time."""

    target = value.replace(minute=minute)
    if direction < 0 and target > value:
        target -= timedelta(hours=1)
    elif direction > 0 and target < value:
        target += timedelta(hours=1)
    return target


class AdminClient:
    """Small localhost-only client used by the native Headmaster window."""

    def __init__(self, settings: dict[str, Any]):
        self.base_url = f"http://{settings['admin_host']}:{settings['admin_port']}"
        self.player_health_url = (
            f"http://{settings['player_host']}:{settings['player_port']}/health"
        )
        self.admin_key = settings["admin_key"]

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        timeout: float = 20,
    ) -> Any:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            method=method,
            headers={"X-Admin-Key": self.admin_key, "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            try:
                detail = json.loads(error.read().decode("utf-8")).get("detail")
            except Exception:
                detail = None
            raise RuntimeError(detail or f"Game Board returned {error.code}") from error
        except urllib.error.URLError as error:
            raise ConnectionError("The local Game Board service is unavailable") from error

    def state(self) -> dict[str, Any]:
        return self.request("GET", "/api/admin/state")

    def health(self) -> dict[str, Any]:
        # The player health route has existed since the first server release,
        # is localhost-bound, and performs no heavy state assembly.  Checking
        # it first also lets a newly opened desktop adopt an already-running
        # service from an earlier release.
        request = urllib.request.Request(self.player_health_url, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=1.0) as response:
                result = json.loads(response.read().decode("utf-8"))
            if result.get("service") == "game-board":
                return result
        except (urllib.error.URLError, ValueError, json.JSONDecodeError):
            pass
        return self.request("GET", "/api/admin/health", timeout=1.0)


class LocalServer:
    """Starts the communication engine when the desktop app owns it."""

    def __init__(self, client: AdminClient):
        self.client = client
        self.process: subprocess.Popen | None = None
        self._log_stream: Any = None
        self.log_path = RUNTIME_DIRECTORY / "game-board-server.log"

    def ready(self) -> bool:
        try:
            self.client.health()
            return True
        except Exception:
            return False

    def start(self, timeout: float = 12.0) -> None:
        if self.ready():
            return
        creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log_stream = self.log_path.open("a", encoding="utf-8")
        self._log_stream.write(f"\n--- Game Board start {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
        self._log_stream.flush()
        self.process = subprocess.Popen(
            [sys.executable, "-B", "-m", "headmasters_scroll.game_board.server"],
            cwd=PROJECT_ROOT,
            stdin=subprocess.DEVNULL,
            stdout=self._log_stream,
            stderr=subprocess.STDOUT,
            creationflags=creation_flags,
        )
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.ready():
                return
            if self.process.poll() is not None:
                break
            time.sleep(0.2)
        detail = ""
        try:
            if self._log_stream:
                self._log_stream.flush()
            if self.log_path.is_file():
                lines = self.log_path.read_text(encoding="utf-8", errors="replace").splitlines()
                detail = next((line.strip() for line in reversed(lines) if line.strip()), "")
        except OSError:
            pass
        message = "The Game Board communication service could not start."
        if detail:
            message += f"\n\nServer report: {detail}"
        else:
            message += f"\n\nStartup details are saved in {self.log_path}."
        raise RuntimeError(message)

    def stop(self) -> None:
        if self.process is None:
            return
        try:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    self.process.kill()
        finally:
            if self._log_stream is not None:
                self._log_stream.close()
                self._log_stream = None


class CalendarDateField(ttk.Frame):
    """A compact, dependency-free date field with a calendar popup."""

    def __init__(
        self,
        parent: tk.Misc,
        initial_date: date | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(parent, **kwargs)
        self._date = initial_date or date.today()
        self._picker: tk.Toplevel | None = None
        self.display_value = tk.StringVar(value=format_date_display(self._date))
        self.entry = ttk.Entry(
            self,
            textvariable=self.display_value,
            width=14,
        )
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", self._commit_text)
        self.entry.bind("<FocusOut>", self._commit_text)
        ttk.Button(
            self,
            text="▦",
            width=3,
            style="Quiet.TButton",
            command=self.open_picker,
        ).pack(side="left", padx=(4, 0))

    def get_date(self) -> date:
        return self._date

    def get_iso(self) -> str:
        self._commit_text()
        return self._date.isoformat()

    def set_date(self, value: date) -> None:
        self._date = value
        self.display_value.set(format_date_display(value))

    def _commit_text(self, _event: tk.Event | None = None) -> None:
        raw = self.display_value.get().strip()
        try:
            try:
                parsed = datetime.strptime(raw, DATE_DISPLAY_FORMAT).date()
            except ValueError:
                parsed = date.fromisoformat(raw)
        except ValueError:
            self.display_value.set(format_date_display(self._date))
            return
        self.set_date(parsed)

    def open_picker(self) -> None:
        if self._picker is not None and self._picker.winfo_exists():
            self._picker.lift()
            return

        self._commit_text()
        picker = tk.Toplevel(self)
        self._picker = picker
        picker.title("Choose date")
        picker.transient(self.winfo_toplevel())
        picker.resizable(False, False)
        picker.configure(background="#f8edcf")
        picker.protocol("WM_DELETE_WINDOW", self._close_picker)
        picker.bind("<Escape>", lambda _event: self._close_picker())

        current = [self._date.year, self._date.month]
        shell = ttk.Frame(picker, padding=8, style="Card.TFrame")
        shell.pack(fill="both", expand=True)
        month_header = ttk.Frame(shell, style="Card.TFrame")
        month_header.pack(fill="x", pady=(0, 6))
        month_label = ttk.Label(month_header, style="Section.TLabel", anchor="center")
        month_label.pack(side="left", fill="x", expand=True)
        year_value = tk.StringVar(value=str(current[0]))
        year_control = ttk.Spinbox(
            month_header, from_=1, to=9999, textvariable=year_value, width=6
        )
        year_control.pack(side="left", padx=4)
        days_frame = ttk.Frame(shell, style="Card.TFrame")
        days_frame.pack(fill="both", expand=True)

        def move_month(offset: int) -> None:
            current[1] += offset
            if current[1] < 1:
                current[:] = [current[0] - 1, 12]
            elif current[1] > 12:
                current[:] = [current[0] + 1, 1]
            draw_month()

        def apply_year(_event: tk.Event | None = None) -> None:
            try:
                selected_year = int(year_value.get())
                if not 1 <= selected_year <= 9999:
                    raise ValueError
            except ValueError:
                year_value.set(str(current[0]))
                return
            if selected_year == current[0]:
                return
            current[0] = selected_year
            draw_month()

        def move_year(offset: int) -> None:
            current[0] = max(1, min(9999, current[0] + offset))
            year_value.set(str(current[0]))
            draw_month()

        year_control.configure(command=apply_year)
        year_control.bind("<Return>", apply_year)
        year_control.bind("<FocusOut>", apply_year)

        ttk.Button(
            month_header,
            text="‹",
            width=3,
            style="Quiet.TButton",
            command=lambda: move_month(-1),
        ).pack(side="left", before=month_label)
        ttk.Button(
            month_header,
            text="›",
            width=3,
            style="Quiet.TButton",
            command=lambda: move_month(1),
        ).pack(side="right")

        ttk.Button(
            month_header,
            text="-Y",
            width=3,
            style="Quiet.TButton",
            command=lambda: move_year(-1),
        ).pack(side="left", before=month_label)
        ttk.Button(
            month_header,
            text="+Y",
            width=3,
            style="Quiet.TButton",
            command=lambda: move_year(1),
        ).pack(side="right")

        def choose(day_number: int) -> None:
            self.set_date(date(current[0], current[1], day_number))
            self._close_picker()

        def draw_month() -> None:
            for child in days_frame.winfo_children():
                child.destroy()
            month_label.configure(text=calendar.month_name[current[1]])
            if year_value.get() != str(current[0]):
                year_value.set(str(current[0]))
            for column, label in enumerate(("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")):
                ttk.Label(
                    days_frame,
                    text=label,
                    style="Card.TLabel",
                    anchor="center",
                    width=4,
                ).grid(row=0, column=column, padx=1, pady=(0, 2))
            weeks = calendar.Calendar(firstweekday=calendar.MONDAY).monthdayscalendar(
                current[0], current[1]
            )
            for row, week in enumerate(weeks, start=1):
                for column, day_number in enumerate(week):
                    if day_number == 0:
                        ttk.Label(days_frame, text="", style="Card.TLabel", width=4).grid(
                            row=row, column=column, padx=1, pady=1
                        )
                        continue
                    style = (
                        "Good.TButton"
                        if date(current[0], current[1], day_number) == self._date
                        else "Quiet.TButton"
                    )
                    ttk.Button(
                        days_frame,
                        text=str(day_number),
                        width=4,
                        style=style,
                        command=lambda selected=day_number: choose(selected),
                    ).grid(row=row, column=column, padx=1, pady=1)

        def choose_today() -> None:
            self.set_date(date.today())
            self._close_picker()

        ttk.Button(
            shell,
            text="Today",
            style="Quiet.TButton",
            command=choose_today,
        ).pack(anchor="e", pady=(7, 0))
        draw_month()
        picker.update_idletasks()
        picker.geometry(f"+{self.winfo_rootx()}+{self.winfo_rooty() + self.winfo_height() + 4}")
        picker.grab_set()

    def _close_picker(self) -> None:
        picker = self._picker
        self._picker = None
        if picker is not None and picker.winfo_exists():
            try:
                picker.grab_release()
            except tk.TclError:
                pass
            picker.destroy()


class GameWorldDateField(ttk.Frame):
    """Editable calendar field that supports historical Game World dates, including BCE."""

    def __init__(
        self,
        parent: tk.Misc,
        initial_date: date | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(parent, **kwargs)
        initial = initial_date or date.today()
        self._year, self._month, self._day = initial.year, initial.month, initial.day
        self._picker: tk.Toplevel | None = None
        self.display_value = tk.StringVar(value=self._display())
        self.entry = ttk.Entry(self, textvariable=self.display_value, width=18)
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", self._commit_text)
        self.entry.bind("<FocusOut>", self._commit_text)
        ttk.Button(
            self,
            text="Calendar",
            style="Quiet.TButton",
            command=self.open_picker,
        ).pack(side="left", padx=(4, 0))

    def _display(self) -> str:
        return (
            f"{self._day:02d} {calendar.month_abbr[self._month]} "
            f"{_display_historical_year(self._year)}"
        )

    def get_iso(self) -> str:
        self._commit_text()
        year = f"-{abs(self._year):04d}" if self._year < 0 else f"{self._year:04d}"
        return f"{year}-{self._month:02d}-{self._day:02d}"

    def set_iso(self, value: str) -> None:
        self._set(*self._parse_text(str(value).strip()))

    def _set(self, year: int, month: int, day_number: int) -> None:
        HistoricalDateTime(year, month, day_number)
        self._year, self._month, self._day = year, month, day_number
        self.display_value.set(self._display())

    def _parse_text(self, raw: str) -> tuple[int, int, int]:
        iso = re.fullmatch(r"(?P<year>-?[1-9]\d*)-(?P<month>\d{2})-(?P<day>\d{2})", raw)
        if iso:
            return tuple(int(iso.group(key)) for key in ("year", "month", "day"))
        shown = re.fullmatch(
            r"(?P<day>\d{1,2})\s+(?P<month>[A-Za-z]{3,9})\s+"
            r"(?P<year>[1-9]\d*)\s*(?P<era>BCE|BC|CE|AD)?",
            raw,
            re.IGNORECASE,
        )
        if not shown:
            raise ValueError
        month_text = shown.group("month")[:3].title()
        try:
            month = list(calendar.month_abbr).index(month_text)
        except ValueError as error:
            raise ValueError from error
        year = int(shown.group("year"))
        if (shown.group("era") or "").upper() in {"BCE", "BC"}:
            year = -year
        return year, month, int(shown.group("day"))

    def _commit_text(self, _event: tk.Event | None = None) -> None:
        try:
            self._set(*self._parse_text(self.display_value.get().strip()))
        except ValueError:
            self.display_value.set(self._display())

    def open_picker(self) -> None:
        if self._picker is not None and self._picker.winfo_exists():
            self._picker.lift()
            return
        self._commit_text()
        picker = tk.Toplevel(self)
        self._picker = picker
        picker.title("Choose Game World Date")
        picker.transient(self.winfo_toplevel())
        picker.resizable(False, False)
        picker.configure(background="#f8edcf")
        picker.protocol("WM_DELETE_WINDOW", self._close_picker)
        picker.bind("<Escape>", lambda _event: self._close_picker())

        current = [self._year, self._month]
        shell = ttk.Frame(picker, padding=8, style="Card.TFrame")
        shell.pack(fill="both", expand=True)
        header = ttk.Frame(shell, style="Card.TFrame")
        header.pack(fill="x", pady=(0, 6))
        month_label = ttk.Label(header, style="Section.TLabel", anchor="center")
        month_label.pack(side="left", fill="x", expand=True)
        year_value = tk.StringVar(value=str(current[0]))
        year_entry = ttk.Entry(header, textvariable=year_value, width=9)
        year_entry.pack(side="left", padx=4)
        days_frame = ttk.Frame(shell, style="Card.TFrame")
        days_frame.pack(fill="both", expand=True)

        def redraw() -> None:
            for child in days_frame.winfo_children():
                child.destroy()
            month_label.configure(text=calendar.month_name[current[1]])
            if year_value.get() != str(current[0]):
                year_value.set(str(current[0]))
            for column, label in enumerate(("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")):
                ttk.Label(days_frame, text=label, style="Card.TLabel", anchor="center", width=4).grid(
                    row=0, column=column, padx=1, pady=(0, 2)
                )
            weeks = calendar.Calendar(firstweekday=calendar.MONDAY).monthdayscalendar(
                current[0], current[1]
            )
            for row, week in enumerate(weeks, start=1):
                for column, day_number in enumerate(week):
                    if not day_number:
                        ttk.Label(days_frame, text="", style="Card.TLabel", width=4).grid(
                            row=row, column=column, padx=1, pady=1
                        )
                        continue
                    selected = (current[0], current[1], day_number) == (
                        self._year, self._month, self._day
                    )
                    ttk.Button(
                        days_frame,
                        text=str(day_number),
                        width=4,
                        style="Good.TButton" if selected else "Quiet.TButton",
                        command=lambda chosen=day_number: choose(chosen),
                    ).grid(row=row, column=column, padx=1, pady=1)

        def apply_year(_event: tk.Event | None = None) -> None:
            try:
                year = int(year_value.get())
                if year == 0 or not -99999 <= year <= 99999:
                    raise ValueError
            except ValueError:
                year_value.set(str(current[0]))
                return
            if year == current[0]:
                return
            current[0] = year
            redraw()

        def move_year(direction: int) -> None:
            current[0] = _next_historical_year(current[0], direction)
            year_value.set(str(current[0]))
            redraw()

        def move_month(direction: int) -> None:
            current[1] += direction
            if current[1] < 1:
                current[:] = [_next_historical_year(current[0], -1), 12]
            elif current[1] > 12:
                current[:] = [_next_historical_year(current[0], 1), 1]
            redraw()

        def choose(day_number: int) -> None:
            self._set(current[0], current[1], day_number)
            self._close_picker()

        ttk.Button(header, text="-Y", width=3, style="Quiet.TButton", command=lambda: move_year(-1)).pack(side="left", before=month_label)
        ttk.Button(header, text="<", width=3, style="Quiet.TButton", command=lambda: move_month(-1)).pack(side="left", before=month_label)
        ttk.Button(header, text="+Y", width=3, style="Quiet.TButton", command=lambda: move_year(1)).pack(side="right")
        ttk.Button(header, text=">", width=3, style="Quiet.TButton", command=lambda: move_month(1)).pack(side="right")
        year_entry.bind("<Return>", apply_year)
        year_entry.bind("<FocusOut>", apply_year)
        ttk.Label(
            shell,
            text="Type a negative year for BCE (for example, -3100).",
            style="Card.TLabel",
        ).pack(anchor="w", pady=(7, 0))
        redraw()
        picker.update_idletasks()
        picker.geometry(f"+{self.winfo_rootx()}+{self.winfo_rooty() + self.winfo_height() + 4}")
        picker.grab_set()

    def _close_picker(self) -> None:
        picker = self._picker
        self._picker = None
        if picker is not None and picker.winfo_exists():
            try:
                picker.grab_release()
            except tk.TclError:
                pass
            picker.destroy()


class GameBoardWindow(tk.Tk):
    PAPER = "#ead7aa"
    LIGHT = "#f8edcf"
    EDGE = "#c9aa71"
    INK = "#382719"
    MUTED = "#765f45"
    ACCENT = "#7b3f2b"
    GREEN = "#49643d"
    RED = "#8a3328"

    def __init__(self, repository: GameBoardRepository | None = None):
        super().__init__()
        self.repository = repository or GameBoardRepository()
        self.preferences_store = Preferences("game-board")
        self.preferences = self.preferences_store.load()
        try:
            self.chat_font_size = max(
                8, min(20, int(self.preferences.get("chat_font_size", 10)))
            )
        except (TypeError, ValueError):
            self.chat_font_size = 10
        self.settings = self.repository.settings()
        self.client = AdminClient(self.settings)
        self.server = LocalServer(self.client)
        self.state_data: dict[str, Any] = {"contacts": [], "settings": {}, "session": None, "connections": []}
        self.refreshing = False
        self.closing = False
        self.settings_dirty = False
        self.asset_store = AssetStore()
        self.world_board = WorldBoardRepository(assets=self.asset_store)
        self.board_snapshot: dict[str, Any] = {}
        self.board_world_revision_id = ""
        self.board_map_label_to_id: dict[str, str] = {}
        self.board_open_map_ids: list[str] = []
        self.board_workspace_campaign_id = ""
        self.board_map_drafts: dict[str, dict[str, Any]] = {}
        self.board_view_states: dict[str, dict[str, float | bool]] = {}
        self._board_camera_save_after_ids: dict[str, str] = {}
        self.selected_board_map_id = ""
        self.selected_board_actor_id = ""
        self._board_image: ImageTk.PhotoImage | None = None
        self._board_portraits: dict[str, ImageTk.PhotoImage] = {}
        self._board_canvas_actors: dict[tuple[str, int], str] = {}
        self._board_canvas_actor_parts: dict[tuple[str, int], str] = {}
        self._board_map_sources: dict[str, Image.Image] = {}
        self._board_obscure_images: dict[str, ImageTk.PhotoImage] = {}
        self.board_obscure_mode = False
        self.board_obscure_drawing = False
        self.board_obscure_draft_points: list[dict[str, float]] = []
        self.board_selected_obscuration_id = ""
        self.board_selected_obscuration_node: int | None = None
        self.board_obscuration_list_ids: list[str] = []
        self.board_obscure_opacity = tk.StringVar(value="35")
        self.board_obscure_color = "#ff0000"
        self.board_confirmation_message_until = 0.0
        self._board_obscure_drag: dict[str, Any] | None = None
        self._board_pan_state: tuple[str, float, float, float, float] | None = None
        self._board_pan_watchdog_id: str | None = None
        self._drag_actor_id = ""
        self._drag_start_point: tuple[float, float] | None = None
        self._drag_actor_part = ""
        self._drag_label_only = False
        self._drag_label_origin: dict[str, float] = {"x": 0.0, "y": 0.0}
        self._piece_popup: tk.Menu | None = None
        self.board_map_controls_dock: ttk.Frame | None = None
        self.board_token_controls_dock: ttk.Frame | None = None
        self.board_groups_dock: ttk.Frame | None = None
        self.board_creatures_dock: ttk.Frame | None = None
        self.board_secrets_dock: ttk.Frame | None = None
        self.board_secret_region_ids: list[str] = []
        self.creature_placement: dict[str, Any] | None = None
        self.board_creature_ids: list[str] = []
        self.board_tools_panels: dict[str, ttk.Frame] = {}
        self.active_headmaster_tool = "groups"
        self.headmaster_tools_collapsed = False
        self.headmaster_tool_widths = {
            "groups": 430,
            "creatures": 440,
            "obfuscation-tools": 330,
            "token-tools": 390,
            "secrets": 360,
        }
        self.board_reveal_value = tk.BooleanVar(value=False)
        self.board_zoom_status_value = tk.StringVar(value="Zoom 100% · 0 clicks")
        self.board_zoom_override_ids: list[int] = []
        self.board_zoom_override_vars: dict[int, tuple[tk.StringVar, tk.StringVar, tk.StringVar]] = {}
        self._board_token_preview_after_id: str | None = None
        self.board_settings_window: tk.Toplevel | None = None
        self._known_pending_ids: set[str] = set()
        self._known_campaign_request_ids: set[str] = set()
        self._board_actor_list_signature: tuple[Any, ...] | None = None
        self._admission_desktop_popup: tk.Toplevel | None = None
        self._chat_layout_after_id: str | None = None
        self._chat_layout_compact: bool | None = None
        self.title("Game Board — Headmaster Controls")
        self.geometry("1240x800")
        self.minsize(760, 520)
        self.configure(background=self.PAPER)
        apply_window_icon(self, GAME_BOARD_ICON)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self._configure_style()
        self._build()
        self.bind("<Configure>", self._window_resized, add="+")
        self.bind("<Escape>", self._cancel_creature_placement, add="+")
        self.after_idle(self._apply_responsive_chat_layout)
        self.after_idle(lambda: maximize_window(self))
        self.after(100, self._start_server)

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=self.PAPER)
        style.configure("Card.TFrame", background=self.LIGHT, relief="solid", borderwidth=1)
        style.configure("TLabel", background=self.PAPER, foreground=self.INK, font=("Segoe UI", 10))
        style.configure("Card.TLabel", background=self.LIGHT, foreground=self.INK)
        style.configure("Title.TLabel", background=self.PAPER, foreground=self.INK, font=("Georgia", 26, "bold"))
        style.configure("Section.TLabel", background=self.LIGHT, foreground=self.INK, font=("Georgia", 14, "bold"))
        style.configure("Muted.TLabel", background=self.PAPER, foreground=self.MUTED)
        style.configure("Status.TLabel", background=self.PAPER, foreground=self.ACCENT, font=("Segoe UI", 9, "bold"))
        style.configure("TButton", background=self.ACCENT, foreground="#fff8e7", padding=(10, 7), font=("Segoe UI", 9, "bold"))
        style.map("TButton", background=[("active", "#63311f")])
        style.configure("Quiet.TButton", background=self.EDGE, foreground=self.INK)
        style.configure("Good.TButton", background=self.GREEN, foreground="white")
        style.configure("Danger.TButton", background=self.RED, foreground="white")
        style.configure("Treeview", background="#fff8e6", fieldbackground="#fff8e6", foreground=self.INK, rowheight=27)
        style.configure("Treeview.Heading", background=self.EDGE, foreground=self.INK, font=("Segoe UI", 9, "bold"))
        style.configure("Board.TNotebook", background=self.PAPER, borderwidth=0, tabmargins=(0, 0, 0, 0))
        style.configure(
            "Board.TNotebook.Tab",
            background=self.EDGE,
            foreground=self.INK,
            padding=(10, 5),
            font=("Segoe UI", 9, "bold"),
        )
        style.map(
            "Board.TNotebook.Tab",
            background=[("selected", "#e4c98f"), ("active", self.LIGHT)],
            foreground=[("selected", self.ACCENT)],
        )

    def _build(self) -> None:
        header = ttk.Frame(self)
        header.pack(fill="x", padx=12, pady=(6, 4))
        self.server_status = tk.Label(
            header, text="STARTING LOCAL SERVER", background=self.PAPER,
            foreground=self.ACCENT, font=("Segoe UI", 9, "bold"),
        )
        self.server_status.pack(side="right")
        tk.Frame(self, height=2, background=self.ACCENT).pack(fill="x", padx=12, pady=(0, 6))

        self.admission_alert = tk.Frame(
            self,
            background="#f4dda7",
            highlightbackground=self.ACCENT,
            highlightthickness=1,
        )
        self.admission_alert_text = tk.Label(
            self.admission_alert,
            text="A player is waiting for approval",
            anchor="w",
            background="#f4dda7",
            foreground=self.INK,
            font=("Segoe UI", 10, "bold"),
            padx=12,
            pady=9,
        )
        self.admission_alert_text.pack(side="left", fill="x", expand=True)
        self.admission_quick_approve_button = tk.Button(
            self.admission_alert,
            text="Approve",
            background=self.GREEN,
            foreground="white",
            activebackground="#31553a",
            activeforeground="white",
            relief="flat",
            font=("Segoe UI", 9, "bold"),
            padx=12,
            pady=7,
            command=self.admit_all_pending,
        )
        self.admission_quick_approve_button.pack(side="right", padx=(0, 6), pady=5)
        tk.Button(
            self.admission_alert,
            text="Review request",
            background=self.ACCENT,
            foreground="#fff8e7",
            activebackground="#63311f",
            activeforeground="#fff8e7",
            relief="flat",
            font=("Segoe UI", 9, "bold"),
            padx=12,
            pady=7,
            command=lambda: self.show_control_page("live-room"),
        ).pack(side="right", padx=6, pady=5)

        self.workspace = ttk.Frame(self)
        self.workspace.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        self._build_chat_shell(self.workspace)

        sidebar = tk.Frame(
            self.workspace,
            width=176,
            background=self.EDGE,
            highlightbackground=self.ACCENT,
            highlightthickness=1,
        )
        self.section_sidebar = sidebar
        sidebar.pack(side="left", fill="y", padx=(0, 8))
        sidebar.pack_propagate(False)
        tk.Label(
            sidebar,
            text="SECTIONS",
            anchor="w",
            background=self.EDGE,
            foreground=self.MUTED,
            font=("Segoe UI", 9, "bold"),
            padx=14,
            pady=12,
        ).pack(fill="x")
        self.sidebar_buttons: dict[str, tk.Button] = {}
        for key, label in (
            ("game-board", "Game Board"),
            ("requests", "Requests"),
            ("control-panel", "Control Room"),
        ):
            button = tk.Button(
                sidebar,
                text=label,
                anchor="w",
                background=self.LIGHT,
                activebackground=self.PAPER,
                foreground=self.INK,
                activeforeground=self.INK,
                relief="flat",
                borderwidth=0,
                font=("Segoe UI", 10, "bold"),
                padx=16,
                pady=12,
                command=lambda selected=key: self.show_app_page(selected),
            )
            button.pack(fill="x", pady=(0, 1))
            self.sidebar_buttons[key] = button
        self.control_panel_button = self.sidebar_buttons["control-panel"]
        self.requests_button = self.sidebar_buttons["requests"]
        self._build_headmaster_tool_rail(self.workspace)

        self.app_host = ttk.Frame(self.workspace)
        self.app_host.pack(side="left", fill="both", expand=True)
        self.app_host.rowconfigure(0, weight=1)
        self.app_host.columnconfigure(0, weight=1)

        game_board_page = ttk.Frame(self.app_host)
        game_board_page.grid(row=0, column=0, sticky="nsew")
        game_board_top = ttk.Frame(game_board_page)
        game_board_top.pack(fill="x", pady=(0, 4))
        self._build_board_search(game_board_top)
        self._build_game_clock(game_board_top)
        game_board_panel = ttk.Frame(game_board_page, style="Card.TFrame")
        game_board_panel.pack(fill="both", expand=True)
        self._build_board_workspace(game_board_panel)

        control_panel = ttk.Frame(self.app_host)
        control_panel.grid(row=0, column=0, sticky="nsew")
        requests_page = ttk.Frame(self.app_host)
        requests_page.grid(row=0, column=0, sticky="nsew")
        self.app_pages = {
            "game-board": game_board_page,
            "requests": requests_page,
            "control-panel": control_panel,
        }
        self._build_requests_page(requests_page)
        control_header = ttk.Frame(control_panel)
        control_header.pack(fill="x", pady=(0, 8))
        ttk.Label(control_header, text="Control Room", style="Title.TLabel").pack(side="left")
        ttk.Button(
            control_header,
            text="Refresh",
            style="Quiet.TButton",
            command=self.refresh,
        ).pack(side="right", padx=(8, 0))
        self.control_section_label = ttk.Label(
            control_header, text="Live Room", style="Status.TLabel"
        )
        self.control_section_label.pack(side="right", pady=10)
        self.notice = tk.Label(
            control_header,
            text="Starting…",
            background=self.PAPER,
            foreground=self.MUTED,
            anchor="e",
        )
        self.notice.pack(side="right", fill="x", expand=True, padx=10)

        control_navigation = tk.Frame(
            control_panel,
            background=self.EDGE,
            highlightbackground=self.ACCENT,
            highlightthickness=1,
        )
        control_navigation.pack(fill="x", pady=(0, 8))
        self.control_buttons: dict[str, tk.Button] = {}
        for key, label in (
            ("live-room", "Live Room"),
            ("sessions", "Sessions"),
            ("players", "Players & Characters"),
            ("connection", "Connection & Gmail"),
        ):
            button = tk.Button(
                control_navigation,
                text=label,
                background=self.LIGHT,
                activebackground=self.PAPER,
                foreground=self.INK,
                activeforeground=self.INK,
                relief="flat",
                borderwidth=0,
                font=("Segoe UI", 9, "bold"),
                padx=12,
                pady=9,
                command=lambda selected=key: self.show_control_page(selected),
            )
            button.pack(side="left", fill="x", expand=True, padx=(0, 1))
            self.control_buttons[key] = button

        control_host = ttk.Frame(control_panel)
        control_host.pack(fill="both", expand=True)
        control_host.rowconfigure(0, weight=1)
        control_host.columnconfigure(0, weight=1)
        overview_page, self.overview_tab = self._scrollable_page(control_host)
        contacts_page, self.contacts_tab = self._scrollable_page(control_host)
        session_page, self.session_tab = self._scrollable_page(control_host)
        settings_page, self.settings_tab = self._scrollable_page(control_host)
        self.control_pages = {
            "live-room": overview_page,
            "players": contacts_page,
            "sessions": session_page,
            "connection": settings_page,
        }
        self._build_overview()
        self._build_contacts()
        self._build_session()
        self._build_settings()
        self.show_control_page("live-room")
        self.show_app_page("game-board")

    def _build_board_search(self, parent: tk.Misc) -> None:
        search = ttk.Frame(parent)
        search.pack(side="left", fill="x", expand=True, padx=(0, 8))
        entry_row = ttk.Frame(search)
        entry_row.pack(fill="x")
        self.board_search_value = tk.StringVar()
        self.board_search_entry = ttk.Entry(entry_row, textvariable=self.board_search_value)
        self.board_search_entry.pack(side="left", fill="x", expand=True)
        self.board_search_entry.bind("<Return>", lambda _event: self.add_best_board_map())
        self.board_search_entry.bind("<KeyRelease>", self.show_board_search_suggestions)
        self.board_search_entry.bind("<Escape>", lambda _event: self._close_board_search_suggestions())
        self.board_search_entry.bind("<FocusIn>", self.show_board_search_suggestions)
        self.board_search_entry.bind("<Down>", self.focus_board_search_results)
        ttk.Button(entry_row, text="Add map", command=self.add_best_board_map).pack(side="left", padx=(4, 0))
        ttk.Button(entry_row, text="Explore…", style="Quiet.TButton", command=self.open_board_explorer).pack(side="left", padx=(4, 0))

        self.board_search_results_panel = tk.Frame(
            search,
            background=self.LIGHT,
            highlightbackground=self.ACCENT,
            highlightthickness=1,
        )
        self.board_search_status = tk.Label(
            self.board_search_results_panel,
            text="",
            anchor="w",
            background=self.LIGHT,
            foreground=self.MUTED,
            font=("Segoe UI", 8),
            padx=6,
            pady=3,
        )
        self.board_search_status.pack(fill="x")
        self.board_search_results = tk.Listbox(
            self.board_search_results_panel,
            activestyle="dotbox",
            background="#fff8e6",
            foreground=self.INK,
            highlightthickness=0,
            relief="flat",
            selectbackground=self.ACCENT,
            selectforeground="#fff8e7",
            exportselection=False,
            height=1,
            font=("Segoe UI", 9),
        )
        self.board_search_results.pack(fill="x")
        self.board_search_results.bind("<Double-Button-1>", self.add_selected_board_search_result)
        self.board_search_results.bind("<Return>", self.add_selected_board_search_result)
        self.board_search_results.bind("<Escape>", lambda _event: self._close_board_search_suggestions())
        self.board_search_result_ids: list[str] = []

    def _board_map_search_text(self, record: dict[str, Any]) -> str:
        direct_fields = " ".join(
            str(record.get(field, "") or "")
            for field in (
                "location_name",
                "floor_name",
                "location_id",
                "record_id",
            )
        ).strip()
        ancestor_names = " ".join(
            str(location.get("name", "") or "")
            for location in record.get("location_ancestry", []) or []
        )
        return f"{direct_fields} {ancestor_names}".strip()

    def fuzzy_board_maps(self, query: str, *, limit: int | None = None) -> list[dict[str, Any]]:
        needle = str(query or "").strip().casefold()
        maps = list(self.board_snapshot.get("maps", []))
        if not needle:
            ranked = sorted(maps, key=lambda item: self._board_map_search_text(item).casefold())
            return ranked[:limit] if limit else ranked
        ranked: list[tuple[float, str, dict[str, Any]]] = []
        for record in maps:
            haystack = self._board_map_search_text(record).casefold()
            words = [word for word in re.split(r"\W+", haystack) if word]
            ratio = max([SequenceMatcher(None, needle, haystack).ratio(), *(
                SequenceMatcher(None, needle, word).ratio() for word in words
            )])
            if needle in haystack:
                ratio += 1.0
            if ratio >= 0.32:
                ranked.append((ratio, haystack, record))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        results = [item[2] for item in ranked]
        return results[:limit] if limit else results

    def _board_map_result_label(self, record: dict[str, Any]) -> str:
        location = str(record.get("location_name") or "Location")
        floor = str(record.get("floor_name") or "")
        if record.get("is_location_default"):
            return f"{location}  —  {floor}" if floor else location
        if record.get("is_floor_primary"):
            return f"{floor or 'Floor'}  —  Floor map"
        return f"{location}  —  Assigned map"

    def show_board_search_suggestions(self, event: tk.Event | None = None) -> str:
        if event is not None and event.keysym in {"Return", "Escape", "Up", "Down"}:
            return ""
        query = self.board_search_value.get().strip()
        matches = self.fuzzy_board_maps(query, limit=8)
        self.board_search_results.delete(0, "end")
        self.board_search_result_ids = [str(record.get("record_id")) for record in matches]
        if not matches:
            self.board_search_results.pack_forget()
            self.board_search_status.configure(
                text="No close matches. Try fewer words, a different spelling, or Explore."
            )
            self.board_search_results_panel.pack(fill="x", pady=(3, 0))
            return ""
        for record in matches:
            self.board_search_results.insert("end", self._board_map_result_label(record))
        self.board_search_results.configure(height=min(6, len(matches)))
        if not self.board_search_results.winfo_manager():
            self.board_search_results.pack(fill="x")
        self.board_search_results.selection_set(0)
        self.board_search_results.activate(0)
        self.board_search_status.configure(
            text=(
                f"{len(matches)} maps available — choose one below."
                if not query
                else f"{len(matches)} close {'match' if len(matches) == 1 else 'matches'} — double-click to add."
            )
        )
        self.board_search_results_panel.pack(fill="x", pady=(3, 0))
        return ""

    def focus_board_search_results(self, _event: tk.Event | None = None) -> str:
        if not self.board_search_result_ids:
            self.show_board_search_suggestions()
        if self.board_search_result_ids:
            self.board_search_results.focus_set()
            self.board_search_results.selection_clear(0, "end")
            self.board_search_results.selection_set(0)
            self.board_search_results.activate(0)
        return "break"

    def add_selected_board_search_result(self, _event: tk.Event | None = None) -> str:
        selection = self.board_search_results.curselection()
        if selection and selection[0] < len(self.board_search_result_ids):
            self.add_board_map(self.board_search_result_ids[selection[0]])
        return "break"

    def _close_board_search_suggestions(self) -> None:
        self.board_search_results_panel.pack_forget()
        self.board_search_result_ids = []

    def add_best_board_map(self) -> None:
        selection = self.board_search_results.curselection()
        if selection and selection[0] < len(self.board_search_result_ids):
            self.add_board_map(self.board_search_result_ids[selection[0]])
            return
        query = self.board_search_value.get().strip()
        if not query:
            self.show_board_search_suggestions()
            return
        matches = self.fuzzy_board_maps(query, limit=1)
        if not matches:
            self.show_board_search_suggestions()
            return
        self.add_board_map(str(matches[0].get("record_id")))

    def add_board_map(self, map_id: str) -> None:
        if not any(str(item.get("record_id")) == map_id for item in self.board_snapshot.get("maps", [])):
            return
        if map_id not in self.board_open_map_ids:
            self.board_open_map_ids.append(map_id)
        self.selected_board_map_id = map_id
        self.board_search_value.set("")
        self._close_board_search_suggestions()
        self._render_board(self.board_snapshot)
        self._save_board_workspace()

    def remove_current_board_map(self) -> None:
        map_id = self.selected_board_map_id
        if not map_id:
            return
        draft = self.board_map_drafts.get(map_id, {})
        if draft.get("dirty") and not messagebox.askyesno(
            "Discard unconfirmed changes",
            "Remove this map and discard its unconfirmed Reveal or obscuring changes?",
            parent=self,
        ):
            return
        self.board_open_map_ids = [value for value in self.board_open_map_ids if value != map_id]
        self.board_map_drafts.pop(map_id, None)
        self.selected_board_map_id = self.board_open_map_ids[-1] if self.board_open_map_ids else ""
        self._render_board(self.board_snapshot)
        self._save_board_workspace()

    def _save_board_workspace(self) -> None:
        if not self.selected_session_id:
            return
        payload = {
            "session_id": self.selected_session_id,
            "loaded_map_ids": list(self.board_open_map_ids),
            "active_map_id": self.selected_board_map_id,
        }
        self._background(
            lambda: self.client.request("PUT", "/api/admin/board/workspace", payload),
            quiet=True,
        )

    def open_board_explorer(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Explore locations")
        dialog.transient(self)
        dialog.grab_set()
        dialog.geometry("820x650")
        dialog.minsize(620, 460)
        apply_window_icon(dialog, GAME_BOARD_ICON)
        shell = ttk.Frame(dialog, padding=10)
        shell.pack(fill="both", expand=True)
        query = tk.StringVar(value=self.board_search_value.get())
        ttk.Label(shell, text="Search the world location hierarchy").pack(anchor="w")
        entry = ttk.Entry(shell, textvariable=query)
        entry.pack(fill="x", pady=(2, 6))
        filters = ttk.Frame(shell)
        filters.pack(fill="x", pady=(0, 6))
        include_default = tk.BooleanVar(value=True)
        include_floors = tk.BooleanVar(value=True)
        for text, variable in (
            ("Default maps", include_default),
            ("Floor maps", include_floors),
        ):
            ttk.Checkbutton(filters, text=text, variable=variable).pack(side="left", padx=(0, 12))
        tree = ttk.Treeview(
            shell,
            columns=("assignment", "visibility"),
            show="tree headings",
            selectmode="browse",
        )
        tree.heading("#0", text="Location")
        tree.heading("assignment", text="Assigned map")
        tree.heading("visibility", text="Players")
        tree.column("#0", width=360)
        tree.column("assignment", width=220)
        tree.column("visibility", width=90)
        tree.pack(fill="both", expand=True)
        count = tk.StringVar()
        ttk.Label(shell, textvariable=count).pack(anchor="w", pady=(4, 0))

        def fill(*_args) -> None:
            tree.delete(*tree.get_children())
            matches = []
            location_nodes: set[str] = set()

            def ensure_location_nodes(record: dict[str, Any]) -> str:
                parent = ""
                for location in record.get("location_ancestry", []) or []:
                    location_id = str(location.get("record_id", "") or "")
                    if not location_id:
                        continue
                    tree_id = f"location:{location_id}"
                    if tree_id not in location_nodes:
                        tree.insert(
                            parent,
                            "end",
                            iid=tree_id,
                            text=str(location.get("name") or "Unnamed location"),
                            open=True,
                        )
                        location_nodes.add(tree_id)
                    parent = tree_id
                return parent

            for record in self.fuzzy_board_maps(query.get()):
                is_default = bool(record.get("is_location_default"))
                is_floor = bool(record.get("is_floor_primary"))
                revealed = bool(record.get("players_published"))
                if not (
                    (is_default and include_default.get())
                    or (is_floor and include_floors.get())
                ):
                    continue
                matches.append(record)
                parent = ensure_location_nodes(record)
                roles = []
                if record.get("is_location_default"):
                    roles.append("Default")
                if record.get("is_floor_primary"):
                    roles.append(str(record.get("floor_name") or "Floor"))
                tree.insert(
                    parent,
                    "end",
                    iid=f"map:{record.get('record_id')}",
                    text="Assigned map",
                    values=(
                        " / ".join(roles) or "Assigned",
                        "Revealed" if revealed else "Hidden",
                    ),
                )
            count.set(f"{len(matches):,} assigned location maps")

        def add_selected(*_args) -> None:
            selected = tree.selection()
            if not selected:
                return
            selected_id = selected[0]
            if not selected_id.startswith("map:"):
                tree.item(selected_id, open=not bool(tree.item(selected_id, "open")))
                return
            self.add_board_map(selected_id.removeprefix("map:"))
            dialog.destroy()

        query.trace_add("write", fill)
        for variable in (include_default, include_floors):
            variable.trace_add("write", fill)
        tree.bind("<Double-Button-1>", add_selected)
        actions = ttk.Frame(shell)
        actions.pack(fill="x", pady=(6, 0))
        ttk.Button(actions, text="Cancel", style="Quiet.TButton", command=dialog.destroy).pack(side="right")
        ttk.Button(actions, text="Add selected", command=add_selected).pack(side="right", padx=(0, 5))
        fill()
        entry.focus_set()

    def _build_board_workspace(self, parent: tk.Misc) -> None:
        board_panel = ttk.Frame(parent, style="Card.TFrame")
        board_panel.pack(fill="both", expand=True)

        self.board_notebook = ttk.Notebook(board_panel, style="Board.TNotebook")
        self.board_notebook.pack(fill="both", expand=True)
        self.board_notebook.bind("<<NotebookTabChanged>>", self._board_tab_changed)
        self.board_notebook.bind("<Button-1>", self._board_tab_click, add="+")
        self.board_empty = ttk.Label(
            board_panel,
            text="Search for a map above or use Explore to add one to the Game Board.",
            style="Card.TLabel",
            anchor="center",
        )
        self.board_loading_overlay = tk.Frame(
            board_panel,
            background="#fff8e6",
            highlightbackground=self.ACCENT,
            highlightthickness=1,
        )
        self.board_loading_text = tk.StringVar(value="Restoring saved campaign…")
        tk.Label(
            self.board_loading_overlay,
            textvariable=self.board_loading_text,
            background="#fff8e6",
            foreground=self.INK,
            font=("Segoe UI", 11, "bold"),
            padx=24,
            pady=16,
        ).pack()
        self._show_board_loading()
        self.board_canvases: dict[str, tk.Canvas] = {}
        self.board_canvas_geometry: dict[str, tuple[float, float, float, float]] = {}
        self.board_map_images: dict[str, ImageTk.PhotoImage] = {}
        self.board_map_ids: tuple[str, ...] = ()
        self._board_preview_after: str | None = None
        self.board_actor_tree: ttk.Treeview | None = None
        self.board_transfer_map: ttk.Combobox | None = None
        self.bind_all("<MouseWheel>", self.route_board_wheel, add="+")
        self.bind_all("<B2-Motion>", self.board_pan_drag, add="+")
        self.bind_all("<ButtonRelease-2>", self.board_pan_release, add="+")
        self.bind("<Control-Key-0>", lambda _event: self.fit_current_board_map(), add="+")
        self.bind("<KeyPress-o>", self.board_obscure_shortcut, add="+")
        self.bind("<KeyPress-O>", self.board_obscure_shortcut, add="+")
        self.bind("<Return>", self.complete_board_obscuration, add="+")
        self.bind("<Escape>", lambda _event: self.cancel_board_obscuration(), add="+")
        self.bind("<Delete>", self.delete_board_obscuration_node, add="+")
        self.bind("<BackSpace>", self.delete_board_obscuration_node, add="+")

    def _show_board_loading(self, text: str = "Restoring saved campaign…") -> None:
        if not hasattr(self, "board_loading_overlay"):
            return
        self.board_loading_text.set(text)
        self.board_loading_overlay.place(relx=0.5, rely=0.5, anchor="center")
        self.board_loading_overlay.lift()

    def _hide_board_loading(self) -> None:
        if hasattr(self, "board_loading_overlay"):
            self.board_loading_overlay.place_forget()

    def _create_board_map_controls(self, parent: tk.Misc) -> None:
        map_controls = ttk.Frame(parent, style="Card.TFrame", padding=4)
        self.board_map_controls_dock = map_controls
        self.board_tools_panels["obfuscation-tools"] = map_controls
        header = ttk.Frame(map_controls, style="Card.TFrame")
        header.pack(fill="x", pady=(0, 3))
        ttk.Label(header, text="OBFUSCATION", style="Card.TLabel", font=("Segoe UI", 8, "bold")).pack(side="left")
        self.board_obscure_button = ttk.Button(header, text="✎", width=3, command=self.start_board_obscuration_drawing)
        self.board_obscure_button.pack(side="right")
        delete_button = ttk.Button(header, text="−", width=3, style="Quiet.TButton", command=self.delete_board_obscuration)
        delete_button.pack(side="right", padx=(0, 3))
        self._attach_tooltip(self.board_obscure_button, "Draw a new obfuscation (O)")
        self._attach_tooltip(delete_button, "Delete the selected obfuscation")
        self.board_obscuration_list = tk.Listbox(
            map_controls,
            activestyle="dotbox",
            background="#fff8e6",
            foreground=self.INK,
            highlightbackground=self.EDGE,
            highlightthickness=1,
            relief="flat",
            selectbackground=self.ACCENT,
            selectforeground="#fff8e7",
            exportselection=False,
            height=5,
            font=("Segoe UI", 8),
        )
        self.board_obscuration_list.pack(fill="x", pady=(0, 4))
        self.board_obscuration_list.bind(
            "<<ListboxSelect>>", self.select_board_obscuration_from_list
        )
        self.board_obscuration_list.bind("<Double-Button-1>", self.rename_board_obscuration)
        preview = ttk.Frame(map_controls, style="Card.TFrame")
        preview.pack(fill="x", pady=(0, 4))
        ttk.Label(preview, text="Preview", style="Card.TLabel", font=("Segoe UI", 8, "bold")).pack(side="left")
        ttk.Label(preview, text="%", style="Card.TLabel").pack(side="left", padx=(6, 1))
        opacity = ttk.Spinbox(preview, from_=5, to=100, increment=5, textvariable=self.board_obscure_opacity, width=4)
        opacity.pack(side="left")
        self._attach_tooltip(opacity, "Headmaster preview opacity")
        opacity.bind("<FocusOut>", self.apply_board_obscuration_preview)
        opacity.bind("<Return>", self.apply_board_obscuration_preview)
        self.board_obscure_color_button = tk.Button(
            preview, text="", width=3, background=self.board_obscure_color,
            activebackground=self.board_obscure_color, relief="solid", borderwidth=1,
            command=self.choose_board_obscuration_preview_color,
        )
        self.board_obscure_color_button.pack(side="left", padx=(4, 0))
        self._attach_tooltip(self.board_obscure_color_button, "Headmaster preview color")
        footer = ttk.Frame(map_controls, style="Card.TFrame")
        footer.pack(fill="x")
        self.board_draft_status = tk.Label(
            footer,
            text="",
            anchor="w",
            background=self.LIGHT,
            foreground=self.MUTED,
            font=("Segoe UI", 8),
        )
        self.board_draft_status.pack(side="left", fill="x", expand=True, padx=(2, 4))
        self.board_confirm_button = ttk.Button(
            footer,
            text="Send",
            width=6,
            style="Good.TButton",
            command=self.confirm_board_presentation,
        )
        self.board_confirm_button.pack(side="right")
        self._attach_tooltip(self.board_confirm_button, "Send pending map changes to players")

    def _create_board_token_controls(self, parent: tk.Misc) -> None:
        token_controls = ttk.Frame(parent, style="Card.TFrame", padding=8)
        self.board_token_controls_dock = token_controls
        self.board_tools_panels["token-tools"] = token_controls
        zoom_header = ttk.Frame(token_controls, style="Card.TFrame")
        zoom_header.pack(fill="x", pady=(0, 4))
        ttk.Label(zoom_header, text="TOKENS & ZOOM", style="Card.TLabel", font=("Segoe UI", 8, "bold")).pack(side="left")
        add_override = ttk.Button(zoom_header, text="+", width=3, command=self.add_board_zoom_override)
        add_override.pack(side="right")
        self._attach_tooltip(add_override, "Add a zoom-level size override")
        defaults = ttk.Frame(token_controls, style="Card.TFrame")
        defaults.pack(fill="x", pady=(0, 5))
        self.board_default_token_value = tk.StringVar(value="100")
        self.board_default_zoom_value = tk.StringVar(value="1.00")
        self.board_default_plaque_value = tk.StringVar(value="10")
        self.board_default_position_value = tk.StringVar(value="0.500, 0.500")
        ttk.Label(defaults, text="Token %", style="Card.TLabel", font=("Segoe UI", 7, "bold")).grid(row=0, column=0, sticky="w")
        token_entry = ttk.Entry(defaults, textvariable=self.board_default_token_value, width=6)
        token_entry.grid(row=0, column=1, sticky="ew", padx=(3, 6))
        ttk.Label(defaults, text="Zoom", style="Card.TLabel", font=("Segoe UI", 7, "bold")).grid(row=0, column=2, sticky="w")
        zoom_entry = ttk.Entry(defaults, textvariable=self.board_default_zoom_value, width=6)
        zoom_entry.grid(row=0, column=3, sticky="ew", padx=(3, 6))
        ttk.Label(defaults, text="Plaque", style="Card.TLabel", font=("Segoe UI", 7, "bold")).grid(row=0, column=4, sticky="w")
        plaque_entry = ttk.Entry(defaults, textvariable=self.board_default_plaque_value, width=4)
        plaque_entry.grid(row=0, column=5, sticky="ew", padx=(3, 3))
        zoom_target = ttk.Button(defaults, text="◎", width=3, style="Quiet.TButton", command=self.use_current_board_zoom_as_default)
        zoom_target.grid(row=0, column=6)
        self._attach_tooltip(zoom_target, "Use the current camera zoom as this map's default")
        ttk.Label(defaults, text="Position", style="Card.TLabel", font=("Segoe UI", 7, "bold")).grid(row=1, column=0, sticky="w", pady=(4, 0))
        position_entry = ttk.Entry(defaults, textvariable=self.board_default_position_value, width=16)
        position_entry.grid(row=1, column=1, columnspan=5, sticky="ew", padx=(3, 3), pady=(4, 0))
        position_target = ttk.Button(defaults, text="⌖", width=3, style="Quiet.TButton", command=self.use_current_board_position_as_default)
        position_target.grid(row=1, column=6, pady=(4, 0))
        self._attach_tooltip(position_target, "Use the current camera position as this map's default")
        for entry in (token_entry, zoom_entry, plaque_entry, position_entry):
            entry.bind("<FocusOut>", lambda _event: self.save_board_zoom_profile())
            entry.bind("<Return>", lambda _event: self.save_board_zoom_profile())
        defaults.columnconfigure(1, weight=1)
        defaults.columnconfigure(3, weight=1)
        defaults.columnconfigure(5, weight=1)
        token_entry.bind("<KeyRelease>", self.preview_board_token_percent)
        plaque_entry.bind("<KeyRelease>", self.preview_board_default_plaque_size)
        override_header = ttk.Frame(token_controls, style="Card.TFrame")
        override_header.pack(fill="x", pady=(2, 0))
        ttk.Label(override_header, text="Clicks", width=6, style="Card.TLabel", font=("Segoe UI", 7, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(override_header, text="Token", width=7, style="Card.TLabel", font=("Segoe UI", 7, "bold")).grid(row=0, column=1, sticky="w")
        ttk.Label(override_header, text="Plaque", width=7, style="Card.TLabel", font=("Segoe UI", 7, "bold")).grid(row=0, column=2, sticky="w")
        self.board_zoom_override_rows = ttk.Frame(token_controls, style="Card.TFrame")
        self.board_zoom_override_rows.pack(fill="x", pady=(0, 2))
        return
        token_row = ttk.Frame(token_controls, style="Card.TFrame")
        token_row.pack(fill="x", pady=(0, 3))
        ttk.Button(
            token_row,
            text="âˆ’",
            width=3,
            style="Quiet.TButton",
            command=lambda: self.adjust_current_map_token_scale(-1),
        ).pack(side="left")
        self.board_token_size_label = ttk.Label(
            token_row, text="100%", anchor="center", style="Card.TLabel"
        )
        self.board_token_size_label.pack(side="left", fill="x", expand=True)
        ttk.Button(
            token_row,
            text="+",
            width=3,
            style="Quiet.TButton",
            command=lambda: self.adjust_current_map_token_scale(1),
        ).pack(side="right")
        ttk.Button(
            token_controls,
            text="Open zoom profile…",
            command=self.open_board_zoom_controls,
        ).pack(fill="x", pady=(4, 0))

    def _create_board_secret_controls(self, parent: tk.Misc) -> None:
        shell = ttk.Frame(parent, style="Card.TFrame", padding=5)
        self.board_secrets_dock = shell
        self.board_tools_panels["secrets"] = shell

        header = ttk.Frame(shell, style="Card.TFrame")
        header.pack(fill="x", pady=(0, 4))
        ttk.Label(
            header, text="SECRETS", style="Card.TLabel", font=("Segoe UI", 8, "bold")
        ).pack(side="left")
        self.board_secret_action_button = ttk.Button(
            header,
            text="Reveal",
            width=9,
            style="Good.TButton",
            command=self.toggle_selected_board_secret,
        )
        self.board_secret_action_button.pack(side="right")
        self._attach_tooltip(
            self.board_secret_action_button,
            "Reveal or conceal the selected secret for every player",
        )

        self.board_secret_list = tk.Listbox(
            shell,
            exportselection=False,
            height=12,
            background="#fff8e6",
            foreground=self.INK,
            selectbackground=self.ACCENT,
            selectforeground="#fff8e7",
            borderwidth=1,
            relief="solid",
            font=("Segoe UI", 9),
        )
        self.board_secret_list.pack(fill="both", expand=True)
        self.board_secret_list.bind(
            "<<ListboxSelect>>", lambda _event: self._sync_board_secret_controls()
        )
        self.board_secret_list.bind(
            "<Double-Button-1>", lambda _event: self.toggle_selected_board_secret()
        )
        self.board_secret_status = tk.StringVar(value="Open a map to view its secrets.")
        ttk.Label(
            shell,
            textvariable=self.board_secret_status,
            style="Card.TLabel",
            wraplength=320,
            justify="left",
            font=("Segoe UI", 8),
        ).pack(fill="x", pady=(4, 0))
        self._refresh_board_secret_list()

    def _selected_board_secret(self) -> dict[str, Any] | None:
        if not hasattr(self, "board_secret_list"):
            return None
        selection = self.board_secret_list.curselection()
        if not selection:
            return None
        index = int(selection[0])
        if index >= len(self.board_secret_region_ids):
            return None
        region_id = self.board_secret_region_ids[index]
        current_map = self._current_board_map() or {}
        return next(
            (
                region
                for region in current_map.get("regions", [])
                if str(region.get("record_id", "")) == region_id
            ),
            None,
        )

    def _refresh_board_secret_list(self) -> None:
        if not hasattr(self, "board_secret_list"):
            return
        previous_id = ""
        selected = self.board_secret_list.curselection()
        if selected and int(selected[0]) < len(self.board_secret_region_ids):
            previous_id = self.board_secret_region_ids[int(selected[0])]

        self.board_secret_list.delete(0, "end")
        self.board_secret_region_ids = []
        current_map = self._current_board_map()
        revealed = {
            str(value)
            for value in self.board_snapshot.get("revealed_secret_region_ids", [])
        }
        secrets = [
            region
            for region in (current_map or {}).get("regions", [])
            if str(region.get("behavior_type", "")) == "secret"
        ]
        secrets.sort(key=lambda region: str(region.get("name") or "Secret").casefold())
        for region in secrets:
            region_id = str(region.get("record_id", ""))
            state = "Shown" if region_id in revealed else "Hidden"
            passage = "  [passage]" if region.get("secret_passage") else ""
            self.board_secret_list.insert(
                "end", f"{state:<6}  {str(region.get('name') or 'Secret')}{passage}"
            )
            self.board_secret_region_ids.append(region_id)

        if previous_id in self.board_secret_region_ids:
            index = self.board_secret_region_ids.index(previous_id)
            self.board_secret_list.selection_set(index)
            self.board_secret_list.see(index)
        elif self.board_secret_region_ids:
            self.board_secret_list.selection_set(0)

        if current_map is None:
            self.board_secret_status.set("Open a map to view its secrets.")
        elif not secrets:
            self.board_secret_status.set("This map has no authored secrets.")
        else:
            self.board_secret_status.set(
                "Double-click a secret or use Reveal/Conceal. Passages become travel regions when shown."
            )
        self._sync_board_secret_controls()

    def _sync_board_secret_controls(self) -> None:
        if not hasattr(self, "board_secret_action_button"):
            return
        region = self._selected_board_secret()
        if region is None:
            self.board_secret_action_button.configure(text="Reveal", state="disabled")
            return
        revealed = {
            str(value)
            for value in self.board_snapshot.get("revealed_secret_region_ids", [])
        }
        is_revealed = str(region.get("record_id", "")) in revealed
        self.board_secret_action_button.configure(
            text="Conceal" if is_revealed else "Reveal",
            state="normal",
            style="Quiet.TButton" if is_revealed else "Good.TButton",
        )

    def toggle_selected_board_secret(self) -> None:
        region = self._selected_board_secret()
        session = self._selected_session()
        session_id = str(
            self.board_snapshot.get("session_id", "")
            or (session or {}).get("id", "")
        )
        map_id = self.selected_board_map_id
        if region is None or not session_id or not map_id:
            self.bell()
            self.set_notice("Select a secret on an open session map", error=True)
            return
        revealed = {
            str(value)
            for value in self.board_snapshot.get("revealed_secret_region_ids", [])
        }
        region_id = str(region.get("record_id", ""))
        make_visible = region_id not in revealed
        payload = {
            "session_id": session_id,
            "map_id": map_id,
            "revealed": make_visible,
        }

        def changed(_result: Any) -> None:
            action = "revealed to" if make_visible else "concealed from"
            self.set_notice(
                f"{str(region.get('name') or 'Secret')} was {action} all players"
            )
            self.refresh(silent=True)

        self._background(
            lambda: self.client.request(
                "PUT",
                f"/api/admin/board/secrets/{region_id}/visibility",
                payload,
            ),
            changed,
        )

    def open_board_map_controls(self) -> None:
        self.show_board_tools_panel("obfuscation-tools")

    def hide_board_map_controls(self) -> None:
        if self.board_obscure_drawing:
            self.bell()
            self.board_draft_status.configure(
                text="Finish or cancel the current obfuscation before hiding Map Tools.",
                foreground=self.RED,
            )
            return
        dock = self.board_map_controls_dock
        if dock is not None and dock.winfo_exists():
            dock.pack_forget()

    def _board_tools_unmapped(self, _event: tk.Event | None = None) -> None:
        return

    def _attach_tooltip(self, widget: tk.Widget, text: str) -> None:
        """Show compact hover help for icon-only controls."""
        state: dict[str, object | None] = {"after": None, "window": None}

        def hide(_event: tk.Event | None = None) -> None:
            after_id = state.get("after")
            if after_id is not None:
                widget.after_cancel(after_id)
                state["after"] = None
            window = state.get("window")
            if isinstance(window, tk.Toplevel) and window.winfo_exists():
                window.destroy()
            state["window"] = None

        def show() -> None:
            state["after"] = None
            if not widget.winfo_exists():
                return
            window = tk.Toplevel(widget)
            window.wm_overrideredirect(True)
            window.attributes("-topmost", True)
            tk.Label(
                window,
                text=text,
                background="#32251d",
                foreground="#fff5d6",
                relief="solid",
                borderwidth=1,
                padx=6,
                pady=3,
                font=("Segoe UI", 8),
            ).pack()
            window.update_idletasks()
            tooltip_width = window.winfo_reqwidth()
            tooltip_height = window.winfo_reqheight()
            screen_left = window.winfo_vrootx()
            screen_top = window.winfo_vrooty()
            screen_right = screen_left + window.winfo_vrootwidth()
            screen_bottom = screen_top + window.winfo_vrootheight()
            desired_x = widget.winfo_rootx() + (widget.winfo_width() - tooltip_width) // 2
            x = max(screen_left + 3, min(desired_x, screen_right - tooltip_width - 3))
            below_y = widget.winfo_rooty() + widget.winfo_height() + 3
            above_y = widget.winfo_rooty() - tooltip_height - 3
            y = below_y if below_y + tooltip_height <= screen_bottom - 3 else max(screen_top + 3, above_y)
            window.wm_geometry(f"+{x}+{y}")
            state["window"] = window

        def schedule(_event: tk.Event | None = None) -> None:
            hide()
            state["after"] = widget.after(350, show)

        widget.bind("<Enter>", schedule, add="+")
        widget.bind("<Leave>", hide, add="+")
        widget.bind("<ButtonPress>", hide, add="+")

    def _create_board_groups_controls(self, parent: tk.Misc) -> None:
        shell = ttk.Frame(parent, style="Card.TFrame", padding=5)
        self.board_groups_dock = shell
        self.board_tools_panels["groups"] = shell
        group_header = ttk.Frame(shell, style="Card.TFrame")
        group_header.pack(fill="x")
        ttk.Label(group_header, text="CHARACTERS", style="Card.TLabel", font=("Segoe UI", 8, "bold")).pack(side="left")
        for text, command, help_text in (
            ("G+", self.create_board_group, "Create a colored character group"),
            ("+", self.open_add_character_menu, "Add a character to this map"),
        ):
            button = ttk.Button(group_header, text=text, width=3, style="Quiet.TButton", command=command)
            button.pack(side="right", padx=(3, 0))
            self._attach_tooltip(button, help_text)
        self.board_actor_search_var = tk.StringVar()
        search = ttk.Entry(shell, textvariable=self.board_actor_search_var)
        search.pack(fill="x", pady=(4, 3))
        self._attach_tooltip(search, "Search characters on this map")
        self.board_actor_search_var.trace_add("write", lambda *_args: self._render_board_actor_list())
        self.board_actor_rows_canvas = tk.Canvas(
            shell, background="#fff8e6", borderwidth=0, highlightthickness=1,
            highlightbackground=self.EDGE, height=190,
        )
        actor_scroll = ttk.Scrollbar(shell, orient="vertical", command=self.board_actor_rows_canvas.yview)
        self.board_actor_rows_canvas.configure(yscrollcommand=actor_scroll.set)
        self.board_actor_rows_canvas.pack(side="left", fill="both", expand=True, pady=(0, 2))
        actor_scroll.pack(side="right", fill="y", pady=(0, 2))
        self.board_actor_rows_frame = tk.Frame(self.board_actor_rows_canvas, background="#fff8e6")
        self._board_actor_rows_window = self.board_actor_rows_canvas.create_window(
            (0, 0), window=self.board_actor_rows_frame, anchor="nw"
        )
        self.board_actor_rows_frame.bind(
            "<Configure>",
            lambda _event: self.board_actor_rows_canvas.configure(
                scrollregion=self.board_actor_rows_canvas.bbox("all")
            ),
        )
        self.board_actor_rows_canvas.bind(
            "<Configure>",
            lambda event: self.board_actor_rows_canvas.itemconfigure(
                self._board_actor_rows_window, width=max(1, event.width)
            ),
        )
        self.board_actor_tree = None
        self.board_transfer_map = None
        self._render_board_actor_list()
        self._render_board_creature_list()

    def _create_board_creature_controls(self, parent: tk.Misc) -> None:
        shell = ttk.Frame(parent, style="Card.TFrame", padding=5)
        self.board_creatures_dock = shell
        self.board_tools_panels["creatures"] = shell
        header = ttk.Frame(shell, style="Card.TFrame")
        header.pack(fill="x")
        ttk.Label(
            header, text="CREATURES", style="Card.TLabel",
            font=("Segoe UI", 8, "bold"),
        ).pack(side="left")
        add = ttk.Button(
            header, text="+", width=3, style="Quiet.TButton",
            command=self.open_add_creature_dialog,
        )
        add.pack(side="right")
        self._attach_tooltip(add, "Add one or more creatures to the open map")
        self.board_creature_search_var = tk.StringVar()
        search = ttk.Entry(shell, textvariable=self.board_creature_search_var)
        search.pack(fill="x", pady=(4, 3))
        self._attach_tooltip(search, "Search creatures on this map")
        self.board_creature_search_var.trace_add(
            "write", lambda *_args: self._render_board_creature_list()
        )
        self.board_creature_list = tk.Listbox(
            shell, height=6, exportselection=False,
            background="#fff8e6", foreground=self.INK,
            selectbackground=self.ACCENT, selectforeground="#fff8e7",
        )
        self.board_creature_list.pack(fill="both", expand=True)
        self.board_creature_list.bind(
            "<<ListboxSelect>>", self._board_creature_selected
        )
        self.board_creature_list.bind(
            "<Button-3>", self._board_creature_list_menu
        )
        self.board_creature_details = tk.Label(
            shell, text="No creature selected", justify="left", anchor="nw",
            background=self.LIGHT, foreground=self.INK,
            font=("Segoe UI", 8), padx=3, pady=3,
        )
        self.board_creature_details.pack(fill="x", pady=(3, 2))
        self.board_creature_actions = tk.Listbox(
            shell, height=4, exportselection=False,
            background="#fff8e6", foreground=self.INK,
            selectbackground=self.ACCENT, selectforeground="#fff8e7",
        )
        self.board_creature_actions.pack(fill="x")
        self.board_creature_actions.bind(
            "<Double-Button-1>", self.roll_selected_creature_action
        )
        buttons = ttk.Frame(shell, style="Card.TFrame")
        buttons.pack(fill="x", pady=(3, 0))
        for text, command, help_text in (
            ("◉", self.toggle_selected_creature_visibility, "Reveal or hide this creature"),
            ("+W", self.wound_selected_creature, "Assign a wound"),
            ("☠", self.toggle_selected_creature_life, "Mark dead or revive"),
            ("⚄", self.roll_selected_creature_action, "Roll the selected attack or ability"),
        ):
            button = ttk.Button(
                buttons, text=text, width=3, style="Quiet.TButton", command=command
            )
            button.pack(side="left", fill="x", expand=True, padx=(0, 2))
            self._attach_tooltip(button, help_text)

    def _current_map_creatures(self) -> list[dict[str, Any]]:
        query = (
            self.board_creature_search_var.get().strip().casefold()
            if hasattr(self, "board_creature_search_var") else ""
        )
        values = [
            actor for actor in self.board_snapshot.get("actors", [])
            if actor.get("actor_type") == "creature"
            and actor.get("map_id") == self.selected_board_map_id
            and (
                not query
                or query in str(actor.get("internal_label") or actor.get("name") or "").casefold()
            )
        ]
        return sorted(
            values,
            key=lambda item: str(item.get("internal_label") or item.get("name") or "").casefold(),
        )

    def _render_board_creature_list(self) -> None:
        listing = getattr(self, "board_creature_list", None)
        if listing is None or not listing.winfo_exists():
            return
        current = self.selected_board_actor_id
        creatures = self._current_map_creatures()
        self.board_creature_ids = [str(item.get("actor_id", "")) for item in creatures]
        listing.delete(0, "end")
        selected_index = None
        for index, creature in enumerate(creatures):
            life = " †" if creature.get("life_state") == "dead" else ""
            hidden = " (hidden)" if creature.get("visibility") != "players" else ""
            listing.insert(
                "end",
                f"{creature.get('internal_label') or creature.get('name') or 'Creature'}{life}{hidden}",
            )
            if str(creature.get("actor_id")) == current:
                selected_index = index
        if selected_index is not None:
            listing.selection_set(selected_index)
            listing.see(selected_index)
        self._render_selected_creature_details()

    def _board_creature_selected(self, _event: tk.Event | None = None) -> None:
        selected = self.board_creature_list.curselection()
        if not selected:
            return
        index = int(selected[0])
        if index >= len(self.board_creature_ids):
            return
        self.selected_board_actor_id = self.board_creature_ids[index]
        self._render_selected_creature_details()
        self._draw_board_map(self.selected_board_map_id)

    def _selected_creature(self) -> dict[str, Any] | None:
        actor = self._selected_board_actor()
        return actor if actor and actor.get("actor_type") == "creature" else None

    def _render_selected_creature_details(self) -> None:
        details = getattr(self, "board_creature_details", None)
        actions = getattr(self, "board_creature_actions", None)
        if details is None or actions is None:
            return
        creature = self._selected_creature()
        actions.delete(0, "end")
        if creature is None:
            details.configure(text="No creature selected")
            return
        generated = creature.get("generated", {}) or {}
        wounds = creature.get("wounds", []) or []
        details.configure(text=(
            f"{creature.get('internal_label') or creature.get('name')}  ·  "
            f"{creature.get('life_state', 'alive').title()}\n"
            f"Size {generated.get('size', '—')}   Heavy cap {generated.get('heavy_wound_cap', '—')}   "
            f"Wounds {len(wounds)}"
        ))
        for action in creature.get("actions", []) or []:
            shown_range = action.get("adjusted_range", {}) or {}
            actions.insert(
                "end",
                f"{action.get('name', 'Action')}  [{action.get('aptitude', 'typical')}; "
                f"{shown_range.get('low', 0)}–{shown_range.get('high', 0)}]",
            )

    def open_add_creature_dialog(self) -> None:
        if not self.selected_session_id or not self.selected_board_map_id:
            messagebox.showinfo(
                "Add creature", "Open a campaign session and a map first.", parent=self
            )
            return
        dialog = tk.Toplevel(self)
        dialog.title("Add Creatures")
        dialog.transient(self)
        dialog.grab_set()
        dialog.geometry("620x560")
        dialog.minsize(460, 380)
        apply_window_icon(dialog, GAME_BOARD_ICON)
        body = ttk.Frame(dialog, padding=10)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Creature catalog", style="Title.TLabel").pack(anchor="w")
        query = tk.StringVar()
        search = ttk.Entry(body, textvariable=query)
        search.pack(fill="x", pady=(5, 5))
        results = tk.Listbox(
            body, exportselection=False, background="#fff8e6",
            foreground=self.INK, selectbackground=self.ACCENT,
            selectforeground="#fff8e7",
        )
        results.pack(fill="both", expand=True)
        detail = ttk.Label(body, text="Search and select a species.", style="Card.TLabel", wraplength=560)
        detail.pack(fill="x", pady=(5, 4))
        quantity_row = ttk.Frame(body)
        quantity_row.pack(fill="x")
        ttk.Label(quantity_row, text="Quantity").pack(side="left")
        quantity = tk.IntVar(value=1)
        ttk.Spinbox(quantity_row, from_=1, to=50, textvariable=quantity, width=5).pack(side="left", padx=5)
        records: list[dict[str, Any]] = []
        selected_id = tk.StringVar()
        search_after: list[str | None] = [None]

        def show_records(payload: Any) -> None:
            records[:] = list((payload or {}).get("creatures", []))
            results.delete(0, "end")
            for item in records:
                suffix = f"  [{item.get('classification')}]" if item.get("classification") else ""
                results.insert("end", f"{item.get('name', 'Creature')}{suffix}")

        def run_search() -> None:
            search_after[0] = None
            term = query.get().strip()
            self._background(
                lambda: self.client.request(
                    "GET", f"/api/admin/creatures?q={urllib.parse.quote(term)}&limit=250"
                ),
                show_records,
            )

        def schedule(*_args: Any) -> None:
            if search_after[0] is not None:
                dialog.after_cancel(search_after[0])
            search_after[0] = dialog.after(180, run_search)

        def choose(_event: tk.Event | None = None) -> None:
            selected = results.curselection()
            if not selected:
                selected_id.set("")
                return
            item = records[int(selected[0])]
            selected_id.set(str(item.get("record_id", "")))
            detail.configure(text=(
                f"{item.get('name', 'Creature')} · {item.get('family', '')}\n"
                f"{item.get('attacks', 0)} attacks · {item.get('abilities', 0)} abilities · "
                f"{item.get('parts', 0)} harvestable parts\n{item.get('description', '')}"
            ))

        def begin() -> None:
            if not selected_id.get():
                messagebox.showwarning("Add creatures", "Choose a creature species first.", parent=dialog)
                return
            count = max(1, min(50, int(quantity.get())))
            selected = next(
                item for item in records
                if str(item.get("record_id", "")) == selected_id.get()
            )
            self.creature_placement = {
                "species_id": selected_id.get(),
                "species_name": str(selected.get("name") or "Creature"),
                "quantity": count, "placed": 0, "busy": False,
            }
            dialog.destroy()
            self._update_creature_placement_notice()
            canvas = self.board_canvases.get(self.selected_board_map_id)
            if canvas is not None:
                canvas.configure(cursor="crosshair")

        query.trace_add("write", schedule)
        results.bind("<<ListboxSelect>>", choose)
        controls = ttk.Frame(body)
        controls.pack(fill="x", pady=(7, 0))
        ttk.Button(controls, text="Cancel", style="Quiet.TButton", command=dialog.destroy).pack(side="right")
        ttk.Button(controls, text="Place on map", command=begin).pack(side="right", padx=(0, 5))
        run_search()
        search.focus_set()

    def _update_creature_placement_notice(self) -> None:
        placement = self.creature_placement
        if not placement:
            return
        next_number = int(placement["placed"]) + 1
        self.set_notice(
            f"Place {placement['species_name']} {next_number} of {placement['quantity']} · Esc cancels the remainder"
        )

    def _cancel_creature_placement(self, _event: tk.Event | None = None) -> str:
        if not self.creature_placement:
            return ""
        remaining = int(self.creature_placement["quantity"]) - int(self.creature_placement["placed"])
        self.creature_placement = None
        for canvas in self.board_canvases.values():
            canvas.configure(cursor="arrow")
        self.set_notice(f"Creature placement ended · {remaining} unplaced")
        return "break"

    def _place_next_creature(self, event: tk.Event, map_id: str) -> None:
        placement = self.creature_placement
        if not placement or placement.get("busy"):
            return
        x, y = self._normalized_board_point(map_id, event.x, event.y)
        payload = {
            "session_id": self.selected_session_id,
            "species_id": placement["species_id"],
            "map_id": map_id, "x": x, "y": y,
        }
        placement["busy"] = True

        def placed(_result: Any) -> None:
            current = self.creature_placement
            if current is None:
                self.refresh(silent=True)
                return
            current["busy"] = False
            current["placed"] = int(current["placed"]) + 1
            if int(current["placed"]) >= int(current["quantity"]):
                self.creature_placement = None
                for canvas in self.board_canvases.values():
                    canvas.configure(cursor="arrow")
                self.set_notice("Creature batch placed")
            else:
                self._update_creature_placement_notice()
            self.refresh(silent=True)

        self._background(
            lambda: self.client.request("POST", "/api/admin/board/creatures", payload),
            placed,
        )

    def _board_creature_list_menu(self, event: tk.Event) -> str:
        index = self.board_creature_list.nearest(event.y)
        if 0 <= index < len(self.board_creature_ids):
            self.selected_board_actor_id = self.board_creature_ids[index]
            self._render_board_creature_list()
            self._open_piece_controls(event.widget, event.x_root, event.y_root)
        return "break"

    def _creature_action_request(self, action: str, **values: Any) -> None:
        creature = self._selected_creature()
        if creature is None or not self.selected_session_id:
            return
        payload = {"session_id": self.selected_session_id, "action": action, **values}
        self._background(
            lambda: self.client.request(
                "POST", f"/api/admin/board/creatures/{creature['actor_id']}/actions", payload
            ),
            lambda _result: self.refresh(silent=True),
        )

    def toggle_selected_creature_visibility(self) -> None:
        creature = self._selected_creature()
        if creature is None:
            return
        visibility = "headmaster" if creature.get("visibility") == "players" else "players"
        self._background(
            lambda: self.client.request(
                "PUT", f"/api/admin/board/creatures/{creature['actor_id']}",
                {"session_id": self.selected_session_id, "visibility": visibility},
            ),
            lambda _result: self.refresh(silent=True),
        )

    def manage_creature_group(self) -> None:
        creature = self._selected_creature()
        if creature is None:
            return
        groups = [
            item for item in self.board_snapshot.get("groups", []) or []
            if str(item.get("location_id", "")) == str(creature.get("location_id", ""))
        ]
        dialog = tk.Toplevel(self)
        dialog.title("Creature Group")
        dialog.transient(self)
        dialog.grab_set()
        dialog.geometry("440x390")
        apply_window_icon(dialog, GAME_BOARD_ICON)
        body = ttk.Frame(dialog, padding=10)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Group", style="Title.TLabel").pack(anchor="w")
        query = tk.StringVar()
        ttk.Entry(body, textvariable=query).pack(fill="x", pady=(4, 5))
        listing = tk.Listbox(
            body, exportselection=False, background="#fff8e6",
            foreground=self.INK, selectbackground=self.ACCENT,
            selectforeground="#fff8e7",
        )
        listing.pack(fill="both", expand=True)
        visible: list[dict[str, Any]] = []

        def render(*_args: Any) -> None:
            term = query.get().strip().casefold()
            visible[:] = [
                item for item in groups
                if not term or term in str(item.get("name", "")).casefold()
            ]
            listing.delete(0, "end")
            listing.insert("end", "No group")
            for item in visible:
                listing.insert("end", str(item.get("name") or "Group"))

        def apply_group() -> None:
            selected = listing.curselection()
            if not selected:
                return
            index = int(selected[0])
            group_id = None if index == 0 else str(visible[index - 1].get("record_id", ""))
            dialog.destroy()
            self._background(
                lambda: self.client.request(
                    "PUT", f"/api/admin/board/groups/creatures/{creature['actor_id']}",
                    {"session_id": self.selected_session_id, "group_id": group_id},
                ),
                lambda _result: self.refresh(silent=True),
            )

        query.trace_add("write", render)
        listing.bind("<Double-Button-1>", lambda _event: apply_group())
        controls = ttk.Frame(body)
        controls.pack(fill="x", pady=(6, 0))
        ttk.Button(controls, text="Cancel", style="Quiet.TButton", command=dialog.destroy).pack(side="right")
        ttk.Button(controls, text="Apply", command=apply_group).pack(side="right", padx=(0, 5))
        render()

    def wound_selected_creature(self) -> None:
        creature = self._selected_creature()
        if creature is None:
            return
        menu = tk.Menu(self, tearoff=False)
        for severity in ("light", "medium", "heavy"):
            menu.add_command(
                label=severity.title(),
                command=lambda value=severity: self._creature_action_request(
                    "wound", severity=value
                ),
            )
        try:
            menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())
        finally:
            menu.grab_release()

    def toggle_selected_creature_life(self) -> None:
        creature = self._selected_creature()
        if creature:
            self._creature_action_request(
                "revive" if creature.get("life_state") == "dead" else "kill"
            )

    def roll_selected_creature_action(self, _event: tk.Event | None = None) -> None:
        creature = self._selected_creature()
        selected = self.board_creature_actions.curselection()
        actions = list((creature or {}).get("actions", []) or [])
        if creature is None or not selected or int(selected[0]) >= len(actions):
            return
        action = actions[int(selected[0])]
        self._background(
            lambda: self.client.request(
                "POST", f"/api/admin/board/creatures/{creature['actor_id']}/roll",
                {"session_id": self.selected_session_id, "action_id": action["record_id"]},
            ),
            lambda _result: self.refresh(silent=True),
        )

    def interact_with_selected_creature(self) -> None:
        creature = self._selected_creature()
        if creature is None or not self.selected_session_id:
            return
        actors = [
            {"record_id": str(item.get("actor_id", "")), "name": str(item.get("name", "Character"))}
            for item in self.board_snapshot.get("actors", []) or []
            if item.get("actor_type") != "creature"
            and item.get("map_id") == creature.get("map_id")
        ]
        if not actors:
            messagebox.showinfo("Creature interaction", "No characters are currently on this map.", parent=self)
            return
        dialog = tk.Toplevel(self)
        dialog.title(f"Interact with {creature.get('internal_label') or creature.get('name') or 'Creature'}")
        dialog.transient(self)
        dialog.grab_set()
        dialog.geometry("620x520")
        apply_window_icon(dialog, GAME_BOARD_ICON)
        shell = ttk.Frame(dialog, padding=10)
        shell.pack(fill="both", expand=True)
        actor_id = tk.StringVar()
        action = tk.StringVar(value="capture")
        creature_name = tk.StringVar()
        ttk.Label(shell, text="Acting character", style="CardTitle.TLabel").pack(anchor="w")
        self._searchable_record_panel(shell, actors, actor_id, height=8).pack(fill="both", expand=True, pady=(0, 8))
        action_row = ttk.Frame(shell)
        action_row.pack(fill="x")
        rules = creature.get("interaction_rules", {}) or {}
        for value, label in (("capture", "Capture"), ("lure", "Lure"), ("tame", "Tame"), ("bond", "Bond")):
            enabled = bool((rules.get(value) or {}).get("enabled", value == "capture"))
            ttk.Radiobutton(
                action_row, text=label, variable=action, value=value,
                state="normal" if enabled else "disabled",
            ).pack(side="left", padx=(0, 10))
        name_row = ttk.Frame(shell)
        name_row.pack(fill="x", pady=8)
        ttk.Label(name_row, text="Name if tamed").pack(side="left")
        ttk.Entry(name_row, textvariable=creature_name).pack(side="left", fill="x", expand=True, padx=(8, 0))
        ttk.Label(
            shell,
            text="Capture requires no creature proficiency. Lure, Tame, and Bond require the acting character's species proficiency.",
            style="Status.TLabel", wraplength=570,
        ).pack(fill="x")
        buttons = ttk.Frame(shell)
        buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(buttons, text="Cancel", style="Quiet.TButton", command=dialog.destroy).pack(side="right")

        def roll() -> None:
            if not actor_id.get():
                messagebox.showinfo("Creature interaction", "Choose an acting character.", parent=dialog)
                return
            payload = {
                "session_id": self.selected_session_id,
                "actor_person_id": actor_id.get(),
                "action": action.get(),
                "creature_name": creature_name.get().strip(),
            }
            dialog.destroy()
            self._background(
                lambda: self.client.request(
                    "POST", f"/api/admin/board/creatures/{creature['actor_id']}/interact", payload
                ),
                lambda _result: self.refresh(silent=True),
            )

        ttk.Button(buttons, text="Roll", command=roll).pack(side="right", padx=(0, 6))

    def open_add_character_menu(self) -> None:
        if not self.selected_session_id or not self.selected_board_map_id:
            messagebox.showinfo(
                "Add character",
                "Open a campaign session and a map first.",
                parent=self,
            )
            return
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(label="Choose from World Builderâ€¦", command=self.choose_character_for_map)
        menu.add_command(label="Quick new characterâ€¦", command=self.quick_create_character_for_map)
        try:
            menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())
        finally:
            menu.grab_release()

    def choose_character_for_map(self) -> None:
        characters = list(self.character_choices)
        if not characters:
            messagebox.showinfo(
                "Add character",
                "No characters are available in World Builder.",
                parent=self,
            )
            return
        dialog = tk.Toplevel(self)
        dialog.title("Add Character to Map")
        dialog.transient(self)
        dialog.grab_set()
        dialog.geometry("600x560")
        dialog.minsize(440, 360)
        apply_window_icon(dialog, GAME_BOARD_ICON)
        body = ttk.Frame(dialog, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Add Character", style="Title.TLabel").pack(anchor="w")
        query = tk.StringVar()
        search = ttk.Entry(body, textvariable=query)
        search.pack(fill="x", pady=(6, 7))
        results = tk.Listbox(
            body,
            exportselection=False,
            background="#fff8e6",
            foreground=self.INK,
            selectbackground=self.ACCENT,
            selectforeground="#fff8e7",
        )
        results.pack(fill="both", expand=True)
        status = ttk.Label(body, text="", style="Status.TLabel")
        status.pack(anchor="w", pady=(5, 0))
        visible: list[dict[str, Any]] = []

        def fill(*_args: object) -> None:
            search_text = " ".join(query.get().strip().casefold().split())
            ranked: list[tuple[float, dict[str, Any]]] = []
            for item in characters:
                name = " ".join(str(item.get("name", "")).casefold().split())
                if not search_text:
                    score = 1.0
                elif search_text in name:
                    score = 2.0 - (name.index(search_text) / max(1, len(name)))
                else:
                    score = SequenceMatcher(None, search_text, name).ratio()
                    word_scores = [
                        SequenceMatcher(None, word, candidate).ratio()
                        for word in search_text.split()
                        for candidate in name.split()
                    ]
                    score = max([score, *word_scores])
                    if score < 0.58:
                        continue
                ranked.append((score, item))
            ranked.sort(
                key=lambda value: (
                    -value[0],
                    str(value[1].get("name", "")).casefold(),
                )
            )
            visible[:] = [item for _score, item in ranked]
            results.delete(0, "end")
            for item in visible:
                results.insert("end", str(item.get("name") or "Unnamed character"))
            status.configure(text=f"{len(visible)} character(s) shown")
            if visible:
                results.selection_set(0)

        def place(confirm_move: bool = False) -> None:
            selection = results.curselection()
            if not selection:
                return
            character = visible[selection[0]]
            payload = {
                "session_id": self.selected_session_id,
                "person_id": character["id"],
                "map_id": self.selected_board_map_id,
                "x": 0.5,
                "y": 0.5,
                "confirm_move": confirm_move,
            }

            def handled(result: dict[str, Any]) -> None:
                if result.get("requires_confirmation"):
                    if messagebox.askyesno(
                        "Move character?",
                        (
                            f"{result.get('person_name') or character['name']} is currently on "
                            f"{result.get('current_map_name') or 'another map'}.\n\n"
                            "Move them to this map?"
                        ),
                        parent=dialog,
                    ):
                        place(True)
                    return
                dialog.destroy()
                if result.get("already_on_map"):
                    self.set_notice(f"{character['name']} is already on this map")
                else:
                    self.set_notice(f"{character['name']} added to map")
                self.refresh(silent=True)

            self._background(
                lambda: self.client.request("POST", "/api/admin/board/place-character", payload),
                handled,
            )

        query.trace_add("write", fill)
        results.bind("<Double-Button-1>", lambda _event: place())
        results.bind("<Return>", lambda _event: place())
        controls = ttk.Frame(body)
        controls.pack(fill="x", pady=(8, 0))
        ttk.Button(controls, text="Cancel", style="Quiet.TButton", command=dialog.destroy).pack(side="right")
        ttk.Button(controls, text="Add to Map", command=place).pack(side="right", padx=(0, 6))
        fill()
        search.focus_set()

    def quick_create_character_for_map(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Quick New Character")
        dialog.transient(self)
        dialog.grab_set()
        dialog.geometry("520x330")
        dialog.resizable(False, False)
        apply_window_icon(dialog, GAME_BOARD_ICON)
        body = ttk.Frame(dialog, padding=16)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Quick New Character", style="Title.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(body, text="Name", style="Card.TLabel").grid(row=1, column=0, sticky="w", pady=(14, 4))
        name_value = tk.StringVar()
        name_entry = ttk.Entry(body, textvariable=name_value)
        name_entry.grid(row=1, column=1, sticky="ew", pady=(14, 4))
        ttk.Label(body, text="Rough age", style="Card.TLabel").grid(row=2, column=0, sticky="w", pady=4)
        age_value = tk.StringVar(value="17")
        age_entry = ttk.Spinbox(body, from_=0, to=1000, textvariable=age_value, width=10)
        age_entry.grid(row=2, column=1, sticky="w", pady=4)
        ttk.Label(body, text="Development strategy", style="Card.TLabel").grid(row=3, column=0, sticky="w", pady=4)
        strategy_value = tk.StringVar(value="Random")
        strategies = (
            "Random", "One skill", "Two skill", "Three skills", "Ability-focus",
            "Material Crafting", "Ingredient Crafting", "Spell-crafting", "Social", "Scattershot",
        )
        strategy = ttk.Combobox(body, textvariable=strategy_value, values=strategies, state="readonly")
        strategy.grid(row=3, column=1, sticky="ew", pady=4)
        player_value = tk.BooleanVar(value=False)
        ttk.Checkbutton(body, text="Player character", variable=player_value).grid(row=4, column=1, sticky="w", pady=(6, 0))
        note = ttk.Label(
            body,
            text="Birth year and completed development years are calculated from the current Game World Date.",
            style="Status.TLabel",
            wraplength=450,
        )
        note.grid(row=5, column=0, columnspan=2, sticky="w", pady=(12, 0))
        body.columnconfigure(1, weight=1)

        def create() -> None:
            try:
                age = int(age_value.get())
            except ValueError:
                messagebox.showwarning("Quick character", "Enter a whole-number age.", parent=dialog)
                return
            payload = {
                "session_id": self.selected_session_id,
                "map_id": self.selected_board_map_id,
                "name": name_value.get().strip(),
                "age": age,
                "development_strategy": strategy_value.get(),
                "player_character": player_value.get(),
            }
            if not payload["name"]:
                messagebox.showwarning("Quick character", "Enter a character name.", parent=dialog)
                return

            def created(result: dict[str, Any]) -> None:
                character = result.get("character", {})
                dialog.destroy()
                self.set_notice(
                    f"Created {character.get('name', 'character')} â€” born {character.get('birth_year')}"
                )
                self.refresh(silent=True)

            self._background(
                lambda: self.client.request("POST", "/api/admin/board/quick-character", payload, timeout=60),
                created,
            )

        controls = ttk.Frame(body)
        controls.grid(row=6, column=0, columnspan=2, sticky="e", pady=(18, 0))
        ttk.Button(controls, text="Cancel", style="Quiet.TButton", command=dialog.destroy).pack(side="right")
        ttk.Button(controls, text="Create and Add", command=create).pack(side="right", padx=(0, 6))
        name_entry.focus_set()

    def open_board_groups(self) -> None:
        self.show_board_tools_panel("groups")

    def show_board_tools_panel(self, key: str) -> None:
        self.active_headmaster_tool = key
        labels = {
            "groups": "Characters",
            "creatures": "Creatures",
            "obfuscation-tools": "Obfuscation",
            "token-tools": "Tokens & Zoom",
            "secrets": "Secrets",
        }
        if hasattr(self, "headmaster_tool_title"):
            self.headmaster_tool_title.set(labels.get(key, "Headmaster Tools"))
        for tool_key, button in self.headmaster_tool_buttons.items():
            active = tool_key == key
            button.configure(
                background=self.EDGE if active else self.ACCENT,
                foreground=self.INK if active else "#fff8e7",
            )
        self._open_headmaster_tools_drawer()
        for panel_key, panel in self.board_tools_panels.items():
            if panel_key == key:
                if not panel.winfo_manager():
                    large = key in {"groups", "creatures", "secrets"}
                    panel.pack(
                        fill="both" if large else "x",
                        expand=large,
                        pady=(0, 5),
                    )
                panel.tkraise()
            elif panel.winfo_manager():
                panel.pack_forget()
        selected = self.board_tools_panels.get(key)
        if selected is not None:
            selected.focus_set()

    def _board_tab_changed(self, _event: tk.Event | None = None) -> None:
        selected = self.board_notebook.select()
        for map_id, canvas in self.board_canvases.items():
            if str(canvas.master) == str(selected):
                self.selected_board_map_id = map_id
                break
        self.cancel_board_obscuration()
        self._sync_board_presentation_controls()
        self._render_board_actor_list()
        self._render_board_creature_list()
        self._refresh_board_secret_list()
        self._save_board_workspace()

    def _current_board_map(self) -> dict[str, Any] | None:
        return next(
            (item for item in self.board_snapshot.get("maps", []) if item.get("record_id") == self.selected_board_map_id),
            None,
        )

    def _render_board(self, snapshot: dict[str, Any]) -> None:
        self.board_snapshot = snapshot or {}
        world_revision_id = str(self.board_snapshot.get("world_revision_id", "") or "")
        if world_revision_id and world_revision_id != self.board_world_revision_id:
            self.board_world_revision_id = world_revision_id
            self._board_map_sources.clear()
            self.board_map_images.clear()
        all_maps = list(self.board_snapshot.get("maps", []))
        valid_ids = {str(item.get("record_id")) for item in all_maps}
        campaign_id = str(self.board_snapshot.get("campaign_id", "") or "")
        if campaign_id and campaign_id != self.board_workspace_campaign_id:
            self.board_workspace_campaign_id = campaign_id
            self.board_view_states.clear()
            self.board_open_map_ids = [
                str(map_id) for map_id in self.board_snapshot.get("loaded_map_ids", [])
                if str(map_id) in valid_ids
            ]
            active_map_id = str(self.board_snapshot.get("active_map_id", "") or "")
            self.selected_board_map_id = (
                active_map_id
                if active_map_id in self.board_open_map_ids
                else (self.board_open_map_ids[0] if self.board_open_map_ids else "")
            )
        self.board_open_map_ids = [map_id for map_id in self.board_open_map_ids if map_id in valid_ids]
        maps_by_id = {str(item.get("record_id")): item for item in all_maps}
        maps = [maps_by_id[map_id] for map_id in self.board_open_map_ids if map_id in maps_by_id]
        map_ids = tuple(str(item.get("record_id")) for item in maps)
        if map_ids != self.board_map_ids:
            current = self.selected_board_map_id
            for tab in self.board_notebook.tabs():
                self.board_notebook.forget(tab)
            self.board_canvases.clear()
            self.board_map_ids = map_ids
            for record in maps:
                map_id = str(record.get("record_id"))
                frame = ttk.Frame(self.board_notebook)
                canvas = tk.Canvas(frame, background="#241d16", highlightthickness=0)
                canvas.pack(fill="both", expand=True)
                reveal_toggle = tk.Checkbutton(
                    frame,
                    text="Reveal",
                    variable=self.board_reveal_value,
                    command=self.board_presentation_changed,
                    background="#e4c98f",
                    activebackground=self.PAPER,
                    foreground=self.INK,
                    activeforeground=self.INK,
                    selectcolor="#fff8e6",
                    relief="solid",
                    borderwidth=1,
                    font=("Segoe UI", 8, "bold"),
                    padx=4,
                    pady=1,
                )
                reveal_toggle.place(x=6, y=4)
                reveal_toggle.lift()
                zoom_status = tk.Label(
                    frame,
                    textvariable=self.board_zoom_status_value,
                    background="#241d16",
                    foreground="#fff8e7",
                    font=("Consolas", 9, "bold"),
                    padx=5,
                    pady=2,
                )
                zoom_status.place(relx=1.0, x=-6, y=4, anchor="ne")
                zoom_status.lift()
                canvas.bind("<Configure>", lambda _event, selected=map_id: self._board_canvas_configured(selected))
                canvas.bind("<ButtonPress-1>", lambda event, selected=map_id: self._board_pointer_start(event, selected))
                canvas.bind("<B1-Motion>", lambda event, selected=map_id: self._board_drag_move(event, selected))
                canvas.bind("<ButtonRelease-1>", lambda event, selected=map_id: self._board_drag_end(event, selected))
                canvas.bind("<Double-Button-1>", lambda event, selected=map_id: self.complete_board_obscuration(event, selected))
                canvas.bind("<Button-3>", lambda event, selected=map_id: self._board_piece_menu(event, selected))
                canvas.bind("<Motion>", lambda event, selected=map_id: self.board_obscure_motion(event, selected))
                canvas.bind("<Leave>", lambda event, selected=map_id: self.board_canvas_leave(event, selected))
                canvas.bind("<Button-2>", lambda event, selected=map_id: self.board_pan_press(event, selected))
                self.board_notebook.add(frame, text=f"{str(record.get('name') or 'Map')}   ×")
                self.board_canvases[map_id] = canvas
            self.selected_board_map_id = current if current in map_ids else (map_ids[0] if map_ids else "")
            if self.selected_board_map_id:
                index = map_ids.index(self.selected_board_map_id)
                self.board_notebook.select(index)
        if maps:
            self.board_empty.pack_forget()
            if not self.board_notebook.winfo_ismapped():
                self.board_notebook.pack(side="left", fill="both", expand=True)
        else:
            self.board_notebook.pack_forget()
            self.board_empty.pack(side="left", fill="both", expand=True)
        name_counts: dict[str, int] = {}
        for item in all_maps:
            name = str(item.get("name") or "Map")
            name_counts[name] = name_counts.get(name, 0) + 1
        self.board_map_label_to_id = {}
        for item in all_maps:
            name = str(item.get("name") or "Map")
            label = name if name_counts[name] == 1 else f"{name} [{str(item.get('record_id'))[:8]}]"
            self.board_map_label_to_id[label] = str(item.get("record_id"))
        map_labels = list(self.board_map_label_to_id)
        if self.board_transfer_map is not None and self.board_transfer_map.winfo_exists():
            self.board_transfer_map.configure(values=map_labels)
        self._sync_board_presentation_controls()
        for map_id in map_ids:
            self._draw_board_map(map_id)
        self._render_board_actor_list()
        self._render_board_creature_list()
        self._refresh_board_secret_list()

    def _board_tab_click(self, event: tk.Event) -> str | None:
        """Close a map when the × area at the right edge of its tab is clicked."""

        try:
            index = self.board_notebook.index(f"@{event.x},{event.y}")
            element = str(self.board_notebook.identify(event.x, event.y) or "")
        except tk.TclError:
            return None
        if index >= len(self.board_map_ids):
            return None
        tab_right = event.x
        while tab_right < self.board_notebook.winfo_width() - 1:
            try:
                if self.board_notebook.index(f"@{tab_right + 1},{event.y}") != index:
                    break
            except tk.TclError:
                break
            tab_right += 1
        if "label" not in element or event.x < tab_right - 22:
            return None
        self.selected_board_map_id = self.board_map_ids[index]
        self.remove_current_board_map()
        return "break"

    def _board_presentation_draft(self, map_id: str | None = None) -> dict[str, Any] | None:
        map_id = map_id or self.selected_board_map_id
        record = next(
            (item for item in self.board_snapshot.get("maps", []) if str(item.get("record_id")) == map_id),
            None,
        )
        if record is None:
            return None
        draft = self.board_map_drafts.get(map_id)
        if draft is None or not draft.get("dirty"):
            draft = {
                "published": bool(record.get("players_published", False)),
                "obscurations": deepcopy(record.get("obscurations", []) or []),
                "preview_opacity": float(record.get("obscuration_preview_opacity", 0.35)),
                "preview_color": str(record.get("obscuration_preview_color", "#ff0000") or "#ff0000"),
                "dirty": False,
            }
            self.board_map_drafts[map_id] = draft
        return draft

    def _sync_board_presentation_controls(self) -> None:
        draft = self._board_presentation_draft()
        if draft is None:
            self.board_reveal_value.set(False)
            self.board_obscure_opacity.set("35")
            self.board_obscure_color = "#ff0000"
            if hasattr(self, "board_obscure_color_button"):
                self.board_obscure_color_button.configure(
                    background=self.board_obscure_color,
                    activebackground=self.board_obscure_color,
                )
            if hasattr(self, "board_default_token_value"):
                self.board_default_token_value.set("100")
                self.board_default_zoom_value.set("1.00")
                self.board_default_plaque_value.set("10")
                self.board_default_position_value.set("0.500, 0.500")
            self.board_draft_status.configure(text="No map open", foreground=self.MUTED)
            self.board_confirm_button.configure(text="Send", state="disabled")
            self._refresh_board_obscuration_list()
            self._refresh_board_zoom_override_list()
            return
        self.board_reveal_value.set(bool(draft["published"]))
        self.board_obscure_opacity.set(str(round(float(draft["preview_opacity"]) * 100)))
        self.board_obscure_color = str(draft["preview_color"])
        if hasattr(self, "board_obscure_color_button"):
            self.board_obscure_color_button.configure(
                background=self.board_obscure_color,
                activebackground=self.board_obscure_color,
            )
        record = self._current_board_map() or {}
        token_scale = float(record.get("token_scale", 0.0055))
        profile = record.get("zoom_profile") if isinstance(record.get("zoom_profile"), dict) else {}
        if hasattr(self, "board_default_token_value"):
            self.board_default_token_value.set(f"{token_scale / 0.0055 * 100:.0f}")
            self.board_default_zoom_value.set(f"{float(profile.get('default_zoom', 1.0)):.2f}")
            self.board_default_plaque_value.set(str(int(profile.get("default_nameplate_size", 10))))
            self.board_default_position_value.set(
                f"{float(profile.get('default_center_x', 0.5)):.3f}, {float(profile.get('default_center_y', 0.5)):.3f}"
            )
        if draft.get("dirty"):
            self.board_draft_status.configure(
                text="Pending",
                foreground=self.RED,
            )
            self.board_confirm_button.configure(text="Send", state="normal")
        elif time.monotonic() < self.board_confirmation_message_until:
            self.board_draft_status.configure(
                text="Sent ✓",
                foreground=self.GREEN,
            )
            self.board_confirm_button.configure(text="Send", state="disabled")
        else:
            self.board_draft_status.configure(
                text="Synced" if draft["published"] else "Hidden",
                foreground=self.GREEN,
            )
            self.board_confirm_button.configure(text="Send", state="disabled")
        self._refresh_board_obscuration_list()
        self._refresh_board_zoom_override_list()

    def _refresh_board_obscuration_list(self) -> None:
        if not hasattr(self, "board_obscuration_list"):
            return
        draft = self._board_presentation_draft()
        shapes = list((draft or {}).get("obscurations", []))
        self.board_obscuration_list.delete(0, "end")
        self.board_obscuration_list_ids = []
        selected_index = None
        for index, shape in enumerate(shapes, start=1):
            shape_id = str(shape.get("record_id") or "")
            self.board_obscuration_list_ids.append(shape_id)
            node_count = len(shape.get("points", []))
            name = str(shape.get("name") or f"Obfuscation {index}")
            self.board_obscuration_list.insert(
                "end", f"{name}  —  {node_count} nodes"
            )
            if shape_id == self.board_selected_obscuration_id:
                selected_index = index - 1
        if selected_index is not None:
            self.board_obscuration_list.selection_set(selected_index)
            self.board_obscuration_list.activate(selected_index)

    def select_board_obscuration_from_list(self, _event: tk.Event | None = None) -> None:
        selection = self.board_obscuration_list.curselection()
        if not selection or selection[0] >= len(self.board_obscuration_list_ids):
            return
        self.board_obscure_draft_points = []
        self.board_obscure_drawing = False
        self.board_obscure_mode = True
        self.board_selected_obscuration_id = self.board_obscuration_list_ids[selection[0]]
        self.board_selected_obscuration_node = None
        self.board_obscure_button.configure(text="✎")
        canvas = self.board_canvases.get(self.selected_board_map_id)
        if canvas is not None and canvas.winfo_exists():
            canvas.configure(cursor="arrow")
            self._draw_board_map(self.selected_board_map_id)

    def rename_board_obscuration(self, _event: tk.Event | None = None) -> None:
        self.select_board_obscuration_from_list()
        draft = self._board_presentation_draft()
        selected = next(
            (item for item in (draft or {}).get("obscurations", []) if str(item.get("record_id")) == self.board_selected_obscuration_id),
            None,
        )
        if selected is None:
            return
        name = simpledialog.askstring(
            "Name obfuscation", "Area name",
            initialvalue=str(selected.get("name") or ""), parent=self,
        )
        if name is None:
            return
        selected["name"] = name.strip() or "Obfuscation"
        selected["last_updated"] = datetime.utcnow().isoformat() + "Z"
        self._board_mark_presentation_dirty()
        self._refresh_board_obscuration_list()

    def board_presentation_changed(self, _event: tk.Event | None = None) -> None:
        draft = self._board_presentation_draft()
        if draft is None:
            return
        try:
            opacity = max(5, min(100, int(float(self.board_obscure_opacity.get()))))
        except ValueError:
            opacity = 35
        self.board_obscure_opacity.set(str(opacity))
        draft["published"] = bool(self.board_reveal_value.get())
        draft["preview_opacity"] = opacity / 100.0
        draft["preview_color"] = self.board_obscure_color
        draft["dirty"] = True
        self.board_confirmation_message_until = 0.0
        self.board_draft_status.configure(
            text="Pending",
            foreground=self.RED,
        )
        self.board_confirm_button.configure(text="Send", state="normal")
        if self.selected_board_map_id:
            self._draw_board_map(self.selected_board_map_id)

    def adjust_current_map_token_scale(self, direction: int) -> None:
        record = self._current_board_map()
        map_id = self.selected_board_map_id
        if record is None or not map_id:
            return
        current = float(record.get("token_scale", 0.0055))
        # Token sizing is perceptual. A 15% step is immediately visible at
        # any zoom and remains proportional whether tokens are tiny or large.
        value = max(0.002, min(0.03, round(current * (1.15 if direction > 0 else 1 / 1.15), 6)))
        if value == current:
            return
        record["token_scale"] = value
        percent = round(value / 0.0055 * 100)
        self.board_token_size_label.configure(text=f"{percent:d}%")
        if hasattr(self, "board_default_token_value"):
            self.board_default_token_value.set(str(percent))
        if self._board_token_preview_after_id is not None:
            self.after_cancel(self._board_token_preview_after_id)
            self._board_token_preview_after_id = None
        self._draw_board_map(map_id)
        self._background(
            lambda: self.client.request(
                "PUT", f"/api/admin/board/maps/{map_id}/settings",
                {"session_id": self.selected_session_id, "token_scale": value}
            ),
            lambda _result: self.refresh(silent=True),
        )

    def _refresh_board_zoom_override_list(self) -> None:
        if not hasattr(self, "board_zoom_override_rows"):
            return
        record = self._current_board_map() or {}
        profile = record.get("zoom_profile") if isinstance(record.get("zoom_profile"), dict) else {}
        tiers = profile.get("tiers") if isinstance(profile.get("tiers"), dict) else {}
        self.board_zoom_override_ids = sorted((int(value) for value in tiers), key=int)
        self.board_zoom_override_vars = {}
        for child in self.board_zoom_override_rows.winfo_children():
            child.destroy()
        for row, clicks in enumerate(self.board_zoom_override_ids):
            item = tiers.get(str(clicks), {})
            click_value = tk.StringVar(value=str(clicks))
            token_value = tk.StringVar(value=str(int(item.get("token_size", 0))))
            plaque_value = tk.StringVar(value=str(int(item.get("nameplate_size", 10))))
            values = (click_value, token_value, plaque_value)
            self.board_zoom_override_vars[clicks] = values
            for column, (variable, width) in enumerate(((click_value, 5), (token_value, 6), (plaque_value, 6))):
                entry = ttk.Entry(self.board_zoom_override_rows, textvariable=variable, width=width)
                entry.grid(row=row, column=column, sticky="ew", padx=(0, 3), pady=1)
                entry.bind(
                    "<FocusOut>",
                    lambda _event, original=clicks, row_values=values:
                        self.save_board_zoom_override_row(original, row_values),
                )
                entry.bind(
                    "<Return>",
                    lambda _event, original=clicks, row_values=values:
                        self.save_board_zoom_override_row(original, row_values),
                )
            delete_button = ttk.Button(
                self.board_zoom_override_rows,
                text="×",
                width=3,
                style="Quiet.TButton",
                command=lambda selected=clicks: self.delete_board_zoom_override(selected),
            )
            delete_button.grid(row=row, column=3, pady=1)
            self._attach_tooltip(delete_button, f"Delete the {clicks}-click override")
        for column in range(3):
            self.board_zoom_override_rows.columnconfigure(column, weight=1)

    def preview_board_token_percent(self, _event: tk.Event | None = None) -> None:
        record = self._current_board_map()
        map_id = self.selected_board_map_id
        if record is None or not map_id:
            return
        try:
            token_scale = 0.0055 * float(self.board_default_token_value.get()) / 100.0
        except ValueError:
            return
        if not 0.002 <= token_scale <= 0.03:
            return
        record["token_scale"] = token_scale
        self._draw_board_map(map_id)
        if self._board_token_preview_after_id is not None:
            self.after_cancel(self._board_token_preview_after_id)
        self._board_token_preview_after_id = self.after(450, self.save_board_zoom_profile)

    def preview_board_default_plaque_size(self, _event: tk.Event | None = None) -> None:
        record = self._current_board_map()
        map_id = self.selected_board_map_id
        if record is None or not map_id:
            return
        try:
            plaque_size = int(self.board_default_plaque_value.get())
        except ValueError:
            return
        if not 6 <= plaque_size <= 32:
            return
        profile = record.setdefault("zoom_profile", {})
        profile["default_nameplate_size"] = plaque_size
        self._draw_board_map(map_id)
        if self._board_token_preview_after_id is not None:
            self.after_cancel(self._board_token_preview_after_id)
        self._board_token_preview_after_id = self.after(450, self.save_board_zoom_profile)

    def save_board_zoom_override_row(
        self,
        original_clicks: int,
        values: tuple[tk.StringVar, tk.StringVar, tk.StringVar],
    ) -> None:
        record = self._current_board_map()
        if record is None:
            return
        try:
            clicks, token_size, plaque_size = (int(value.get()) for value in values)
            if not 0 <= clicks <= 250 or not 0 <= token_size <= 240 or not 6 <= plaque_size <= 32:
                raise ValueError
        except ValueError:
            self.bell()
            self._refresh_board_zoom_override_list()
            return
        profile = record.setdefault("zoom_profile", {})
        tiers = profile.setdefault("tiers", {})
        if clicks != original_clicks:
            tiers.pop(str(original_clicks), None)
        tiers[str(clicks)] = {"token_size": token_size, "nameplate_size": plaque_size}
        profile["tiers"] = dict(sorted(tiers.items(), key=lambda item: int(item[0])))
        self._draw_board_map(self.selected_board_map_id)
        self.save_board_zoom_profile()

    def use_current_board_camera_as_default(self) -> None:
        state = self.board_view_states.get(self.selected_board_map_id)
        if state is None:
            messagebox.showinfo("Zoom controls", "Open a map first.", parent=self)
            return
        self._board_update_camera_coordinates(self.selected_board_map_id)
        self.board_default_zoom_value.set(f"{float(state.get('zoom', 1.0)):.2f}")
        self.board_default_position_value.set(
            f"{float(state.get('center_x', 0.5)):.3f}, {float(state.get('center_y', 0.5)):.3f}"
        )
        self.save_board_zoom_profile()

    def use_current_board_zoom_as_default(self) -> None:
        state = self.board_view_states.get(self.selected_board_map_id)
        if state is None:
            return
        self._board_update_camera_coordinates(self.selected_board_map_id)
        self.board_default_zoom_value.set(f"{float(state.get('zoom', 1.0)):.2f}")
        self.save_board_zoom_profile()

    def use_current_board_position_as_default(self) -> None:
        state = self.board_view_states.get(self.selected_board_map_id)
        if state is None:
            return
        self._board_update_camera_coordinates(self.selected_board_map_id)
        self.board_default_position_value.set(
            f"{float(state.get('center_x', 0.5)):.3f}, {float(state.get('center_y', 0.5)):.3f}"
        )
        self.save_board_zoom_profile()

    def choose_board_obscuration_preview_color(self) -> None:
        selected = colorchooser.askcolor(
            color=self.board_obscure_color,
            title="Headmaster obfuscation color",
            parent=self,
        )[1]
        if selected:
            self.board_obscure_color = selected.lower()
            self.board_obscure_color_button.configure(
                background=self.board_obscure_color,
                activebackground=self.board_obscure_color,
            )
            self.apply_board_obscuration_preview()

    def apply_board_obscuration_preview(self, _event: tk.Event | None = None) -> None:
        draft = self._board_presentation_draft()
        map_id = self.selected_board_map_id
        if draft is None or not map_id:
            return
        try:
            opacity = max(5, min(100, int(float(self.board_obscure_opacity.get()))))
        except ValueError:
            opacity = 35
        self.board_obscure_opacity.set(str(opacity))
        draft["preview_opacity"] = opacity / 100.0
        draft["preview_color"] = self.board_obscure_color
        self._draw_board_map(map_id)
        self._background(
            lambda: self.client.request(
                "PUT", f"/api/admin/board/maps/{map_id}/settings",
                {
                    "session_id": self.selected_session_id,
                    "preview_opacity": opacity / 100.0,
                    "preview_color": self.board_obscure_color,
                },
            ),
            lambda _result: None,
        )

    def _edit_board_zoom_override_dialog(self, clicks: int | None = None) -> None:
        record = self._current_board_map()
        if record is None:
            messagebox.showinfo("Zoom controls", "Open a map first.", parent=self)
            return
        profile = record.setdefault("zoom_profile", {})
        tiers = profile.setdefault("tiers", {})
        saved = tiers.get(str(clicks), {}) if clicks is not None else {}
        dialog = tk.Toplevel(self)
        dialog.title("Zoom override")
        dialog.transient(self)
        dialog.resizable(False, False)
        dialog.configure(background=self.PAPER)
        apply_window_icon(dialog, GAME_BOARD_ICON)
        body = ttk.Frame(dialog, style="Card.TFrame", padding=10)
        body.pack(fill="both", expand=True, padx=8, pady=8)
        click_value = tk.StringVar(value="" if clicks is None else str(clicks))
        token_value = tk.StringVar(value=str(int(saved.get("token_size", 0))))
        plaque_value = tk.StringVar(value=str(int(saved.get("nameplate_size", 10))))
        for row, (label, variable) in enumerate((
            ("Zoom clicks", click_value), ("Token px", token_value), ("Plaque text px", plaque_value),
        )):
            ttk.Label(body, text=label, style="Card.TLabel").grid(row=row, column=0, sticky="w", pady=2)
            ttk.Entry(body, textvariable=variable, width=10).grid(row=row, column=1, padx=(8, 0), pady=2)

        def save() -> None:
            try:
                new_clicks = int(click_value.get())
                token_size = int(token_value.get())
                plaque_size = int(plaque_value.get())
                if not 0 <= new_clicks <= 250 or not 0 <= token_size <= 240 or not 6 <= plaque_size <= 32:
                    raise ValueError
            except ValueError:
                messagebox.showerror(
                    "Zoom override",
                    "Use whole numbers: clicks 0–250, token 0–240 px, plaque 6–32 px.",
                    parent=dialog,
                )
                return
            if clicks is not None and new_clicks != clicks:
                tiers.pop(str(clicks), None)
            tiers[str(new_clicks)] = {"token_size": token_size, "nameplate_size": plaque_size}
            profile["tiers"] = dict(sorted(tiers.items(), key=lambda item: int(item[0])))
            self._refresh_board_zoom_override_list()
            self._draw_board_map(self.selected_board_map_id)
            dialog.destroy()
            self.save_board_zoom_profile()

        actions = ttk.Frame(body, style="Card.TFrame")
        actions.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Button(actions, text="Save", command=save).pack(side="left", fill="x", expand=True)
        ttk.Button(actions, text="Cancel", style="Quiet.TButton", command=dialog.destroy).pack(side="left", fill="x", expand=True, padx=(4, 0))

    def add_board_zoom_override(self) -> None:
        self._edit_board_zoom_override_dialog()

    def edit_board_zoom_override(self) -> None:
        if self.board_zoom_override_ids:
            self._edit_board_zoom_override_dialog(self.board_zoom_override_ids[0])

    def delete_board_zoom_override(self, clicks: int | None = None) -> None:
        if clicks is None:
            return
        record = self._current_board_map() or {}
        profile = record.get("zoom_profile") if isinstance(record.get("zoom_profile"), dict) else {}
        tiers = profile.get("tiers") if isinstance(profile.get("tiers"), dict) else {}
        tiers.pop(str(clicks), None)
        self._refresh_board_zoom_override_list()
        self._draw_board_map(self.selected_board_map_id)
        self.save_board_zoom_profile()

    def save_board_zoom_profile(self) -> None:
        record = self._current_board_map()
        map_id = self.selected_board_map_id
        if record is None or not map_id:
            messagebox.showinfo("Zoom controls", "Open a map first.", parent=self)
            return
        try:
            token_percent = float(self.board_default_token_value.get())
            token_scale = 0.0055 * token_percent / 100.0
            zoom = float(self.board_default_zoom_value.get())
            plaque_size = int(self.board_default_plaque_value.get())
            position = [float(value.strip()) for value in self.board_default_position_value.get().split(",")]
            if (
                len(position) != 2
                or not 0.002 <= token_scale <= 0.03
                or not 1.0 <= zoom <= 32.0
                or not 6 <= plaque_size <= 32
            ):
                raise ValueError
            center_x, center_y = position
            if not 0.0 <= center_x <= 1.0 or not 0.0 <= center_y <= 1.0:
                raise ValueError
        except ValueError:
            messagebox.showerror(
                "Zoom controls",
                "Use token size 36–545%, plaque size 6–32, zoom 1–32, and position as x, y values from 0 to 1.",
                parent=self,
            )
            return
        profile = record.get("zoom_profile") if isinstance(record.get("zoom_profile"), dict) else {}
        saved_profile = {
            "default_zoom": zoom,
            "default_center_x": center_x,
            "default_center_y": center_y,
            "default_nameplate_size": plaque_size,
            "tiers": deepcopy(profile.get("tiers", {}) or {}),
        }
        record["token_scale"] = token_scale
        record["zoom_profile"] = saved_profile
        self._draw_board_map(map_id)
        self._background(
            lambda: self.client.request(
                "PUT", f"/api/admin/board/maps/{map_id}/settings",
                {"session_id": self.selected_session_id, "token_scale": token_scale, "zoom_profile": saved_profile},
            ),
            lambda _result: self.refresh(silent=True),
        )

    def open_board_zoom_controls(self) -> None:
        self.show_board_tools_panel("token-tools")
        return
        window = tk.Toplevel(self)
        window.title("Map Zoom Controls")
        window.transient(self)
        window.resizable(False, False)
        window.configure(background=self.PAPER)
        apply_window_icon(window, GAME_BOARD_ICON)

        profile = record.get("zoom_profile") if isinstance(record.get("zoom_profile"), dict) else {}
        default_zoom = tk.StringVar(value=f"{float(profile.get('default_zoom', 1.0)):.2f}")
        header = ttk.Frame(window, style="Card.TFrame", padding=10)
        header.pack(fill="x", padx=10, pady=(10, 6))
        ttk.Label(header, text="Default zoom", style="Card.TLabel").pack(side="left")
        ttk.Spinbox(header, from_=1.0, to=32.0, increment=0.15, textvariable=default_zoom, width=7).pack(side="right")

        grid = ttk.Frame(window, style="Card.TFrame", padding=10)
        grid.pack(fill="both", expand=True, padx=10)
        ttk.Label(grid, text="Clicks", style="Card.TLabel", font=("Segoe UI", 8, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(grid, text="Token px", style="Card.TLabel", font=("Segoe UI", 8, "bold")).grid(row=0, column=1, padx=8)
        ttk.Label(grid, text="Plaque text px", style="Card.TLabel", font=("Segoe UI", 8, "bold")).grid(row=0, column=2, padx=8)
        tiers = profile.get("tiers", {}) if isinstance(profile.get("tiers"), dict) else {}
        values: dict[int, tuple[tk.StringVar, tk.StringVar]] = {}
        for row, clicks in enumerate(range(0, 22, 3), start=1):
            saved = tiers.get(str(clicks), {}) if isinstance(tiers.get(str(clicks)), dict) else {}
            token = tk.StringVar(value=str(int(saved.get("token_size", BOARD_TOKEN_SCREEN_SIZES[row - 1]))))
            plaque = tk.StringVar(value=str(int(saved.get("nameplate_size", BOARD_LABEL_FONT_SIZES[row - 1]))))
            values[clicks] = (token, plaque)
            ttk.Label(grid, text=str(clicks), style="Card.TLabel").grid(row=row, column=0, sticky="w", pady=2)
            ttk.Spinbox(grid, from_=0, to=240, textvariable=token, width=7).grid(row=row, column=1, padx=8, pady=2)
            ttk.Spinbox(grid, from_=6, to=32, textvariable=plaque, width=7).grid(row=row, column=2, padx=8, pady=2)

        actions = ttk.Frame(window)
        actions.pack(fill="x", padx=10, pady=10)

        def save() -> None:
            try:
                zoom = max(1.0, min(32.0, float(default_zoom.get())))
                saved_profile = {
                    "default_zoom": zoom,
                    "tiers": {
                        str(clicks): {
                            "token_size": max(0, min(240, int(token.get()))),
                            "nameplate_size": max(6, min(32, int(plaque.get()))),
                        }
                        for clicks, (token, plaque) in values.items()
                    },
                }
            except ValueError:
                messagebox.showerror("Zoom controls", "Use numbers for every zoom setting.", parent=window)
                return
            record["zoom_profile"] = saved_profile
            state = self.board_view_states.get(self.selected_board_map_id)
            if state is not None:
                state["zoom"] = zoom
                state["scale"] = float(state["fit_scale"]) * zoom
                self._board_clamp_view(self.selected_board_map_id)
                self._board_update_camera_coordinates(self.selected_board_map_id)
                self._queue_board_camera_save(self.selected_board_map_id)
            map_id = self.selected_board_map_id
            self._draw_board_map(map_id)
            self._background(
                lambda: self.client.request(
                    "PUT",
                    f"/api/admin/board/maps/{map_id}/settings",
                    {"session_id": self.selected_session_id, "zoom_profile": saved_profile},
                ),
                lambda _result: self.refresh(silent=True),
            )
            window.destroy()

        ttk.Button(actions, text="Cancel", style="Quiet.TButton", command=window.destroy).pack(side="right")
        ttk.Button(actions, text="Save profile", command=save).pack(side="right", padx=(0, 6))

    def start_setting_board_start_point(self) -> None:
        messagebox.showinfo(
            "Player arrival",
            "Choose a warp point in Mapper and mark it as the player arrival for this map.",
            parent=self,
        )
        return
        if not self.selected_board_map_id:
            messagebox.showinfo(
                "Player start point",
                "Add and select a map before setting its player start point.",
                parent=self,
            )
            return
        self.cancel_board_obscuration()
        self.board_obscure_mode = False
        self.board_start_point_mode = True
        self.board_start_point_button.configure(text="Click the mapâ€¦")
        self.board_draft_status.configure(
            text="Click once on the map to set the ideal player start point.",
            foreground=self.MUTED,
        )
        canvas = self.board_canvases.get(self.selected_board_map_id)
        if canvas is not None:
            canvas.configure(cursor="crosshair")
            canvas.focus_set()

    def set_board_start_point(self, event: tk.Event, map_id: str) -> None:
        if map_id != self.selected_board_map_id:
            return
        x, y = self._normalized_board_point(map_id, event.x, event.y, clamp=False)
        if not 0.0 <= x <= 1.0 or not 0.0 <= y <= 1.0:
            return
        self.board_start_point_mode = False
        self.board_start_point_button.configure(text="Mapper owns player arrivals")
        canvas = self.board_canvases.get(map_id)
        if canvas is not None:
            canvas.configure(cursor="arrow")
        record = self._current_board_map()
        if record is not None:
            record["start_point"] = {"x": x, "y": y}
        self._draw_board_map(map_id)
        self.board_draft_status.configure(text="Player start point saved.", foreground=self.GREEN)
        self._background(
            lambda: self.client.request(
                "PUT",
                f"/api/admin/board/maps/{map_id}/settings",
                {
                    "session_id": self.selected_session_id,
                    "start_point": {"x": x, "y": y},
                    "update_start_point": True,
                },
            ),
            lambda _result: self.refresh(silent=True),
        )

    def open_board_settings(self) -> None:
        if not self.selected_board_map_id:
            messagebox.showinfo(
                "Game Board Settings",
                "Add and select a map before changing its display settings.",
                parent=self,
            )
            return
        window = self.board_settings_window
        if window is not None and window.winfo_exists():
            window.deiconify()
            window.lift()
            return
        window = tk.Toplevel(self)
        self.board_settings_window = window
        window.title("Game Board Settings")
        window.resizable(False, False)
        window.configure(background=self.PAPER)
        window.protocol("WM_DELETE_WINDOW", window.destroy)
        apply_window_icon(window, GAME_BOARD_ICON)
        shell = ttk.Frame(window, style="Card.TFrame", padding=12)
        shell.pack(fill="both", expand=True)
        ttk.Label(shell, text="OBFUSCATION PREVIEW", style="Section.TLabel").pack(anchor="w")
        ttk.Label(
            shell,
            text="These settings affect only what the Headmaster sees while editing this map.",
            style="Card.TLabel",
            wraplength=300,
        ).pack(anchor="w", pady=(2, 10))
        ttk.Label(shell, text="Preview opacity (%)", style="Card.TLabel").pack(anchor="w")
        opacity = tk.StringVar(value=self.board_obscure_opacity.get())
        ttk.Spinbox(shell, from_=5, to=100, increment=5, textvariable=opacity, width=8).pack(
            anchor="w", pady=(2, 10)
        )
        color = [self.board_obscure_color]
        color_button = ttk.Button(shell, text=color[0].upper(), style="Quiet.TButton")

        def choose_color() -> None:
            selected = colorchooser.askcolor(
                color=color[0], title="Headmaster obfuscation color", parent=window
            )[1]
            if selected:
                color[0] = selected.lower()
                color_button.configure(text=color[0].upper())

        ttk.Label(shell, text="Preview color", style="Card.TLabel").pack(anchor="w")
        color_button.configure(command=choose_color)
        color_button.pack(fill="x", pady=(2, 12))

        def apply() -> None:
            try:
                value = max(5, min(100, int(float(opacity.get()))))
            except ValueError:
                messagebox.showerror(
                    "Game Board Settings", "Opacity must be a number from 5 to 100.", parent=window
                )
                return
            self.board_obscure_opacity.set(str(value))
            self.board_obscure_color = color[0]
            self.board_presentation_changed()
            window.destroy()

        ttk.Button(shell, text="Apply", style="Good.TButton", command=apply).pack(fill="x")
        window.update_idletasks()
        window.geometry(
            f"340x{max(260, window.winfo_reqheight())}+"
            f"{self.winfo_rootx() + 300}+{self.winfo_rooty() + 150}"
        )

    def confirm_board_presentation(self) -> None:
        map_id = self.selected_board_map_id
        draft = self._board_presentation_draft(map_id)
        if not map_id or draft is None:
            return
        if self.board_obscure_draft_points:
            messagebox.showinfo(
                "Finish obscuring shape",
                "Close or cancel the unfinished obscuring shape before confirming.",
                parent=self,
            )
            return
        payload = {
            "session_id": self.selected_session_id,
            "published": bool(draft["published"]),
            "obscurations": deepcopy(draft["obscurations"]),
            "preview_opacity": float(draft["preview_opacity"]),
            "preview_color": str(draft["preview_color"]),
        }

        def complete(_result: Any) -> None:
            draft["dirty"] = False
            self.board_confirmation_message_until = time.monotonic() + 5.0
            self.board_draft_status.configure(
                text="Sent ✓",
                foreground=self.GREEN,
            )
            self.board_confirm_button.configure(text="Send", state="disabled")
            self.refresh(silent=True)
            self.after(5100, self._sync_board_presentation_controls)

        def failed(error: Exception) -> None:
            draft["dirty"] = True
            self.board_draft_status.configure(
                text="Send failed",
                foreground=self.RED,
            )
            self.board_confirm_button.configure(text="Retry", state="normal")
            self._failed(error, False)

        self.board_draft_status.configure(text="Sending…", foreground=self.MUTED)
        self.board_confirm_button.configure(text="…", state="disabled")
        self._background(
            lambda: self.client.request(
                "PUT",
                f"/api/admin/board/maps/{map_id}/presentation",
                payload,
            ),
            complete,
            failure=failed,
        )

    def set_current_map_published(self, published: bool) -> None:
        self.board_reveal_value.set(bool(published))
        self.board_presentation_changed()

    def _draw_board_map(self, map_id: str) -> None:
        canvas = self.board_canvases.get(map_id)
        record = next((item for item in self.board_snapshot.get("maps", []) if item.get("record_id") == map_id), None)
        if canvas is None or record is None or not canvas.winfo_exists():
            return
        canvas.delete("all")
        self._board_canvas_actors = {
            key: value for key, value in self._board_canvas_actors.items()
            if key[0] != map_id
        }
        self._board_canvas_actor_parts = {
            key: value for key, value in self._board_canvas_actor_parts.items()
            if key[0] != map_id
        }
        width = max(2, canvas.winfo_width())
        height = max(2, canvas.winfo_height())
        state = self.board_view_states.get(map_id)
        if state is None:
            layout_width = max(100, width)
            layout_height = max(100, height)
            fit_scale = max(0.000001, min(
                (layout_width - 24) / MAP_CANVAS_WIDTH,
                (layout_height - 24) / MAP_CANVAS_HEIGHT,
            ))
            saved_camera = record.get("camera") if isinstance(record.get("camera"), dict) else {}
            zoom = max(1.0, min(32.0, float(saved_camera.get("zoom", 1.0))))
            center_x = max(0.0, min(1.0, float(saved_camera.get("center_x", 0.5))))
            center_y = max(0.0, min(1.0, float(saved_camera.get("center_y", 0.5))))
            scale = fit_scale * zoom
            state = {
                "fit_scale": fit_scale,
                "scale": scale,
                "origin_x": layout_width / 2 - center_x * MAP_CANVAS_WIDTH * scale,
                "origin_y": layout_height / 2 - center_y * MAP_CANVAS_HEIGHT * scale,
                "zoom": zoom,
                "center_x": center_x,
                "center_y": center_y,
                "modified": zoom > 1.000001 or abs(center_x - 0.5) > 0.000001 or abs(center_y - 0.5) > 0.000001,
            }
            self.board_view_states[map_id] = state
            if width >= 50 and height >= 50:
                self._board_clamp_view(map_id)
                self._board_update_camera_coordinates(map_id)
        draw_width = max(1.0, MAP_CANVAS_WIDTH * float(state["scale"]))
        draw_height = max(1.0, MAP_CANVAS_HEIGHT * float(state["scale"]))
        left = float(state["origin_x"])
        top = float(state["origin_y"])
        canvas.create_rectangle(left, top, left + draw_width, top + draw_height, fill="#241d16", outline="#9d7a4e")
        metadata = record.get("asset")
        if isinstance(metadata, dict) and metadata.get("asset_id"):
            try:
                source = self._board_map_sources.get(map_id)
                if source is None:
                    path = self.asset_store.resolve(str(metadata["asset_id"]), metadata)
                    with Image.open(path) as opened:
                        source = ImageOps.pad(
                            opened.convert("RGB"),
                            MAP_CANVAS_SIZE,
                            method=Image.Resampling.LANCZOS,
                            color="#241d16",
                        )
                    self._board_map_sources[map_id] = source
                visible_left = max(0.0, left)
                visible_top = max(0.0, top)
                visible_right = min(float(width), left + draw_width)
                visible_bottom = min(float(height), top + draw_height)
                if visible_right > visible_left and visible_bottom > visible_top:
                    source_left = max(0, math.floor((visible_left - left) / draw_width * source.width))
                    source_top = max(0, math.floor((visible_top - top) / draw_height * source.height))
                    source_right = min(source.width, math.ceil((visible_right - left) / draw_width * source.width))
                    source_bottom = min(source.height, math.ceil((visible_bottom - top) / draw_height * source.height))
                    visible = source.crop((source_left, source_top, source_right, source_bottom))
                    resized = visible.resize(
                        (max(1, round(visible_right - visible_left)), max(1, round(visible_bottom - visible_top))),
                        Image.Resampling.BILINEAR,
                    )
                    photo = ImageTk.PhotoImage(resized)
                    self.board_map_images[map_id] = photo
                    canvas.create_image(visible_left, visible_top, image=photo, anchor="nw")
            except (FileNotFoundError, OSError, ValueError):
                canvas.create_text(width / 2, height / 2, text="Map image unavailable", fill="#f8edcf", font=("Segoe UI", 14, "bold"))
        else:
            canvas.create_text(width / 2, height / 2, text="No map image imported", fill="#f8edcf", font=("Segoe UI", 14, "bold"))
        self.board_canvas_geometry[map_id] = (left, top, draw_width, draw_height)
        token_scale = max(0.002, min(0.03, float(record.get("token_scale", 0.0055))))
        zoom = max(1.0, float(state.get("zoom", 1.0)))
        zoom_clicks = max(0, round(math.log(zoom) / math.log(1.15)))
        zoom_tier = max(0, min(len(BOARD_TOKEN_SCREEN_SIZES) - 1, zoom_clicks // 3))
        profile = record.get("zoom_profile") if isinstance(record.get("zoom_profile"), dict) else {}
        profile_tiers = profile.get("tiers", {}) if isinstance(profile.get("tiers"), dict) else {}
        applicable_clicks = max(
            (int(value) for value in profile_tiers if int(value) <= zoom_clicks),
            default=None,
        )
        tier_override = profile_tiers.get(str(applicable_clicks), {}) if applicable_clicks is not None else {}
        if map_id == self.selected_board_map_id:
            self.board_zoom_status_value.set(f"Zoom {round(zoom * 100):d}% · {zoom_clicks} clicks")
        overview_mode = zoom_tier < 6
        size_ratio = max(0.35, min(5.5, token_scale / 0.0055))
        base_token_size = int(tier_override.get("token_size", BOARD_TOKEN_SCREEN_SIZES[zoom_tier]))
        token_diameter = max(8, round(base_token_size * size_ratio))
        portrait_diameter = token_diameter
        dot_diameter = max(7, round((BOARD_OVERVIEW_DOT_SIZES[zoom_tier] or 8) * size_ratio))
        label_font_size = int(tier_override.get(
            "nameplate_size",
            profile.get("default_nameplate_size", BOARD_LABEL_FONT_SIZES[zoom_tier]),
        ))
        for key in [key for key in self._board_portraits if key.startswith(f"{map_id}:")]:
            self._board_portraits.pop(key, None)

        def clamp_text_to_canvas(item_id: int, x_value: float, y_value: float) -> tuple[float, float]:
            """Keep the complete plaque text inside the visible map canvas."""

            bounds = canvas.bbox(item_id)
            if not bounds:
                return x_value, y_value
            dx = max(4.0 - bounds[0], min(0.0, width - 4.0 - bounds[2]))
            dy = max(4.0 - bounds[1], min(0.0, height - 4.0 - bounds[3]))
            if dx or dy:
                canvas.move(item_id, dx, dy)
            return x_value + dx, y_value + dy

        for actor_index, actor in enumerate(self.board_snapshot.get("actors", [])):
            if actor.get("map_id") != map_id:
                continue
            x = left + float(actor.get("x", 0.5)) * draw_width
            y = top + float(actor.get("y", 0.5)) * draw_height
            actor_id = str(actor.get("actor_id"))
            color = str(actor.get("faction_color") or "#808080")
            selected = actor_id == self.selected_board_actor_id
            is_player = bool(actor.get("is_player_character"))
            is_creature = actor.get("actor_type") == "creature"
            name = str(
                actor.get("internal_label") if is_creature else actor.get("name")
            ) or ("Character" if is_player else "Unknown")
            group_id = str(actor.get("group_id", "") or "")
            group_color = str(actor.get("group_color") or "#b0b0b0")
            # Ownership controls the plaque fill; a board group contributes
            # only its border color.  This keeps an unowned, ungrouped NPC
            # unmistakably grey while still making groups easy to scan.
            plaque_fill = "#d6ad52" if is_player else (group_color if is_creature else "#b0b0b0")
            plaque_outline = group_color if group_id else (self.INK if is_player else "#707070")
            actor_label_font_size = max(
                6,
                min(
                    48,
                    round(label_font_size * float(actor.get("nameplate_scale", 1.0) or 1.0)),
                ),
            )
            saved_label_offset = actor.get("label_offset") if isinstance(actor.get("label_offset"), dict) else {}
            label_dx = float(saved_label_offset.get("x", 0.0)) * draw_width
            label_dy = float(saved_label_offset.get("y", 0.0)) * draw_height
            actor_on_screen = 10 <= x <= width - 10 and 10 <= y <= height - 10
            if is_player and not actor_on_screen:
                marker_x = max(12.0, min(width - 12.0, x))
                marker_y = max(12.0, min(height - 12.0, y))
                angle = math.atan2(y - marker_y, x - marker_x)
                radius = dot_diameter / 2
                item = canvas.create_oval(
                    marker_x - radius, marker_y - radius,
                    marker_x + radius, marker_y + radius,
                    fill=plaque_fill, outline="#fff3cf" if selected else plaque_outline, width=2,
                )
                line = canvas.create_line(marker_x, marker_y, marker_x, marker_y, fill=self.INK, width=2)
                plaque_x = max(50.0, min(width - 50.0, marker_x - math.cos(angle) * 54 + label_dx))
                plaque_y = max(18.0, min(height - 18.0, marker_y - math.sin(angle) * 28 + label_dy))
                label = canvas.create_text(
                    plaque_x, plaque_y, text=name, fill="#000000",
                    font=("Segoe UI", actor_label_font_size, "bold"),
                )
                plaque_x, plaque_y = clamp_text_to_canvas(label, plaque_x, plaque_y)
                canvas.coords(line, marker_x, marker_y, plaque_x, plaque_y)
                label_box = canvas.bbox(label) or (plaque_x - 28, plaque_y - 8, plaque_x + 28, plaque_y + 8)
                label_bg = canvas.create_rectangle(
                    label_box[0] - 5, label_box[1] - 3,
                    label_box[2] + 5, label_box[3] + 3,
                    fill=plaque_fill, outline=plaque_outline, width=1,
                )
                canvas.tag_raise(line)
                canvas.tag_raise(item)
                canvas.tag_raise(label_bg)
                canvas.tag_raise(label)
                for actor_item in (item, line, label_bg, label):
                    self._board_canvas_actors[(map_id, actor_item)] = actor_id
                self._board_canvas_actor_parts[(map_id, label_bg)] = "label"
                self._board_canvas_actor_parts[(map_id, label)] = "label"
                continue
            if is_player and overview_mode:
                radius = dot_diameter / 2
                item = canvas.create_oval(
                    x - radius, y - radius, x + radius, y + radius,
                    fill=plaque_fill, outline="#fff3cf" if selected else plaque_outline, width=2,
                )
                direction = -1 if actor_index % 2 == 0 else 1
                label_y = y - 24 + label_dy
                label_x = x + direction * max(20, min(72, len(name) * 3)) + label_dx
                line = canvas.create_line(x, y, label_x, label_y, fill=self.INK, width=2)
                label = canvas.create_text(
                    label_x, label_y, text=name, fill="#000000",
                    font=("Segoe UI", actor_label_font_size, "bold"),
                )
                label_x, label_y = clamp_text_to_canvas(label, label_x, label_y)
                canvas.coords(line, x, y, label_x, label_y)
                label_box = canvas.bbox(label) or (label_x - 28, label_y - 8, label_x + 28, label_y + 8)
                label_bg = canvas.create_rectangle(
                    label_box[0] - 5, label_box[1] - 3,
                    label_box[2] + 5, label_box[3] + 3,
                    fill=plaque_fill, outline=plaque_outline, width=1,
                )
                canvas.tag_raise(line)
                canvas.tag_raise(item)
                canvas.tag_raise(label_bg)
                canvas.tag_raise(label)
                for actor_item in (item, line, label_bg, label):
                    self._board_canvas_actors[(map_id, actor_item)] = actor_id
                self._board_canvas_actor_parts[(map_id, label_bg)] = "label"
                self._board_canvas_actor_parts[(map_id, label)] = "label"
                continue
            if actor.get("display_mode") == "token" and actor.get("portrait_asset_id"):
                try:
                    portrait_path = self.asset_store.resolve(str(actor["portrait_asset_id"]))
                    with Image.open(portrait_path) as opened:
                        portrait = opened.convert("RGBA").resize((portrait_diameter, portrait_diameter), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(portrait)
                    self._board_portraits[f"{map_id}:{actor_id}:{token_diameter}"] = photo
                    item = canvas.create_image(x, y, image=photo)
                    if selected:
                        radius = token_diameter / 2 + 2
                        canvas.create_rectangle(
                            x - radius, y - radius, x + radius, y + radius,
                            outline="#d6ad52", width=2,
                        )
                except (FileNotFoundError, OSError, ValueError):
                    radius = dot_diameter / 2
                    item = canvas.create_oval(x - radius, y - radius, x + radius, y + radius, fill=color, outline="#d6ad52" if selected else self.INK, width=2)
            elif actor.get("display_mode") == "nameplate":
                # Legacy plaque-only records now retain a real spatial dot and
                # the same permanent dot-to-plaque leader as every other piece.
                radius = dot_diameter / 2
                item = canvas.create_oval(
                    x - radius, y - radius, x + radius, y + radius,
                    fill=plaque_fill, outline="#fff3cf" if selected else plaque_outline, width=2,
                )
            else:
                radius = dot_diameter / 2
                item = canvas.create_oval(x - radius, y - radius, x + radius, y + radius, fill=color, outline="#fff3cf" if selected else self.INK, width=2)
            self._board_canvas_actors[(map_id, item)] = actor_id
            label_offset = max(token_diameter, dot_diameter) / 2 + 10
            label_x, label_y = x + label_dx, y + label_offset + label_dy
            line = canvas.create_line(x, y, label_x, label_y, fill=self.INK, width=2)
            label = canvas.create_text(label_x, label_y, text=name, fill="#000000", font=("Segoe UI", actor_label_font_size, "bold"))
            label_x, label_y = clamp_text_to_canvas(label, label_x, label_y)
            if actor.get("display_mode") == "token" and actor.get("portrait_asset_id"):
                delta_x, delta_y = label_x - x, label_y - y
                distance = math.hypot(delta_x, delta_y) or 1.0
                edge = portrait_diameter / 2
                line_start_x = x + delta_x / distance * edge
                line_start_y = y + delta_y / distance * edge
            else:
                # Dot leaders originate at the centre of the circle.
                line_start_x, line_start_y = x, y
            canvas.coords(line, line_start_x, line_start_y, label_x, label_y)
            label_box = canvas.bbox(label) or (label_x - 20, label_y - 7, label_x + 20, label_y + 7)
            label_bg = canvas.create_rectangle(
                label_box[0] - 4, label_box[1] - 2,
                label_box[2] + 4, label_box[3] + 2,
                fill=plaque_fill, outline=plaque_outline, width=1,
            )
            canvas.tag_raise(line)
            canvas.tag_raise(label)
            self._board_canvas_actors[(map_id, line)] = actor_id
            self._board_canvas_actors[(map_id, label_bg)] = actor_id
            self._board_canvas_actors[(map_id, label)] = actor_id
            self._board_canvas_actor_parts[(map_id, label_bg)] = "label"
            self._board_canvas_actor_parts[(map_id, label)] = "label"

        draft = self._board_presentation_draft(map_id)
        obscurations = list((draft or {}).get("obscurations", []))
        if obscurations:
            overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            painter = ImageDraw.Draw(overlay, "RGBA")
            color = str((draft or {}).get("preview_color", "#ff0000"))
            try:
                red, green, blue = tuple(int(color[index:index + 2], 16) for index in (1, 3, 5))
            except (TypeError, ValueError):
                red, green, blue = (255, 0, 0)
            alpha = round(float((draft or {}).get("preview_opacity", 0.35)) * 255)
            for obscuration in obscurations:
                coordinates = [
                    (left + float(point["x"]) * draw_width, top + float(point["y"]) * draw_height)
                    for point in obscuration.get("points", [])
                ]
                if len(coordinates) >= 3:
                    painter.polygon(coordinates, fill=(red, green, blue, alpha))
            photo = ImageTk.PhotoImage(overlay)
            self._board_obscure_images[map_id] = photo
            canvas.create_image(0, 0, image=photo, anchor="nw", tags=("obscuration-overlay",))
            for (actor_map_id, actor_item), _actor_id in self._board_canvas_actors.items():
                if actor_map_id == map_id:
                    canvas.tag_raise(actor_item)
        if self.board_obscure_mode:
            for obscuration in obscurations:
                points = obscuration.get("points", [])
                coordinates = [coordinate for point in points for coordinate in (
                    left + float(point["x"]) * draw_width,
                    top + float(point["y"]) * draw_height,
                )]
                selected = str(obscuration.get("record_id")) == self.board_selected_obscuration_id
                if len(coordinates) >= 6:
                    canvas.create_polygon(
                        *coordinates,
                        fill="",
                        outline="#fff3cf" if selected else "#5b1717",
                        width=3 if selected else 1,
                        tags=("obscuration-shape",),
                    )
                if selected:
                    for index, point in enumerate(points):
                        x = left + float(point["x"]) * draw_width
                        y = top + float(point["y"]) * draw_height
                        radius = 6 if index == self.board_selected_obscuration_node else 4
                        canvas.create_oval(x - radius, y - radius, x + radius, y + radius, fill="#fff8e7", outline="#000000", width=2)
        if self.board_obscure_draft_points and map_id == self.selected_board_map_id:
            coordinates = [coordinate for point in self.board_obscure_draft_points for coordinate in (
                left + point["x"] * draw_width,
                top + point["y"] * draw_height,
            )]
            if len(coordinates) >= 4:
                canvas.create_line(*coordinates, fill="#000000", width=2, tags=("obscuration-draft",))
            for x, y in zip(coordinates[0::2], coordinates[1::2]):
                canvas.create_oval(x - 4, y - 4, x + 4, y + 4, fill="#fff8e7", outline="#000000", width=2)

    def _board_canvas_configured(self, map_id: str) -> None:
        canvas = self.board_canvases.get(map_id)
        if canvas is None:
            return
        state = self.board_view_states.get(map_id)
        if state is None or not bool(state.get("modified")):
            self._board_fit_map(map_id)
            return
        zoom = max(1.0, min(32.0, float(state.get("zoom", 1.0))))
        center_x = max(0.0, min(1.0, float(state.get("center_x", 0.5))))
        center_y = max(0.0, min(1.0, float(state.get("center_y", 0.5))))
        state["fit_scale"] = min(
            (max(100, canvas.winfo_width()) - 24) / MAP_CANVAS_WIDTH,
            (max(100, canvas.winfo_height()) - 24) / MAP_CANVAS_HEIGHT,
        )
        state["scale"] = float(state["fit_scale"]) * zoom
        state["origin_x"] = float(canvas.winfo_width()) / 2 - center_x * MAP_CANVAS_WIDTH * float(state["scale"])
        state["origin_y"] = float(canvas.winfo_height()) / 2 - center_y * MAP_CANVAS_HEIGHT * float(state["scale"])
        self._board_clamp_view(map_id)
        self._board_update_camera_coordinates(map_id)
        self._draw_board_map(map_id)

    def _board_fit_map(self, map_id: str, *, redraw: bool = True) -> None:
        canvas = self.board_canvases.get(map_id)
        if canvas is None or not canvas.winfo_exists():
            return
        width, height = max(100, canvas.winfo_width()), max(100, canvas.winfo_height())
        fit_scale = min((width - 24) / MAP_CANVAS_WIDTH, (height - 24) / MAP_CANVAS_HEIGHT)
        self.board_view_states[map_id] = {
            "fit_scale": fit_scale,
            "scale": fit_scale,
            "origin_x": (width - MAP_CANVAS_WIDTH * fit_scale) / 2,
            "origin_y": (height - MAP_CANVAS_HEIGHT * fit_scale) / 2,
            "zoom": 1.0,
            "center_x": 0.5,
            "center_y": 0.5,
            "modified": False,
        }
        if redraw:
            self._draw_board_map(map_id)

    def fit_current_board_map(self) -> None:
        if self.selected_board_map_id:
            self._board_fit_map(self.selected_board_map_id)
            self._queue_board_camera_save(self.selected_board_map_id)

    def _board_clamp_view(self, map_id: str) -> None:
        canvas = self.board_canvases.get(map_id)
        state = self.board_view_states.get(map_id)
        if canvas is None or state is None:
            return
        canvas_width, canvas_height = max(1.0, float(canvas.winfo_width())), max(1.0, float(canvas.winfo_height()))
        state["scale"] = max(float(state["fit_scale"]), float(state["scale"]))
        display_width = MAP_CANVAS_WIDTH * float(state["scale"])
        display_height = MAP_CANVAS_HEIGHT * float(state["scale"])
        if display_width <= canvas_width:
            state["origin_x"] = (canvas_width - display_width) / 2
        else:
            state["origin_x"] = min(0.0, max(canvas_width - display_width, float(state["origin_x"])))
        if display_height <= canvas_height:
            state["origin_y"] = (canvas_height - display_height) / 2
        else:
            state["origin_y"] = min(0.0, max(canvas_height - display_height, float(state["origin_y"])))

    def _board_update_camera_coordinates(self, map_id: str) -> None:
        canvas = self.board_canvases.get(map_id)
        state = self.board_view_states.get(map_id)
        if canvas is None or state is None:
            return
        scale = max(0.000001, float(state["scale"]))
        fit_scale = max(0.000001, float(state["fit_scale"]))
        state["zoom"] = max(1.0, min(32.0, scale / fit_scale))
        state["center_x"] = max(0.0, min(
            1.0,
            (float(canvas.winfo_width()) / 2 - float(state["origin_x"]))
            / (MAP_CANVAS_WIDTH * scale),
        ))
        state["center_y"] = max(0.0, min(
            1.0,
            (float(canvas.winfo_height()) / 2 - float(state["origin_y"]))
            / (MAP_CANVAS_HEIGHT * scale),
        ))

    def _board_camera_payload(self, map_id: str) -> dict[str, Any] | None:
        state = self.board_view_states.get(map_id)
        if state is None or not self.selected_session_id:
            return None
        self._board_update_camera_coordinates(map_id)
        return {
            "session_id": self.selected_session_id,
            "zoom": float(state.get("zoom", 1.0)),
            "center_x": float(state.get("center_x", 0.5)),
            "center_y": float(state.get("center_y", 0.5)),
        }

    def _save_board_camera(self, map_id: str, *, synchronous: bool = False) -> None:
        self._board_camera_save_after_ids.pop(map_id, None)
        payload = self._board_camera_payload(map_id)
        if payload is None:
            return
        work = lambda: self.client.request(
            "PUT", f"/api/admin/board/maps/{map_id}/camera", payload
        )
        if synchronous:
            work()
        else:
            self._background(work, quiet=True)

    def _queue_board_camera_save(self, map_id: str, delay_ms: int = 450) -> None:
        pending = self._board_camera_save_after_ids.pop(map_id, None)
        if pending is not None:
            try:
                self.after_cancel(pending)
            except tk.TclError:
                pass
        self._board_camera_save_after_ids[map_id] = self.after(
            delay_ms, lambda selected=map_id: self._save_board_camera(selected)
        )

    def focus_players_on_current_view(self) -> None:
        map_id = self.selected_board_map_id
        payload = self._board_camera_payload(map_id)
        if not map_id or payload is None:
            messagebox.showinfo(
                "Focus players", "Open a map before focusing players.", parent=self
            )
            return
        payload["force_players"] = True

        def complete(_result: Any) -> None:
            self.set_notice("Players were focused on the current map view")

        self._background(
            lambda: self.client.request(
                "PUT", f"/api/admin/board/maps/{map_id}/camera", payload
            ),
            complete,
        )

    @staticmethod
    def _board_wheel_steps(event: tk.Event) -> float:
        return event.delta / 120 if event.delta else 0.0

    @staticmethod
    def _board_windows_key_down(virtual_key: int) -> bool:
        if sys.platform != "win32":
            return False
        try:
            import ctypes

            return bool(ctypes.windll.user32.GetAsyncKeyState(virtual_key) & 0x8000)
        except (AttributeError, OSError):
            return False

    def _board_canvas_under_event(self, event: tk.Event) -> tuple[str, tk.Canvas] | tuple[None, None]:
        try:
            target = self.winfo_containing(event.x_root, event.y_root)
        except (AttributeError, tk.TclError):
            return None, None
        for map_id, canvas in self.board_canvases.items():
            current = target
            while current is not None and current is not canvas:
                current = getattr(current, "master", None)
            if current is canvas:
                return map_id, canvas
        return None, None

    def route_board_wheel(self, event: tk.Event) -> str:
        map_id, canvas = self._board_canvas_under_event(event)
        if not map_id or canvas is None:
            return ""
        if self._board_pan_state is not None and sys.platform == "win32" and not self._board_windows_key_down(0x04):
            self._finish_board_pan()
        if sys.platform == "win32":
            control_down = bool(event.state & 0x0004) or self._board_windows_key_down(0x11)
            alt_down = bool(event.state & (0x0008 | 0x20000)) and self._board_windows_key_down(0x12)
        else:
            control_down = bool(event.state & 0x0004)
            alt_down = bool(event.state & (0x0008 | 0x20000))
        state = self.board_view_states.get(map_id)
        if state is None:
            self._board_fit_map(map_id, redraw=False)
            state = self.board_view_states[map_id]
        steps = self._board_wheel_steps(event)
        if control_down:
            point = self._normalized_board_point(map_id, event.x, event.y, clamp=False)
            state["scale"] = max(
                float(state["fit_scale"]),
                min(float(state["fit_scale"]) * 32.0, float(state["scale"]) * (1.15 ** steps)),
            )
            state["origin_x"] = event.x - point[0] * MAP_CANVAS_WIDTH * float(state["scale"])
            state["origin_y"] = event.y - point[1] * MAP_CANVAS_HEIGHT * float(state["scale"])
        elif alt_down:
            state["origin_x"] = float(state["origin_x"]) + steps * 24
        else:
            state["origin_y"] = float(state["origin_y"]) + steps * 24
        state["modified"] = True
        self._board_clamp_view(map_id)
        self._board_update_camera_coordinates(map_id)
        self._draw_board_map(map_id)
        self._queue_board_camera_save(map_id)
        return "break"

    def board_pan_press(self, event: tk.Event, map_id: str) -> str:
        self._finish_board_pan()
        state = self.board_view_states.get(map_id)
        if state is None:
            self._board_fit_map(map_id, redraw=False)
            state = self.board_view_states[map_id]
        self._board_pan_state = (
            map_id,
            float(event.x_root),
            float(event.y_root),
            float(state["origin_x"]),
            float(state["origin_y"]),
        )
        self.board_canvases[map_id].configure(cursor="fleur")
        self._board_pan_watchdog_id = self.after(40, self._watch_board_middle_button)
        return "break"

    def board_pan_drag(self, event: tk.Event) -> str:
        if self._board_pan_state is None:
            return ""
        map_id, start_x, start_y, origin_x, origin_y = self._board_pan_state
        state = self.board_view_states.get(map_id)
        if state is None:
            return ""
        state["origin_x"] = origin_x + float(event.x_root) - start_x
        state["origin_y"] = origin_y + float(event.y_root) - start_y
        state["modified"] = True
        self._board_clamp_view(map_id)
        self._board_update_camera_coordinates(map_id)
        self._draw_board_map(map_id)
        return "break"

    def _watch_board_middle_button(self) -> None:
        self._board_pan_watchdog_id = None
        if self._board_pan_state is None:
            return
        if sys.platform == "win32" and not self._board_windows_key_down(0x04):
            self._finish_board_pan()
            return
        self._board_pan_watchdog_id = self.after(40, self._watch_board_middle_button)

    def _finish_board_pan(self) -> bool:
        if self._board_pan_state is None:
            return False
        map_id = self._board_pan_state[0]
        self._board_pan_state = None
        if self._board_pan_watchdog_id is not None:
            try:
                self.after_cancel(self._board_pan_watchdog_id)
            except tk.TclError:
                pass
            self._board_pan_watchdog_id = None
        canvas = self.board_canvases.get(map_id)
        if canvas is not None and canvas.winfo_exists():
            canvas.configure(cursor="crosshair" if self.board_obscure_drawing else "arrow")
        self._board_update_camera_coordinates(map_id)
        self._queue_board_camera_save(map_id, 100)
        return True

    def board_pan_release(self, _event: tk.Event | None = None) -> str:
        return "break" if self._finish_board_pan() else ""

    def start_board_obscuration_drawing(self) -> None:
        if not self.selected_board_map_id:
            messagebox.showinfo(
                "Draw obfuscation",
                "Add and select a map before drawing an obfuscation.",
                parent=self,
            )
            return
        self.open_board_map_controls()
        self.board_obscure_mode = True
        self.board_obscure_drawing = True
        self.board_obscure_draft_points = []
        self.board_selected_obscuration_id = ""
        self.board_selected_obscuration_node = None
        self.board_obscuration_list.selection_clear(0, "end")
        self.board_obscure_button.configure(text="✎")
        self.board_draft_status.configure(
            text="Drawing…",
            foreground=self.MUTED,
        )
        canvas = self.board_canvases.get(self.selected_board_map_id)
        if canvas is not None:
            canvas.configure(cursor="crosshair")
            canvas.focus_set()
        self._draw_board_map(self.selected_board_map_id)

    def toggle_board_obscure_mode(self) -> None:
        """Compatibility alias: O now explicitly starts the obfuscation pen."""

        self.start_board_obscuration_drawing()

    def board_obscure_shortcut(self, event: tk.Event) -> str:
        if event.widget.winfo_class() in {"Entry", "TEntry", "Text", "TCombobox", "Spinbox", "TSpinbox"}:
            return ""
        self.start_board_obscuration_drawing()
        return "break"

    def _board_pointer_start(self, event: tk.Event, map_id: str) -> None:
        if self.creature_placement is not None:
            self._place_next_creature(event, map_id)
            return
        canvas = self.board_canvases[map_id]
        actor_id, _part = self._actor_at(canvas, map_id, event.x, event.y)
        if actor_id:
            # Character pieces remain movable even while a map-authoring tool
            # is active.  The Headmaster must never have to leave a tool just
            # to reposition an occupant.
            self._board_drag_start(event, map_id)
        elif self.board_obscure_mode:
            self._board_obscuration_press(event, map_id)
        else:
            self._board_drag_start(event, map_id)

    def _board_obscuration_point(self, map_id: str, x: float, y: float, *, clamp: bool = False) -> dict[str, float]:
        nx, ny = self._normalized_board_point(map_id, x, y, clamp=clamp)
        return {"x": nx, "y": ny}

    @staticmethod
    def _board_nearest_edge(points: list[dict[str, float]], x: float, y: float) -> tuple[int, dict[str, float], float]:
        best_index, best_point, best_distance = 0, {"x": x, "y": y}, float("inf")
        for index, start in enumerate(points):
            end = points[(index + 1) % len(points)]
            dx, dy = end["x"] - start["x"], end["y"] - start["y"]
            length_squared = dx * dx + dy * dy
            ratio = 0.0 if length_squared == 0 else max(0.0, min(1.0, ((x - start["x"]) * dx + (y - start["y"]) * dy) / length_squared))
            projected = {"x": start["x"] + ratio * dx, "y": start["y"] + ratio * dy}
            distance = math.hypot(x - projected["x"], y - projected["y"])
            if distance < best_distance:
                best_index, best_point, best_distance = index, projected, distance
        return best_index, best_point, best_distance

    @staticmethod
    def _board_point_in_polygon(x: float, y: float, points: list[dict[str, float]]) -> bool:
        inside, previous = False, points[-1]
        for current in points:
            if (current["y"] > y) != (previous["y"] > y):
                crossing = (previous["x"] - current["x"]) * (y - current["y"]) / (previous["y"] - current["y"]) + current["x"]
                if x < crossing:
                    inside = not inside
            previous = current
        return inside

    def _board_mark_presentation_dirty(self) -> None:
        draft = self._board_presentation_draft()
        if draft is not None:
            draft["dirty"] = True
            self.board_confirmation_message_until = 0.0
            self.board_draft_status.configure(
                text="Pending",
                foreground=self.RED,
            )
            self.board_confirm_button.configure(text="Send", state="normal")

    def _board_obscuration_press(self, event: tk.Event, map_id: str) -> None:
        if map_id != self.selected_board_map_id:
            return
        point = self._board_obscuration_point(map_id, event.x, event.y)
        if not 0.0 <= point["x"] <= 1.0 or not 0.0 <= point["y"] <= 1.0:
            return
        canvas = self.board_canvases[map_id]
        left, top, width, height = self.board_canvas_geometry.get(map_id, (0, 0, 1, 1))
        if self.board_obscure_draft_points:
            first = self.board_obscure_draft_points[0]
            first_x, first_y = left + first["x"] * width, top + first["y"] * height
            if len(self.board_obscure_draft_points) >= 3 and math.hypot(event.x - first_x, event.y - first_y) <= 16:
                self.complete_board_obscuration(event, map_id)
                return
            last = self.board_obscure_draft_points[-1]
            if math.hypot(point["x"] - last["x"], point["y"] - last["y"]) > 1e-6:
                self.board_obscure_draft_points.append(point)
            self._draw_board_map(map_id)
            return
        if self.board_obscure_drawing:
            self.board_obscure_draft_points = [point]
            canvas.focus_set()
            self._draw_board_map(map_id)
            return
        draft = self._board_presentation_draft(map_id)
        obscurations = list((draft or {}).get("obscurations", []))
        selected = next((item for item in obscurations if str(item.get("record_id")) == self.board_selected_obscuration_id), None)
        if selected is not None:
            for index, node in enumerate(selected["points"]):
                node_x, node_y = left + node["x"] * width, top + node["y"] * height
                if math.hypot(event.x - node_x, event.y - node_y) <= 9:
                    self.board_selected_obscuration_node = index
                    self._board_obscure_drag = {"kind": "node", "changed": False}
                    return
            edge_index, projected, _distance = self._board_nearest_edge(selected["points"], point["x"], point["y"])
            projected_x, projected_y = left + projected["x"] * width, top + projected["y"] * height
            if math.hypot(event.x - projected_x, event.y - projected_y) <= 12:
                selected["points"].insert(edge_index + 1, projected)
                selected["last_updated"] = datetime.utcnow().isoformat() + "Z"
                self.board_selected_obscuration_node = edge_index + 1
                self._board_mark_presentation_dirty()
                self._refresh_board_obscuration_list()
                self._draw_board_map(map_id)
                return
        hit = next((item for item in reversed(obscurations) if self._board_point_in_polygon(point["x"], point["y"], item["points"])), None)
        if hit is not None:
            self.board_selected_obscuration_id = str(hit["record_id"])
            self.board_selected_obscuration_node = None
            self._board_obscure_drag = {"kind": "polygon", "start": point, "points": deepcopy(hit["points"]), "changed": False}
        else:
            self.board_selected_obscuration_id = ""
            self.board_selected_obscuration_node = None
        canvas.focus_set()
        self._draw_board_map(map_id)

    def complete_board_obscuration(self, event: tk.Event | None = None, map_id: str | None = None) -> str:
        if event is not None and event.widget.winfo_class() in {"Entry", "TEntry", "Text", "TCombobox", "Spinbox", "TSpinbox"}:
            return ""
        map_id = map_id or self.selected_board_map_id
        if not self.board_obscure_mode or map_id != self.selected_board_map_id:
            return ""
        if len(self.board_obscure_draft_points) < 3:
            return "break"
        draft = self._board_presentation_draft(map_id)
        if draft is None:
            return "break"
        now = datetime.utcnow().isoformat() + "Z"
        obscuration = {
            "record_id": str(uuid4()),
            "name": f"Obfuscation {len(draft['obscurations']) + 1}",
            "points": deepcopy(self.board_obscure_draft_points),
            "created_at": now,
            "last_updated": now,
        }
        draft["obscurations"].append(obscuration)
        self.board_obscure_draft_points = []
        self.board_obscure_drawing = False
        self.board_selected_obscuration_id = obscuration["record_id"]
        self.board_selected_obscuration_node = None
        self.board_obscure_button.configure(text="✎")
        self._board_mark_presentation_dirty()
        self._refresh_board_obscuration_list()
        self._draw_board_map(map_id)
        return "break"

    def cancel_board_obscuration(self) -> None:
        self.board_obscure_draft_points = []
        self._board_obscure_drag = None
        if self.board_obscure_drawing:
            self.board_obscure_drawing = False
            self.board_obscure_button.configure(text="✎")
            if not self.board_selected_obscuration_id:
                self.board_obscure_mode = False
            self._sync_board_presentation_controls()
        canvas = self.board_canvases.get(self.selected_board_map_id)
        if canvas is not None and canvas.winfo_exists():
            canvas.delete("obscuration-close-cursor")
            canvas.configure(cursor="crosshair" if self.board_obscure_drawing else "arrow")
            self._draw_board_map(self.selected_board_map_id)

    def board_obscure_motion(self, event: tk.Event, map_id: str) -> None:
        if not self.board_obscure_mode or map_id != self.selected_board_map_id or not self.board_obscure_draft_points:
            return
        canvas = self.board_canvases[map_id]
        canvas.delete("obscuration-close-cursor")
        if len(self.board_obscure_draft_points) < 3:
            canvas.configure(cursor="crosshair")
            return
        left, top, width, height = self.board_canvas_geometry.get(map_id, (0, 0, 1, 1))
        first = self.board_obscure_draft_points[0]
        first_x, first_y = left + first["x"] * width, top + first["y"] * height
        if math.hypot(event.x - first_x, event.y - first_y) > 16:
            canvas.configure(cursor="crosshair")
            return
        canvas.configure(cursor="none")
        canvas.create_oval(event.x - 10, event.y - 10, event.x + 10, event.y + 10, fill="#2f7d32", outline="#ffffff", width=2, tags=("obscuration-close-cursor",))
        canvas.create_text(event.x, event.y, text="✓", fill="#ffffff", font=("Segoe UI Symbol", 12, "bold"), tags=("obscuration-close-cursor",))

    def board_canvas_leave(self, _event: tk.Event, map_id: str) -> None:
        canvas = self.board_canvases.get(map_id)
        if canvas is not None:
            canvas.delete("obscuration-close-cursor")
            canvas.configure(cursor="crosshair" if self.board_obscure_drawing else "arrow")

    def delete_board_obscuration(self) -> None:
        draft = self._board_presentation_draft()
        if draft is None or not self.board_selected_obscuration_id:
            return
        draft["obscurations"] = [
            item for item in draft["obscurations"]
            if str(item.get("record_id")) != self.board_selected_obscuration_id
        ]
        self.board_selected_obscuration_id = ""
        self.board_selected_obscuration_node = None
        self.board_obscure_mode = False
        self._board_mark_presentation_dirty()
        self._refresh_board_obscuration_list()
        self._draw_board_map(self.selected_board_map_id)

    def delete_board_obscuration_node(self, event: tk.Event | None = None) -> str:
        if event is not None and event.widget.winfo_class() in {"Entry", "TEntry", "Text", "TCombobox", "Spinbox", "TSpinbox"}:
            return ""
        draft = self._board_presentation_draft()
        selected = next(
            (item for item in (draft or {}).get("obscurations", []) if str(item.get("record_id")) == self.board_selected_obscuration_id),
            None,
        )
        if selected is None or self.board_selected_obscuration_node is None:
            return ""
        if len(selected["points"]) <= 3:
            messagebox.showinfo("Three nodes required", "An obscuring shape must retain at least three nodes.", parent=self)
            return "break"
        selected["points"].pop(self.board_selected_obscuration_node)
        selected["last_updated"] = datetime.utcnow().isoformat() + "Z"
        self.board_selected_obscuration_node = None
        self._board_mark_presentation_dirty()
        self._refresh_board_obscuration_list()
        self._draw_board_map(self.selected_board_map_id)
        return "break"

    def _actor_at(self, canvas: tk.Canvas, map_id: str, x: float, y: float) -> tuple[str, str]:
        # Prefer the canvas item directly under the pointer.  The broader checks
        # make small overview dots and the thin leader line practical targets.
        candidates = list(canvas.find_withtag("current"))
        candidates.extend(canvas.find_overlapping(x - 14, y - 14, x + 14, y + 14))
        seen: set[int] = set()
        for item in reversed(candidates):
            if item in seen:
                continue
            seen.add(item)
            actor_id = self._board_canvas_actors.get((map_id, item))
            if actor_id:
                return actor_id, self._board_canvas_actor_parts.get((map_id, item), "piece")

        # Canvas text has a surprisingly narrow hit target on Windows.  Fall
        # back to the visible bounds of every actor item, with a small margin.
        for (actor_map_id, item), actor_id in reversed(tuple(self._board_canvas_actors.items())):
            if actor_map_id != map_id:
                continue
            bounds = canvas.bbox(item)
            if bounds and bounds[0] - 6 <= x <= bounds[2] + 6 and bounds[1] - 6 <= y <= bounds[3] + 6:
                return actor_id, self._board_canvas_actor_parts.get((map_id, item), "piece")
        return "", ""

    def _board_drag_start(self, event: tk.Event, map_id: str) -> None:
        canvas = self.board_canvases[map_id]
        self._drag_start_point = (float(event.x), float(event.y))
        self._drag_actor_id, self._drag_actor_part = self._actor_at(canvas, map_id, event.x, event.y)
        self._drag_label_only = bool(self._drag_actor_id and self._drag_actor_part == "label" and event.state & 0x0004)
        if self._drag_actor_id:
            actor = next((item for item in self.board_snapshot.get("actors", []) if item.get("actor_id") == self._drag_actor_id), {})
            offset = actor.get("label_offset") if isinstance(actor.get("label_offset"), dict) else {}
            self._drag_label_origin = {"x": float(offset.get("x", 0.0)), "y": float(offset.get("y", 0.0))}
            self.selected_board_actor_id = self._drag_actor_id
            self._render_board_actor_list()
            self._draw_board_map(map_id)

    def _normalized_board_point(
        self,
        map_id: str,
        x: float,
        y: float,
        *,
        clamp: bool = True,
    ) -> tuple[float, float]:
        left, top, width, height = self.board_canvas_geometry.get(map_id, (0, 0, 1, 1))
        nx, ny = (x - left) / max(1.0, width), (y - top) / max(1.0, height)
        if clamp:
            nx, ny = max(0.0, min(1.0, nx)), max(0.0, min(1.0, ny))
        return nx, ny

    def _board_drag_move(self, event: tk.Event, map_id: str) -> None:
        if self._board_obscure_drag is not None and self.board_obscure_mode:
            draft = self._board_presentation_draft(map_id)
            selected = next(
                (item for item in (draft or {}).get("obscurations", []) if str(item.get("record_id")) == self.board_selected_obscuration_id),
                None,
            )
            if selected is None:
                return
            point = self._board_obscuration_point(map_id, event.x, event.y, clamp=True)
            if self._board_obscure_drag["kind"] == "node" and self.board_selected_obscuration_node is not None:
                selected["points"][self.board_selected_obscuration_node] = point
            else:
                start = self._board_obscure_drag["start"]
                original = self._board_obscure_drag["points"]
                dx, dy = point["x"] - start["x"], point["y"] - start["y"]
                min_x, max_x = min(item["x"] for item in original), max(item["x"] for item in original)
                min_y, max_y = min(item["y"] for item in original), max(item["y"] for item in original)
                dx, dy = min(max(dx, -min_x), 1.0 - max_x), min(max(dy, -min_y), 1.0 - max_y)
                selected["points"] = [{"x": item["x"] + dx, "y": item["y"] + dy} for item in original]
            self._board_obscure_drag["changed"] = True
            self._draw_board_map(map_id)
            return
        if not self._drag_actor_id:
            return
        if self._drag_label_only:
            start = self._drag_start_point or (float(event.x), float(event.y))
            _left, _top, draw_width, draw_height = self.board_canvas_geometry.get(map_id, (0, 0, 1, 1))
            dx = (float(event.x) - start[0]) / max(1.0, draw_width)
            dy = (float(event.y) - start[1]) / max(1.0, draw_height)
            actor = next((item for item in self.board_snapshot.get("actors", []) if item.get("actor_id") == self._drag_actor_id), None)
            if actor is not None:
                actor["label_offset"] = {
                    "x": max(-1.0, min(1.0, self._drag_label_origin["x"] + dx)),
                    "y": max(-1.0, min(1.0, self._drag_label_origin["y"] + dy)),
                }
                self._draw_board_map(map_id)
            return
        x, y = self._normalized_board_point(map_id, event.x, event.y)
        actor = next((item for item in self.board_snapshot.get("actors", []) if item.get("actor_id") == self._drag_actor_id), None)
        if actor:
            actor.update(map_id=map_id, x=x, y=y)
            self._draw_board_map(map_id)
        if self._board_preview_after:
            self.after_cancel(self._board_preview_after)
        self._board_preview_after = self.after(
            80,
            lambda: self._send_board_preview(self._drag_actor_id, map_id, x, y),
        )

    def _send_board_preview(self, person_id: str, map_id: str, x: float, y: float) -> None:
        self._board_preview_after = None
        session_id = self.selected_session_id
        if not session_id:
            return
        actor = next(
            (item for item in self.board_snapshot.get("actors", []) if item.get("actor_id") == person_id),
            None,
        )
        if actor and actor.get("actor_type") == "creature":
            return
        self._background(
            lambda: self.client.request("POST", "/api/admin/board/move-preview", {
                "session_id": session_id, "person_id": person_id, "map_id": map_id, "x": x, "y": y,
            }),
            quiet=True,
        )

    def _board_drag_end(self, event: tk.Event, map_id: str) -> None:
        if self._board_obscure_drag is not None and self.board_obscure_mode:
            changed = bool(self._board_obscure_drag.get("changed"))
            self._board_obscure_drag = None
            if changed:
                draft = self._board_presentation_draft(map_id)
                selected = next(
                    (item for item in (draft or {}).get("obscurations", []) if str(item.get("record_id")) == self.board_selected_obscuration_id),
                    None,
                )
                if selected is not None:
                    selected["last_updated"] = datetime.utcnow().isoformat() + "Z"
                self._board_mark_presentation_dirty()
                self._draw_board_map(map_id)
            return
        person_id = self._drag_actor_id
        self._drag_actor_id = ""
        label_only = self._drag_label_only
        self._drag_label_only = False
        self._drag_actor_part = ""
        start = self._drag_start_point
        self._drag_start_point = None
        if not person_id:
            return
        if label_only:
            actor = next((item for item in self.board_snapshot.get("actors", []) if item.get("actor_id") == person_id), {})
            if actor.get("actor_type") == "creature":
                self._background(
                    lambda: self.client.request(
                        "PUT", f"/api/admin/board/creatures/{person_id}",
                        {
                            "session_id": self.selected_session_id,
                            "label_x": float(actor.get("label_offset", {}).get("x", 0.0)),
                            "label_y": float(actor.get("label_offset", {}).get("y", 0.0)),
                        },
                    ),
                    lambda _result: self.refresh(silent=True),
                )
                return
            self._background(
                lambda: self.client.request(
                    "PUT",
                    f"/api/admin/board/people/{person_id}",
                    {
                        "session_id": self.selected_session_id,
                        "label_offset": actor.get("label_offset", {"x": 0.0, "y": 0.0}),
                    },
                ),
                lambda _result: self.refresh(silent=True),
            )
            return
        if start and abs(float(event.x) - start[0]) < 5 and abs(float(event.y) - start[1]) < 5:
            # A normal left click selects the piece; only right click opens
            # its Windows-style action menu.
            return
        if not self.selected_session_id:
            return
        x, y = self._normalized_board_point(map_id, event.x, event.y)
        actor = next(
            (item for item in self.board_snapshot.get("actors", []) if item.get("actor_id") == person_id),
            None,
        )
        if actor and actor.get("actor_type") == "creature":
            self._background(
                lambda: self.client.request(
                    "PUT", f"/api/admin/board/creatures/{person_id}",
                    {
                        "session_id": self.selected_session_id,
                        "map_id": map_id, "x": x, "y": y,
                    },
                ),
                lambda _result: self.refresh(silent=True),
            )
            return
        payload = {"session_id": self.selected_session_id, "person_id": person_id, "map_id": map_id, "x": x, "y": y}
        self._background(
            lambda: self.client.request("POST", "/api/admin/board/move", payload),
            lambda _result: self.refresh(silent=True),
        )

    def _board_piece_menu(self, event: tk.Event, map_id: str) -> str:
        canvas = self.board_canvases[map_id]
        actor_id, _part = self._actor_at(canvas, map_id, event.x, event.y)
        if actor_id:
            # A character is always the primary right-click target, including
            # while the obfuscation editor is open.
            self.selected_board_actor_id = actor_id
            self._draw_board_map(map_id)
            self._render_board_actor_list()
            self._open_piece_controls(canvas, event.x_root, event.y_root)
            return "break"
        if self.board_obscure_mode:
            draft = self._board_presentation_draft(map_id)
            left, top, width, height = self.board_canvas_geometry.get(map_id, (0, 0, 1, 1))
            for obscuration in (draft or {}).get("obscurations", []):
                for index, point in enumerate(obscuration.get("points", [])):
                    x, y = left + point["x"] * width, top + point["y"] * height
                    if math.hypot(event.x - x, event.y - y) <= 10:
                        self.board_selected_obscuration_id = str(obscuration.get("record_id"))
                        self.board_selected_obscuration_node = index
                        return self.delete_board_obscuration_node(event)
            return "break"
        return "break"

    def _open_piece_controls(self, anchor: tk.Widget, root_x: int, root_y: int) -> None:
        del anchor
        actor = self._selected_board_actor()
        if not actor:
            return
        if self._piece_popup is not None and self._piece_popup.winfo_exists():
            self._piece_popup.destroy()
        popup = tk.Menu(self, tearoff=False)
        self._piece_popup = popup
        if actor.get("actor_type") == "creature":
            popup.add_command(
                label=str(actor.get("internal_label") or actor.get("name") or "Creature"),
                state="disabled",
            )
            visible = actor.get("visibility") == "players"
            popup.add_command(
                label="Hide from players" if visible else "Reveal to players",
                command=self.toggle_selected_creature_visibility,
            )
            popup.add_command(label="Add to group…", command=self.manage_creature_group)
            if actor.get("life_state") == "alive":
                popup.add_command(
                    label="Capture, lure, tame, or bond…",
                    command=self.interact_with_selected_creature,
                )
            popup.add_command(label="Assign wound…", command=self.wound_selected_creature)
            popup.add_command(
                label="Revive" if actor.get("life_state") == "dead" else "Mark dead",
                command=self.toggle_selected_creature_life,
            )
            popup.add_separator()
            popup.add_command(
                label="Enter battle…",
                command=lambda: self._creature_action_request(
                    "enter_battle",
                    battle_name=(simpledialog.askstring("Battle", "Battle name:", parent=self) or "Battle"),
                ),
            )
            popup.add_command(
                label="Leave battle", command=lambda: self._creature_action_request("leave_battle")
            )
            popup.add_command(
                label="Reroll stats…",
                command=lambda: (
                    self._creature_action_request("reroll")
                    if messagebox.askyesno(
                        "Reroll creature",
                        "Replace all generated stats and action aptitudes?",
                        parent=self,
                    ) else None
                ),
            )
            popup.add_separator()
            popup.add_command(
                label="Delete accidental spawn…",
                command=lambda: (
                    self._creature_action_request("delete")
                    if messagebox.askyesno(
                        "Delete creature", "Permanently delete this campaign creature?", parent=self
                    ) else None
                ),
            )
            try:
                popup.tk_popup(root_x, root_y)
            finally:
                popup.grab_release()
            return
        popup.add_command(label=str(actor.get("name") or "Unknown occupant"), state="disabled")
        popup.add_command(label="Teach...", command=self.teach_selected_actor)
        popup.add_command(label="Search area...", command=self.search_area_for_selected_actor)
        popup.add_separator()
        visible = actor.get("visibility") == "players"
        popup.add_command(label="Transport…", command=self.transport_selected_actor)
        popup.add_command(label="Add to group…", command=self.manage_actor_group)
        popup.add_separator()
        popup.add_command(label="Assign wound…", command=self.add_selected_actor_wound)
        popup.add_command(label="Enter or leave battle…", command=self.toggle_selected_actor_battle)
        popup.add_command(
            label="Ground",
            state="normal" if actor.get("airborne") else "disabled",
            command=lambda: self._send_selected_actor_action("ground"),
        )
        popup.add_command(label="Add character note…", command=self.add_selected_actor_note)
        popup.add_command(label="Adjust Knut balance…", command=self.adjust_selected_actor_currency)
        popup.add_separator()
        popup.add_command(
            label="Hide from players" if visible else "Reveal to players",
            command=lambda: self.update_selected_actor(
                visibility="headmaster" if visible else "players"
            ),
        )
        popup.add_command(label="Display as dot", command=lambda: self.update_selected_actor(display_mode="dot"))
        popup.add_command(label="Display portrait", command=lambda: self.update_selected_actor(display_mode="token"))
        popup.add_command(
            label=(
                "Conceal name from players"
                if bool(actor.get("name_revealed"))
                else "Share name with players"
            ),
            command=self.toggle_selected_name,
        )
        popup.add_separator()
        popup.add_command(
            label="Increase nameplate size",
            command=lambda: self.adjust_selected_nameplate_size(0.1),
        )
        popup.add_command(
            label="Decrease nameplate size",
            command=lambda: self.adjust_selected_nameplate_size(-0.1),
        )
        popup.add_separator()
        popup.add_command(
            label="Increase token size",
            command=lambda: self.adjust_current_map_token_scale(1),
        )
        popup.add_command(
            label="Decrease token size",
            command=lambda: self.adjust_current_map_token_scale(-1),
        )
        try:
            popup.tk_popup(root_x, root_y)
        finally:
            popup.grab_release()

    def _searchable_record_panel(
        self, parent: tk.Misc, records: list[dict[str, Any]],
        selected: tk.StringVar, *, height: int = 8,
    ) -> ttk.Frame:
        """Search-first chooser used for large core-data collections."""
        shell = ttk.Frame(parent)
        query = tk.StringVar()
        entry = ttk.Entry(shell, textvariable=query)
        entry.pack(fill="x", pady=(0, 4))
        listing = tk.Listbox(shell, height=height, exportselection=False)
        listing.pack(fill="both", expand=True)
        visible: list[dict[str, Any]] = []

        def render(*_args: Any) -> None:
            term = query.get().strip().casefold()
            visible[:] = [item for item in records if not term or term in str(item.get("name") or "").casefold()][:500]
            listing.delete(0, "end")
            for item in visible:
                listing.insert("end", str(item.get("name") or "Unknown"))

        def choose(_event: tk.Event | None = None) -> None:
            indices = listing.curselection()
            if indices:
                selected.set(str(visible[indices[0]].get("record_id") or ""))

        query.trace_add("write", render)
        listing.bind("<<ListboxSelect>>", choose)
        listing.bind("<Double-Button-1>", choose)
        render()
        shell.after_idle(entry.focus_set)
        return shell

    def search_area_for_selected_actor(self) -> None:
        actor = self._selected_board_actor()
        if not actor or not self.selected_session_id:
            return
        payload = {
            "session_id": self.selected_session_id,
            "person_id": str(actor.get("actor_id") or ""),
        }
        self._background(
            lambda: self.client.request(
                "POST", "/api/admin/regions/search-options", payload
            ),
            lambda options: self._open_region_search_dialog(actor, options),
        )

    def _open_region_search_dialog(
        self, actor: dict[str, Any], options: dict[str, Any]
    ) -> None:
        regions = list(options.get("regions", []) or [])
        if not regions:
            messagebox.showinfo(
                "Search area",
                "There are no available searchable areas on this character's map.",
                parent=self,
            )
            return

        dialog = tk.Toplevel(self)
        dialog.title(f"Search area — {actor.get('name') or 'Character'}")
        dialog.transient(self)
        dialog.grab_set()
        dialog.geometry("640x430")
        dialog.minsize(520, 360)
        apply_window_icon(dialog, GAME_BOARD_ICON)

        shell = ttk.Frame(dialog, padding=10)
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(0, weight=1)
        shell.columnconfigure(1, weight=1)
        shell.rowconfigure(2, weight=1)

        ttk.Label(
            shell,
            text=f"{options.get('map_name') or 'Current map'} · {actor.get('name') or 'Character'}",
            style="CardTitle.TLabel",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))

        query = tk.StringVar()
        search_entry = ttk.Entry(shell, textvariable=query)
        search_entry.grid(row=1, column=0, sticky="ew", padx=(0, 5))
        search_entry.insert(0, "")
        ttk.Label(shell, text="Method", style="Card.TLabel").grid(
            row=1, column=1, sticky="w", padx=(5, 0)
        )

        region_list = tk.Listbox(shell, exportselection=False)
        region_list.grid(row=2, column=0, sticky="nsew", padx=(0, 5), pady=(5, 8))
        mode_list = tk.Listbox(shell, exportselection=False)
        mode_list.grid(row=2, column=1, sticky="nsew", padx=(5, 0), pady=(5, 8))

        extraction_row = ttk.Frame(shell)
        extraction_row.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        extraction_row.columnconfigure(1, weight=1)
        extraction_label = ttk.Label(
            extraction_row, text="Searching Method", style="Card.TLabel"
        )
        extraction_var = tk.StringVar()
        extraction_box = ttk.Combobox(
            extraction_row,
            textvariable=extraction_var,
            state="readonly",
        )

        visible_regions: list[dict[str, Any]] = []
        visible_modes: list[dict[str, Any]] = []
        extraction_by_name: dict[str, str] = {}

        def selected_region() -> dict[str, Any] | None:
            indices = region_list.curselection()
            return visible_regions[indices[0]] if indices else None

        def selected_mode() -> dict[str, Any] | None:
            indices = mode_list.curselection()
            return visible_modes[indices[0]] if indices else None

        def render_extraction(_event: tk.Event | None = None) -> None:
            nonlocal extraction_by_name
            method = selected_mode() or {}
            extraction_methods = list(method.get("extraction_methods", []) or [])
            extraction_by_name = {
                str(item.get("name") or "Method"): str(item.get("record_id") or "")
                for item in extraction_methods
            }
            extraction_box.configure(values=list(extraction_by_name))
            extraction_var.set("")
            if extraction_methods:
                extraction_label.grid(row=0, column=0, sticky="w", padx=(0, 6))
                extraction_box.grid(row=0, column=1, sticky="ew")
            else:
                extraction_label.grid_remove()
                extraction_box.grid_remove()

        def render_modes(_event: tk.Event | None = None) -> None:
            nonlocal visible_modes
            region = selected_region() or {}
            visible_modes = list(region.get("modes", []) or [])
            mode_list.delete(0, "end")
            for mode in visible_modes:
                suffix = " · already searched" if mode.get("attempted_today") else ""
                mode_list.insert(
                    "end",
                    f"{mode.get('name') or 'Search'} · {mode.get('skill') or 'Skill'}{suffix}",
                )
            if visible_modes:
                mode_list.selection_set(0)
            render_extraction()

        def render_regions(*_args: Any) -> None:
            nonlocal visible_regions
            needle = query.get().strip().casefold()
            visible_regions = [
                item for item in regions
                if not needle or needle in str(item.get("title") or "Search").casefold()
            ]
            region_list.delete(0, "end")
            for region in visible_regions:
                region_list.insert("end", str(region.get("title") or "Search"))
            if visible_regions:
                region_list.selection_set(0)
            render_modes()

        def search() -> None:
            region = selected_region()
            mode = selected_mode()
            if region is None or mode is None:
                messagebox.showinfo(
                    "Search area", "Choose an area and search method.", parent=dialog
                )
                return
            if mode.get("attempted_today"):
                messagebox.showinfo(
                    "Search area", "This area was already searched today.", parent=dialog
                )
                return
            method_id = extraction_by_name.get(extraction_var.get(), "")
            if extraction_by_name and not method_id:
                messagebox.showinfo(
                    "Search area", "Choose a Searching Method.", parent=dialog
                )
                extraction_box.focus_set()
                return
            payload = {
                "session_id": self.selected_session_id,
                "person_id": str(actor.get("actor_id") or ""),
                "map_id": str(options.get("map_id") or ""),
                "region_id": str(region.get("region_id") or ""),
                "mode_id": str(mode.get("record_id") or ""),
                "extraction_method_id": method_id,
            }
            self._background(
                lambda: self.client.request(
                    "POST", "/api/admin/regions/search", payload
                ),
                lambda _result: (dialog.destroy(), self.refresh(silent=True)),
            )

        region_list.bind("<<ListboxSelect>>", render_modes)
        mode_list.bind("<<ListboxSelect>>", render_extraction)
        query.trace_add("write", render_regions)
        render_regions()

        actions = ttk.Frame(shell)
        actions.grid(row=4, column=0, columnspan=2, sticky="ew")
        ttk.Button(
            actions, text="Cancel", style="Quiet.TButton", command=dialog.destroy
        ).pack(side="right")
        ttk.Button(actions, text="Search", command=search).pack(
            side="right", padx=(0, 6)
        )
        dialog.after_idle(search_entry.focus_set)

    def teach_selected_actor(self) -> None:
        actor = self._selected_board_actor()
        if not actor or not self.selected_session_id:
            return
        request = {
            "session_id": self.selected_session_id,
            "teacher_person_id": str(actor.get("actor_id") or ""),
        }
        self._background(
            lambda: self.client.request(
                "POST", "/api/admin/teaching/options", request
            ),
            lambda options: self._open_known_teaching_dialog(actor, options),
        )
        return
        catalog = self.state_data.get("teaching_catalog", {}) or {}
        dialog = tk.Toplevel(self)
        dialog.title(f"Teach — {actor.get('name') or 'Pupil'}")
        dialog.transient(self)
        dialog.grab_set()
        dialog.geometry("620x500")
        apply_window_icon(dialog, GAME_BOARD_ICON)
        shell = ttk.Frame(dialog, padding=10)
        shell.pack(fill="both", expand=True)
        ttk.Label(shell, text="Pupil", style="CardTitle.TLabel").pack(anchor="w")
        pupil = tk.StringVar(value=str(actor.get("actor_id") or ""))
        characters = [
            {"record_id": item["id"], "name": item["name"]}
            for item in self.state_data.get("characters", [])
        ]
        self._searchable_record_panel(shell, characters, pupil, height=6).pack(
            fill="both", expand=True, pady=(0, 8)
        )
        ttk.Label(shell, text="Subject", style="CardTitle.TLabel").pack(anchor="w")
        kind = tk.StringVar(value="spell")
        chosen = tk.StringVar()
        kinds = ttk.Frame(shell)
        kinds.pack(fill="x", pady=(8, 0))
        chooser_host = ttk.Frame(shell)
        chooser_host.pack(fill="both", expand=True, pady=8)

        def render_kind() -> None:
            for child in chooser_host.winfo_children():
                child.destroy()
            chosen.set("")
            self._searchable_record_panel(chooser_host, list(catalog.get(kind.get(), []) or []), chosen, height=14).pack(fill="both", expand=True)

        for value, label in (("spell", "Spells"), ("proficiency", "Proficiencies"), ("recipe", "Recipes")):
            ttk.Radiobutton(kinds, text=label, variable=kind, value=value, command=render_kind).pack(side="left", padx=(0, 12))
        render_kind()

        def teach() -> None:
            record_id = chosen.get()
            record = next((item for item in catalog.get(kind.get(), []) if item.get("record_id") == record_id), None)
            if record is None:
                messagebox.showinfo("Teach", "Choose a subject from the search results.", parent=dialog)
                return
            if not pupil.get():
                messagebox.showinfo("Teach", "Choose a pupil from the search results.", parent=dialog)
                return
            payload = {"session_id": self.selected_session_id, "pupil_person_id": pupil.get(), "knowledge_kind": kind.get(), "knowledge_record_id": record_id, "knowledge_collection": record.get("collection", "")}
            self._background(lambda: self.client.request("POST", "/api/admin/teaching", payload), lambda _result: (dialog.destroy(), self.refresh(silent=True)))

        actions = ttk.Frame(shell)
        actions.pack(fill="x")
        ttk.Button(actions, text="Cancel", style="Quiet.TButton", command=dialog.destroy).pack(side="right")
        ttk.Button(actions, text="Teach", command=teach).pack(side="right", padx=(0, 6))

    def _open_known_teaching_dialog(
        self, actor: dict[str, Any], options: dict[str, Any],
    ) -> None:
        dialog = tk.Toplevel(self)
        dialog.title(f"Teach — {actor.get('name') or 'Character'}")
        dialog.transient(self)
        dialog.grab_set()
        dialog.geometry("920x620")
        dialog.minsize(760, 520)
        apply_window_icon(dialog, GAME_BOARD_ICON)
        shell = ttk.Frame(dialog, padding=10)
        shell.pack(fill="both", expand=True)
        teacher = options.get("teacher", {}) or {}
        ttk.Label(
            shell,
            text=f"{teacher.get('name') or actor.get('name') or 'Character'} is teaching",
            style="Section.TLabel",
        ).pack(anchor="w", pady=(0, 8))
        workspace = ttk.Panedwindow(shell, orient="horizontal")
        workspace.pack(fill="both", expand=True)
        pupil_side = ttk.Frame(workspace, padding=(0, 0, 8, 0))
        subject_side = ttk.Frame(workspace, padding=(8, 0, 0, 0))
        workspace.add(pupil_side, weight=2)
        workspace.add(subject_side, weight=5)

        ttk.Label(pupil_side, text="Pupil on this map", style="CardTitle.TLabel").pack(anchor="w")
        pupil_query = tk.StringVar()
        ttk.Entry(pupil_side, textvariable=pupil_query).pack(fill="x", pady=(4, 6))
        pupil_tree = ttk.Treeview(
            pupil_side, columns=("name",), show="headings", selectmode="browse"
        )
        pupil_tree.heading("name", text="Character")
        pupil_tree.column("name", minwidth=170, width=230, stretch=True)
        pupil_tree.pack(fill="both", expand=True)
        pupils = list(options.get("pupils", []) or [])

        def render_pupils(*_args: Any) -> None:
            term = pupil_query.get().strip().casefold()
            pupil_tree.delete(*pupil_tree.get_children())
            for item in pupils:
                if term and term not in str(item.get("name", "")).casefold():
                    continue
                pupil_tree.insert(
                    "", "end", iid=str(item["record_id"]),
                    values=(item.get("name", "Unknown"),),
                )

        pupil_query.trace_add("write", render_pupils)
        render_pupils()

        ttk.Label(subject_side, text="Known subject", style="CardTitle.TLabel").pack(anchor="w")
        kind = tk.StringVar(value="spell")
        query = tk.StringVar()
        skill_filter = tk.StringVar(value="All skills")
        source_filter = tk.StringVar(value="All sources")
        sort_mode = tk.StringVar(value="Name")
        kinds = ttk.Frame(subject_side)
        kinds.pack(fill="x", pady=(4, 5))
        filters = ttk.Frame(subject_side)
        filters.pack(fill="x", pady=(0, 5))
        search = ttk.Entry(filters, textvariable=query)
        search.pack(side="left", fill="x", expand=True)
        skill_box = ttk.Combobox(
            filters, textvariable=skill_filter, state="readonly", width=14
        )
        source_box = ttk.Combobox(
            filters, textvariable=source_filter, state="readonly", width=14
        )
        sort_box = ttk.Combobox(
            filters, textvariable=sort_mode, state="readonly", width=12,
            values=("Name", "Skill", "Difficulty", "Source"),
        )
        skill_box.pack(side="left", padx=(5, 0))
        source_box.pack(side="left", padx=(5, 0))
        sort_box.pack(side="left", padx=(5, 0))
        subject_tree = ttk.Treeview(
            subject_side,
            columns=("name", "skill", "difficulty", "source"),
            show="headings", selectmode="browse",
        )
        for column, title, width in (
            ("name", "Name", 235), ("skill", "Skill", 105),
            ("difficulty", "Difficulty", 72), ("source", "Source", 125),
        ):
            subject_tree.heading(column, text=title)
            subject_tree.column(
                column, width=width, minwidth=55,
                stretch=column in {"name", "source"},
            )
        subject_tree.pack(fill="both", expand=True)
        visible_subjects: dict[str, dict[str, Any]] = {}

        def records() -> list[dict[str, Any]]:
            selected = pupil_tree.selection()
            if not selected:
                return []
            pupil = next(
                (item for item in pupils if item.get("record_id") == selected[0]),
                {},
            )
            already_known = set((pupil.get("known") or {}).get(kind.get(), []))
            return [
                item for item in options.get(kind.get(), []) or []
                if str(item.get("record_id") or "") not in already_known
            ]

        def render_subjects(*_args: Any) -> None:
            term = query.get().strip().casefold()
            skill = skill_filter.get()
            source = source_filter.get()
            values = [item for item in records() if (
                (not term or term in " ".join(
                    str(item.get(field) or "")
                    for field in ("name", "skill", "source", "subtype", "description")
                ).casefold())
                and (skill == "All skills" or str(item.get("skill") or "") == skill)
                and (source == "All sources" or str(item.get("source") or "") == source)
            )]
            mode = sort_mode.get()
            if mode == "Difficulty":
                values.sort(key=lambda item: (
                    float(item.get("threshold") or 10**9),
                    str(item.get("name") or "").casefold(),
                ))
            else:
                field = {"Skill": "skill", "Source": "source"}.get(mode, "name")
                values.sort(key=lambda item: (
                    str(item.get(field) or "").casefold(),
                    str(item.get("name") or "").casefold(),
                ))
            subject_tree.delete(*subject_tree.get_children())
            visible_subjects.clear()
            for item in values[:1000]:
                record_id = str(item.get("record_id") or "")
                visible_subjects[record_id] = item
                subject_tree.insert("", "end", iid=record_id, values=(
                    item.get("name", "Unknown"), item.get("skill", ""),
                    item.get("threshold", ""), item.get("source", ""),
                ))

        def reset_filters() -> None:
            values = records()
            skills = sorted(
                {str(item.get("skill")) for item in values if item.get("skill")},
                key=str.casefold,
            )
            sources = sorted(
                {str(item.get("source")) for item in values if item.get("source")},
                key=str.casefold,
            )
            skill_box.configure(values=("All skills", *skills))
            source_box.configure(values=("All sources", *sources))
            skill_filter.set("All skills")
            source_filter.set("All sources")
            render_subjects()

        for value, label in (
            ("spell", "Spells"), ("proficiency", "Proficiencies"),
            ("recipe", "Recipes"),
        ):
            ttk.Radiobutton(
                kinds, text=label, variable=kind, value=value,
                command=reset_filters,
            ).pack(side="left", padx=(0, 16))
        query.trace_add("write", render_subjects)
        skill_box.bind("<<ComboboxSelected>>", render_subjects)
        source_box.bind("<<ComboboxSelected>>", render_subjects)
        sort_box.bind("<<ComboboxSelected>>", render_subjects)
        def pupil_changed(_event: tk.Event | None = None) -> None:
            subject_tree.selection_remove(subject_tree.selection())
            reset_filters()

        def clear_pupil_on_blank(event: tk.Event) -> None:
            if not pupil_tree.identify_row(event.y):
                pupil_tree.selection_remove(pupil_tree.selection())
                pupil_changed()

        pupil_tree.bind("<<TreeviewSelect>>", pupil_changed)
        pupil_tree.bind("<Button-1>", clear_pupil_on_blank, add="+")
        reset_filters()

        def teach() -> None:
            pupils_selected = pupil_tree.selection()
            subjects_selected = subject_tree.selection()
            record = visible_subjects.get(
                subjects_selected[0] if subjects_selected else ""
            )
            if not pupils_selected:
                messagebox.showinfo(
                    "Teach", "Choose a pupil who is on this map.", parent=dialog
                )
                return
            if record is None:
                messagebox.showinfo(
                    "Teach", "Choose a known subject.", parent=dialog
                )
                return
            request = {
                "session_id": self.selected_session_id,
                "teacher_person_id": str(actor.get("actor_id") or ""),
                "pupil_person_id": pupils_selected[0],
                "knowledge_kind": kind.get(),
                "knowledge_record_id": str(record.get("record_id") or ""),
                "knowledge_collection": str(record.get("collection") or ""),
            }
            self._background(
                lambda: self.client.request(
                    "POST", "/api/admin/teaching", request
                ),
                lambda _result: (dialog.destroy(), self.refresh(silent=True)),
            )

        actions = ttk.Frame(shell)
        actions.pack(fill="x", pady=(10, 0))
        ttk.Button(
            actions, text="Cancel", width=14, style="Quiet.TButton",
            command=dialog.destroy,
        ).pack(side="right", ipady=5)
        ttk.Button(
            actions, text="Teach selected", width=18, command=teach,
        ).pack(side="right", padx=(0, 8), ipady=5)
        search.focus_set()

    def transport_selected_actor(self) -> None:
        actor = self._selected_board_actor()
        maps = list(self.board_snapshot.get("maps", []))
        if not actor or not maps or not self.selected_session_id:
            messagebox.showinfo("Transport", "Select a character and campaign first.", parent=self)
            return
        dialog = tk.Toplevel(self)
        dialog.title(f"Transport {actor.get('name') or 'character'}")
        dialog.transient(self)
        dialog.grab_set()
        dialog.geometry("560x430")
        dialog.minsize(440, 320)
        apply_window_icon(dialog, GAME_BOARD_ICON)
        shell = ttk.Frame(dialog, padding=10)
        shell.pack(fill="both", expand=True)
        query = tk.StringVar()
        search = ttk.Entry(shell, textvariable=query)
        search.pack(fill="x", pady=(0, 6))
        results = tk.Listbox(
            shell,
            exportselection=False,
            background="#fff8e6",
            foreground=self.INK,
            selectbackground=self.ACCENT,
            selectforeground="#fff8e7",
        )
        results.pack(fill="both", expand=True)
        result_ids: list[str] = []
        current_map_id = str(actor.get("map_id", "") or "")

        def fill(*_args) -> None:
            matches = [
                item for item in self.fuzzy_board_maps(query.get(), limit=101)
                if str(item.get("record_id", "")) != current_map_id
            ][:100]
            results.delete(0, "end")
            result_ids[:] = [str(item.get("record_id")) for item in matches]
            for record in matches:
                results.insert("end", self._board_map_result_label(record))
            if result_ids:
                results.selection_set(0)

        def choose_warp(*_args) -> None:
            selection = results.curselection()
            if not selection or selection[0] >= len(result_ids):
                return
            map_id = result_ids[selection[0]]
            destination = next(
                (item for item in maps if str(item.get("record_id")) == map_id),
                None,
            )
            if destination is None:
                return
            warps = list(destination.get("warp_points", []) or [])
            if not warps:
                messagebox.showinfo(
                    "No warp points",
                    "This map has no warp points. Add one in Mapper before transporting a character here.",
                    parent=dialog,
                )
                return
            for child in shell.winfo_children():
                child.destroy()
            ttk.Label(
                shell,
                text=f"Arrival point on {destination.get('name') or 'destination'}",
                font=("Segoe UI", 10, "bold"),
            ).pack(anchor="w", pady=(0, 6))
            warp_list = tk.Listbox(
                shell,
                exportselection=False,
                background="#fff8e6",
                foreground=self.INK,
                selectbackground=self.ACCENT,
                selectforeground="#fff8e7",
            )
            warp_list.pack(fill="both", expand=True)
            for point in warps:
                suffix = " — Player arrival" if point.get("player_arrival") else ""
                warp_list.insert("end", f"{point.get('name') or 'Unnamed warp'}{suffix}")
            preferred = next(
                (index for index, point in enumerate(warps) if point.get("player_arrival")),
                0,
            )
            warp_list.selection_set(preferred)
            warp_list.activate(preferred)

            def transport(*_args) -> None:
                warp_selection = warp_list.curselection()
                if not warp_selection:
                    return
                warp = warps[warp_selection[0]]
                payload = {
                    "session_id": self.selected_session_id,
                    "person_id": actor["actor_id"],
                    "map_id": map_id,
                    "warp_point_id": str(warp.get("record_id", "")),
                }
                dialog.destroy()
                if str(actor.get("location_id")) == str(destination.get("location_id")):
                    self._background(
                        lambda: self.client.request("POST", "/api/admin/board/transport", payload),
                        lambda _result: self.refresh(silent=True),
                    )
                else:
                    self._choose_arrival_group(
                        actor,
                        destination,
                        payload,
                        move_path="/api/admin/board/transport",
                    )

            warp_list.bind("<Double-Button-1>", transport)
            warp_list.bind("<Return>", transport)
            warp_actions = ttk.Frame(shell)
            warp_actions.pack(fill="x", pady=(6, 0))
            ttk.Button(warp_actions, text="Cancel", style="Quiet.TButton", command=dialog.destroy).pack(side="right")
            ttk.Button(warp_actions, text="Transport", command=transport).pack(side="right", padx=(0, 5))
            warp_list.focus_set()

        query.trace_add("write", fill)
        results.bind("<Double-Button-1>", choose_warp)
        results.bind("<Return>", choose_warp)
        actions = ttk.Frame(shell)
        actions.pack(fill="x", pady=(6, 0))
        ttk.Button(actions, text="Cancel", style="Quiet.TButton", command=dialog.destroy).pack(side="right")
        ttk.Button(actions, text="Next", command=choose_warp).pack(side="right", padx=(0, 5))
        fill()
        search.focus_set()

    def _send_selected_actor_action(self, action: str, **values: Any) -> None:
        actor = self._selected_board_actor()
        if not actor or not self.selected_session_id:
            return
        payload = {"session_id": self.selected_session_id, "action": action, **values}
        self._background(
            lambda: self.client.request(
                "POST",
                f"/api/admin/board/people/{actor['actor_id']}/actions",
                payload,
            ),
            lambda _result: self.refresh(silent=True),
        )

    def add_selected_actor_wound(self) -> None:
        actor = self._selected_board_actor()
        if not actor:
            return
        dialog = tk.Toplevel(self)
        dialog.title(f"Wound — {actor.get('name') or 'Character'}")
        dialog.transient(self)
        dialog.grab_set()
        severity = tk.StringVar(value="light")
        row = ttk.Frame(dialog, padding=(10, 10, 10, 4))
        row.pack(fill="x")
        for value in ("light", "medium", "heavy"):
            ttk.Radiobutton(row, text=value.title(), value=value, variable=severity).pack(side="left", padx=(0, 10))
        ttk.Label(dialog, text="Optional note", padding=(10, 4, 10, 2)).pack(anchor="w")
        note = ttk.Entry(dialog)
        note.pack(fill="x", padx=10)
        ttk.Button(
            dialog,
            text="Add wound",
            command=lambda: (
                self._send_selected_actor_action(
                    "add_wound", severity=severity.get(), text=note.get().strip()
                ),
                dialog.destroy(),
            ),
        ).pack(pady=10)

    def toggle_selected_actor_battle(self) -> None:
        actor = self._selected_board_actor()
        if not actor:
            return
        if actor.get("battle"):
            if messagebox.askyesno(
                "Battle",
                f"Remove {actor.get('name') or 'this character'} from the current battle?",
                parent=self,
            ):
                self._send_selected_actor_action("leave_battle")
            return
        name = simpledialog.askstring(
            "Enter battle",
            "Battle name:",
            initialvalue="Battle",
            parent=self,
        )
        if name is not None:
            self._send_selected_actor_action("enter_battle", battle_name=name.strip() or "Battle")

    def add_selected_actor_note(self) -> None:
        actor = self._selected_board_actor()
        if not actor:
            return
        dialog = tk.Toplevel(self)
        dialog.title(f"Character Note — {actor.get('name') or 'Character'}")
        dialog.transient(self)
        dialog.grab_set()
        dialog.geometry("480x260")
        editor = tk.Text(dialog, wrap="word", padx=8, pady=8)
        editor.pack(fill="both", expand=True, padx=10, pady=(10, 5))

        def save() -> None:
            text = editor.get("1.0", "end").strip()
            if not text:
                return
            self._send_selected_actor_action("add_note", text=text)
            dialog.destroy()

        actions = ttk.Frame(dialog, padding=(10, 5, 10, 10))
        actions.pack(fill="x")
        ttk.Button(actions, text="Cancel", style="Quiet.TButton", command=dialog.destroy).pack(side="right")
        ttk.Button(actions, text="Add note", command=save).pack(side="right", padx=(0, 5))
        editor.focus_set()

    def adjust_selected_actor_currency(self) -> None:
        actor = self._selected_board_actor()
        if actor is None:
            return
        change = simpledialog.askinteger(
            "Wizarding currency",
            (
                f"Knut adjustment for {actor.get('name') or 'this character'}:\n"
                "Use a positive amount to add money or a negative amount to remove it."
            ),
            initialvalue=0,
            minvalue=-2_147_483_647,
            maxvalue=2_147_483_647,
            parent=self,
        )
        if change is None or change == 0:
            return
        payload = {
            "session_id": self.selected_session_id,
            "change_knuts": int(change),
        }
        self._background(
            lambda: self.client.request(
                "POST",
                f"/api/admin/board/people/{actor['actor_id']}/currency-adjustment",
                payload,
            ),
            lambda _result: self.refresh(silent=True),
        )

    def _render_board_actor_list(self) -> None:
        frame = getattr(self, "board_actor_rows_frame", None)
        if frame is None or not frame.winfo_exists():
            return
        search_value = self.board_actor_search_var.get() if hasattr(self, "board_actor_search_var") else ""
        query = str(search_value or "").strip().casefold()
        actors = [
            actor for actor in self.board_snapshot.get("actors", [])
            if actor.get("map_id") == self.selected_board_map_id
            and actor.get("actor_type", "person") == "person"
            and (not query or query in str(actor.get("name") or "Unknown").casefold())
        ]
        actors.sort(key=lambda actor: str(actor.get("name") or "Unknown").casefold())
        signature = (
            self.selected_board_map_id,
            self.selected_board_actor_id,
            query,
            tuple((
                str(actor.get("actor_id") or ""),
                str(actor.get("name") or "Unknown"),
                str(actor.get("faction_id") or ""),
                str(actor.get("faction_color") or ""),
                bool(actor.get("faction_revealed")),
                str(actor.get("group_id") or ""),
                str(actor.get("group_color") or ""),
                str(actor.get("visibility") or ""),
                str(actor.get("display_mode") or ""),
                bool(actor.get("name_revealed")),
            ) for actor in actors),
        )
        if signature == self._board_actor_list_signature:
            return
        self._board_actor_list_signature = signature
        previous_y = self.board_actor_rows_canvas.yview()[0]
        for child in frame.winfo_children():
            child.destroy()
        for row_index, actor in enumerate(actors):
            actor_id = str(actor.get("actor_id"))
            row = tk.Frame(
                frame,
                background="#ead8aa" if actor_id == self.selected_board_actor_id else "#fff8e6",
                highlightbackground=self.EDGE,
                highlightthickness=0 if row_index == 0 else 1,
            )
            row.pack(fill="x")
            row.bind(
                "<Button-3>",
                lambda event, value=actor_id: self._open_actor_row_menu(event, value),
            )
            row.bind(
                "<Control-Button-1>",
                lambda event, value=actor_id: self._open_actor_row_menu(event, value),
            )
            name_button = tk.Button(
                row, text=str(actor.get("name") or "Unknown"), anchor="w",
                background=row.cget("background"), activebackground="#ead8aa",
                foreground=self.INK, relief="flat", borderwidth=0,
                font=("Segoe UI", 8, "bold"), padx=3, pady=2,
                command=lambda value=actor_id: self._select_board_actor(value),
            )
            name_button.pack(side="left", fill="x", expand=True)
            name_button.bind(
                "<Button-3>",
                lambda event, value=actor_id: self._open_actor_row_menu(event, value),
            )
            name_button.bind(
                "<Control-Button-1>",
                lambda event, value=actor_id: self._open_actor_row_menu(event, value),
            )
            faction_help = "Conceal faction" if actor.get("faction_revealed") else "Reveal faction"
            character_help = "Conceal character" if actor.get("visibility") == "players" else "Reveal character"
            name_help = "Conceal name" if actor.get("name_revealed") else "Reveal name"
            controls = (
                ("⚑", lambda value=actor_id: self._actor_row_action(value, self.select_actor_faction), "Choose or create a faction", actor.get("faction_color") if actor.get("faction_id") else "#d8c9a1"),
                ("F" if actor.get("faction_revealed") else "f", lambda value=actor_id: self._actor_row_action(value, self.toggle_selected_faction), faction_help, "#4d6b43" if actor.get("faction_revealed") else "#d8c9a1"),
                ("G", lambda value=actor_id: self._actor_row_action(value, self.manage_actor_group), "Choose or create a colored group", actor.get("group_color") if actor.get("group_id") else "#d8c9a1"),
                ("◉" if actor.get("visibility") == "players" else "○", lambda value=actor_id, current=actor.get("visibility"): self._actor_row_update(value, visibility="headmaster" if current == "players" else "players"), character_help, "#4d6b43" if actor.get("visibility") == "players" else "#d8c9a1"),
                ("▣" if actor.get("display_mode") == "token" else "●", lambda value=actor_id, current=actor.get("display_mode"): self._actor_row_update(value, display_mode="dot" if current == "token" else "token"), "Toggle dot or portrait token", "#4d6b43" if actor.get("display_mode") == "token" else "#d8c9a1"),
                ("N" if actor.get("name_revealed") else "n", lambda value=actor_id: self._actor_row_action(value, self.toggle_selected_name), name_help, "#4d6b43" if actor.get("name_revealed") else "#d8c9a1"),
            )
            for text, command, help_text, button_color in controls:
                button = tk.Button(
                    row, text=text, width=2, command=command,
                    background=str(button_color or "#d8c9a1"),
                    activebackground="#ead8aa", foreground=self.INK,
                    relief="flat", borderwidth=0, font=("Segoe UI", 8, "bold"), padx=1, pady=2,
                )
                button.pack(side="left", padx=(1, 0))
                self._attach_tooltip(button, help_text)
        frame.update_idletasks()
        self.board_actor_rows_canvas.configure(
            scrollregion=self.board_actor_rows_canvas.bbox("all")
        )
        self.board_actor_rows_canvas.yview_moveto(previous_y)

    def _open_actor_row_menu(self, event: tk.Event, actor_id: str) -> str:
        self.selected_board_actor_id = actor_id
        self._render_board_actor_list()
        self._draw_board_map(self.selected_board_map_id)
        self._open_piece_controls(event.widget, event.x_root, event.y_root)
        return "break"

    def _select_board_actor(self, actor_id: str) -> None:
        self.selected_board_actor_id = actor_id
        self._render_board_actor_list()
        self._draw_board_map(self.selected_board_map_id)

    def _actor_row_action(self, actor_id: str, command: Callable[[], None]) -> None:
        self.selected_board_actor_id = actor_id
        command()

    def _actor_row_update(self, actor_id: str, **updates: Any) -> None:
        self.selected_board_actor_id = actor_id
        self.update_selected_actor(**updates)

    def _board_actor_selected(self, _event: tk.Event | None = None) -> None:
        tree = self.board_actor_tree
        if tree is None or not tree.winfo_exists():
            return
        selected = tree.selection()
        if selected:
            self.selected_board_actor_id = selected[0]
            self._draw_board_map(self.selected_board_map_id)

    def _selected_board_actor(self) -> dict[str, Any] | None:
        return next((item for item in self.board_snapshot.get("actors", []) if item.get("actor_id") == self.selected_board_actor_id), None)

    def update_selected_actor(self, **updates: Any) -> None:
        if not self.selected_board_actor_id:
            messagebox.showinfo("Board", "Select a character first.", parent=self)
            return
        payload = {"session_id": self.selected_session_id, **updates}
        self._background(
            lambda: self.client.request("PUT", f"/api/admin/board/people/{self.selected_board_actor_id}", payload),
            lambda _result: self.refresh(silent=True),
        )

    def toggle_selected_name(self) -> None:
        actor = self._selected_board_actor()
        if actor:
            self.update_selected_actor(name_revealed=not bool(actor.get("name_revealed")))

    def adjust_selected_nameplate_size(self, change: float) -> None:
        actor = self._selected_board_actor()
        if actor is None:
            return
        scale = max(
            0.5,
            min(3.0, round(float(actor.get("nameplate_scale", 1.0) or 1.0) + change, 2)),
        )
        self.update_selected_actor(nameplate_scale=scale)

    def toggle_selected_faction(self) -> None:
        actor = self._selected_board_actor()
        if actor:
            self.update_selected_actor(faction_revealed=not bool(actor.get("faction_revealed")))

    def select_actor_faction(self) -> None:
        actor = self._selected_board_actor()
        if not actor:
            messagebox.showinfo("Board", "Select a character first.", parent=self)
            return
        choices = list(self.board_snapshot.get("factions", []))
        chooser = tk.Toplevel(self)
        chooser.title("Displayed faction")
        chooser.transient(self)
        chooser.grab_set()
        chooser.geometry("440x470")
        apply_window_icon(chooser, GAME_BOARD_ICON)
        ttk.Label(chooser, text="Faction", style="Title.TLabel", padding=(12, 10, 12, 3)).pack(anchor="w")
        query = tk.StringVar()
        search = ttk.Entry(chooser, textvariable=query)
        search.pack(fill="x", padx=12, pady=(0, 6))
        choice_ids = [str(item.get("organization_id")) for item in choices]
        value = tk.StringVar(value=str(actor.get("faction_id") or (choice_ids[0] if choice_ids else "")))
        results = ttk.Frame(chooser)
        results.pack(fill="both", expand=True, padx=12)

        def render(*_args: Any) -> None:
            for child in results.winfo_children():
                child.destroy()
            needle = query.get().strip().casefold()
            for faction in choices:
                name = str(faction.get("name") or faction.get("organization_id"))
                if needle and needle not in name.casefold():
                    continue
                row = ttk.Frame(results)
                row.pack(fill="x", pady=1)
                tk.Label(row, background=str(faction.get("color") or "#808080"), width=2).pack(side="left", fill="y")
                ttk.Radiobutton(
                    row, text=name, value=str(faction.get("organization_id")), variable=value
                ).pack(side="left", fill="x", expand=True)
                edit = ttk.Button(
                    row,
                    text="Color…",
                    width=7,
                    style="Quiet.TButton",
                    command=lambda selected=faction: edit_faction_color(selected),
                )
                edit.pack(side="right", padx=(4, 0))

        def edit_faction_color(faction: dict[str, Any]) -> None:
            current_color = str(faction.get("color") or "#808080")
            selected = colorchooser.askcolor(current_color, parent=chooser)[1]
            if not selected:
                return
            faction["color"] = selected.lower()
            self._background(
                lambda: self.client.request(
                    "PUT",
                    f"/api/admin/board/factions/{faction.get('organization_id')}",
                    {
                    "session_id": self.selected_session_id,
                    "color": selected.lower(),
                    },
                ),
                lambda _result: self.refresh(silent=True),
            )
            render()

        query.trace_add("write", render)
        render()
        create = ttk.LabelFrame(chooser, text="Create and join", padding=8)
        create.pack(fill="x", padx=12, pady=6)
        new_name = ttk.Entry(create)
        new_name.pack(side="left", fill="x", expand=True)
        color_value = tk.StringVar(value="#808080")
        color_button = tk.Button(create, text="■", width=3, background=color_value.get())
        color_button.pack(side="left", padx=4)

        def choose_color() -> None:
            selected = colorchooser.askcolor(color_value.get(), parent=chooser)[1]
            if selected:
                color_value.set(selected.lower())
                color_button.configure(background=selected)

        color_button.configure(command=choose_color)

        def create_faction() -> None:
            name = new_name.get().strip()
            if not name:
                return
            self._background(
                lambda: self.client.request("POST", "/api/admin/board/factions", {
                    "session_id": self.selected_session_id,
                    "person_id": actor["actor_id"],
                    "name": name,
                    "color": color_value.get(),
                }),
                lambda _result: self.refresh(silent=True),
            )
            chooser.destroy()

        ttk.Button(create, text="+", width=3, command=create_faction).pack(side="left")
        actions = ttk.Frame(chooser, padding=(12, 0, 12, 12))
        actions.pack(fill="x")
        ttk.Button(actions, text="Cancel", style="Quiet.TButton", command=chooser.destroy).pack(side="right")

        def use_faction() -> None:
            faction_id = value.get()
            faction = next(
                (item for item in choices if str(item.get("organization_id")) == faction_id),
                None,
            )
            if faction is None:
                return
            self._background(
                lambda: self.client.request("POST", "/api/admin/board/factions", {
                    "session_id": self.selected_session_id,
                    "person_id": actor["actor_id"],
                    "name": str(faction.get("name") or faction_id),
                    "color": str(faction.get("color") or "#808080"),
                }),
                lambda _result: self.refresh(silent=True),
            )
            chooser.destroy()

        ttk.Button(
            actions, text="Use faction",
            command=use_faction,
        ).pack(side="right", padx=(0, 5))
        search.focus_set()

    def transfer_selected_actor(self) -> None:
        actor = self._selected_board_actor()
        if self.board_transfer_map is None or not self.board_transfer_map.winfo_exists():
            return
        label = self.board_transfer_map.get()
        map_id = self.board_map_label_to_id.get(label, "")
        record = next((item for item in self.board_snapshot.get("maps", []) if str(item.get("record_id")) == map_id), None)
        if not actor or not record or not self.selected_session_id:
            messagebox.showinfo("Board", "Select a character and destination map.", parent=self)
            return
        payload = {"session_id": self.selected_session_id, "person_id": actor["actor_id"], "map_id": record["record_id"], "x": 0.5, "y": 0.5}
        if str(actor.get("location_id")) == str(record.get("location_id")):
            self._background(lambda: self.client.request("POST", "/api/admin/board/move", payload), lambda _result: self.refresh(silent=True))
            return
        self._choose_arrival_group(actor, record, payload)

    def _choose_arrival_group(
        self,
        actor: dict[str, Any],
        destination: dict[str, Any],
        move_payload: dict[str, Any],
        *,
        move_path: str = "/api/admin/board/move",
    ) -> None:
        location_id = str(destination.get("location_id"))
        groups = [group for group in self.board_snapshot.get("groups", []) if str(group.get("location_id")) == location_id]
        occupants = [
            item for item in self.board_snapshot.get("actors", [])
            if str(item.get("location_id")) == location_id and item.get("actor_id") != actor.get("actor_id")
        ]
        if not groups and not occupants:
            self._background(lambda: self.client.request("POST", move_path, move_payload), lambda _result: self.refresh(silent=True))
            return
        dialog = tk.Toplevel(self)
        dialog.title("Arrival at a new location")
        dialog.transient(self)
        dialog.grab_set()
        ttk.Label(dialog, text="How should this character arrive?", padding=10).pack(anchor="w")
        choice = tk.StringVar(value="solo")
        ttk.Radiobutton(dialog, text="Remain solo", variable=choice, value="solo").pack(anchor="w", padx=10, pady=2)
        for group in groups:
            ttk.Radiobutton(dialog, text=f"Join {group.get('name', 'group')}", variable=choice, value=f"group:{group['record_id']}").pack(anchor="w", padx=10, pady=2)
        for occupant in occupants:
            ttk.Radiobutton(dialog, text=f"Create a group with {occupant.get('name', 'occupant')}", variable=choice, value=f"create:{occupant['actor_id']}").pack(anchor="w", padx=10, pady=2)
        def apply() -> None:
            selected = choice.get()
            def work() -> None:
                self.client.request("POST", move_path, move_payload)
                if selected.startswith("group:"):
                    self.client.request("PUT", f"/api/admin/board/groups/people/{actor['actor_id']}", {
                        "session_id": self.selected_session_id,
                        "group_id": selected.split(':', 1)[1],
                    })
                elif selected.startswith("create:"):
                    self.client.request("POST", "/api/admin/board/groups", {
                        "session_id": self.selected_session_id,
                        "name": f"{actor.get('name', 'New')} group",
                        "location_id": location_id,
                        "person_ids": [actor["actor_id"], selected.split(':', 1)[1]],
                    })
            self._background(work, lambda _result: self.refresh(silent=True))
            dialog.destroy()
        ttk.Button(dialog, text="Move", command=apply).pack(pady=10)

    def grant_actor_control(self) -> None:
        actor = self._selected_board_actor()
        session = next((item for item in self.state_data.get("sessions", []) if item.get("id") == self.selected_session_id), None)
        if not actor or not session:
            messagebox.showinfo("Board", "Select a character and active session.", parent=self)
            return
        roster = session.get("roster", [])
        if not roster:
            return
        chooser = tk.Toplevel(self)
        chooser.title("Grant token control")
        chooser.transient(self)
        chooser.grab_set()
        ttk.Label(chooser, text="Player", padding=10).pack(anchor="w")
        labels = [player["name"] for player in roster]
        value = tk.StringVar(value=labels[0])
        box = ttk.Combobox(chooser, state="readonly", values=labels, textvariable=value)
        box.pack(fill="x", padx=10)
        def apply(granted: bool) -> None:
            player = roster[labels.index(value.get())]
            payload = {"session_id": session["id"], "contact_id": player["contact_id"], "person_id": actor["actor_id"], "granted": granted}
            self._background(lambda: self.client.request("PUT", "/api/admin/board/control", payload), lambda _result: self.refresh(silent=True))
            chooser.destroy()
        row = ttk.Frame(chooser, padding=10)
        row.pack(fill="x")
        ttk.Button(row, text="Grant", style="Good.TButton", command=lambda: apply(True)).pack(side="left")
        ttk.Button(row, text="Revoke", style="Danger.TButton", command=lambda: apply(False)).pack(side="right")

    def create_board_group(self) -> None:
        actors = [item for item in self.board_snapshot.get("actors", []) if item.get("map_id") == self.selected_board_map_id]
        if not actors:
            messagebox.showinfo("Groups", "Add a character to this map first.", parent=self)
            return
        dialog = tk.Toplevel(self)
        dialog.title("Create board group")
        dialog.transient(self)
        dialog.grab_set()
        ttk.Label(dialog, text="Group name", padding=(10, 10, 10, 2)).pack(anchor="w")
        name = ttk.Entry(dialog)
        name.pack(fill="x", padx=10)
        name.insert(0, "Party")
        color_value = tk.StringVar(value="#d6ad52")
        color_row = ttk.Frame(dialog, padding=(10, 6, 10, 2))
        color_row.pack(fill="x")
        ttk.Label(color_row, text="Plaque color").pack(side="left")
        color_button = tk.Button(
            color_row,
            textvariable=color_value,
            background=color_value.get(),
            width=10,
        )
        color_button.pack(side="right")

        def choose_color() -> None:
            selected = colorchooser.askcolor(color_value.get(), parent=dialog)[1]
            if selected:
                color_value.set(selected.lower())
                color_button.configure(background=selected)

        color_button.configure(command=choose_color)
        values: dict[str, tk.BooleanVar] = {}
        for actor in actors:
            variable = tk.BooleanVar(value=actor.get("actor_id") == self.selected_board_actor_id)
            values[str(actor["actor_id"])] = variable
            ttk.Checkbutton(dialog, text=str(actor.get("name") or "Unknown"), variable=variable).pack(anchor="w", padx=10, pady=2)
        def save() -> None:
            person_ids = [actor_id for actor_id, variable in values.items() if variable.get()]
            current_map = self._current_board_map()
            if not person_ids or not current_map:
                messagebox.showerror("Groups", "Choose at least one character.", parent=dialog)
                return
            payload = {
                "session_id": self.selected_session_id,
                "name": name.get().strip() or "Group",
                "location_id": current_map["location_id"],
                "person_ids": person_ids,
                "color": color_value.get(),
            }
            self._background(lambda: self.client.request("POST", "/api/admin/board/groups", payload), lambda _result: self.refresh(silent=True))
            dialog.destroy()
        ttk.Button(dialog, text="Create group", command=save).pack(pady=10)

    def manage_actor_group(self) -> None:
        actor = self._selected_board_actor()
        if not actor:
            messagebox.showinfo("Groups", "Select a character first.", parent=self)
            return
        groups = [
            group for group in self.board_snapshot.get("groups", [])
            if str(group.get("location_id")) == str(actor.get("location_id"))
        ]
        dialog = tk.Toplevel(self)
        dialog.title("Choose or Create Group")
        dialog.transient(self)
        dialog.grab_set()
        dialog.geometry("440x460")
        dialog.minsize(360, 360)
        apply_window_icon(dialog, GAME_BOARD_ICON)
        value = tk.StringVar(value="")
        current = ""
        for group in groups:
            if any(member.get("actor_id") == actor.get("actor_id") for member in group.get("members", [])):
                current = str(group.get("record_id"))
                break
        value.set(current)
        body = ttk.Frame(dialog, padding=12)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Group", style="Title.TLabel").pack(anchor="w")
        query = tk.StringVar()
        search = ttk.Entry(body, textvariable=query)
        search.pack(fill="x", pady=(5, 5))
        self._attach_tooltip(search, "Search groups at this location")
        results = ttk.Frame(body)
        results.pack(fill="both", expand=True)

        def render(*_args: Any) -> None:
            for child in results.winfo_children():
                child.destroy()
            ttk.Radiobutton(
                results, text="Remain solo", variable=value, value=""
            ).pack(fill="x", anchor="w", pady=1)
            needle = query.get().strip().casefold()
            for group in groups:
                name = str(group.get("name") or "Group")
                if needle and needle not in name.casefold():
                    continue
                row = ttk.Frame(results)
                row.pack(fill="x", pady=1)
                tk.Label(
                    row, background=str(group.get("color") or "#b0b0b0"), width=2
                ).pack(side="left", fill="y")
                ttk.Radiobutton(
                    row, text=name, variable=value, value=str(group.get("record_id"))
                ).pack(side="left", fill="x", expand=True)

        query.trace_add("write", render)
        render()

        create = ttk.LabelFrame(body, text="New group", padding=6)
        create.pack(fill="x", pady=(6, 0))
        new_name = ttk.Entry(create)
        new_name.insert(0, "Party")
        new_name.pack(side="left", fill="x", expand=True)
        color_value = tk.StringVar(value="#d6ad52")
        color_button = tk.Button(create, text="■", width=3, background=color_value.get())
        color_button.pack(side="left", padx=4)

        def choose_color() -> None:
            selected = colorchooser.askcolor(color_value.get(), parent=dialog)[1]
            if selected:
                color_value.set(selected.lower())
                color_button.configure(background=selected)

        color_button.configure(command=choose_color)

        def create_group() -> None:
            name = new_name.get().strip()
            if not name:
                return
            payload = {
                "session_id": self.selected_session_id,
                "name": name,
                "location_id": actor.get("location_id"),
                "person_ids": [actor["actor_id"]],
                "color": color_value.get(),
            }
            self._background(
                lambda: self.client.request("POST", "/api/admin/board/groups", payload),
                lambda _result: self.refresh(silent=True),
            )
            dialog.destroy()

        ttk.Button(create, text="+", width=3, command=create_group).pack(side="left")

        def save() -> None:
            self._background(
                lambda: self.client.request("PUT", f"/api/admin/board/groups/people/{actor['actor_id']}", {
                    "session_id": self.selected_session_id,
                    "group_id": value.get() or None,
                }),
                lambda _result: self.refresh(silent=True),
            )
            dialog.destroy()
        actions = ttk.Frame(body)
        actions.pack(fill="x", pady=(8, 0))
        ttk.Button(actions, text="Cancel", style="Quiet.TButton", command=dialog.destroy).pack(side="right")
        ttk.Button(actions, text="Use group", command=save).pack(side="right", padx=(0, 5))
        search.focus_set()

    def _build_game_clock(self, parent: tk.Misc) -> None:
        shell = tk.Frame(
            parent,
            background=self.EDGE,
            highlightbackground=self.ACCENT,
            highlightthickness=1,
        )
        shell.pack(side="right", anchor="n")
        self.game_clock_buttons: list[tk.Button] = []

        def add_button(text: str, command: Callable[[], None] | None = None) -> tk.Button:
            button = tk.Button(
                shell,
                text=text,
                width=max(2, len(text)),
                background=self.LIGHT,
                activebackground=self.PAPER,
                foreground=self.INK,
                activeforeground=self.INK,
                relief="flat",
                borderwidth=0,
                font=("Consolas", 9, "bold"),
                padx=2,
                pady=5,
                command=command,
            )
            button.pack(side="left", padx=(0, 1))
            self.game_clock_buttons.append(button)
            return button

        add_button("<<<", lambda: self.shift_game_clock(years=-1))
        add_button("<<", lambda: self.shift_game_clock(months=-1))
        add_button("<", lambda: self.shift_game_clock(days=-1))
        hour_back = add_button("hh")
        minute_back = add_button("mm")
        self.game_clock_value = tk.StringVar(value="Select a session")
        tk.Label(
            shell,
            textvariable=self.game_clock_value,
            background="#fff8e6",
            foreground=self.INK,
            font=("Consolas", 10, "bold"),
            padx=6,
            pady=6,
        ).pack(side="left", padx=(0, 1))
        minute_forward = add_button("mm")
        hour_forward = add_button("hh")
        add_button(">", lambda: self.shift_game_clock(days=1))
        add_button(">>", lambda: self.shift_game_clock(months=1))
        add_button(">>>", lambda: self.shift_game_clock(years=1))
        tk.Button(
            shell,
            text="●",
            width=2,
            background=self.GREEN,
            activebackground="#31553a",
            foreground="white",
            activeforeground="white",
            relief="flat",
            borderwidth=0,
            font=("Segoe UI", 8, "bold"),
            padx=3,
            pady=5,
            command=self.focus_players_on_current_view,
        ).pack(side="left", padx=(3, 0))
        tk.Button(
            shell,
            text="⛶",
            width=2,
            background=self.LIGHT,
            activebackground=self.PAPER,
            foreground=self.INK,
            activeforeground=self.INK,
            relief="flat",
            borderwidth=0,
            font=("Segoe UI Symbol", 9, "bold"),
            padx=3,
            pady=5,
            command=self.fit_current_board_map,
        ).pack(side="left", padx=(1, 0))
        hour_back.configure(
            command=lambda widget=hour_back: self.open_time_popup(widget, "hour", -1)
        )
        minute_back.configure(
            command=lambda widget=minute_back: self.open_time_popup(widget, "minute", -1)
        )
        minute_forward.configure(
            command=lambda widget=minute_forward: self.open_time_popup(widget, "minute", 1)
        )
        hour_forward.configure(
            command=lambda widget=hour_forward: self.open_time_popup(widget, "hour", 1)
        )

    def _build_headmaster_tool_rail(self, parent: tk.Misc) -> None:
        """Build a Photoshop-style tool strip that does not navigate the workspace."""

        rail = tk.Frame(
            parent,
            width=50,
            background=self.ACCENT,
            highlightbackground=self.ACCENT,
            highlightthickness=1,
        )
        self.headmaster_tool_rail = rail
        rail.pack(side="left", fill="y", padx=(0, 8))
        rail.pack_propagate(False)
        tk.Label(
            rail,
            text="TOOLS",
            background=self.ACCENT,
            foreground="#fff8e7",
            font=("Segoe UI", 7, "bold"),
            pady=8,
        ).pack(fill="x")
        self.headmaster_tool_buttons: dict[str, tk.Button] = {}
        tools = (
            ("groups", "●", "Characters"),
            ("creatures", "◆", "Creatures"),
            ("obfuscation-tools", "▧", "Obfuscation"),
            ("token-tools", "◉", "Tokens & Zoom"),
            ("secrets", "✦", "Secrets"),
            ("roll", "⚄", "Roll"),
            ("target", "⌖", "Target"),
            ("marker", "◎", "Marker"),
        )
        for key, symbol, label in tools:
            button = tk.Button(
                rail,
                text=symbol,
                background=self.ACCENT,
                activebackground=self.EDGE,
                foreground="#fff8e7",
                activeforeground=self.INK,
                relief="flat",
                borderwidth=0,
                font=("Segoe UI Symbol", 16),
                padx=4,
                pady=8,
                cursor="hand2",
                command=lambda selected=key, name=label: self.select_headmaster_tool(selected, name),
            )
            button.pack(fill="x", pady=(0, 1))
            self.headmaster_tool_buttons[key] = button
        self._build_headmaster_tools_drawer(parent)
        self.select_headmaster_tool("groups", "Characters")

    def _build_headmaster_tools_drawer(self, parent: tk.Misc) -> None:
        """Build the expandable drawer immediately beside the tool rail."""

        drawer = tk.Frame(
            parent,
            width=self.headmaster_tool_widths["groups"],
            background=self.LIGHT,
            highlightbackground=self.ACCENT,
            highlightthickness=1,
        )
        self.headmaster_tools_drawer = drawer
        drawer.pack_propagate(False)

        header = tk.Frame(drawer, background=self.EDGE, height=34)
        header.pack(fill="x")
        header.pack_propagate(False)
        self.headmaster_tool_title = tk.StringVar(value="Characters")
        tk.Label(
            header,
            textvariable=self.headmaster_tool_title,
            anchor="w",
            background=self.EDGE,
            foreground=self.INK,
            font=("Segoe UI", 9, "bold"),
            padx=8,
        ).pack(side="left", fill="both", expand=True)
        collapse = tk.Button(
            header,
            text="‹",
            width=3,
            background=self.EDGE,
            activebackground=self.PAPER,
            foreground=self.INK,
            activeforeground=self.INK,
            relief="flat",
            borderwidth=0,
            font=("Segoe UI Symbol", 11, "bold"),
            cursor="hand2",
            command=self.collapse_headmaster_tools,
        )
        collapse.pack(side="right", fill="y")
        self._attach_tooltip(collapse, "Collapse the Headmaster tool drawer")

        self.board_tools_host = tk.Frame(drawer, background=self.LIGHT)
        self.board_tools_host.pack(fill="both", expand=True)
        self.board_tools_canvas = tk.Canvas(
            self.board_tools_host,
            background=self.LIGHT,
            borderwidth=0,
            highlightthickness=0,
        )
        tools_scroll = ttk.Scrollbar(
            self.board_tools_host,
            orient="vertical",
            command=self.board_tools_canvas.yview,
        )
        self.board_tools_canvas.configure(yscrollcommand=tools_scroll.set)
        self.board_tools_canvas.pack(side="left", fill="both", expand=True)
        tools_scroll.pack(side="right", fill="y")
        self.board_tools_content = ttk.Frame(
            self.board_tools_canvas, style="Card.TFrame"
        )
        self._board_tools_window = self.board_tools_canvas.create_window(
            (0, 0), window=self.board_tools_content, anchor="nw"
        )
        self.board_tools_content.bind("<Configure>", self._resize_board_tools_scroll)
        self.board_tools_canvas.bind("<Configure>", self._resize_board_tools_scroll)
        self._create_board_map_controls(self.board_tools_content)
        self._create_board_token_controls(self.board_tools_content)
        self._create_board_groups_controls(self.board_tools_content)
        self._create_board_creature_controls(self.board_tools_content)
        self._create_board_secret_controls(self.board_tools_content)

    def collapse_headmaster_tools(self) -> None:
        self.headmaster_tools_collapsed = True
        if self.headmaster_tools_drawer.winfo_manager():
            self.headmaster_tools_drawer.place_forget()

    def _position_headmaster_tools_drawer(self) -> None:
        """Overlay the drawer on the board without changing the map layout."""

        sidebar_width = int(self.section_sidebar.cget("width"))
        rail_width = int(self.headmaster_tool_rail.cget("width"))
        width = self.headmaster_tool_widths.get(self.active_headmaster_tool, 340)
        self.headmaster_tools_drawer.configure(width=width)
        self.headmaster_tools_drawer.place(
            x=sidebar_width + rail_width + 16,
            y=0,
            width=width,
            relheight=1.0,
        )
        self.headmaster_tools_drawer.lift()

    def _open_headmaster_tools_drawer(self) -> None:
        self.headmaster_tools_collapsed = False
        drawer = self.headmaster_tools_drawer
        self._position_headmaster_tools_drawer()

    def select_headmaster_tool(self, key: str, label: str) -> None:
        """Select a future quick tool without changing the visible app panel."""

        for tool_key, button in self.headmaster_tool_buttons.items():
            active = tool_key == key
            button.configure(
                background=self.EDGE if active else self.ACCENT,
                foreground=self.INK if active else "#fff8e7",
            )
        self.active_headmaster_tool = key
        self.headmaster_tool_title.set(label)
        self._open_headmaster_tools_drawer()
        if key == "groups":
            self.open_board_groups()
            if hasattr(self, "notice"):
                self.set_notice("Group controls opened")
            return
        if key == "creatures":
            self.show_board_tools_panel("creatures")
            self._render_board_creature_list()
            if hasattr(self, "notice"):
                self.set_notice("Creature encounter controls opened")
            return
        if key == "obfuscation-tools":
            self.open_board_map_controls()
            if hasattr(self, "notice"):
                self.set_notice("Obfuscation controls opened")
            return
        if key == "token-tools":
            self.show_board_tools_panel("token-tools")
            if hasattr(self, "notice"):
                self.set_notice("Token and zoom controls opened")
            return
        if key == "secrets":
            self.show_board_tools_panel("secrets")
            self._refresh_board_secret_list()
            if hasattr(self, "notice"):
                self.set_notice("Secret visibility controls opened")
            return
        if key == "board-settings":
            self.open_board_settings()
            if hasattr(self, "notice"):
                self.set_notice("Game Board Settings opened")
            return
        if hasattr(self, "notice"):
            self.set_notice(f"{label} tool selected — controls coming soon")

    def _current_game_datetime(self) -> GameDateTime | None:
        session = self._selected_session()
        if not session:
            return None
        raw = session.get("game_datetime")
        if not raw:
            fallback = session.get("event_date") or session.get("game_day")
            raw = f"{fallback or date.today().isoformat()}T08:00"
        try:
            return parse_game_datetime(str(raw))
        except ValueError:
            return None

    def _render_game_clock(self, session: dict[str, Any] | None) -> None:
        current = self._current_game_datetime() if session else None
        self.game_clock_value.set(
            format_game_datetime(current) if current else "Select a session"
        )
        state = "normal" if current else "disabled"
        for button in self.game_clock_buttons:
            button.configure(state=state)

    def set_game_clock(self, value: GameDateTime) -> None:
        session = self._selected_session()
        if not session:
            self.set_notice("Select a session before changing in-world time", error=True)
            return
        normalized = value.replace(second=0, microsecond=0)
        self.game_clock_value.set(format_game_datetime(normalized))
        self._api_action(
            "PUT",
            f"/api/admin/sessions/{session['id']}/game-datetime",
            {"game_datetime": normalized.isoformat(timespec="minutes")},
            f"In-world time set to {format_game_datetime(normalized)}",
        )

    def shift_game_clock(
        self,
        *,
        years: int = 0,
        months: int = 0,
        days: int = 0,
    ) -> None:
        current = self._current_game_datetime()
        if current is None:
            self.set_notice("Select a session before changing in-world time", error=True)
            return
        try:
            self.set_game_clock(
                shift_game_calendar(current, years=years, months=months, days=days)
            )
        except (OverflowError, ValueError) as error:
            self.set_notice(str(error), error=True)

    def open_time_popup(self, anchor: tk.Widget, unit: str, direction: int) -> None:
        current = self._current_game_datetime()
        if current is None:
            self.set_notice("Select a session before changing in-world time", error=True)
            return
        existing = getattr(self, "_time_popup", None)
        if existing is not None and existing.winfo_exists():
            existing.destroy()

        popup = tk.Toplevel(self)
        self._time_popup = popup
        popup.overrideredirect(True)
        popup.transient(self)
        popup.configure(background=self.ACCENT)
        popup.bind("<Escape>", lambda _event: popup.destroy())
        body = tk.Frame(
            popup,
            background=self.LIGHT,
            highlightbackground=self.ACCENT,
            highlightthickness=1,
            padx=8,
            pady=7,
        )
        body.pack(fill="both", expand=True)
        heading = "Earlier" if direction < 0 else "Later"
        tk.Label(
            body,
            text=f"{heading} {unit}",
            background=self.LIGHT,
            foreground=self.INK,
            font=("Segoe UI", 9, "bold"),
        ).grid(row=0, column=0, columnspan=6, sticky="w")
        tk.Button(
            body,
            text="×",
            width=2,
            relief="flat",
            background=self.LIGHT,
            activebackground=self.EDGE,
            foreground=self.INK,
            command=popup.destroy,
        ).grid(row=0, column=6, sticky="e")
        error_value = tk.StringVar()
        entry_value = tk.StringVar(
            value=current.strftime("%H:%M") if unit == "hour" else current.strftime("%M")
        )
        entry = ttk.Entry(body, textvariable=entry_value, width=9)
        entry.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(6, 5))

        def close_and_apply(target: GameDateTime, *, same_hour: bool = False) -> None:
            if target.date() != current.date():
                error_value.set("Time must remain on the same Game World Date.")
                return
            if same_hour and target.hour != current.hour:
                error_value.set("Time must remain in the same hour.")
                return
            if direction < 0 and target > current:
                error_value.set("Choose a time no later than the current game time.")
                return
            if direction > 0 and target < current:
                error_value.set("Choose a time no earlier than the current game time.")
                return
            popup.destroy()
            self.set_game_clock(target)

        def apply_manual() -> None:
            try:
                if unit == "hour":
                    parsed_time = datetime.strptime(entry_value.get().strip(), "%H:%M").time()
                    target = current.replace(
                        hour=parsed_time.hour, minute=parsed_time.minute
                    )
                    close_and_apply(target)
                else:
                    minute = int(entry_value.get().strip())
                    if not 0 <= minute <= 59:
                        raise ValueError
                    close_and_apply(current.replace(minute=minute), same_hour=True)
            except ValueError:
                error_value.set(
                    "Use HH:MM (24-hour)." if unit == "hour" else "Enter a minute from 00 to 59."
                )

        ttk.Button(body, text="Set", command=apply_manual).grid(
            row=1, column=4, columnspan=3, sticky="ew", padx=(5, 0), pady=(6, 5)
        )
        entry.bind("<Return>", lambda _event: apply_manual())

        def quick_button(
            label: str,
            target: GameDateTime,
            row: int,
            column: int,
            *,
            same_hour: bool = False,
        ) -> None:
            valid = (
                target.date() == current.date()
                and (not same_hour or target.hour == current.hour)
                and (target <= current if direction < 0 else target >= current)
            )
            button = tk.Button(
                body,
                text=label,
                relief="flat",
                borderwidth=1,
                background=self.EDGE,
                activebackground=self.PAPER,
                foreground=self.INK,
                font=("Segoe UI", 8),
                padx=4,
                pady=3,
                state="normal" if valid else "disabled",
                command=lambda: close_and_apply(target, same_hour=same_hour),
            )
            button.grid(row=row, column=column, sticky="ew", padx=1, pady=1)

        if unit == "hour":
            for index, amount in enumerate((1, 3, 6, 8, 12, 16)):
                quick_button(
                    f"{amount}h",
                    current + timedelta(hours=direction * amount),
                    2,
                    index,
                )
            named_times = (("Morning", 8), ("Afternoon", 12), ("Evening", 17), ("Night", 19))
            for index, (label, hour) in enumerate(named_times):
                quick_button(label, current.replace(hour=hour, minute=0), 3, index)
        else:
            for index, amount in enumerate((1, 3, 5, 10, 15, 30, 45)):
                quick_button(
                    f"{amount}m",
                    current + timedelta(minutes=direction * amount),
                    2 + index // 6,
                    index % 6,
                    same_hour=True,
                )
            adjacent_hour = current.replace(minute=0) + timedelta(hours=direction)
            quick_button(
                "Last hour" if direction < 0 else "Next hour",
                adjacent_hour,
                4,
                0,
            )
            for index, minute in enumerate((0, 15, 30, 45), start=1):
                quick_button(
                    f":{minute:02d}",
                    directional_minute_snap(current, minute, direction),
                    4,
                    index,
                )

        tk.Label(
            body,
            textvariable=error_value,
            background=self.LIGHT,
            foreground=self.RED,
            font=("Segoe UI", 8),
            anchor="w",
        ).grid(row=5, column=0, columnspan=7, sticky="ew", pady=(4, 0))
        popup.update_idletasks()
        x = min(anchor.winfo_rootx(), popup.winfo_screenwidth() - popup.winfo_reqwidth() - 8)
        y = anchor.winfo_rooty() + anchor.winfo_height() + 3
        if y + popup.winfo_reqheight() > popup.winfo_screenheight():
            y = anchor.winfo_rooty() - popup.winfo_reqheight() - 3
        popup.geometry(f"+{max(0, x)}+{max(0, y)}")
        popup.grab_set()
        entry.focus_force()

    def show_app_page(self, key: str) -> None:
        if key == "game-board":
            if not self.headmaster_tool_rail.winfo_manager():
                self.headmaster_tool_rail.pack(
                    side="left", fill="y", padx=(0, 8), before=self.app_host
                )
            if not self.headmaster_tools_collapsed:
                self._open_headmaster_tools_drawer()
        else:
            if self.headmaster_tool_rail.winfo_manager():
                self.headmaster_tool_rail.pack_forget()
            if (
                hasattr(self, "headmaster_tools_drawer")
                and self.headmaster_tools_drawer.winfo_manager()
            ):
                self.headmaster_tools_drawer.place_forget()
        self.app_pages[key].tkraise()
        for page_key, button in self.sidebar_buttons.items():
            active = page_key == key
            button.configure(
                background=self.ACCENT if active else self.LIGHT,
                foreground="#fff8e7" if active else self.INK,
                activebackground=self.ACCENT if active else self.PAPER,
                activeforeground="#fff8e7" if active else self.INK,
            )

    def _build_requests_page(self, parent: tk.Misc) -> None:
        header = ttk.Frame(parent)
        header.pack(fill="x", pady=(0, 8))
        ttk.Label(header, text="Requests", style="Title.TLabel").pack(side="left")
        ttk.Label(header, text="Player actions awaiting review", style="Status.TLabel").pack(side="left", padx=12)
        columns = ("request", "campaign", "submitted")
        self.requests_tree = ttk.Treeview(parent, columns=columns, show="headings", selectmode="browse")
        for key, label, width in (("request", "Request", 480), ("campaign", "Campaign", 180), ("submitted", "Submitted", 175)):
            self.requests_tree.heading(key, text=label)
            self.requests_tree.column(key, width=width, minwidth=80, stretch=key == "request")
        self.requests_tree.pack(fill="both", expand=True)
        actions = ttk.Frame(parent)
        actions.pack(fill="x", pady=(6, 0))
        ttk.Button(actions, text="Reject", style="Danger.TButton", command=lambda: self.resolve_selected_request("rejected")).pack(side="right")
        ttk.Button(actions, text="Edit & Approve...", style="Quiet.TButton", command=self.edit_selected_request).pack(side="right", padx=6)
        ttk.Button(actions, text="Approve", command=lambda: self.resolve_selected_request("approved")).pack(side="right")

    def _selected_campaign_request(self) -> dict[str, Any] | None:
        selected = self.requests_tree.selection() if hasattr(self, "requests_tree") else ()
        if not selected:
            return None
        return next((item for item in self.state_data.get("requests", []) if item.get("record_id") == selected[0]), None)

    def resolve_selected_request(self, decision: str, overrides: dict[str, str] | None = None) -> None:
        request = self._selected_campaign_request()
        if request is None:
            messagebox.showinfo("Requests", "Select a request first.", parent=self)
            return
        payload = {"campaign_id": request["campaign_id"], "decision": decision}
        payload.update(overrides or {})
        self._background(lambda: self.client.request("POST", f"/api/admin/requests/{request['record_id']}/resolve", payload), lambda _result: self.refresh(silent=True))

    def edit_selected_request(self) -> None:
        request = self._selected_campaign_request()
        if request is not None and request.get("request_type") == "creature_interaction":
            self._edit_creature_interaction_request(request)
            return
        if request is None or request.get("request_type") != "teaching":
            messagebox.showinfo("Requests", "Select a teaching or creature request to edit.", parent=self)
            return
        # The edit dialog intentionally uses search lists, never a select box.
        dialog = tk.Toplevel(self)
        dialog.title("Edit Teaching Request")
        dialog.transient(self)
        dialog.grab_set()
        dialog.geometry("720x560")
        apply_window_icon(dialog, GAME_BOARD_ICON)
        shell = ttk.Frame(dialog, padding=10)
        shell.pack(fill="both", expand=True)
        characters = [{"record_id": item["id"], "name": item["name"]} for item in self.state_data.get("characters", [])]
        pupil = tk.StringVar(value=str(request.get("pupil_person_id") or ""))
        kind = tk.StringVar(value="spell" if request.get("knowledge_collection") == "spells" else "proficiency" if request.get("knowledge_collection") == "proficiencies" else "recipe")
        subject = tk.StringVar(value=str(request.get("knowledge_record_id") or ""))
        ttk.Label(shell, text="Pupil", style="CardTitle.TLabel").pack(anchor="w")
        self._searchable_record_panel(shell, characters, pupil, height=7).pack(fill="both", expand=True, pady=(0, 8))
        kind_row = ttk.Frame(shell)
        kind_row.pack(fill="x")
        subject_host = ttk.Frame(shell)
        subject_host.pack(fill="both", expand=True, pady=8)

        def render_subjects() -> None:
            for child in subject_host.winfo_children(): child.destroy()
            choices = list((self.state_data.get("teaching_catalog", {}) or {}).get(kind.get(), []) or [])
            if not any(item.get("record_id") == subject.get() for item in choices):
                subject.set("")
            self._searchable_record_panel(subject_host, choices, subject, height=8).pack(fill="both", expand=True)

        for value, label in (("spell", "Spells"), ("proficiency", "Proficiencies"), ("recipe", "Recipes")):
            ttk.Radiobutton(kind_row, text=label, variable=kind, value=value, command=render_subjects).pack(side="left", padx=(0, 10))
        render_subjects()
        actions = ttk.Frame(shell)
        actions.pack(fill="x")
        ttk.Button(actions, text="Cancel", style="Quiet.TButton", command=dialog.destroy).pack(side="right")
        def approve() -> None:
            record = next((item for item in (self.state_data.get("teaching_catalog", {}) or {}).get(kind.get(), []) if item.get("record_id") == subject.get()), None)
            if not pupil.get() or record is None:
                messagebox.showinfo("Requests", "Choose both a pupil and a subject.", parent=dialog)
                return
            self.resolve_selected_request("approved", {"pupil_person_id": pupil.get(), "knowledge_kind": kind.get(), "knowledge_record_id": subject.get(), "knowledge_collection": record.get("collection", "")})
            dialog.destroy()
        ttk.Button(actions, text="Approve changes", command=approve).pack(side="right", padx=(0, 6))

    def _edit_creature_interaction_request(self, request: dict[str, Any]) -> None:
        creature_id = str(request.get("creature_id") or "")
        creature = next(
            (item for item in self.board_snapshot.get("actors", []) or [] if str(item.get("actor_id")) == creature_id),
            None,
        )
        if creature is None:
            messagebox.showinfo("Requests", "That creature is no longer on the active board.", parent=self)
            return
        actors = [
            {"record_id": str(item.get("actor_id", "")), "name": str(item.get("name", "Character"))}
            for item in self.board_snapshot.get("actors", []) or []
            if item.get("actor_type") != "creature" and item.get("map_id") == creature.get("map_id")
        ]
        dialog = tk.Toplevel(self)
        dialog.title("Edit Creature Request")
        dialog.transient(self)
        dialog.grab_set()
        dialog.geometry("620x500")
        apply_window_icon(dialog, GAME_BOARD_ICON)
        body = ttk.Frame(dialog, padding=10)
        body.pack(fill="both", expand=True)
        actor_id = tk.StringVar(value=str(request.get("actor_person_id") or ""))
        action = tk.StringVar(value=str(request.get("interaction_action") or "capture"))
        creature_name = tk.StringVar(value=str(request.get("creature_name") or ""))
        ttk.Label(body, text="Acting character", style="CardTitle.TLabel").pack(anchor="w")
        self._searchable_record_panel(body, actors, actor_id, height=8).pack(fill="both", expand=True, pady=(0, 8))
        actions = ttk.Frame(body)
        actions.pack(fill="x")
        for value, label in (("capture", "Capture"), ("lure", "Lure"), ("tame", "Tame"), ("bond", "Bond")):
            ttk.Radiobutton(actions, text=label, variable=action, value=value).pack(side="left", padx=(0, 10))
        name_row = ttk.Frame(body)
        name_row.pack(fill="x", pady=8)
        ttk.Label(name_row, text="Name if tamed").pack(side="left")
        ttk.Entry(name_row, textvariable=creature_name).pack(side="left", fill="x", expand=True, padx=(8, 0))
        buttons = ttk.Frame(body)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Cancel", style="Quiet.TButton", command=dialog.destroy).pack(side="right")

        def approve() -> None:
            if not actor_id.get():
                messagebox.showinfo("Requests", "Choose an acting character.", parent=dialog)
                return
            self.resolve_selected_request("approved", {
                "actor_person_id": actor_id.get(), "interaction_action": action.get(),
                "creature_name": creature_name.get().strip(),
            })
            dialog.destroy()

        ttk.Button(buttons, text="Approve & Roll", command=approve).pack(side="right", padx=(0, 6))

    def show_control_page(self, key: str) -> None:
        self.show_app_page("control-panel")
        page = self.control_pages[key]
        page.tkraise()
        labels = {
            "live-room": "Live Room",
            "sessions": "Sessions",
            "players": "Players & Characters",
            "connection": "Connection & Gmail",
        }
        self.control_section_label.configure(text=labels[key])
        for page_key, button in self.control_buttons.items():
            active = page_key == key
            button.configure(
                background=self.ACCENT if active else self.LIGHT,
                foreground="#fff8e7" if active else self.INK,
                activebackground=self.ACCENT if active else self.PAPER,
                activeforeground="#fff8e7" if active else self.INK,
            )

    def _build_chat_shell(self, parent: tk.Misc) -> None:
        self.chat_collapsed = False
        self.chat_shell = tk.Frame(
            parent,
            width=292,
            background=self.LIGHT,
            highlightbackground=self.ACCENT,
            highlightthickness=1,
        )
        self.chat_shell.pack(side="right", fill="y", padx=(8, 0))
        self.chat_shell.pack_propagate(False)
        self.chat_expanded = tk.Frame(self.chat_shell, background=self.LIGHT)
        self.right_panel_header = tk.Frame(self.chat_expanded, background=self.LIGHT)
        self.right_panel_header.pack(fill="x")
        tk.Button(
            self.right_panel_header, text="›", width=3,
            background=self.LIGHT, activebackground=self.EDGE,
            foreground=self.INK, activeforeground=self.INK,
            relief="flat", borderwidth=0, font=("Segoe UI", 9, "bold"),
            command=self.toggle_chat,
        ).pack(side="right", fill="y")
        self._build_chat(self.chat_expanded)
        self.chat_rail = tk.Button(
            self.chat_shell,
            text="‹\n\nH\nM",
            background=self.EDGE,
            activebackground=self.PAPER,
            foreground=self.INK,
            relief="flat",
            borderwidth=0,
            font=("Segoe UI", 10, "bold"),
            command=self.toggle_chat,
        )
        self.chat_expanded.pack(fill="both", expand=True)

    def _resize_board_tools_host(self, _event: tk.Event | None = None) -> None:
        if not hasattr(self, "board_tools_host") or not self.board_tools_host.winfo_exists():
            return
        self._resize_board_tools_scroll()

    def _resize_board_tools_scroll(self, _event: tk.Event | None = None) -> None:
        if not hasattr(self, "board_tools_canvas") or not self.board_tools_canvas.winfo_exists():
            return
        self.board_tools_canvas.itemconfigure(
            self._board_tools_window,
            width=max(1, self.board_tools_canvas.winfo_width()),
            height=max(
                self.board_tools_content.winfo_reqheight(),
                self.board_tools_canvas.winfo_height(),
            ),
        )
        self.board_tools_canvas.configure(scrollregion=self.board_tools_canvas.bbox("all"))

    def toggle_chat(self) -> None:
        self.chat_collapsed = not self.chat_collapsed
        if self.chat_collapsed:
            self.chat_expanded.pack_forget()
            self.chat_shell.configure(width=44)
            self.chat_rail.pack(fill="both", expand=True)
        else:
            self.chat_rail.pack_forget()
            self.chat_shell.configure(width=292)
            self.chat_expanded.pack(fill="both", expand=True)
        self._apply_responsive_chat_layout()

    def _window_resized(self, event: tk.Event) -> None:
        if event.widget is not self:
            return
        if self._chat_layout_after_id is not None:
            try:
                self.after_cancel(self._chat_layout_after_id)
            except tk.TclError:
                pass
        self._chat_layout_after_id = self.after(60, self._apply_responsive_chat_layout)

    def _apply_responsive_chat_layout(self) -> None:
        self._chat_layout_after_id = None
        if not hasattr(self, "chat_shell") or not self.chat_shell.winfo_exists():
            return
        compact = self.winfo_width() < 1120
        self._chat_layout_compact = compact
        self.chat_shell.pack_forget()
        if self.chat_collapsed:
            self.chat_shell.configure(width=44, height=1)
            self.chat_shell.pack(side="right", fill="y", padx=(6, 0), before=self.section_sidebar)
        elif compact:
            self.chat_shell.configure(width=1, height=190)
            self.chat_shell.pack(side="bottom", fill="x", pady=(6, 0), before=self.section_sidebar)
        else:
            self.chat_shell.configure(width=292, height=1)
            self.chat_shell.pack(side="right", fill="y", padx=(8, 0), before=self.section_sidebar)

    def _scrollable_page(self, parent: tk.Misc) -> tuple[ttk.Frame, ttk.Frame]:
        container = ttk.Frame(parent)
        container.grid(row=0, column=0, sticky="nsew")
        container.rowconfigure(0, weight=1)
        container.columnconfigure(0, weight=1)
        canvas = tk.Canvas(
            container,
            background=self.PAPER,
            borderwidth=0,
            highlightthickness=0,
        )
        vertical = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vertical.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        content = ttk.Frame(canvas)
        window = canvas.create_window((0, 0), window=content, anchor="nw")

        def update_region(_event: tk.Event | None = None) -> None:
            canvas.update_idletasks()
            # Keep every Control Room page inside the visible application
            # width. Its weighted grids can then contract instead of creating
            # a hidden wide page that clips right-edge actions such as Send.
            canvas.itemconfigure(window, width=max(1, canvas.winfo_width()))
            canvas.configure(scrollregion=canvas.bbox("all"))

        def wheel(event: tk.Event) -> str:
            try:
                target = self.winfo_containing(event.x_root, event.y_root)
            except (AttributeError, tk.TclError):
                return ""
            current = target
            while current is not None and current is not canvas:
                current = getattr(current, "master", None)
            if current is not canvas:
                return ""
            canvas.yview_scroll(int(-event.delta / 120), "units")
            return "break"

        content.bind("<Configure>", update_region)
        canvas.bind("<Configure>", update_region)
        self.bind_all("<MouseWheel>", wheel, add="+")
        return container, content

    def _card(self, parent: tk.Misc, title: str) -> ttk.Frame:
        card = ttk.Frame(parent, style="Card.TFrame", padding=16)
        ttk.Label(card, text=title, style="Section.TLabel").pack(anchor="w", pady=(0, 10))
        return card

    def _grid_card(self, parent: tk.Misc, title: str, columns: int) -> ttk.Frame:
        card = ttk.Frame(parent, style="Card.TFrame", padding=16)
        ttk.Label(card, text=title, style="Section.TLabel").grid(
            row=0, column=0, columnspan=columns, sticky="w", pady=(0, 10)
        )
        return card

    def _tree(self, parent: tk.Misc, columns: tuple[str, ...], headings: tuple[str, ...]) -> ttk.Treeview:
        tree = ttk.Treeview(parent, columns=columns, show="headings", selectmode="extended")
        for column, heading in zip(columns, headings):
            tree.heading(column, text=heading)
            tree.column(column, width=145, minwidth=80, anchor="w")
        tree.pack(fill="both", expand=True)
        return tree

    def _build_overview(self) -> None:
        self.overview_tab.columnconfigure(0, weight=1)
        self.overview_tab.columnconfigure(1, weight=1)
        self.overview_tab.rowconfigure(0, weight=1)
        pending_card = self._card(self.overview_tab, "Waiting for Approval")
        pending_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=8)
        self.pending_tree = self._tree(pending_card, ("name", "requested", "address"), ("Player", "Requested", "Address"))
        row = ttk.Frame(pending_card, style="Card.TFrame")
        row.pack(fill="x", pady=(10, 0))
        ttk.Button(row, text="Approve", style="Good.TButton", command=lambda: self.resolve_pending("approve")).pack(side="left")
        ttk.Button(row, text="Deny", style="Danger.TButton", command=lambda: self.resolve_pending("deny")).pack(side="left", padx=8)
        ttk.Button(row, text="Admit All", style="Good.TButton", command=self.admit_all_pending).pack(side="right")

        connected_card = self._card(self.overview_tab, "Currently Logged In")
        connected_card.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=8)
        self.connections_tree = self._tree(
            connected_card,
            ("name", "quality", "latency", "activity"),
            ("Player", "Quality", "Latency", "Last Activity"),
        )
        ttk.Button(connected_card, text="Revoke & Disconnect", style="Danger.TButton", command=self.revoke_connected).pack(anchor="e", pady=(10, 0))

        announcement_card = self._card(self.overview_tab, "Announcement")
        announcement_card.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.announcement = tk.Text(announcement_card, height=3, wrap="word", background="#fff8e6", foreground=self.INK, relief="solid", borderwidth=1)
        self.announcement.pack(fill="x")
        ttk.Button(announcement_card, text="Send to Connected Players", command=self.send_announcement).pack(anchor="e", pady=(10, 0))

    def _build_contacts(self) -> None:
        form = ttk.Frame(self.contacts_tab, style="Card.TFrame", padding=(10, 8))
        form.pack(fill="x", pady=(4, 6))
        ttk.Label(form, text="Add Player", style="Section.TLabel").grid(
            row=0, column=0, columnspan=5, sticky="w", pady=(0, 6)
        )
        ttk.Label(form, text="Name", style="Card.TLabel").grid(row=1, column=0, sticky="w")
        ttk.Label(form, text="Email", style="Card.TLabel").grid(row=1, column=2, sticky="w", padx=(10, 0))
        self.contact_name = ttk.Entry(form)
        self.contact_email = ttk.Entry(form)
        self.contact_name.grid(row=1, column=1, sticky="ew", padx=(6, 0))
        self.contact_email.grid(row=1, column=3, sticky="ew", padx=(6, 0))
        ttk.Button(form, text="Add Player", command=self.add_contact).grid(row=1, column=4, padx=(10, 0))
        form.columnconfigure(1, weight=1)
        form.columnconfigure(3, weight=1)

        card = ttk.Frame(self.contacts_tab, style="Card.TFrame", padding=10)
        card.pack(fill="x", pady=(0, 4))
        address_header = ttk.Frame(card, style="Card.TFrame")
        address_header.pack(fill="x", pady=(0, 6))
        ttk.Label(address_header, text="Private Address Book", style="Section.TLabel").pack(side="left")
        ttk.Button(
            address_header,
            text="Remove Selected",
            style="Danger.TButton",
            command=self.remove_contacts,
        ).pack(side="right")
        self.contacts_tree = self._tree(
            card,
            ("name", "email", "character"),
            ("Player", "Email Address", "Character Identity"),
        )
        self.contacts_tree.configure(height=6)
        self.contacts_tree.bind("<<TreeviewSelect>>", self._contact_selected)
        character_row = ttk.Frame(card, style="Card.TFrame")
        character_row.pack(fill="x", pady=(6, 0))
        ttk.Label(character_row, text="Character identity", style="Card.TLabel").pack(side="left")
        self.selected_character_label = tk.StringVar(value="No character selected")
        ttk.Label(
            character_row,
            textvariable=self.selected_character_label,
            style="Card.TLabel",
        ).pack(side="left", fill="x", expand=True, padx=10)
        ttk.Button(
            character_row,
            text="Choose Character...",
            command=self.choose_character,
        ).pack(side="left")
        ttk.Button(
            character_row,
            text="Clear Link",
            style="Quiet.TButton",
            command=self.clear_character_link,
        ).pack(side="left", padx=(8, 0))
        self.character_choices: list[dict[str, str]] = []
        self.character_label_to_id: dict[str, str] = {}
        self.character_id_to_label: dict[str, str] = {}
        self.selected_character_id: str | None = None

    def _build_chat(self, parent: tk.Misc) -> None:
        card = ttk.Frame(parent, style="Card.TFrame", padding=10)
        self.chat_card = card
        card.pack(fill="both", expand=True)
        chat_controls = ttk.Frame(card, style="Card.TFrame")
        chat_controls.pack(fill="x", pady=(0, 4))
        decrease = ttk.Button(
            chat_controls,
            text="−",
            width=3,
            style="Quiet.TButton",
            command=lambda: self.adjust_chat_font_size(-1),
        )
        increase = ttk.Button(
            chat_controls,
            text="+",
            width=3,
            style="Quiet.TButton",
            command=lambda: self.adjust_chat_font_size(1),
        )
        increase.pack(side="right")
        decrease.pack(side="right", padx=(0, 3))
        self._attach_tooltip(decrease, "Decrease chat text size")
        self._attach_tooltip(increase, "Increase chat text size")
        log_frame = ttk.Frame(card, style="Card.TFrame")
        log_frame.pack(fill="both", expand=True)
        self.chat_log = tk.Text(
            log_frame,
            wrap="word",
            state="disabled",
            background="#fff8e6",
            foreground=self.INK,
            relief="solid",
            borderwidth=1,
            padx=10,
            pady=10,
            font=("Segoe UI", self.chat_font_size),
        )
        chat_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.chat_log.yview)
        self.chat_log.configure(yscrollcommand=chat_scroll.set)
        self.chat_log.pack(side="left", fill="both", expand=True)
        chat_scroll.pack(side="right", fill="y")
        self.chat_log.bind("<Button-1>", self._inspect_chat_roll)
        self._configure_chat_fonts()
        composer = ttk.Frame(card, style="Card.TFrame")
        composer.pack(fill="x", pady=(10, 0))
        self.chat_entry = ttk.Entry(
            composer, font=("Segoe UI", self.chat_font_size)
        )
        self.chat_entry.pack(side="left", fill="x", expand=True)
        self.chat_entry.bind("<Return>", lambda _event: self.send_chat())
        ttk.Button(composer, text="Send", command=self.send_chat).pack(side="right", padx=(10, 0))
        self._rendered_chat_ids: tuple[str, ...] = ()
        self._chat_roll_ranges: list[tuple[str, str, str, str]] = []
        self._expanded_chat_roll_ids: set[str] = set()
        self._last_chat_messages: list[dict[str, Any]] = []
        self._chat_focus_roll_id = ""

    def _configure_chat_fonts(self) -> None:
        if not hasattr(self, "chat_log"):
            return
        normal = ("Segoe UI", self.chat_font_size)
        bold = ("Segoe UI", self.chat_font_size, "bold")
        self.chat_log.configure(font=normal)
        shared = {
            "lmargin1": 8, "lmargin2": 8, "rmargin": 8,
            "spacing1": 4, "spacing3": 4,
        }
        self.chat_log.tag_configure(
            "headmaster", foreground=self.INK, background="#fff1ce",
            font=bold, justify="right", **shared,
        )
        self.chat_log.tag_configure(
            "system", foreground=self.GREEN, background="#f2ead0",
            font=bold, **shared,
        )
        self.chat_log.tag_configure(
            "player", foreground=self.INK, background="#fff8e6",
            font=bold, **shared,
        )
        self.chat_log.tag_configure(
            "message_body", foreground=self.INK, font=normal,
            lmargin1=8, lmargin2=8, rmargin=8, spacing3=5,
        )
        self.chat_log.tag_configure(
            "roll_summary", background="#ead18e", foreground=self.INK,
            font=("Segoe UI", max(8, self.chat_font_size - 1), "bold"),
            relief="raised", borderwidth=1,
            lmargin1=8, lmargin2=8, rmargin=8, spacing1=3, spacing3=5,
        )
        self.chat_log.tag_configure(
            "roll_detail", background="#f8edcf", foreground=self.INK,
            font=("Segoe UI", max(8, self.chat_font_size - 1)),
            lmargin1=18, lmargin2=18, rmargin=8, spacing1=1, spacing3=1,
            tabs=(190,),
        )
        self.chat_log.tag_configure(
            "roll_source", background="#f8edcf", foreground="#735031",
            font=("Segoe UI", max(8, self.chat_font_size - 2)),
            lmargin1=32, lmargin2=32, rmargin=8, spacing1=0, spacing3=0,
            tabs=(190,),
        )
        self.chat_log.tag_configure(
            "roll_total", background="#ead18e", foreground=self.INK,
            font=("Segoe UI", max(8, self.chat_font_size - 1), "bold"),
            lmargin1=18, lmargin2=18, rmargin=8, spacing1=3, spacing3=5,
            tabs=(190,),
        )
        self.chat_log.tag_configure(
            "critical_failure", background="#6f1717", foreground="#ffe2e2",
        )
        self.chat_log.tag_configure(
            "failure", background="#f3c5bd", foreground=self.INK,
        )
        self.chat_log.tag_configure(
            "success", background="#d7efcb", foreground=self.INK,
        )
        self.chat_log.tag_configure(
            "critical_success", background="#d7efcb", foreground="#314d2a",
            relief="solid", borderwidth=2,
        )
        if hasattr(self, "chat_entry"):
            self.chat_entry.configure(font=normal)

    def adjust_chat_font_size(self, direction: int) -> None:
        next_size = max(8, min(20, self.chat_font_size + int(direction)))
        if next_size == self.chat_font_size:
            return
        self.chat_font_size = next_size
        self._configure_chat_fonts()
        self.preferences["chat_font_size"] = next_size
        try:
            self.preferences_store.save(self.preferences)
        except OSError:
            self.set_notice("Chat size changed, but the preference could not be saved")

    def _build_session(self) -> None:
        self.session_tab.columnconfigure(0, weight=1)
        self.session_tab.columnconfigure(1, weight=2)
        self.session_tab.rowconfigure(0, weight=1)
        self.selected_session_id: str | None = str(
            self.preferences.get("last_session_id", "") or ""
        ) or None
        self.selected_invite_ids: set[str] = set()
        self._invite_selection_session_id: str | None = None
        self._invite_roster_ids_by_session: dict[str, set[str]] = {}
        self.sending_invitations = False

        sessions_card = self._card(self.session_tab, "Sessions")
        self.sessions_card = sessions_card
        sessions_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=8)
        self.sessions_tree = ttk.Treeview(
            sessions_card,
            columns=("title", "campaign", "event_date", "game_date", "expires"),
            show="headings",
            selectmode="browse",
            height=12,
        )
        for column, heading, width in (
            ("title", "Session", 145),
            ("campaign", "Campaign", 125),
            ("event_date", "Event Date", 95),
            ("game_date", "Game World Date & Time", 145),
            ("expires", "Expires", 95),
        ):
            self.sessions_tree.heading(column, text=heading)
            self.sessions_tree.column(column, width=width, minwidth=75, anchor="w")
        session_scroll = ttk.Scrollbar(
            sessions_card, orient="vertical", command=self.sessions_tree.yview
        )
        self.sessions_tree.configure(yscrollcommand=session_scroll.set)
        self.sessions_tree.pack(side="left", fill="both", expand=True)
        session_scroll.pack(side="right", fill="y")
        self.sessions_tree.bind("<<TreeviewSelect>>", self._session_selected)

        session_buttons = ttk.Frame(self.session_tab, style="Card.TFrame")
        self.session_buttons = session_buttons
        session_buttons.grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=(0, 8))
        ttk.Button(session_buttons, text="Create", command=self.create_session).pack(side="left")
        ttk.Button(
            session_buttons, text="Duplicate", style="Quiet.TButton",
            command=self.duplicate_session,
        ).pack(side="left", padx=6)
        ttk.Button(
            session_buttons, text="End", style="Quiet.TButton", command=self.end_session
        ).pack(side="left")
        ttk.Button(
            session_buttons, text="Delete", style="Danger.TButton", command=self.delete_session
        ).pack(side="right")

        invitations_card = self._card(self.session_tab, "Invitations")
        self.invitations_card = invitations_card
        invitations_card.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=8)
        self.session_summary = ttk.Label(
            invitations_card, text="Select a session", style="Card.TLabel"
        )
        self.session_summary.pack(anchor="w", pady=(0, 10))
        self.invites_tree = ttk.Treeview(
            invitations_card,
            columns=("checked", "name", "email", "sent", "logged_in"),
            show="headings",
            selectmode="browse",
            height=12,
        )
        for column, heading, width, anchor in (
            ("checked", "✓", 30, "center"),
            ("name", "Player", 105, "w"),
            ("email", "Email", 140, "w"),
            ("sent", "Last invitation", 115, "w"),
            ("logged_in", "Logged in", 58, "center"),
        ):
            self.invites_tree.heading(column, text=heading)
            self.invites_tree.column(
                column,
                width=width,
                minwidth=34 if column == "checked" else 60,
                anchor=anchor,
                stretch=column in {"name", "email", "sent"},
            )
        invitation_scroll = ttk.Scrollbar(
            invitations_card, orient="vertical", command=self.invites_tree.yview
        )
        self.invites_tree.configure(yscrollcommand=invitation_scroll.set)
        self.invites_tree.pack(side="left", fill="both", expand=True)
        invitation_scroll.pack(side="right", fill="y")
        self.invites_tree.bind("<ButtonRelease-1>", self._toggle_invitation_check)
        self.invites_tree.bind("<space>", self._toggle_focused_invitation)
        self.invites_tree.bind("<Return>", self._toggle_focused_invitation)

        invite_controls = ttk.Frame(self.session_tab, style="Card.TFrame")
        self.invite_controls = invite_controls
        invite_controls.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(0, 8))
        self.invite_selection_label = ttk.Label(
            invite_controls, text="0 selected", style="Card.TLabel"
        )
        self.invite_selection_label.pack(side="left")
        check_all = ttk.Button(
            invite_controls, text="☑", width=3, style="Quiet.TButton",
            command=self.select_all_invites,
        )
        check_all.pack(side="left", padx=(6, 0))
        clear = ttk.Button(
            invite_controls, text="☐", width=3, style="Quiet.TButton",
            command=self.clear_invite_selection,
        )
        clear.pack(side="left", padx=(3, 0))
        remove = ttk.Button(
            invite_controls, text="−", width=3, style="Danger.TButton",
            command=self.remove_from_session,
        )
        remove.pack(side="left", padx=(3, 0))
        self._attach_tooltip(check_all, "Check every player")
        self._attach_tooltip(clear, "Clear all checks")
        self._attach_tooltip(remove, "Remove checked players from this session")
        self.send_selected_button = ttk.Button(
            invite_controls, text="Send ✓",
            command=lambda: self.send_invites(False),
        )
        self.send_selected_button.pack(side="right")
        self.send_all_button = ttk.Button(
            invite_controls, text="Send all", style="Quiet.TButton",
            command=lambda: self.send_invites(True),
        )
        self.send_all_button.pack(side="right", padx=5)
        self._attach_tooltip(self.send_selected_button, "Email the checked players")
        self._attach_tooltip(self.send_all_button, "Email every player in this session")
        self.session_tab.bind("<Configure>", self._apply_responsive_session_layout, add="+")

    def _apply_responsive_session_layout(self, event: tk.Event | None = None) -> None:
        """Stack both panes before their tables or action rows can clip."""

        if not all(
            hasattr(self, name)
            for name in (
                "sessions_card", "session_buttons", "invitations_card", "invite_controls"
            )
        ):
            return
        width = int(getattr(event, "width", 0) or self.session_tab.winfo_width())
        compact = width < 980
        if compact:
            self.session_tab.columnconfigure(0, weight=1)
            self.session_tab.columnconfigure(1, weight=0)
            self.session_tab.rowconfigure(0, weight=1)
            self.session_tab.rowconfigure(2, weight=1)
            self.sessions_card.grid_configure(
                row=0, column=0, sticky="nsew", padx=0, pady=(8, 4)
            )
            self.session_buttons.grid_configure(
                row=1, column=0, sticky="ew", padx=0, pady=(0, 6)
            )
            self.invitations_card.grid_configure(
                row=2, column=0, sticky="nsew", padx=0, pady=(6, 4)
            )
            self.invite_controls.grid_configure(
                row=3, column=0, sticky="ew", padx=0, pady=(0, 8)
            )
        else:
            self.session_tab.columnconfigure(0, weight=1)
            self.session_tab.columnconfigure(1, weight=2)
            self.session_tab.rowconfigure(0, weight=1)
            self.session_tab.rowconfigure(2, weight=0)
            self.sessions_card.grid_configure(
                row=0, column=0, sticky="nsew", padx=(0, 8), pady=8
            )
            self.session_buttons.grid_configure(
                row=1, column=0, sticky="ew", padx=(0, 8), pady=(0, 8)
            )
            self.invitations_card.grid_configure(
                row=0, column=1, sticky="nsew", padx=(8, 0), pady=8
            )
            self.invite_controls.grid_configure(
                row=1, column=1, sticky="ew", padx=(8, 0), pady=(0, 8)
            )

    def _build_settings(self) -> None:
        card = self._grid_card(self.settings_tab, "Connection & Gmail Setup", 3)
        card.pack(fill="both", expand=True, pady=8)
        fields = (
            ("wordpress_player_url", "WordPress Game Board page"),
            ("allowed_origin", "Allowed WordPress origin (automatic)"),
            ("public_api_base", "Public Game Board address"),
            ("gmail_credentials_path", "Google credentials file"),
            ("gmail_sender", "Sending Gmail address (optional)"),
            ("timezone", "Timezone"),
        )
        self.setting_entries: dict[str, ttk.Entry] = {}
        for row, (key, label) in enumerate(fields):
            grid_row = row + 1
            ttk.Label(card, text=label, style="Card.TLabel").grid(row=grid_row, column=0, sticky="w", pady=6)
            entry = ttk.Entry(card)
            entry.grid(row=grid_row, column=1, sticky="ew", padx=(18, 0), pady=6)
            entry.bind("<FocusIn>", self._begin_settings_edit)
            self.setting_entries[key] = entry
            if key == "gmail_credentials_path":
                ttk.Button(
                    card,
                    text="Browse…",
                    style="Quiet.TButton",
                    command=self.choose_credentials_file,
                ).grid(row=grid_row, column=2, padx=(10, 0), pady=6)
        card.columnconfigure(1, weight=1)
        controls = ttk.Frame(card, style="Card.TFrame")
        controls.grid(row=len(fields) + 1, column=0, columnspan=2, sticky="e", pady=(18, 0))
        ttk.Button(controls, text="Connect Gmail", style="Quiet.TButton", command=self.connect_gmail).pack(side="left", padx=(0, 8))
        ttk.Button(controls, text="Save Settings", command=self.save_settings).pack(side="left")
        self.gmail_status = ttk.Label(card, text="Gmail status: checking…", style="Card.TLabel")
        self.gmail_status.grid(row=len(fields) + 2, column=0, columnspan=2, sticky="w", pady=(14, 0))

    def _begin_settings_edit(self, _event: tk.Event | None = None) -> None:
        self.settings_dirty = True

    def choose_credentials_file(self) -> None:
        selected = filedialog.askopenfilename(
            parent=self,
            title="Select Google OAuth credentials",
            filetypes=(("JSON files", "*.json"), ("All files", "*.*")),
        )
        if selected:
            entry = self.setting_entries["gmail_credentials_path"]
            entry.delete(0, "end")
            entry.insert(0, selected)
            self.settings_dirty = True

    def _start_server(self) -> None:
        self._background(self.server.start, self._server_started)

    def _server_started(self, _result: Any) -> None:
        self.server_status.configure(text="LOCAL SERVER ONLINE", foreground=self.GREEN)
        self.set_notice("Game Board is ready. Tailscale Funnel remains separately controlled.")
        self.refresh()
        self.after(2000, self._poll)

    def _poll(self) -> None:
        if not self.closing:
            self.refresh(silent=True)
            self.after(2000, self._poll)

    def _background(
        self,
        work: Callable[[], Any],
        success: Callable[[Any], None] | None = None,
        *,
        failure: Callable[[Exception], None] | None = None,
        quiet: bool = False,
    ) -> None:
        def runner() -> None:
            try:
                result = work()
            except Exception as error:
                self.after(
                    0,
                    lambda captured=error: (
                        failure(captured) if failure else self._failed(captured, quiet)
                    ),
                )
            else:
                if success:
                    self.after(0, lambda: success(result))

        threading.Thread(target=runner, daemon=True).start()

    def _failed(self, error: Exception, quiet: bool) -> None:
        self.refreshing = False
        self._hide_board_loading()
        if isinstance(error, ConnectionError):
            self.server_status.configure(text="LOCAL SERVER OFFLINE", foreground=self.RED)
        else:
            self.server_status.configure(text="LOCAL SERVER ONLINE", foreground=self.GREEN)
        self.set_notice(str(error), error=True)
        if not quiet:
            messagebox.showerror("Game Board", str(error), parent=self)

    def set_notice(self, text: str, error: bool = False) -> None:
        self.notice.configure(text=text, foreground=self.RED if error else self.MUTED)

    def refresh(self, silent: bool = False) -> None:
        if self.refreshing:
            return
        self.refreshing = True
        if not silent or not self.board_snapshot:
            self._show_board_loading()

        def done(state: dict[str, Any]) -> None:
            self.refreshing = False
            self.server_status.configure(text="LOCAL SERVER ONLINE", foreground=self.GREEN)
            self.render(state)

        self._background(self.client.state, done, quiet=silent)

    def render(self, state: dict[str, Any]) -> None:
        self.state_data = state
        contacts = state.get("contacts", [])
        self._replace_tree(self.contacts_tree, [
            (c["id"], (c["name"], c["email"], c.get("character_name") or "Not linked"))
            for c in contacts
        ])
        characters = state.get("characters", [])
        if characters != self.character_choices:
            self.character_choices = list(characters)
            counts: dict[str, int] = {}
            for character in characters:
                counts[character["name"]] = counts.get(character["name"], 0) + 1
            self.character_label_to_id = {}
            self.character_id_to_label = {}
            for character in characters:
                label = character["name"]
                if counts[label] > 1:
                    label = f"{label}  [{character['id'][:8]}]"
                self.character_label_to_id[label] = character["id"]
                self.character_id_to_label[character["id"]] = label
            if self.selected_character_id not in self.character_id_to_label:
                self._set_character_selection(None)
        settings = state.get("settings", {})
        if not self.settings_dirty:
            for key, entry in self.setting_entries.items():
                entry.delete(0, "end")
                entry.insert(0, settings.get(key, ""))
        gmail = state.get("gmail", {})
        gmail_text = "connected" if gmail.get("connected") else gmail.get("error") or "not connected"
        self.gmail_status.configure(text=f"Gmail status: {gmail_text}")

        live_sessions = list(
            state.get("sessions") or ([state["session"]] if state.get("session") else [])
        )
        archived_sessions = list(state.get("archived_sessions") or [])
        sessions = live_sessions + archived_sessions
        session_rows = [
            (
                session["id"],
                (
                    (
                        f"{session['title']}  [{str(session.get('status') or 'ended').upper()}]"
                        if session.get("archived")
                        else session["title"]
                    ),
                    session.get("campaign_name") or "Legacy session",
                    format_stored_date(session.get("event_date")),
                    format_stored_game_datetime(session.get("game_datetime")),
                    format_stored_date(session.get("expires_at")),
                ),
            )
            for session in sessions
        ]
        self._replace_tree(self.sessions_tree, session_rows)
        session_ids = {session["id"] for session in sessions}
        if self.selected_session_id not in session_ids:
            self.selected_session_id = sessions[0]["id"] if sessions else None
            self._invite_selection_session_id = None
        if self.selected_session_id:
            selected_for_memory = next(
                (item for item in sessions if item.get("id") == self.selected_session_id),
                None,
            )
            self.preferences["last_session_id"] = self.selected_session_id
            if selected_for_memory and selected_for_memory.get("campaign_id"):
                self.preferences["last_campaign_id"] = selected_for_memory["campaign_id"]
            try:
                self.preferences_store.save(self.preferences)
            except OSError:
                pass
        if self.selected_session_id and self.sessions_tree.exists(self.selected_session_id):
            self.sessions_tree.selection_set(self.selected_session_id)
        session = next(
            (item for item in sessions if item["id"] == self.selected_session_id), None
        )
        self._render_game_clock(session)
        board = deepcopy(
            (state.get("boards") or {}).get(self.selected_session_id or "", {})
        )
        if not board.get("maps"):
            board["maps"] = list(state.get("location_maps") or [])
        self._render_board(board)
        self.after_idle(self._hide_board_loading)

        pending_rows: list[tuple[str, tuple[Any, ...]]] = []
        invite_rows: list[tuple[str, tuple[Any, ...]]] = []
        for active_session in sessions:
            for request in active_session.get("pending", []):
                if request.get("status") == "pending":
                    pending_rows.append((
                        request["id"],
                        (
                            f"{request['name']} — {active_session['title']}",
                            request["requested_at"],
                            request.get("client_ip", ""),
                        ),
                    ))
        if session:
            session_state = (
                f"  •  Status: {str(session.get('status') or 'ended').upper()}"
                if session.get("archived")
                else "  •  Status: ACTIVE"
            )
            self.session_summary.configure(
                text=(
                    f"{session['title']}  •  Campaign: {session.get('campaign_name') or 'Legacy session'}"
                    f"{session_state}"
                    f"  •  Event date: {format_stored_date(session.get('event_date'))}"
                    f"  •  Game World Date: {format_stored_game_datetime(session.get('game_datetime'))}"
                    f"  •  Expires: {format_stored_date(session.get('expires_at'))}"
                )
            )
            roster_ids = {
                player["contact_id"] for player in session.get("roster", [])
                if player.get("contact_id")
            }
            if self._invite_selection_session_id != session["id"]:
                self.selected_invite_ids = {
                    player["contact_id"]
                    for player in session.get("roster", [])
                    if not player.get("revoked")
                }
                self._invite_selection_session_id = session["id"]
            else:
                self.selected_invite_ids.intersection_update(roster_ids)
                previous_roster = self._invite_roster_ids_by_session.get(session["id"], set())
                newly_added = roster_ids - previous_roster
                self.selected_invite_ids.update(
                    player["contact_id"]
                    for player in session.get("roster", [])
                    if player["contact_id"] in newly_added and not player.get("revoked")
                )
            self._invite_roster_ids_by_session[session["id"]] = roster_ids
            for player in session.get("roster", []):
                sent_at = player.get("sent_at")
                sent_text = f"{str(sent_at)[:16].replace('T', ' ')} UTC" if sent_at else "Never"
                invite_rows.append((
                    player["contact_id"],
                    (
                        "✓" if player["contact_id"] in self.selected_invite_ids else "",
                        player["name"],
                        player["email"],
                        sent_text,
                        "Yes" if player.get("has_logged_in") else "No",
                    ),
                ))
        else:
            self.session_summary.configure(text="Select a session")
            self.selected_invite_ids.clear()
            self._invite_selection_session_id = None
        self._render_chat(list((session or {}).get("chat", [])))
        self._replace_tree(self.pending_tree, pending_rows)
        self._replace_tree(self.invites_tree, invite_rows)
        campaign_requests = list(state.get("requests", []) or [])
        if hasattr(self, "requests_tree"):
            self._replace_tree(self.requests_tree, [
                (
                    str(item.get("record_id")),
                    (
                        str(item.get("request_summary") or item.get("request_type") or "Request"),
                        str(item.get("campaign_name") or ""),
                        str(item.get("submitted_at") or "")[:16].replace("T", " "),
                    ),
                )
                for item in campaign_requests
            ])
        request_count = len(campaign_requests)
        request_ids = {str(item.get("record_id")) for item in campaign_requests}
        new_request_ids = request_ids - self._known_campaign_request_ids
        self._known_campaign_request_ids.update(request_ids)
        self.requests_button.configure(
            text=f"Requests ({request_count})" if request_count else "Requests"
        )
        if new_request_ids:
            self.bell()
            self.set_notice(
                f"{len(new_request_ids)} new player request{'s' if len(new_request_ids) != 1 else ''} awaiting review"
            )
        self._update_invite_count()
        self._update_admission_alert(pending_rows)

        connection_rows = []
        for connection in state.get("connections", []):
            latency = "Measuring" if connection.get("latency_ms") is None else f"{connection['latency_ms']} ms"
            connection_id = f"{connection.get('session_id', '')}:{connection['contact_id']}"
            connection_rows.append((connection_id, (
                connection["name"], connection["quality"].title(), latency, connection["last_activity"]
            )))
        self._replace_tree(self.connections_tree, connection_rows)

    def _update_admission_alert(self, pending_rows: list[tuple[str, tuple[Any, ...]]]) -> None:
        pending_ids = {request_id for request_id, _values in pending_rows}
        new_ids = pending_ids - self._known_pending_ids
        self._known_pending_ids.update(pending_ids)
        count = len(pending_ids)
        if count:
            names = [str(values[0]) for _request_id, values in pending_rows]
            label = f"{count} player{'s are' if count != 1 else ' is'} waiting for approval: {', '.join(names)}"
            self.admission_alert_text.configure(text=label)
            self.admission_quick_approve_button.configure(
                text="Approve" if count == 1 else "Approve all"
            )
            if not self.admission_alert.winfo_manager():
                self.admission_alert.pack(
                    fill="x", padx=12, pady=(0, 6), before=self.workspace
                )
            self.control_panel_button.configure(text=f"Control Room  •  {count} waiting")
        else:
            if self.admission_alert.winfo_manager():
                self.admission_alert.pack_forget()
            self.control_panel_button.configure(text="Control Room")
        if new_ids:
            self._notify_join_request(new_ids, pending_rows)

    def _notify_join_request(
        self,
        new_ids: set[str] | None = None,
        pending_rows: list[tuple[str, tuple[Any, ...]]] | None = None,
    ) -> None:
        self.bell()
        self.set_notice("A player is waiting for admission approval")
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.user32.FlashWindow(self.winfo_id(), True)
            except Exception:
                pass
        request_ids = list(new_ids or [])
        if not request_ids:
            return
        names_by_id = {
            request_id: str(values[0])
            for request_id, values in (pending_rows or [])
        }
        if (
            self._admission_desktop_popup is not None
            and self._admission_desktop_popup.winfo_exists()
        ):
            self._admission_desktop_popup.destroy()
        popup = tk.Toplevel(self)
        self._admission_desktop_popup = popup
        popup.title("Game Board admission")
        popup.configure(background="#f6e7b8")
        popup.resizable(False, False)
        popup.attributes("-topmost", True)
        apply_window_icon(popup, GAME_BOARD_ICON)
        shell = tk.Frame(
            popup, background="#f6e7b8", padx=12, pady=10,
            highlightbackground=self.ACCENT, highlightthickness=1,
        )
        shell.pack(fill="both", expand=True)
        tk.Label(
            shell, text="Player waiting for approval",
            background="#f6e7b8", foreground=self.INK,
            font=("Segoe UI", 10, "bold"), anchor="w",
        ).pack(fill="x")
        display_names = [names_by_id.get(item, "Player") for item in request_ids]
        tk.Label(
            shell, text="\n".join(display_names[:3]),
            background="#f6e7b8", foreground=self.INK,
            font=("Segoe UI", 9), justify="left", anchor="w", wraplength=330,
        ).pack(fill="x", pady=(3, 8))
        actions = tk.Frame(shell, background="#f6e7b8")
        actions.pack(fill="x")

        def close_popup() -> None:
            if popup.winfo_exists():
                popup.destroy()
            self._admission_desktop_popup = None

        def approve() -> None:
            ids = list(request_ids)
            close_popup()

            def work() -> None:
                for request_id in ids:
                    self.client.request(
                        "POST", f"/api/admin/admissions/{request_id}/approve"
                    )

            self._background(
                work,
                lambda _result: (
                    self.set_notice(f"Admitted {len(ids)} player(s)"),
                    self.refresh(silent=True),
                ),
            )

        def review() -> None:
            close_popup()
            self.deiconify()
            self.lift()
            self.show_control_page("live-room")

        tk.Button(
            actions, text="Dismiss", command=close_popup,
            background="#d2b274", foreground=self.INK, relief="flat", padx=10, pady=5,
        ).pack(side="right")
        tk.Button(
            actions, text="Review", command=review,
            background=self.ACCENT, foreground="#fff8e7", relief="flat", padx=12, pady=5,
        ).pack(side="right", padx=(0, 5))
        tk.Button(
            actions, text="Approve" if len(request_ids) == 1 else "Approve all",
            command=approve, background=self.GREEN, foreground="#fff8e7",
            relief="flat", padx=12, pady=5,
        ).pack(side="right", padx=(0, 5))
        popup.update_idletasks()
        width = max(360, popup.winfo_reqwidth())
        height = popup.winfo_reqheight()
        x = popup.winfo_screenwidth() - width - 18
        y = popup.winfo_screenheight() - height - 58
        popup.geometry(f"{width}x{height}+{x}+{y}")
        popup.protocol("WM_DELETE_WINDOW", close_popup)

    @staticmethod
    def _replace_tree(tree: ttk.Treeview, rows: list[tuple[str, tuple[Any, ...]]]) -> None:
        wanted = {item_id for item_id, _values in rows}
        for item_id in tree.get_children():
            if item_id not in wanted:
                tree.delete(item_id)
        for index, (item_id, values) in enumerate(rows):
            if tree.exists(item_id):
                tree.item(item_id, values=values)
                tree.move(item_id, "", index)
            else:
                tree.insert("", "end", iid=item_id, values=values)

    def _selected_session(self) -> dict[str, Any] | None:
        return next(
            (
                session for session in (
                    list(self.state_data.get("sessions") or [])
                    + list(self.state_data.get("archived_sessions") or [])
                )
                if session.get("id") == self.selected_session_id
            ),
            None,
        )

    def _session_selected(self, _event: tk.Event | None = None) -> None:
        selection = self.sessions_tree.selection()
        if not selection or selection[0] == self.selected_session_id:
            return
        self._show_board_loading("Loading campaign board…")
        self.selected_session_id = selection[0]
        self._invite_selection_session_id = None
        self.preferences["last_session_id"] = self.selected_session_id
        selected = next(
            (
                item for item in (
                    list(self.state_data.get("sessions") or [])
                    + list(self.state_data.get("archived_sessions") or [])
                )
                if item.get("id") == self.selected_session_id
            ),
            None,
        )
        if selected and selected.get("campaign_id"):
            self.preferences["last_campaign_id"] = selected["campaign_id"]
        try:
            self.preferences_store.save(self.preferences)
        except OSError:
            pass
        self.render(self.state_data)

    def _toggle_invitation_id(self, contact_id: str) -> None:
        if contact_id in self.selected_invite_ids:
            self.selected_invite_ids.remove(contact_id)
        else:
            self.selected_invite_ids.add(contact_id)
        self.render(self.state_data)

    def _toggle_invitation_check(self, event: tk.Event) -> str:
        contact_id = self.invites_tree.identify_row(event.y)
        if contact_id:
            self.invites_tree.focus(contact_id)
            self._toggle_invitation_id(contact_id)
        return "break"

    def _toggle_focused_invitation(self, _event: tk.Event | None = None) -> str:
        contact_id = self.invites_tree.focus()
        if contact_id:
            self._toggle_invitation_id(contact_id)
        return "break"

    def select_all_invites(self) -> None:
        self.selected_invite_ids = set(self.invites_tree.get_children())
        self.render(self.state_data)

    def clear_invite_selection(self) -> None:
        self.selected_invite_ids.clear()
        self.render(self.state_data)

    def _update_invite_count(self) -> None:
        if hasattr(self, "invite_selection_label"):
            count = len(self.selected_invite_ids)
            self.invite_selection_label.configure(
                text=f"{count} selected"
            )

    def _api_action(self, method: str, path: str, payload: dict[str, Any] | None, success_message: str) -> None:
        def done(_result: Any) -> None:
            self.set_notice(success_message)
            self.refresh()

        self._background(lambda: self.client.request(method, path, payload), done)

    def add_contact(self) -> None:
        name, email = self.contact_name.get().strip(), self.contact_email.get().strip()
        if not name or not email:
            messagebox.showwarning("Add player", "Enter both a name and email address.", parent=self)
            return
        self._api_action("POST", "/api/admin/contacts", {"name": name, "email": email}, "Player added")
        self.contact_name.delete(0, "end")
        self.contact_email.delete(0, "end")

    def remove_contacts(self) -> None:
        selected = list(self.contacts_tree.selection())
        if not selected or not messagebox.askyesno("Remove players", "Remove the selected players?", parent=self):
            return

        def work() -> None:
            for contact_id in selected:
                self.client.request("DELETE", f"/api/admin/contacts/{contact_id}")

        self._background(work, lambda _value: (self.set_notice("Players removed"), self.refresh()))

    def _set_character_selection(self, character_id: str | None) -> None:
        self.selected_character_id = character_id
        self.selected_character_label.set(
            self.character_id_to_label.get(character_id, "No character selected")
        )

    def choose_character(self) -> None:
        selected_contacts = list(self.contacts_tree.selection())
        if len(selected_contacts) != 1:
            messagebox.showwarning(
                "Choose character",
                "Select exactly one player first.",
                parent=self,
            )
            return
        contact_id = selected_contacts[0]
        if not self.character_label_to_id:
            messagebox.showinfo(
                "Choose character",
                "No characters are available in the shared world data.",
                parent=self,
            )
            return
        picker = tk.Toplevel(self)
        picker.title("Choose Character")
        picker.transient(self)
        picker.geometry("560x520")
        picker.minsize(420, 360)
        picker.configure(background=self.PAPER)
        picker.grab_set()

        body = ttk.Frame(picker, padding=18)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Choose Character", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            body,
            text="Search by character name. Choosing a result links it immediately.",
            style="Card.TLabel",
        ).pack(anchor="w", pady=(2, 10))
        search_value = tk.StringVar()
        search = ttk.Entry(body, textvariable=search_value)
        search.pack(fill="x", pady=(0, 10))

        results_frame = ttk.Frame(body)
        results_frame.pack(fill="both", expand=True)
        results = tk.Listbox(
            results_frame,
            exportselection=False,
            background="#fff8e6",
            foreground=self.INK,
            selectbackground=self.ACCENT,
            selectforeground="#fff8e7",
        )
        scrollbar = ttk.Scrollbar(results_frame, orient="vertical", command=results.yview)
        results.configure(yscrollcommand=scrollbar.set)
        results.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        match_label = ttk.Label(body, text="", style="Status.TLabel")
        match_label.pack(anchor="w", pady=(8, 0))
        visible: list[tuple[str, str]] = []

        def populate(*_args: object) -> None:
            query = search_value.get().strip().casefold()
            visible.clear()
            visible.extend(
                (label, character_id)
                for label, character_id in self.character_label_to_id.items()
                if not query or query in label.casefold()
            )
            results.delete(0, "end")
            selected_index = None
            for index, (label, character_id) in enumerate(visible):
                results.insert("end", label)
                if character_id == self.selected_character_id:
                    selected_index = index
            if selected_index is not None:
                results.selection_set(selected_index)
                results.see(selected_index)
            match_label.configure(text=f"{len(visible)} character(s) shown")

        def accept(_event: tk.Event | None = None) -> None:
            selection = results.curselection()
            if not selection:
                return
            label, character_id = visible[selection[0]]
            self._set_character_selection(character_id)
            picker.destroy()
            self._api_action(
                "PUT",
                f"/api/admin/contacts/{contact_id}/character",
                {"character_id": character_id},
                f"{label} linked to player",
            )

        search_value.trace_add("write", populate)
        search.bind("<Return>", lambda _event: results.focus_set())
        results.bind("<Double-Button-1>", accept)
        results.bind("<Return>", accept)
        buttons = ttk.Frame(body)
        buttons.pack(fill="x", pady=(12, 0))
        ttk.Button(
            buttons, text="Cancel", style="Quiet.TButton", command=picker.destroy
        ).pack(side="right")
        ttk.Button(buttons, text="Choose and Link", command=accept).pack(
            side="right", padx=(0, 8)
        )
        populate()
        search.focus_set()

    def _contact_selected(self, _event: tk.Event | None = None) -> None:
        selected = list(self.contacts_tree.selection())
        if len(selected) != 1:
            self._set_character_selection(None)
            return
        contact = next(
            (item for item in self.state_data.get("contacts", []) if item["id"] == selected[0]),
            None,
        )
        if not contact or not contact.get("character_id"):
            self._set_character_selection(None)
            return
        self._set_character_selection(contact["character_id"])

    def clear_character_link(self) -> None:
        selected = list(self.contacts_tree.selection())
        if len(selected) != 1:
            messagebox.showwarning(
                "Clear character link", "Select exactly one player first.", parent=self
            )
            return
        self._api_action(
            "PUT",
            f"/api/admin/contacts/{selected[0]}/character",
            {"character_id": None},
            "Character identity cleared",
        )

    def create_session(self) -> None:
        contacts = self.state_data.get("contacts", [])
        if not contacts:
            messagebox.showwarning(
                "Create session", "Add players before creating a session.", parent=self
            )
            return
        campaigns = list(self.state_data.get("campaigns", []))
        if not campaigns:
            messagebox.showwarning(
                "Create session",
                "Create a campaign in Campaigner before starting a Game Board session.",
                parent=self,
            )
            return
        dialog = tk.Toplevel(self)
        dialog.title("Create Session")
        dialog.transient(self)
        dialog.geometry("650x590")
        dialog.minsize(520, 470)
        dialog.configure(background=self.PAPER)
        dialog.grab_set()

        body = ttk.Frame(dialog, padding=18)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Create Session", style="Title.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 12)
        )
        title_value = tk.StringVar()
        expiration_value = tk.StringVar(value="23:59")
        field_labels = (
            ("Session title", 0),
            ("Event date", 1),
            ("Invitations expire", 2),
        )
        for label, column in field_labels:
            ttk.Label(body, text=label, style="Card.TLabel").grid(
                row=1, column=column, sticky="w", padx=(0 if column == 0 else 8, 0)
            )
            body.columnconfigure(column, weight=2 if column == 0 else 1)
        ttk.Entry(body, textvariable=title_value).grid(row=2, column=0, sticky="ew")
        event_date_field = CalendarDateField(body, date.today())
        event_date_field.grid(row=2, column=1, sticky="ew", padx=(8, 0))
        ttk.Entry(body, textvariable=expiration_value, width=8).grid(
            row=2, column=2, sticky="ew", padx=(8, 0)
        )
        ttk.Label(body, text="Campaign", style="Card.TLabel").grid(
            row=3, column=0, columnspan=3, sticky="w", pady=(10, 0)
        )
        selected_campaign_id = tk.StringVar(
            value=campaigns[0]["record_id"] if len(campaigns) == 1 else ""
        )
        selected_campaign_text = tk.StringVar(
            value=(
                f"{campaigns[0]['name']} — starts "
                f"{format_game_world_date(campaigns[0]['game_world_start_date'])} at 08:00"
                if len(campaigns) == 1
                else "No campaign chosen"
            )
        )
        campaign_row = ttk.Frame(body)
        campaign_row.grid(row=4, column=0, columnspan=3, sticky="ew")
        campaign_row.columnconfigure(0, weight=1)
        ttk.Label(
            campaign_row,
            textvariable=selected_campaign_text,
            style="Card.TLabel",
            relief="solid",
            padding=(7, 5),
        ).grid(row=0, column=0, sticky="ew")

        def choose_campaign() -> None:
            picker = tk.Toplevel(dialog)
            picker.title("Choose Campaign")
            picker.transient(dialog)
            picker.grab_set()
            picker.geometry("520x420")
            picker.configure(background=self.PAPER)
            shell = ttk.Frame(picker, padding=12)
            shell.pack(fill="both", expand=True)
            ttk.Label(
                shell,
                text="Search campaigns",
                style="Card.TLabel",
            ).pack(anchor="w")
            query = tk.StringVar()
            entry = ttk.Entry(shell, textvariable=query)
            entry.pack(fill="x", pady=(3, 7))
            results = tk.Listbox(
                shell,
                exportselection=False,
                background="#fff8e6",
                foreground=self.INK,
                selectbackground=self.ACCENT,
                selectforeground="#fff8e7",
            )
            results.pack(fill="both", expand=True)
            visible: list[dict[str, Any]] = []

            def redraw(*_args) -> None:
                needle = query.get().strip().casefold()
                visible[:] = [
                    item for item in campaigns if needle in item["name"].casefold()
                ]
                results.delete(0, "end")
                for campaign in visible:
                    results.insert(
                        "end",
                        f"{campaign['name']} — starts "
                        f"{format_game_world_date(campaign['game_world_start_date'])} at 08:00",
                    )
                if visible:
                    results.selection_set(0)

            def accept(_event: tk.Event | None = None) -> None:
                selected = results.curselection()
                if not selected:
                    return
                campaign = visible[selected[0]]
                selected_campaign_id.set(campaign["record_id"])
                selected_campaign_text.set(
                    f"{campaign['name']} — starts "
                    f"{format_game_world_date(campaign['game_world_start_date'])} at 08:00"
                )
                picker.destroy()

            query.trace_add("write", redraw)
            results.bind("<Double-Button-1>", accept)
            results.bind("<Return>", accept)
            actions = ttk.Frame(shell)
            actions.pack(fill="x", pady=(7, 0))
            ttk.Button(actions, text="Cancel", style="Quiet.TButton", command=picker.destroy).pack(side="right")
            ttk.Button(actions, text="Choose", command=accept).pack(side="right", padx=(0, 6))
            redraw()
            entry.focus_set()

        ttk.Button(
            campaign_row,
            text="Choose Campaign…",
            style="Quiet.TButton",
            command=choose_campaign,
        ).grid(row=0, column=1, padx=(8, 0))

        ttk.Label(body, text="Players", style="Section.TLabel").grid(
            row=5, column=0, columnspan=3, sticky="w", pady=(16, 6)
        )
        roster_frame = ttk.Frame(body)
        roster_frame.grid(row=6, column=0, columnspan=3, sticky="nsew")
        body.rowconfigure(6, weight=1)
        roster = tk.Listbox(
            roster_frame,
            exportselection=False,
            background="#fff8e6",
            foreground=self.INK,
            selectbackground=self.ACCENT,
            selectforeground="#fff8e7",
        )
        roster_scroll = ttk.Scrollbar(roster_frame, orient="vertical", command=roster.yview)
        roster.configure(yscrollcommand=roster_scroll.set)
        roster.pack(side="left", fill="both", expand=True)
        roster_scroll.pack(side="right", fill="y")
        contact_ids = [contact["id"] for contact in contacts]
        checked: set[str] = set(contact_ids)

        def redraw() -> None:
            focused = roster.curselection()
            roster.delete(0, "end")
            for contact in contacts:
                identity = contact.get("character_name") or "No character linked"
                roster.insert(
                    "end",
                    f"{'✓' if contact['id'] in checked else ' '}  {contact['name']}  —  {identity}",
                )
            if focused and focused[0] < roster.size():
                roster.selection_set(focused[0])

        def toggle(_event: tk.Event | None = None) -> str:
            selection = roster.curselection()
            if not selection:
                return "break"
            contact_id = contact_ids[selection[0]]
            if contact_id in checked:
                checked.remove(contact_id)
            else:
                checked.add(contact_id)
            redraw()
            return "break"

        roster.bind("<ButtonRelease-1>", toggle)
        roster.bind("<space>", toggle)
        roster.bind("<Return>", toggle)
        redraw()

        selection_row = ttk.Frame(body)
        selection_row.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        ttk.Button(
            selection_row, text="Check All", style="Quiet.TButton",
            command=lambda: (checked.update(contact_ids), redraw()),
        ).pack(side="left")
        ttk.Button(
            selection_row, text="Clear", style="Quiet.TButton",
            command=lambda: (checked.clear(), redraw()),
        ).pack(side="left", padx=8)

        buttons = ttk.Frame(body)
        buttons.grid(row=8, column=0, columnspan=3, sticky="e", pady=(16, 0))
        ttk.Button(buttons, text="Cancel", style="Quiet.TButton", command=dialog.destroy).pack(
            side="left", padx=(0, 8)
        )

        def submit() -> None:
            if not checked:
                messagebox.showwarning(
                    "Create session", "Check at least one player.", parent=dialog
                )
                return
            if not selected_campaign_id.get():
                messagebox.showwarning(
                    "Create session", "Choose a campaign.", parent=dialog
                )
                return
            payload = {
                "title": title_value.get().strip(),
                "campaign_id": selected_campaign_id.get(),
                "event_date": event_date_field.get_iso(),
                "game_day": event_date_field.get_iso(),
                "expiration_time": expiration_value.get().strip(),
                "contact_ids": [contact_id for contact_id in contact_ids if contact_id in checked],
            }

            def done(result: dict[str, Any]) -> None:
                self.selected_session_id = result["id"]
                self.selected_invite_ids.clear()
                dialog.destroy()
                self.set_notice("Session created")
                self.refresh()

            self._background(
                lambda: self.client.request("POST", "/api/admin/sessions", payload), done
            )

        ttk.Button(buttons, text="Create Session", command=submit).pack(side="left")
        dialog.bind("<Escape>", lambda _event: dialog.destroy())

    def send_invites(self, all_players: bool) -> None:
        if self.sending_invitations:
            self.set_notice("An invitation batch is already being sent")
            return
        session = self._selected_session()
        if not session:
            messagebox.showwarning("Invitations", "Select a session first.", parent=self)
            return
        ids = (
            [player["contact_id"] for player in session["roster"] if not player.get("revoked")]
            if all_players else list(self.selected_invite_ids)
        )
        if not ids:
            messagebox.showwarning("Invitations", "Select at least one player.", parent=self)
            return

        self.sending_invitations = True
        self.send_selected_button.configure(state="disabled")
        self.send_all_button.configure(state="disabled")
        self.set_notice(f"Sending {len(ids)} invitation(s)…")

        def done(result: dict[str, Any]) -> None:
            self.sending_invitations = False
            self.send_selected_button.configure(state="normal")
            self.send_all_button.configure(state="normal")
            if result.get("_client_error"):
                self.set_notice(str(result["_client_error"]), error=True)
                messagebox.showerror("Send invitations", str(result["_client_error"]), parent=self)
                return
            results = list(result.get("results", []))
            failures = [item for item in results if not item.get("success")]
            sent = len(results) - len(failures)
            message = f"{sent} invitation(s) sent"
            if failures:
                message += f"; {len(failures)} failed"
            self.set_notice(message, error=bool(failures))
            if failures:
                roster_names = {
                    player["contact_id"]: player.get("name") or player["contact_id"]
                    for player in session.get("roster", [])
                }
                details = "\n".join(
                    f"{roster_names.get(item.get('contact_id'), item.get('contact_id'))}: "
                    f"{item.get('error') or 'Unknown Gmail error'}"
                    for item in failures
                )
                messagebox.showerror(
                    "Invitation delivery failed",
                    f"{message}.\n\n{details}",
                    parent=self,
                )
            self.refresh()

        payload = {"session_id": session["id"], "contact_ids": ids}

        def work() -> dict[str, Any]:
            try:
                return self.client.request(
                    "POST",
                    "/api/admin/invitations/send",
                    payload,
                    timeout=max(120, 75 * len(ids)),
                )
            except Exception as error:
                return {"_client_error": str(error)}

        self._background(work, done)

    def duplicate_session(self) -> None:
        session = self._selected_session()
        if not session:
            messagebox.showwarning("Duplicate session", "Select a session first.", parent=self)
            return

        def done(result: dict[str, Any]) -> None:
            self.selected_session_id = result["id"]
            self.selected_invite_ids.clear()
            self.set_notice("Session duplicated")
            self.refresh()

        self._background(
            lambda: self.client.request(
                "POST", f"/api/admin/sessions/{session['id']}/duplicate"
            ),
            done,
        )

    def delete_session(self) -> None:
        session = self._selected_session()
        if not session:
            return
        if not messagebox.askyesno(
            "Delete session",
            f"Permanently delete {session['title']} without retaining a summary?",
            parent=self,
        ):
            return
        self._api_action(
            "DELETE", f"/api/admin/sessions/{session['id']}", None, "Session deleted"
        )

    def remove_from_session(self) -> None:
        session = self._selected_session()
        contact_ids = list(self.selected_invite_ids)
        if not session or not contact_ids:
            messagebox.showwarning(
                "Remove from session", "Check one or more players first.", parent=self
            )
            return
        if not messagebox.askyesno(
            "Remove from session",
            f"Remove {len(contact_ids)} checked player(s) from {session['title']}?",
            parent=self,
        ):
            return

        def work() -> None:
            for contact_id in contact_ids:
                self.client.request(
                    "DELETE",
                    f"/api/admin/sessions/{session['id']}/players/{contact_id}",
                )

        def done(_result: Any) -> None:
            self.selected_invite_ids.clear()
            self.set_notice(f"Removed {len(contact_ids)} player(s) from the session")
            self.refresh()

        self._background(work, done)

    def resolve_pending(self, action: str) -> None:
        selected = list(self.pending_tree.selection())
        if not selected:
            return
        result_word = "approved" if action == "approve" else "denied"
        for request_id in selected:
            self._api_action("POST", f"/api/admin/admissions/{request_id}/{action}", None, f"Admission {result_word}")

    def admit_all_pending(self) -> None:
        request_ids = list(self.pending_tree.get_children())
        if not request_ids:
            messagebox.showinfo("Admit all", "No players are currently waiting.", parent=self)
            return

        def work() -> None:
            for request_id in request_ids:
                self.client.request("POST", f"/api/admin/admissions/{request_id}/approve")

        self._background(
            work,
            lambda _value: (self.set_notice(f"Admitted {len(request_ids)} player(s)"), self.refresh()),
        )

    def revoke_connected(self) -> None:
        selected = list(self.connections_tree.selection())
        if not selected:
            return
        if not messagebox.askyesno("Revoke access", "Revoke and disconnect the selected players?", parent=self):
            return
        for connection_id in selected:
            session_id, contact_id = connection_id.split(":", 1)
            self._api_action(
                "POST",
                f"/api/admin/sessions/{session_id}/players/{contact_id}/revoke",
                None,
                "Player disconnected",
            )

    def end_session(self) -> None:
        session = self._selected_session()
        if not session:
            return
        if messagebox.askyesno(
            "End session",
            f"End {session['title']}, disconnect its players, and retain its summary?",
            parent=self,
        ):
            self._api_action(
                "POST", f"/api/admin/sessions/{session['id']}/end", None, "Session ended"
            )

    def send_announcement(self) -> None:
        text = self.announcement.get("1.0", "end").strip()
        if not text:
            return
        self._api_action(
            "POST", "/api/admin/announcements",
            {"message": text, "session_id": self.selected_session_id},
            "Announcement sent",
        )
        self.announcement.delete("1.0", "end")

    def _render_chat(self, messages: list[dict[str, Any]]) -> None:
        message_ids = tuple(str(item.get("id", "")) for item in messages)
        if message_ids == self._rendered_chat_ids:
            return
        self._last_chat_messages = deepcopy(messages)
        self._rendered_chat_ids = message_ids
        self.chat_log.configure(state="normal")
        self.chat_log.delete("1.0", "end")
        self._chat_roll_ranges = []
        for message_number, message in enumerate(messages):
            message_id = str(message.get("id") or f"message-{message_number}")
            start = self.chat_log.index("end-1c")
            stamp = str(message.get("sent_at", ""))[11:16] or "--:--"
            role = message.get("sender_role") if message.get("sender_role") in {"headmaster", "system"} else "player"
            activity = message.get("activity")
            outcome = str((activity or {}).get("outcome") or "")
            outcome_tag = outcome if outcome in {
                "critical_failure", "failure", "success", "critical_success"
            } else None
            header_tags = (role, outcome_tag) if outcome_tag else (role,)
            body_tags = ("message_body", outcome_tag) if outcome_tag else ("message_body",)
            self.chat_log.insert(
                "end", f"{message.get('sender_name', 'Player')}  {stamp}\n",
                header_tags,
            )
            self.chat_log.insert(
                "end", f"{message.get('text', '')}\n", body_tags,
            )
            if isinstance(activity, dict):
                summary_start = self.chat_log.index("end-1c")
                expanded = message_id in self._expanded_chat_roll_ids
                self.chat_log.insert(
                    "end",
                    f"  {activity.get('target_name') or 'Roll'} · {activity.get('total', 0)}  {'▴' if expanded else '▾'}  \n",
                    ("roll_summary", outcome_tag) if outcome_tag else ("roll_summary",),
                )
                summary_end = self.chat_log.index("end-1c")
                self._chat_roll_ranges.append(
                    (summary_start, summary_end, summary_end, message_id)
                )
                self.chat_log.tag_add("roll", summary_start, summary_end)
                self.chat_log.tag_configure("roll", underline=False)
                self.chat_log.tag_bind(
                    "roll", "<Enter>",
                    lambda _event: self.chat_log.configure(cursor="hand2"),
                )
                self.chat_log.tag_bind(
                    "roll", "<Leave>",
                    lambda _event: self.chat_log.configure(cursor="xterm"),
                )
                if expanded:
                    self._insert_inline_roll_details(activity, outcome_tag)
                detail_end = self.chat_log.index("end-1c")
                self._chat_roll_ranges[-1] = (
                    summary_start, summary_end, detail_end, message_id
                )
            end = self.chat_log.index("end-1c")
            self.chat_log.insert("end", "\n")
        self.chat_log.configure(state="disabled")
        focus_range = next(
            ((start, detail_end) for start, _summary_end, detail_end, roll_id
             in self._chat_roll_ranges
             if roll_id == self._chat_focus_roll_id),
            None,
        )
        if focus_range:
            focus_start, focus_end = focus_range
            self.chat_log.see(focus_start)
            self.chat_log.see(focus_end)
        else:
            self.chat_log.see("end")
        self._chat_focus_roll_id = ""

    def _insert_inline_roll_details(
        self, activity: dict[str, Any], outcome_tag: str | None
    ) -> None:
        detail_tags = ("roll_detail", outcome_tag) if outcome_tag else ("roll_detail",)
        source_tags = ("roll_source", outcome_tag) if outcome_tag else ("roll_source",)
        total_tags = ("roll_total", outcome_tag) if outcome_tag else ("roll_total",)
        for component in activity.get("components", []) or []:
            if not isinstance(component, dict):
                continue
            self.chat_log.insert(
                "end",
                f"  {component.get('label') or 'Value'}\t{component.get('value', 0)}\n",
                detail_tags,
            )
            for source in component.get("sources", []) or []:
                if not isinstance(source, dict):
                    continue
                self.chat_log.insert(
                    "end",
                    f"  ↳ {source.get('label') or 'Source'}\t{source.get('value', 0)}\n",
                    source_tags,
                )
        if activity.get("threshold") is not None:
            self.chat_log.insert(
                "end", f"  Threshold\t{activity['threshold']}\n", detail_tags
            )
        self.chat_log.insert(
            "end", f"  TOTAL\t{activity.get('total', 0)}\n", total_tags
        )

    def _inspect_chat_roll(self, event: tk.Event) -> str | None:
        index = self.chat_log.index(f"@{event.x},{event.y}")
        for start, end, _detail_end, roll_id in self._chat_roll_ranges:
            if self.chat_log.compare(index, ">=", start) and self.chat_log.compare(index, "<", end):
                if roll_id in self._expanded_chat_roll_ids:
                    self._expanded_chat_roll_ids.remove(roll_id)
                else:
                    self._expanded_chat_roll_ids.add(roll_id)
                self._chat_focus_roll_id = roll_id
                self._rendered_chat_ids = ()
                self._render_chat(self._last_chat_messages)
                return "break"
        return None

    def send_chat(self) -> None:
        message = self.chat_entry.get().strip()
        if not message:
            return

        def done(_result: Any) -> None:
            self.chat_entry.delete(0, "end")
            self.set_notice("Chat message sent")
            self.refresh()

        self._background(
            lambda: self.client.request(
                "POST", "/api/admin/chat",
                {"message": message, "session_id": self.selected_session_id},
            ),
            done,
        )

    def save_settings(self) -> None:
        payload = {key: entry.get().strip() for key, entry in self.setting_entries.items()}

        def work() -> Any:
            return self._save_settings_on_server(payload)

        def done(_result: Any) -> None:
            self.settings_dirty = False
            self.set_notice("Settings saved; the local communication service was refreshed")
            self.refresh()

        self._background(work, done)

    def _save_settings_on_server(self, payload: dict[str, str]) -> Any:
        result = self.client.request("PUT", "/api/admin/settings", payload)
        if self.server.process is not None:
            self.server.stop()
            self.server.start()
        return result

    def connect_gmail(self) -> None:
        self.set_notice("Complete Google authorization in the browser window.")
        payload = {
            "credentials_path": self.setting_entries["gmail_credentials_path"].get().strip(),
            "sender": self.setting_entries["gmail_sender"].get().strip(),
        }

        def work() -> Any:
            return self.client.request("POST", "/api/admin/gmail/authorize", payload, timeout=300)

        def done(_result: Any) -> None:
            self.set_notice("Gmail connected")
            self.refresh()

        self._background(work, done)

    def close(self) -> None:
        self.closing = True
        for after_id in list(self._board_camera_save_after_ids.values()):
            try:
                self.after_cancel(after_id)
            except tk.TclError:
                pass
        self._board_camera_save_after_ids.clear()
        for map_id in list(self.board_view_states):
            try:
                self._save_board_camera(map_id, synchronous=True)
            except Exception:
                # A previously debounced save normally already holds this view;
                # shutdown must still be allowed if the local service has stopped.
                pass
        self.server.stop()
        self.destroy()


def main() -> None:
    configure_windows_app_id("GameBoard")
    GameBoardWindow().mainloop()


if __name__ == "__main__":
    main()
