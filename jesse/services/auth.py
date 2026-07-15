from hashlib import sha256
from typing import Optional

from fastapi import Header, HTTPException, Query
from fastapi.responses import JSONResponse
from jesse.services.env import ENV_VALUES


class InvalidAuthError(HTTPException):
    def __init__(self):
        super().__init__(status_code=401, detail="Invalid password")


def require_auth(authorization: Optional[str] = Header(None)) -> None:
    if not is_valid_token(authorization):
        raise InvalidAuthError


def require_auth_token(token: str = Query(...)) -> None:
    if not is_valid_token(token):
        raise InvalidAuthError


def require_auth_any(
    token: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
) -> None:
    if not is_valid_token(token or authorization):
        raise InvalidAuthError


def password_to_token(password: str) -> JSONResponse:
    if password != ENV_VALUES['PASSWORD']:
        return unauthorized_response()

    auth_token = sha256(password.encode('utf-8')).hexdigest()

    return JSONResponse({
        'auth_token': auth_token,
    }, status_code=200)


def is_valid_token(auth_token: Optional[str]) -> bool:
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


def user_validation(password: str) -> JSONResponse:
    if password != ENV_VALUES['PASSWORD']:
        return unauthorized_response()

    auth_token = sha256(password.encode('utf-8')).hexdigest()

    return JSONResponse({
        'auth_token': auth_token,
    }, status_code=200)
