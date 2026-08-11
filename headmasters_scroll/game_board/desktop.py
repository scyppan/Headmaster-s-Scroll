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
import urllib.request
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk
from typing import Any, Callable
from uuid import uuid4

from PIL import Image, ImageDraw, ImageOps, ImageTk

from ..assets import AssetStore, MAP_CANVAS_HEIGHT, MAP_CANVAS_WIDTH, MAP_CANVAS_SIZE
from ..board import WorldBoardRepository
from ..campaigns import format_game_world_date
from ..paths import PROJECT_ROOT
from ..windowing import GAME_BOARD_ICON, apply_window_icon, configure_windows_app_id, maximize_window
from .storage import GameBoardRepository


DATE_DISPLAY_FORMAT = "%d %b %Y"
GAME_DATETIME_DISPLAY_FORMAT = "%d %b %Y  %H:%M"
GAME_DATETIME_RE = re.compile(
    r"^(?P<year>-?[1-9]\d*)-(?P<month>\d{2})-(?P<day>\d{2})T"
    r"(?P<hour>\d{2}):(?P<minute>\d{2})$"
)


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


class LocalServer:
    """Starts the communication engine when the desktop app owns it."""

    def __init__(self, client: AdminClient):
        self.client = client
        self.process: subprocess.Popen | None = None

    def ready(self) -> bool:
        try:
            self.client.state()
            return True
        except Exception:
            return False

    def start(self, timeout: float = 12.0) -> None:
        if self.ready():
            return
        creation_flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        self.process = subprocess.Popen(
            [sys.executable, "-B", "-m", "headmasters_scroll.game_board.server"],
            cwd=PROJECT_ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creation_flags,
        )
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.ready():
                return
            if self.process.poll() is not None:
                break
            time.sleep(0.2)
        raise RuntimeError(
            "The Game Board communication service could not start. "
            "Install the optional dependencies with: python -m pip install -e .[game-board]"
        )

    def stop(self) -> None:
        if self.process is None or self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=4)
        except subprocess.TimeoutExpired:
            self.process.kill()


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
        self.board_map_label_to_id: dict[str, str] = {}
        self.board_open_map_ids: list[str] = []
        self.board_map_drafts: dict[str, dict[str, Any]] = {}
        self.board_view_states: dict[str, dict[str, float | bool]] = {}
        self.selected_board_map_id = ""
        self.selected_board_actor_id = ""
        self._board_image: ImageTk.PhotoImage | None = None
        self._board_portraits: dict[str, ImageTk.PhotoImage] = {}
        self._board_canvas_actors: dict[tuple[str, int], str] = {}
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
        self._piece_popup: tk.Toplevel | None = None
        self.board_map_controls_window: tk.Toplevel | None = None
        self.board_settings_window: tk.Toplevel | None = None
        self._known_pending_ids: set[str] = set()
        self.title("Game Board — Headmaster Controls")
        self.geometry("1240x800")
        self.minsize(760, 520)
        self.configure(background=self.PAPER)
        apply_window_icon(self, GAME_BOARD_ICON)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self._configure_style()
        self._build()
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
        for key, label in (("game-board", "Game Board"), ("control-panel", "Control Panel")):
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
        self.app_pages = {"game-board": game_board_page, "control-panel": control_panel}
        control_header = ttk.Frame(control_panel)
        control_header.pack(fill="x", pady=(0, 8))
        ttk.Label(control_header, text="Control Panel", style="Title.TLabel").pack(side="left")
        self.control_section_label = ttk.Label(
            control_header, text="Live Room", style="Status.TLabel"
        )
        self.control_section_label.pack(side="right", pady=10)

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

        footer = ttk.Frame(self)
        footer.pack(fill="x", padx=12, pady=(0, 8))
        self.notice = tk.Label(footer, text="Starting…", background=self.PAPER, foreground=self.MUTED)
        self.notice.pack(side="left")
        ttk.Button(footer, text="Refresh", style="Quiet.TButton", command=self.refresh).pack(side="right")

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
            detail = "Default map"
            if record.get("is_floor_primary") and floor:
                detail = f"Default map ({floor})"
            return f"{location}  —  {detail}"
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

        self._create_board_map_controls()

        self.board_notebook = ttk.Notebook(board_panel)
        self.board_notebook.pack(fill="both", expand=True)
        self.board_notebook.bind("<<NotebookTabChanged>>", self._board_tab_changed)
        self.board_empty = ttk.Label(
            board_panel,
            text="Search for a map above or use Explore to add one to the Game Board.",
            style="Card.TLabel",
            anchor="center",
        )
        self.board_canvases: dict[str, tk.Canvas] = {}
        self.board_canvas_geometry: dict[str, tuple[float, float, float, float]] = {}
        self.board_map_images: dict[str, ImageTk.PhotoImage] = {}
        self.board_map_ids: tuple[str, ...] = ()
        self._board_preview_after: str | None = None
        self.board_actor_tree: ttk.Treeview | None = None
        self.board_transfer_map: ttk.Combobox | None = None
        self.occupants_dialog: tk.Toplevel | None = None
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

    def _create_board_map_controls(self) -> None:
        window = tk.Toplevel(self)
        self.board_map_controls_window = window
        window.title("Map Tools")
        window.resizable(False, False)
        window.configure(background=self.PAPER)
        window.protocol("WM_DELETE_WINDOW", self.hide_board_map_controls)
        window.bind("<Unmap>", self._board_tools_unmapped)
        apply_window_icon(window, GAME_BOARD_ICON)
        map_controls = ttk.Frame(window, style="Card.TFrame", padding=8)
        map_controls.pack(fill="both", expand=True)
        ttk.Label(
            map_controls,
            text="MAP CONTROLS",
            style="Card.TLabel",
            font=("Segoe UI", 8, "bold"),
        ).pack(fill="x", pady=(0, 5))
        self.board_obscure_button = ttk.Button(
            map_controls,
            text="Draw obfuscation  [O]",
            command=self.start_board_obscuration_drawing,
        )
        self.board_obscure_button.pack(fill="x", pady=(0, 3))
        self.board_reveal_value = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            map_controls,
            text="Reveal",
            variable=self.board_reveal_value,
            command=self.board_presentation_changed,
        ).pack(anchor="w", pady=(1, 5))
        ttk.Label(
            map_controls,
            text="OBFUSCATIONS",
            style="Card.TLabel",
            font=("Segoe UI", 8, "bold"),
        ).pack(fill="x", pady=(5, 2))
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
        ttk.Button(map_controls, text="Delete obfuscation", style="Quiet.TButton", command=self.delete_board_obscuration).pack(fill="x", pady=(0, 3))
        ttk.Button(map_controls, text="Fit map", style="Quiet.TButton", command=self.fit_current_board_map).pack(fill="x", pady=(0, 3))
        ttk.Button(map_controls, text="Remove map", style="Quiet.TButton", command=self.remove_current_board_map).pack(fill="x", pady=(0, 6))
        self.board_confirm_button = ttk.Button(map_controls, text="Confirm to players", style="Good.TButton", command=self.confirm_board_presentation)
        self.board_confirm_button.pack(fill="x")
        self.board_draft_status = tk.Label(
            map_controls,
            text="",
            anchor="w",
            justify="left",
            background=self.LIGHT,
            foreground=self.MUTED,
            wraplength=216,
            font=("Segoe UI", 8, "bold"),
        )
        self.board_draft_status.pack(fill="x", pady=(5, 0))
        window.update_idletasks()
        width = max(240, window.winfo_reqwidth())
        height = max(390, window.winfo_reqheight())
        window.geometry(
            f"{width}x{height}+{self.winfo_rootx() + 230}+{self.winfo_rooty() + 110}"
        )
        window.minsize(width, height)
        window.maxsize(width, height)

    def open_board_map_controls(self) -> None:
        window = self.board_map_controls_window
        if window is None or not window.winfo_exists():
            self._create_board_map_controls()
            window = self.board_map_controls_window
        if window is None:
            return
        window.deiconify()
        window.lift()

    def hide_board_map_controls(self) -> None:
        window = self.board_map_controls_window
        if self.board_obscure_drawing:
            if window is not None and window.winfo_exists():
                window.deiconify()
                window.lift()
            self.bell()
            self.board_draft_status.configure(
                text="Finish or cancel the current obfuscation before hiding Map Tools.",
                foreground=self.RED,
            )
            return
        if window is not None and window.winfo_exists():
            window.withdraw()

    def _board_tools_unmapped(self, _event: tk.Event | None = None) -> None:
        if not self.board_obscure_drawing or self.state() == "iconic":
            return
        self.after(50, self.open_board_map_controls)

    def open_occupants_dialog(self) -> None:
        if self.occupants_dialog is not None and self.occupants_dialog.winfo_exists():
            self.occupants_dialog.lift()
            return
        dialog = tk.Toplevel(self)
        self.occupants_dialog = dialog
        dialog.title("Game Board Occupants")
        dialog.transient(self)
        dialog.geometry("620x650")
        dialog.minsize(500, 500)
        dialog.configure(background=self.PAPER)
        apply_window_icon(dialog, GAME_BOARD_ICON)
        dialog.protocol("WM_DELETE_WINDOW", self._close_occupants_dialog)
        shell = ttk.Frame(dialog, style="Card.TFrame", padding=14)
        shell.pack(fill="both", expand=True, padx=10, pady=10)
        ttk.Label(shell, text="Occupants", style="Section.TLabel").pack(anchor="w")
        self.board_actor_tree = ttk.Treeview(
            shell,
            columns=("name", "display", "visibility"),
            show="headings",
            selectmode="browse",
            height=14,
        )
        for column, label, width in (
            ("name", "Character", 145),
            ("display", "Piece", 70),
            ("visibility", "Players", 70),
        ):
            self.board_actor_tree.heading(column, text=label)
            self.board_actor_tree.column(column, width=width, minwidth=55, anchor="w")
        self.board_actor_tree.pack(fill="both", expand=True, pady=(6, 10))
        self.board_actor_tree.bind("<<TreeviewSelect>>", self._board_actor_selected)

        ttk.Label(shell, text="Move to map", style="Card.TLabel").pack(anchor="w")
        self.board_transfer_map = ttk.Combobox(shell, state="readonly")
        self.board_transfer_map.pack(fill="x", pady=(2, 5))
        ttk.Button(
            shell,
            text="Move selected to map centre",
            command=self.transfer_selected_actor,
        ).pack(fill="x", pady=(0, 8))

        piece_row = ttk.Frame(shell, style="Card.TFrame")
        piece_row.pack(fill="x", pady=(0, 5))
        ttk.Button(piece_row, text="Dot", style="Quiet.TButton", command=lambda: self.update_selected_actor(display_mode="dot")).pack(side="left", fill="x", expand=True)
        ttk.Button(piece_row, text="Portrait", command=lambda: self.update_selected_actor(display_mode="token")).pack(side="left", fill="x", expand=True, padx=(5, 0))
        visibility_row = ttk.Frame(shell, style="Card.TFrame")
        visibility_row.pack(fill="x", pady=(0, 5))
        ttk.Button(visibility_row, text="Hide", style="Quiet.TButton", command=lambda: self.update_selected_actor(visibility="headmaster")).pack(side="left", fill="x", expand=True)
        ttk.Button(visibility_row, text="Reveal", style="Good.TButton", command=lambda: self.update_selected_actor(visibility="players")).pack(side="left", fill="x", expand=True, padx=(5, 0))
        identity_row = ttk.Frame(shell, style="Card.TFrame")
        identity_row.pack(fill="x", pady=(0, 8))
        ttk.Button(identity_row, text="Toggle name", style="Quiet.TButton", command=self.toggle_selected_name).pack(side="left", fill="x", expand=True)
        ttk.Button(identity_row, text="Toggle faction", style="Quiet.TButton", command=self.toggle_selected_faction).pack(side="left", fill="x", expand=True, padx=(5, 0))

        ttk.Button(shell, text="Select displayed faction", command=self.select_actor_faction).pack(fill="x", pady=(0, 5))
        ttk.Button(shell, text="Grant player control…", command=self.grant_actor_control).pack(fill="x", pady=(0, 5))
        ttk.Button(shell, text="Join or leave group…", command=self.manage_actor_group).pack(fill="x", pady=(0, 5))
        ttk.Button(shell, text="Create group…", command=self.create_board_group).pack(fill="x")
        map_labels = list(self.board_map_label_to_id)
        self.board_transfer_map.configure(values=map_labels)
        if map_labels:
            current_label = next(
                (
                    label
                    for label, map_id in self.board_map_label_to_id.items()
                    if map_id == self.selected_board_map_id
                ),
                map_labels[0],
            )
            self.board_transfer_map.set(current_label)
        self._render_board_actor_list()
        if self.selected_board_actor_id and self.board_actor_tree.exists(self.selected_board_actor_id):
            self.board_actor_tree.selection_set(self.selected_board_actor_id)

    def _close_occupants_dialog(self) -> None:
        dialog = self.occupants_dialog
        self.occupants_dialog = None
        self.board_actor_tree = None
        self.board_transfer_map = None
        if dialog is not None and dialog.winfo_exists():
            dialog.destroy()

    def _board_tab_changed(self, _event: tk.Event | None = None) -> None:
        selected = self.board_notebook.select()
        for map_id, canvas in self.board_canvases.items():
            if str(canvas.master) == str(selected):
                self.selected_board_map_id = map_id
                break
        self.cancel_board_obscuration()
        self._sync_board_presentation_controls()
        self._render_board_actor_list()

    def _current_board_map(self) -> dict[str, Any] | None:
        return next(
            (item for item in self.board_snapshot.get("maps", []) if item.get("record_id") == self.selected_board_map_id),
            None,
        )

    def _render_board(self, snapshot: dict[str, Any]) -> None:
        self.board_snapshot = snapshot or {}
        all_maps = list(self.board_snapshot.get("maps", []))
        valid_ids = {str(item.get("record_id")) for item in all_maps}
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
                canvas.bind("<Configure>", lambda _event, selected=map_id: self._board_canvas_configured(selected))
                canvas.bind("<ButtonPress-1>", lambda event, selected=map_id: self._board_pointer_start(event, selected))
                canvas.bind("<B1-Motion>", lambda event, selected=map_id: self._board_drag_move(event, selected))
                canvas.bind("<ButtonRelease-1>", lambda event, selected=map_id: self._board_drag_end(event, selected))
                canvas.bind("<Double-Button-1>", lambda event, selected=map_id: self.complete_board_obscuration(event, selected))
                canvas.bind("<Button-3>", lambda event, selected=map_id: self._board_piece_menu(event, selected))
                canvas.bind("<Motion>", lambda event, selected=map_id: self.board_obscure_motion(event, selected))
                canvas.bind("<Leave>", lambda event, selected=map_id: self.board_canvas_leave(event, selected))
                canvas.bind("<Button-2>", lambda event, selected=map_id: self.board_pan_press(event, selected))
                self.board_notebook.add(frame, text=str(record.get("name") or "Map"))
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
            self.board_draft_status.configure(text="No map open", foreground=self.MUTED)
            self.board_confirm_button.configure(text="No changes to send", state="disabled")
            self._refresh_board_obscuration_list()
            return
        self.board_reveal_value.set(bool(draft["published"]))
        self.board_obscure_opacity.set(str(round(float(draft["preview_opacity"]) * 100)))
        self.board_obscure_color = str(draft["preview_color"])
        if draft.get("dirty"):
            self.board_draft_status.configure(
                text="Not sent — these changes are visible only to you.",
                foreground=self.RED,
            )
            self.board_confirm_button.configure(text="Send changes to players", state="normal")
        elif time.monotonic() < self.board_confirmation_message_until:
            self.board_draft_status.configure(
                text="Changes sent to players ✓",
                foreground=self.GREEN,
            )
            self.board_confirm_button.configure(text="Sent ✓", state="disabled")
        else:
            self.board_draft_status.configure(
                text=(
                    "Up to date — players have this version."
                    if draft["published"]
                    else "Up to date — this map is hidden from players."
                ),
                foreground=self.GREEN,
            )
            self.board_confirm_button.configure(text="No changes to send", state="disabled")
        self._refresh_board_obscuration_list()

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
            self.board_obscuration_list.insert(
                "end", f"Obfuscation {index}  —  {node_count} nodes"
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
        self.board_obscure_button.configure(text="Draw obfuscation  [O]")
        canvas = self.board_canvases.get(self.selected_board_map_id)
        if canvas is not None and canvas.winfo_exists():
            canvas.configure(cursor="arrow")
            self._draw_board_map(self.selected_board_map_id)

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
            text="Not sent — these changes are visible only to you.",
            foreground=self.RED,
        )
        self.board_confirm_button.configure(text="Send changes to players", state="normal")
        if self.selected_board_map_id:
            self._draw_board_map(self.selected_board_map_id)

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
            "published": bool(draft["published"]),
            "obscurations": deepcopy(draft["obscurations"]),
            "preview_opacity": float(draft["preview_opacity"]),
            "preview_color": str(draft["preview_color"]),
        }

        def complete(_result: Any) -> None:
            draft["dirty"] = False
            self.board_confirmation_message_until = time.monotonic() + 5.0
            self.board_draft_status.configure(
                text="Changes sent to players ✓",
                foreground=self.GREEN,
            )
            self.board_confirm_button.configure(text="Sent ✓", state="disabled")
            self.refresh(silent=True)
            self.after(5100, self._sync_board_presentation_controls)

        def failed(error: Exception) -> None:
            draft["dirty"] = True
            self.board_draft_status.configure(
                text="Send failed — changes are still only visible to you.",
                foreground=self.RED,
            )
            self.board_confirm_button.configure(text="Try sending again", state="normal")
            self._failed(error, False)

        self.board_draft_status.configure(text="Sending changes…", foreground=self.MUTED)
        self.board_confirm_button.configure(text="Sending…", state="disabled")
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
        width = max(2, canvas.winfo_width())
        height = max(2, canvas.winfo_height())
        state = self.board_view_states.get(map_id)
        if state is None:
            fit_scale = min((width - 24) / MAP_CANVAS_WIDTH, (height - 24) / MAP_CANVAS_HEIGHT)
            state = {
                "fit_scale": fit_scale,
                "scale": fit_scale,
                "origin_x": (width - MAP_CANVAS_WIDTH * fit_scale) / 2,
                "origin_y": (height - MAP_CANVAS_HEIGHT * fit_scale) / 2,
                "modified": False,
            }
            self.board_view_states[map_id] = state
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
        for actor in self.board_snapshot.get("actors", []):
            if actor.get("map_id") != map_id:
                continue
            x = left + float(actor.get("x", 0.5)) * draw_width
            y = top + float(actor.get("y", 0.5)) * draw_height
            actor_id = str(actor.get("actor_id"))
            color = str(actor.get("faction_color") or "#808080")
            selected = actor_id == self.selected_board_actor_id
            if actor.get("display_mode") == "token" and actor.get("portrait_asset_id"):
                try:
                    portrait_path = self.asset_store.resolve(str(actor["portrait_asset_id"]))
                    with Image.open(portrait_path) as opened:
                        portrait = opened.convert("RGB").resize((52, 52), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(portrait)
                    self._board_portraits[actor_id] = photo
                    canvas.create_oval(x - 30, y - 30, x + 30, y + 30, fill=color, outline="#fff3cf" if selected else self.INK, width=4 if selected else 2)
                    item = canvas.create_image(x, y, image=photo)
                except (FileNotFoundError, OSError, ValueError):
                    item = canvas.create_oval(x - 11, y - 11, x + 11, y + 11, fill=color, outline="white" if selected else self.INK, width=3)
            elif actor.get("display_mode") == "nameplate":
                name = str(actor.get("name") or "Character")
                text_item = canvas.create_text(x, y, text=name, fill=self.INK, font=("Segoe UI", 9, "bold"))
                box = canvas.bbox(text_item) or (x - 25, y - 10, x + 25, y + 10)
                item = canvas.create_rectangle(box[0] - 6, box[1] - 4, box[2] + 6, box[3] + 4, fill="#f8edcf", outline=color, width=3 if selected else 2)
                canvas.tag_raise(text_item)
                self._board_canvas_actors[(map_id, text_item)] = actor_id
            else:
                item = canvas.create_oval(x - 9, y - 9, x + 9, y + 9, fill=color, outline="#fff3cf" if selected else self.INK, width=3 if selected else 2)
            self._board_canvas_actors[(map_id, item)] = actor_id
            name = str(actor.get("name") or "Unknown")
            label = canvas.create_text(x, y + 38 if actor.get("display_mode") == "token" else y + 18, text=name, fill="#fff8e7", font=("Segoe UI", 9, "bold"))
            self._board_canvas_actors[(map_id, label)] = actor_id

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
        state["fit_scale"] = min(
            (max(100, canvas.winfo_width()) - 24) / MAP_CANVAS_WIDTH,
            (max(100, canvas.winfo_height()) - 24) / MAP_CANVAS_HEIGHT,
        )
        self._board_clamp_view(map_id)
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
            "modified": False,
        }
        if redraw:
            self._draw_board_map(map_id)

    def fit_current_board_map(self) -> None:
        if self.selected_board_map_id:
            self._board_fit_map(self.selected_board_map_id)

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
        self._draw_board_map(map_id)
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
        self.board_obscure_button.configure(text="Drawing… click the map")
        self.board_draft_status.configure(
            text="Pen active — click nodes on the map, then click the first node to finish.",
            foreground=self.MUTED,
        )
        window = self.board_map_controls_window
        if window is not None and window.winfo_exists():
            window.attributes("-topmost", True)
            window.deiconify()
            window.lift()
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
        if self.board_obscure_mode:
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
                text="Not sent — these changes are visible only to you.",
                foreground=self.RED,
            )
            self.board_confirm_button.configure(text="Send changes to players", state="normal")

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
            "points": deepcopy(self.board_obscure_draft_points),
            "created_at": now,
            "last_updated": now,
        }
        draft["obscurations"].append(obscuration)
        self.board_obscure_draft_points = []
        self.board_obscure_drawing = False
        self.board_selected_obscuration_id = obscuration["record_id"]
        self.board_selected_obscuration_node = None
        self.board_obscure_button.configure(text="Draw obfuscation  [O]")
        window = self.board_map_controls_window
        if window is not None and window.winfo_exists():
            window.attributes("-topmost", False)
            window.lift()
        self._board_mark_presentation_dirty()
        self._refresh_board_obscuration_list()
        self._draw_board_map(map_id)
        return "break"

    def cancel_board_obscuration(self) -> None:
        self.board_obscure_draft_points = []
        self._board_obscure_drag = None
        if self.board_obscure_drawing:
            self.board_obscure_drawing = False
            self.board_obscure_button.configure(text="Draw obfuscation  [O]")
            window = self.board_map_controls_window
            if window is not None and window.winfo_exists():
                window.attributes("-topmost", False)
                window.lift()
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

    def _actor_at(self, canvas: tk.Canvas, map_id: str, x: float, y: float) -> str:
        for item in reversed(canvas.find_overlapping(x - 8, y - 8, x + 8, y + 8)):
            actor_id = self._board_canvas_actors.get((map_id, item))
            if actor_id:
                return actor_id
        return ""

    def _board_drag_start(self, event: tk.Event, map_id: str) -> None:
        canvas = self.board_canvases[map_id]
        self._drag_start_point = (float(event.x), float(event.y))
        self._drag_actor_id = self._actor_at(canvas, map_id, event.x, event.y)
        if self._drag_actor_id:
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
        start = self._drag_start_point
        self._drag_start_point = None
        if not person_id:
            return
        if start and abs(float(event.x) - start[0]) < 5 and abs(float(event.y) - start[1]) < 5:
            self._open_piece_controls(event.widget, event.x_root, event.y_root)
            return
        if not self.selected_session_id:
            return
        x, y = self._normalized_board_point(map_id, event.x, event.y)
        payload = {"session_id": self.selected_session_id, "person_id": person_id, "map_id": map_id, "x": x, "y": y}
        self._background(
            lambda: self.client.request("POST", "/api/admin/board/move", payload),
            lambda _result: self.refresh(silent=True),
        )

    def _board_piece_menu(self, event: tk.Event, map_id: str) -> str:
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
        canvas = self.board_canvases[map_id]
        actor_id = self._actor_at(canvas, map_id, event.x, event.y)
        if actor_id:
            self.selected_board_actor_id = actor_id
            self._draw_board_map(map_id)
            self._render_board_actor_list()
            self._open_piece_controls(canvas, event.x_root, event.y_root)
        return "break"

    def _open_piece_controls(self, anchor: tk.Widget, root_x: int, root_y: int) -> None:
        actor = self._selected_board_actor()
        if not actor:
            return
        if self._piece_popup is not None and self._piece_popup.winfo_exists():
            self._piece_popup.destroy()
        popup = tk.Toplevel(self)
        self._piece_popup = popup
        popup.overrideredirect(True)
        popup.transient(self)
        popup.configure(background=self.ACCENT)
        popup.bind("<Escape>", lambda _event: popup.destroy())
        body = tk.Frame(
            popup,
            background=self.LIGHT,
            highlightbackground=self.ACCENT,
            highlightthickness=1,
            padx=7,
            pady=7,
        )
        body.pack(fill="both", expand=True)
        tk.Label(
            body,
            text=str(actor.get("name") or "Unknown occupant"),
            background=self.LIGHT,
            foreground=self.INK,
            font=("Segoe UI", 9, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 5))
        tk.Button(
            body,
            text="×",
            width=2,
            relief="flat",
            background=self.LIGHT,
            foreground=self.INK,
            command=popup.destroy,
        ).grid(row=0, column=3, sticky="e")

        def action(label: str, command: Callable[[], None], row: int, column: int) -> None:
            tk.Button(
                body,
                text=label,
                relief="flat",
                background=self.EDGE,
                activebackground=self.PAPER,
                foreground=self.INK,
                font=("Segoe UI", 8, "bold"),
                padx=5,
                pady=4,
                command=lambda: (popup.destroy(), command()),
            ).grid(row=row, column=column, sticky="ew", padx=1, pady=1)

        visible = actor.get("visibility") == "players"
        action("Hide" if visible else "Reveal", lambda: self.update_selected_actor(visibility="headmaster" if visible else "players"), 1, 0)
        action("Dot", lambda: self.update_selected_actor(display_mode="dot"), 1, 1)
        action("Portrait", lambda: self.update_selected_actor(display_mode="token"), 1, 2)
        action("Name", self.toggle_selected_name, 2, 0)
        action("Faction", self.toggle_selected_faction, 2, 1)
        action("More…", self.open_occupants_dialog, 2, 2)
        popup.update_idletasks()
        x = min(root_x + 8, popup.winfo_screenwidth() - popup.winfo_reqwidth() - 8)
        y = min(root_y + 8, popup.winfo_screenheight() - popup.winfo_reqheight() - 8)
        popup.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _render_board_actor_list(self) -> None:
        tree = self.board_actor_tree
        if tree is None or not tree.winfo_exists():
            return
        rows = []
        for actor in self.board_snapshot.get("actors", []):
            if actor.get("map_id") != self.selected_board_map_id:
                continue
            rows.append((str(actor.get("actor_id")), (
                actor.get("name") or "Unknown",
                actor.get("display_mode", "dot").title(),
                "Visible" if actor.get("visibility") == "players" else "Hidden",
            )))
        self._replace_tree(tree, rows)
        if self.selected_board_actor_id and tree.exists(self.selected_board_actor_id):
            tree.selection_set(self.selected_board_actor_id)

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
        self._background(
            lambda: self.client.request("PUT", f"/api/admin/board/people/{self.selected_board_actor_id}", updates),
            lambda _result: self.refresh(silent=True),
        )

    def toggle_selected_name(self) -> None:
        actor = self._selected_board_actor()
        if actor:
            self.update_selected_actor(name_revealed=not bool(actor.get("name_revealed")))

    def toggle_selected_faction(self) -> None:
        actor = self._selected_board_actor()
        if actor:
            self.update_selected_actor(faction_revealed=not bool(actor.get("faction_revealed")))

    def select_actor_faction(self) -> None:
        actor = self._selected_board_actor()
        if not actor:
            messagebox.showinfo("Board", "Select a character first.", parent=self)
            return
        choices = list(actor.get("active_factions", []))
        if not choices:
            messagebox.showinfo("Faction", "This character has no active faction on the current Game World Date.", parent=self)
            return
        chooser = tk.Toplevel(self)
        chooser.title("Displayed faction")
        chooser.transient(self)
        chooser.grab_set()
        ttk.Label(chooser, text="Choose the active faction to display:", padding=12).pack(anchor="w")
        choice_ids = [str(item.get("organization_id")) for item in choices]
        value = tk.StringVar(value=str(actor.get("faction_id") or choice_ids[0]))
        for faction in choices:
            faction_id = str(faction.get("organization_id"))
            ttk.Radiobutton(chooser, text=str(faction.get("name") or faction_id), value=faction_id, variable=value).pack(anchor="w", padx=12, pady=2)
        ttk.Button(chooser, text="Use faction", command=lambda: (self.update_selected_actor(faction_organization_id=value.get()), chooser.destroy())).pack(pady=12)

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
    ) -> None:
        location_id = str(destination.get("location_id"))
        groups = [group for group in self.board_snapshot.get("groups", []) if str(group.get("location_id")) == location_id]
        occupants = [
            item for item in self.board_snapshot.get("actors", [])
            if str(item.get("location_id")) == location_id and item.get("actor_id") != actor.get("actor_id")
        ]
        if not groups and not occupants:
            self._background(lambda: self.client.request("POST", "/api/admin/board/move", move_payload), lambda _result: self.refresh(silent=True))
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
                self.client.request("POST", "/api/admin/board/move", move_payload)
                if selected.startswith("group:"):
                    self.client.request("PUT", f"/api/admin/board/groups/people/{actor['actor_id']}", {"group_id": selected.split(':', 1)[1]})
                elif selected.startswith("create:"):
                    self.client.request("POST", "/api/admin/board/groups", {
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
        if len(actors) < 2:
            messagebox.showinfo("Groups", "At least two people must occupy this map.", parent=self)
            return
        dialog = tk.Toplevel(self)
        dialog.title("Create board group")
        dialog.transient(self)
        dialog.grab_set()
        ttk.Label(dialog, text="Group name", padding=(10, 10, 10, 2)).pack(anchor="w")
        name = ttk.Entry(dialog)
        name.pack(fill="x", padx=10)
        values: dict[str, tk.BooleanVar] = {}
        for actor in actors:
            variable = tk.BooleanVar(value=actor.get("actor_id") == self.selected_board_actor_id)
            values[str(actor["actor_id"])] = variable
            ttk.Checkbutton(dialog, text=str(actor.get("name") or "Unknown"), variable=variable).pack(anchor="w", padx=10, pady=2)
        def save() -> None:
            person_ids = [actor_id for actor_id, variable in values.items() if variable.get()]
            current_map = self._current_board_map()
            if len(person_ids) < 2 or not current_map:
                messagebox.showerror("Groups", "Choose at least two people.", parent=dialog)
                return
            payload = {"name": name.get().strip() or "Group", "location_id": current_map["location_id"], "person_ids": person_ids}
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
        dialog.title("Board group")
        dialog.transient(self)
        dialog.grab_set()
        value = tk.StringVar(value="")
        current = ""
        for group in groups:
            if any(member.get("actor_id") == actor.get("actor_id") for member in group.get("members", [])):
                current = str(group.get("record_id"))
                break
        value.set(current)
        ttk.Label(dialog, text="Choose a group at this location, or remain solo.", padding=10).pack(anchor="w")
        ttk.Radiobutton(dialog, text="Remain solo", variable=value, value="").pack(anchor="w", padx=10, pady=2)
        for group in groups:
            ttk.Radiobutton(dialog, text=str(group.get("name") or "Group"), variable=value, value=str(group.get("record_id"))).pack(anchor="w", padx=10, pady=2)
        def save() -> None:
            self._background(
                lambda: self.client.request("PUT", f"/api/admin/board/groups/people/{actor['actor_id']}", {"group_id": value.get() or None}),
                lambda _result: self.refresh(silent=True),
            )
            dialog.destroy()
        ttk.Button(dialog, text="Apply", command=save).pack(pady=10)

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
            ("select", "↖", "Select"),
            ("map-tools", "▦", "Map Tools"),
            ("occupants", "●", "Occupants"),
            ("reveal", "✦", "Reveal"),
            ("roll", "⚄", "Roll"),
            ("target", "⌖", "Target"),
            ("marker", "◎", "Marker"),
            ("board-settings", "⚙", "Game Board Settings"),
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
        self.select_headmaster_tool("select", "Select")

    def select_headmaster_tool(self, key: str, label: str) -> None:
        """Select a future quick tool without changing the visible app panel."""

        for tool_key, button in self.headmaster_tool_buttons.items():
            active = tool_key == key
            button.configure(
                background=self.EDGE if active else self.ACCENT,
                foreground=self.INK if active else "#fff8e7",
            )
        if key == "occupants":
            self.open_occupants_dialog()
            if hasattr(self, "notice"):
                self.set_notice("Occupant controls opened")
            return
        if key == "map-tools":
            self.open_board_map_controls()
            if hasattr(self, "notice"):
                self.set_notice("Map Tools opened")
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
        elif self.headmaster_tool_rail.winfo_manager():
            self.headmaster_tool_rail.pack_forget()
        self.app_pages[key].tkraise()
        for page_key, button in self.sidebar_buttons.items():
            active = page_key == key
            button.configure(
                background=self.ACCENT if active else self.LIGHT,
                foreground="#fff8e7" if active else self.INK,
                activebackground=self.ACCENT if active else self.PAPER,
                activeforeground="#fff8e7" if active else self.INK,
            )

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
            width=330,
            background=self.LIGHT,
            highlightbackground=self.ACCENT,
            highlightthickness=1,
        )
        self.chat_shell.pack(side="right", fill="y", padx=(8, 0))
        self.chat_shell.pack_propagate(False)
        self.chat_expanded = tk.Frame(self.chat_shell, background=self.LIGHT)
        chat_header = tk.Frame(self.chat_expanded, background=self.EDGE)
        chat_header.pack(fill="x")
        tk.Label(
            chat_header,
            text="SESSION CHAT",
            anchor="w",
            background=self.EDGE,
            foreground=self.INK,
            font=("Segoe UI", 9, "bold"),
            padx=12,
            pady=11,
        ).pack(side="left", fill="x", expand=True)
        tk.Button(
            chat_header,
            text="›",
            width=3,
            background=self.EDGE,
            activebackground=self.PAPER,
            foreground=self.INK,
            relief="flat",
            font=("Segoe UI", 15, "bold"),
            command=self.toggle_chat,
        ).pack(side="right", fill="y")
        self._build_chat(self.chat_expanded)
        self.chat_rail = tk.Button(
            self.chat_shell,
            text="‹\n\nC\nH\nA\nT",
            background=self.EDGE,
            activebackground=self.PAPER,
            foreground=self.INK,
            relief="flat",
            borderwidth=0,
            font=("Segoe UI", 10, "bold"),
            command=self.toggle_chat,
        )
        self.chat_expanded.pack(fill="both", expand=True)

    def toggle_chat(self) -> None:
        self.chat_collapsed = not self.chat_collapsed
        if self.chat_collapsed:
            self.chat_expanded.pack_forget()
            self.chat_shell.configure(width=52)
            self.chat_rail.pack(fill="both", expand=True)
        else:
            self.chat_rail.pack_forget()
            self.chat_shell.configure(width=330)
            self.chat_expanded.pack(fill="both", expand=True)

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
        horizontal = ttk.Scrollbar(container, orient="horizontal", command=canvas.xview)
        canvas.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        content = ttk.Frame(canvas)
        window = canvas.create_window((0, 0), window=content, anchor="nw")

        def update_region(_event: tk.Event | None = None) -> None:
            canvas.update_idletasks()
            requested = max(content.winfo_reqwidth(), canvas.winfo_width())
            canvas.itemconfigure(window, width=requested)
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
        card.pack(fill="both", expand=True)
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
        )
        chat_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.chat_log.yview)
        self.chat_log.configure(yscrollcommand=chat_scroll.set)
        self.chat_log.pack(side="left", fill="both", expand=True)
        chat_scroll.pack(side="right", fill="y")
        self.chat_log.tag_configure("headmaster", foreground=self.ACCENT, font=("Segoe UI", 10, "bold"))
        self.chat_log.tag_configure("system", foreground=self.GREEN, font=("Segoe UI", 10, "bold"))
        self.chat_log.tag_configure("player", foreground=self.INK, font=("Segoe UI", 10, "bold"))
        composer = ttk.Frame(card, style="Card.TFrame")
        composer.pack(fill="x", pady=(10, 0))
        self.chat_entry = ttk.Entry(composer)
        self.chat_entry.pack(side="left", fill="x", expand=True)
        self.chat_entry.bind("<Return>", lambda _event: self.send_chat())
        ttk.Button(composer, text="Send", command=self.send_chat).pack(side="right", padx=(10, 0))
        self._rendered_chat_ids: tuple[str, ...] = ()

    def _build_session(self) -> None:
        self.session_tab.columnconfigure(0, weight=1)
        self.session_tab.columnconfigure(1, weight=2)
        self.session_tab.rowconfigure(0, weight=1)
        self.selected_session_id: str | None = None
        self.selected_invite_ids: set[str] = set()
        self._invite_selection_session_id: str | None = None
        self._invite_roster_ids_by_session: dict[str, set[str]] = {}
        self.sending_invitations = False

        sessions_card = self._card(self.session_tab, "Sessions")
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
            ("checked", "✓", 38, "center"),
            ("name", "Player", 140, "w"),
            ("email", "Email", 190, "w"),
            ("sent", "Last Invitation", 145, "w"),
            ("logged_in", "Logged In", 85, "center"),
        ):
            self.invites_tree.heading(column, text=heading)
            self.invites_tree.column(column, width=width, minwidth=35, anchor=anchor)
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
        invite_controls.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(0, 8))
        self.invite_selection_label = ttk.Label(
            invite_controls, text="0 players checked", style="Card.TLabel"
        )
        self.invite_selection_label.pack(side="left")
        ttk.Button(
            invite_controls, text="Check All", style="Quiet.TButton",
            command=self.select_all_invites,
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            invite_controls, text="Clear", style="Quiet.TButton",
            command=self.clear_invite_selection,
        ).pack(side="left", padx=(6, 0))
        self.send_selected_button = ttk.Button(
            invite_controls, text="Send to Selected",
            command=lambda: self.send_invites(False),
        )
        self.send_selected_button.pack(side="right")
        self.send_all_button = ttk.Button(
            invite_controls, text="Send to All", style="Quiet.TButton",
            command=lambda: self.send_invites(True),
        )
        self.send_all_button.pack(side="right", padx=8)
        ttk.Button(
            invite_controls, text="Remove from Session", style="Danger.TButton",
            command=self.remove_from_session,
        ).pack(side="right")

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

        sessions = list(state.get("sessions") or ([state["session"]] if state.get("session") else []))
        session_rows = [
            (
                session["id"],
                (
                    session["title"],
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
        if self.selected_session_id and self.sessions_tree.exists(self.selected_session_id):
            self.sessions_tree.selection_set(self.selected_session_id)
        session = next(
            (item for item in sessions if item["id"] == self.selected_session_id), None
        )
        self._render_game_clock(session)
        board = deepcopy(
            (state.get("boards") or {}).get(self.selected_session_id or "", {})
        )
        location_maps = list(state.get("location_maps") or [])
        if not location_maps:
            try:
                location_maps = self.world_board.location_maps()
            except (KeyError, OSError, RuntimeError, ValueError):
                location_maps = []
        board["maps"] = location_maps
        self._render_board(board)

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
            self.session_summary.configure(
                text=(
                    f"{session['title']}  •  Campaign: {session.get('campaign_name') or 'Legacy session'}"
                    f"  •  Event date: {format_stored_date(session.get('event_date'))}"
                    f"  •  Game World Date: {format_stored_game_datetime(session.get('game_datetime'))}"
                    f"  •  Expires: {format_stored_date(session.get('expires_at'))}"
                )
            )
            roster_ids = {player["contact_id"] for player in session.get("roster", [])}
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
            if not self.admission_alert.winfo_manager():
                self.admission_alert.pack(
                    fill="x", padx=12, pady=(0, 6), before=self.workspace
                )
            self.control_panel_button.configure(text=f"Control Panel  •  {count} waiting")
        else:
            if self.admission_alert.winfo_manager():
                self.admission_alert.pack_forget()
            self.control_panel_button.configure(text="Control Panel")
        if new_ids:
            self._notify_join_request()

    def _notify_join_request(self) -> None:
        self.bell()
        self.set_notice("A player is waiting for admission approval")
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.user32.FlashWindow(self.winfo_id(), True)
            except Exception:
                pass

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
                session for session in self.state_data.get("sessions", [])
                if session.get("id") == self.selected_session_id
            ),
            None,
        )

    def _session_selected(self, _event: tk.Event | None = None) -> None:
        selection = self.sessions_tree.selection()
        if not selection or selection[0] == self.selected_session_id:
            return
        self.selected_session_id = selection[0]
        self._invite_selection_session_id = None
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
                text=f"{count} player{'s' if count != 1 else ''} checked"
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
        self._rendered_chat_ids = message_ids
        self.chat_log.configure(state="normal")
        self.chat_log.delete("1.0", "end")
        for message in messages:
            stamp = str(message.get("sent_at", ""))[11:16] or "--:--"
            role = message.get("sender_role") if message.get("sender_role") in {"headmaster", "system"} else "player"
            self.chat_log.insert("end", f"{stamp}  {message.get('sender_name', 'Player')}: ", role)
            self.chat_log.insert("end", f"{message.get('text', '')}\n")
        self.chat_log.configure(state="disabled")
        self.chat_log.see("end")

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
        self.server.stop()
        self.destroy()


def main() -> None:
    configure_windows_app_id("GameBoard")
    GameBoardWindow().mainloop()


if __name__ == "__main__":
    main()
