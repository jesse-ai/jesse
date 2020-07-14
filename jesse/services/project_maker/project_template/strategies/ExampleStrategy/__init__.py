from jesse.strategies import Strategy


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
        return False

    def go_long(self):
        """

        """
        pass

    def go_short(self):
        """

        """
        pass
