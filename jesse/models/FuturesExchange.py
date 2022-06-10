import numpy as np
import jesse.helpers as jh
import jesse.services.logger as logger
from jesse.enums import sides, order_types
from jesse.exceptions import InsufficientMargin
from jesse.models import Order
from jesse.services import selectors
from jesse.models.Exchange import Exchange


class FuturesExchange(Exchange):
    def __init__(
            self,
            name: str,
            starting_balance: float,
            fee_rate: float,
            futures_leverage_mode: str,
            futures_leverage: int
    ):
        super().__init__(name, starting_balance, fee_rate, 'futures')

        # # # # live-trading only # # # #
        # in futures trading, margin is only with one asset, so:
        self._available_margin = 0
        # in futures trading, wallet is only with one asset, so:
        self._wallet_balance = 0
        # so is started_balance
        self._started_balance = 0
        # # # # # # # # # # # # # # # # #

        self.futures_leverage_mode = futures_leverage_mode
        self.futures_leverage = futures_leverage

    @property
    def started_balance(self) -> float:
        if jh.is_livetrading():
            return self._started_balance

        return self.starting_assets[jh.app_currency()]

    @property
    def wallet_balance(self) -> float:
        if jh.is_livetrading():
            return self._wallet_balance

        return self.assets[self.settlement_currency]

    @property
    def available_margin(self) -> float:
        if jh.is_livetrading():
            return self._available_margin

        # a temp which gets added to per each asset (remember that all future assets use the same currency for settlement)
        temp_credits = self.assets[self.settlement_currency]

        # we need to consider buy and sell orders of ALL pairs
        # also, consider the value of all open positions
        for asset in self.assets:
            if asset == self.settlement_currency:
                continue

            position = selectors.get_position(self.name, f"{asset}-{self.settlement_currency}")
            if position is None:
                continue

            if position.is_open:
                # add unrealized PNL
                temp_credits += position.pnl

            # only which of these has actual values, so we can count all of them!
            sum_buy_orders = (self.buy_orders[asset][:][:, 0] * self.buy_orders[asset][:][:, 1]).sum()
            sum_sell_orders = (self.sell_orders[asset][:][:, 0] * self.sell_orders[asset][:][:, 1]).sum()

            if position.is_open:
                temp_credits -= position.total_cost

            # Subtract the amount we paid for open orders. Notice that this does NOT include
            # reduce_only orders so either sum_buy_orders or sum_sell_orders is zero. We also
            # care about the cost we actually paid for it which takes into account the leverage
            temp_credits -= max(
                abs(sum_buy_orders) / self.futures_leverage, abs(sum_sell_orders) / self.futures_leverage
            )

        # count in the leverage
        return temp_credits * self.futures_leverage

    def charge_fee(self, amount: float) -> None:
        if jh.is_livetrading():
            return

        fee_amount = abs(amount) * self.fee_rate
        new_balance = self.assets[self.settlement_currency] - fee_amount
        if fee_amount != 0:
            logger.info(
                f'Charged {round(fee_amount, 2)} as fee. Balance for {self.settlement_currency} on {self.name} changed from {round(self.assets[self.settlement_currency], 2)} to {round(new_balance, 2)}'
            )
        self.assets[self.settlement_currency] = new_balance

    def add_realized_pnl(self, realized_pnl: float) -> None:
        if jh.is_livetrading():
            return

        new_balance = self.assets[self.settlement_currency] + realized_pnl
        logger.info(
            f'Added realized PNL of {round(realized_pnl, 2)}. Balance for {self.settlement_currency} on {self.name} changed from {round(self.assets[self.settlement_currency], 2)} to {round(new_balance, 2)}')
        self.assets[self.settlement_currency] = new_balance

    def on_order_submission(self, order: Order) -> None:
        if jh.is_livetrading():
            return

        base_asset = jh.base_asset(order.symbol)

        # make sure we don't spend more than we're allowed considering current allowed leverage
        if not order.reduce_only:
            order_size = abs(order.qty * order.price)
            if order_size > self.available_margin:
                raise InsufficientMargin(
                    f'You cannot submit an order for ${round(order_size)} when your margin balance is ${round(self.available_margin)}')

        self.available_assets[base_asset] += order.qty

        if not order.reduce_only:
            if order.side == sides.BUY:
                self.buy_orders[base_asset].append(np.array([order.qty, order.price]))
            else:
                self.sell_orders[base_asset].append(np.array([order.qty, order.price]))

    def on_order_execution(self, order: Order) -> None:
        if jh.is_livetrading():
            return

        base_asset = jh.base_asset(order.symbol)

        if not order.reduce_only:
            if order.side == sides.BUY:
                # find and set order to [0, 0] (same as removing it)
                for index, item in enumerate(self.buy_orders[base_asset]):
                    if item[0] == order.qty and item[1] == order.price:
                        self.buy_orders[base_asset][index] = np.array([0, 0])
                        break
            else:
                # find and set order to [0, 0] (same as removing it)
                for index, item in enumerate(self.sell_orders[base_asset]):
                    if item[0] == order.qty and item[1] == order.price:
                        self.sell_orders[base_asset][index] = np.array([0, 0])
                        break

    def on_order_cancellation(self, order: Order) -> None:
        if jh.is_livetrading():
            return

        base_asset = jh.base_asset(order.symbol)

        self.available_assets[base_asset] -= order.qty
        # self.available_assets[quote_asset] += order.qty * order.price
        if not order.reduce_only:
            if order.side == sides.BUY:
                # find and set order to [0, 0] (same as removing it)
                for index, item in enumerate(self.buy_orders[base_asset]):
                    if item[0] == order.qty and item[1] == order.price:
                        self.buy_orders[base_asset][index] = np.array([0, 0])
                        break
            else:
                # find and set order to [0, 0] (same as removing it)
                for index, item in enumerate(self.sell_orders[base_asset]):
                    if item[0] == order.qty and item[1] == order.price:
                        self.sell_orders[base_asset][index] = np.array([0, 0])
                        break

    def update_from_stream(self, data: dict) -> None:
        """
        Used for updating the exchange from the WS stream (only for live trading)
        """
        if not jh.is_livetrading():
            raise Exception('This method is only for live trading')

        self._available_margin = data['available_margin']
        self._wallet_balance = data['wallet_balance']
        if self._started_balance == 0:
            self._started_balance = self._wallet_balance
