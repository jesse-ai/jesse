import jesse.helpers as jh
import jesse.services.logger as logger
from jesse.exceptions import NegativeBalance


class Exchange:
    name = ''
    starting_balance = 0
    balance = 0
    fee_rate = None

    def __init__(self, name, starting_balance, fee_rate):
        self.name = name
        self.starting_balance = starting_balance
        self.balance = starting_balance
        self.fee_rate = fee_rate

    def increase_balance(self, position, delta_balance, is_refund=False):
        old_balance = self.balance

        if is_refund:
            self.balance += abs(delta_balance) * (1 + self.fee_rate)
        else:
            self.balance += abs(delta_balance) * (1 - self.fee_rate)

        new_balance = self.balance

        if jh.is_debuggable('balance_update'):
            logger.info('balance changed from {} to {}'.format(old_balance, new_balance))

    def decrease_balance(self, position, delta_balance):
        old_balance = self.balance

        to_spend = abs(delta_balance) * (1 + self.fee_rate)
        
        self.balance -= to_spend

        new_balance = self.balance

        if new_balance < 0:
            raise NegativeBalance(
                "Balance cannot go below zero. Available capital at {} is {} but you're trying to spend {}".format(
                    self.name, old_balance, to_spend
                )
            )

        if jh.is_debuggable('balance_update'):
            logger.info('balance changed from {} to {}'.format(old_balance, new_balance))
