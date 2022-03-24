from typing import Union

import numpy as np

import jesse.helpers as jh
import jesse.services.selectors as selectors
from jesse.enums import trade_types, order_types
from jesse.exceptions import EmptyPosition, OpenPositionError
from jesse.models import Order, Exchange
from jesse.services import logger
from jesse.utils import sum_floats, subtract_floats


class Position:
    def __init__(self, exchange_name: str, symbol: str, attributes: dict = None) -> None:
        self.id = jh.generate_unique_id()
        self.entry_price = None
        self.exit_price = None
        self.current_price = None
        self.qty = 0
        self.opened_at = None
        self.closed_at = None
        self._mark_price = None
        self._funding_rate = None
        self._next_funding_timestamp = None
        self._liquidation_price = None

        if attributes is None:
            attributes = {}

        self.exchange_name = exchange_name
        self.exchange: Exchange = selectors.get_exchange(self.exchange_name)

        self.symbol = symbol
        self.strategy = None

        for a in attributes:
            setattr(self, a, attributes[a])

    @property
    def mark_price(self) -> float:
        if not jh.is_live():
            return self.current_price

        return self._mark_price

    @property
    def funding_rate(self) -> float:
        if not jh.is_live():
            return 0

        return self._funding_rate

    @property
    def next_funding_timestamp(self) -> Union[int, None]:
        if not jh.is_live():
            return None

        return self._next_funding_timestamp

    @property
    def value(self) -> float:
        """
        The value of open position in the quote currency

        :return: float
        """
        return abs(self.current_price * self.qty)

    @property
    def type(self) -> str:
        """
        The type of open position - long, short, or close

        :return: str
        """
        if self.is_long:
            return 'long'
        if self.is_short:
            return 'short'

        return 'close'

    @property
    def pnl_percentage(self) -> float:
        """
        Alias for self.roi

        :return: float
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
        if self.is_close:
            return np.nan

        base_cost = self.entry_price * abs(self.qty)
        if self.strategy:
            return base_cost / self.leverage

        return base_cost

    @property
    def leverage(self) -> Union[int, np.float64]:
        if self.exchange.type == 'spot':
            return 1

        if self.strategy:
            return self.strategy.leverage
        else:
            return np.nan

    @property
    def entry_margin(self) -> float:
        """
        Alias for self.total_cost
        """
        return self.total_cost

    @property
    def pnl(self) -> float:
        """
        The PNL of the position

        :return: float
        """
        if self.qty == 0:
            return 0

        diff = self.value - abs(self.entry_price * self.qty)

        return -diff if self.type == 'short' else diff

    @property
    def is_open(self) -> bool:
        """
        Is the current position open?

        :return: bool
        """
        return self.qty != 0

    @property
    def is_close(self) -> bool:
        """
        Is the current position close?

        :return: bool
        """
        return self.qty == 0

    @property
    def is_long(self) -> bool:
        """
        Is the current position a long position?

        :return: bool
        """
        return self.qty > 0

    @property
    def is_short(self) -> bool:
        """
        Is the current position a short position?

        :return: bool
        """
        return self.qty < 0

    @property
    def mode(self) -> str:
        if self.exchange.type == 'spot':
            return 'spot'
        else:
            return self.exchange.futures_leverage_mode

    @property
    def liquidation_price(self) -> Union[float, np.float64]:
        """
        The price at which the position gets liquidated. formulas are taken from:
        https://help.bybit.com/hc/en-us/articles/900000181046-Liquidation-Price-USDT-Contract-
        """
        if self.is_close:
            return np.nan

        if jh.is_livetrading():
            return self._liquidation_price

        if self.mode in ['cross', 'spot']:
            return np.nan

        elif self.mode == 'isolated':
            if self.type == 'long':
                return self.entry_price * (1 - self._initial_margin_rate + 0.004)
            elif self.type == 'short':
                return self.entry_price * (1 + self._initial_margin_rate - 0.004)
            else:
                return np.nan

        else:
            raise ValueError

    @property
    def _initial_margin_rate(self) -> float:
        return 1 / self.leverage

    @property
    def bankruptcy_price(self) -> Union[float, np.float64]:
        if self.type == 'long':
            return self.entry_price * (1 - self._initial_margin_rate)
        elif self.type == 'short':
            return self.entry_price * (1 + self._initial_margin_rate)
        else:
            return np.nan

    @property
    def to_dict(self):
        return {
            'entry_price': self.entry_price,
            'qty': self.qty,
            'current_price': self.current_price,
            'value': self.value,
            'type': self.type,
            'exchange': self.exchange_name,
            'pnl': self.pnl,
            'pnl_percentage': self.pnl_percentage,
            'leverage': self.leverage,
            'liquidation_price': self.liquidation_price,
            'bankruptcy_price': self.bankruptcy_price,
            'mode': self.mode,
        }

    def _mutating_close(self, close_price: float) -> None:
        if self.is_open is False:
            raise EmptyPosition('The position is already closed.')

        # just to prevent confusion
        close_qty = abs(self.qty)

        estimated_profit = jh.estimate_PNL(
            close_qty, self.entry_price,
            close_price, self.type
        )
        entry = self.entry_price
        trade_type = self.type
        self.exit_price = close_price

        if self.exchange:
            self.exchange.add_realized_pnl(estimated_profit)
            self.exchange.temp_reduced_amount[jh.base_asset(self.symbol)] += abs(close_qty * close_price)
        self.closed_at = jh.now_to_timestamp()

        self.qty = 0
        self.entry_price = None

        self._close()

    def _close(self):
        from jesse.store import store
        store.completed_trades.close_trade(self)

    def _mutating_reduce(self, qty: float, price: float) -> None:
        if self.is_open is False:
            raise EmptyPosition('The position is closed.')

        # just to prevent confusion
        qty = abs(qty)

        estimated_profit = jh.estimate_PNL(qty, self.entry_price, price, self.type)

        if self.exchange:
            # self.exchange.increase_futures_balance(qty * self.entry_price + estimated_profit)
            self.exchange.add_realized_pnl(estimated_profit)
            self.exchange.temp_reduced_amount[jh.base_asset(self.symbol)] += abs(qty * price)

        if self.type == trade_types.LONG:
            self.qty = subtract_floats(self.qty, qty)
        elif self.type == trade_types.SHORT:
            self.qty = sum_floats(self.qty, qty)

    def _mutating_increase(self, qty: float, price: float) -> None:
        if not self.is_open:
            raise OpenPositionError('position must be already open in order to increase its size')

        qty = abs(qty)

        self.entry_price = jh.estimate_average_price(
            qty, price, self.qty,
            self.entry_price
        )

        if self.type == trade_types.LONG:
            self.qty = sum_floats(self.qty, qty)
        elif self.type == trade_types.SHORT:
            self.qty = subtract_floats(self.qty, qty)

    def _mutating_open(self, qty: float, price: float, change_balance: bool = True) -> None:
        if self.is_open:
            raise OpenPositionError('an already open position cannot be opened')

        self.entry_price = price
        self.exit_price = None
        self.qty = qty
        self.opened_at = jh.now_to_timestamp()

        self._open()

    def _open(self):
        from jesse.store import store
        store.completed_trades.open_trade(self)

    def _on_executed_order(self, order: Order) -> None:
        if jh.is_livetrading():
            # if position got closed because of this order
            if order.is_partially_filled:
                before_qty = self.qty - order.filled_qty
            else:
                before_qty = self.qty - order.qty
            after_qty = self.qty
            if before_qty != 0 and after_qty == 0:
                self._close()
        else:
            qty = order.qty
            price = order.price

            # TODO: detect reduce_only order, and if so, see if you need to adjust qty and price (above variables)

            self.exchange.charge_fee(qty * price)

            # order opens position
            if self.qty == 0:
                change_balance = order.type == order_types.MARKET
                self._mutating_open(qty, price, change_balance)
            # order closes position
            elif (sum_floats(self.qty, qty)) == 0:
                self._mutating_close(price)
            # order increases the size of the position
            elif self.qty * qty > 0:
                if order.reduce_only:
                    logger.info('Did not increase position because order is a reduce_only order')
                else:
                    self._mutating_increase(qty, price)
            # order reduces the size of the position
            elif self.qty * qty < 0:
                # if size of the order is big enough to both close the
                # position AND open it on the opposite side
                if abs(qty) > abs(self.qty):
                    if order.reduce_only:
                        logger.info(
                            f'Executed order is bigger than the current position size but it is a reduce_only order so it just closes it. Order QTY: {qty}, Position QTY: {self.qty}')
                        self._mutating_close(price)
                    else:
                        logger.info(
                            f'Executed order is big enough to not close, but flip the position type. Order QTY: {qty}, Position QTY: {self.qty}')
                        diff_qty = sum_floats(self.qty, qty)
                        self._mutating_close(price)
                        self._mutating_open(diff_qty, price)
                else:
                    self._mutating_reduce(qty, price)

        if self.strategy:
            self.strategy._on_updated_position(order)

    def update_from_stream(self, data: dict, is_initial: bool) -> None:
        """
        Used for updating the position from the WS stream (only for live trading)
        """
        before_qty = abs(self.qty)
        after_qty = abs(data['qty'])

        self.entry_price = data['entry_price']
        self._liquidation_price = data['liquidation_price']
        self.qty = data['qty']

        # if opening position
        if before_qty == 0 and after_qty != 0:
            if is_initial:
                from jesse.store import store
                store.completed_trades.add_order_record_only(
                    self.exchange_name, self.symbol, jh.type_to_side(self.type),
                    self.qty, self.entry_price
                )
            self.opened_at = jh.now_to_timestamp()
            self._open()
        # if closing position
        elif before_qty != 0 and after_qty == 0:
            self.closed_at = jh.now_to_timestamp()
