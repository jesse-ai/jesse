import numpy as np
import pytest

import jesse.helpers as jh
from jesse import research
from jesse.enums import order_types
from jesse.store import store
from jesse.strategies import Strategy


START_TIMESTAMP = 1_609_459_200_000
EXCHANGE = 'Sandbox'
SYMBOL = 'BTC-USDT'


class _PriceGapExitStrategy(Strategy):
    """Exercise protective exits at the first available price after an opening gap."""

    def before(self) -> None:
        if self.index == 0:
            self.vars['phase'] = 0

    def before_terminate(self) -> None:
        assert self.vars['phase'] == 4
        assert len(store.closed_trades.trades) == 2
        assert store.app.total_open_trades == 0
        assert store.app.total_liquidations == 0

        exchange = store.exchanges.get_exchange(self.exchange)
        wallet_delta = round(exchange.wallet_balance - 10_000, 8)
        total_pnl = round(sum(trade.pnl for trade in store.closed_trades.trades), 8)
        assert wallet_delta == total_pnl == -0.8

    def should_long(self) -> bool:
        return self.price == 100 and self.vars['phase'] in (0, 2)

    def go_long(self) -> None:
        self.buy = 2, self.price
        self.vars['phase'] += 1

    def on_open_position(self, order) -> None:
        assert order.type == order_types.MARKET
        assert order.price == 100
        assert self.position.qty == 2

        if self.vars['phase'] == 1:
            self.stop_loss = 2, 95
        else:
            self.take_profit = 2, 105

    def on_close_position(self, order, closed_trade) -> None:
        assert self.position.qty == 0
        assert self.active_exit_orders == []
        assert closed_trade.type == 'long'
        assert closed_trade.entry_price == 100
        assert closed_trade.qty == 2

        if self.vars['phase'] == 1:
            assert order.type == order_types.STOP
            assert order.is_stop_loss is True
            assert order.vars['submitted_price'] == 95
            assert order.price == 90
            assert closed_trade.exit_price == 90
            assert round(closed_trade.fee, 8) == 0.38
            assert round(closed_trade.pnl, 8) == -20.38
        else:
            assert self.vars['phase'] == 3
            assert order.type == order_types.LIMIT
            assert order.is_take_profit is True
            assert order.vars['submitted_price'] == 105
            assert order.price == 110
            assert closed_trade.exit_price == 110
            assert round(closed_trade.fee, 8) == 0.42
            assert round(closed_trade.pnl, 8) == 19.58

        self.vars['phase'] += 1

    def should_cancel_entry(self) -> bool:
        return False


class _ShortPriceGapExitStrategy(Strategy):
    """Exercise short protective exits at the first available opening price."""

    def before(self) -> None:
        if self.index == 0:
            self.vars['phase'] = 0

    def before_terminate(self) -> None:
        assert self.vars['phase'] == 4
        assert len(store.closed_trades.trades) == 2
        assert store.app.total_open_trades == 0
        assert store.app.total_liquidations == 0

        exchange = store.exchanges.get_exchange(self.exchange)
        wallet_delta = round(exchange.wallet_balance - 10_000, 8)
        total_pnl = round(sum(trade.pnl for trade in store.closed_trades.trades), 8)
        assert wallet_delta == total_pnl == -0.8

    def should_short(self) -> bool:
        return self.price == 100 and self.vars['phase'] in (0, 2)

    def should_long(self) -> bool:
        return False

    def go_long(self) -> None:
        pass

    def go_short(self) -> None:
        self.sell = 2, self.price
        self.vars['phase'] += 1

    def on_open_position(self, order) -> None:
        assert order.type == order_types.MARKET
        assert order.price == 100
        assert self.position.qty == -2

        if self.vars['phase'] == 1:
            self.stop_loss = 2, 105
        else:
            self.take_profit = 2, 95

    def on_close_position(self, order, closed_trade) -> None:
        assert self.position.qty == 0
        assert self.active_exit_orders == []
        assert closed_trade.type == 'short'
        assert closed_trade.entry_price == 100
        assert closed_trade.qty == 2

        if self.vars['phase'] == 1:
            assert order.type == order_types.STOP
            assert order.is_stop_loss is True
            assert order.vars['submitted_price'] == 105
            assert order.price == 110
            assert closed_trade.exit_price == 110
            assert round(closed_trade.fee, 8) == 0.42
            assert round(closed_trade.pnl, 8) == -20.42
        else:
            assert self.vars['phase'] == 3
            assert order.type == order_types.LIMIT
            assert order.is_take_profit is True
            assert order.vars['submitted_price'] == 95
            assert order.price == 90
            assert closed_trade.exit_price == 90
            assert round(closed_trade.fee, 8) == 0.38
            assert round(closed_trade.pnl, 8) == 19.62

        self.vars['phase'] += 1

    def should_cancel_entry(self) -> bool:
        return False


def _price_gap_candles() -> np.ndarray:
    """Return three 5m blocks containing boundary and intra-block price gaps."""
    return np.array([
        [START_TIMESTAMP, 100, 100, 101, 99, 10],
        [START_TIMESTAMP + 60_000, 100, 100, 101, 99, 10],
        [START_TIMESTAMP + 120_000, 100, 100, 101, 99, 10],
        [START_TIMESTAMP + 180_000, 100, 100, 101, 99, 10],
        [START_TIMESTAMP + 240_000, 100, 100, 101, 99, 10],
        [START_TIMESTAMP + 300_000, 90, 90, 92, 88, 10],
        [START_TIMESTAMP + 360_000, 90, 90, 91, 89, 10],
        [START_TIMESTAMP + 420_000, 90, 90, 91, 89, 10],
        [START_TIMESTAMP + 480_000, 90, 90, 91, 89, 10],
        [START_TIMESTAMP + 540_000, 90, 100, 101, 89, 10],
        [START_TIMESTAMP + 600_000, 100, 100, 101, 99, 10],
        [START_TIMESTAMP + 660_000, 100, 100, 101, 99, 10],
        [START_TIMESTAMP + 720_000, 110, 110, 112, 108, 10],
        [START_TIMESTAMP + 780_000, 110, 110, 111, 109, 10],
        [START_TIMESTAMP + 840_000, 110, 110, 111, 109, 10],
    ], dtype=np.float64)


def _short_price_gap_candles() -> np.ndarray:
    """Return mirrored upward-stop and downward-take-profit opening gaps."""
    return np.array([
        [START_TIMESTAMP, 100, 100, 101, 99, 10],
        [START_TIMESTAMP + 60_000, 100, 100, 101, 99, 10],
        [START_TIMESTAMP + 120_000, 100, 100, 101, 99, 10],
        [START_TIMESTAMP + 180_000, 100, 100, 101, 99, 10],
        [START_TIMESTAMP + 240_000, 100, 100, 101, 99, 10],
        [START_TIMESTAMP + 300_000, 110, 110, 112, 108, 10],
        [START_TIMESTAMP + 360_000, 110, 110, 111, 109, 10],
        [START_TIMESTAMP + 420_000, 110, 110, 111, 109, 10],
        [START_TIMESTAMP + 480_000, 110, 110, 111, 109, 10],
        [START_TIMESTAMP + 540_000, 110, 100, 111, 99, 10],
        [START_TIMESTAMP + 600_000, 100, 100, 101, 99, 10],
        [START_TIMESTAMP + 660_000, 100, 100, 101, 99, 10],
        [START_TIMESTAMP + 720_000, 90, 90, 92, 88, 10],
        [START_TIMESTAMP + 780_000, 90, 90, 91, 89, 10],
        [START_TIMESTAMP + 840_000, 90, 90, 91, 89, 10],
    ], dtype=np.float64)


def _run_price_gap_backtest(
        strategy: type[Strategy],
        candles: np.ndarray,
        fast_mode: bool,
) -> dict:
    config = {
        'starting_balance': 10_000,
        'fee': 0.001,
        'type': 'futures',
        'futures_leverage': 2,
        'futures_leverage_mode': 'cross',
        'exchange': EXCHANGE,
        'warm_up_candles': 0,
    }
    routes = [{
        'exchange': EXCHANGE,
        'strategy': strategy,
        'symbol': SYMBOL,
        'timeframe': '5m',
    }]
    candle_data = {
        jh.key(EXCHANGE, SYMBOL): {
            'exchange': EXCHANGE,
            'symbol': SYMBOL,
            'candles': candles,
        },
    }
    return research.backtest(config, routes, [], candle_data, fast_mode=fast_mode)


@pytest.mark.parametrize('fast_mode', [False, True], ids=['step', 'fast'])
def test_price_gaps_execute_protective_orders_consistently(fast_mode: bool) -> None:
    candles = _price_gap_candles()

    # A 5m route makes fast mode process five 1m candles per batch. The stop gap
    # starts a batch, while the take-profit gap occurs inside a later batch.
    np.testing.assert_array_equal(np.diff(candles[:, 0]), np.full(14, 60_000))
    assert candles[5, 1] != candles[4, 2]
    assert candles[5, 3] < 95
    assert candles[12, 1] != candles[11, 2]
    assert candles[12, 4] > 105

    result = _run_price_gap_backtest(_PriceGapExitStrategy, candles, fast_mode)
    assert candles[5, 1] == 90
    assert candles[12, 1] == 110
    metrics = result['metrics']

    assert metrics['total'] == 2
    assert metrics['total_winning_trades'] == 1
    assert metrics['total_losing_trades'] == 1
    assert metrics['longs_count'] == 2
    assert metrics['shorts_count'] == 0
    assert metrics['total_open_trades'] == 0
    assert metrics['open_pl'] == 0
    assert round(metrics['fee'], 8) == 0.8
    assert round(metrics['net_profit'], 8) == -0.8
    assert round(metrics['finishing_balance'], 8) == 9_999.2

    trade_fingerprint = [
        (
            trade['type'],
            trade['entry_price'],
            trade['exit_price'],
            trade['qty'],
            round(trade['fee'], 8),
            round(trade['PNL'], 8),
            int(trade['opened_at']),
            int(trade['closed_at']),
            trade['holding_period'],
        )
        for trade in result['trades']
    ]
    assert trade_fingerprint == [
        ('long', 100, 90, 2, 0.38, -20.38, START_TIMESTAMP + 300_000, START_TIMESTAMP + 360_000, 60),
        ('long', 100, 110, 2, 0.42, 19.58, START_TIMESTAMP + 600_000, START_TIMESTAMP + 780_000, 180),
    ]


@pytest.mark.parametrize('fast_mode', [False, True], ids=['step', 'fast'])
def test_short_price_gaps_execute_protective_orders_consistently(fast_mode: bool) -> None:
    candles = _short_price_gap_candles()

    np.testing.assert_array_equal(np.diff(candles[:, 0]), np.full(14, 60_000))
    assert candles[5, 4] > 105
    assert candles[12, 3] < 95

    result = _run_price_gap_backtest(_ShortPriceGapExitStrategy, candles, fast_mode)
    assert candles[5, 1] == 110
    assert candles[12, 1] == 90
    metrics = result['metrics']

    assert metrics['total'] == 2
    assert metrics['total_winning_trades'] == 1
    assert metrics['total_losing_trades'] == 1
    assert metrics['longs_count'] == 0
    assert metrics['shorts_count'] == 2
    assert metrics['total_open_trades'] == 0
    assert metrics['open_pl'] == 0
    assert round(metrics['fee'], 8) == 0.8
    assert round(metrics['net_profit'], 8) == -0.8
    assert round(metrics['finishing_balance'], 8) == 9_999.2

    trade_fingerprint = [
        (
            trade['type'],
            trade['entry_price'],
            trade['exit_price'],
            trade['qty'],
            round(trade['fee'], 8),
            round(trade['PNL'], 8),
            int(trade['opened_at']),
            int(trade['closed_at']),
            trade['holding_period'],
        )
        for trade in result['trades']
    ]
    assert trade_fingerprint == [
        ('short', 100, 110, 2, 0.42, -20.42, START_TIMESTAMP + 300_000, START_TIMESTAMP + 360_000, 60),
        ('short', 100, 90, 2, 0.38, 19.62, START_TIMESTAMP + 600_000, START_TIMESTAMP + 780_000, 180),
    ]
