import os
from hashlib import sha256
import requests
from fastapi.responses import JSONResponse
from jesse.services.env import ENV_VALUES
import jesse.helpers as jh


def password_to_token(password: str) -> JSONResponse:
    if password != ENV_VALUES['PASSWORD']:
        return unauthorized_response()

    auth_token = sha256(password.encode('utf-8')).hexdigest()

    return JSONResponse({
        'auth_token': auth_token,
    }, status_code=200)


def is_valid_token(auth_token: str) -> bool:
    hashed_local_pass = sha256(ENV_VALUES['PASSWORD'].encode('utf-8')).hexdigest()
    return auth_token == hashed_local_pass


def unauthorized_response() -> JSONResponse:
    return JSONResponse({
        'message': "Invalid password",
    }, status_code=401)


def get_access_token():
    from jesse.services.env import ENV_VALUES

    if 'LICENSE_API_TOKEN' not in ENV_VALUES:
        return None
    if not ENV_VALUES['LICENSE_API_TOKEN']:
        return None

    return ENV_VALUES['LICENSE_API_TOKEN']


def login_to_jesse_trade(email: str, password: str) -> JSONResponse:
    response = requests.post('https://jesse.trade/api/auth', json={
        'email': email,
        'password': password,
        'device_name': jh.computer_name()
    })

    if response.status_code != 200:
        return JSONResponse({
            'status': 'error',
            'message': f"[{response.status_code}]: {response.json()['message']}\nPlease contact us at support@jesse.trade if this is unexpected.",
        }, status_code=200)

    access_token = response.json()['token']

    os.makedirs('./storage/temp', exist_ok=True)
    with open('storage/temp/access_token', 'w') as f:
        f.write(access_token)

    return JSONResponse({
        'status': 'success',
        'message': 'Successfully logged in to Jesse.Trade',
    }, status_code=200)


def logout_from_jesse_trade() -> JSONResponse:
    os.remove('storage/temp/access_token')

    return JSONResponse({
        'message': 'Successfully logged out from Jesse.Trade and removed access_token file'
    })
