import numpy as np
import peewee

import jesse.helpers as jh
from jesse.config import config
from jesse.services.db import db


class CompletedTrade(peewee.Model):
    """A trade is made when a position is opened AND closed."""

    id = peewee.UUIDField(primary_key=True)
    strategy_name = peewee.CharField()
    symbol = peewee.CharField()
    exchange = peewee.CharField()
    type = peewee.CharField()
    timeframe = peewee.CharField()
    entry_price = peewee.FloatField(default=np.nan)
    exit_price = peewee.FloatField(default=np.nan)
    take_profit_at = peewee.FloatField(default=np.nan)
    stop_loss_at = peewee.FloatField(default=np.nan)
    qty = peewee.FloatField(default=np.nan)
    opened_at = peewee.BigIntegerField()
    closed_at = peewee.BigIntegerField()
    entry_candle_timestamp = peewee.BigIntegerField()
    exit_candle_timestamp = peewee.BigIntegerField()
    leverage = peewee.IntegerField()

    orders = []

    class Meta:
        database = db
        indexes = ((('strategy_name', 'exchange', 'symbol'), False),)

    def __init__(self, attributes=None, **kwargs) -> None:
        peewee.Model.__init__(self, attributes=attributes, **kwargs)

        if attributes is None:
            attributes = {}

        for a in attributes:
            setattr(self, a, attributes[a])

    def toJSON(self) -> dict:
        orders = []
        for o in self.orders:
            orders.append(o.__dict__)
        return {
            "id": self.id,
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "exchange": self.exchange,
            "type": self.type,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "take_profit_at": self.take_profit_at,
            "stop_loss_at": self.stop_loss_at,
            "qty": self.qty,
            "fee": self.fee,
            "reward": self.reward,
            "size": self.size,
            "risk": self.risk,
            "risk_percentage": self.risk_percentage,
            "R": self.r,
            "PNL": self.pnl,
            "PNL_percentage": self.pnl_percentage,
            "holding_period": self.holding_period,
            "opened_at": self.opened_at,
            "closed_at": self.closed_at,
            "entry_candle_timestamp": self.entry_candle_timestamp,
            "exit_candle_timestamp": self.exit_candle_timestamp,
            "orders": orders,
        }

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'strategy_name': self.strategy_name,
            'symbol': self.symbol,
            'exchange': self.exchange,
            'type': self.type,
            'entry_price': self.entry_price,
            'exit_price': self.exit_price,
            'take_profit_at': self.take_profit_at,
            'stop_loss_at': self.stop_loss_at,
            'qty': self.qty,
            'opened_at': self.opened_at,
            'closed_at': self.closed_at,
            'entry_candle_timestamp': self.entry_candle_timestamp,
            'exit_candle_timestamp': self.exit_candle_timestamp,
            "fee": self.fee,
            "reward": self.reward,
            "size": self.size,
            "risk": self.risk,
            "risk_percentage": self.risk_percentage,
            "R": self.r,
            "PNL": self.pnl,
            "PNL_percentage": self.pnl_percentage,
            "holding_period": self.holding_period,
        }

    @property
    def fee(self) -> float:
        trading_fee = jh.get_config('env.exchanges.{}.fee'.format(self.exchange))
        return trading_fee * self.qty * (self.entry_price + self.exit_price)

    @property
    def reward(self) -> float:
        return abs(self.take_profit_at - self.entry_price) * self.qty

    @property
    def size(self) -> float:
        return self.qty * self.entry_price

    @property
    def risk(self) -> float:
        return abs(self.stop_loss_at - self.entry_price) * self.qty

    @property
    def risk_percentage(self) -> float:
        return round((self.risk / self.size) * 100, 2)

    @property
    def risk_reward_ratio(self) -> float:
        return self.reward / self.risk

    @property
    def r(self) -> float:
        """alias for risk_reward_ratio"""
        return self.risk_reward_ratio

    @property
    def pnl(self) -> float:
        """PNL"""
        fee = config['env']['exchanges'][self.exchange]['fee']
        return jh.estimate_PNL(
            self.qty, self.entry_price, self.exit_price,
            self.type, fee
        )

    @property
    def pnl_percentage(self) -> float:
        """
        Alias for self.roi
        """
        return self.roi

    @property
    def roi(self) -> float:
        """
        Return on Investment in percentage
        More at: https://www.binance.com/en/support/faq/5b9ad93cb4854f5990b9fb97c03cfbeb
        """
        return self.pnl / self.total_cost * 100

    @property
    def total_cost(self) -> float:
        """
        How much we paid to open this position (currently does not include fees, should we?!)
        """
        return self.entry_price * abs(self.qty) / self.leverage

    @property
    def holding_period(self) -> int:
        """How many SECONDS has it taken for the trade to be done."""
        return (self.closed_at - self.opened_at) / 1000


if not jh.is_unit_testing():
    # create the table
    CompletedTrade.create_table()
