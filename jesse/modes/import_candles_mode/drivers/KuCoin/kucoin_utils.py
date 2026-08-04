from jesse.enums import timeframes


# KuCoin SPOT klines use string interval names: 1min, 5min, 1hour, 1day, ...
def timeframe_to_spot_type(timeframe: str) -> str:
    mapping = {
        timeframes.MINUTE_1: '1min',
        timeframes.MINUTE_3: '3min',
        timeframes.MINUTE_5: '5min',
        timeframes.MINUTE_15: '15min',
        timeframes.MINUTE_30: '30min',
        timeframes.HOUR_1: '1hour',
        timeframes.HOUR_2: '2hour',
        timeframes.HOUR_4: '4hour',
        timeframes.HOUR_6: '6hour',
        timeframes.HOUR_8: '8hour',
        timeframes.HOUR_12: '12hour',
        timeframes.DAY_1: '1day',
        timeframes.WEEK_1: '1week',
    }
    if timeframe not in mapping:
        raise ValueError(f'Invalid timeframe: {timeframe}')
    return mapping[timeframe]


# KuCoin FUTURES klines use integer granularity in MINUTES: 1, 5, 60, 1440, ...
def timeframe_to_futures_granularity(timeframe: str) -> int:
    mapping = {
        timeframes.MINUTE_1: 1,
        timeframes.MINUTE_5: 5,
        timeframes.MINUTE_15: 15,
        timeframes.MINUTE_30: 30,
        timeframes.HOUR_1: 60,
        timeframes.HOUR_2: 120,
        timeframes.HOUR_4: 240,
        timeframes.HOUR_8: 480,
        timeframes.HOUR_12: 720,
        timeframes.DAY_1: 1440,
        timeframes.WEEK_1: 10080,
    }
    if timeframe not in mapping:
        raise ValueError(f'Invalid timeframe: {timeframe}')
    return mapping[timeframe]


def jesse_symbol_to_futures_contract(symbol: str) -> str:
    """
    Map a Jesse dashy symbol (BTC-USDT) to a KuCoin futures contract code (XBTUSDTM).
    KuCoin futures uses XBT instead of BTC for the bitcoin contract.
    """
    base, quote = symbol.split('-')
    if base == 'BTC':
        base = 'XBT'  # KuCoin futures lists bitcoin as XBT, not BTC
    return f'{base}{quote}M'  # e.g. ETH-USDT -> ETHUSDTM, BTC-USDT -> XBTUSDTM
