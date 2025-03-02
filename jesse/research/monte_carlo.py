import functools
import multiprocessing
from typing import List, Dict

import jesse.helpers as jh
from jesse.research import backtest


def monte_carlo(
    config: dict,
    routes: List[Dict[str, str]],
    data_routes: List[Dict[str, str]],
    candles: dict,
    warmup_candles: dict = None,
    benchmark: bool = False,
    hyperparameters: dict = None,
    fast_mode: bool = True,
    scenarios: int = 1000,
    progress_bar: bool = False,
    cpu_cores: int = 0,
) -> list[dict]:
    if progress_bar:
        if jh.is_notebook():
            from tqdm.notebook import tqdm
        else:
            from tqdm import tqdm
        scenarios_list = tqdm(range(scenarios))
    else:
        scenarios_list = range(scenarios)

    cpu_cores = cpu_cores or multiprocessing.cpu_count()
    _backtest = functools.partial(
        backtest,
        config=config,
        routes=routes,
        data_routes=data_routes,
        candles=candles,
        warmup_candles=warmup_candles,
        generate_equity_curve=True,
        hyperparameters=hyperparameters,
        fast_mode=fast_mode,
    )

    def allow_failures_backtests(*args, **kwargs):
        try:
            return _backtest(*args, **kwargs)
        except Exception as e:
            return {'exception': e}

    with multiprocessing.Pool(processes=cpu_cores) as pool:
        benchmarks = [benchmark] + [False] * (scenarios - 1)
        results = pool.map(allow_failures_backtests, benchmarks)
    return results
