from abc import ABC, abstractmethod
from jesse.models import Order
from jesse.services import selectors
import jesse.helpers as jh
from jesse.libs import DynamicNumpyArray
from jesse.info import exchange_info

class Exchange(ABC):
    def __init__(self, name: str, starting_balance: float, fee_rate: float, exchange_type: str):
        # currently holding assets
        self.assets = {}
        # used for calculating available balance in futures mode:
        self.temp_reduced_amount = {}
        # used for calculating final performance metrics
        self.starting_assets = {}
        # current available assets (dynamically changes based on active orders)
        self.available_assets = {}
        self.fee_rate = fee_rate
        # some exchanges might require even further info
        self.vars = {}

        self.buy_orders = {}
        self.sell_orders = {}

        self.name = name
        self.type = exchange_type.lower()

        # in running session's quote currency
        self.starting_balance = starting_balance

        all_trading_routes = selectors.get_all_trading_routes()
        first_route = all_trading_routes[0]
        # check the settlement_currency is in the exchange info with name equal to the exchange name
        if self.name in exchange_info and 'settlement_currency' in exchange_info[self.name]:
            self.settlement_currency = exchange_info[self.name]['settlement_currency']
        else:
            self.settlement_currency = jh.quote_asset(first_route.symbol)

        # initiate dict keys for trading assets
        for r in all_trading_routes:
            base_asset = jh.base_asset(r.symbol)
            self.buy_orders[base_asset] = DynamicNumpyArray((10, 2))
            self.sell_orders[base_asset] = DynamicNumpyArray((10, 2))
            self.assets[base_asset] = 0.0
            self.assets[self.settlement_currency] = starting_balance
            self.temp_reduced_amount[base_asset] = 0.0
            self.temp_reduced_amount[self.settlement_currency] = 0.0
            self.starting_assets[base_asset] = 0.0
            self.starting_assets[self.settlement_currency] = starting_balance
            self.available_assets[base_asset] = 0.0
            self.available_assets[self.settlement_currency] = starting_balance

    @property
    @abstractmethod
    def wallet_balance(self) -> float:
        pass

    @property
    @abstractmethod
    def available_margin(self) -> float:
        pass

    @abstractmethod
    def on_order_submission(self, order: Order) -> None:
        pass

    @abstractmethod
    def on_order_execution(self, order: Order) -> None:
        pass

    @abstractmethod
    def on_order_cancellation(self, order: Order) -> None:
        pass
