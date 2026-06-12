from jesse.strategies import Strategy


class TestBaseAndQuoteAssetProperties(Strategy):
    def before(self) -> None:
        if self.index == 0:
            assert self.base_asset == 'BTC'
            assert self.quote_asset == 'USDT'

    def should_long(self) -> bool:
        return False

    def go_long(self):
        pass

    def should_cancel_entry(self) -> bool:
        return False
