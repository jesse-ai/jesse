from jesse.factories import range_candles
from jesse.services.candle import *


def test_candle_includes_price():
    c = np.array([1543387200000, 10, 20, 25, 5, 195])

    assert candle_includes_price(c, 5)
    assert candle_includes_price(c, 15)
    assert candle_includes_price(c, 25)

    assert not candle_includes_price(c, 4)
    assert not candle_includes_price(c, 26)


def test_generate_candle_from_one_minutes():
    candles = range_candles(5)

    five_minutes_candle = generate_candle_from_one_minutes('5m', candles)

    assert five_minutes_candle[0] == candles[0][0]
    assert five_minutes_candle[1] == candles[0][1]
    assert five_minutes_candle[2] == candles[-1][2]
    assert five_minutes_candle[3] == candles[:, 3].max()
    assert five_minutes_candle[4] == candles[:, 4].min()
    assert five_minutes_candle[5] == candles[:, 5].sum()


def test_is_bearish():
    c = np.array([1543387200000, 200, 190, 220, 180, 195])
    assert is_bearish(c)


def test_is_bullish():
    c = np.array([1543387200000, 190, 200, 220, 180, 195])
    assert is_bullish(c)


def test_split_candle():
    """
    these values has been tested from my thoughts on paper. You need to reproduce my drawings for them to make sense
    """
    bull = np.array([1111, 10, 20, 25, 5, 2222])
    bear = np.array([1111, 20, 10, 25, 5, 2222])

    # bullish candle, low < price < open
    np.testing.assert_equal(
        split_candle(bull, 7),
        (
            np.array([1111, 10, 7, 10, 7, 2222]),
            np.array([1111, 7, 20, 25, 5, 2222]),
        )
    )
    # bearish candle, open < price < high
    np.testing.assert_equal(
        split_candle(bear, 23),
        (
            np.array([1111, 20, 23, 23, 20, 2222]),
            np.array([1111, 23, 10, 25, 5, 2222]),
        )
    )

    # bullish candle, price == open
    np.testing.assert_equal(
        split_candle(bull, bull[1]),
        (bull, bull)
    )
    # bearish candle, price == open
    np.testing.assert_equal(
        split_candle(bear, bear[1]),
        (bear, bear)
    )

    # bearish candle,  low < price < close
    np.testing.assert_equal(
        split_candle(bear, 7),
        (
            np.array([1111, 20, 7, 25, 7, 2222]),
            np.array([1111, 7, 10, 10, 5, 2222]),
        )
    )
    # bullish candle,  close < price < high
    np.testing.assert_equal(
        split_candle(bull, 23),
        (
            np.array([1111, 10, 23, 23, 5, 2222]),
            np.array([1111, 23, 20, 25, 20, 2222]),
        )
    )

    # bearish candle,  price == close
    np.testing.assert_equal(
        split_candle(bear, 10),
        (
            np.array([1111, 20, 10, 25, 10, 2222]),
            np.array([1111, 10, 10, 10, 5, 2222]),
        )
    )
    # bullish candle,  close < price < high
    np.testing.assert_equal(
        split_candle(bull, 20),
        (
            np.array([1111, 10, 20, 20, 5, 2222]),
            np.array([1111, 20, 20, 25, 20, 2222]),
        )
    )

    # bearish candle,  price == high
    np.testing.assert_equal(
        split_candle(bear, 25),
        (
            np.array([1111, 20, 25, 25, 20, 2222]),
            np.array([1111, 25, 10, 25, 5, 2222]),
        )
    )
    # bullish candle,  price == low
    np.testing.assert_equal(
        split_candle(bull, 5),
        (
            np.array([1111, 10, 5, 10, 5, 2222]),
            np.array([1111, 5, 20, 25, 5, 2222]),
        )
    )

    # bearish candle,  price == low
    np.testing.assert_equal(
        split_candle(bear, 5),
        (
            np.array([1111, 20, 5, 25, 5, 2222]),
            np.array([1111, 5, 10, 10, 5, 2222]),
        )
    )
    # bullish candle,  price == high
    np.testing.assert_equal(
        split_candle(bull, 25),
        (
            np.array([1111, 10, 25, 25, 5, 2222]),
            np.array([1111, 25, 20, 25, 20, 2222]),
        )
    )

    # bearish candle, close < price < open
    np.testing.assert_equal(
        split_candle(bear, 15),
        (
            np.array([1111, 20, 15, 25, 15, 2222]),
            np.array([1111, 15, 10, 15, 5, 2222]),
        )
    )
    # bullish candle, open < price < close
    np.testing.assert_equal(
        split_candle(bull, 15),
        (
            np.array([1111, 10, 15, 15, 5, 2222]),
            np.array([1111, 15, 20, 25, 15, 2222]),
        )
    )
