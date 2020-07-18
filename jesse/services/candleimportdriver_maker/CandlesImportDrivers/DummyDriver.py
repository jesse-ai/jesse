
import numpy as np
from jesse.interface import CandleExchange


class DummyDriver(CandleExchange):
    """
    """

    def __init__(self):
        super().__init__("DummyDriver", 10, 0)

    def init_backup_exchange(self):
        """
        """
        self.backup_exchange = None

    def get_starting_time(self, symbol) -> int:
        """
        :param symbol:
        :return:
        """
        return 0

    def fetch(self, symbol, start_timestamp) -> np.ndarray:
        """
        """
        return np.ndarray()
