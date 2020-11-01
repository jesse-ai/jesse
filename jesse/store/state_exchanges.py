from jesse.config import config
from jesse.models import Exchange


class ExchangesState:
    def __init__(self):
        self.storage = {}

        for name in config['app']['considering_exchanges']:
            starting_assets = config['env']['exchanges'][name]['assets']
            fee = config['env']['exchanges'][name]['fee']
            exchange_type = config['env']['exchanges'][name]['type']
            settlement_currency = config['env']['exchanges'][name]['settlement_currency']
            self.storage[name] = Exchange(name, starting_assets, fee, exchange_type, settlement_currency)
