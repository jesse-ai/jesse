from typing import Union, ValuesView

from jesse.config import config
from jesse.models import SpotExchange, FuturesExchange
from jesse.exceptions import InvalidConfig
import jesse.helpers as jh


class ExchangesState:
    def __init__(self) -> None:
        self.storage = {}

        for name in config['app']['considering_exchanges']:
            starting_assets = config['env']['exchanges'][name]['assets']
            fee = config['env']['exchanges'][name]['fee']
            exchange_type = config['env']['exchanges'][name]['type']

            if exchange_type == 'spot':
                self.storage[name] = SpotExchange(name, starting_assets, fee)
            elif exchange_type == 'futures':
                self.storage[name] = FuturesExchange(
                    name, starting_assets, fee,
                    settlement_currency=jh.get_config('env.exchanges.{}.settlement_currency'.format(name)),
                    futures_leverage_mode=jh.get_config('env.exchanges.{}.futures_leverage_mode'.format(name)),
                    futures_leverage=jh.get_config('env.exchanges.{}.futures_leverage'.format(name)),
                )
            else:
                raise InvalidConfig('Value for exchange type in your config file in not valid. Supported values are "spot" and "futures"')
