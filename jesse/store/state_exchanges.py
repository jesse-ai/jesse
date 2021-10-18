import jesse.helpers as jh
from jesse.config import config
from jesse.exceptions import InvalidConfig
from jesse.models import SpotExchange, FuturesExchange
import pydash


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
                settlement_currency = jh.get_config(f'env.exchanges.{name}.settlement_currency')
                # dirty fix to get the settlement_currency right for none-USDT pairs
                settlement_asset_dict = pydash.find(starting_assets, lambda asset: asset['asset'] == settlement_currency)
                if settlement_asset_dict is None:
                    starting_assets[0]['asset'] = settlement_currency
                self.storage[name] = FuturesExchange(
                    name, starting_assets, fee,
                    settlement_currency=settlement_currency,
                    futures_leverage_mode=jh.get_config(f'env.exchanges.{name}.futures_leverage_mode'),
                    futures_leverage=jh.get_config(f'env.exchanges.{name}.futures_leverage'),
                )
            else:
                raise InvalidConfig(
                    'Value for exchange type in your config file in not valid. Supported values are "spot" and "futures"')
