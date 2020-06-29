import numpy as np

import jesse.helpers as jh
from jesse.config import config


class CompletedTrade:
    """A trade is made when a position is opened AND closed."""

    def __init__(self, attributes=None):
        self.id = ''
        self.strategy_name = ''
        self.symbol = ''
        self.exchange = ''
        self.type = ''
        self.timeframe = None
        self.entry_price = np.nan
        self.exit_price = np.nan
        self.take_profit_at = np.nan
        self.stop_loss_at = np.nan
        self.qty = np.nan
        self.orders = []
        self.opened_at = None
        self.closed_at = None
        self.entry_candle_timestamp = None
        self.exit_candle_timestamp = None
        self.reduced_at = None
        self.reduction_timestamp = None
        self.reduction_candle_timestamp = None

        if attributes is None:
            attributes = {}

        for a in attributes:
            setattr(self, a, attributes[a])

    def toJSON(self):
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
            "R": self.R,
            "PNL": self.PNL,
            "PNL_percentage": self.PNL_percentage,
            "holding_period": self.holding_period,
            "opened_at": self.opened_at,
            "closed_at": self.closed_at,
            "entry_candle_timestamp": self.entry_candle_timestamp,
            "exit_candle_timestamp": self.exit_candle_timestamp,
            "orders": orders,
        }

    def to_dict(self):
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
            "R": self.R,
            "PNL": self.PNL,
            "PNL_percentage": self.PNL_percentage,
            "holding_period": self.holding_period,
        }

    @property
    def fee(self):
        trading_fee = config['env']['exchanges'][self.exchange]['fee']
        return trading_fee * self.qty * (self.entry_price + self.exit_price)

    @property
    def reward(self):
        return abs(self.take_profit_at - self.entry_price) * self.qty

    @property
    def size(self):
        return self.qty * self.entry_price

    @property
    def risk(self):
        return abs(self.stop_loss_at - self.entry_price) * self.qty

    @property
    def risk_percentage(self):
        return round((self.risk / self.size) * 100, 2)

    @property
    def risk_reward_ratio(self):
        return self.reward / self.risk

    @property
    def R(self):
        """alias for risk_reward_ratio"""
        return self.risk_reward_ratio

    @property
    def PNL(self):
        """PNL"""
        fee = config['env']['exchanges'][self.exchange]['fee']
        return jh.estimate_PNL(self.qty, self.entry_price, self.exit_price,
                               self.type, fee)

    @property
    def PNL_percentage(self):
        """The PNL%"""
        return round((self.PNL / self.size) * 100, 2)

    @property
    def holding_period(self):
        """How many SECONDS has it taken for the trade to be done."""
        return (self.closed_at - self.opened_at) / 1000
