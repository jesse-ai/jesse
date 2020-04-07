from jesse.config import config
from jesse.models import Exchange


class ExchangesState:
    def __init__(self):
        self.storage = {}

        for name in config['app']['considering_exchanges']:
            starting_balance = config['env']['exchanges'][name]['starting_balance']
            fee = config['env']['exchanges'][name]['fee']
            self.storage[name] = Exchange(name, starting_balance, fee)
