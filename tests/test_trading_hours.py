import datetime as dt
from zoneinfo import ZoneInfo

import numpy as np
import pytest

from jesse import utils
from jesse.services import trading_hours as th

ET = ZoneInfo('America/New_York')
UTC = ZoneInfo('UTC')

US_HOURS = {'timezone': 'America/New_York', 'hours': {'Mon-Fri': '09:30-16:00'}}


def ms(year, month, day, hour=0, minute=0, tz=ET) -> int:
    return int(dt.datetime(year, month, day, hour, minute, tzinfo=tz).timestamp() * 1000)


def local(timestamp: int, tz=ET) -> dt.datetime:
    return dt.datetime.fromtimestamp(timestamp / 1000, tz)


def timestamps(start: int, count: int, step_ms: int) -> np.ndarray:
    return start + np.arange(count, dtype=np.int64) * step_ms


def candles_at(ts: np.ndarray) -> np.ndarray:
    candles = np.zeros((len(ts), 6))
    candles[:, 0] = ts
    return candles


# ---- contains() -----------------------------------------------------------------

def test_boundary_ticks_are_half_open():
    schedule = th.get_schedule(US_HOURS)
    # Monday 2026-09-14
    assert schedule.contains(ms(2026, 9, 14, 9, 15)) is False
    assert schedule.contains(ms(2026, 9, 14, 9, 30)) is True
    assert schedule.contains(ms(2026, 9, 14, 15, 45)) is True
    assert schedule.contains(ms(2026, 9, 14, 16, 0)) is False
    # Saturday
    assert schedule.contains(ms(2026, 9, 12, 11, 0)) is False


def test_dst_transition_is_handled_per_day():
    schedule = th.get_schedule(US_HOURS)
    # 2026-03-08 is the spring-forward date: 09:30 ET is 14:30 UTC before and 13:30 UTC after
    assert schedule.contains(ms(2026, 3, 6, 14, 29, UTC)) is False
    assert schedule.contains(ms(2026, 3, 6, 14, 30, UTC)) is True
    assert schedule.contains(ms(2026, 3, 9, 13, 29, UTC)) is False
    assert schedule.contains(ms(2026, 3, 9, 13, 30, UTC)) is True


def test_multiple_windows_per_day():
    tokyo = ZoneInfo('Asia/Tokyo')
    schedule = th.get_schedule({'timezone': 'Asia/Tokyo', 'hours': {'Mon-Fri': ['09:00-11:30', '12:30-15:30']}})
    assert schedule.contains(ms(2026, 9, 14, 11, 29, tokyo)) is True
    assert schedule.contains(ms(2026, 9, 14, 12, 0, tokyo)) is False
    assert schedule.contains(ms(2026, 9, 14, 12, 30, tokyo)) is True
    assert schedule.contains(ms(2026, 9, 14, 15, 30, tokyo)) is False


def test_day_groups_with_different_hours_and_unlisted_days_closed():
    karachi = ZoneInfo('Asia/Karachi')
    schedule = th.get_schedule({
        'timezone': 'Asia/Karachi',
        'hours': {'Mon-Thu': '09:30-15:30', 'Fri': ['09:30-12:00', '14:30-16:30']},
    })
    assert schedule.contains(ms(2026, 9, 14, 15, 0, karachi)) is True   # Monday inside the regular day
    assert schedule.contains(ms(2026, 9, 14, 16, 0, karachi)) is False  # Monday after the 15:30 close
    assert schedule.contains(ms(2026, 9, 18, 13, 0, karachi)) is False  # Friday prayer break
    assert schedule.contains(ms(2026, 9, 18, 16, 0, karachi)) is True   # Friday afternoon session
    assert schedule.contains(ms(2026, 9, 19, 11, 0, karachi)) is False  # Saturday is not listed


def test_window_wrapping_past_midnight_belongs_to_its_start_day():
    schedule = th.get_schedule({'timezone': 'UTC', 'hours': {'Mon-Fri': '22:00-05:00'}})
    assert schedule.contains(ms(2026, 9, 14, 23, 0, UTC)) is True
    assert schedule.contains(ms(2026, 9, 15, 4, 59, UTC)) is True
    assert schedule.contains(ms(2026, 9, 15, 5, 0, UTC)) is False
    # Friday's window spills into Saturday morning, but nothing starts on Saturday
    assert schedule.contains(ms(2026, 9, 19, 3, 0, UTC)) is True
    assert schedule.contains(ms(2026, 9, 20, 3, 0, UTC)) is False


def test_fx_week_and_full_day_windows():
    schedule = th.get_schedule({
        'timezone': 'America/New_York',
        'hours': {'Sun': '17:00-24:00', 'Mon-Thu': '00:00-24:00', 'Fri': '00:00-17:00'},
    })
    assert schedule.contains(ms(2026, 9, 13, 16, 59)) is False
    assert schedule.contains(ms(2026, 9, 13, 17, 0)) is True
    assert schedule.contains(ms(2026, 9, 15, 3, 0)) is True
    assert schedule.contains(ms(2026, 9, 18, 16, 59)) is True
    assert schedule.contains(ms(2026, 9, 18, 17, 0)) is False
    assert schedule.contains(ms(2026, 9, 19, 12, 0)) is False


def test_closed_dates_and_per_date_overrides():
    riyadh = ZoneInfo('Asia/Riyadh')
    schedule = th.get_schedule({
        'timezone': 'Asia/Riyadh',
        'hours': {'Sun-Thu': '10:00-15:00'},
        'closed': ['2026-09-14'],
        'overrides': {'2026-09-15': '10:00-12:00'},
    })
    assert schedule.contains(ms(2026, 9, 14, 11, 0, riyadh)) is False  # closed date
    assert schedule.contains(ms(2026, 9, 15, 11, 0, riyadh)) is True   # inside the override
    assert schedule.contains(ms(2026, 9, 15, 13, 0, riyadh)) is False  # after the early close
    assert schedule.contains(ms(2026, 9, 16, 13, 0, riyadh)) is True   # regular day


# ---- mask() / filter_candles() ------------------------------------------------------

def test_filter_keeps_26_fifteen_minute_rows_per_weekday_and_none_on_weekends():
    schedule = th.get_schedule(US_HOURS)
    ts = timestamps(ms(2026, 9, 13, 0, 0), 7 * 96, 15 * 60_000)  # Sunday 00:00 ET, one week
    kept = schedule.filter_candles(candles_at(ts))
    assert len(kept) == 5 * 26
    for row in kept:
        moment = local(int(row[0]))
        assert moment.weekday() < 5
        assert dt.time(9, 30) <= moment.time() < dt.time(16, 0)


def test_mask_agrees_with_contains_on_every_row():
    for spec in (
        US_HOURS,
        {'timezone': 'UTC', 'hours': {'Mon-Fri': '22:00-05:00'}},
        {'timezone': 'Asia/Tokyo', 'hours': {'Mon-Fri': ['09:00-11:30', '12:30-15:30']}},
    ):
        schedule = th.get_schedule(spec)
        ts = timestamps(ms(2026, 9, 12, 0, 0, UTC), 9 * 24 * 4, 15 * 60_000)
        mask = schedule.mask(ts)
        assert [bool(flag) for flag in mask] == [schedule.contains(int(t)) for t in ts]


def test_partial_hourly_candle_at_the_open_is_excluded():
    schedule = th.get_schedule(US_HOURS)
    ts = timestamps(ms(2026, 9, 14, 0, 0), 24, 3_600_000)
    kept_hours = [local(int(t)).hour for t in ts[schedule.mask(ts)]]
    assert kept_hours == [10, 11, 12, 13, 14, 15]


def test_filter_preserves_order_and_columns():
    schedule = th.get_schedule(US_HOURS)
    ts = timestamps(ms(2026, 9, 14, 9, 0), 8, 15 * 60_000)
    candles = candles_at(ts)
    candles[:, 2] = np.arange(8)  # close column carries the original index
    kept = schedule.filter_candles(candles)
    assert kept.shape[1] == 6
    assert list(kept[:, 2]) == [2, 3, 4, 5, 6, 7]  # 09:00 and 09:15 dropped, rest in order


def test_empty_input_and_no_schedule_pass_through():
    empty = np.zeros((0, 6))
    assert len(th.filter_candles(empty, US_HOURS)) == 0
    candles = candles_at(timestamps(ms(2026, 9, 14, 3, 0), 4, 60_000))
    assert th.filter_candles(candles, None) is candles
    assert th.is_in_trading_hours(ms(2026, 9, 14, 3, 0), None) is True


# ---- caching and utils wrappers -----------------------------------------------------

def test_equal_dicts_share_one_cached_schedule():
    assert th.get_schedule(dict(US_HOURS)) is th.get_schedule({'hours': {'Mon-Fri': '09:30-16:00'}, 'timezone': 'America/New_York'})


def test_utils_wrappers_match_service():
    ts = timestamps(ms(2026, 9, 14, 9, 0), 8, 15 * 60_000)
    candles = candles_at(ts)
    np.testing.assert_array_equal(utils.filter_candles_by_hours(candles, US_HOURS), th.filter_candles(candles, US_HOURS))
    assert utils.is_in_trading_hours(ms(2026, 9, 14, 9, 30), US_HOURS) is True
    assert utils.is_in_trading_hours(ms(2026, 9, 14, 9, 29), US_HOURS) is False


# ---- validation -----------------------------------------------------------------------

@pytest.mark.parametrize('spec, message', [
    ({'hours': {'Mon-Fri': '09:30-16:00'}}, "'timezone' is required"),
    ({'timezone': 'Mars/Olympus', 'hours': {'Mon': '09:00-10:00'}}, 'unknown timezone'),
    ({'timezone': 'UTC', 'hours': {'Monday': '09:00-10:00'}}, "unknown day 'Monday'"),
    ({'timezone': 'UTC', 'hours': {'Mon': '10:00-10:00'}}, 'same open and close time'),
    ({'timezone': 'UTC', 'hours': {'Mon-Fri': '09:00-17:00', 'Fri': '09:00-12:00'}}, 'Fri is listed more than once'),
    ({'timezone': 'UTC', 'hours': {'Mon': '09:00-17:00'}, 'extra': 1}, "unknown key(s) ['extra']"),
    ({'timezone': 'UTC', 'hours': {'Mon': '24:00-03:00'}}, 'cannot open at 24:00'),
    ({'timezone': 'UTC', 'hours': {'Mon': '09:60-10:00'}}, 'out of range'),
    ({'timezone': 'UTC', 'hours': {}}, "'hours' must be a non-empty dict"),
    ({'timezone': 'UTC', 'hours': {'Mon': '09:00-10:00'}, 'closed': ['yesterday']}, 'not an ISO date'),
    ('NYSE', 'must be a dict or None'),
    (42, 'must be a dict or None'),
])
def test_invalid_specs_raise_with_a_pointed_message(spec, message):
    with pytest.raises(ValueError, match=__import__('re').escape(message)):
        th.get_schedule(spec)


# ---- independent cross-checks -------------------------------------------------------

def test_southern_hemisphere_dst_is_reversed_correctly():
    # Sydney leaves DST on 2026-04-05: 10:00 local is 23:00 UTC the day before while on AEDT,
    # and 00:00 UTC the same day once on AEST.
    schedule = th.get_schedule({'timezone': 'Australia/Sydney', 'hours': {'Mon-Fri': '10:00-16:00'}})
    assert schedule.contains(ms(2026, 4, 2, 22, 59, UTC)) is False
    assert schedule.contains(ms(2026, 4, 2, 23, 0, UTC)) is True   # Friday 2026-04-03 10:00 AEDT
    assert schedule.contains(ms(2026, 4, 5, 23, 59, UTC)) is False
    assert schedule.contains(ms(2026, 4, 6, 0, 0, UTC)) is True    # Monday 2026-04-06 10:00 AEST


def _reference_contains(spec: dict, timestamp: int) -> bool:
    """Brute-force re-implementation using only datetime arithmetic, for fuzzing the service."""
    tz = ZoneInfo(spec['timezone'])
    by_weekday = {}
    for day_text, windows in spec['hours'].items():
        for weekday in th._parse_days(day_text):
            by_weekday[weekday] = windows if isinstance(windows, list) else [windows]
    moment = local(timestamp, tz)

    def windows_for(day):
        if day.isoformat() in spec.get('closed', []):
            return []
        override = spec.get('overrides', {}).get(day.isoformat())
        if override is not None:
            return override if isinstance(override, list) else [override]
        return by_weekday.get(day.weekday(), [])

    for day in (moment.date() - dt.timedelta(days=1), moment.date()):
        for window in windows_for(day):
            open_text, close_text = window.split('-')
            oh, om = map(int, open_text.split(':'))
            ch, cm = map(int, close_text.split(':'))
            start = dt.datetime(day.year, day.month, day.day, oh, om, tzinfo=tz)
            close_day = day if ch * 60 + cm > oh * 60 + om else day + dt.timedelta(days=1)
            if ch == 24:
                end = dt.datetime.combine(close_day + dt.timedelta(days=1), dt.time(0), tzinfo=tz)
            else:
                end = dt.datetime(close_day.year, close_day.month, close_day.day, ch, cm, tzinfo=tz)
            if start.timestamp() * 1000 <= timestamp < end.timestamp() * 1000:
                return True
    return False


def test_mask_and_contains_match_a_brute_force_reference_across_zones_and_dst():
    import random

    rng = random.Random(7)
    day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    zones = ['America/New_York', 'Europe/London', 'Australia/Sydney', 'Asia/Tokyo', 'Asia/Kolkata',
             'America/Santiago', 'Asia/Tehran', 'UTC']
    # two days either side of DST changes in those zones, plus ordinary weeks
    anchors = [dt.datetime(2026, m, d, tzinfo=UTC) for m, d in
               [(3, 8), (3, 29), (4, 5), (10, 4), (10, 25), (11, 1), (1, 12), (6, 15), (9, 7), (12, 28)]]

    def random_spec() -> dict:
        hours, used = {}, set()
        for _ in range(rng.randint(1, 3)):
            a, b = rng.sample(range(7), 2)
            lo, hi = sorted((a, b))
            days = list(range(lo, hi + 1)) if rng.random() < 0.7 else [a]
            if any(d in used for d in days):
                continue
            used.update(days)
            windows = []
            for _ in range(rng.randint(1, 2)):
                open_minutes = rng.randint(0, 1439)
                close_minutes = min(rng.choice([rng.randint(0, 1440), open_minutes + rng.randint(1, 600)]), 1440)
                if close_minutes == open_minutes:
                    close_minutes = (open_minutes + 30) % 1441 or 1
                windows.append(f'{open_minutes // 60:02d}:{open_minutes % 60:02d}-{close_minutes // 60:02d}:{close_minutes % 60:02d}')
            key = f'{day_names[days[0]]}-{day_names[days[-1]]}' if len(days) > 1 else day_names[days[0]]
            hours[key] = windows if len(windows) > 1 else windows[0]
        spec = {'timezone': rng.choice(zones), 'hours': hours or {'Mon-Fri': '09:30-16:00'}}
        if rng.random() < 0.5:
            spec['closed'] = ['2026-03-09', '2026-10-05']
        if rng.random() < 0.5:
            spec['overrides'] = {'2026-04-06': '10:00-12:00', '2026-11-02': ['01:00-02:30', '22:00-03:00']}
        return spec

    checks = 0
    for _ in range(60):
        spec = random_spec()
        schedule = th.get_schedule(spec)
        base = int(rng.choice(anchors).timestamp() * 1000) - 2 * 86_400_000
        ts = base + np.arange(4 * 24 * 6, dtype=np.int64) * 10 * 60_000 + rng.randint(0, 59) * 1000
        mask = schedule.mask(ts)
        for flag, t in zip(mask, ts):
            expected = _reference_contains(spec, int(t))
            assert bool(flag) is expected, (spec, local(int(t), ZoneInfo(spec['timezone'])))
            assert schedule.contains(int(t)) is expected
            checks += 1
    assert checks == 60 * 4 * 24 * 6
