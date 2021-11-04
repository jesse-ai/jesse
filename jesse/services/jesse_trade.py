import requests
from starlette.responses import JSONResponse
from jesse.services.auth import get_access_token


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

    # get log file using mode and session_id
    if mode == 'backtest':
        path = f'storage/logs/backtest-mode/{session_id}.txt'
    else:
        raise ValueError('Invalid mode')

    files = {'log_file': open(path, 'rb')} if attach_logs else None

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
