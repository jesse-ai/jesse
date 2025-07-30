import numpy as np
import peewee
import threading

import jesse.helpers as jh
from jesse.config import config
from jesse.services.db import database
from jesse.libs.dynamic_numpy_array import DynamicNumpyArray
from jesse.enums import trade_types
from jesse.models.Order import Order
from jesse.enums import order_statuses

if database.is_closed():
    database.open_connection()


class ClosedTrade(peewee.Model):
    """A trade is made when a position is opened AND closed."""

    id = peewee.UUIDField(primary_key=True)
    session_id = peewee.UUIDField()
    strategy_name = peewee.CharField()
    symbol = peewee.CharField()
    exchange = peewee.CharField()
    type = peewee.CharField()
    timeframe = peewee.CharField()
    opened_at = peewee.BigIntegerField()
    closed_at = peewee.BigIntegerField(null=True)
    leverage = peewee.IntegerField()
    created_at = peewee.BigIntegerField()
    updated_at = peewee.BigIntegerField()
    session_mode = peewee.CharField()
    soft_deleted_at = peewee.BigIntegerField(null=True)

    class Meta:
        from jesse.services.db import database

        database = database.db
        indexes = ((('strategy_name', 'exchange', 'symbol'), False),)

    def __init__(self, attributes: dict = None, **kwargs) -> None:
        peewee.Model.__init__(self, attributes=attributes, **kwargs)

        if attributes is None:
            attributes = {}

        for a, value in attributes.items():
            setattr(self, a, value)

        # used for fast calculation of the total qty, entry_price, exit_price, etc.
        self.buy_orders = DynamicNumpyArray((10, 2))
        self.sell_orders = DynamicNumpyArray((10, 2))
        # to store the actual order objects
        self.orders = []

    @staticmethod
    def get_trade_by_id(trade_id):
        return ClosedTrade.get(ClosedTrade.id == trade_id)

    @staticmethod
    def store_closed_trade_into_db(closed_trade):
        # check id exist in previouse record or not
        db_trade = ClosedTrade.select().where(ClosedTrade.id == closed_trade.id).first()
        if db_trade:
            return

        d = {
            'id': closed_trade.id,
            'session_id': closed_trade.session_id,
            'strategy_name': closed_trade.strategy_name,
            'symbol': closed_trade.symbol,
            'exchange': closed_trade.exchange,
            'type': closed_trade.type,
            'timeframe': closed_trade.timeframe,
            'opened_at': closed_trade.opened_at,
            'leverage': closed_trade.leverage,
            'created_at': jh.now_to_timestamp(),
            'updated_at': jh.now_to_timestamp(),
            'session_mode': config['app']['trading_mode'],
        }

        try:
            ClosedTrade.insert(**d).execute()
        except Exception as e:
            jh.dump(f"Error storing closed trade in database: {e}")

    @staticmethod
    def close_trade_in_db(closed_trade):
        d = {
            'closed_at': closed_trade.closed_at if closed_trade.closed_at else jh.now_to_timestamp(),
            'updated_at': jh.now_to_timestamp(),
        }
        try:
            ClosedTrade.update(**d).where(ClosedTrade.id == closed_trade.id).execute()
        except Exception as e:
            jh.dump(f"Error closing trade in database: {e}")

    @staticmethod
    def get_open_trade(exchange_name, symbol):
        valid_value = None
        trade = ClosedTrade.select().where(
            ClosedTrade.soft_deleted_at == valid_value).where(
            ClosedTrade.session_mode == 'livetrade').where(
            ClosedTrade.exchange == exchange_name).where(
            ClosedTrade.symbol == symbol).order_by(
            ClosedTrade.opened_at.desc()).first()

        if trade is None:
            return None

        # Fetch orders for each trade and populate the orders list
        from jesse.enums import sides
        exchange_orders = list(Order.select().where(Order.trade_id == trade.id).where(Order.status == order_statuses.EXECUTED).where(Order.order_exist_in_exchange == True).order_by(Order.executed_at))
        simulated_orders = list(Order.select().where(Order.trade_id == trade.id).where(Order.status == order_statuses.EXECUTED).where(Order.order_exist_in_exchange == False).order_by(Order.executed_at))
        if len(exchange_orders) == 0:
            # when trade don't have any exchange orders, we need to check if it has simulated orders
            if len(simulated_orders) > 0:
                for simulated_order in simulated_orders:
                    if simulated_order.side == sides.BUY:
                        trade.buy_orders.append(np.array([abs(simulated_order.qty), simulated_order.price]))
                    elif simulated_order.side == sides.SELL:
                        trade.sell_orders.append(np.array([abs(simulated_order.qty), simulated_order.price]))
                trade.is_simulated = True
            return trade
        trade.orders = {order.exchange_id: order for order in exchange_orders if order.exchange_id}
        trade.is_simulated = False
        for o in exchange_orders + simulated_orders:
            if o.side == sides.BUY:
                trade.buy_orders.append(np.array([abs(o.filled_qty), o.price]))
            elif o.side == sides.SELL:
                trade.sell_orders.append(np.array([abs(o.filled_qty), o.price]))
        if trade.current_qty == 0:
            ClosedTrade.close_trade_in_db(trade)
            return None
        else:
            return trade

    @staticmethod
    def disable_trade_in_db(trade_id):
        d = {
            'soft_deleted_at': jh.now_to_timestamp(),
        }
        ClosedTrade.update(**d).where(ClosedTrade.id == trade_id).execute()

    @property
    def to_json(self) -> dict:
        return {
            "id": self.id,
            "strategy_name": jh.get_class_name(self.strategy_name),
            "symbol": self.symbol,
            "exchange": self.exchange,
            "type": self.type,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "qty": self.qty,
            "fee": self.fee,
            "size": self.size,
            "PNL": self.pnl,
            "PNL_percentage": self.pnl_percentage,
            "holding_period": self.holding_period,
            "opened_at": self.opened_at,
            "closed_at": self.closed_at,
        }

    @property
    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'strategy_name': jh.get_class_name(self.strategy_name),
            'symbol': self.symbol,
            'exchange': self.exchange,
            'type': self.type,
            'entry_price': self.entry_price,
            'exit_price': self.exit_price,
            'qty': self.qty,
            'opened_at': self.opened_at,
            'closed_at': self.closed_at,
            "fee": self.fee,
            "size": self.size,
            "PNL": self.pnl,
            "PNL_percentage": self.pnl_percentage,
            "holding_period": self.holding_period,
        }

    @property
    def to_dict_with_orders(self) -> dict:
        data = self.to_dict
        data['orders'] = [order.to_dict for order in self.orders]
        return data

    @property
    def fee(self) -> float:
        trading_fee = jh.get_config(f'env.exchanges.{self.exchange}.fee')
        return trading_fee * self.qty * (self.entry_price + self.exit_price)

    @property
    def size(self) -> float:
        return self.qty * self.entry_price

    @property
    def pnl(self) -> float:
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
        if self.closed_at is None:
            return None
        return (self.closed_at - self.opened_at) / 1000

    @property
    def is_long(self) -> bool:
        return self.type == trade_types.LONG

    @property
    def is_short(self) -> bool:
        return self.type == trade_types.SHORT

    @property
    def qty(self) -> float:
        if self.is_long:
            return self.buy_orders[:][:, 0].sum()
        elif self.is_short:
            return self.sell_orders[:][:, 0].sum()
        else:
            return 0.0

    @property
    def entry_price(self) -> float:
        if self.is_long:
            orders = self.buy_orders[:]
        elif self.is_short:
            orders = self.sell_orders[:]
        else:
            return np.nan

        return (orders[:, 0] * orders[:, 1]).sum() / orders[:, 0].sum()

    @property
    def current_qty(self) -> float:
        trade_orders = Order.select().where(Order.trade_id == self.id).where(Order.status == order_statuses.EXECUTED).order_by(Order.executed_at)
        if len(trade_orders) == 0:
            return 0.0
        else:
            import jesse.utils as utils
            qty = 0.0
            for order in trade_orders:
                qty = utils.sum_floats(qty, order.filled_qty)
            return qty

    @property
    def exit_price(self) -> float:
        if self.is_long:
            orders = self.sell_orders[:]
        elif self.is_short:
            orders = self.buy_orders[:]
        else:
            return np.nan

        return (orders[:, 0] * orders[:, 1]).sum() / orders[:, 0].sum()

    @property
    def is_open(self) -> bool:
        return self.opened_at is not None


# if database is open, create the table
if database.is_open():
    ClosedTrade.create_table()


# # # # # # # # # # # # # # # # # # # # # # # # # # #
# # # # # # # # # DB FUNCTIONS # # # # # # # # #
# # # # # # # # # # # # # # # # # # # # # # # # # # #

def store_closed_trade_into_db(closed_trade) -> None:
    return

    d = {
        'id': closed_trade.id,
        'strategy_name': closed_trade.strategy_name,
        'symbol': closed_trade.symbol,
        'exchange': closed_trade.exchange,
        'type': closed_trade.type,
        'timeframe': closed_trade.timeframe,
        'entry_price': closed_trade.entry_price,
        'exit_price': closed_trade.exit_price,
        'qty': closed_trade.qty,
        'opened_at': closed_trade.opened_at,
        'closed_at': closed_trade.closed_at,
        'leverage': closed_trade.leverage,
    }

    def async_save() -> None:
        ClosedTrade.insert(**d).execute()
        if jh.is_debugging():
            logger.info(
                f'Stored the closed trade record for {closed_trade.exchange}-{closed_trade.symbol}-{closed_trade.strategy_name} into database.')

    # async call
    threading.Thread(target=async_save).start()
