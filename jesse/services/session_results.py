"""
Bounded, read-only views of stored session results for MCP assistants.

One entry point, `get_results(session_type, session_id, section, offset, limit)`, covers
backtests, optimizations, Monte Carlo runs, rule significance tests, and live/paper
sessions. The "summary" section is compact and is what assistants should read first; the
other sections return one page of real stored rows (trades, equity points, optimization
trials, Monte Carlo scenarios, orders, log lines, ...).

Every page is bounded twice: by `limit` items and by MAX_PAGE_BYTES of JSON, so a result
always fits an assistant's context window. `next_offset` continues where a page stopped.
Nothing here computes new statistics: values are the ones Jesse stored, with NaN and
infinite floats returned as null exactly like the dashboard API.

`export_session()` returns the complete (unpaged) data of one session for temporary
analysis jobs (jesse.services.analysis_jobs), which write it to a snapshot file so large
arrays never have to pass through the assistant. A live session over a row cap is refused
rather than exported in part.

Live and paper sessions are only readable when the live trading plugin is installed and
enabled, the same condition under which Jesse registers its /live routes. In their
responses and snapshots, every exact occurrence of a stored value (at least
MIN_REDACTED_SECRET_LENGTH characters) of the saved exchange and notification keys the
session's form references is replaced with "[redacted]", for example in a log line or
traceback. This is string matching, not a guarantee: other keys, encoded or partial forms
of a value, and secrets a strategy logged from elsewhere are not recognized. Redaction runs
before any text is cut. A session whose stored state names no readable form is redacted with
every saved key's values; a state of an unexpected shape fails the read (_state_secrets).
Reading never starts, stops, or changes a session (apart from the dashboard's own stale-status
fix, see _live_session_view).
"""
import json
import os
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterable, Iterator, List, Optional, Tuple
from uuid import UUID

import peewee

import jesse.helpers as jh
from jesse.services.project_files import ProjectFileError

SESSION_TYPES = ('backtest', 'optimization', 'monte_carlo', 'significance_test', 'live')
SECTIONS: Dict[str, Tuple[str, ...]] = {
    'backtest': ('summary', 'trades', 'equity_curve', 'hyperparameters', 'logs'),
    'optimization': ('summary', 'best_trials', 'objective_curve', 'logs'),
    'monte_carlo': ('summary', 'confidence_analysis', 'scenario_metrics', 'equity_curves', 'logs'),
    'significance_test': ('summary',),
    'live': ('summary', 'closed_trades', 'orders', 'equity_curve', 'logs', 'error_logs'),
}

DEFAULT_LIMIT = 50
MAX_LIMIT = 500
# A page is cut before its JSON exceeds this size (about 30k tokens), whatever `limit` says.
# Large enough for a few Monte Carlo scenario curves or several hundred trades; anything
# bigger belongs in a temporary analysis job, which reads the full snapshot server-side.
MAX_PAGE_BYTES = 128 * 1024
# Free text (descriptions, tracebacks) in summaries is cut to its last/first characters here.
MAX_TEXT_CHARS = 4000
# Individual log lines longer than this are cut; generated lines are short, but a strategy
# can log whole arrays or responses.
MAX_LOG_LINE_CHARS = 2000
# Reading log lines from the end scans at most this many bytes, so a request for a very old
# page of a huge log cannot read the whole file.
MAX_LOG_SCAN_BYTES = 16 * 1024 * 1024
# Upper bounds on rows exported for one live session into an analysis snapshot; a session with
# more is refused (too_many_records), never cut. Minute equity snapshots reach ~525k per year.
# A session near every cap at once can still exceed the 64 MiB snapshot cap (too_large).
MAX_EXPORT_LIVE_TRADES = 100_000
MAX_EXPORT_LIVE_ORDERS = 200_000
MAX_EXPORT_LIVE_EQUITY_POINTS = 600_000
# Saved credential values shorter than this are not searched for, so short fields such as
# a region code cannot redact ordinary words.
MIN_REDACTED_SECRET_LENGTH = 6
REDACTED = '[redacted]'

LOG_FILES = {
    'backtest': os.path.join('storage', 'logs', 'backtest-mode'),
    'optimization': os.path.join('storage', 'logs', 'optimize-mode'),
    'monte_carlo': os.path.join('storage', 'logs', 'monte-carlo-mode'),
}

STATUS_NOTES = {
    'draft': 'Not started yet, so there are no results.',
    'running': 'Still running; results may be missing or partial until it finishes.',
    'starting': 'Still starting; results may be missing until it runs.',
    'stopped': 'Stopped before finishing (an error or a cancellation); see `error` if present. Results may be partial.',
    'cancelled': 'Cancelled by a user request; results may be partial or empty.',
    'terminated': 'Terminated by a user request; results may be partial or empty.',
    'paused': 'Paused; results reflect the work done so far.',
}


def _error(error_type: str, message: str, status_code: int) -> ProjectFileError:
    return ProjectFileError(error_type, message, status_code)


def _clean(value: Any) -> Any:
    return jh.clean_nan_values(jh.clean_infinite_values(value))


def _json(text: Any, default: Any = None) -> Any:
    """Parse a stored JSON text column; already-parsed values pass through."""
    if text is None or text == '':
        return default
    if isinstance(text, (dict, list)):
        return _clean(text)
    try:
        return _clean(json.loads(text))
    except (TypeError, ValueError):
        return default


def _size(value: Any) -> int:
    return len(json.dumps(value, default=str, separators=(',', ':')))


def _cut_text(text: Optional[str], keep: str = 'start') -> Tuple[Optional[str], bool]:
    if text is None or len(text) <= MAX_TEXT_CHARS:
        return text, False
    return (text[:MAX_TEXT_CHARS] if keep == 'start' else text[-MAX_TEXT_CHARS:]), True


def _error_block(exception: Optional[str], traceback: Optional[str]) -> Optional[dict]:
    if not exception and not traceback:
        return None
    tail, cut = _cut_text(traceback, keep='end')
    return {'exception': exception, 'traceback_tail': tail, 'traceback_truncated': cut}


def _base(session_type: str, session_id: str, status: Optional[str]) -> dict:
    # `session_status`, not `status`: API responses use `status` for success/error.
    base = {'session_type': session_type, 'session_id': session_id, 'session_status': status}
    note = STATUS_NOTES.get((status or '').lower())
    if note:
        base['status_note'] = note
    return base


def _notes(title: Optional[str], description: Optional[str]) -> dict:
    text, cut = _cut_text(description)
    return {'title': title, 'description': text, 'description_truncated': cut}


# ---------------------------------------------------------------------------
# Validation and paging
# ---------------------------------------------------------------------------

def _validate(session_type: object, session_id: object, section: object, offset: object, limit: object) -> str:
    if session_type not in SESSION_TYPES:
        raise _error('invalid_request', f'session_type must be one of: {", ".join(SESSION_TYPES)}.', 400)
    try:
        normalized = str(UUID(str(session_id)))
    except (TypeError, ValueError):
        raise _error('invalid_request', 'session_id must be a session UUID.', 400)
    allowed = SECTIONS[str(session_type)]
    if section not in allowed:
        raise _error('invalid_request', f'section for {session_type} must be one of: {", ".join(allowed)}.', 400)
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise _error('invalid_request', 'offset must be 0 or greater.', 400)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise _error('invalid_request', f'limit must be between 1 and {MAX_LIMIT}.', 400)
    return normalized


def _page(items: List[Any], offset: int, limit: int, total: Optional[int] = None) -> dict:
    """
    Return items[offset:offset+limit], stopping early before the JSON would pass MAX_PAGE_BYTES.

    A single item that alone exceeds the budget is refused rather than cut, because a
    partial trade or curve would be misleading.
    """
    total = len(items) if total is None else total
    page: List[Any] = []
    used = 2
    truncated = False
    for item in items[offset:offset + limit]:
        size = _size(item) + 1
        if used + size > MAX_PAGE_BYTES:
            if not page:
                raise _error(
                    'item_too_large',
                    f'Item {offset} alone is larger than the {MAX_PAGE_BYTES // 1024} KiB page limit. '
                    'Analyze it with run_analysis, which reads the full data on the Jesse host.',
                    413,
                )
            truncated = True
            break
        page.append(item)
        used += size
    end = offset + len(page)
    return {
        'items': page,
        'offset': offset,
        'limit': limit,
        'returned': len(page),
        'total': total,
        'next_offset': end if end < total else None,
        'has_more': end < total,
        'truncated_by_size': truncated,
    }


def _page_series(series: List[dict], offset: int, limit: int) -> dict:
    """
    Page the points of several curves in parallel: points offset..offset+limit of each curve.

    The window shrinks until the page fits MAX_PAGE_BYTES, so `next_offset` may advance by
    less than `limit`.
    """
    total = max((len(s.get('data') or []) for s in series), default=0)
    window = limit
    while True:
        items = [
            {key: value for key, value in s.items() if key != 'data'}
            | {'points': (s.get('data') or [])[offset:offset + window], 'total_points': len(s.get('data') or [])}
            for s in series
        ]
        if _size(items) <= MAX_PAGE_BYTES or window == 1:
            break
        window = max(1, window // 2)
    if _size(items) > MAX_PAGE_BYTES:
        raise _error('item_too_large', 'One point of these curves is larger than the page limit.', 413)
    end = min(offset + window, total)
    return {
        'items': items,
        'offset': offset,
        'limit': limit,
        'returned': max(0, end - offset),
        'total': total,
        'next_offset': end if end < total else None,
        'has_more': end < total,
        'truncated_by_size': window < limit and end < min(offset + limit, total),
    }


def _log_lines_from_end(path: str, offset: int, limit: int) -> Optional[dict]:
    """
    Return `limit` lines of a text log, skipping the newest `offset` lines, oldest first.

    Reads backwards in chunks and never scans more than MAX_LOG_SCAN_BYTES. Returns None
    when the log file does not exist.
    """
    try:
        f = open(path, 'rb')
    except FileNotFoundError:
        return None
    with f:
        size = os.fstat(f.fileno()).st_size
        wanted = offset + limit + 1
        position = size
        # Chunks are counted as they are read and joined once, so a long scan stays linear.
        chunks: List[bytes] = []
        newlines = 0
        while position > 0 and newlines <= wanted and size - position < MAX_LOG_SCAN_BYTES:
            step = min(64 * 1024, position, MAX_LOG_SCAN_BYTES - (size - position))
            position -= step
            f.seek(position)
            chunk = f.read(step)
            chunks.append(chunk)
            newlines += chunk.count(b'\n')
        data = b''.join(reversed(chunks))
        reached_start = position == 0
    lines = data.decode('utf-8', errors='replace').splitlines()
    if not reached_start and lines:
        lines = lines[1:]  # Possibly a partial first line.
    if offset > len(lines) and not reached_start:
        raise _error(
            'offset_too_large',
            f'Only the last {MAX_LOG_SCAN_BYTES // (1024 * 1024)} MiB of this log can be paged. Use a smaller offset.',
            400,
        )
    newest_first = list(reversed(lines[max(0, len(lines) - offset - limit):len(lines) - offset] if offset < len(lines) else []))
    page = _page_from_newest(newest_first, offset, limit, len(lines) if reached_start else None)
    if not reached_start:
        page['has_more'] = True
        page['next_offset'] = offset + page['returned']
    return {**page, 'log_size_bytes': size}


def _page_from_newest(newest_first: List[Any], offset: int, limit: int, total: Optional[int]) -> dict:
    """
    Page log entries given newest first (already skipped by `offset`), returned oldest first.

    `total` is the number of entries in the whole log when known. Long text is cut to
    MAX_LOG_LINE_CHARS and the page to MAX_PAGE_BYTES, keeping the newest entries.
    """
    items: List[Any] = []
    used = 2
    truncated = False
    for entry in newest_first[:limit]:
        if isinstance(entry, str) and len(entry) > MAX_LOG_LINE_CHARS:
            entry = entry[:MAX_LOG_LINE_CHARS] + ' [line cut]'
        elif isinstance(entry, dict) and isinstance(entry.get('message'), str) and len(entry['message']) > MAX_LOG_LINE_CHARS:
            entry = {**entry, 'message': entry['message'][:MAX_LOG_LINE_CHARS] + ' [line cut]'}
        size = _size(entry) + 1
        if used + size > MAX_PAGE_BYTES:
            truncated = True
            break
        items.append(entry)
        used += size
    end = offset + len(items)
    more = total is None or end < total
    return {
        'items': list(reversed(items)),
        'offset': offset,
        'limit': limit,
        'returned': len(items),
        'total': total,
        'next_offset': end if more else None,
        'has_more': more,
        'truncated_by_size': truncated,
        'order': 'offset counts entries back from the newest; each page is oldest first',
    }


def _db_page(rows: List[Any], offset: int, limit: int, total: int) -> dict:
    """Page rows already fetched from the database with OFFSET/LIMIT, applying the size budget."""
    page = _page(rows, 0, limit, total=len(rows))
    end = offset + page['returned']
    return {**page, 'offset': offset, 'total': total, 'next_offset': end if end < total else None, 'has_more': end < total}


def _file_log_section(session_type: str, session_id: str, offset: int, limit: int) -> dict:
    page = _log_lines_from_end(os.path.join(LOG_FILES[session_type], f'{session_id}.txt'), offset, limit)
    if page is None:
        return {'available': False, 'message': 'No log file exists for this session.', **_page([], 0, limit)}
    return {'available': True, **page}


def _log_file_size(session_type: str, session_id: str) -> Optional[int]:
    try:
        return os.path.getsize(os.path.join(LOG_FILES[session_type], f'{session_id}.txt'))
    except OSError:
        return None


# ---------------------------------------------------------------------------
# Database access (module-level so tests can substitute stored records)
# ---------------------------------------------------------------------------

def _load_backtest(session_id: str):
    from jesse.models.BacktestSession import get_backtest_session_by_id
    return get_backtest_session_by_id(session_id)


def _load_optimization(session_id: str):
    from jesse.models.OptimizationSession import get_optimization_session_by_id
    return get_optimization_session_by_id(session_id)


def _load_monte_carlo(session_id: str):
    from jesse.models.MonteCarloSession import get_monte_carlo_session_by_id
    return get_monte_carlo_session_by_id(session_id)


def _load_significance_test(session_id: str):
    from jesse.models.SignificanceTestSession import get_significance_test_session_by_id
    return get_significance_test_session_by_id(session_id)


def _load_live(session_id: str):
    from jesse.repositories import live_session_repository
    return live_session_repository.get_live_session_by_id(session_id)


def _live_plugin_available() -> bool:
    return jh.has_live_trade_plugin()


def _live_session_view(row, persist_reconciliation: bool = True) -> dict:
    """
    The dashboard's live session view, including its running-worker status reconciliation, which
    it writes back unless `persist_reconciliation` is False (read-only snapshots).
    """
    from jesse.services.transformers import get_live_session
    return get_live_session(row, persist_reconciliation)


@contextmanager
def _read_snapshot() -> Iterator[None]:
    """
    Run a history page (live_history) or one analysis snapshot input (a live session export or a
    live history dataset) against a single consistent, read-only view of the database, so its
    counts, rows, their orders, sessions, and saved keys agree even while live sessions write.

    PostgreSQL (Jesse's database): one REPEATABLE READ, READ ONLY transaction, whose snapshot is
    taken by its first query; writers are never blocked by it and it cannot write. SQLite (tests):
    one deferred transaction; in WAL mode its first read fixes the snapshot, otherwise its shared
    lock holds writers back until it ends. The transaction ends with the block, including an
    error or a generator closed early, so a refusal never leaves it open.
    """
    from jesse.models.ClosedTrade import ClosedTrade
    db = ClosedTrade._meta.database
    if db.in_transaction():
        # Only when a caller already holds a transaction on this connection; its view applies.
        yield
        return
    postgres = isinstance(db, peewee.PostgresqlDatabase)
    if postgres and not db.is_closed():
        # SET TRANSACTION must be the first statement of the transaction. PostgreSQL connections
        # are idle between peewee statements (commit_select), except after an earlier failed
        # statement on this thread's connection, which leaves an aborted transaction behind.
        db.rollback()
    with db.atomic():
        if postgres:
            db.execute_sql('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        yield


def _live_trades(session_id: str, offset: int, limit: Optional[int]) -> Tuple[List[dict], int]:
    """Closed and open trades of a live session, oldest first, with their executed orders' values."""
    from jesse.models.ClosedTrade import ClosedTrade
    from jesse.repositories.closed_trade_repository import history_query, populate_order_arrays
    from jesse.services.transformers import get_closed_trade_details

    query = history_query(session_id=session_id)
    total = query.count()
    rows = query.order_by(ClosedTrade.opened_at, ClosedTrade.id).offset(offset)
    if limit is not None:
        rows = rows.limit(limit)
    trades = []
    for trade in rows:
        details = get_closed_trade_details(populate_order_arrays(trade))
        details['orders_count'] = len(details.pop('orders', []))
        trades.append(details)
    return trades, total


def _live_orders(session_id: str, offset: int, limit: Optional[int]) -> Tuple[List[dict], int]:
    from jesse.models.Order import Order
    from jesse.repositories.order_repository import history_query
    from jesse.services.transformers import get_order_details

    query = history_query(session_id=session_id)
    total = query.count()
    rows = query.order_by(Order.created_at, Order.id).offset(offset)
    if limit is not None:
        rows = rows.limit(limit)
    return [get_order_details(order) for order in rows], total


def _live_equity(session_id: str, offset: int, limit: Optional[int]) -> Tuple[List[dict], int]:
    """Raw per-minute equity snapshots, oldest first."""
    from jesse.models.LiveEquitySnapshot import LiveEquitySnapshot

    query = LiveEquitySnapshot.select().where(LiveEquitySnapshot.session_id == session_id)
    total = query.count()
    rows = query.order_by(LiveEquitySnapshot.timestamp).offset(offset)
    if limit is not None:
        rows = rows.limit(limit)
    return [_clean({'time': row.timestamp, 'equity': row.equity, 'currency': row.currency}) for row in rows], total


def _live_logs(session_id: str, log_type: int, offset: int, limit: int) -> Tuple[List[dict], int]:
    """Live log rows of one type (1 info, 2 error), newest first."""
    from jesse.models.Log import Log

    query = Log.select().where((Log.session_id == session_id) & (Log.type == log_type))
    total = query.count()
    rows = query.order_by(Log.timestamp.desc(), Log.id.desc()).offset(offset).limit(limit)
    return [{'timestamp': row.timestamp, 'message': row.message} for row in rows], total


def _live_counts(session_id: str) -> dict:
    from jesse.models.ClosedTrade import ClosedTrade
    from jesse.models.LiveEquitySnapshot import LiveEquitySnapshot
    from jesse.models.Log import Log
    from jesse.models.Order import Order

    trades = ClosedTrade.select().where(ClosedTrade.session_id == session_id)
    snapshots = LiveEquitySnapshot.select().where(LiveEquitySnapshot.session_id == session_id)
    first = snapshots.order_by(LiveEquitySnapshot.timestamp).first()
    last = snapshots.order_by(LiveEquitySnapshot.timestamp.desc()).first()
    return {
        'trades': trades.count(),
        'open_trades': trades.where(ClosedTrade.closed_at.is_null(True)).count(),
        'orders': Order.select().where(Order.session_id == session_id).count(),
        'info_logs': Log.select().where((Log.session_id == session_id) & (Log.type == 1)).count(),
        'error_logs': Log.select().where((Log.session_id == session_id) & (Log.type == 2)).count(),
        'equity_points': snapshots.count(),
        'first_equity': _clean({'time': first.timestamp, 'equity': first.equity, 'currency': first.currency}) if first else None,
        'last_equity': _clean({'time': last.timestamp, 'equity': last.equity, 'currency': last.currency}) if last else None,
    }


def _credential_values(value: Any) -> List[str]:
    """
    Every scalar inside a stored credential field, including values nested in objects or
    lists and JSON text; numbers are included as text (e.g. a numeric chat ID).
    """
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except ValueError:
            return [value]
        return [value, *(_credential_values(parsed) if isinstance(parsed, (dict, list)) else [])]
    if isinstance(value, dict):
        return [v for item in value.values() for v in _credential_values(item)]
    if isinstance(value, list):
        return [v for item in value for v in _credential_values(item)]
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return [str(value)]
    return []


def _key_id(value: Any) -> Optional[str]:
    """A saved-key ID from the session form, or None when it cannot reference a key (e.g. a draft's '')."""
    try:
        return str(UUID(str(value))) if value else None
    except ValueError:
        return None


def _live_secrets(form: dict) -> List[str]:
    """
    Saved credential values of the keys this session uses, for redaction only; never returned.

    Keys deleted since the session ran simply contribute nothing. Any other failure to read
    them propagates, so a response is never sent unredacted because the lookup failed.
    """
    from jesse.models.ExchangeApiKeys import ExchangeApiKeys
    from jesse.models.NotificationApiKeys import NotificationApiKeys

    values: List[str] = []
    exchange_key_id = _key_id(form.get('exchange_api_key_id'))
    if exchange_key_id:
        key = ExchangeApiKeys.get_or_none(ExchangeApiKeys.id == exchange_key_id)
        if key is not None:
            values += _credential_values([key.api_key, key.api_secret, key.additional_fields])
    notification_key_id = _key_id(form.get('notification_api_key_id'))
    if notification_key_id:
        key = NotificationApiKeys.get_or_none(NotificationApiKeys.id == notification_key_id)
        if key is not None:
            values += _credential_values(key.fields)
    return sorted({v for v in values if len(v) >= MIN_REDACTED_SECRET_LENGTH}, key=len, reverse=True)


def _all_saved_secrets() -> List[str]:
    """Values of every saved exchange and notification key, when a session's own keys are unknown."""
    from jesse.models.ExchangeApiKeys import ExchangeApiKeys
    from jesse.models.NotificationApiKeys import NotificationApiKeys

    values: List[str] = []
    for key in ExchangeApiKeys.select():
        values += _credential_values([key.api_key, key.api_secret, key.additional_fields])
    for key in NotificationApiKeys.select():
        values += _credential_values(key.fields)
    return sorted({v for v in values if len(v) >= MIN_REDACTED_SECRET_LENGTH}, key=len, reverse=True)


def _unreadable_state(session_id: Any) -> ProjectFileError:
    return _error('read_failed', f'The stored state of live session {session_id} cannot be read, so the saved keys it '
                                 'uses cannot be redacted; nothing was returned.', 500)


KEY_FORM_FIELDS = ('exchange_api_key_id', 'notification_api_key_id')


def _state_secrets(state: Any, session_id: Any) -> List[str]:
    """
    Redaction values for a live session from its parsed stored state (None when it has none).

    Only a readable form object whose key fields are text (or absent/null) is trusted to name the
    session's keys, including naming none. A missing state or form says nothing about which keys
    were used, so every saved key's values are used, as for a deleted session. A state or form of
    any other shape fails the read (read_failed): it may reference keys in a way this code cannot see.
    """
    if state is None:
        return _all_saved_secrets()
    if not isinstance(state, dict):
        raise _unreadable_state(session_id)
    form = state.get('form')
    if form is None:
        return _all_saved_secrets()
    if not isinstance(form, dict) or any(form.get(field) is not None and not isinstance(form[field], str)
                                         for field in KEY_FORM_FIELDS):
        raise _unreadable_state(session_id)
    return _live_secrets(form)


def _stored_state_secrets(state_text: Optional[str], session_id: Any) -> List[str]:
    """_state_secrets for a LiveSession.state column (JSON text); unparsable text fails the read."""
    if state_text is None or state_text == '':
        return _state_secrets(None, session_id)
    try:
        state = json.loads(state_text)
    except (TypeError, ValueError):
        raise _unreadable_state(session_id)
    return _state_secrets(state, session_id)


def _redact(value: Any, secrets: List[str]) -> Any:
    if not secrets:
        return value
    if isinstance(value, str):
        for secret in secrets:
            if secret in value:
                value = value.replace(secret, REDACTED)
        return value
    if isinstance(value, dict):
        return {k: _redact(v, secrets) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v, secrets) for v in value]
    return value


def _not_found(label: str, session_id: str) -> ProjectFileError:
    return _error('not_found', f'{label} session {session_id} does not exist.', 404)


# ---------------------------------------------------------------------------
# Backtest
# ---------------------------------------------------------------------------

def _backtest_parts(row) -> dict:
    return {
        'state': _json(row.state, {}) or {},
        'metrics': _json(row.metrics),
        'trades': _json(row.trades, []) or [],
        'equity_curve': _json(row.equity_curve, []) or [],
        'hyperparameters': _json(row.hyperparameters, []) or [],
    }


def _backtest_summary(row, session_id: str, parts: dict) -> dict:
    form = parts['state'].get('form') if isinstance(parts['state'], dict) else None
    charts_image = os.path.exists(os.path.join('storage', 'backtest-charts', f'{session_id}_equity_curve.png'))
    return {
        **_base('backtest', session_id, row.status),
        **_notes(row.title, row.description),
        'created_at': row.created_at,
        'updated_at': row.updated_at,
        'execution_duration': row.execution_duration,
        'form': form,
        'metrics': parts['metrics'],
        'error': _error_block(row.exception, row.traceback),
        'has_chart_data': bool(row.chart_data),
        'has_charts_image': charts_image,
        'sections': {
            'trades': {'count': len(parts['trades'])},
            'equity_curve': {'series': [
                {'name': s.get('name'), 'points': len(s.get('data') or [])}
                for s in parts['equity_curve'] if isinstance(s, dict)
            ]},
            'hyperparameters': {'count': len(parts['hyperparameters'])},
            'logs': {'log_size_bytes': _log_file_size('backtest', session_id)},
        },
    }


def _backtest(session_id: str, section: str, offset: int, limit: int) -> dict:
    row = _load_backtest(session_id)
    if not row:
        raise _not_found('Backtest', session_id)
    if section == 'logs':
        return {**_base('backtest', session_id, row.status), 'section': section,
                **_file_log_section('backtest', session_id, offset, limit)}
    parts = _backtest_parts(row)
    if section == 'summary':
        return _backtest_summary(row, session_id, parts)
    head = {**_base('backtest', session_id, row.status), 'section': section}
    if section == 'trades':
        return {**head, 'order': 'as stored (chronological)', **_page(parts['trades'], offset, limit)}
    if section == 'equity_curve':
        series = [s for s in parts['equity_curve'] if isinstance(s, dict)]
        return {**head, **_page_series(series, offset, limit)}
    return {**head, **_page(parts['hyperparameters'], offset, limit)}


# ---------------------------------------------------------------------------
# Optimization
# ---------------------------------------------------------------------------

# Metrics shown for the leading trials in the optimization summary; the best_trials section
# returns every stored metric.
SUMMARY_TRIAL_METRICS = ('net_profit_percentage', 'max_drawdown', 'sharpe_ratio', 'win_rate', 'total')
SUMMARY_TRIALS = 3


def _optimization_view(row) -> dict:
    from jesse.services.transformers import get_optimization_session_for_load_more
    return _clean(get_optimization_session_for_load_more(row))


def _optimization(session_id: str, section: str, offset: int, limit: int) -> dict:
    row = _load_optimization(session_id)
    if not row:
        raise _not_found('Optimization', session_id)
    head = {**_base('optimization', session_id, row.status), 'section': section}
    if section == 'logs':
        return {**head, **_file_log_section('optimization', session_id, offset, limit)}
    view = _optimization_view(row)
    trials = view.get('best_candidates') or []
    curve = view.get('objective_curve')
    if section == 'best_trials':
        return {**head, 'order': 'best first', **_page(trials, offset, limit)}
    if section == 'objective_curve':
        items = curve if isinstance(curve, list) else ([] if curve is None else [curve])
        return {**head, **_page(items, offset, limit)}

    state = view.get('state') if isinstance(view.get('state'), dict) else {}
    leading = []
    for trial in trials[:SUMMARY_TRIALS]:
        leading.append({
            'rank': trial.get('rank'),
            'trial': trial.get('trial'),
            'params': trial.get('params'),
            'fitness': trial.get('fitness'),
            'objective_metric_training_testing': trial.get('objective_metric'),
            'training_metrics': {k: (trial.get('training_metrics') or {}).get(k) for k in SUMMARY_TRIAL_METRICS},
            'testing_metrics': {k: (trial.get('testing_metrics') or {}).get(k) for k in SUMMARY_TRIAL_METRICS},
        })
    return {
        **_base('optimization', session_id, row.status),
        **_notes(row.title, row.description),
        'created_at': row.created_at,
        'updated_at': row.updated_at,
        'completed_trials': row.completed_trials,
        'total_trials': row.total_trials,
        'best_score': view.get('best_score'),
        'form': state.get('form'),
        'leading_trials': leading,
        'error': _error_block(row.exception, row.traceback),
        'sections': {
            'best_trials': {'count': len(trials)},
            'objective_curve': {'count': len(curve) if isinstance(curve, list) else (0 if curve is None else 1)},
            'logs': {'log_size_bytes': _log_file_size('optimization', session_id)},
        },
    }


# ---------------------------------------------------------------------------
# Monte Carlo
# ---------------------------------------------------------------------------

def _monte_carlo_pipelines(row) -> List[Tuple[str, Any]]:
    return [(name, child) for name, child in (('candles', row.candles_session), ('trades', row.trades_session)) if child]


def _portfolio_curve(result: Any) -> Optional[dict]:
    """The Portfolio series of a backtest-style result, as the dashboard's equity-curves route picks it."""
    if not isinstance(result, dict):
        return None
    for curve in result.get('equity_curve') or []:
        if isinstance(curve, dict) and curve.get('name') == 'Portfolio':
            return curve
    return None


def _scenario_values(scenario: Any) -> dict:
    """A scenario's stored metrics and scalar fields, without its bulky curves and trade lists."""
    if not isinstance(scenario, dict):
        return {}
    values = {k: v for k, v in scenario.items() if isinstance(v, (int, float, str, bool)) or v is None}
    if isinstance(scenario.get('metrics'), dict):
        values['metrics'] = scenario['metrics']
    return values


def _monte_carlo_summary(row, session_id: str) -> dict:
    from jesse.services.transformers import get_monte_carlo_session_for_load_more
    view = _clean(get_monte_carlo_session_for_load_more(row))
    pipelines = {}
    for name in ('candles', 'trades'):
        child = view.get(f'{name}_session')
        if not child:
            continue
        pipelines[name] = {
            'status': child.get('status'),
            'num_scenarios': child.get('num_scenarios'),
            'completed_scenarios': child.get('completed_scenarios'),
            'summary_metrics': child.get('summary_metrics'),
            'error': _error_block(child.get('exception'), child.get('traceback')),
            **({'pipeline_type': child.get('pipeline_type'), 'pipeline_params': child.get('pipeline_params')}
               if name == 'candles' else {}),
        }
    state = view.get('state') if isinstance(view.get('state'), dict) else {}
    return {
        **_base('monte_carlo', session_id, row.status),
        **_notes(row.title, row.description),
        'created_at': row.created_at,
        'updated_at': row.updated_at,
        'form': state.get('form'),
        'pipelines': pipelines,
        'summary_metrics_columns': 'original = the unmodified backtest; worst_5 / median / best_5 = 5th / 50th / 95th percentile across scenarios',
        'sections': {'logs': {'log_size_bytes': _log_file_size('monte_carlo', session_id)}},
    }


def _monte_carlo(session_id: str, section: str, offset: int, limit: int) -> dict:
    row = _load_monte_carlo(session_id)
    if not row:
        raise _not_found('Monte Carlo', session_id)
    head = {**_base('monte_carlo', session_id, row.status), 'section': section}
    if section == 'summary':
        return _monte_carlo_summary(row, session_id)
    if section == 'logs':
        page = _file_log_section('monte_carlo', session_id, offset, limit)
        if not page['available']:
            # Without a log file, fall back to the log text stored with each pipeline's record.
            lines = []
            for name, child in _monte_carlo_pipelines(row):
                lines += [f'[{name}] {line}' for line in (child.logs or '').splitlines()]
            newest_first = list(reversed(lines))[offset:offset + limit]
            page = {'available': bool(lines), 'source': 'database', **_page_from_newest(newest_first, offset, limit, len(lines))}
        return {**head, **page}

    items: List[Any] = []
    for name, child in _monte_carlo_pipelines(row):
        if not child.results:
            continue
        results = _clean(child.results_json)
        if section == 'confidence_analysis':
            items.append({'pipeline': name, 'confidence_analysis': results.get('confidence_analysis'),
                          'num_scenarios': results.get('num_scenarios'), 'total_requested': results.get('total_requested')})
        elif section == 'scenario_metrics':
            items.append({'pipeline': name, 'scenario': 'original', **_scenario_values(results.get('original'))})
            items += [{'pipeline': name, 'scenario': i, **_scenario_values(s)} for i, s in enumerate(results.get('scenarios') or [])]
        else:
            original = _portfolio_curve(results.get('original'))
            if original:
                items.append({'pipeline': name, 'scenario': 'original', **original})
            for i, scenario in enumerate(results.get('scenarios') or []):
                curve = _portfolio_curve(scenario)
                if curve:
                    items.append({'pipeline': name, 'scenario': i, **curve})
    return {**head, **_page(items, offset, limit)}


# ---------------------------------------------------------------------------
# Significance test
# ---------------------------------------------------------------------------

def _significance_test(session_id: str, section: str, offset: int, limit: int) -> dict:
    row = _load_significance_test(session_id)
    if not row:
        raise _not_found('Significance test', session_id)
    state = _json(row.state, {}) or {}
    return {
        **_base('significance_test', session_id, row.status),
        **_notes(row.title, row.description),
        'created_at': row.created_at,
        'updated_at': row.updated_at,
        'form': state.get('form') if isinstance(state, dict) else None,
        'results': _json(row.results),
        'has_chart': bool(row.chart_path) and os.path.exists(row.chart_path),
        'error': _error_block(row.exception, row.traceback),
    }


# ---------------------------------------------------------------------------
# Live and paper sessions
# ---------------------------------------------------------------------------

def _require_live_plugin() -> None:
    if not _live_plugin_available():
        raise _error(
            'live_plugin_unavailable',
            'Live and paper trading sessions need the Jesse live trading plugin, which is not installed '
            'or is disabled on this Jesse instance.',
            403,
        )


def _live(session_id: str, section: str, offset: int, limit: int, persist_reconciliation: bool = True) -> dict:
    _require_live_plugin()
    row = _load_live(session_id)
    if not row:
        raise _not_found('Live', session_id)
    # From the stored column itself, not the transformed view, so no parsing step in between can
    # turn an unreadable state into an empty one.
    secrets = _stored_state_secrets(row.state, session_id)
    view = _clean(_live_session_view(row, persist_reconciliation))
    # Redact before anything is cut (description, traceback tail, log lines below), so a saved
    # value crossing a cut is never partly returned.
    view = _redact(view, secrets)
    state = view.get('state') if isinstance(view.get('state'), dict) else {}
    form = state.get('form') if isinstance(state.get('form'), dict) else {}
    head = {**_base('live', session_id, view.get('status')), 'session_mode': view.get('session_mode'), 'section': section}

    if section == 'summary':
        result = {
            **head,
            **_notes(view.get('title'), view.get('description')),
            'is_active': view.get('is_active'),
            'exchange': view.get('exchange'),
            'created_at': view.get('created_at'),
            'updated_at': view.get('updated_at'),
            'finished_at': view.get('finished_at'),
            'form': form or None,
            'error': _error_block(view.get('exception'), view.get('traceback')),
            'counts': _live_counts(session_id),
        }
        result.pop('section')
    elif section in ('closed_trades', 'orders', 'equity_curve'):
        loader: Callable[[str, int, Optional[int]], Tuple[List[dict], int]] = {
            'closed_trades': _live_trades, 'orders': _live_orders, 'equity_curve': _live_equity,
        }[section]
        rows, total = loader(session_id, offset, limit)
        result = {**head, 'order': 'oldest first', **_db_page(rows, offset, limit, total)}
    else:
        rows, total = _live_logs(session_id, 1 if section == 'logs' else 2, offset, limit)
        result = {**head, **_page_from_newest(_redact(rows, secrets), offset, limit, total)}
    return _redact(result, secrets)


_READERS = {
    'backtest': _backtest,
    'optimization': _optimization,
    'monte_carlo': _monte_carlo,
    'significance_test': _significance_test,
    'live': _live,
}


def get_results(session_type: str, session_id: str, section: str = 'summary', offset: int = 0,
                limit: int = DEFAULT_LIMIT) -> dict:
    """Return the summary or one bounded page of a section of a stored session."""
    normalized = _validate(session_type, session_id, section, offset, limit)
    return _READERS[session_type](normalized, section, offset, limit)


def list_live_sessions(limit: int = 20, offset: int = 0, status_filter: Optional[str] = None,
                       mode_filter: Optional[str] = None, title_search: Optional[str] = None) -> dict:
    """Compact live/paper session list (newest activity first); drafts are excluded like on the dashboard."""
    _require_live_plugin()
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise _error('invalid_request', 'limit must be between 1 and 100.', 400)
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise _error('invalid_request', 'offset must be 0 or greater.', 400)
    rows = _list_live_rows(limit, offset, title_search, status_filter, mode_filter)
    sessions = []
    for row in rows:
        # Titles and routes are free text too; each row is redacted with its own session's keys.
        secrets = _stored_state_secrets(row.state, row.id)
        view = _clean(_live_session_view(row))
        state = view.get('state') if isinstance(view.get('state'), dict) else {}
        form = state.get('form') if isinstance(state.get('form'), dict) else {}
        sessions.append(_redact({
            'id': view.get('id'),
            'title': view.get('title'),
            'status': view.get('status'),
            'is_active': view.get('is_active'),
            'session_mode': view.get('session_mode'),
            'exchange': view.get('exchange'),
            'routes': form.get('routes'),
            'created_at': view.get('created_at'),
            'updated_at': view.get('updated_at'),
            'finished_at': view.get('finished_at'),
            'has_error': bool(view.get('exception')),
        }, secrets))
    return {'sessions': sessions, 'offset': offset, 'limit': limit, 'returned': len(sessions),
            'next_offset': offset + len(sessions) if len(sessions) == limit else None}


def _list_live_rows(limit: int, offset: int, title_search, status_filter, mode_filter) -> Iterable:
    from jesse.repositories import live_session_repository
    return live_session_repository.get_live_sessions(
        limit=limit, offset=offset, title_search=title_search, status_filter=status_filter,
        date_filter=None, mode_filter=mode_filter,
    )


# ---------------------------------------------------------------------------
# Full exports for temporary analysis snapshots
# ---------------------------------------------------------------------------

def export_session(session_type: str, session_id: str) -> dict:
    """
    Return one session's complete stored results for an analysis snapshot.

    Contains the summary plus every row of the result arrays (logs excluded), never paged.
    Live exports are redacted like live responses, read in one consistent view (_export_live),
    and a live session with more rows than a MAX_EXPORT_LIVE_* cap is refused
    (too_many_records) instead of being cut.
    """
    normalized = _validate(session_type, session_id, 'summary', 0, 1)
    if session_type == 'live':
        return _export_live(normalized)
    summary = get_results(session_type, normalized)
    if session_type == 'backtest':
        parts = _backtest_parts(_load_backtest(normalized))
        return {'summary': summary, 'metrics': parts['metrics'], 'trades': parts['trades'],
                'equity_curve': parts['equity_curve'], 'hyperparameters': parts['hyperparameters']}
    if session_type == 'optimization':
        view = _optimization_view(_load_optimization(normalized))
        return {'summary': summary, 'best_trials': view.get('best_candidates') or [],
                'objective_curve': view.get('objective_curve')}
    if session_type == 'monte_carlo':
        pipelines = {}
        for name, child in _monte_carlo_pipelines(_load_monte_carlo(normalized)):
            pipelines[name] = _clean(child.results_json) if child.results else None
        return {'summary': summary, 'pipelines': pipelines}
    return {'summary': summary}


def _export_live(session_id: str) -> dict:
    """
    A live session's snapshot, read in one consistent read-only database view (_read_snapshot):
    the summary, its counts, and every row agree even while the session is still writing. The
    dashboard's stale-status reconciliation is reported in the summary but not written back; it
    reads the Redis worker set at that moment, outside the database view (best effort).
    """
    _require_live_plugin()
    with _read_snapshot():
        return _export_live_rows(session_id)


def _export_live_rows(session_id: str) -> dict:
    row = _load_live(session_id)
    if not row:
        raise _not_found('Live', session_id)
    secrets = _stored_state_secrets(row.state, session_id)
    summary = _live(session_id, 'summary', 0, 1, persist_reconciliation=False)
    counts = summary.get('counts') or {}
    sections = (
        ('closed_trades', 'trades', _live_trades, MAX_EXPORT_LIVE_TRADES),
        ('orders', 'orders', _live_orders, MAX_EXPORT_LIVE_ORDERS),
        ('equity_curve', 'equity_points', _live_equity, MAX_EXPORT_LIVE_EQUITY_POINTS),
    )
    # Every cap is checked from the summary's counts before any rows are loaded.
    for section, count_key, _loader, cap in sections:
        _refuse_live_export(session_id, section, counts.get(count_key) or 0, cap)
    data: Dict[str, Any] = {'summary': summary}
    for section, _count_key, loader, cap in sections:
        # One row past the cap is read: a guard for writes made through this same connection, as
        # nothing else can change the rows inside the snapshot.
        rows, total = loader(session_id, 0, cap + 1)
        _refuse_live_export(session_id, section, max(total, len(rows)), cap)
        data[section] = rows
    data['complete'] = True
    return _redact(data, secrets)


def _refuse_live_export(session_id: str, section: str, count: int, cap: int) -> None:
    if count > cap:
        raise _error(
            'too_many_records',
            f'Live session {session_id} has {count} {section.replace("_", " ")} rows; an analysis snapshot of one '
            f'session is limited to {cap}. Nothing was run. For trades and orders, analyze date windows with '
            '{"dataset": "live_trades" | "live_orders", ...} inputs (see jesse://session_analysis); page the '
            'equity curve with get_session_results.',
            413,
        )
