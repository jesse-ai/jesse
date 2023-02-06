import pytest
from jesse import research


def test_store_candles():
    """
    for now, don't actually store it in the db. But test validations, etc
    """
    # validate that candles type must be np.ndarray
    with pytest.raises(TypeError):
        research.store_candles({}, 'Test Exchange', 'BTC-USDT')
    with pytest.raises(TypeError):
        research.store_candles([], 'Test Exchange', 'BTC-USDT')

    # add validation for timeframe to make sure it's `1m`
    with pytest.raises(ValueError):
        close_prices = [10, 11]
        np_candles = research.candles_from_close_prices(close_prices)
        # change the timeframe to 5 minutes
        np_candles[1][0] += 300_000
        research.store_candles(np_candles, 'Test Exchange', 'BTC-USDT')

    # just make sure it doesn't raise an error
    close_prices = [10, 11, 12, 12, 11, 13, 14, 12, 11, 15]
    np_candles = research.candles_from_close_prices(close_prices)
    research.store_candles(np_candles, 'Test Exchange', 'BTC-USDT')
