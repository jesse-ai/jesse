from math import log10
import jesse.helpers as jh
from jesse.research import backtest as isolated_backtest
from jesse.services import logger
import traceback
import os


def _formatted_inputs_for_isolated_backtest(user_config, routes):
    formatted_config = {
        'starting_balance': user_config['exchange']['balance'],
        'fee': user_config['exchange']['fee'],
        'futures_leverage': user_config['exchange']['futures_leverage'],
        'futures_leverage_mode': user_config['exchange']['futures_leverage_mode'],
        'exchange': routes[0]['exchange'],
        'settlement_currency': jh.quote_asset(routes[0]['symbol']),
        'warm_up_candles': user_config['warmup_candles_num']
    }

    return formatted_config


def get_fitness(
        optimization_config: dict, routes: list, extra_routes: list, strategy_hp, dna: str, training_candles,
        testing_candles, optimal_total
) -> tuple:
    """
    Notice that this function is likely to be executed inside workers, hence its inputs must
    have everything required for it to run. So it cannot access store, config, etc
    """
    hp = jh.dna_to_hp(strategy_hp, dna)

    # run backtest simulation
    training_data_metrics = isolated_backtest(
        _formatted_inputs_for_isolated_backtest(optimization_config, routes),
        routes,
        extra_routes,
        training_candles,
        hp
    )

    training_log = {'win-rate': None, 'total': None, 'PNL': None}
    testing_log = {'win-rate': None, 'total': None, 'PNL': None}

    # TODO: some of these have to be dynamic based on how many days it's trading for like for example "total"
    # I'm guessing we should accept "optimal" total from command line
    if training_data_metrics['total'] > 5:
        total_effect_rate = log10(training_data_metrics['total']) / log10(optimal_total)
        total_effect_rate = min(total_effect_rate, 1)
        ratio_config = jh.get_config('env.optimization.ratio', 'sharpe')
        if ratio_config == 'sharpe':
            ratio = training_data_metrics['sharpe_ratio']
            ratio_normalized = jh.normalize(ratio, -.5, 5)
        elif ratio_config == 'calmar':
            ratio = training_data_metrics['calmar_ratio']
            ratio_normalized = jh.normalize(ratio, -.5, 30)
        elif ratio_config == 'sortino':
            ratio = training_data_metrics['sortino_ratio']
            ratio_normalized = jh.normalize(ratio, -.5, 15)
        elif ratio_config == 'omega':
            ratio = training_data_metrics['omega_ratio']
            ratio_normalized = jh.normalize(ratio, -.5, 5)
        elif ratio_config == 'serenity':
            ratio = training_data_metrics['serenity_index']
            ratio_normalized = jh.normalize(ratio, -.5, 15)
        elif ratio_config == 'smart sharpe':
            ratio = training_data_metrics['smart_sharpe']
            ratio_normalized = jh.normalize(ratio, -.5, 5)
        elif ratio_config == 'smart sortino':
            ratio = training_data_metrics['smart_sortino']
            ratio_normalized = jh.normalize(ratio, -.5, 15)
        else:
            raise ValueError(
                f'The entered ratio configuration `{ratio_config}` for the optimization is unknown. Choose between sharpe, calmar, sortino, serenity, smart shapre, smart sortino and omega.')

        if ratio < 0:
            score = 0.0001
            return score, training_log, testing_log

        # log for debugging/monitoring
        training_log = {
            'win-rate': int(training_data_metrics['win_rate'] * 100), 'total': training_data_metrics['total'],
            'PNL': round(training_data_metrics['net_profit_percentage'], 2)
        }

        score = total_effect_rate * ratio_normalized

        # run backtest simulation
        testing_data_metrics = isolated_backtest(
            _formatted_inputs_for_isolated_backtest(),
            routes,
            extra_routes,
            testing_candles,
            hp
        )

        # log for debugging/monitoring
        if testing_data_metrics['total'] > 0:
            testing_log = {
                'win-rate': int(testing_data_metrics['win_rate'] * 100), 'total': testing_data_metrics['total'],
                'PNL': round(testing_data_metrics['net_profit_percentage'], 2)
            }

    else:
        score = 0.0001

    return score, training_log, testing_log


def get_and_add_fitness_to_the_bucket(
        dna_bucket, optimization_config, routes: list, extra_routes: list, strategy_hp, dna, training_candles,
        testing_candles, optimal_total
) -> None:
    """
    Calculates the fitness ands adds the result into the dna_bucket (which is the object passed among workers)
    """
    try:
        # check if the DNA is already in the list
        if all(dna_tuple[0] != dna for dna_tuple in dna_bucket):
            fitness_score, fitness_log_training, fitness_log_testing = get_fitness(
                optimization_config, routes, extra_routes, strategy_hp, dna, training_candles, testing_candles,
                optimal_total
            )
            dna_bucket.append((dna, fitness_score, fitness_log_training, fitness_log_testing))
        else:
            raise ValueError(f"Initial Population: Double DNA: {dna}")
    except Exception as e:
        proc = os.getpid()
        logger.error(f'process failed - ID: {str(proc)}')
        logger.error("".join(traceback.TracebackException.from_exception(e).format()))
        raise e
