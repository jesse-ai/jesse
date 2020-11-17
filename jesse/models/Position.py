import jesse.helpers as jh
import jesse.services.selectors as selectors
import jesse.utils as ju
from jesse.config import config
from jesse.enums import trade_types, order_types
from jesse.exceptions import EmptyPosition, OpenPositionError
from jesse.models import Order
from jesse.services import logger, notifier
from jesse.utils import sum_floats, subtract_floats


class Position:
    def __init__(self, exchange_name, symbol, attributes=None):
        self.id = jh.generate_unique_id()
        self.entry_price = None
        self.exit_price = None
        self.current_price = None
        self.qty = 0
        self.opened_at = None
        self.closed_at = None

        if attributes is None:
            attributes = {}

        self.exchange_name = exchange_name
        self.exchange = selectors.get_exchange(self.exchange_name)
        self.symbol = symbol
        self.strategy = None

        for a in attributes:
            setattr(self, a, attributes[a])

    @property
    def value(self):
        """
        The value of open position

        :return: float
        """
        return abs(self.current_price * self.qty)

    @property
    def type(self):
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
    def pnl_percentage(self):
        """
        The PNL% of the position

        :return: float
        """
        if self.qty == 0:
            return 0

        exit_price = self.current_price if self.exit_price is None else self.exit_price

        return jh.estimate_PNL_percentage(self.qty, self.entry_price, exit_price, self.type)

    @property
    def pnl(self):
        """
        The PNL of the position

        :return: float
        """
        if self.qty == 0:
            return 0

        diff = self.value - abs(self.entry_price * self.qty)

        return -diff if self.type == 'short' else diff

    @property
    def is_open(self):
        """
        Is the current position open?

        :return: bool
        """
        return self.qty != 0

    @property
    def is_close(self):
        """
        Is the current position close?

        :return: bool
        """
        return self.qty == 0

    def _close(self, close_price):
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
        self.closed_at = jh.now()

        info_text = 'CLOSED {} position: {}, {}. PNL: ${}, entry: {}, exit: {}'.format(
            trade_type, self.exchange_name, self.symbol, round(estimated_profit, 2), entry, close_price
        )

        if jh.is_debuggable('position_closed'):
            logger.info(info_text)

        if jh.is_live() and config['env']['notifications']['events']['updated_position']:
            notifier.notify(info_text)

    def _reduce(self, qty, price):
        if self.is_open is False:
            raise EmptyPosition('The position is closed.')

        # just to prevent confusion
        qty = abs(qty)

        estimated_profit = jh.estimate_PNL(qty, self.entry_price, price, self.type)

        if self.exchange:
            # self.exchange.increase_margin_balance(qty * self.entry_price + estimated_profit)
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

    def _increase(self, qty, price):
        if not self.is_open:
            raise OpenPositionError('position must be already open in order to increase its size')

        qty = abs(qty)
        size = qty * price

        # if self.exchange:
        #     self.exchange.decrease_margin_balance(size)

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

    def _open(self, qty, price, change_balance=True):
        if self.is_open:
            raise OpenPositionError('an already open position cannot be opened')

        # if change_balance:
        #     size = abs(qty) * price
            # if self.exchange:
            #     self.exchange.decrease_margin_balance(size)

        self.entry_price = price
        self.exit_price = None
        self.qty = qty
        self.opened_at = jh.now()

        info_text = 'OPENED {} position: {}, {}, {}, ${}'.format(
            self.type, self.exchange_name, self.symbol, self.qty, round(self.entry_price, 2)
        )

        if jh.is_debuggable('position_opened'):
            logger.info(info_text)

        if jh.is_live() and config['env']['notifications']['events']['updated_position']:
            notifier.notify(info_text)

    def _on_opened_order(self, order):
        # skip MARKET orders because they're already
        # being impacted at self.on_executed_order
        if order.type == order_types.MARKET:
            return

        # qty = order.qty
        # price = order.price
        # size = ju.qty_to_size(qty, price)
        # available_qty = self.exchange.available_assets[jh.base_asset(self.symbol)]
        #
        # # # open-position order
        # # if available_qty == 0:
        # #     if self.exchange:
        # #         self.exchange.decrease_margin_balance(size)
        # # # increase-position order
        # # elif available_qty * qty > 0:
        # #     if self.exchange:
        # #         self.exchange.decrease_margin_balance(size)
        # # # reduce-position order
        # # elif available_qty * qty < 0:
        # #     if abs(qty) > abs(available_qty):
        # #         diff_qty = qty + available_qty
        # #         size = ju.qty_to_size(diff_qty, price)
        # #         if self.exchange:
        # #             self.exchange.decrease_margin_balance(size)

    def _on_canceled_order(self, order):
        qty = order.qty
        price = order.price
        size = ju.qty_to_size(qty, price)
        available_qty = self.exchange.available_assets[jh.base_asset(self.symbol)]

        if order.is_reduce_only:
            return
        #
        # # detect reduce_only
        # if abs(available_qty + order.qty) > abs(available_qty):
        #     return
        #
        # # open-position order
        # if available_qty == 0:
        #     if self.exchange:
        #         self.exchange.increase_margin_balance(size, True)
        # # increase-position order
        # elif available_qty * qty > 0:
        #     if self.exchange:
        #         self.exchange.increase_margin_balance(size, True)
        # # reduce-position order
        # elif available_qty * qty < 0:
        #     if abs(qty) > abs(available_qty):
        #         diff_qty = qty + available_qty
        #         size = ju.qty_to_size(diff_qty, price)
        #         if self.exchange:
        #             self.exchange.increase_margin_balance(size, True)

    def _on_executed_order(self, order: Order):
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
            self._increase(qty, price)
        # order reduces the size of the position
        elif self.qty * qty < 0:
            # if size of the order is big enough to both close the
            # position AND open it on the opposite side
            if abs(qty) > abs(self.qty):
                logger.info('Executed order is big enough to not close, but flip the position type. Order QTY: {}, Position QTY: {}'.format(
                    qty, self.qty
                ))
                diff_qty = sum_floats(self.qty, qty)
                self._close(price)
                self._open(diff_qty, price)
            else:
                self._reduce(qty, price)

        if self.strategy:
            self.strategy._on_updated_position(order)
        #
        # # handle REDUCE_ONLY orders
        # if order.flag == order_flags.REDUCE_ONLY:
        #     if self.qty == 0 or self.qty * qty > 0:
        #         return
        #     if self.qty * qty < 0 and abs(qty) > abs(self.qty):
        #         self._close(price)
        #         if self.strategy:
        #             self.strategy._on_updated_position(order)
        #         return
        #
        # # order opens position
        # if self.qty == 0 and order.type:
        #     change_balance = order.type == order_types.MARKET
        #     self._open(qty, price, change_balance)
        # # order closes position
        # elif (self.qty + qty) == 0:
        #     self._close(price)
        # # order increases the size of the position
        # elif self.qty * qty > 0:
        #     self._increase(qty, price)
        # # order reduces the size of the position
        # elif self.qty * qty < 0:
        #     # if size of the order is big enough to both close the
        #     # position AND open it on the opposite side
        #     if abs(qty) > abs(self.qty):
        #         diff_qty = qty + self.qty
        #         self._close(price)
        #         self._open(diff_qty, price)
        #     else:
        #         self._reduce(qty, price)
        #
        # if self.strategy:
        #     self.strategy._on_updated_position(order)
