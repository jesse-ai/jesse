from typing import List, Dict, Tuple
import copy
import jesse.helpers as jh
from jesse.research.backtest import _isolated_backtest


def optimization(
        config: dict,
        routes: List[Dict[str, str]],
        data_routes: List[Dict[str, str]],
        training_candles: dict,
        testing_candles: dict,
        training_warmup_candles: dict = None,
        testing_warmup_candles: dict = None,
        strategy_hp: List[Dict] = None,
        optimal_total: int = 100,
        n_trials: int = 200,
        fast_mode: bool = False,
        cpu_cores: int = 1,
        objective_function: str = 'sharpe',
        generate_tradingview: bool = False,
        generate_hyperparameters: bool = False,
        generate_equity_curve: bool = False,
        benchmark: bool = False,
        generate_csv: bool = False,
        generate_json: bool = False,
        generate_logs: bool = False,
) -> dict:
    """
    An isolated optimization() function which is perfect for using in research, and AI training
    such as our own optimization mode. Because of it being a pure function, it can be used
    in Python's multiprocessing without worrying about pickling issues.

    Example `config`:
    {
        'starting_balance': 5_000,
        'fee': 0.005,
        'type': 'futures',
        'futures_leverage': 3,
        'futures_leverage_mode': 'cross',
        'exchange': 'Binance',
        'warm_up_candles': 0
    }

    Example `route`:
    [{'exchange': 'Bybit USDT Perpetual', 'strategy': 'A1', 'symbol': 'BTC-USDT', 'timeframe': '1m'}]

    Example `data_route`:
    [{'exchange': 'Bybit USDT Perpetual', 'symbol': 'BTC-USDT', 'timeframe': '3m'}]

    Example `training_candles` and `testing_candles`:
    {
        'Binance-BTC-USDT': {
            'exchange': 'Binance',
            'symbol': 'BTC-USDT',
            'candles': np.array([]),
        },
    }

    Example `strategy_hp`:
    [
        {'name': 'rsi_period', 'type': 'int', 'min': 10, 'max': 30},
        {'name': 'rsi_threshold', 'type': 'float', 'min': 20.0, 'max': 40.0},
        {'name': 'ema_period', 'type': 'int', 'min': 20, 'max': 50}
    ]
    """
    return _isolated_optimization(
        config,
        routes,
        data_routes,
        training_candles,
        testing_candles,
        training_warmup_candles,
        testing_warmup_candles,
        strategy_hp,
        optimal_total,
        n_trials,
        fast_mode,
        cpu_cores,
        objective_function,
        generate_tradingview=generate_tradingview,
        generate_csv=generate_csv,
        generate_json=generate_json,
        generate_equity_curve=generate_equity_curve,
        benchmark=benchmark,
        generate_hyperparameters=generate_hyperparameters,
        generate_logs=generate_logs,
    )


def _isolated_optimization(
        config: dict,
        routes: List[Dict[str, str]],
        data_routes: List[Dict[str, str]],
        training_candles: dict,
        testing_candles: dict,
        training_warmup_candles: dict = None,
        testing_warmup_candles: dict = None,
        strategy_hp: List[Dict] = None,
        optimal_total: int = 100,
        n_trials: int = 200,
        fast_mode: bool = False,
        cpu_cores: int = 1,
        objective_function: str = 'sharpe',
        generate_tradingview: bool = False,
        generate_hyperparameters: bool = False,
        generate_equity_curve: bool = False,
        benchmark: bool = False,
        generate_csv: bool = False,
        generate_json: bool = False,
        generate_logs: bool = False,
) -> dict:
    """
    Internal isolated optimization function that can be used in multiprocessing.
    """
    from jesse.services.validators import validate_routes
    from jesse.config import config as jesse_config, reset_config
    from jesse.routes import router
    from jesse.store import store
    from jesse.config import set_config
    from jesse.services.candle import inject_warmup_candles_to_store

    # Check Python version for Ray compatibility
    if jh.python_version() == (3, 13):
        raise ValueError(
            'Optimization is not supported on Python 3.13. The Ray library used for optimization does not support Python 3.13 yet. Please use Python 3.12 or lower.'
        )

    jesse_config['app']['trading_mode'] = 'optimize'

    # inject (formatted) configuration values
    set_config(_format_config(config))

    # set routes
    router.initiate(routes, data_routes)

    validate_routes(router)

    # initiate candle store
    store.candles.init_storage(5000)

    # assert that the passed candles are 1m candles
    for key, value in training_candles.items():
        candle_set = value['candles']
        if len(candle_set) > 1 and candle_set[1][0] - candle_set[0][0] != 60_000:
            raise ValueError(
                f'Training candles passed to the research.optimization() must be 1m candles. '
                f'\nIf you wish to trade other timeframes, notice that you need to pass it through '
                f'the timeframe option in your routes. '
                f'\nThe difference between your candles are {candle_set[1][0] - candle_set[0][0]} milliseconds which more than '
                f'the accepted 60000 milliseconds.'
            )

    for key, value in testing_candles.items():
        candle_set = value['candles']
        if len(candle_set) > 1 and candle_set[1][0] - candle_set[0][0] != 60_000:
            raise ValueError(
                f'Testing candles passed to the research.optimization() must be 1m candles. '
                f'\nIf you wish to trade other timeframes, notice that you need to pass it through '
                f'the timeframe option in your routes. '
                f'\nThe difference between your candles are {candle_set[1][0] - candle_set[0][0]} milliseconds which more than '
                f'the accepted 60000 milliseconds.'
            )

    # make a copy to make sure we don't mutate the past data causing some issues for multiprocessing tasks
    training_candles_dict = copy.deepcopy(training_candles)
    testing_candles_dict = copy.deepcopy(testing_candles)
    training_warmup_candles_dict = copy.deepcopy(training_warmup_candles)
    testing_warmup_candles_dict = copy.deepcopy(testing_warmup_candles)

    # if warmup_candles is passed, use it
    if training_warmup_candles:
        for c in jesse_config['app']['considering_candles']:
            key = jh.key(c[0], c[1])
            # inject warm-up candles
            inject_warmup_candles_to_store(
                training_warmup_candles_dict[key]['candles'],
                c[0],
                c[1]
            )

    if testing_warmup_candles:
        for c in jesse_config['app']['considering_candles']:
            key = jh.key(c[0], c[1])
            # inject warm-up candles
            inject_warmup_candles_to_store(
                testing_warmup_candles_dict[key]['candles'],
                c[0],
                c[1]
            )

    # Get strategy hyperparameters if not provided
    if strategy_hp is None:
        strategy_class = jh.get_strategy_class(router.routes[0].strategy_name)
        strategy_hp = strategy_class.hyperparameters(None)
        
        if not strategy_hp:
            raise ValueError('Targeted strategy does not implement a valid hyperparameters() method.')

    # Run optimization
    best_trial, all_trials = _run_optimization(
        config,
        routes,
        data_routes,
        training_candles_dict,
        testing_candles_dict,
        training_warmup_candles_dict,
        testing_warmup_candles_dict,
        strategy_hp,
        optimal_total,
        n_trials,
        fast_mode,
        cpu_cores,
        objective_function,
        generate_tradingview=generate_tradingview,
        generate_csv=generate_csv,
        generate_json=generate_json,
        generate_equity_curve=generate_equity_curve,
        benchmark=benchmark,
        generate_hyperparameters=generate_hyperparameters,
        generate_logs=generate_logs,
    )

    result = {
        'best_trial': best_trial,
        'all_trials': all_trials,
        'total_trials': len(all_trials),
        'best_score': best_trial.get('score', 0) if best_trial else 0,
        'best_params': best_trial.get('params', {}) if best_trial else {},
    }

    # reset store and config so rerunning would be flawlessly possible
    reset_config()
    store.reset()

    return result


def _run_optimization(
        config: dict,
        routes: List[Dict[str, str]],
        data_routes: List[Dict[str, str]],
        training_candles: dict,
        testing_candles: dict,
        training_warmup_candles: dict,
        testing_warmup_candles: dict,
        strategy_hp: List[Dict],
        optimal_total: int,
        n_trials: int,
        fast_mode: bool,
        cpu_cores: int,
        objective_function: str,
        generate_tradingview: bool = False,
        generate_hyperparameters: bool = False,
        generate_equity_curve: bool = False,
        benchmark: bool = False,
        generate_csv: bool = False,
        generate_json: bool = False,
        generate_logs: bool = False,
) -> Tuple[dict, List[dict]]:
    """
    Run the actual optimization process using random search.
    """

    all_trials = []
    best_trial = None
    best_score = -float('inf')

    # Format config for backtest
    backtest_config = _format_config_for_backtest(config, routes[0]['exchange'])

    for trial_num in range(n_trials):
        # Generate random hyperparameters
        hp = _generate_random_hyperparameters(strategy_hp)
        
        try:
            # Evaluate fitness
            score, training_metrics, testing_metrics = _evaluate_fitness(
                backtest_config,
                routes,
                data_routes,
                training_candles,
                testing_candles,
                training_warmup_candles,
                testing_warmup_candles,
                hp,
                optimal_total,
                objective_function,
                fast_mode,
                generate_tradingview=generate_tradingview,
                generate_csv=generate_csv,
                generate_json=generate_json,
                generate_equity_curve=generate_equity_curve,
                benchmark=benchmark,
                generate_hyperparameters=generate_hyperparameters,
                generate_logs=generate_logs,
            )

            # Create trial result
            trial_result = {
                'trial_number': trial_num + 1,
                'params': hp,
                'score': score,
                'training_metrics': training_metrics,
                'testing_metrics': testing_metrics,
                'dna': _encode_params_to_dna(hp)
            }

            all_trials.append(trial_result)

            # Update best trial if this is better
            if score > best_score:
                best_score = score
                best_trial = trial_result

        except Exception as e:
            # Log error and continue with next trial
            print(f"Trial {trial_num + 1} failed: {str(e)}")
            continue

    # Sort trials by score (descending)
    all_trials.sort(key=lambda x: x['score'], reverse=True)

    return best_trial, all_trials


def _generate_random_hyperparameters(strategy_hp: List[Dict]) -> dict:
    """
    Generate random hyperparameters based on strategy configuration.
    """
    import numpy as np
    
    hp = {}
    for param in strategy_hp:
        param_name = str(param['name'])
        param_type = param['type']
        
        # Convert to string whether input is type class or string
        if isinstance(param_type, type):
            param_type = param_type.__name__
        else:
            # Remove quotes if they exist
            param_type = param_type.strip("'").strip('"')

        if param_type == 'int':
            if 'step' in param and param['step'] is not None:
                steps = (param['max'] - param['min']) // param['step'] + 1
                value = param['min'] + np.random.randint(0, steps) * param['step']
            else:
                value = np.random.randint(param['min'], param['max'] + 1)
            hp[param_name] = value
        elif param_type == 'float':
            if 'step' in param and param['step'] is not None:
                steps = int((param['max'] - param['min']) / param['step']) + 1
                value = param['min'] + np.random.randint(0, steps) * param['step']
            else:
                value = np.random.uniform(param['min'], param['max'])
            hp[param_name] = value
        elif param_type == 'categorical':
            options = param['options']
            hp[param_name] = options[np.random.randint(0, len(options))]
        else:
            raise ValueError(f"Unsupported hyperparameter type: {param_type}")

    return hp


def _evaluate_fitness(
        config: dict,
        routes: List[Dict[str, str]],
        data_routes: List[Dict[str, str]],
        training_candles: dict,
        testing_candles: dict,
        training_warmup_candles: dict,
        testing_warmup_candles: dict,
        hp: dict,
        optimal_total: int,
        objective_function: str,
        fast_mode: bool,
        generate_tradingview: bool = False,
        generate_hyperparameters: bool = False,
        generate_equity_curve: bool = False,
        benchmark: bool = False,
        generate_csv: bool = False,
        generate_json: bool = False,
        generate_logs: bool = False,
) -> Tuple[float, dict, dict]:
    """
    Evaluate fitness of hyperparameters by running backtests.
    """
    from math import log10

    # Run training backtest
    training_result = _isolated_backtest(
        config,
        routes,
        data_routes,
        candles=training_candles,
        warmup_candles=training_warmup_candles,
        hyperparameters=hp,
        fast_mode=fast_mode,
        generate_tradingview=generate_tradingview,
        generate_csv=generate_csv,
        generate_json=generate_json,
        generate_equity_curve=generate_equity_curve,
        benchmark=benchmark,
        generate_hyperparameters=generate_hyperparameters,
        generate_logs=generate_logs,
    )

    training_metrics = training_result['metrics']

    # Calculate fitness score
    if training_metrics['total'] > 5:
        total_effect_rate = log10(training_metrics['total']) / log10(optimal_total)
        total_effect_rate = min(total_effect_rate, 1)
        
        # Get the ratio based on objective function
        if objective_function == 'sharpe':
            ratio = training_metrics['sharpe_ratio']
            ratio_normalized = jh.normalize(ratio, -.5, 5)
        elif objective_function == 'calmar':
            ratio = training_metrics['calmar_ratio']
            ratio_normalized = jh.normalize(ratio, -.5, 30)
        elif objective_function == 'sortino':
            ratio = training_metrics['sortino_ratio']
            ratio_normalized = jh.normalize(ratio, -.5, 15)
        elif objective_function == 'omega':
            ratio = training_metrics['omega_ratio']
            ratio_normalized = jh.normalize(ratio, -.5, 5)
        elif objective_function == 'serenity':
            ratio = training_metrics['serenity_index']
            ratio_normalized = jh.normalize(ratio, -.5, 15)
        elif objective_function == 'smart sharpe':
            ratio = training_metrics['smart_sharpe']
            ratio_normalized = jh.normalize(ratio, -.5, 5)
        elif objective_function == 'smart sortino':
            ratio = training_metrics['smart_sortino']
            ratio_normalized = jh.normalize(ratio, -.5, 15)
        else:
            raise ValueError(
                f'The entered ratio configuration `{objective_function}` for the optimization is unknown. '
                f'Choose between sharpe, calmar, sortino, serenity, smart sharpe, smart sortino and omega.'
            )

        # If the ratio is negative then the configuration is not usable
        if ratio < 0:
            return 0.0001, training_metrics, {}

        # Run testing backtest
        testing_result = _isolated_backtest(
            config,
            routes,
            data_routes,
            candles=testing_candles,
            warmup_candles=testing_warmup_candles,
            hyperparameters=hp,
            fast_mode=fast_mode,
            generate_tradingview=generate_tradingview,
            generate_csv=generate_csv,
            generate_json=generate_json,
            generate_equity_curve=generate_equity_curve,
            benchmark=benchmark,
            generate_hyperparameters=generate_hyperparameters,
            generate_logs=generate_logs,
        )

        testing_metrics = testing_result['metrics']

        # Calculate fitness score
        score = total_effect_rate * ratio_normalized
        import numpy as np
        if np.isnan(score):
            score = 0.0001
    else:
        score = 0.0001
        training_metrics = {}
        testing_metrics = {}

    return score, training_metrics, testing_metrics


def _format_config_for_backtest(config: dict, exchange: str) -> dict:
    """
    Format config for backtest function.
    """
    return {
        'starting_balance': config['starting_balance'],
        'fee': config['fee'],
        'type': config['type'],
        'futures_leverage': config['futures_leverage'],
        'futures_leverage_mode': config['futures_leverage_mode'],
        'exchange': exchange,
        'warm_up_candles': config['warm_up_candles']
    }


def _encode_params_to_dna(params: dict) -> str:
    """
    Encode parameters to DNA (base64) for identification.
    """
    import base64
    import json
    
    params_str = json.dumps(params, sort_keys=True)
    return base64.b64encode(params_str.encode()).decode()


def _format_config(config):
    """
    Jesse's required format for user_config is different from what this function accepts (so it
    would be easier to write for the researcher). Hence, we need to reformat the config_dict:
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
