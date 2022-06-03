import jesse.helpers as jh
from jesse.config import config
from jesse.exceptions import InvalidConfig
from jesse.models import SpotExchange, FuturesExchange
from jesse.modes.utils import get_exchange_type


class ExchangesState:
    def __init__(self) -> None:
        self.storage = {}

        for name in config['app']['considering_exchanges']:
            starting_assets = config['env']['exchanges'][name]['balance']
            fee = config['env']['exchanges'][name]['fee']
            exchange_type = get_exchange_type(name)

            if exchange_type == 'spot':
                self.storage[name] = SpotExchange(name, starting_assets, fee)
            elif exchange_type == 'futures':
                self.storage[name] = FuturesExchange(
                    name, starting_assets, fee,
                    futures_leverage_mode=jh.get_config(f'env.exchanges.{name}.futures_leverage_mode'),
                    futures_leverage=jh.get_config(f'env.exchanges.{name}.futures_leverage'),
                )
            else:
                raise InvalidConfig(
                    f'Value for exchange type in your config file in not valid. Supported values are "spot" and "futures". Your value is "{exchange_type}"'
                )
