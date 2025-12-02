from jesse.config import config
from jesse.models import Position
from jesse.store import store


def initialize_positions_state() -> None:
    for exchange in config['app']['trading_exchanges']:
        for symbol in config['app']['trading_symbols']:
            key: str = f'{exchange}-{symbol}'
            store.positions.storage[key] = Position(exchange, symbol)
