import functools
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
    with_candles_pipeline: bool = True,
) -> list[dict]:
    if progress_bar:
        if jh.is_notebook():
            from tqdm.notebook import tqdm
        else:
            from tqdm import tqdm
        scenarios_list = tqdm(range(scenarios))
    else:
        scenarios_list = range(scenarios)

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
        with_candles_pipeline=with_candles_pipeline
    )


    return [
        _backtest(
            benchmark=benchmark and i == 0, with_candles_pipeline=i != 0
        )
        for i in scenarios_list
    ]
