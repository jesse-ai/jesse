from jesse.models.ExchangeApiKeys import ExchangeApiKeys
from jesse.models.NotificationApiKeys import NotificationApiKeys
from jesse.models.OptimizationSession import OptimizationSession
import json
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
        'created_at': session.created_at,
        'updated_at': session.updated_at,
        'best_score': session.best_score,
        'state': json.loads(session.state) if session.state else None
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
        'traceback': session.traceback
    }
