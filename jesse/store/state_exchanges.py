import jesse.helpers as jh
from jesse.config import config
from jesse.exceptions import InvalidConfig
from jesse.models import SpotExchange, FuturesExchange


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
                    settlement_currency=jh.get_config(f'env.exchanges.{name}.settlement_currency'),
                    futures_leverage_mode=jh.get_config(f'env.exchanges.{name}.futures_leverage_mode'),
                    futures_leverage=jh.get_config(f'env.exchanges.{name}.futures_leverage'),
                )
            else:
                raise InvalidConfig(
                    'Value for exchange type in your config file in not valid. Supported values are "spot" and "futures"')
