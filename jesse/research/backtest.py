from typing import List, Dict


def backtest(
        config: dict,
        routes: List[Dict[str, str]],
        extra_routes: List[Dict[str, str]],
        candles: dict,
        run_silently: bool = True,
        hyperparameters: dict = None
) -> dict:
    """
    An isolated backtest() function which is perfect for using in research, and AI training
    such as  our own optimization mode. Because of its isolation design, it can be used
    in Python's multiprocessing without worrying about pickling issues.

    Example `config`:
    {
        'starting_balance': 5_000,
        'fee': 0.001,
        'futures_leverage': 3,
        'futures_leverage_mode': 'cross',
        'exchange': 'Binance',
        'settlement_currency': 'USDT',
        'warm_up_candles': 100
    }

    Example `route`:
    [{'exchange': 'Binance', 'strategy': 'A1', 'symbol': 'BTC-USDT', 'timeframe': '1m'}]

    Example `extra_route`:
    [{'exchange': 'Binance', 'symbol': 'BTC-USD', 'timeframe': '3m'}]

    Example `candles`:
    {
        'Binance-BTC-USDT': {
            'exchange': 'Binance',
            'symbol': 'BTC-USDT',
            'candles': np.array([]),
        },
    }
    """
    from jesse.services.validators import validate_routes
    from jesse.modes.backtest_mode import simulator
    from jesse.config import config as jesse_config, reset_config
    from jesse.routes import router
    from jesse.store import store
    from jesse.config import set_config
    from jesse.services import metrics
    from jesse.services import required_candles
    import jesse.helpers as jh

    jesse_config['app']['trading_mode'] = 'backtest'

    # inject (formatted) configuration values
    set_config(_format_config(config))

    # set routes
    router.initiate(routes, extra_routes)

    # register_custom_exception_handler()

    validate_routes(router)
    # TODO: further validate routes and allow only one exchange
    # TODO: validate the name of the exchange in the config and the route? or maybe to make sure it's a supported exchange

    # initiate candle store
    store.candles.init_storage(5000)

    # divide candles into warm_up_candles and trading_candles and then inject warm_up_candles

    max_timeframe = jh.max_timeframe(jesse_config['app']['considering_timeframes'])
    warm_up_num = config['warm_up_candles'] * jh.timeframe_to_one_minutes(max_timeframe)
    trading_candles = candles
    if warm_up_num != 0:
        for c in jesse_config['app']['considering_candles']:
            key = jh.key(c[0], c[1])
            # update trading_candles
            trading_candles[key]['candles'] = candles[key]['candles'][warm_up_num:]
            # inject warm-up candles
            required_candles.inject_required_candles_to_store(
                candles[key]['candles'][:warm_up_num],
                c[0],
                c[1]
            )

    # run backtest simulation
    simulator(trading_candles, run_silently, hyperparameters)

    result = metrics.trades(store.completed_trades.trades, store.app.daily_balance)

    # reset store and config so rerunning would be flawlessly possible
    reset_config()
    store.reset()

    return result


def _format_config(config):
    """
    Jesse's required format for user_config is different from what this function accepts (so it
    would be easier to write for the researcher). Hence we need to reformat the config_dict:
    """
    return {
        'exchanges': {
            config['exchange']: {
                'balance': config['starting_balance'],
                'fee': config['fee'],
                'futures_leverage': config['futures_leverage'],
                'futures_leverage_mode': config['futures_leverage_mode'],
                'name': config['exchange'],
                'settlement_currency': config['settlement_currency']
            }
        },
        'logging': {
            'balance_update': True,
            'order_cancellation': True,
            'order_execution': True,
            'order_submission': True,
            'position_closed': True,
            'position_increased': True,
            'position_opened': True,
            'position_reduced': True,
            'shorter_period_candles': False,
            'trading_candles': True
        },
        'warm_up_candles': config['warm_up_candles']
    }
