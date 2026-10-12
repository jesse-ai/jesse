"""
Jesse-recorded live/paper trade and order history across sessions, selected by date window.

`list_trades()` and `list_orders()` return bounded pages for MCP assistants; `iter_dataset_json()`
streams the complete filtered history into a temporary analysis snapshot
(jesse.services.analysis_jobs), so a question like "analyze my trades of the last 7 days" never
needs the rows to pass through the assistant.

What the data is: the ClosedTrade and Order rows Jesse's live plugin wrote while its live and
paper sessions ran. It is not the exchange account's history: trades made outside Jesse, or while
no session ran, are missing, and nothing here contacts an exchange.

Semantics shared by pages and snapshots:
- Windows are half-open UTC ranges [start, end) in milliseconds. `start`/`end` are RFC 3339
  date-times with an explicit offset; `recent_days` (or the default window) is resolved once
  against the current time and returned as explicit bounds.
- Pages continue with a keyset cursor: `next_page` holds every argument of the selection plus a
  cursor after the last record's (time, id) key, bound to that exact window, mode, filters, and
  order. Rows added or removed before the cursor never shift later pages; rows changed between
  calls (a trade the plugin reconciles later) can still appear or disappear in later pages.
- Trades are closed trades selected by `closed_at`. Open trades are never included; their count
  is reported separately. Trades the plugin discarded or merged into another trade
  (`soft_deleted_at` set) are excluded, as their orders belong to the surviving trade.
- Orders are selected by `created_at` (default) or `executed_at` (orders without it never match)
  and keep their stored status and timestamps.
- `mode` defaults to live trading only, so paper results are never mixed into real ones unless
  asked for.
- Every filter is applied in the database query before counting and paging, and every ordering
  ends with the row ID, so equal timestamps page deterministically.
- Each page, and each analysis snapshot input, is read inside one read-only transaction
  (session_results._read_snapshot), so its count, rows, their orders, sessions, and saved keys agree even while
  sessions write. Separate pages and separate analysis inputs are separate views.
- Pages are bounded by record count and by their full serialized size as the client receives it;
  trade pages also by the executed orders loaded to compute them.
- Values are computed with the same model properties the dashboard uses; no balances or account
  performance are derived here.

Redaction: every record is redacted with the saved exchange and notification key values that its
own session's form references (session_results._state_secrets). A record whose session no longer
exists, or whose session has no readable form, is redacted with the values of every saved key; a
session state of an unexpected shape, or a key lookup that fails, fails the read, so nothing is
returned unredacted. Text is redacted before it is cut. Reading never writes to the database.
"""
import base64
import binascii
import hashlib
import json
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterator, List, Optional, Tuple
from uuid import UUID

import numpy as np
import pydantic_core

import jesse.helpers as jh
from jesse.enums import live_session_modes, live_session_statuses, order_statuses
from jesse.repositories import closed_trade_repository, order_repository
from jesse.services import session_results
from jesse.services.project_files import ProjectFileError

DATASETS = ('live_trades', 'live_orders')
MODES: Dict[str, Tuple[str, ...]] = {
    'live': (live_session_modes.LIVETRADE,),
    'paper': (live_session_modes.PAPERTRADE,),
    'all': (live_session_modes.LIVETRADE, live_session_modes.PAPERTRADE),
}
DEFAULT_MODE = 'live'
# "Recent" questions are usually about the last few days; a week covers them without paging
# through months of history by accident.
DEFAULT_RECENT_DAYS = 7
# One year (plus a leap day); longer spans are still possible with explicit start/end.
MAX_RECENT_DAYS = 366
DAY_MS = 24 * 60 * 60 * 1000
DEFAULT_LIMIT = 100
# Same per-page record bound as get_session_results.
MAX_LIMIT = session_results.MAX_LIMIT
# A whole page (records, session details, and envelope) is cut to fit this many bytes as the
# client receives it: the text FastMCP renders for a dict result, escaped as a JSON string inside
# the JSON-RPC message. Same 128 KiB (~30k tokens) budget as get_session_results pages.
MAX_RESPONSE_BYTES = 128 * 1024
# Reserved within that budget for what wraps the page after it is built: the route's "status",
# the MCP service's "action", "location" (~130 bytes), and "session_dashboard_url_template" (one
# link, up to ~350 bytes for the longest valid DASHBOARD_URL), the JSON-RPC result object (~120
# bytes), and SSE framing (~25 bytes).
TRANSPORT_ALLOWANCE = 2 * 1024
# Cursors are small base64url JSON objects (~140 characters); anything longer is not one.
MAX_CURSOR_CHARS = 512
CURSOR_VERSION = 1
# Trade values need every executed order of the trade (the dashboard loads them all too). One
# trade with more than this is refused rather than computed from part of its orders; ordinary
# strategies have a handful, heavy DCA/grid strategies hundreds.
MAX_ORDERS_PER_TRADE = 10_000
# Executed orders held in memory at once while computing a trade page or snapshot batch (a few
# MB of rows). A page stops early instead (truncated_by_orders); a snapshot works in chunks.
MAX_HYDRATED_ORDERS = 20_000
ORDERINGS = ('newest_first', 'oldest_first')
ORDER_TIME_FIELDS = ('created_at', 'executed_at')
ORDER_STATUSES = (
    order_statuses.ACTIVE, order_statuses.CANCELED, order_statuses.EXECUTED, order_statuses.PARTIALLY_FILLED,
    order_statuses.QUEUED, order_statuses.LIQUIDATED, order_statuses.REJECTED,
)
# Exchange names and symbols are short identifiers ("Bybit USDT Perpetual", "BTC-USDT").
MAX_FILTER_CHARS = 100
# Analysis snapshots refuse larger selections instead of truncating them. Records have no fixed
# size; realistic ones measure about 600 bytes of JSON (long exchange names, symbols, and exchange
# order IDs), so 100,000 of them fit the 64 MiB snapshot cap, which analysis_jobs enforces
# separately while writing (too_large).
MAX_ANALYSIS_TRADES = 100_000
MAX_ANALYSIS_ORDERS = 100_000
# Rows read per database round trip while streaming a snapshot; bounds memory to one batch.
BATCH_SIZE = 1000
# Session titles (up to 255 characters in LiveSession) are cut to this after redaction.
MAX_SESSION_TITLE_CHARS = 200

TRADE_PARAMS = ('start', 'end', 'recent_days', 'mode', 'exchange', 'symbol', 'session_id')
ORDER_PARAMS = TRADE_PARAMS + ('time_field', 'status')
PARAMS = {'live_trades': TRADE_PARAMS, 'live_orders': ORDER_PARAMS}
PAGE_PARAMS = ('order', 'cursor', 'limit')

SOURCE = ("Jesse's own records of its live/paper sessions (closed trades and orders written by the live "
          "plugin). Not the exchange account's history: activity outside Jesse sessions is not included.")
TRADES_NOTE = ('Closed trades only, selected by closed_at. Open trades are not included (see '
               'open_trades_not_included). pnl is the price difference times qty minus the fees Jesse recorded on '
               "the trade's executed orders; orders_without_fee counts executed orders with no recorded fee.")
ORDERS_NOTE = ('Orders with their stored status. Selected by {field}; executed_at and canceled_at are null '
               'when the order was not executed or cancelled.')
PAGING_NOTE = ('Each page is read from one consistent database view. next_page repeats every argument of this '
               'selection and continues after the last record, so records added or removed before it never shift '
               'later pages; records changed between calls (such as a trade the plugin reconciles later) can still '
               'appear or disappear. For one coherent dataset, use run_analysis with a dataset input.')

# RFC 3339 date-time with an explicit offset. Jesse stores milliseconds, so at most three
# fractional digits are accepted; finer values could not be bounded exactly.
_DATETIME = re.compile(
    r'(\d{4})-(\d{2})-(\d{2})[Tt](\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,3}))?(?:([Zz])|([+-])(\d{2}):(\d{2}))'
)
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_CURSOR = re.compile(r'[A-Za-z0-9_-]+')


def _error(error_type: str, message: str, status_code: int = 400) -> ProjectFileError:
    return ProjectFileError(error_type, message, status_code)


def _now_ms() -> int:
    """Current UTC time in milliseconds (module-level so tests can freeze it)."""
    return time.time_ns() // 1_000_000


def _iso(ms: int) -> str:
    return (_EPOCH + timedelta(milliseconds=ms)).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _parse_datetime(value: Any, label: str) -> int:
    """An RFC 3339 date-time with an offset as UTC milliseconds. Messages never repeat the value."""
    example = 'e.g. "2026-09-21T00:00:00Z" or "2026-09-21T03:00:00+03:00"'
    match = _DATETIME.fullmatch(value.strip()) if isinstance(value, str) else None
    if match is None:
        raise _error('invalid_request', f'{label} must be an RFC 3339 date-time with a UTC offset ({example}); '
                                        'dates without a time or offset are ambiguous.')
    year, month, day, hour, minute, second, fraction, zulu, sign, off_hours, off_minutes = match.groups()
    try:
        offset = timedelta(0) if zulu else timedelta(hours=int(off_hours), minutes=int(off_minutes))
        if offset >= timedelta(hours=24) or int(off_minutes or 0) >= 60:
            raise ValueError
        moment = datetime(int(year), int(month), int(day), int(hour), int(minute), int(second),
                          int((fraction or '0').ljust(3, '0')) * 1000,
                          tzinfo=timezone(-offset if sign == '-' else offset))
        # The offset can move a value at the edge of the calendar (0001-01-01T00:00:00+01:00,
        # 9999-12-31T23:59:59-01:00) outside what UTC datetimes represent; the window's bounds are
        # reported as UTC date-times, so such values are refused here rather than failing later.
        moment = moment.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        raise _error('invalid_request', f'{label} is not a valid date-time between 0001-01-01T00:00:00Z and '
                                        f'9999-12-31T23:59:59.999Z ({example}).')
    return (moment - _EPOCH) // timedelta(milliseconds=1)


def _given(value: Any) -> bool:
    return value is not None and value != ''


def resolve_range(start: Any = None, end: Any = None, recent_days: Any = None) -> dict:
    """
    The effective [start, end) window. `recent_days` and the default window are anchored to the
    current time once, here; the returned bounds are what every later page must reuse.
    """
    if _given(recent_days) and (_given(start) or _given(end)):
        raise _error('invalid_request', 'Use either recent_days or start/end, not both.')
    if _given(end) and not _given(start):
        raise _error('invalid_request', 'end needs a start. Give both, only start (up to now), or recent_days.')
    now = _now_ms()
    if _given(start):
        start_ms = _parse_datetime(start, 'start')
        end_ms = _parse_datetime(end, 'end') if _given(end) else now
        source = 'start_end' if _given(end) else 'start_until_now'
        days = None
    else:
        days = DEFAULT_RECENT_DAYS if not _given(recent_days) else recent_days
        if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= MAX_RECENT_DAYS:
            raise _error('invalid_request', f'recent_days must be a whole number from 1 to {MAX_RECENT_DAYS}.')
        start_ms, end_ms = now - days * DAY_MS, now
        source = 'recent_days' if _given(recent_days) else 'default_recent_days'
    if end_ms <= start_ms:
        raise _error('invalid_request', 'end must be later than start.')
    return {
        'start': _iso(start_ms), 'end': _iso(end_ms), 'start_ms': start_ms, 'end_ms': end_ms,
        'bounds': 'start inclusive, end exclusive (UTC)', 'source': source, 'recent_days': days,
    }


def _text_filter(value: Any, label: str) -> Optional[str]:
    if not _given(value):
        return None
    if not isinstance(value, str) or len(value) > MAX_FILTER_CHARS or '\x00' in value:
        raise _error('invalid_request', f'{label} must be text of at most {MAX_FILTER_CHARS} characters, '
                                        'exactly as stored (see the exchange/symbol fields of any record).')
    return value


def _session_filter(value: Any) -> Optional[str]:
    if not _given(value):
        return None
    if isinstance(value, str):
        try:
            return str(UUID(value))
        except ValueError:
            pass
    raise _error('invalid_request', 'session_id must be a live session UUID (from get_live_sessions).')


def parse_query(dataset: str, params: Dict[str, Any]) -> dict:
    """Validate and normalize a history selection; resolves its window against the current time."""
    if not isinstance(dataset, str) or dataset not in DATASETS:
        raise _error('invalid_request', f'dataset must be one of: {", ".join(DATASETS)}.')
    mode = params.get('mode')
    mode = DEFAULT_MODE if not _given(mode) else mode
    if not isinstance(mode, str) or mode not in MODES:
        raise _error('invalid_request', 'mode must be "live" (default, real-money sessions only), "paper", or "all".')
    query = {
        'dataset': dataset,
        'range': resolve_range(params.get('start'), params.get('end'), params.get('recent_days')),
        'mode': mode,
        'exchange': _text_filter(params.get('exchange'), 'exchange'),
        'symbol': _text_filter(params.get('symbol'), 'symbol'),
        'session_id': _session_filter(params.get('session_id')),
    }
    if dataset == 'live_orders':
        time_field = params.get('time_field')
        time_field = 'created_at' if not _given(time_field) else time_field
        if not isinstance(time_field, str) or time_field not in ORDER_TIME_FIELDS:
            raise _error('invalid_request', 'time_field must be "created_at" (default) or "executed_at".')
        status = params.get('status')
        if _given(status):
            canonical = {s.lower(): s for s in ORDER_STATUSES}
            status = canonical.get(status.strip().lower().replace('_', ' ')) if isinstance(status, str) else None
            if status is None:
                raise _error('invalid_request', f'status must be one of: {", ".join(ORDER_STATUSES)}.')
        query.update(time_field=time_field, status=status or None)
    _check_session_mode(query)
    return query


def refuse_unknown_fields(dataset: str, extra: Optional[Dict[str, Any]]) -> None:
    """
    Refuse request fields the history routes do not know. A misspelled filter ("symbl") or one
    of the other dataset ("time_field" for trades) would otherwise be dropped, silently widening
    or changing the selection. The message lists the accepted names, never the given ones.
    """
    if extra:
        accepted = ', '.join(PARAMS[dataset] + PAGE_PARAMS)
        raise _error('invalid_request', f'Unknown field(s) in the request; {dataset} accepts only: {accepted}.')


def _check_session_mode(query: dict) -> None:
    """A session filter whose session has the other mode would silently match nothing; refuse it."""
    if not query['session_id']:
        return
    from jesse.models.LiveSession import LiveSession
    row = LiveSession.select(LiveSession.session_mode).where(LiveSession.id == query['session_id']).first()
    if row is not None and row.session_mode not in MODES[query['mode']]:
        kind = 'a paper' if row.session_mode == live_session_modes.PAPERTRADE else 'a live'
        raise _error('mode_mismatch', f'Live session {query["session_id"]} is {kind} session; its records are only '
                                      f'returned with mode "{"paper" if kind == "a paper" else "live"}" or "all".')


def _fingerprint(query: dict, order: str) -> str:
    """Identifies the exact selection and ordering a cursor continues (the page size may change)."""
    material = {
        'v': CURSOR_VERSION, 'order': order, 'dataset': query['dataset'], 'start_ms': query['range']['start_ms'],
        'end_ms': query['range']['end_ms'], 'mode': query['mode'], 'exchange': query['exchange'],
        'symbol': query['symbol'], 'session_id': query['session_id'], 'time_field': query.get('time_field'),
        'status': query.get('status'),
    }
    return hashlib.sha256(json.dumps(material, sort_keys=True).encode('utf-8')).hexdigest()[:32]


def _encode_cursor(query: dict, order: str, time_value: int, record_id: str) -> str:
    """
    An opaque continuation token: the last record's (time, id) key and the selection's fingerprint.
    It is not signed: it grants nothing the arguments do not, since the fingerprint is recomputed
    from the arguments of the call that uses it.
    """
    payload = json.dumps({'v': CURSOR_VERSION, 't': time_value, 'id': record_id, 'q': _fingerprint(query, order)},
                         separators=(',', ':'))
    return base64.urlsafe_b64encode(payload.encode('utf-8')).decode('ascii').rstrip('=')


def _decode_cursor(value: Any, query: dict, order: str) -> Tuple[int, UUID]:
    """The (time, id) key a page continues after. Messages never repeat the value."""
    malformed = _error('invalid_cursor', 'cursor must be next_page.cursor from the previous page, unchanged.')
    if not isinstance(value, str) or len(value) > MAX_CURSOR_CHARS or not _CURSOR.fullmatch(value):
        raise malformed
    try:
        data = json.loads(base64.urlsafe_b64decode(value + '=' * (-len(value) % 4)).decode('utf-8'))
        if not isinstance(data, dict) or set(data) != {'v', 't', 'id', 'q'} or type(data['v']) is not int:
            raise ValueError
        time_value = data['t']
        if data['v'] != CURSOR_VERSION or type(time_value) is not int or not isinstance(data['id'], str):
            raise ValueError
        record_id = UUID(data['id'])
    except (ValueError, TypeError, binascii.Error, UnicodeDecodeError):
        raise malformed
    window = query['range']
    if data['q'] != _fingerprint(query, order) or not window['start_ms'] <= time_value < window['end_ms']:
        # Replaying a cursor with a filter dropped or changed would silently read a different
        # (possibly wider) selection from the middle.
        raise _error('invalid_cursor', 'cursor belongs to a different selection. Pass exactly the arguments in '
                                       'next_page (window, mode, filters, order) together with its cursor.')
    return time_value, record_id


def _paging(query: dict, order: Any, cursor: Any, limit: Any) -> Tuple[str, int, Optional[Tuple[int, UUID]]]:
    if not isinstance(order, str) or order not in ORDERINGS:
        raise _error('invalid_request', 'order must be "newest_first" (default) or "oldest_first".')
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise _error('invalid_request', f'limit must be a whole number from 1 to {MAX_LIMIT}.')
    if not _given(cursor):
        return order, limit, None
    if query['range']['source'] != 'start_end':
        # A relative window moves with the clock, so a later page would come from a different selection.
        raise _error('invalid_request', 'cursor needs the explicit start and end from next_page, so every page reads '
                                        'the same window.')
    return order, limit, _decode_cursor(cursor, query, order)


def _keyset(column, model, key: Tuple[int, UUID], order: str):
    """Rows after `key` in the page order: stable under equal timestamps, cheap at any depth."""
    time_value, record_id = key
    if order == 'oldest_first':
        return (column > time_value) | ((column == time_value) & (model.id > record_id))
    return (column < time_value) | ((column == time_value) & (model.id < record_id))


def _ordering(column, model, order: str) -> tuple:
    return (column, model.id) if order == 'oldest_first' else (column.desc(), model.id.desc())


def public_query(query: dict) -> dict:
    """The effective range and filters, as reported in responses and snapshot manifests."""
    filters = {
        'mode': query['mode'],
        'session_modes': list(MODES[query['mode']]),
        'exchange': query['exchange'],
        'symbol': query['symbol'],
        'session_id': query['session_id'],
    }
    if query['dataset'] == 'live_orders':
        filters.update(time_field=query['time_field'], status=query['status'])
    return {'range': query['range'], 'filters': filters}


# ---------------------------------------------------------------------------
# Database queries (every filter is part of the WHERE clause)
# ---------------------------------------------------------------------------

def _history_query(query: dict, *, open_trades: bool = False):
    """Translate a validated MCP selection into the repository's shared history query."""
    options = dict(exact_match=True, exchange_filter=query['exchange'], symbol_filter=query['symbol'],
                   session_id=query['session_id'], session_modes=MODES[query['mode']],
                   start_ms=None if open_trades else query['range']['start_ms'], end_ms=query['range']['end_ms'])
    if query['dataset'] == 'live_trades':
        return closed_trade_repository.history_query(
            **options, status_filter='open' if open_trades else 'closed',
            time_field='opened_at' if open_trades else 'closed_at', include_soft_deleted=False,
        )
    return order_repository.history_query(**options, time_field=query['time_field'], status_filter=query['status'])


def _open_trades_count(query: dict) -> int:
    """Open trades in the same scope that were opened before the window's end (never included)."""
    return _history_query(query, open_trades=True).count()


def _order_time_column(query: dict):
    from jesse.models.Order import Order
    return getattr(Order, query['time_field'])


def _order_columns() -> list:
    """Every Order column except `vars` (exchange-specific driver state that no response includes)."""
    from jesse.models.Order import Order
    return [field for name, field in Order._meta.fields.items() if name != 'vars']


def _status_counts(query: dict) -> Dict[str, int]:
    from peewee import fn
    from jesse.models.Order import Order
    rows = (_history_query(query).select(Order.status, fn.COUNT(Order.id).alias('count'))
            .group_by(Order.status).order_by(Order.status))
    return {row.status: row.count for row in rows}


def _executed_orders(trade_ids: List[Any]) -> Dict[str, list]:
    """Executed orders of the given trades in one query, grouped by trade, oldest execution first."""
    from jesse.models.Order import Order
    grouped: Dict[str, list] = {}
    if not trade_ids:
        return grouped
    rows = (order_repository.executed_for_trades_query(trade_ids)
            .select(Order.id, Order.trade_id, Order.side, Order.filled_qty, Order.price, Order.fee, Order.executed_at)
            .order_by(Order.executed_at, Order.id))
    for order in rows:
        grouped.setdefault(str(order.trade_id), []).append(order)
    return grouped


def _executed_counts(trade_ids: List[Any]) -> Dict[str, int]:
    from peewee import fn
    from jesse.models.Order import Order
    if not trade_ids:
        return {}
    rows = (order_repository.executed_for_trades_query(trade_ids)
            .select(Order.trade_id, fn.COUNT(Order.id).alias('count')).group_by(Order.trade_id))
    return {str(row.trade_id): row.count for row in rows}


def _hydration_chunks(trades: list) -> Iterator[list]:
    """
    Consecutive chunks of `trades` whose executed orders together stay within MAX_HYDRATED_ORDERS.
    A trade over MAX_ORDERS_PER_TRADE is refused (too_many_orders) rather than computed from part
    of its orders; the trades before it are yielded first, so a page still makes progress up to it.
    """
    counts = _executed_counts([trade.id for trade in trades])
    chunk: list = []
    used = 0
    for trade in trades:
        count = counts.get(str(trade.id), 0)
        if count > MAX_ORDERS_PER_TRADE:
            if chunk:
                yield chunk
            raise _error('too_many_orders', f'Trade {trade.id} has {count} executed orders; its values are only computed '
                                            f'from all of them, up to {MAX_ORDERS_PER_TRADE}. Nothing past it was read. '
                                            'Choose a window that ends before or starts after it.', 413)
        if chunk and used + count > MAX_HYDRATED_ORDERS:
            yield chunk
            chunk, used = [], 0
        chunk.append(trade)
        used += count
    if chunk:
        yield chunk


def _trade_record(trade, orders: list) -> dict:
    """
    A closed trade with the dashboard's values. The executed orders are attached the way
    closed_trade_repository.populate_order_arrays does, so entry/exit price, qty, fee, and pnl
    come from the same ClosedTrade properties.
    """
    closed_trade_repository.attach_executed_orders(trade, orders)
    # A trade without executed orders has no prices; numpy then yields NaN (returned as null).
    with np.errstate(all='ignore'):
        record = {
            'id': str(trade.id),
            'session_id': str(trade.session_id),
            'session_mode': trade.session_mode,
            'exchange': trade.exchange,
            'symbol': trade.symbol,
            'strategy_name': jh.get_class_name(trade.strategy_name),
            'timeframe': trade.timeframe,
            'type': trade.type,
            'leverage': trade.leverage,
            'opened_at': trade.opened_at,
            'closed_at': trade.closed_at,
            'holding_period_seconds': trade.holding_period,
            'qty': float(trade.qty),
            'entry_price': float(trade.entry_price),
            'exit_price': float(trade.exit_price),
            'size': float(trade.size),
            'fee': float(trade.fee),
            'pnl': float(trade.pnl),
            'pnl_percentage': float(trade.pnl_percentage),
            'executed_orders': len(orders),
            'orders_without_fee': sum(1 for order in orders if order.fee is None),
        }
    return session_results._clean(record)


def _trade_records(trades: list) -> List[dict]:
    orders = _executed_orders([trade.id for trade in trades])
    return [_trade_record(trade, orders.get(str(trade.id), [])) for trade in trades]


def _order_record(order) -> dict:
    from jesse.services.transformers import get_order_details
    return {**get_order_details(order), 'session_id': str(order.session_id), 'session_mode': order.session_mode,
            'jesse_submitted': order.jesse_submitted}


# ---------------------------------------------------------------------------
# Sessions and redaction
# ---------------------------------------------------------------------------

class _Sessions:
    """
    Per-session metadata and redaction values for the records being returned, loaded once per
    session (see session_results._state_secrets). Values of every saved key are loaded only for a
    record whose session no longer exists or has no readable form. The rows come from the page's
    database view; `is_active` (and the reconciled `status`) come from the Redis worker set, read
    at that moment outside the database view, best effort, for display only.
    """

    def __init__(self):
        self.info: Dict[str, Optional[dict]] = {}
        self._secrets: Dict[str, List[str]] = {}
        self._all_secrets: Optional[List[str]] = None

    def load(self, session_ids) -> None:
        from jesse.models.LiveSession import LiveSession
        missing = sorted({sid for sid in session_ids if sid not in self.info})
        if not missing:
            return
        active = _active_workers()
        rows = LiveSession.select(
            LiveSession.id, LiveSession.title, LiveSession.status, LiveSession.session_mode, LiveSession.exchange,
            LiveSession.state, LiveSession.created_at, LiveSession.finished_at,
        ).where(LiveSession.id.in_(missing))
        for row in rows:
            sid = str(row.id)
            secrets = session_results._stored_state_secrets(row.state, sid)
            status = (row.status or '').lower()
            is_active = sid in active
            if status in (live_session_statuses.STARTING, live_session_statuses.RUNNING) and not is_active:
                # The dashboard's reconciliation, reported without writing it back.
                status = live_session_statuses.STOPPED
            info = session_results._redact({
                'title': row.title, 'session_mode': row.session_mode, 'exchange': row.exchange, 'status': status,
                'is_active': is_active, 'created_at': row.created_at, 'finished_at': row.finished_at,
            }, secrets)
            # Cut only after redaction, so a saved value crossing the cut is never partly returned.
            if isinstance(info['title'], str):
                info['title'] = info['title'][:MAX_SESSION_TITLE_CHARS]
            self._secrets[sid] = secrets
            self.info[sid] = info
        for sid in missing:
            self.info.setdefault(sid, None)

    def secrets(self, session_id: str) -> List[str]:
        if self.info.get(session_id) is not None:
            return self._secrets[session_id]
        if self._all_secrets is None:
            self._all_secrets = session_results._all_saved_secrets()
        return self._all_secrets

    def redact(self, records: List[dict]) -> List[dict]:
        self.load(record['session_id'] for record in records)
        return [session_results._redact(record, self.secrets(record['session_id'])) for record in records]

    def public(self, session_ids) -> Dict[str, dict]:
        """Session metadata keyed by ID; a deleted session reads {"exists": false}."""
        return {sid: ({'exists': True, **self.info[sid]} if self.info.get(sid) is not None else {'exists': False})
                for sid in sorted(set(session_ids))}


def _active_workers() -> set:
    """
    Session IDs with a running worker, from Redis, as in the dashboard's live session view. Not
    part of the database snapshot; an unreachable Redis reads as "none active" (display only).
    """
    from jesse.services.multiprocessing import process_manager
    try:
        return set(process_manager.active_workers)
    except Exception:
        return set()


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

def _wire_bytes(value: Any) -> int:
    """
    Bytes of `value` as an MCP client receives it: the text FastMCP renders for a dict tool result
    (the same pydantic_core call with indent=2), escaped as a JSON string in the JSON-RPC message.
    The HTTP route's compact JSON is always smaller.
    """
    text = pydantic_core.to_json(value, fallback=str, indent=2).decode('utf-8')
    return len(json.dumps(text, ensure_ascii=False).encode('utf-8'))


def _page_response(query: dict, order: str, limit: int, continued: bool, records: List[dict], total: int,
                   more: bool, orders_cut: bool, sessions: _Sessions, extra: dict) -> dict:
    """
    The page holding as many of `records` as fit MAX_RESPONSE_BYTES (minus TRANSPORT_ALLOWANCE)
    together with their session details and the envelope. At least one record is returned, or the
    page is refused as item_too_large, so paging always makes progress.
    """
    records = sessions.redact(records)
    window = query['range']
    time_key = 'closed_at' if query['dataset'] == 'live_trades' else query['time_field']
    replay = {'start': window['start'], 'end': window['end'], 'mode': query['mode'], 'exchange': query['exchange'],
              'symbol': query['symbol'], 'session_id': query['session_id']}
    if query['dataset'] == 'live_orders':
        replay.update(time_field=query['time_field'], status=query['status'])

    def build(count: int) -> dict:
        items = records[:count]
        has_more = more or count < len(records)
        next_page = None
        if has_more and items:
            cursor = _encode_cursor(query, order, items[-1][time_key], items[-1]['id'])
            next_page = {**replay, 'order': order, 'limit': limit, 'cursor': cursor}
        return {
            'dataset': query['dataset'],
            'source': SOURCE,
            **public_query(query),
            'order': f'{order.replace("_", " ")} by {time_key}, then id',
            'items': items,
            'limit': limit,
            'returned': count,
            'total': total,
            'has_more': has_more,
            'truncated_by_size': count < len(records),
            'truncated_by_orders': orders_cut,
            'all_records_returned': not continued and not has_more,
            'next_page': next_page,
            'sessions': sessions.public(item['session_id'] for item in items),
            **extra,
            'paging': PAGING_NOTE,
        }

    budget = MAX_RESPONSE_BYTES - TRANSPORT_ALLOWANCE
    page = build(len(records))
    if _wire_bytes(page) <= budget:
        return page
    # The size grows with every record and its session details: find the largest page that fits.
    fits, too_big = 0, len(records)
    while too_big - fits > 1:
        middle = (fits + too_big) // 2
        if _wire_bytes(build(middle)) <= budget:
            fits = middle
        else:
            too_big = middle
    if fits == 0:
        raise _error('item_too_large', f'Record {records[0]["id"]} with its session details is larger than the '
                                       f'{MAX_RESPONSE_BYTES // 1024} KiB page limit. Analyze it with run_analysis '
                                       'and a dataset input.', 413)
    return build(fits)


def list_trades(start: Any = None, end: Any = None, recent_days: Any = None, mode: Any = DEFAULT_MODE,
                exchange: Any = None, symbol: Any = None, session_id: Any = None, order: Any = 'newest_first',
                cursor: Any = None, limit: Any = DEFAULT_LIMIT) -> dict:
    """One page of closed trades across live/paper sessions, closed within the window."""
    from jesse.models.ClosedTrade import ClosedTrade
    session_results._require_live_plugin()
    query = parse_query('live_trades', {'start': start, 'end': end, 'recent_days': recent_days, 'mode': mode,
                                        'exchange': exchange, 'symbol': symbol, 'session_id': session_id})
    order, limit, after = _paging(query, order, cursor, limit)
    with session_results._read_snapshot():
        selection = _history_query(query)
        total = selection.count()
        if after is not None:
            selection = selection.where(_keyset(ClosedTrade.closed_at, ClosedTrade, after, order))
        fetched = list(selection.order_by(*_ordering(ClosedTrade.closed_at, ClosedTrade, order)).limit(limit + 1))
        rows = fetched[:limit]
        chunks = _hydration_chunks(rows)
        try:
            # Only the first chunk: a page stops early rather than loading more orders at once.
            chunk = next(chunks, [])
        finally:
            chunks.close()
        return _page_response(query, order, limit, after is not None, _trade_records(chunk), total,
                              len(fetched) > len(chunk), len(chunk) < len(rows), _Sessions(), {
                                  'open_trades_not_included': _open_trades_count(query),
                                  'note': TRADES_NOTE,
                              })


def list_orders(start: Any = None, end: Any = None, recent_days: Any = None, mode: Any = DEFAULT_MODE,
                exchange: Any = None, symbol: Any = None, session_id: Any = None, time_field: Any = 'created_at',
                status: Any = None, order: Any = 'newest_first', cursor: Any = None, limit: Any = DEFAULT_LIMIT) -> dict:
    """One page of orders across live/paper sessions whose `time_field` falls in the window."""
    from jesse.models.Order import Order
    session_results._require_live_plugin()
    query = parse_query('live_orders', {'start': start, 'end': end, 'recent_days': recent_days, 'mode': mode,
                                        'exchange': exchange, 'symbol': symbol, 'session_id': session_id,
                                        'time_field': time_field, 'status': status})
    order, limit, after = _paging(query, order, cursor, limit)
    column = _order_time_column(query)
    with session_results._read_snapshot():
        selection = _history_query(query)
        total = selection.count()
        selection = selection.select(*_order_columns())
        if after is not None:
            selection = selection.where(_keyset(column, Order, after, order))
        fetched = list(selection.order_by(*_ordering(column, Order, order)).limit(limit + 1))
        return _page_response(query, order, limit, after is not None, [_order_record(row) for row in fetched[:limit]],
                              total, len(fetched) > limit, False, _Sessions(), {
                                  'counts_by_status': _status_counts(query),
                                  'note': ORDERS_NOTE.format(field=query['time_field']),
                              })


# ---------------------------------------------------------------------------
# Analysis snapshots
# ---------------------------------------------------------------------------

def validate_dataset_input(item: Dict[str, Any]) -> dict:
    """
    Validate a run_analysis input selecting live history ({"dataset": ..., filters}) and resolve
    its window now, before any workspace is created. Unknown fields are refused, because a
    misspelled filter would silently widen the selection.
    """
    session_results._require_live_plugin()
    dataset = item.get('dataset')
    if not isinstance(dataset, str) or dataset not in DATASETS:
        raise _error('invalid_request', f'dataset must be one of: {", ".join(DATASETS)}.')
    given = {key for key, value in item.items() if value is not None} - {'dataset', 'name'}
    if 'session_type' in given:
        raise _error('invalid_request', 'An input selects either a session (session_type + session_id) or a dataset, not both.')
    if given - set(PARAMS[dataset]):
        raise _error('invalid_request', f'A {dataset} input accepts only: dataset, name, {", ".join(PARAMS[dataset])}.')
    return parse_query(dataset, {key: item.get(key) for key in PARAMS[dataset]})


def iter_dataset_json(query: dict, stats: dict) -> Iterator[str]:
    """
    Stream the complete selection as JSON text, oldest first, one batch of rows at a time, all
    read inside one consistent read-only transaction (session_results._read_snapshot), so the header's counts,
    the rows, their orders, and the sessions agree. Separate inputs are separate views.

    Refuses instead of truncating: too_many_records when the selection exceeds the analysis cap
    (checked up front and again while streaming), too_many_orders for a trade whose values would
    need more than MAX_ORDERS_PER_TRADE executed orders. The caller must close the generator
    when it stops early (analysis_jobs does), which ends the transaction at once. `stats`
    receives the final count.
    """
    from jesse.models.ClosedTrade import ClosedTrade
    from jesse.models.Order import Order
    session_results._require_live_plugin()
    trades = query['dataset'] == 'live_trades'
    cap = MAX_ANALYSIS_TRADES if trades else MAX_ANALYSIS_ORDERS
    model = ClosedTrade if trades else Order
    column = ClosedTrade.closed_at if trades else _order_time_column(query)
    columns = [] if trades else _order_columns()

    def refuse(count: int) -> ProjectFileError:
        noun = 'trades' if trades else 'orders'
        return _error('too_many_records', f'The selection holds {count} {noun}; an analysis input is limited to {cap}. '
                                          'Narrow the window or add exchange/symbol/session filters (several inputs '
                                          'can split a long period).', 413)

    with session_results._read_snapshot():
        base_selection = _history_query(query)
        total = base_selection.count()
        if total > cap:
            raise refuse(total)
        header = {
            'dataset': query['dataset'],
            'source': SOURCE,
            **public_query(query),
            'order': f'oldest first by {"closed_at" if trades else query["time_field"]}, then id',
            'note': TRADES_NOTE if trades else ORDERS_NOTE.format(field=query['time_field']),
        }
        if trades:
            header['open_trades_not_included'] = _open_trades_count(query)
        else:
            header['counts_by_status'] = _status_counts(query)
        records_key = 'trades' if trades else 'orders'
        yield json.dumps(header, default=str, separators=(',', ':'))[:-1] + f',"{records_key}":['

        sessions = _Sessions()
        session_ids = set()
        count = 0
        last: Optional[Tuple[Any, Any]] = None
        while True:
            selection = base_selection.select(*columns) if columns else base_selection
            if last is not None:
                selection = selection.where(_keyset(column, model, last, 'oldest_first'))
            rows = list(selection.order_by(column, model.id).limit(BATCH_SIZE))
            if not rows:
                break
            # Inside one transaction the count cannot change; this guards a write made through
            # the same connection while streaming.
            if count + len(rows) > cap:
                raise refuse(count + len(rows))
            last = (getattr(rows[-1], column.name), rows[-1].id)
            for part in (_hydration_chunks(rows) if trades else [rows]):
                records = sessions.redact(_trade_records(part) if trades else [_order_record(row) for row in part])
                session_ids.update(record['session_id'] for record in records)
                yield (',' if count else '') + ','.join(json.dumps(r, default=str, separators=(',', ':')) for r in records)
                count += len(records)
        stats['count'] = count
        yield ('],"sessions":' + json.dumps(sessions.public(session_ids), default=str, separators=(',', ':'))
               + f',"count":{count},"complete":true}}')
