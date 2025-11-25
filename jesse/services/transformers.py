from jesse.models.ExchangeApiKeys import ExchangeApiKeys
from jesse.models.NotificationApiKeys import NotificationApiKeys
from jesse.models.OptimizationSession import OptimizationSession
from jesse.models.BacktestSession import BacktestSession
from jesse.models.MonteCarloSession import MonteCarloSession
import json
import math
import jesse.helpers as jh


def get_exchange_api_key(exchange_api_key: ExchangeApiKeys) -> dict:
    result = {
        'id': str(exchange_api_key.id),
        'exchange': exchange_api_key.exchange_name,
        'name': exchange_api_key.name,
        'api_key': exchange_api_key.api_key[0:4] + '***...***' + exchange_api_key.api_key[-4:],
        'api_secret': exchange_api_key.api_secret[0:4] + '***...***' + exchange_api_key.api_secret[-4:],
        'created_at': exchange_api_key.created_at.isoformat(),
    }

    if type(exchange_api_key.additional_fields) == str:
        exchange_api_key.additional_fields = json.loads(exchange_api_key.additional_fields)

    # additional fields
    if exchange_api_key.additional_fields:
        for key, value in exchange_api_key.additional_fields.items():
            result[key] = value[0:4] + '***...***' + value[-4:]

    return result


def get_notification_api_key(api_key: NotificationApiKeys, protect_sensitive_data=True) -> dict:
    result = {
        'id': str(api_key.id),
        'name': api_key.name,
        'driver': api_key.driver,
        'created_at': api_key.created_at.isoformat()
    }

    # Parse the fields from the JSON string
    fields = json.loads(api_key.fields)

    # Add each field to the result
    for key, value in fields.items():
        if protect_sensitive_data:
            result[key] = value[0:4] + '***...***' + value[-4:]
        else:
            result[key] = value

    return result


def get_optimization_session(session: OptimizationSession) -> dict:
    """
    Transform an OptimizationSession model instance into a dictionary for API responses
    """
    return {
        'id': str(session.id),
        'status': session.status,
        'completed_trials': session.completed_trials,
        'total_trials': session.total_trials,
        'created_at': session.created_at,
        'updated_at': session.updated_at,
        'best_score': session.best_score,
        'state': json.loads(session.state) if session.state else None,
        'title': session.title,
        'description': session.description,
        'strategy_codes': json.loads(session.strategy_codes) if session.strategy_codes else {}
    }


def get_optimization_session_for_load_more(session: OptimizationSession) -> dict:
    objective_function_config = jh.get_config('env.optimization.objective_function', 'sharpe').lower()
    mapping = {
        'sharpe': 'sharpe_ratio',
        'calmar': 'calmar_ratio',
        'sortino': 'sortino_ratio',
        'omega': 'omega_ratio',
        'serenity': 'serenity_index',
        'smart sharpe': 'smart_sharpe',
        'smart sortino': 'smart_sortino'
    }
    metric_key = mapping.get(objective_function_config, objective_function_config)

    best_candidates = []

    def replace_inf_with_null(obj):
        if isinstance(obj, dict):
            return {k: replace_inf_with_null(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [replace_inf_with_null(item) for item in obj]
        elif isinstance(obj, float) and (obj == float('inf') or obj == float('-inf')):
            return None
        return obj

    best_trials_list = replace_inf_with_null(json.loads(session.best_trials)) if session.best_trials else []

    for idx, t in enumerate(best_trials_list):
        training_metrics = t.get('training_metrics', {})
        testing_metrics = t.get('testing_metrics', {})

        train_value = training_metrics.get(metric_key, None)
        test_value = testing_metrics.get(metric_key, None)
        if isinstance(train_value, (int, float)):
            train_value = round(train_value, 2)
        if isinstance(test_value, (int, float)):
            test_value = round(test_value, 2)
        if train_value is None:
            train_value = "N/A"
        if test_value is None:
            test_value = "N/A"

        candidate_objective_metric = f"{train_value} / {test_value}"

        best_candidates.append({
            'rank': f"#{idx + 1}",
            'trial': f"Trial {t['trial']}",
            'params': t['params'],
            'fitness': t['fitness'],
            'dna': t['dna'],
            'training_metrics': training_metrics,  # Use the already fetched metrics
            'testing_metrics': testing_metrics,   # Use the already fetched metrics
            'objective_metric': candidate_objective_metric
        })

    best_candidates = json.dumps(best_candidates).replace('NaN', 'null')
    best_candidates = json.loads(best_candidates)

    objective_curve = None
    if session.objective_curve:
        objective_curve = session.objective_curve.replace('-Infinity', 'null').replace('Infinity', 'null')
        objective_curve = objective_curve.replace('NaN', 'null')
        objective_curve = json.loads(objective_curve)

    return {
        'id': str(session.id),
        'status': session.status,
        'completed_trials': session.completed_trials,
        'total_trials': session.total_trials,
        'created_at': session.created_at,
        'updated_at': session.updated_at,
        'best_score': session.best_score,
        'best_candidates': best_candidates,
        'objective_curve': objective_curve,
        'state': session.state_json,
        'exception': session.exception,
        'traceback': session.traceback,
        'title': session.title,
        'description': session.description,
    }


def get_backtest_session(session: BacktestSession) -> dict:
    """
    Transform a BacktestSession model instance into a dictionary for API responses (listing)
    """
    return {
        'id': str(session.id),
        'status': session.status,
        'created_at': session.created_at,
        'updated_at': session.updated_at,
        'execution_duration': session.execution_duration,
        'net_profit_percentage': session.net_profit_percentage,
        'state': json.loads(session.state) if session.state else None,
        'title': session.title,
        'description': session.description,
        'strategy_codes': session.strategy_codes_json
    }


def get_backtest_session_for_load_more(session: BacktestSession) -> dict:
    """
    Transform a BacktestSession model instance with full data for detailed view
    """
    # Parse JSON fields and clean infinite values
    metrics = jh.clean_infinite_values(json.loads(session.metrics)) if session.metrics else None
    equity_curve = jh.clean_infinite_values(json.loads(session.equity_curve)) if session.equity_curve else []
    trades = jh.clean_infinite_values(json.loads(session.trades)) if session.trades else []
    hyperparameters = jh.clean_infinite_values(json.loads(session.hyperparameters)) if session.hyperparameters else None
    
    return {
        'id': str(session.id),
        'status': session.status,
        'metrics': metrics,
        'equity_curve': equity_curve,
        'trades': trades,
        'hyperparameters': hyperparameters,
        'has_chart_data': bool(session.chart_data),
        'created_at': session.created_at,
        'updated_at': session.updated_at,
        'execution_duration': session.execution_duration,
        'state': session.state_json,
        'exception': session.exception,
        'traceback': session.traceback,
        'title': session.title,
        'description': session.description,
        'strategy_codes': session.strategy_codes_json
    }


def get_monte_carlo_session(session: MonteCarloSession) -> dict:
    """
    Transform a MonteCarloSession model instance into a dictionary for API responses (listing)
    """
    trades_session = session.trades_session
    candles_session = session.candles_session
    
    return {
        'id': str(session.id),
        'status': session.status,
        'has_trades': trades_session is not None,
        'has_candles': candles_session is not None,
        'trades_status': trades_session.status if trades_session else None,
        'candles_status': candles_session.status if candles_session else None,
        'created_at': session.created_at,
        'updated_at': session.updated_at,
        'title': session.title,
        'description': session.description,
        'strategy_codes': json.loads(session.strategy_codes) if session.strategy_codes else {},
        'state': session.state_json
    }


def _percentile(arr: list, p: float) -> float:
    """Calculate the p-th percentile of a list of numbers."""
    if not arr:
        return 0.0
    sorted_arr = sorted(arr)
    index = (p / 100.0) * (len(sorted_arr) - 1)
    lower = int(index)
    upper = min(lower + 1, len(sorted_arr) - 1)
    weight = index % 1
    return sorted_arr[lower] * (1 - weight) + sorted_arr[upper] * weight


def _extract_candles_summary_metrics(results: dict) -> list:
    """Extract summary metrics from Monte Carlo candles results."""
    metrics = []
    results = json.loads(results)

    if not results or 'confidence_analysis' not in results:
        return metrics

    ca_metrics = results['confidence_analysis']['metrics']

    # Define metrics to display (in order)
    metric_keys = ['net_profit_percentage', 'max_drawdown', 'sharpe_ratio', 'win_rate', 'total', 'annual_return', 'calmar_ratio']

    for key in metric_keys:
        if key not in ca_metrics:
            continue

        analysis = ca_metrics[key]
        original = analysis.get('original')
        percentiles = analysis.get('percentiles', {})

        # Get percentiles
        p5 = percentiles.get('5th')
        p50 = percentiles.get('50th')
        p95 = percentiles.get('95th')

        metrics.append({
            'metric': key,
            'original': original,
            'worst_5': p5,
            'median': p50,
            'best_5': p95
        })

    return metrics


def _extract_trades_summary_metrics(results: dict) -> list:
    """Extract summary metrics from Monte Carlo trades confidence analysis."""
    metrics = []
    results = json.loads(results)

    if not results or 'confidence_analysis' not in results:
        return metrics

    ca_metrics = results['confidence_analysis']['metrics']

    # Define metrics to display (in order)
    metric_keys = ['total_return', 'max_drawdown', 'sharpe_ratio', 'calmar_ratio']

    for key in metric_keys:
        if key not in ca_metrics:
            continue

        analysis = ca_metrics[key]
        original = analysis.get('original')
        percentiles = analysis.get('percentiles', {})

        # Get percentiles
        p5 = percentiles.get('5th')
        p50 = percentiles.get('50th')
        p95 = percentiles.get('95th')
        
        metrics.append({
            'metric': key,
            'original': original,
            'worst_5': p5,
            'median': p50,
            'best_5': p95
        })

    return metrics


def get_monte_carlo_session_for_load_more(session: MonteCarloSession) -> dict:
    """
    Transform a MonteCarloSession model instance with full data for detailed view
    """
    trades_session = session.trades_session
    candles_session = session.candles_session

    trades_data = None
    if trades_session:
        trades_data = {
            'id': str(trades_session.id),
            'status': trades_session.status,
            'num_scenarios': trades_session.num_scenarios,
            'completed_scenarios': trades_session.completed_scenarios,
            'summary_metrics': _extract_trades_summary_metrics(trades_session.results) if trades_session.results else [],
            'logs': trades_session.logs,
            'exception': trades_session.exception,
            'traceback': trades_session.traceback,
        }

    candles_data = None
    if candles_session:
        candles_data = {
            'id': str(candles_session.id),
            'status': candles_session.status,
            'num_scenarios': candles_session.num_scenarios,
            'completed_scenarios': candles_session.completed_scenarios,
            'pipeline_type': candles_session.pipeline_type,
            'pipeline_params': json.loads(candles_session.pipeline_params) if candles_session.pipeline_params else None,
            'logs': candles_session.logs,
            'exception': candles_session.exception,
            'traceback': candles_session.traceback,
            'summary_metrics': _extract_candles_summary_metrics(candles_session.results) if candles_session.results else [],
        }
        # Sanitize nested NaN/Inf across entire candles_data structure
        candles_data = jh.clean_nan_values(candles_data)

    # Sanitize trades_data as well for completeness
    if trades_data is not None:
        trades_data = jh.clean_nan_values(trades_data)

    return {
        'id': str(session.id),
        'status': session.status,
        'trades_session': trades_data,
        'candles_session': candles_data,
        'created_at': session.created_at,
        'updated_at': session.updated_at,
        'title': session.title,
        'description': session.description,
        'state': session.state_json,
    }
