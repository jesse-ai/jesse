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

