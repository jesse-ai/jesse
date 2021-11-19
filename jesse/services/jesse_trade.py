import requests
from fastapi.responses import JSONResponse
from jesse.services.auth import get_access_token
import jesse.helpers as jh


def feedback(description: str) -> JSONResponse:
    access_token = get_access_token()

    res = requests.post(
        'https://jesse.trade/api/feedback', {
            'description': description
        },
        headers={'Authorization': f'Bearer {access_token}'}
    )

    success_message = 'Feedback submitted successfully'
    error_message = f"{res.status_code} error: {res.json()['message']}"

    return JSONResponse({
        'status': 'success' if res.status_code == 200 else 'error',
        'message': success_message if res.status_code == 200 else error_message
    }, status_code=200)


def report_exception(description: str, traceback: str, mode: str, attach_logs: bool, session_id: str) -> JSONResponse:
    access_token = get_access_token()

    if attach_logs and session_id:
        path_exchange_log = None
        if mode == 'backtest':
            path_log = f'storage/logs/backtest-mode/{session_id}.txt'
        elif mode == 'live':
            path_log = f'storage/logs/live-mode/{session_id}.txt'
            path_exchange_log = 'storage/logs/exchange-streams.txt'
        else:
            raise ValueError('Invalid mode')

        # attach exchange_log if there's any
        files = {'log_file': open(path_log, 'rb')}
        if path_exchange_log and jh.file_exists(path_exchange_log):
            files['exchange_log'] = open(path_exchange_log, 'rb')
    else:
        files = None

    params = {
        'description': description,
        'traceback': traceback,
    }
    res = requests.post(
        'https://jesse.trade/api/exception',
        data=params,
        files=files,
        headers={'Authorization': f'Bearer {access_token}'}
    )

    success_message = 'Exception report submitted successfully'
    error_message = f"{res.status_code} error: {res.json()['message']}"

    return JSONResponse({
        'status': 'success' if res.status_code == 200 else 'error',
        'message': success_message if res.status_code == 200 else error_message
    }, status_code=200)
