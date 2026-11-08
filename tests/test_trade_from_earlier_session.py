from types import SimpleNamespace

import pytest

import jesse.helpers as jh
from jesse.services import closed_trade_service
from jesse.store import store


@pytest.fixture
def close_live_trade(monkeypatch):
    """Close a restored live trade the way a live session does, with storage and notifications faked."""
    saved = []
    monkeypatch.setattr(jh, 'is_livetrading', lambda: True)
    monkeypatch.setattr(jh, 'is_live', lambda: False)
    monkeypatch.setattr(closed_trade_service.closed_trade_repository, 'store_or_update', saved.append)
    monkeypatch.setattr(closed_trade_service.closed_trade_repository, 'close_trade', lambda trade: None)
    monkeypatch.setattr(store.closed_trades, 'trades', [])
    monkeypatch.setattr(store.closed_trades, '_reset_current_trade', lambda exchange, symbol: None)
    monkeypatch.setattr(store.app, 'session_id', 'this-session')

    def run(trade_session_id):
        trade = SimpleNamespace(
            session_id=trade_session_id, is_open=True, closed_at=None, symbol='DOGE-USD',
            exchange='Kraken Pro Futures', type='long', qty=100, entry_price=0.0728, exit_price=0.0727,
            pnl=-0.01, pnl_percentage=-0.14, fee=0.007,
        )
        monkeypatch.setattr(store.closed_trades, '_get_current_trade', lambda exchange, symbol: trade)
        strategy = SimpleNamespace(trades_count=0)
        position = SimpleNamespace(
            exchange_name='Kraken Pro Futures', symbol='DOGE-USD', closed_at=1_000, strategy=strategy,
            exchange=SimpleNamespace(settlement_currency='usd'),
        )
        closed_trade_service.close_trade(position)
        return SimpleNamespace(trade=trade, saved=saved, strategy=strategy)

    return run


def test_a_trade_from_an_earlier_session_is_saved_but_not_counted(close_live_trade):
    result = close_live_trade('earlier-session')

    assert result.saved == [result.trade] and result.trade.session_id == 'earlier-session'
    assert result.trade.closed_at == 1_000
    assert store.closed_trades.trades == []
    assert result.strategy.trades_count == 0
    # The strategy's close callback still receives the closed trade.
    assert store.closed_trades.pop_closure('Kraken Pro Futures', 'DOGE-USD') is result.trade


def test_a_trade_opened_in_this_session_is_counted(close_live_trade):
    result = close_live_trade('this-session')

    assert store.closed_trades.trades == [result.trade]
    assert result.strategy.trades_count == 1
