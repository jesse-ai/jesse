"""
Trading-hours schedules for instruments that follow a market calendar.

A schedule is a plain, JSON-compatible dict:

    {
        'timezone': 'America/New_York',                 # IANA name, required
        'hours': {'Mon-Fri': '09:30-16:00'},            # day spec -> window or list of windows
        'closed': ['2026-11-26'],                       # optional: ISO dates treated as closed
        'overrides': {'2026-11-27': '09:30-13:00'},     # optional: ISO date -> window(s) for that day
    }

Jesse timestamps are UTC milliseconds everywhere, so the local windows are converted to UTC
intervals per calendar day (DST is therefore handled by ``zoneinfo``) and the module answers two
questions: is a moment inside the schedule, and which candles fall inside it. Nothing here
touches the candle store; callers filter their own arrays.

Windows are half-open (``open <= t < close``). A window whose close is not later than its open
wraps past midnight and belongs to the day it starts on. A day that is not listed under
``hours`` is closed; nothing is implied.
"""
from __future__ import annotations

import datetime as dt
import json
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import numpy as np
from jesse_rust import filter_candles_by_intervals, trading_hours_mask

TradingHoursSpec = Optional[dict]

_DAY_NAMES = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')
_DAY_INDEX = {name: index for index, name in enumerate(_DAY_NAMES)}
_MINUTES_PER_DAY = 24 * 60
_ONE_DAY = dt.timedelta(days=1)
_ALLOWED_KEYS = {'timezone', 'hours', 'closed', 'overrides'}


Window = Tuple[int, int]  # minutes since local midnight: (open, close); close may be 1440 for 24:00
Interval = Tuple[int, int]  # UTC milliseconds: [start, end)


def _parse_time(text: str, context: str) -> int:
    """'HH:MM' -> minutes since midnight. '24:00' is allowed so a window can end at midnight."""
    parts = text.strip().split(':')
    if len(parts) != 2 or not (parts[0].isdigit() and parts[1].isdigit()):
        raise ValueError(f"{context}: time '{text}' must look like 'HH:MM'")
    hours, minutes = int(parts[0]), int(parts[1])
    if minutes > 59 or hours > 24 or (hours == 24 and minutes != 0):
        raise ValueError(f"{context}: time '{text}' is out of range (00:00 to 24:00)")
    return hours * 60 + minutes


def _parse_window(text: str, context: str) -> Window:
    """'HH:MM-HH:MM' -> (open, close) in minutes. Equal times are rejected as ambiguous."""
    if not isinstance(text, str) or text.count('-') != 1:
        raise ValueError(f"{context}: window '{text}' must look like 'HH:MM-HH:MM'")
    open_text, close_text = text.split('-')
    open_minutes = _parse_time(open_text, context)
    close_minutes = _parse_time(close_text, context)
    if open_minutes == _MINUTES_PER_DAY:
        raise ValueError(f"{context}: a window cannot open at 24:00")
    if open_minutes == close_minutes:
        raise ValueError(f"{context}: window '{text}' has the same open and close time")
    return open_minutes, close_minutes


def _parse_windows(value, context: str) -> List[Window]:
    """A single 'HH:MM-HH:MM' string or a list of them."""
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)) or len(value) == 0:
        raise ValueError(f"{context}: expected a window string or a non-empty list of windows")
    return [_parse_window(item, context) for item in value]


def _parse_days(text: str) -> List[int]:
    """'Mon-Fri', 'Mon,Wed,Fri' or 'Sun' -> weekday indexes (Mon=0). Ranges may wrap ('Fri-Mon')."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"'hours' key '{text}' must name days like 'Mon-Fri', 'Mon,Wed,Fri' or 'Sun'")
    days: List[int] = []
    for part in text.split(','):
        part = part.strip()
        if '-' in part:
            first_text, last_text = (p.strip() for p in part.split('-', 1))
            if first_text not in _DAY_INDEX or last_text not in _DAY_INDEX:
                raise ValueError(f"'hours' key '{text}': unknown day in range '{part}' (use Mon..Sun)")
            first, last = _DAY_INDEX[first_text], _DAY_INDEX[last_text]
            span = (last - first) % 7
            days.extend((first + offset) % 7 for offset in range(span + 1))
        else:
            if part not in _DAY_INDEX:
                raise ValueError(f"'hours' key '{text}': unknown day '{part}' (use Mon..Sun)")
            days.append(_DAY_INDEX[part])
    return days


def _parse_date(text, context: str) -> dt.date:
    if isinstance(text, dt.date):
        return text
    try:
        return dt.date.fromisoformat(str(text))
    except ValueError as e:
        raise ValueError(f"{context}: '{text}' is not an ISO date (YYYY-MM-DD)") from e


class TradingHours:
    """A validated schedule with a per-day cache of UTC intervals."""

    def __init__(self, spec: dict) -> None:
        if not isinstance(spec, dict):
            raise ValueError('trading hours must be a dict or None')
        unknown = set(spec) - _ALLOWED_KEYS
        if unknown:
            raise ValueError(
                f"trading hours: unknown key(s) {sorted(unknown)}; allowed keys are {sorted(_ALLOWED_KEYS)}"
            )
        timezone = spec.get('timezone')
        if not isinstance(timezone, str) or not timezone:
            raise ValueError("trading hours: 'timezone' is required and must be an IANA name such as 'America/New_York'")
        try:
            self.timezone = ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError) as e:
            raise ValueError(f"trading hours: unknown timezone '{timezone}'") from e

        hours = spec.get('hours')
        if not isinstance(hours, dict) or len(hours) == 0:
            raise ValueError("trading hours: 'hours' must be a non-empty dict of day spec -> window(s)")
        self.weekday_windows: Dict[int, List[Window]] = {}
        for day_text, windows_value in hours.items():
            windows = _parse_windows(windows_value, f"'hours' entry '{day_text}'")
            for weekday in _parse_days(day_text):
                if weekday in self.weekday_windows:
                    raise ValueError(
                        f"trading hours: {_DAY_NAMES[weekday]} is listed more than once in 'hours'"
                    )
                self.weekday_windows[weekday] = windows

        closed_value = spec.get('closed') or []
        if not isinstance(closed_value, (list, tuple)):
            raise ValueError("trading hours: 'closed' must be a list of ISO dates")
        self.closed = frozenset(_parse_date(item, "'closed'") for item in closed_value)

        overrides_value = spec.get('overrides') or {}
        if not isinstance(overrides_value, dict):
            raise ValueError("trading hours: 'overrides' must be a dict of ISO date -> window(s)")
        self.overrides: Dict[dt.date, List[Window]] = {
            _parse_date(date_text, "'overrides'"): _parse_windows(windows_value, f"'overrides' entry '{date_text}'")
            for date_text, windows_value in overrides_value.items()
        }

        # UTC intervals that *start* on a given local date; wrapped windows end on the next date.
        self._intervals_by_day: Dict[dt.date, List[Interval]] = {}
        # The most recent merged interval arrays, reused while the queried date range is unchanged.
        self._range_cache: Optional[Tuple[dt.date, dt.date, np.ndarray, np.ndarray]] = None

    # ---- local <-> UTC ------------------------------------------------------

    def _windows_for(self, day: dt.date) -> List[Window]:
        # Precedence: an explicit closure wins, then a per-date override, then the weekday rule.
        if day in self.closed:
            return []
        override = self.overrides.get(day)
        if override is not None:
            return override
        return self.weekday_windows.get(day.weekday(), [])

    def _local_to_ms(self, day: dt.date, minutes: int) -> int:
        # ``minutes`` may reach 1440 (24:00), which is midnight of the following day.
        extra_days, minutes = divmod(minutes, _MINUTES_PER_DAY)
        day = day + dt.timedelta(days=extra_days)
        hours, minutes = divmod(minutes, 60)
        local = dt.datetime(day.year, day.month, day.day, hours, minutes, tzinfo=self.timezone)
        return int(local.timestamp() * 1000)

    def _local_date(self, timestamp: int) -> dt.date:
        return dt.datetime.fromtimestamp(timestamp / 1000, self.timezone).date()

    def _intervals_starting_on(self, day: dt.date) -> List[Interval]:
        intervals = self._intervals_by_day.get(day)
        if intervals is None:
            intervals = []
            for open_minutes, close_minutes in self._windows_for(day):
                # A close at or before the open wraps into the next local day.
                close_day = day if close_minutes > open_minutes else day + _ONE_DAY
                intervals.append((self._local_to_ms(day, open_minutes), self._local_to_ms(close_day, close_minutes)))
            self._intervals_by_day[day] = intervals
        return intervals

    def _merged_intervals(self, first_day: dt.date, last_day: dt.date) -> Tuple[np.ndarray, np.ndarray]:
        """Sorted, non-overlapping UTC intervals for windows starting between the two local dates."""
        cache = self._range_cache
        if cache is not None and cache[0] == first_day and cache[1] == last_day:
            return cache[2], cache[3]

        intervals: List[Interval] = []
        day = first_day
        while day <= last_day:
            intervals.extend(self._intervals_starting_on(day))
            day += _ONE_DAY
        intervals.sort()

        # Wrapped windows can run into the next day's window; merge so searchsorted stays valid.
        merged: List[List[int]] = []
        for start, end in intervals:
            if merged and start <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])

        starts = np.array([item[0] for item in merged], dtype=np.int64)
        ends = np.array([item[1] for item in merged], dtype=np.int64)
        self._range_cache = (first_day, last_day, starts, ends)
        return starts, ends

    # ---- public ---------------------------------------------------------------

    def contains(self, timestamp: int) -> bool:
        """Whether a UTC-millisecond moment is inside the schedule."""
        timestamp = int(timestamp)
        day = self._local_date(timestamp)
        # Yesterday's windows may wrap past midnight into today.
        for candidate in (day - _ONE_DAY, day):
            for start, end in self._intervals_starting_on(candidate):
                if start <= timestamp < end:
                    return True
        return False

    def _intervals_for_timestamps(self, timestamps: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Compile the enclosing local dates, including yesterday's overnight windows."""
        first_day = self._local_date(int(timestamps.min())) - _ONE_DAY
        last_day = self._local_date(int(timestamps.max()))
        return self._merged_intervals(first_day, last_day)

    def mask(self, timestamps: np.ndarray) -> np.ndarray:
        """Boolean mask marking which UTC-millisecond timestamps are inside the schedule."""
        timestamps = np.asarray(timestamps, dtype=np.int64)
        if len(timestamps) == 0:
            return np.zeros(0, dtype=bool)
        starts, ends = self._intervals_for_timestamps(timestamps)
        return trading_hours_mask(timestamps, starts, ends)

    def filter_candles(self, candles: np.ndarray) -> np.ndarray:
        """Rows whose open timestamp (column 0) is inside the schedule, in original order."""
        if len(candles) == 0:
            return candles
        timestamps = np.asarray(candles[:, 0], dtype=np.int64)
        starts, ends = self._intervals_for_timestamps(timestamps)
        if candles.dtype == np.float64:
            return filter_candles_by_intervals(candles, timestamps, starts, ends)
        # Research arrays may have another dtype; retain it instead of coercing OHLCV.
        return candles[trading_hours_mask(timestamps, starts, ends)]


# ---- lookup -------------------------------------------------------------------

_schedules: Dict[str, TradingHours] = {}


def get_schedule(spec: TradingHoursSpec) -> Optional[TradingHours]:
    """Resolve a spec (dict or None) to a cached, validated schedule.

    Specs are cached by value, so a strategy that rebuilds the same dict on every candle pays
    the validation cost once.
    """
    if spec is None:
        return None
    if not isinstance(spec, dict):
        raise ValueError('trading hours must be a dict or None')
    key = json.dumps(spec, sort_keys=True, default=str)
    schedule = _schedules.get(key)
    if schedule is None:
        schedule = TradingHours(spec)
        _schedules[key] = schedule
    return schedule


def is_in_trading_hours(timestamp: int, spec: TradingHoursSpec) -> bool:
    """Whether a UTC-millisecond moment is inside the schedule; always True without a schedule."""
    schedule = get_schedule(spec)
    return True if schedule is None else schedule.contains(timestamp)


def filter_candles(candles: np.ndarray, spec: TradingHoursSpec) -> np.ndarray:
    """Candles whose open time is inside the schedule; the input itself without a schedule."""
    schedule = get_schedule(spec)
    return candles if schedule is None else schedule.filter_candles(candles)
