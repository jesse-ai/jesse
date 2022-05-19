import jesse.helpers as jh
from jesse.enums import sides
from jesse.exceptions import InsufficientBalance
from jesse.models import Order
from jesse.models.Exchange import Exchange


class SpotExchange(Exchange):
    def __init__(self, name: str, starting_balance: float, fee_rate: float):
        super().__init__(name, starting_balance, fee_rate, 'spot')

        jh.dump(self.type)

    @property
    def wallet_balance(self) -> float:
        return self.assets[self.settlement_currency]

    @property
    def available_margin(self) -> float:
        return self.wallet_balance

    def on_order_submission(self, order: Order) -> None:
        if jh.is_livetrading():
            return

        base_asset = jh.base_asset(order.symbol)

        # buy order
        if order.side == sides.BUY:
            # cannot buy if we don't have enough balance (of the settlement currency)
            quote_balance = self.assets[self.settlement_currency]
            self.assets[self.settlement_currency] -= (abs(order.qty) * order.price) * (1 + self.fee_rate)
            if self.assets[self.settlement_currency] < 0:
                raise InsufficientBalance(
                    f"Not enough balance. Available balance at {self.name} for {self.settlement_currency} is {quote_balance} but you're trying to spend {abs(order.qty * order.price)}"
                )
        # sell order
        else:
            # sell order's qty cannot be bigger than the amount of existing base asset
            base_balance = self.assets[base_asset]
            jh.dump(order.to_dict, self.assets)
            if abs(order.qty) > base_balance:
                raise InsufficientBalance(
                    f"Not enough balance. Available balance at {self.name} for {base_asset} is {base_balance} but you're trying to sell {abs(order.qty)}"
                )
            self.assets[base_asset] -= abs(order.qty)

    def on_order_execution(self, order: Order) -> None:
        if jh.is_livetrading():
            return

        base_asset = jh.base_asset(order.symbol)

        # buy order
        if order.side == sides.BUY:
            # asset's balance is increased by the amount of the order's qty after fees are deducted
            self.assets[base_asset] += abs(order.qty) * (1 - self.fee_rate)
        # sell order
        else:
            # settlement currency's balance is increased by the amount of the order's qty after fees are deducted
            self.assets[self.settlement_currency] += abs(order.qty) * order.price * (1 - self.fee_rate)

    def on_order_cancellation(self, order: Order) -> None:
        if jh.is_livetrading():
            return

        base_asset = jh.base_asset(order.symbol)

        # buy order
        if order.side == sides.BUY:
            self.assets[self.settlement_currency] += abs(order.qty) * order.price * (1 + self.fee_rate)
        # sell order
        else:
            self.assets[base_asset] += abs(order.qty)
