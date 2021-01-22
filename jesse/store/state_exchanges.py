from jesse.config import config
from jesse.models import SpotExchange, FuturesExchange


class ExchangesState:
    def __init__(self):
        self.storage = {}

        for name in config['app']['considering_exchanges']:
            starting_assets = config['env']['exchanges'][name]['assets']
            fee = config['env']['exchanges'][name]['fee']
            exchange_type = config['env']['exchanges'][name]['type']

            if exchange_type == 'spot':
                self.storage[name] = SpotExchange(name, starting_assets, fee)
            elif exchange_type == 'futures':
                self.storage[name] = FuturesExchange(name, starting_assets, fee, settlement_currency=config['env']['exchanges'][name]['settlement_currency'])
