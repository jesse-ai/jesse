import jesse.helpers as jh
import jesse.services.logger as logger
from jesse.exceptions import NegativeBalance
from jesse.models import Order
from jesse.enums import sides, order_types
from jesse.libs import DynamicNumpyArray
import numpy as np
from jesse.services import selectors


class Exchange:
    name = ''
    fee_rate = None

    # current holding assets
    assets = {}
    # used for calculating available balance in margin mode:
    temp_reduced_amount = {}
    # current available assets (dynamically changes based on active orders)
    available_assets = {}
    # used for calculating final performance metrics
    starting_assets = {}

    buy_orders = {}
    sell_orders = {}

    def __init__(self, name: str, starting_assets: list, fee_rate: float, exchange_type: str, settlement_currency: str):
        self.name = name
        self.type = exchange_type.lower()

        for item in starting_assets:
            self.assets[item['asset']] = item['balance']
            self.buy_orders[item['asset']] = DynamicNumpyArray((10, 2))
            self.sell_orders[item['asset']] = DynamicNumpyArray((10, 2))
            self.temp_reduced_amount[item['asset']] = 0

        # margin only: make sure trading routes exist in starting_assets
        if self.type == 'margin':
            from jesse.routes import router
            for r in router.routes:
                base = jh.base_asset(r.symbol)
                if base not in self.assets:
                    self.assets[base] = 0
                if base not in self.buy_orders:
                    self.buy_orders[base] = DynamicNumpyArray((10, 2))
                if base not in self.sell_orders:
                    self.sell_orders[base] = DynamicNumpyArray((10, 2))
                if base not in self.temp_reduced_amount:
                    self.temp_reduced_amount[base] = 0

        self.starting_assets = self.assets.copy()
        self.available_assets = self.assets.copy()
        # in margin mode, start from 0 balance for self.available_assets
        # which acts as a temp variable
        if self.type == 'margin':
            for k in self.available_assets:
                self.available_assets[k] = 0
        self.fee_rate = fee_rate
        self.settlement_currency = settlement_currency.upper()

    def tradable_balance(self, symbol=''):
        if self.type == 'spot':
            if symbol == '':
                raise ValueError
            quote_asset = jh.quote_asset(symbol)
            return self.available_assets[quote_asset]
        else:
            temp_credit = self.assets[self.settlement_currency]
            # we need to consider buy and sell orders of ALL pairs
            # also, consider the value of all open positions
            for asset in self.assets:
                if asset == self.settlement_currency:
                    continue

                position = selectors.get_position(self.name, asset + self.settlement_currency)
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

    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    # MARGIN ONLY
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    def charge_fee(self, amount):
        if self.type == 'spot':
            return

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
        if self.type == 'spot':
            return

        new_balance = self.assets[self.settlement_currency] + realized_pnl
        logger.info('Added realized PNL of {}. Balance for {} on {} changed from {} to {}'.format(
            round(realized_pnl, 2),
            self.settlement_currency, self.name,
            round(self.assets[self.settlement_currency], 2),
            round(new_balance, 2),
        ))
        self.assets[self.settlement_currency] = new_balance

    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    # SPOT and a bit of MARGIN
    #
    # in margin, we only modify self.available_assets[base_asset]
    # which is used to detect whether or not the order reduce_only
    # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
    def on_order_submission(self, order: Order, skip_market_order=True):
        base_asset = jh.base_asset(order.symbol)
        quote_asset = jh.quote_asset(order.symbol)

        # skip market order at the time of submission because we don't have
        # the exact order.price. Instead, we call on_order_submission() one
        # more time at time of execution without "skip_market_order=False".
        if order.type == order_types.MARKET and skip_market_order:
            return

        # in margin, we only update available_asset's value which is used for detecting reduce_only orders
        if self.type == 'margin':
            self.available_assets[base_asset] += order.qty
            if order.side == sides.BUY:
                self.buy_orders[base_asset].append(np.array([order.qty, order.price]))
            else:
                self.sell_orders[base_asset].append(np.array([order.qty, order.price]))
            # self.available_assets[quote_asset] -= order.qty * order.price
            return

        # used for logging balance change
        temp_old_quote_available_asset = self.available_assets[quote_asset]
        temp_old_base_available_asset = self.available_assets[base_asset]

        if order.side == sides.BUY:
            quote_balance = self.available_assets[quote_asset]
            self.available_assets[quote_asset] -= (abs(order.qty) * order.price) * (1 + self.fee_rate)
            if self.available_assets[quote_asset] < 0:
                raise NegativeBalance(
                    "Balance cannot go below zero in spot market. Available capital at {} for {} is {} but you're trying to sell {}".format(
                        self.name, quote_asset, quote_balance, abs(order.qty * order.price)
                    )
                )
        # sell order
        else:
            base_balance = self.available_assets[base_asset]
            new_base_balance = base_balance + order.qty
            if new_base_balance < 0:
                raise NegativeBalance(
                    "Balance cannot go below zero in spot market. Available capital at {} for {} is {} but you're trying to sell {}".format(
                        self.name, base_asset, base_balance, abs(order.qty)
                    )
                )

            self.available_assets[base_asset] -= abs(order.qty)

        temp_new_quote_available_asset = self.available_assets[quote_asset]
        if jh.is_debuggable('balance_update') and temp_old_quote_available_asset != temp_new_quote_available_asset:
            logger.info(
                'Available balance for {} on {} changed from {} to {}'.format(
                    quote_asset, self.name,
                    round(temp_old_quote_available_asset, 2), round(temp_new_quote_available_asset, 2)
                )
            )
        temp_new_base_available_asset = self.available_assets[base_asset]
        if jh.is_debuggable('balance_update') and temp_old_base_available_asset != temp_new_base_available_asset:
            logger.info(
                'Available balance for {} on {} changed from {} to {}'.format(
                    base_asset, self.name,
                    round(temp_old_base_available_asset, 2), round(temp_new_base_available_asset, 2)
                )
            )

    def on_order_execution(self, order: Order):
        base_asset = jh.base_asset(order.symbol)
        quote_asset = jh.quote_asset(order.symbol)

        if order.type == order_types.MARKET:
            self.on_order_submission(order, skip_market_order=False)

        if self.type == 'margin':
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

        # used for logging balance change
        temp_old_quote_asset = self.assets[quote_asset]
        temp_old_quote_available_asset = self.available_assets[quote_asset]
        temp_old_base_asset = self.assets[base_asset]
        temp_old_base_available_asset = self.available_assets[base_asset]

        # works for both buy and sell orders (sell order's qty < 0)
        self.assets[base_asset] += order.qty

        if order.side == sides.BUY:
            self.available_assets[base_asset] += order.qty
            self.assets[quote_asset] -= (abs(order.qty) * order.price) * (1 + self.fee_rate)
        # sell order
        else:
            self.available_assets[quote_asset] += abs(order.qty) * order.price * (1 - self.fee_rate)
            self.assets[quote_asset] += abs(order.qty) * order.price * (1 - self.fee_rate)

        temp_new_quote_asset = self.assets[quote_asset]
        if jh.is_debuggable('balance_update') and temp_old_quote_asset != temp_new_quote_asset:
            logger.info(
                'Balance for {} on {} changed from {} to {}'.format(
                    quote_asset, self.name,
                    round(temp_old_quote_asset, 2), round(temp_new_quote_asset, 2)
                )
            )
        temp_new_quote_available_asset = self.available_assets[quote_asset]
        if jh.is_debuggable('balance_update') and temp_old_quote_available_asset != temp_new_quote_available_asset:
            logger.info(
                'Balance for {} on {} changed from {} to {}'.format(
                    quote_asset, self.name,
                    round(temp_old_quote_available_asset, 2), round(temp_new_quote_available_asset, 2)
                )
            )

        temp_new_base_asset = self.assets[base_asset]
        if jh.is_debuggable('balance_update') and temp_old_base_asset != temp_new_base_asset:
            logger.info(
                'Balance for {} on {} changed from {} to {}'.format(
                    base_asset, self.name,
                    round(temp_old_base_asset, 2), round(temp_new_base_asset, 2)
                )
            )
        temp_new_base_available_asset = self.available_assets[base_asset]
        if jh.is_debuggable('balance_update') and temp_old_base_available_asset != temp_new_base_available_asset:
            logger.info(
                'Balance for {} on {} changed from {} to {}'.format(
                    base_asset, self.name,
                    round(temp_old_base_available_asset, 2), round(temp_new_base_available_asset, 2)
                )
            )

    def on_order_cancellation(self, order: Order):
        base_asset = jh.base_asset(order.symbol)
        quote_asset = jh.quote_asset(order.symbol)

        # in margin, we only update available_asset's value which is used for detecting reduce_only orders
        if self.type == 'margin':
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

        # used for logging balance change
        temp_old_quote_available_asset = self.available_assets[quote_asset]
        temp_old_base_available_asset = self.available_assets[base_asset]

        if order.side == sides.BUY:
            self.available_assets[quote_asset] += (abs(order.qty) * order.price) * (1 + self.fee_rate)
        # sell order
        else:
            self.available_assets[base_asset] += abs(order.qty)

        temp_new_quote_available_asset = self.available_assets[quote_asset]
        if jh.is_debuggable('balance_update') and temp_old_quote_available_asset != temp_new_quote_available_asset:
            logger.info(
                'Available balance for {} on {} changed from {} to {}'.format(
                    quote_asset, self.name,
                    round(temp_old_quote_available_asset, 2), round(temp_new_quote_available_asset, 2)
                )
            )
        temp_new_base_available_asset = self.available_assets[base_asset]
        if jh.is_debuggable('balance_update') and temp_old_base_available_asset != temp_new_base_available_asset:
            logger.info(
                'Available balance for {} on {} changed from {} to {}'.format(
                    base_asset, self.name,
                    round(temp_old_base_available_asset, 2), round(temp_new_base_available_asset, 2)
                )
            )
