from jesse.strategies import Strategy
from jesse import utils
import jesse.indicators as ta


class ExampleStrategy(Strategy):
    def should_long(self) -> bool:
        """

        :return:
        """
        return False

    def should_short(self) -> bool:
        """

        :return:
        """
        return False

    def should_cancel(self) -> bool:
        """

        :return:
        """
        return True

    def go_long(self):
        """

        """
        pass

    def go_short(self):
        """

        """
        pass
