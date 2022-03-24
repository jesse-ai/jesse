from abc import ABC, abstractmethod
from typing import Union
from jesse.models import Order

class Exchange(ABC):
    """
    The interface that every Exchange driver has to implement
    """

    @abstractmethod
    def market_order(self, symbol: str, qty: float, current_price: float, side: str, reduce_only: bool) -> Order:
        pass

    @abstractmethod
    def limit_order(self, symbol: str, qty: float, price: float, side: str, reduce_only: bool) -> Order:
        pass

    @abstractmethod
    def stop_order(self, symbol: str, qty: float, price: float, side: str, reduce_only: bool) -> Order:
        pass

    @abstractmethod
    def cancel_all_orders(self, symbol: str) -> None:
        pass

    @abstractmethod
    def cancel_order(self, symbol: str, order_id: str) -> None:
        pass

    @abstractmethod
    def _fetch_precisions(self) -> None:
        pass
