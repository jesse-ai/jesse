import jesse.helpers as jh
import jesse.services.logger as logger
from jesse.exceptions import NegativeBalance, InsufficientMargin
from jesse.models import Order
from jesse.enums import sides, order_types
from jesse.libs import DynamicNumpyArray
import numpy as np
from jesse.services import selectors
from .Exchange import Exchange


class FuturesExchange(Exchange):
    # current holding assets
    assets = {}
    # current available assets (dynamically changes based on active orders)
    available_assets = {}

    buy_orders = {}
    sell_orders = {}

    def __init__(
            self,
            name: str,
            starting_assets: list,
            fee_rate: float,
            settlement_currency: str,
            futures_leverage_mode: str,
            futures_leverage: int
    ):
        super().__init__(name, starting_assets, fee_rate, 'futures')

        self.futures_leverage_mode = futures_leverage_mode
        self.futures_leverage = futures_leverage

        for item in starting_assets:
            self.buy_orders[item['asset']] = DynamicNumpyArray((10, 2))
            self.sell_orders[item['asset']] = DynamicNumpyArray((10, 2))

        # make sure trading routes exist in starting_assets
        from jesse.routes import router
        for r in router.routes:
            base = jh.base_asset(r.symbol)
            if base not in self.assets:
                self.assets[base] = 0
            if base not in self.buy_orders:
                self.buy_orders[base] = DynamicNumpyArray((10, 2))
            if base not in self.sell_orders:
                self.sell_orders[base] = DynamicNumpyArray((10, 2))

        self.starting_assets = self.assets.copy()
        self.available_assets = self.assets.copy()

        # start from 0 balance for self.available_assets which acts as a temp variable
        for k in self.available_assets:
            self.available_assets[k] = 0

        self.settlement_currency = settlement_currency.upper()

    def wallet_balance(self, symbol=''):
        return self.assets[self.settlement_currency]

    def available_margin(self, symbol=''):
        temp_credit = self.assets[self.settlement_currency] * self.futures_leverage
        # we need to consider buy and sell orders of ALL pairs
        # also, consider the value of all open positions
        for asset in self.assets:
            if asset == self.settlement_currency:
                continue

            position = selectors.get_position(self.name, asset + "-" + self.settlement_currency)
            if position is None:
                continue

            if position.is_open:
                # add unrealized PNL
                temp_credit += position.pnl

            # subtract worst scenario orders' used margin
            sum_buy_orders = (self.buy_orders[asset][:][:, 0] * self.buy_orders[asset][:][:, 1]).sum()
            sum_sell_orders = (self.sell_orders[asset][:][:, 0] * self.sell_orders[asset][:][:, 1]).sum()
            if position.is_open:
                if position.type == 'long':
                    sum_buy_orders += position.value
                else:
                    sum_sell_orders -= abs(position.value)
            temp_credit -= max(abs(sum_buy_orders), abs(sum_sell_orders))

        return temp_credit

    def charge_fee(self, amount):
        fee_amount = abs(amount) * self.fee_rate
        new_balance = self.assets[self.settlement_currency] - fee_amount
        logger.info(
            'Charged {} as fee. Balance for {} on {} changed from {} to {}'.format(
                round(fee_amount, 2), self.settlement_currency, self.name,
                round(self.assets[self.settlement_currency], 2),
                round(new_balance, 2),
            )
        )
        self.assets[self.settlement_currency] = new_balance

    def add_realized_pnl(self, realized_pnl: float):
        new_balance = self.assets[self.settlement_currency] + realized_pnl
        logger.info('Added realized PNL of {}. Balance for {} on {} changed from {} to {}'.format(
            round(realized_pnl, 2),
            self.settlement_currency, self.name,
            round(self.assets[self.settlement_currency], 2),
            round(new_balance, 2),
        ))
        self.assets[self.settlement_currency] = new_balance

    def on_order_submission(self, order: Order, skip_market_order=True):
        base_asset = jh.base_asset(order.symbol)

        # make sure we don't spend more than we're allowed considering current allowed leverage
        if order.type != order_types.MARKET or skip_market_order:
            if not order.is_reduce_only:
                order_size = abs(order.qty * order.price)
                remaining_margin = self.available_margin()
                if order_size > remaining_margin:
                    raise InsufficientMargin('You cannot submit an order for ${} when your margin balance is ${}'.format(
                        round(order_size), round(remaining_margin)
                    ))

        # skip market order at the time of submission because we don't have
        # the exact order.price. Instead, we call on_order_submission() one
        # more time at time of execution without "skip_market_order=False".
        if order.type == order_types.MARKET and skip_market_order:
            return

        self.available_assets[base_asset] += order.qty
        if order.side == sides.BUY:
            self.buy_orders[base_asset].append(np.array([order.qty, order.price]))
        else:
            self.sell_orders[base_asset].append(np.array([order.qty, order.price]))

    def on_order_execution(self, order: Order):
        base_asset = jh.base_asset(order.symbol)

        if order.type == order_types.MARKET:
            self.on_order_submission(order, skip_market_order=False)

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
        return

    def on_order_cancellation(self, order: Order):
        base_asset = jh.base_asset(order.symbol)

        self.available_assets[base_asset] -= order.qty
        # self.available_assets[quote_asset] += order.qty * order.price
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
        return