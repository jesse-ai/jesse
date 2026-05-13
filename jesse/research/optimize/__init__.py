import base64
import json
from multiprocessing import cpu_count
from typing import Dict, List, Optional, TypedDict

import numpy as np
import optuna
import ray
import ray.exceptions
from tqdm import tqdm

import jesse.helpers as jh
from jesse import exceptions
from jesse.config import config as jesse_config, set_config
from jesse.research.monte_carlo.common import DEFAULT_CPU_USAGE_RATIO, MIN_CPU_CORES

from jesse.routes import router


class TrialResult(TypedDict):
    rank: int
    trial: int
    params: dict
    fitness: float
    dna: str
    training_metrics: dict
    testing_metrics: dict


class OptimizeReturn(TypedDict):
    best_trials: List[TrialResult]
    total_trials: int
    completed_trials: int
    objective_function: str


def _generate_trial_params(strategy_hp: list) -> dict:
    """Generate random hyperparameters for a trial, mirroring Optimizer._generate_trial_params."""
    hp = {}
    for param in strategy_hp:
        param_name = str(param['name'])
        param_type = param['type']
        if isinstance(param_type, type):
            param_type = param_type.__name__
        else:
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


def optimize(
    config: dict,
    routes: List[Dict[str, str]],
    data_routes: List[Dict[str, str]],
    training_candles: dict,
    training_warmup_candles: dict,
    testing_candles: dict,
    testing_warmup_candles: dict,
    optimal_total: int = 200,
    fast_mode: bool = True,
    cpu_cores: Optional[int] = None,
    trials: int = 200,
    objective_function: str = 'sharpe',
    best_candidates_count: int = 20,
    progress_bar: bool = True,
) -> OptimizeReturn:
    """
    A pure research function for running hyperparameter optimization without any
    dashboard, database, or WebSocket dependencies. Mirrors the pattern of
    research.backtest() and research.monte_carlo_trades().

    The ``config`` dict must follow the format consumed by
    ``jesse.modes.optimize_mode`` — i.e. with an ``exchange`` sub-dict:

    Example config::

        {
            'exchange': {
                'name': 'Binance Perpetual Futures',
                'balance': 10_000,
                'fee': 0.0007,
                'type': 'futures',
                'futures_leverage': 10,
                'futures_leverage_mode': 'cross',
            },
            'warm_up_candles': 210,
        }

    :param config: Jesse exchange/warmup config.
    :param routes: List of route dicts (without 'exchange'; it is injected).
    :param data_routes: List of extra data-route dicts.
    :param training_candles: Candle dict for the training period.
    :param training_warmup_candles: Warmup candle dict for the training period.
    :param testing_candles: Candle dict for the testing/validation period.
    :param testing_warmup_candles: Warmup candle dict for the testing period.
    :param optimal_total: Target number of trades used in fitness normalisation.
    :param fast_mode: Pass ``True`` to run backtests in fast (no-chart) mode.

    :param trials: Number of trials **per hyperparameter**. The total number of
        trials that will run is ``trials * number_of_hyperparameters``. Defaults
        to ``200``, which matches the dashboard optimization mode default.
    :param cpu_cores: Number of Ray workers to use. Defaults to 80% of available cores.
    :param objective_function: One of 'sharpe', 'calmar', 'sortino', 'omega'.
    :param best_candidates_count: How many top candidates to keep in the result.
    :param progress_bar: Show a tqdm progress bar.
    :return: An :class:`OptimizeReturn` typed dict.
    """
    # ------------------------------------------------------------------ guards
    if jh.python_version() == (3, 13):
        raise ValueError(
            'Optimization is not supported on Python 3.13. '
            'The Ray library used for optimization does not support Python 3.13 yet. '
            'Please use Python 3.12 or lower.'
        )

    _supported_objectives = ('sharpe', 'calmar', 'sortino', 'omega')
    if objective_function not in _supported_objectives:
        raise ValueError(
            f"Unsupported objective_function '{objective_function}'. "
            f"Choose one of: {', '.join(_supported_objectives)}."
        )

    if not routes:
        raise ValueError('At least one route is required.')

    # ---------------------------------------------------------- Jesse bootstrap
    # Set trading mode so that set_config() applies optimization-specific keys.
    jesse_config['app']['trading_mode'] = 'optimize'

    set_config({
        'warm_up_candles': config.get('warm_up_candles', 0),
        'objective_function': objective_function,
        # 'trials' is a required key in optimize mode; we override n_trials ourselves.
        'trials': 200,
        'best_candidates_count': best_candidates_count,
    })

    # Inject the exchange name into routes (mirrors optimize_mode/__init__.py pattern).
    exchange_name = config['exchange']['name']
    for r in routes:
        r['exchange'] = exchange_name
    for r in data_routes:
        r['exchange'] = exchange_name

    router.initiate(routes, data_routes)

    # ------------------------------------------------- resolve hyperparameters
    strategy_class = jh.get_strategy_class(router.routes[0].strategy_name)
    strategy_hp = strategy_class.hyperparameters(None)

    if not strategy_hp:
        raise exceptions.InvalidStrategy(
            'Targeted strategy does not implement a valid hyperparameters() method.'
        )

    solution_len = len(strategy_hp)

    # ----------------------------------------------------------- resolve cores
    available = cpu_count()
    if cpu_cores is None:
        cpu_cores = max(MIN_CPU_CORES, int(available * DEFAULT_CPU_USAGE_RATIO))
    else:
        cpu_cores = max(MIN_CPU_CORES, min(cpu_cores, available))

    # ----------------------------------------------------------- resolve trials
    # Always multiply by solution_len — identical behaviour to the dashboard.
    n_trials = solution_len * trials

    # ----------------------------------------------- create in-memory study
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    # The study is created for completeness/future use; random sampling is done
    # directly via _generate_trial_params, matching the existing Optimizer.
    _study = optuna.create_study(direction='maximize', storage=None)  # noqa: F841

    # ------------------------------------------------------------ init Ray
    ray_started_here = False
    if not ray.is_initialized():
        ray.init(num_cpus=cpu_cores, ignore_reinit_error=True)
        ray_started_here = True

    best_trials: list = []
    trial_counter: int = 0
    completed_trials: int = 0

    try:
        # Keep slightly more workers than cores to avoid CPU starvation, but
        # never more than the total number of remaining trials.
        max_workers = min(cpu_cores * 2, n_trials)
        active_refs: dict = {}

        bar = tqdm(total=n_trials, disable=not progress_bar, desc='Optimizing', unit='trial')

        # Deferred import to avoid circular dependency:
        # research/__init__.py ← optimize/__init__.py ← Optimize.py ← fitness.py ← research/__init__.py
        from jesse.modes.optimize_mode.Optimize import ray_evaluate_trial  # noqa: PLC0415

        # Place shared read-only objects in Ray's object store once so that
        # workers receive lightweight refs instead of full copies per trial.
        shared_user_config = ray.put(config)
        shared_formatted_routes = ray.put(router.formatted_routes)
        shared_formatted_data_routes = ray.put(router.formatted_data_routes)
        shared_strategy_hp = ray.put(strategy_hp)
        shared_training_warmup_candles = ray.put(training_warmup_candles)
        shared_training_candles = ray.put(training_candles)
        shared_testing_warmup_candles = ray.put(testing_warmup_candles)
        shared_testing_candles = ray.put(testing_candles)

        while completed_trials < n_trials:
            while len(active_refs) < max_workers and trial_counter < n_trials:
                hp = _generate_trial_params(strategy_hp)

                ref = ray_evaluate_trial.options(num_cpus=1).remote(
                    shared_user_config,
                    shared_formatted_routes,
                    shared_formatted_data_routes,
                    shared_strategy_hp,
                    hp,
                    shared_training_warmup_candles,
                    shared_training_candles,
                    shared_testing_warmup_candles,
                    shared_testing_candles,
                    optimal_total,
                    fast_mode,
                    trial_counter,
                    'research',
                )
                active_refs[ref] = trial_counter
                trial_counter += 1

            if not active_refs:
                break

            # ---- wait for at least one result ----
            done_refs, _ = ray.wait(list(active_refs.keys()), num_returns=1, timeout=0.5)

            for ref in done_refs:
                t_num = active_refs.pop(ref)
                try:
                    result = ray.get(ref)
                    completed_trials += 1
                    bar.update(1)

                    score = result['score']
                    params = result['params']
                    t_training_metrics = result['training_metrics']
                    t_testing_metrics = result['testing_metrics']

                    if score > 0.0001:
                        params_str = json.dumps(params, sort_keys=True)
                        dna = base64.b64encode(params_str.encode()).decode()

                        trial_info = {
                            'trial': t_num,
                            'params': params,
                            'fitness': round(score, 4),
                            'value': score,  # kept for sort; not exposed in return type
                            'dna': dna,
                            'training_metrics': t_training_metrics,
                            'testing_metrics': t_testing_metrics,
                        }

                        # Insert maintaining descending score order
                        insert_idx = 0
                        for idx, t in enumerate(best_trials):
                            if score > t['value']:
                                insert_idx = idx
                                break
                            else:
                                insert_idx = idx + 1

                        if insert_idx < best_candidates_count or len(best_trials) < best_candidates_count:
                            best_trials.insert(insert_idx, trial_info)
                            best_trials = best_trials[:best_candidates_count]

                except ray.exceptions.RayTaskError as e:
                    # Re-raise RouteNotFound as the underlying RuntimeError
                    if hasattr(e, 'cause') and isinstance(e.cause, RuntimeError) and 'RouteNotFound:' in str(e.cause):
                        raise e.cause
                    jh.debug(f'Ray task error for trial {t_num}: {e}')
                    raise
                except Exception as e:
                    jh.debug(f'Exception in ray method for trial {t_num}: {e}')
                    raise

        bar.close()

    finally:
        if ray_started_here and ray.is_initialized():
            ray.shutdown()

    # --------------------------------------------------------- build result
    ranked: List[TrialResult] = []
    for idx, t in enumerate(best_trials):
        ranked.append(TrialResult(
            rank=idx + 1,
            trial=t['trial'],
            params=t['params'],
            fitness=t['fitness'],
            dna=t['dna'],
            training_metrics=t['training_metrics'],
            testing_metrics=t['testing_metrics'],
        ))

    return OptimizeReturn(
        best_trials=ranked,
        total_trials=n_trials,
        completed_trials=completed_trials,
        objective_function=objective_function,
    )


def print_optimize_summary(result: OptimizeReturn, show_params: bool = False) -> None:
    """
    Print a human-readable summary table for an :class:`OptimizeReturn` result.

    :param result: The result returned by :func:`optimize`.
    :param show_params: When ``True``, the last column shows the raw parameter
        dict instead of the DNA string. Defaults to ``False`` (DNA shown).

    Example output::

        Completed 400 / 400 trials  |  Objective: sharpe

        Rank  Trial    Fitness  Training Sharpe Ratio  Testing Sharpe Ratio  DNA
        ----  -------  -------  --------------------   -------------------   ---
        #1    Trial 7   1.2345  2.34                   1.89                  eyJwZXJpb2QiOiAxNH0=
        ...
    """
    objective_function = result['objective_function']
    completed = result['completed_trials']
    total = result['total_trials']
    best_trials = result['best_trials']

    # Map objective_function → metrics key (mirrors _update_best_candidates)
    mapping = {
        'sharpe': 'sharpe_ratio',
        'calmar': 'calmar_ratio',
        'sortino': 'sortino_ratio',
        'omega': 'omega_ratio',
    }
    metric_key = mapping.get(objective_function.lower(), objective_function.lower())

    # Human-readable column header for the metric
    label_map = {
        'sharpe_ratio': 'Sharpe Ratio',
        'calmar_ratio': 'Calmar Ratio',
        'sortino_ratio': 'Sortino Ratio',
        'omega_ratio': 'Omega Ratio',
    }
    metric_label = label_map.get(metric_key, metric_key.replace('_', ' ').title())

    print(f"\nCompleted {completed} / {total} trials  |  Objective: {objective_function}\n")

    if not best_trials:
        print("No profitable trials found.")
        return

    # Column headers
    train_hdr = f"Train {metric_label}"
    test_hdr = f"Test {metric_label}"
    last_col_hdr = "Params" if show_params else "DNA"
    headers = ["Rank", "Trial", "Fitness", train_hdr, test_hdr, last_col_hdr]

    # Build rows
    rows = []
    for t in best_trials:
        train_val = t['training_metrics'].get(metric_key, None)
        test_val = t['testing_metrics'].get(metric_key, None)

        train_str = f"{round(train_val, 4)}" if isinstance(train_val, (int, float)) else "N/A"
        test_str = f"{round(test_val, 4)}" if isinstance(test_val, (int, float)) else "N/A"
        last_col_val = str(t['params']) if show_params else t['dna']

        rows.append([
            f"#{t['rank']}",
            f"Trial {t['trial']}",
            f"{t['fitness']}",
            train_str,
            test_str,
            last_col_val,
        ])

    # Compute column widths
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(cell))

    # Separator line
    separator = "  ".join("-" * w for w in col_widths)

    # Header line
    header_line = "  ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))

    print(header_line)
    print(separator)
    for row in rows:
        print("  ".join(cell.ljust(col_widths[i]) for i, cell in enumerate(row)))

    print()