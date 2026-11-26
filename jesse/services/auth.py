import hmac
import os
import secrets
import threading
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode
from hashlib import sha256
from typing import Annotated, Optional

from fastapi import Form, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from jesse.services.env import ENV_VALUES

# Three kinds of credentials reach the API:
# - session tokens, which the dashboard gets at login and sends in the Authorization header;
# - link tokens, short-lived and only for the URLs a browser opens without headers (the
#   websocket, the code editor, downloads and images), so one copied from a log soon expires;
# - the static token, sha256(PASSWORD). AI assistants are configured with it once (see
#   jesse.mcp.auth), so it never expires; it is accepted in the Authorization header only.
SESSION_TOKEN_SECONDS = 30 * 24 * 3600
LINK_TOKEN_SECONDS = 3600
_TOKEN_VERSION = 'jst1'
_SECRET_FILE = os.path.join('storage', '.auth-secret')


class InvalidAuthError(HTTPException):
    def __init__(self):
        super().__init__(status_code=401, detail="Invalid password")


def require_auth(authorization: Optional[str] = Header(None)) -> None:
    if not is_valid_token(authorization):
        raise InvalidAuthError()


def require_auth_token(token: str = Query(...)) -> None:
    if not is_valid_link_token(token):
        raise InvalidAuthError()


def require_auth_any(
    token: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
) -> None:
    if not (is_valid_token(authorization) or is_valid_link_token(token)):
        raise InvalidAuthError()


def require_auth_form(token: Annotated[str, Form()]) -> None:
    """Authenticate native form submissions that cannot attach an Authorization header."""
    # A form body is not written to access logs, so a session token is fine here.
    if not (is_valid_token(token) or is_valid_link_token(token)):
        raise InvalidAuthError()


_secret_lock = threading.Lock()
_secret: Optional[bytes] = None


def _install_secret() -> bytes:
    """
    A random secret kept in the project's storage folder, shared by every Jesse process of the
    project. Tokens are signed with it and the PASSWORD together, so a token says nothing about
    the password, and changing the password signs everyone out.
    """
    global _secret
    with _secret_lock:
        if _secret is not None:
            return _secret
        import jesse.helpers as jh
        if jh.is_unit_testing():
            # tests run outside a project, so nothing is written to disk
            _secret = secrets.token_hex(32).encode()
            return _secret
        try:
            os.makedirs(os.path.dirname(_SECRET_FILE), exist_ok=True)
            try:
                fd = os.open(_SECRET_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, 'w') as f:
                    f.write(secrets.token_hex(32))
            except FileExistsError:
                pass
            with open(_SECRET_FILE) as f:
                value = f.read().strip()
            if len(value) < 32:
                raise ValueError('the stored auth secret is too short')
            _secret = value.encode()
        except (OSError, ValueError):
            # Without a writable storage folder, tokens last until Jesse restarts.
            _secret = secrets.token_hex(32).encode()
        return _secret


def _signing_key() -> Optional[bytes]:
    password = ENV_VALUES.get('PASSWORD') or ''
    if not password:
        return None
    return hmac.new(_install_secret(), password.encode('utf-8'), sha256).digest()


def _signature(key: bytes, body: str) -> str:
    digest = hmac.new(key, body.encode('utf-8'), sha256).digest()
    return urlsafe_b64encode(digest).decode().rstrip('=')


def _issue(purpose: str, seconds: int) -> str:
    key = _signing_key()
    if key is None:
        raise ValueError('A non-empty PASSWORD is required to issue a token.')
    expires = int(time.time()) + seconds
    body = f'{_TOKEN_VERSION}.{purpose}.{expires}.{secrets.token_urlsafe(12)}'
    return f'{body}.{_signature(key, body)}'


def _verify(token: Optional[str], purpose: str) -> bool:
    if not token:
        return False
    token = token.strip()
    if token.lower().startswith('bearer '):
        token = token[7:].strip()
    parts = token.split('.')
    if len(parts) != 5 or parts[0] != _TOKEN_VERSION or parts[1] != purpose:
        return False
    key = _signing_key()
    if key is None:
        return False
    body = '.'.join(parts[:4])
    if not hmac.compare_digest(_signature(key, body).encode(), parts[4].encode()):
        return False
    try:
        return int(parts[2]) > time.time()
    except ValueError:
        return False


def issue_session_token() -> str:
    return _issue('session', SESSION_TOKEN_SECONDS)


def issue_link_token() -> str:
    return _issue('link', LINK_TOKEN_SECONDS)


def static_token() -> Optional[str]:
    """The never-expiring token AI assistants use, derived from the PASSWORD (see jesse.mcp.auth)."""
    password = ENV_VALUES.get('PASSWORD') or ''
    return sha256(password.encode('utf-8')).hexdigest() if password else None


def is_valid_token(auth_token: Optional[str]) -> bool:
    """Whether an Authorization header carries a session token or the static token."""
    if _verify(auth_token, 'session'):
        return True
    expected = static_token()
    if not auth_token or expected is None:
        return False
    value = auth_token.strip()
    if value.lower().startswith('bearer '):
        value = value[7:].strip()
    return hmac.compare_digest(value.encode('utf-8'), expected.encode('utf-8'))


def is_valid_link_token(token: Optional[str]) -> bool:
    """Whether a URL query parameter carries an unexpired link token."""
    return _verify(token, 'link')


def is_correct_password(password: Optional[str]) -> bool:
    expected = ENV_VALUES.get('PASSWORD') or ''
    if not expected or not password:
        return False
    return hmac.compare_digest(password.encode('utf-8'), expected.encode('utf-8'))


class LoginThrottle:
    """
    Limits wrong passwords per client address, so a web page or a script can't guess the
    password at full speed. Ten wrong attempts lock that address out for fifteen minutes; a
    correct password clears its count.
    """
    MAX_FAILURES = 10
    WINDOW_SECONDS = 15 * 60

    def __init__(self):
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, address: str, now: float) -> list[float]:
        recent = [t for t in self._failures.get(address, []) if now - t < self.WINDOW_SECONDS]
        if recent:
            self._failures[address] = recent
        else:
            self._failures.pop(address, None)
        return recent

    def seconds_locked(self, address: str) -> int:
        """How long this address must wait before trying again, 0 when it may try now."""
        now = time.time()
        with self._lock:
            recent = self._recent(address, now)
            if len(recent) < self.MAX_FAILURES:
                return 0
            return max(1, int(recent[0] + self.WINDOW_SECONDS - now))

    def failed(self, address: str) -> None:
        now = time.time()
        with self._lock:
            self._recent(address, now)
            self._failures.setdefault(address, []).append(now)

    def succeeded(self, address: str) -> None:
        with self._lock:
            self._failures.pop(address, None)


login_throttle = LoginThrottle()


def password_to_token(password: str, address: str = '') -> JSONResponse:
    locked = login_throttle.seconds_locked(address)
    if locked:
        return JSONResponse({
            'message': f'Too many wrong passwords. Try again in {max(1, round(locked / 60))} minute(s).',
        }, status_code=429)
    if not is_correct_password(password):
        login_throttle.failed(address)
        return unauthorized_response()
    login_throttle.succeeded(address)
    return JSONResponse({
        'auth_token': issue_session_token(),
    }, status_code=200)


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


def user_validation(password: str, address: str = '') -> JSONResponse:
    return password_to_token(password, address)
