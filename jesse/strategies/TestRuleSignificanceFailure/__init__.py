from jesse.strategies import Strategy


class TestRuleSignificanceFailure(Strategy):
    """Fail after initialization so research-runtime cleanup can be verified."""

    def before(self) -> None:
        if self.index == 5:
            raise RuntimeError('intentional significance strategy failure')

    def should_long(self) -> bool:
        return False

    def should_short(self) -> bool:
        return False

    def go_long(self) -> None:
        pass

    def go_short(self) -> None:
        pass
