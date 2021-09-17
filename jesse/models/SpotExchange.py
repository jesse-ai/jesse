import jesse.helpers as jh
import jesse.services.logger as logger
from jesse.enums import sides, order_types
from jesse.exceptions import NegativeBalance, InvalidConfig
from jesse.models import Order
from .Exchange import Exchange


class SpotExchange(Exchange):
    def add_realized_pnl(self, realized_pnl: float) -> None:
        pass

    def charge_fee(self, amount: float) -> None:
        pass

    # current holding assets
    assets = {}
    # current available assets (dynamically changes based on active orders)
    available_assets = {}

    def __init__(self, name: str, starting_assets: list, fee_rate: float):
        super().__init__(name, starting_assets, fee_rate, 'spot')

        from jesse.routes import router
        # check if base assets are configured
        for route in router.routes:
            base_asset = jh.base_asset(route.symbol)
            if base_asset not in self.available_assets:
                raise InvalidConfig(
                    f"Jesse needs to know the balance of your base asset for spot mode. Please add {base_asset} to your exchanges assets config.")

    def wallet_balance(self, symbol: str = '') -> float:
        if symbol == '':
            raise ValueError
        quote_asset = jh.quote_asset(symbol)
        return self.assets[quote_asset]

    def available_margin(self, symbol: str = '') -> float:
        return self.wallet_balance(symbol)

    def on_order_submission(self, order: Order, skip_market_order=True):
        base_asset = jh.base_asset(order.symbol)
        quote_asset = jh.quote_asset(order.symbol)

        # skip market order at the time of submission because we don't have
        # the exact order.price. Instead, we call on_order_submission() one
        # more time at time of execution without "skip_market_order=False".
        if order.type == order_types.MARKET and skip_market_order:
            return

        # used for logging balance change
        temp_old_quote_available_asset = self.available_assets[quote_asset]
        temp_old_base_available_asset = self.available_assets[base_asset]

        if order.side == sides.BUY:
            quote_balance = self.available_assets[quote_asset]
            self.available_assets[quote_asset] -= (abs(order.qty) * order.price) * (1 + self.fee_rate)
            if self.available_assets[quote_asset] < 0:
                raise NegativeBalance(
                    f"Balance cannot go below zero in spot market. Available capital at {self.name} for {quote_asset} is {quote_balance} but you're trying to sell {abs(order.qty * order.price)}"
                )
        # sell order
        else:
            base_balance = self.available_assets[base_asset]
            new_base_balance = base_balance + order.qty
            if new_base_balance < 0:
                raise NegativeBalance(
                    f"Balance cannot go below zero in spot market. Available capital at {self.name} for {base_asset} is {base_balance} but you're trying to sell {abs(order.qty)}"
                )

            self.available_assets[base_asset] -= abs(order.qty)

        temp_new_quote_available_asset = self.available_assets[quote_asset]
        if jh.is_debuggable('balance_update') and temp_old_quote_available_asset != temp_new_quote_available_asset:
            logger.info(
                f'Available balance for {quote_asset} on {self.name} changed from {round(temp_old_quote_available_asset, 2)} to {round(temp_new_quote_available_asset, 2)}'
            )
        temp_new_base_available_asset = self.available_assets[base_asset]
        if jh.is_debuggable('balance_update') and temp_old_base_available_asset != temp_new_base_available_asset:
            logger.info(
                f'Available balance for {base_asset} on {self.name} changed from {round(temp_old_base_available_asset, 2)} to {round(temp_new_base_available_asset, 2)}'
            )

    def on_order_execution(self, order: Order) -> None:
        base_asset = jh.base_asset(order.symbol)
        quote_asset = jh.quote_asset(order.symbol)

        if order.type == order_types.MARKET:
            self.on_order_submission(order, skip_market_order=False)

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
                f'Balance for {quote_asset} on {self.name} changed from {round(temp_old_quote_asset, 2)} to {round(temp_new_quote_asset, 2)}'
            )
        temp_new_quote_available_asset = self.available_assets[quote_asset]
        if jh.is_debuggable('balance_update') and temp_old_quote_available_asset != temp_new_quote_available_asset:
            logger.info(
                f'Balance for {quote_asset} on {self.name} changed from {round(temp_old_quote_available_asset, 2)} to {round(temp_new_quote_available_asset, 2)}'
            )

        temp_new_base_asset = self.assets[base_asset]
        if jh.is_debuggable('balance_update') and temp_old_base_asset != temp_new_base_asset:
            logger.info(
                f'Balance for {base_asset} on {self.name} changed from {round(temp_old_base_asset, 2)} to {round(temp_new_base_asset, 2)}'
            )
        temp_new_base_available_asset = self.available_assets[base_asset]
        if jh.is_debuggable('balance_update') and temp_old_base_available_asset != temp_new_base_available_asset:
            logger.info(
                f'Balance for {base_asset} on {self.name} changed from {round(temp_old_base_available_asset, 2)} to {round(temp_new_base_available_asset, 2)}'
            )

    def on_order_cancellation(self, order: Order) -> None:
        base_asset = jh.base_asset(order.symbol)
        quote_asset = jh.quote_asset(order.symbol)

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
                f'Available balance for {quote_asset} on {self.name} changed from {round(temp_old_quote_available_asset, 2)} to {round(temp_new_quote_available_asset, 2)}'
            )
        temp_new_base_available_asset = self.available_assets[base_asset]
        if jh.is_debuggable('balance_update') and temp_old_base_available_asset != temp_new_base_available_asset:
            logger.info(
                f'Available balance for {base_asset} on {self.name} changed from {round(temp_old_base_available_asset, 2)} to {round(temp_new_base_available_asset, 2)}'
            )
