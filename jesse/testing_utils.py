import jesse.helpers as jh
from jesse.config import reset_config
from jesse.enums import exchanges
from jesse.factories import candles_from_close_prices
from jesse.modes import backtest_mode
from jesse.config import config


def get_btc_and_eth_candles():
    candles = {
        jh.key(exchanges.SANDBOX, 'BTC-USDT'): {
            'exchange': exchanges.SANDBOX,
            'symbol': 'BTC-USDT',
            'candles': candles_from_close_prices(range(101, 200)),
        }
    }

    candles[jh.key(exchanges.SANDBOX, 'ETH-USDT')] = {
        'exchange': exchanges.SANDBOX,
        'symbol': 'ETH-USDT',
        'candles': candles_from_close_prices(range(1, 100))
    }
    return candles


def get_btc_candles(candles_count=100):
    return {
        jh.key(exchanges.SANDBOX, 'BTC-USDT'): {
            'exchange': exchanges.SANDBOX,
            'symbol': 'BTC-USDT',
            'candles': candles_from_close_prices(range(1, candles_count)),
        }
    }


def get_downtrend_candles(candles_count=100):
    return {
        jh.key(exchanges.SANDBOX, 'BTC-USDT'): {
            'exchange': exchanges.SANDBOX,
            'symbol': 'BTC-USDT',
            'candles': candles_from_close_prices(range(candles_count, 10, -1)),
        }
    }


def set_up(is_futures_trading=True, leverage=1, leverage_mode='cross', fee=0):
    reset_config()
    config['env']['exchanges'][exchanges.SANDBOX]['balance'] = 10_000

    config['env']['exchanges']['Sandbox']['fee'] = fee

    if is_futures_trading:
        # used only in futures trading
        config['env']['exchanges'][exchanges.SANDBOX]['type'] = 'futures'
        config['env']['exchanges'][exchanges.SANDBOX]['futures_leverage_mode'] = leverage_mode
        config['env']['exchanges'][exchanges.SANDBOX]['futures_leverage'] = leverage
    else:
        config['env']['exchanges'][exchanges.SANDBOX]['type'] = 'spot'


def single_route_backtest(
        strategy_name: str, is_futures_trading=True,
        leverage=1, leverage_mode='cross', trend='up', fee=0,
        candles_count=100, timeframe='1m'
):
    """
    used to simplify simple tests
    """
    set_up(
        is_futures_trading=is_futures_trading,
        leverage=leverage,
        leverage_mode=leverage_mode,
        fee=fee
    )

    routes = [{'symbol': 'BTC-USDT', 'timeframe': timeframe, 'strategy': strategy_name}]

    if trend == 'up':
        candles = get_btc_candles(candles_count)
    elif trend == 'down':
        candles = get_downtrend_candles(candles_count)
    else:
        raise ValueError

    # dates are fake. just to pass required parameters
    backtest_mode.run('000', False, {}, exchanges.SANDBOX, routes, [], '2019-04-01', '2019-04-02', candles)


def two_routes_backtest(
        strategy_name1: str, strategy_name2: str, is_futures_trading=True, leverage=1, leverage_mode='cross', trend='up'
):
    """
    used to simplify simple tests
    """
    set_up(
        is_futures_trading=is_futures_trading,
        leverage=leverage,
        leverage_mode=leverage_mode
    )

    routes = [
        {'symbol': 'BTC-USDT', 'timeframe': '1m', 'strategy': strategy_name1},
        {'symbol': 'ETH-USDT', 'timeframe': '1m', 'strategy': strategy_name2},
    ]

    # dates are fake. just to pass required parameters
    backtest_mode.run('000', False, {}, exchanges.SANDBOX, routes, [], '2019-04-01', '2019-04-02', get_btc_and_eth_candles())
