import peewee
import jesse.helpers as jh
import numpy as np
import threading
from datetime import datetime
from jesse.services.db import database

class Trade(peewee.Model):
    id = peewee.UUIDField(primary_key=True)

    session_id = peewee.UUIDField(null=False)

    buy_at_price = peewee.FloatField(null=False)
    sell_at_price = peewee.FloatField(null=True)

    qty = peewee.FloatField(null=True)

    type = peewee.CharField(null=False)

    buy_by = peewee.CharField(choices=[('user', 'User'), ('jesse', 'Jesse')], default='user')
    sell_by = peewee.CharField(choices=[('user', 'User'), ('jesse', 'Jesse')], null=True)

    buy_at_datetime = peewee.DateTimeField(default=datetime.now)
    sell_at_datetime = peewee.DateTimeField(null=True)

    symbol = peewee.CharField(null=False)
    exchange = peewee.CharField(null=False)

    created_at = peewee.DateTimeField(default=datetime.now)
    updated_at = peewee.DateTimeField(default=datetime.now)

    class Meta:
        database = database.db
        indexes = ((('exchange', 'symbol', 'buy_at_datetime'), False),)

    def __init__(self, attributes: dict = None, **kwargs) -> None:
        peewee.Model.__init__(self, attributes=attributes, **kwargs)

        if attributes is None:
            attributes = {}

        for a, value in attributes.items():
            setattr(self, a, value)

    @staticmethod
    def store_trade_into_db(trade: np.array) -> None:
        d = {
            'id': jh.generate_unique_id(),
            'session_id': trade['session_id'],
            'buy_at_price': trade['buy_at_price'],
            'qty': trade['qty'],
            'type': trade['type'],
            'buy_by': trade['buy_by'],
            'buy_at_datetime': datetime.now(),
            'symbol': trade['symbol'],
            'exchange': trade['exchange'],
            'created_at': datetime.now(),
            'updated_at': datetime.now(),
        }

        Trade.insert(**d).execute()

    @staticmethod
    def get_trade_from_db(session_id: str, exchange: str, symbol: str, qty: float, type: str) -> any:
        return Trade.select().where(
            Trade.session_id == session_id,
            Trade.exchange == exchange,
            Trade.symbol == symbol,
            Trade.qty == qty,
            Trade.sell_at_datetime is None,
            Trade.sell_at_price is None,
            Trade.type == type).first()

    @staticmethod
    def close_trade_in_db(id: str, trade: np.array) -> None:
        d = {
            'sell_at_datetime': datetime.now(),
            'sell_at_price': trade['sell_at_price'],
            'sell_by': trade['sell_by'],
        }
        Trade.update(**d).where(Trade.id == id).execute()

# # # # # # # # # # # # # # # # # # # # # # # # # # #
# # # # # # # # # DB FUNCTIONS # # # # # # # # #
# # # # # # # # # # # # # # # # # # # # # # # # # # #
