import peewee
from jesse.services.db import database
import jesse.helpers as jh
import numpy as np


if database.is_closed():
    database.open_connection()


class FundingRate(peewee.Model):
    id = peewee.UUIDField(primary_key=True)
    timestamp = peewee.BigIntegerField()
    funding_rate = peewee.FloatField()
    exchange = peewee.CharField()
    symbol = peewee.CharField()
    

    # partial candles: 5 * 1m candle = 5m candle while 1m == partial candle
    is_partial = True

    class Meta:
        from jesse.services.db import database

        database = database.db
        indexes = (
            (('exchange', 'symbol', 'timestamp'), True),
        )

    def __init__(self, attributes: dict = None, **kwargs) -> None:
        peewee.Model.__init__(self, attributes=attributes, **kwargs)

        if attributes is None:
            attributes = {}

        for a, value in attributes.items():
            setattr(self, a, value)


# if database is open, create the table
if database.is_open():
    FundingRate.create_table()
    
    

# # # # # # # # # # # # # # # # # # # # # # # # # # # 
# # # # # # # # # DB FUNCTIONS # # # # # # # # #
# # # # # # # # # # # # # # # # # # # # # # # # # # # 


def store_funding_rate_into_db(exchange: str, symbol: str, funding_rate: float, timestamp: int, on_conflict='ignore') -> None:
    d = {
        'id': jh.generate_unique_id(),
        'exchange': exchange,
        'symbol': symbol,
        'timestamp': timestamp,
        'funding_rate': funding_rate,
    }

    if on_conflict == 'ignore':
        FundingRate.insert(**d).on_conflict_ignore().execute()
    elif on_conflict == 'replace':
        FundingRate.insert(**d).on_conflict(
            conflict_target=['exchange', 'symbol', 'timestamp'],
            preserve=(FundingRate.funding_rate),
        ).execute()
    elif on_conflict == 'error':
        FundingRate.insert(**d).execute()
    else:
        raise Exception(f'Unknown on_conflict value: {on_conflict}')


def store_funding_rates_into_db(exchange: str, symbol: str, funding_rates_data: np.ndarray, on_conflict='ignore') -> None:
    # make sure the number of candles is more than 0
    if len(funding_rates_data) == 0:
        raise Exception(f'No funding rates to store for {exchange}-{symbol}')

    # convert candles to list of dicts
    funding_rates_list = []
    for data in funding_rates_data:
        d = {
            'id': jh.generate_unique_id(),
            'symbol': symbol,
            'exchange': exchange,
            'timestamp': data[0],
            'funding_rate': data[1],
        }
        funding_rates_list.append(d)

    if on_conflict == 'ignore':
        FundingRate.insert_many(funding_rates_list).on_conflict_ignore().execute()
    elif on_conflict == 'replace':
        FundingRate.insert_many(funding_rates_list).on_conflict(
            conflict_target=['exchange', 'symbol', 'timestamp'],
            preserve=(FundingRate.funding_rate),
        ).execute()
    elif on_conflict == 'error':
        FundingRate.insert_many(funding_rates_list).execute()
    else:
        raise Exception(f'Unknown on_conflict value: {on_conflict}')


def fetch_funding_rates_from_db(exchange: str, symbol: str, start_date: int, finish_date: int) -> tuple:
    res = tuple(
        FundingRate.select(
            FundingRate.timestamp, FundingRate.funding_rate
        ).where(
            FundingRate.exchange == exchange,
            FundingRate.symbol == symbol,
            FundingRate.timestamp.between(start_date, finish_date)
        ).order_by(FundingRate.timestamp.asc()).tuples()
    )

    return res

