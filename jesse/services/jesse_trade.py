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


def report_exception(description: str, traceback: str) -> JSONResponse:
    access_token = get_access_token()

    res = requests.post(
        'https://jesse.trade/api/exception', {
            'description': description,
            'traceback': traceback
        },
        headers={'Authorization': f'Bearer {access_token}'}
    )

    success_message = 'Exception report submitted successfully'
    error_message = f"{res.status_code} error: {res.json()['message']}"

    return JSONResponse({
        'status': 'success' if res.status_code == 200 else 'error',
        'message': success_message if res.status_code == 200 else error_message
    }, status_code=200)
