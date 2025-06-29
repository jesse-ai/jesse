from jesse.strategies import Strategy


class TestCurrentRouteIndex2(Strategy):
    def before(self) -> None:
        if self.index == 0 or self.index == 10:
            assert self.current_route_index == 1

    def should_long(self):
        return False

    def go_long(self):
        pass

    def should_cancel_entry(self):
        return False
