import jesse.helpers as jh
from jesse.enums import sides
from jesse.exceptions import InsufficientBalance
from jesse.models import Order
from jesse.models.Exchange import Exchange
from jesse.enums import order_types
from jesse.utils import sum_floats, subtract_floats


class SpotExchange(Exchange):
    def __init__(self, name: str, starting_balance: float, fee_rate: float):
        super().__init__(name, starting_balance, fee_rate, 'spot')

        self.stop_orders_sum = {}
        self.limit_orders_sum = {}

        # # # # live-trading only # # # #
        self._started_balance = 0
        # # # # # # # # # # # # # # # # #

    @property
    def started_balance(self) -> float:
        if jh.is_livetrading():
            return self._started_balance

        return self.starting_assets[jh.app_currency()]

    @property
    def wallet_balance(self) -> float:
        return self.assets[self.settlement_currency]

    @property
    def available_margin(self) -> float:
        return self.wallet_balance

    def on_order_submission(self, order: Order) -> None:
        if jh.is_livetrading():
            return

        if order.side == sides.SELL:
            if order.type == order_types.STOP:
                self.stop_orders_sum[order.symbol] = sum_floats(self.stop_orders_sum.get(order.symbol, 0), abs(order.qty))
            elif order.type == order_types.LIMIT:
                self.limit_orders_sum[order.symbol] = sum_floats(self.limit_orders_sum.get(order.symbol, 0), abs(order.qty))

        base_asset = jh.base_asset(order.symbol)

        # buy order
        if order.side == sides.BUY:
            # cannot buy if we don't have enough balance (of the settlement currency)
            quote_balance = self.assets[self.settlement_currency]
            self.assets[self.settlement_currency] = subtract_floats(self.assets[self.settlement_currency], (abs(order.qty) * order.price))
            if self.assets[self.settlement_currency] < 0:
                raise InsufficientBalance(
                    f"Not enough balance. Available balance at {self.name} for {self.settlement_currency} is {quote_balance} but you're trying to spend {abs(order.qty * order.price)}"
                )
        # sell order
        else:
            # sell order's qty cannot be bigger than the amount of existing base asset
            base_balance = self.assets[base_asset]
            if order.type == order_types.MARKET:
                order_qty = sum_floats(abs(order.qty), self.limit_orders_sum.get(order.symbol, 0))
            elif order.type == order_types.STOP:
                order_qty = self.stop_orders_sum[order.symbol]
            elif order.type == order_types.LIMIT:
                order_qty = self.limit_orders_sum[order.symbol]
            else:
                raise Exception(f"Unknown order type {order.type}")
            # validate that the total selling amount is not bigger than the amount of the existing base asset
            if order_qty > base_balance:
                raise InsufficientBalance(
                    f"Not enough balance. Available balance at {self.name} for {base_asset} is {base_balance} but you're trying to sell {order_qty}"
                )

    def on_order_execution(self, order: Order) -> None:
        if jh.is_livetrading():
            return

        if order.side == sides.SELL:
            if order.type == order_types.STOP:
                self.stop_orders_sum[order.symbol] = subtract_floats(self.stop_orders_sum[order.symbol], abs(order.qty))
            elif order.type == order_types.LIMIT:
                self.limit_orders_sum[order.symbol] = subtract_floats(self.limit_orders_sum[order.symbol], abs(order.qty))

        base_asset = jh.base_asset(order.symbol)

        # buy order
        if order.side == sides.BUY:
            # asset's balance is increased by the amount of the order's qty after fees are deducted
            self.assets[base_asset] = sum_floats(self.assets[base_asset], abs(order.qty) * (1 - self.fee_rate))
        # sell order
        else:
            # settlement currency's balance is increased by the amount of the order's qty after fees are deducted
            self.assets[self.settlement_currency] = sum_floats(self.assets[self.settlement_currency], (abs(order.qty) * order.price) * (1 - self.fee_rate))
            # now reduce base asset's balance by the amount of the order's qty
            self.assets[base_asset] = subtract_floats(self.assets[base_asset], abs(order.qty))

    def on_order_cancellation(self, order: Order) -> None:
        if jh.is_livetrading():
            return

        if order.side == sides.SELL:
            if order.type == order_types.STOP:
                self.stop_orders_sum[order.symbol] = subtract_floats(self.stop_orders_sum[order.symbol], abs(order.qty))
            elif order.type == order_types.LIMIT:
                self.limit_orders_sum[order.symbol] = subtract_floats(self.limit_orders_sum[order.symbol], abs(order.qty))

        base_asset = jh.base_asset(order.symbol)

        # buy order
        if order.side == sides.BUY:
            self.assets[self.settlement_currency] = sum_floats(self.assets[self.settlement_currency], abs(order.qty) * order.price)
        # sell order
        else:
            self.assets[base_asset] = sum_floats(self.assets[base_asset], abs(order.qty))

    def update_from_stream(self, data: dict) -> None:
        """
        Used for updating the exchange from the WS stream (only for live trading)
        """
        if not jh.is_livetrading():
            raise Exception('This method is only for live trading')

        self.assets[self.settlement_currency] = data['balance']
        if self._started_balance == 0:
            self._started_balance = data['balance']
