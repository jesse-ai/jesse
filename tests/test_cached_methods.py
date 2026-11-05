from jesse.strategies import Strategy, cached


class CachedStrategy(Strategy):
    def __init__(self):
        super().__init__()
        self.price_now = 100
        self.calls = 0
        self.seen_in_check = []

    @cached
    def stretch(self):
        self.calls += 1
        return self.price_now

    def should_long(self) -> bool:
        return False

    def go_long(self):
        pass

    def before(self) -> None:
        pass

    def after(self) -> None:
        pass

    def update_chart(self) -> None:
        pass

    def _check(self) -> None:
        # read twice, as should_long() and go_long() would
        self.seen_in_check.append((self.stretch(), self.stretch()))

    # keep _execute() away from the candle store
    @property
    def close(self) -> float:
        return self.price_now

    @property
    def is_live(self) -> bool:
        return True


def test_values_are_cached_within_one_execution():
    strategy = CachedStrategy()

    strategy._execute()

    assert strategy.seen_in_check == [(100, 100)]
    assert strategy.calls == 1


def test_calls_outside_execution_compute_fresh_and_store_nothing():
    strategy = CachedStrategy()

    assert strategy.stretch() == 100
    strategy.price_now = 105
    assert strategy.stretch() == 105
    assert strategy.calls == 2
    assert all(m.cache_info().currsize == 0 for m in strategy._cached_methods.values())


def test_watch_list_between_candles_cannot_leak_into_the_next_execution():
    strategy = CachedStrategy()

    # the live dashboard reads the watch list on the forming candle...
    strategy.price_now = 101
    assert strategy.stretch() == 101

    # ...and the candle closes at a different price before the strategy executes
    strategy.price_now = 104
    strategy._execute()

    assert strategy.seen_in_check == [(104, 104)]


def test_a_stale_cache_is_cleared_when_execution_starts():
    strategy = CachedStrategy()

    # a value stored during execution that somehow survived to the next candle
    strategy._is_executing = True
    assert strategy.stretch() == 100
    strategy._is_executing = False

    strategy.price_now = 107
    strategy._execute()

    assert strategy.seen_in_check == [(107, 107)]


def test_signal_test_execution_also_starts_with_a_fresh_cache():
    strategy = CachedStrategy()
    strategy._is_executing = True
    strategy.stretch()
    strategy._is_executing = False
    strategy.price_now = 103

    strategy.should_long = lambda: strategy.stretch() == 103
    signal, _ = strategy._execute_for_signal_test()

    assert signal == 1
