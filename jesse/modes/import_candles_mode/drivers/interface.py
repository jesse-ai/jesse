from abc import ABC, abstractmethod


class CandleExchange(ABC):
    def __init__(self, name: str, count: int, rate_limit_per_second: float, backup_exchange_class):
        self.name = name
        self.count = count
        self.sleep_time = 1 / rate_limit_per_second
        self._backup_exchange_class = backup_exchange_class
        self._backup_exchange = None

    @property
    def backup_exchange(self):
        if self._backup_exchange_class is None:
            return None

        if self._backup_exchange is None:
            self._backup_exchange = self._backup_exchange_class()

        return self._backup_exchange

    @abstractmethod
    def fetch(self, symbol: str, start_timestamp: int) -> list:
        pass

    @abstractmethod
    def get_starting_time(self, symbol: str) -> int:
        pass
