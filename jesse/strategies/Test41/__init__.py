from jesse.services import logger
from jesse.strategies import Strategy


# test_end
class Test41(Strategy):
    def should_long(self) -> bool:
        return self.index == 0

    def should_short(self) -> bool:
        return False

    def go_long(self):
        qty = 1
        self.buy = qty, 2

    def go_short(self):
        pass

    def should_cancel(self):
        return False

    def terminate(self):
        # log, so we can check this block was executed in the first place
        logger.info('executed terminate successfully')

        # assert open position
        assert self.position.is_open
        assert self.position.pnl == 97

        # close it manually
        self.liquidate()
