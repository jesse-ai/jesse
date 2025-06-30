import sys
from math import log10
import jesse.helpers as jh
from jesse.research.backtest import _isolated_backtest as isolated_backtest
from jesse.services import logger
import numpy as np
from jesse import exceptions


def _formatted_inputs_for_isolated_backtest(user_config, routes):
    # Format input parameters required for backtest simulation
    return {
        'starting_balance': user_config['exchange']['balance'],
        'fee': user_config['exchange']['fee'],
        'type': user_config['exchange']['type'],
        'futures_leverage': user_config['exchange']['futures_leverage'],
        'futures_leverage_mode': user_config['exchange']['futures_leverage_mode'],
        'exchange': routes[0]['exchange'],
        'warm_up_candles': jh.get_config('env.data.warmup_candles_num')
    }


def get_fitness(
        user_config: dict, routes: list, data_routes: list, strategy_hp, hp: dict,
        training_warmup_candles: dict, training_candles: dict,
        testing_warmup_candles: dict, testing_candles: dict, optimal_total: int, fast_mode: bool
) -> tuple:
    """
    Evaluates the fitness (i.e. backtest performance) of the strategy
    using the given hyperparameters (hp). The fitness score is calculated based on the backtest results.
    """
    try:
        inputs = _formatted_inputs_for_isolated_backtest(user_config, routes)
        # Run backtest simulation for the training data using the suggested hyperparameters
        training_metrics = isolated_backtest(
            inputs,
            routes,
            data_routes,
            candles=training_candles,
            warmup_candles=training_warmup_candles,
            hyperparameters=hp,
            fast_mode=fast_mode
        )['metrics']

        # Calculate fitness score
        if training_metrics['total'] > 5:
            total_effect_rate = log10(training_metrics['total']) / log10(optimal_total)
            total_effect_rate = min(total_effect_rate, 1)
            objective_function_config = jh.get_config('env.optimization.objective_function', 'sharpe')
            
            # Get the ratio based on objective function
            if objective_function_config == 'sharpe':
                ratio = training_metrics['sharpe_ratio']
                ratio_normalized = jh.normalize(ratio, -.5, 5)
            elif objective_function_config == 'calmar':
                ratio = training_metrics['calmar_ratio']
                ratio_normalized = jh.normalize(ratio, -.5, 30)
            elif objective_function_config == 'sortino':
                ratio = training_metrics['sortino_ratio']
                ratio_normalized = jh.normalize(ratio, -.5, 15)
            elif objective_function_config == 'omega':
                ratio = training_metrics['omega_ratio']
                ratio_normalized = jh.normalize(ratio, -.5, 5)
            elif objective_function_config == 'serenity':
                ratio = training_metrics['serenity_index']
                ratio_normalized = jh.normalize(ratio, -.5, 15)
            elif objective_function_config == 'smart sharpe':
                ratio = training_metrics['smart_sharpe']
                ratio_normalized = jh.normalize(ratio, -.5, 5)
            elif objective_function_config == 'smart sortino':
                ratio = training_metrics['smart_sortino']
                ratio_normalized = jh.normalize(ratio, -.5, 15)
            else:
                raise ValueError(
                    f'The entered ratio configuration `{objective_function_config}` for the optimization is unknown. '
                    f'Choose between sharpe, calmar, sortino, serenity, smart sharpe, smart sortino and omega.'
                )

            # If the ratio is negative then the configuration is not usable
            if ratio < 0:
                score = 0.0001
                logger.log_optimize_mode(f"NEGATIVE RATIO: hp is not usable => {objective_function_config}: {ratio}, total: {training_metrics['total']}")
                return score, training_metrics, {}

            # Run backtest for testing period
            testing_metrics = isolated_backtest(
                inputs,
                routes,
                data_routes,
                candles=testing_candles,
                warmup_candles=testing_warmup_candles,
                hyperparameters=hp,
                fast_mode=fast_mode
            )['metrics']

            # Calculate fitness score
            score = total_effect_rate * ratio_normalized
            if np.isnan(score):
                logger.log_optimize_mode(f'Score is nan. hp configuration is invalid')
                score = 0.0001
            else:
                logger.log_optimize_mode(f"hp config is usable => {objective_function_config}: {round(ratio, 2)}, total: {training_metrics['total']}, "
                                       f"pnl%: {round(training_metrics['net_profit_percentage'], 2)}%, win-rate: {round(training_metrics['win_rate']*100, 2)}%")
        else:
            logger.log_optimize_mode('Less than 5 trades in the training data. hp configuration is invalid')
            score = 0.0001
            training_metrics = {}
            testing_metrics = {}

        return score, training_metrics, testing_metrics

    except exceptions.RouteNotFound as e:
        raise e
    except Exception as e:
        import sys, traceback
        exc_type, exc_value, exc_traceback = sys.exc_info()
        traceback_details = {
            "filename": exc_traceback.tb_frame.f_code.co_filename,
            "line": exc_traceback.tb_lineno,
            "name": exc_traceback.tb_frame.f_code.co_name,
            "type": exc_type.__name__,
            "message": str(e)
        }
        logger.log_optimize_mode(f"Trial evaluation failed: {traceback_details}")
        return 0.0001, {}, {}
