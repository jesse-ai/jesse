from jesse.config import config
from jesse.models import Position


class PositionsState:
    """

    """
    def __init__(self):
        self.storage = {}

        for exchange in config['app']['trading_exchanges']:
            for symbol in config['app']['trading_symbols']:
                key = '{}-{}'.format(exchange, symbol)
                self.storage[key] = Position(exchange, symbol)

    def count_open_positions(self):
        c = 0
        for key in self.storage:
            p = self.storage[key]
            if p.is_open:
                c += 1
        return c
