from abc import ABC, abstractmethod


class CandleExchange(ABC):
    def __init__(self, name, count, sleep_time):
        self.name = name
        self.count = count
        self.sleep_time = sleep_time
        self.backup_exchange: CandleExchange = None

    @abstractmethod
    def init_backup_exchange(self):
        pass

    @abstractmethod
    def fetch(self, symbol, start_timestamp):
        pass

    @abstractmethod
    def get_starting_time(self, symbol) -> int:
        pass
