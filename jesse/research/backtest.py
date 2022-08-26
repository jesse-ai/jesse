from typing import List, Dict
import copy


def backtest(
        config: dict,
        routes: List[Dict[str, str]],
        extra_routes: List[Dict[str, str]],
        candles: dict,
        generate_charts: bool = False,
        generate_tradingview: bool = False,
        generate_quantstats: bool = False,
        generate_hyperparameters: bool = False,
        generate_equity_curve: bool = False,
        generate_csv: bool = False,
        generate_json: bool = False,
        hyperparameters: dict = None
) -> dict:
    """
    An isolated backtest() function which is perfect for using in research, and AI training
    such as our own optimization mode. Because of it being a pure function, it can be used
    in Python's multiprocessing without worrying about pickling issues.

    Example `config`:
    {
        'starting_balance': 5_000,
        'fee': 0.001,
        'type': 'futures',
        'futures_leverage': 3,
        'futures_leverage_mode': 'cross',
        'exchange': 'Binance',
        'warm_up_candles': 100
    }

    Example `route`:
    [{'exchange': 'Bybit USDT Perpetual', 'strategy': 'A1', 'symbol': 'BTC-USDT', 'timeframe': '1m'}]

    Example `extra_route`:
    [{'exchange': 'Bybit USDT Perpetual', 'symbol': 'BTC-USDT', 'timeframe': '3m'}]

    Example `candles`:
    {
        'Binance-BTC-USDT': {
            'exchange': 'Binance',
            'symbol': 'BTC-USDT',
            'candles': np.array([]),
        },
    }
    """
    return _isolated_backtest(
        config,
        routes,
        extra_routes,
        candles,
        run_silently=True,
        hyperparameters=hyperparameters,
        generate_charts=generate_charts,
        generate_tradingview=generate_tradingview,
        generate_quantstats=generate_quantstats,
        generate_csv=generate_csv,
        generate_json=generate_json,
        generate_equity_curve=generate_equity_curve,
        generate_hyperparameters=generate_hyperparameters,
    )


def _isolated_backtest(
        config: dict,
        routes: List[Dict[str, str]],
        extra_routes: List[Dict[str, str]],
        candles: dict,
        run_silently: bool = True,
        hyperparameters: dict = None,
        generate_charts: bool = False,
        generate_tradingview: bool = False,
        generate_quantstats: bool = False,
        generate_csv: bool = False,
        generate_json: bool = False,
        generate_equity_curve: bool = False,
        generate_hyperparameters: bool = False
) -> dict:
    from jesse.services.validators import validate_routes
    from jesse.modes.backtest_mode import simulator
    from jesse.config import config as jesse_config, reset_config
    from jesse.routes import router
    from jesse.store import store
    from jesse.config import set_config
    from jesse.services import required_candles
    import jesse.helpers as jh

    jesse_config['app']['trading_mode'] = 'backtest'

    # inject (formatted) configuration values
    set_config(_format_config(config))

    # set routes
    router.initiate(routes, extra_routes)

    validate_routes(router)
    # TODO: further validate routes and allow only one exchange
    # TODO: validate the name of the exchange in the config and the route? or maybe to make sure it's a supported exchange

    # initiate candle store
    store.candles.init_storage(5000)

    # assert that the passed candles are 1m candles
    for key, value in candles.items():
        candle_set = value['candles']
        if candle_set[1][0] - candle_set[0][0] != 60_000:
            raise ValueError(
                f'Candles passed to the research.backtest() must be 1m candles. '
                f'\nIf you wish to trade other timeframes, notice that you need to pass it through '
                f'the timeframe option in your routes. '
                f'\nThe difference between your candles are {candle_set[1][0] - candle_set[0][0]} milliseconds which more than '
                f'the accepted 60000 milliseconds.'
            )

    # divide candles into warm_up_candles and trading_candles and then inject warm_up_candles
    max_timeframe = jh.max_timeframe(jesse_config['app']['considering_timeframes'])
    warm_up_num = config['warm_up_candles'] * jh.timeframe_to_one_minutes(max_timeframe)
    trading_candles = copy.deepcopy(candles)

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
    backtest_result = simulator(
        trading_candles,
        run_silently,
        hyperparameters=hyperparameters,
        generate_charts=generate_charts,
        generate_tradingview=generate_tradingview,
        generate_quantstats=generate_quantstats,
        generate_csv=generate_csv,
        generate_json=generate_json,
        generate_equity_curve=generate_equity_curve,
        generate_hyperparameters=generate_hyperparameters
    )

    result = {
        'metrics': {'total': 0, 'win_rate': 0, 'net_profit_percentage': 0},
        'logs': None,
    }

    if backtest_result['metrics'] is None:
        result['metrics'] = {'total': 0, 'win_rate': 0, 'net_profit_percentage': 0}
        result['logs'] = None
    else:
        result['metrics'] = backtest_result['metrics']
        result['logs'] = store.logs.info

    if generate_charts:
        result['charts'] = backtest_result['charts']
    if generate_tradingview:
        result['tradingview'] = backtest_result['tradingview']
    if generate_quantstats:
        result['quantstats'] = backtest_result['quantstats']
    if generate_csv:
        result['csv'] = backtest_result['csv']
    if generate_json:
        result['json'] = backtest_result['json']
    if generate_equity_curve:
        result['equity_curve'] = backtest_result['equity_curve']
    if generate_hyperparameters:
        result['hyperparameters'] = backtest_result['hyperparameters']

    # reset store and config so rerunning would be flawlessly possible
    reset_config()
    store.reset()

    return result


def _format_config(config):
    """
    Jesse's required format for user_config is different from what this function accepts (so it
    would be easier to write for the researcher). Hence we need to reformat the config_dict:
    """
    exchange_config = {
        'balance': config['starting_balance'],
        'fee': config['fee'],
        'type': config['type'],
        'name': config['exchange'],
    }
    # futures exchange has different config, so:
    if exchange_config['type'] == 'futures':
        exchange_config['futures_leverage'] = config['futures_leverage']
        exchange_config['futures_leverage_mode'] = config['futures_leverage_mode']

    return {
        'exchanges': {
            config['exchange']: exchange_config
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
