from types import SimpleNamespace

import pytest

import jesse.helpers as jh
from jesse.enums import exchanges
from jesse.routes import router
from jesse.services import exchange_service, position_service
from jesse.store import store
from jesse.strategies import Strategy
from jesse.testing_utils import set_up as configure_test


class FakeStrategy:
    """The parts of a strategy _on_updated_position needs, recording the events it fires."""

    def __init__(self, position) -> None:
        self.position = position
        self.exchange = position.exchange_name
        self.symbol = position.symbol
        self.events = []
        self._is_handling_updated_order = False
        self._position_qty_at_last_event = None

    def _handle_executed_order_for_chart(self, order) -> None:
        pass

    def _on_open_position(self, order) -> None:
        self.events.append('open')

    def _on_close_position(self, order) -> None:
        self.events.append('close')

    def _on_increased_position(self, order) -> None:
        self.events.append('increased')

    def _on_reduced_position(self, order) -> None:
        self.events.append('reduced')

    def fill(self) -> None:
        Strategy._on_updated_position(self, SimpleNamespace())


def _stream(position, qty: float) -> None:
    position_service.update_from_stream(position, {
        'qty': qty, 'entry_price': 100, 'liquidation_price': None,
    }, is_initial=False)


@pytest.fixture
def strategy(monkeypatch):
    configure_test()
    router.initiate([
        {'exchange': exchanges.SANDBOX, 'symbol': 'BTC-USDT', 'timeframe': '1m', 'strategy': 'TestVanillaStrategy'}
    ])
    store.reset()
    exchange_service.initialize_exchanges_state()
    monkeypatch.setattr(jh, 'is_livetrading', lambda: True)
    monkeypatch.setattr(position_service, '_open', lambda *args, **kwargs: None)

    position = position_service.create_position(exchanges.SANDBOX, 'BTC-USDT', {
        'entry_price': 100, 'current_price': 100, 'qty': 0,
    })
    fake = FakeStrategy(position)
    position.strategy = fake
    return fake


def test_a_fill_the_position_already_reflects_fires_no_second_event(strategy):
    _stream(strategy.position, 2)

    strategy.fill()
    strategy.fill()
    strategy.fill()

    assert strategy.events == ['open']


def test_every_size_change_fires_its_own_event(strategy):
    _stream(strategy.position, 1)
    strategy.fill()
    _stream(strategy.position, 2)
    strategy.fill()
    _stream(strategy.position, 1)
    strategy.fill()
    _stream(strategy.position, 0)
    strategy.fill()

    assert strategy.events == ['open', 'increased', 'reduced', 'close']


def test_a_resent_closing_fill_fires_no_second_close(strategy):
    _stream(strategy.position, 1)
    strategy.fill()
    _stream(strategy.position, 0)
    strategy.fill()
    strategy.fill()

    assert strategy.events == ['open', 'close']


def test_reentry_at_the_same_size_opens_after_a_close_no_fill_reported(strategy):
    # regression: the closing fill never reached the strategy (a liquidation or a lost stream
    # message), so a new position of the same size looked like a repeat of the old one and
    # on_open_position, which sets its stop-loss and take-profit, never ran.
    _stream(strategy.position, 1)
    strategy.fill()

    _stream(strategy.position, 0)
    _stream(strategy.position, 1)
    strategy.fill()

    assert strategy.events == ['open', 'open']


def test_backtests_do_not_skip_events(strategy, monkeypatch):
    monkeypatch.setattr(jh, 'is_livetrading', lambda: False)
    _stream(strategy.position, 2)

    strategy.fill()
    strategy.fill()

    assert strategy.events == ['open', 'open']
