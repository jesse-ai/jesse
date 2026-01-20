from jesse.config import config
from jesse.exceptions import InvalidConfig
from jesse.models import SpotExchange, FuturesExchange, Exchange
from jesse.modes.utils import get_exchange_type
from jesse.store import store


def initialize_exchanges_state() -> None:
    for name in config['app']['considering_exchanges']:
        starting_assets = config['env']['exchanges'][name]['balance']
        fee = config['env']['exchanges'][name]['fee']
        exchange_type = get_exchange_type(name)

        if exchange_type == 'spot':
            store.exchanges.storage[name] = SpotExchange(name, starting_assets, fee)
        elif exchange_type == 'futures':
            store.exchanges.storage[name] = FuturesExchange(
                name, starting_assets, fee,
                futures_leverage_mode=config['env']['exchanges'][name]['futures_leverage_mode'],
                futures_leverage=config['env']['exchanges'][name]['futures_leverage'],
            )
        else:
            raise InvalidConfig(
                f'Value for exchange type in your config file in not valid. Supported values are "spot" and "futures". Your value is "{exchange_type}"'
            )