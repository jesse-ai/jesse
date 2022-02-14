"""
For the multiprocessing to work property, it's best to pass around pure functions into workers instead
of methods of a class. Below functions have been designed with that in mind.
"""
from math import log10
import jesse.helpers as jh
from jesse.research.backtest import _isolated_backtest as isolated_backtest
from jesse.services import logger
import traceback
import os
from random import randint, choice
import numpy as np


def _formatted_inputs_for_isolated_backtest(user_config, routes):
    return {
        'starting_balance': user_config['exchange']['balance'],
        'fee': user_config['exchange']['fee'],
        'futures_leverage': user_config['exchange']['futures_leverage'],
        'futures_leverage_mode': user_config['exchange']['futures_leverage_mode'],
        'exchange': routes[0]['exchange'],
        'settlement_currency': jh.quote_asset(routes[0]['symbol']),
        'warm_up_candles': user_config['warmup_candles_num']
    }


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
    try:
        training_data_metrics = isolated_backtest(
            _formatted_inputs_for_isolated_backtest(optimization_config, routes),
            routes,
            extra_routes,
            training_candles,
            hyperparameters=hp
        )['metrics']
    except Exception as e:
        # get the main title of the exception
        log_text = e
        log_text = f"Exception in strategy execution:\n {log_text}"
        logger.log_optimize_mode(log_text)
        raise e

    training_log = {'win-rate': None, 'total': None, 'PNL': None}
    testing_log = {'win-rate': None, 'total': None, 'PNL': None}

    # TODO: some of these have to be dynamic based on how many days it's trading for like for example "total"
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
            logger.log_optimize_mode(f"NEGATIVE RATIO: DNA is not usable => {ratio_config}: {ratio}, total: {training_data_metrics['total']}")
            return score, training_log, testing_log

        # log for debugging/monitoring
        training_log = {
            'win-rate': int(training_data_metrics['win_rate'] * 100),
            'total': training_data_metrics['total'],
            'PNL': round(training_data_metrics['net_profit_percentage'], 2)
        }

        score = total_effect_rate * ratio_normalized
        # if score is numpy nan, replace it with 0.0001
        if np.isnan(score):
            logger.log_optimize_mode(f'Score is nan. DNA is invalid')
            score = 0.0001
        # elif jh.is_debugging():
        else:
            logger.log_optimize_mode(f"DNA is usable => {ratio_config}: {round(ratio, 2)}, total: {training_data_metrics['total']}, PNL%: {round(training_data_metrics['net_profit_percentage'], 2)}%, win-rate: {round(training_data_metrics['win_rate']*100, 2)}%")

        # run backtest simulation
        testing_data_metrics = isolated_backtest(
            _formatted_inputs_for_isolated_backtest(optimization_config, routes),
            routes,
            extra_routes,
            testing_candles,
            hyperparameters=hp
        )['metrics']

        # log for debugging/monitoring
        if testing_data_metrics['total'] > 0:
            testing_log = {
                'win-rate': int(testing_data_metrics['win_rate'] * 100), 'total': testing_data_metrics['total'],
                'PNL': round(testing_data_metrics['net_profit_percentage'], 2)
            }
    else:
        logger.log_optimize_mode(f'Less than 5 trades in the training data. DNA is invalid')
        score = 0.0001

    return score, training_log, testing_log


def get_and_add_fitness_to_the_bucket(
        dna_bucket, optimization_config, routes: list, extra_routes: list, strategy_hp, dna, training_candles,
        testing_candles, optimal_total
) -> None:
    """
    Calculates the fitness and adds the result into the dna_bucket (which is the object passed among workers)
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
        pid = os.getpid()
        logger.log_optimize_mode(f"process failed (ID: {pid}):\n{e}")


def make_love(
    mommy, daddy, solution_len,
    optimization_config, routes, extra_routes, strategy_hp, training_candles, testing_candles, optimal_total
) -> dict:
    dna = ''.join(
        daddy['dna'][i] if i % 2 == 0 else mommy['dna'][i] for i in range(solution_len)
    )

    # not found - so run the backtest
    fitness_score, fitness_log_training, fitness_log_testing = get_fitness(
        optimization_config, routes, extra_routes, strategy_hp, dna, training_candles, testing_candles, optimal_total
    )

    return {
        'dna': dna,
        'fitness': fitness_score,
        'training_log': fitness_log_training,
        'testing_log': fitness_log_testing
    }


def mutate(
        baby, solution_len, charset,
        optimization_config, routes, extra_routes, strategy_hp, training_candles, testing_candles, optimal_total
) -> dict:
    replace_at = randint(0, solution_len - 1)
    replace_with = choice(charset)
    dna = f"{baby['dna'][:replace_at]}{replace_with}{baby['dna'][replace_at + 1:]}"

    # not found - so run the backtest
    fitness_score, fitness_log_training, fitness_log_testing = get_fitness(
        optimization_config, routes, extra_routes, strategy_hp, dna, training_candles, testing_candles, optimal_total
    )

    return {
        'dna': dna,
        'fitness': fitness_score,
        'training_log': fitness_log_training,
        'testing_log': fitness_log_testing
    }


def create_baby(
    people_bucket: list, mommy, daddy, solution_len, charset,
    optimization_config, routes, extra_routes, strategy_hp, training_candles, testing_candles, optimal_total
) -> None:
    try:
        # let's make a baby together 👀
        baby = make_love(
            mommy, daddy, solution_len,
            optimization_config, routes, extra_routes, strategy_hp, training_candles, testing_candles, optimal_total
        )
        # let's mutate baby's genes, who knows, maybe we create a x-man or something
        baby = mutate(
            baby, solution_len, charset,
            optimization_config, routes, extra_routes, strategy_hp, training_candles, testing_candles, optimal_total
        )
        people_bucket.append(baby)
    except Exception as e:
        pid = os.getpid()
        logger.log_optimize_mode(f"process failed - ID: {pid}\n{e}")
