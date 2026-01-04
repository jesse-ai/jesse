from jesse.config import config
from jesse.models import Position
from jesse.store import store
from jesse.services import selectors
import jesse.helpers as jh


def initialize_positions_state() -> None:
    for exchange in config['app']['trading_exchanges']:
        for symbol in config['app']['trading_symbols']:
            key: str = f'{exchange}-{symbol}'
            store.positions.storage[key] = create_position(exchange, symbol)


def create_position(exchange_name: str, symbol: str, attributes: dict = None) -> Position:
    p = Position(attributes)
    if p.id is None:
        p.id = jh.generate_unique_id()  
    p.exchange_name = exchange_name
    p.exchange = selectors.get_exchange(exchange_name)
    p.symbol = symbol
    return p
