from jesse.strategies import Strategy


class TestRuleSignificanceAlignment(Strategy):
    """Alternate direction so tests can distinguish current and next-bar returns."""

    def should_long(self) -> bool:
        return self.index % 2 == 0

    def should_short(self) -> bool:
        return self.index % 2 == 1

    def go_long(self) -> None:
        pass

    def go_short(self) -> None:
        pass
