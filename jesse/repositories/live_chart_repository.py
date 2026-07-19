from collections import defaultdict
from typing import Optional

import jesse.helpers as jh
from peewee import EXCLUDED

from jesse.models.LiveChart import LiveChartPoint, LiveChartSeries
from jesse.services.db import database


LINE = 'line'
HORIZONTAL = 'horizontal'


def _ensure_db_open() -> None:
    if not database.is_open():
        database.open_connection()


def store_points(points: list[dict]) -> None:
    if jh.is_unit_testing() or not points:
        return

    _ensure_db_open()
    grouped = defaultdict(list)
    for point in points:
        key = (
            point['session_id'],
            point['exchange'],
            point['symbol'],
            point['timeframe'],
            point.get('chart_name', ''),
            point['title'],
            point['line_type'],
        )
        grouped[key].append(point)

    with database.db.atomic():
        for key, series_points in grouped.items():
            session_id, exchange, symbol, timeframe, chart_name, title, line_type = key
            default_color = series_points[0].get('default_color')
            series, _ = LiveChartSeries.get_or_create(
                session=session_id,
                exchange=exchange,
                symbol=symbol,
                timeframe=timeframe,
                chart_name=chart_name,
                title=title,
                line_type=line_type,
                defaults={'default_color': default_color},
            )

            rows = [
                {
                    'series': series.id,
                    'timestamp': point['timestamp'],
                    'value': point['value'],
                    'color': point.get('color') if point.get('color') != series.default_color else None,
                    'line_width': point.get('line_width'),
                    'line_style': point.get('line_style'),
                }
                for point in series_points
            ]
            LiveChartPoint.insert_many(rows).on_conflict(
                conflict_target=[LiveChartPoint.series, LiveChartPoint.timestamp],
                update={
                    LiveChartPoint.value: EXCLUDED.value,
                    LiveChartPoint.color: EXCLUDED.color,
                    LiveChartPoint.line_width: EXCLUDED.line_width,
                    LiveChartPoint.line_style: EXCLUDED.line_style,
                },
            ).execute()


def _empty_charts() -> dict:
    return {
        'lines': {},
        'horizontal_lines': {},
        'extra_charts': {},
        'horizontal_extra_lines': {},
    }


def get_chart_data(
    session_id: str,
    exchange: str,
    symbol: str,
    timeframe: str,
    start_time: int,
    finish_time: int,
) -> Optional[dict]:
    if jh.is_unit_testing():
        return None

    _ensure_db_open()
    series_list = list(
        LiveChartSeries.select().where(
            (LiveChartSeries.session == session_id)
            & (LiveChartSeries.exchange == exchange)
            & (LiveChartSeries.symbol == symbol)
            & (LiveChartSeries.timeframe == timeframe)
        )
    )
    if not series_list:
        return None

    charts = _empty_charts()
    for series in series_list:
        if series.line_type == LINE:
            points = list(
                LiveChartPoint.select()
                .where(
                    (LiveChartPoint.series == series.id)
                    & (LiveChartPoint.timestamp >= start_time)
                    & (LiveChartPoint.timestamp <= finish_time)
                )
                .order_by(LiveChartPoint.timestamp)
            )
            if not points:
                continue
            line = {
                'color': series.default_color,
                'data': [
                    {
                        'time': point.timestamp // 1000,
                        'value': point.value,
                        'color': point.color or series.default_color,
                    }
                    for point in points
                ],
            }
            if series.chart_name:
                charts['extra_charts'].setdefault(series.chart_name, {})[series.title] = line
            else:
                charts['lines'][series.title] = line
            continue

        point = (
            LiveChartPoint.select()
            .where(
                (LiveChartPoint.series == series.id)
                & (LiveChartPoint.timestamp <= finish_time)
            )
            .order_by(LiveChartPoint.timestamp.desc())
            .first()
        )
        if point is None:
            continue
        horizontal = {
            'title': series.title,
            'price': point.value,
            'color': point.color or series.default_color,
            'lineWidth': point.line_width,
            'lineStyle': point.line_style,
        }
        if series.chart_name:
            charts['horizontal_extra_lines'].setdefault(series.chart_name, {})[series.title] = horizontal
        else:
            charts['horizontal_lines'][series.title] = horizontal

    if not any(charts.values()):
        return None
    return charts
