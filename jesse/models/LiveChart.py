import uuid

import peewee

from jesse.models.LiveSession import LiveSession
from jesse.services.db import database


if database.is_closed():
    database.open_connection()


class LiveChartSeries(peewee.Model):
    id = peewee.UUIDField(primary_key=True, default=uuid.uuid4)
    session = peewee.ForeignKeyField(
        LiveSession,
        backref='chart_series',
        column_name='session_id',
        on_delete='CASCADE',
    )
    exchange = peewee.CharField()
    symbol = peewee.CharField()
    timeframe = peewee.CharField()
    chart_name = peewee.CharField(default='')
    title = peewee.CharField()
    line_type = peewee.CharField()
    default_color = peewee.CharField(null=True)

    class Meta:
        from jesse.services.db import database

        database = database.db
        indexes = (
            (
                ('session', 'exchange', 'symbol', 'timeframe', 'chart_name', 'title', 'line_type'),
                True,
            ),
        )


class LiveChartPoint(peewee.Model):
    series = peewee.ForeignKeyField(
        LiveChartSeries,
        backref='points',
        column_name='series_id',
        on_delete='CASCADE',
    )
    timestamp = peewee.BigIntegerField()
    value = peewee.DoubleField()
    color = peewee.CharField(null=True)
    line_width = peewee.DoubleField(null=True)
    line_style = peewee.IntegerField(null=True)

    class Meta:
        from jesse.services.db import database

        database = database.db
        primary_key = peewee.CompositeKey('series', 'timestamp')


if database.is_open():
    database.db.create_tables([LiveChartSeries, LiveChartPoint], safe=True)
