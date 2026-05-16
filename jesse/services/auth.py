from hashlib import sha256
from typing import Optional
from fastapi import Header, Query, Depends
from fastapi.responses import JSONResponse
from fastapi import HTTPException
from jesse.services.env import ENV_VALUES


def require_auth(authorization: Optional[str] = Header(None)) -> None:
    if not is_valid_token(authorization):
        raise HTTPException(status_code=401, detail="Invalid password")


def require_auth_token(token: Optional[str] = Query(None)) -> None:
    if not is_valid_token(token):
        raise HTTPException(status_code=401, detail="Invalid password")


def require_auth_any(
    token: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
) -> None:
    effective = token or authorization
    if not is_valid_token(effective):
        raise HTTPException(status_code=401, detail="Invalid password")


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


def user_validation(password: str) -> JSONResponse:
    if password != ENV_VALUES['PASSWORD']:
        return unauthorized_response()

    auth_token = sha256(password.encode('utf-8')).hexdigest()

    return JSONResponse({
        'auth_token': auth_token,
    }, status_code=200)