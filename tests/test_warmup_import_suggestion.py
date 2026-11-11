import pytest

import jesse.helpers as jh
from jesse.config import config
from jesse.modes import backtest_mode


@pytest.fixture
def suggest(monkeypatch):
    def run(exchange: str, timeframe: str, warmup_num: int = 210, start_date: str = '2024-01-01') -> str:
        monkeypatch.setitem(config['app'], 'considering_timeframes', ['1m', timeframe])
        real_get_config = jh.get_config
        monkeypatch.setattr(jh, 'get_config', lambda key, default=None: (
            warmup_num if key == 'env.data.warmup_candles_num' else real_get_config(key, default)))
        return backtest_mode.suggested_warmup_import_start(start_date, exchange)
    return run


def test_a_24_7_market_needs_only_its_warmup_period(suggest):
    # 210 five-minute candles, doubled for safety, is 35 hours.
    assert suggest('Binance Perpetual Futures', '5m') == '2023-12-30'


def test_a_stock_market_reaches_past_nights_weekends_and_holidays(suggest):
    # Importing from 2023-12-30 only brought in Friday's last after-hours hour for SPY,
    # 12 of the 210 five-minute warm-up candles, so the backtest kept asking for the same import.
    # 210 candles at 60 per short trading day is 4 trading days, 6 calendar days, plus 14 for holidays.
    assert suggest('FMP Stocks', '5m') == '2023-12-12'
    assert suggest('Massive Stocks', '5m') == '2023-12-12'


def test_daily_candles_on_a_stock_market_count_one_per_trading_day(suggest):
    # 210 trading days is 294 calendar days, plus 14 for holidays.
    assert suggest('FMP Stocks', '1D') == jh.timestamp_to_date(jh.date_to_timestamp('2024-01-01') - 308 * 86_400_000)


def test_no_warmup_needs_no_earlier_data(suggest):
    assert suggest('FMP Stocks', '5m', warmup_num=0) == '2024-01-01'
