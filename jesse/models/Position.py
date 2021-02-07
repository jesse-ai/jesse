import numpy as np

import jesse.helpers as jh
import jesse.services.selectors as selectors
from jesse.config import config
from jesse.enums import trade_types, order_types
from jesse.exceptions import EmptyPosition, OpenPositionError
from jesse.models import Order, Exchange
from jesse.services import logger, notifier
from jesse.utils import sum_floats, subtract_floats


class Position:
    def __init__(self, exchange_name: str, symbol: str, attributes=None) -> None:
        self.id = jh.generate_unique_id()
        self.entry_price = None
        self.exit_price = None
        self.current_price = None
        self.qty = 0
        self.opened_at = None
        self.closed_at = None

        # TODO: self._mark_price = None

        if attributes is None:
            attributes = {}

        self.exchange_name = exchange_name
        self.exchange: Exchange = selectors.get_exchange(self.exchange_name)

        self.symbol = symbol
        self.strategy = None

        for a in attributes:
            setattr(self, a, attributes[a])

    # @property
    # def mark_price(self):
    #     # TODO: make sure that it is available only for live trading in futures markets
    #     return self._mark_price

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
        if self.qty > 0:
            return 'long'
        if self.qty < 0:
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

        return self.entry_price * abs(self.qty) / self.exchange.futures_leverage

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
    def mode(self) -> str:
        if self.exchange.spot == 'spot':
            return 'spot'
        else:
            return self.exchange.futures_leverage_mode

    # - Margin Ratio
    # * Liquidation price
    # * mark price?!
    # * ROE(PNL?)
    # * Maintenance futures
    # * futures balance

    # @property
    # def futures_ratio(self):
    #     return 0

    def _close(self, close_price: float) -> None:
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
        self.qty = 0
        self.entry_price = None
        self.closed_at = jh.now_to_timestamp()

        if not jh.is_unit_testing():
            info_text = 'CLOSED {} position: {}, {}, {}. PNL: ${}, Balance: ${}, entry: {}, exit: {}'.format(
                trade_type, self.exchange_name, self.symbol, self.strategy.name,
                round(estimated_profit, 2), jh.format_currency(round(self.exchange.wallet_balance(self.symbol), 2)),
                entry, close_price
            )

            if jh.is_debuggable('position_closed'):
                logger.info(info_text)

            if jh.is_live() and config['env']['notifications']['events']['updated_position']:
                notifier.notify(info_text)

    def _reduce(self, qty: float, price: float) -> None:
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

        info_text = 'REDUCED position: {}, {}, {}, {}, ${}'.format(
            self.exchange_name, self.symbol, self.type, self.qty, round(self.entry_price, 2)
        )

        if jh.is_debuggable('position_reduced'):
            logger.info(info_text)

        if jh.is_live() and config['env']['notifications']['events']['updated_position']:
            notifier.notify(info_text)

    def _increase(self, qty: float, price: float) -> None:
        if not self.is_open:
            raise OpenPositionError('position must be already open in order to increase its size')

        qty = abs(qty)
        size = qty * price

        # if self.exchange:
        #     self.exchange.decrease_futures_balance(size)

        self.entry_price = jh.estimate_average_price(qty, price, self.qty,
                                                     self.entry_price)

        if self.type == trade_types.LONG:
            self.qty = sum_floats(self.qty, qty)
        elif self.type == trade_types.SHORT:
            self.qty = subtract_floats(self.qty, qty)

        info_text = 'INCREASED position: {}, {}, {}, {}, ${}'.format(
            self.exchange_name, self.symbol, self.type, self.qty, round(self.entry_price, 2)
        )

        if jh.is_debuggable('position_increased'):
            logger.info(info_text)

        if jh.is_live() and config['env']['notifications']['events']['updated_position']:
            notifier.notify(info_text)

    def _open(self, qty: float, price: float, change_balance: bool = True) -> None:
        if self.is_open:
            raise OpenPositionError('an already open position cannot be opened')

        self.entry_price = price
        self.exit_price = None
        self.qty = qty
        self.opened_at = jh.now_to_timestamp()

        info_text = 'OPENED {} position: {}, {}, {}, ${}'.format(
            self.type, self.exchange_name, self.symbol, self.qty, round(self.entry_price, 2)
        )

        if jh.is_debuggable('position_opened'):
            logger.info(info_text)

        if jh.is_live() and config['env']['notifications']['events']['updated_position']:
            notifier.notify(info_text)

    def _on_executed_order(self, order: Order) -> None:
        qty = order.qty
        price = order.price

        # TODO: detect reduce_only order, and if so, see if you need to adjust qty and price (above variables)

        self.exchange.charge_fee(qty * price)

        # order opens position
        if self.qty == 0:
            change_balance = order.type == order_types.MARKET
            self._open(qty, price, change_balance)
        # order closes position
        elif (sum_floats(self.qty, qty)) == 0:
            self._close(price)
        # order increases the size of the position
        elif self.qty * qty > 0:
            if order.is_reduce_only:
                logger.info('Did not increase position because order is a reduce_only order')
            else:
                self._increase(qty, price)
        # order reduces the size of the position
        elif self.qty * qty < 0:
            # if size of the order is big enough to both close the
            # position AND open it on the opposite side
            if abs(qty) > abs(self.qty):
                if order.is_reduce_only:
                    logger.info(
                        'Executed order is bigger than the current position size but it is a reduce_only order so it just closes it. Order QTY: {}, Position QTY: {}'.format(
                            qty, self.qty
                        ))
                    self._close(price)
                else:
                    logger.info(
                        'Executed order is big enough to not close, but flip the position type. Order QTY: {}, Position QTY: {}'.format(
                            qty, self.qty
                        ))
                    diff_qty = sum_floats(self.qty, qty)
                    self._close(price)
                    self._open(diff_qty, price)
            else:
                self._reduce(qty, price)

        if self.strategy:
            self.strategy._on_updated_position(order)
