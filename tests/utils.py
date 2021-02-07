import jesse.helpers as jh
from jesse.config import reset_config
from jesse.enums import exchanges, timeframes
from jesse.factories import fake_range_candle_from_range_prices
from jesse.modes import backtest_mode
from jesse.routes import router
from jesse.store import store
from jesse.config import config


def get_btc_and_eth_candles():
    candles = {}
    candles[jh.key(exchanges.SANDBOX, 'BTC-USDT')] = {
        'exchange': exchanges.SANDBOX,
        'symbol': 'BTC-USDT',
        'candles': fake_range_candle_from_range_prices(range(101, 200))
    }
    candles[jh.key(exchanges.SANDBOX, 'ETH-USDT')] = {
        'exchange': exchanges.SANDBOX,
        'symbol': 'ETH-USDT',
        'candles': fake_range_candle_from_range_prices(range(1, 100))
    }
    return candles


def get_btc_candles():
    candles = {}
    candles[jh.key(exchanges.SANDBOX, 'BTC-USDT')] = {
        'exchange': exchanges.SANDBOX,
        'symbol': 'BTC-USDT',
        'candles': fake_range_candle_from_range_prices(range(1, 100))
    }
    return candles


def set_up(routes=None, is_futures_trading=True, leverage=1, leverage_mode='cross', zero_fee=False):
    reset_config()
    config['env']['exchanges'][exchanges.SANDBOX]['assets'] = [
        {'asset': 'USDT', 'balance': 10_000},
        {'asset': 'BTC', 'balance': 0},
        {'asset': 'ETH', 'balance': 0},
    ]

    if zero_fee:
        config['env']['exchanges']['Sandbox']['fee'] = 0

    if is_futures_trading:
        # used only in futures trading
        config['env']['exchanges'][exchanges.SANDBOX]['type'] = 'futures'
        config['env']['exchanges'][exchanges.SANDBOX]['futures_leverage_mode'] = leverage_mode
        config['env']['exchanges'][exchanges.SANDBOX]['futures_leverage'] = leverage
    else:
        config['env']['exchanges'][exchanges.SANDBOX]['type'] = 'spot'

    if routes:
        router.set_routes(routes)

    store.reset(True)


def single_route_backtest(strategy_name: str, is_futures_trading=True, leverage=1):
    """
    used to simplify simple tests
    """
    set_up(
        [(exchanges.SANDBOX, 'BTC-USDT', timeframes.MINUTE_1, strategy_name)],
        is_futures_trading=is_futures_trading,
        leverage=leverage
    )
    # dates are fake. just to pass required parameters
    backtest_mode.run('2019-04-01', '2019-04-02', get_btc_candles())
