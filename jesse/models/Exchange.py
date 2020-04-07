import jesse.helpers as jh
import jesse.services.logger as logger


class Exchange:
    name = ''
    starting_balance = 0
    balance = 0
    fee = None

    def __init__(self, name, starting_balance, fee):
        self.name = name
        self.starting_balance = starting_balance
        self.balance = starting_balance
        self.fee = fee

    def increase_balance(self, position, balance, is_refund=False):
        old_balance = self.balance
        if is_refund:
            self.balance += abs(balance) * (1 + self.fee)
        else:
            self.balance += abs(balance) * (1 - self.fee)
        new_balance = self.balance

        if jh.is_debuggable('balance_update'):
            logger.info('balance changed from {} to {}'.format(old_balance, new_balance))

    def decrease_balance(self, position, balance):
        old_balance = self.balance

        self.balance -= abs(balance) * (1 + self.fee)

        new_balance = self.balance

        if jh.is_debuggable('balance_update'):
            logger.info('balance changed from {} to {}'.format(old_balance, new_balance))
