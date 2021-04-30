from abc import ABC, abstractmethod

from jesse.models import Order


class Exchange(ABC):
    name = ''
    fee_rate = None

    # current holding assets
    assets = {}
    # used for calculating available balance in futures mode:
    temp_reduced_amount = {}
    # current available assets (dynamically changes based on active orders)
    available_assets = {}
    # used for calculating final performance metrics
    starting_assets = {}

    # some exchanges might require even further info
    vars = {}

    def __init__(self, name: str, starting_assets: list, fee_rate: float, exchange_type: str):
        self.name = name
        self.type = exchange_type.lower()

        for item in starting_assets:
            self.assets[item['asset']] = item['balance']
            self.temp_reduced_amount[item['asset']] = 0

        self.starting_assets = self.assets.copy()
        self.available_assets = self.assets.copy()
        self.fee_rate = fee_rate

    @abstractmethod
    def wallet_balance(self, symbol=''):
        pass

    @abstractmethod
    def available_margin(self, symbol=''):
        pass

    @abstractmethod
    def on_order_submission(self, order: Order, skip_market_order=True):
        pass

    @abstractmethod
    def on_order_execution(self, order: Order):
        pass

    @abstractmethod
    def on_order_cancellation(self, order: Order):
        pass

    @abstractmethod
    def add_realized_pnl(self, realized_pnl: float):
        pass

    @abstractmethod
    def charge_fee(self, amount):
        pass
