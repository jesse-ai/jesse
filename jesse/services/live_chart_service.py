from copy import deepcopy
from typing import Optional

import jesse.helpers as jh
from jesse.enums import order_statuses
from jesse.repositories import (
    candle_repository,
    closed_trade_repository,
    live_chart_repository,
    order_repository,
)
from jesse.services import transformers
from jesse.services.redis import get_live_charts_snapshot


MIN_CANDLE_COUNT = 100
MAX_CANDLE_COUNT = 5_000
CONTEXT_CANDLES = 50


def _session_routes(session) -> list[dict]:
    state = session.state_json if session.state else {}
    form = state.get('form', {}) if isinstance(state, dict) else {}
    routes = form.get('routes', []) if isinstance(form, dict) else []
    return routes if isinstance(routes, list) else []


def _validate_route(session, exchange: str, symbol: str, timeframe: str) -> None:
    if exchange != session.exchange:
        raise ValueError('The requested exchange does not belong to this live session.')

    belongs_to_session = any(
        route.get('symbol') == symbol and route.get('timeframe') == timeframe
        for route in _session_routes(session)
        if isinstance(route, dict)
    )
    if not belongs_to_session:
        raise ValueError('The requested route does not belong to this live session.')


def _candle_window(
    session,
    timeframe: str,
    anchor_time: Optional[int],
    candle_count: int,
) -> tuple[int, int, int, int, int]:
    count = max(MIN_CANDLE_COUNT, min(int(candle_count), MAX_CANDLE_COUNT))
    timeframe_ms = jh.timeframe_to_one_minutes(timeframe) * 60_000
    session_start = int(session.created_at)
    session_end = int(session.finished_at or jh.now(force_fresh=True))
    lower_bound = session_start - (CONTEXT_CANDLES * timeframe_ms)
    span = max(0, count - 1) * timeframe_ms

    if anchor_time is None:
        finish = session_end
        start = max(lower_bound, finish - span)
    else:
        anchor = max(lower_bound, min(int(anchor_time), session_end))
        start = anchor - ((count // 2) * timeframe_ms)
        finish = start + span
        if start < lower_bound:
            start = lower_bound
            finish = min(session_end, start + span)
        elif finish > session_end:
            finish = session_end
            start = max(lower_bound, finish - span)

    return start, finish, count, lower_bound, session_end


def _strategy_charts_for_window(
    session_id: str,
    exchange: str,
    symbol: str,
    timeframe: str,
    route_key: str,
    start: int,
    finish: int,
    include_current_horizontals: bool,
) -> Optional[dict]:
    stored_charts = live_chart_repository.get_chart_data(
        session_id,
        exchange,
        symbol,
        timeframe,
        start,
        finish,
    )
    snapshot_charts = get_live_charts_snapshot(session_id).get(route_key)
    if stored_charts is None and snapshot_charts is None:
        return None

    strategy_charts = deepcopy(snapshot_charts) if snapshot_charts is not None else {
        'lines': {},
        'horizontal_lines': {},
        'extra_charts': {},
        'horizontal_extra_lines': {},
    }
    start_seconds = start // 1000
    finish_seconds = finish // 1000

    for line_name in list(strategy_charts.get('lines', {})):
        line = strategy_charts['lines'][line_name]
        line['data'] = [
            point
            for point in line.get('data', [])
            if start_seconds <= point['time'] <= finish_seconds
        ]
        if not line['data']:
            del strategy_charts['lines'][line_name]

    for chart_name in list(strategy_charts.get('extra_charts', {})):
        chart = strategy_charts['extra_charts'][chart_name]
        for line_name in list(chart):
            chart[line_name]['data'] = [
                point
                for point in chart[line_name].get('data', [])
                if start_seconds <= point['time'] <= finish_seconds
            ]
            if not chart[line_name]['data']:
                del chart[line_name]
        if not chart:
            del strategy_charts['extra_charts'][chart_name]

    if stored_charts is None:
        return strategy_charts

    result = deepcopy(stored_charts)
    for line_name, line in strategy_charts.get('lines', {}).items():
        stored_line = result['lines'].setdefault(line_name, deepcopy(line))
        points = {point['time']: point for point in stored_line['data']}
        points.update({point['time']: point for point in line['data']})
        stored_line['data'] = [points[time] for time in sorted(points)]
        stored_line['color'] = line.get('color', stored_line.get('color'))

    for chart_name, chart in strategy_charts.get('extra_charts', {}).items():
        stored_chart = result['extra_charts'].setdefault(chart_name, {})
        for line_name, line in chart.items():
            stored_line = stored_chart.setdefault(line_name, deepcopy(line))
            points = {point['time']: point for point in stored_line['data']}
            points.update({point['time']: point for point in line['data']})
            stored_line['data'] = [points[time] for time in sorted(points)]
            stored_line['color'] = line.get('color', stored_line.get('color'))

    if include_current_horizontals:
        result['horizontal_lines'].update(strategy_charts.get('horizontal_lines', {}))
        for chart_name, lines in strategy_charts.get('horizontal_extra_lines', {}).items():
            result['horizontal_extra_lines'].setdefault(chart_name, {}).update(lines)

    return result


def get_live_session_chart_data(
    session,
    exchange: str,
    symbol: str,
    timeframe: str,
    anchor_time: Optional[int] = None,
    candle_count: int = 1000,
) -> dict:
    _validate_route(session, exchange, symbol, timeframe)
    start, finish, count, lower_bound, session_end = _candle_window(
        session, timeframe, anchor_time, candle_count
    )

    raw_candles = candle_repository.fetch_candles_from_db(
        exchange,
        symbol,
        timeframe,
        start,
        finish,
    )
    candles = [
        {
            'time': int(candle[0] / 1000),
            'open': candle[1],
            'close': candle[2],
            'high': candle[3],
            'low': candle[4],
            'volume': candle[5],
        }
        for candle in raw_candles
    ]

    orders = [
        transformers.get_order_details(order)
        for order in order_repository.get_session_orders(str(session.id), exchange, symbol)
        if order.status == order_statuses.EXECUTED and order.executed_at is not None
    ]

    trades = [
        transformers.get_closed_trade_details(trade)
        for trade in closed_trade_repository.find_by_session_id(str(session.id))
        if trade.exchange == exchange and trade.symbol == symbol and trade.closed_at is not None
    ]

    route_key = jh.key(exchange, symbol, timeframe)
    strategy_charts = _strategy_charts_for_window(
        str(session.id),
        exchange,
        symbol,
        timeframe,
        route_key,
        start,
        finish,
        finish >= session_end,
    )

    return {
        'route': {
            'exchange': exchange,
            'symbol': symbol,
            'timeframe': timeframe,
        },
        'candles': candles,
        'orders': orders,
        'trades': trades,
        'strategy_charts': strategy_charts,
        'window': {
            'from': start,
            'to': finish,
            'candle_count': count,
            'has_older': start > lower_bound,
            'has_newer': finish < session_end,
        },
    }
