from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import JSONResponse
import requests
from jesse.services.env import ENV_VALUES
from jesse.services import auth as authenticator
from jesse.services.auth import require_auth
from jesse.services.multiprocessing import process_manager
from jesse.services.web import LoginRequestJson
import jesse.helpers as jh
from jesse.info import JESSE_API2_URL

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _client_address(request: Request) -> str:
    return request.client.host if request.client else ''


@router.post("/login")
def login(json_request: LoginRequestJson, request: Request):
    """
    Authenticate user with password and return a token
    """
    return authenticator.password_to_token(json_request.password, _client_address(request))


@router.post("/user-validation")
def user_validation(json_request: LoginRequestJson, request: Request):
    """
    Authenticate user with password and return a token
    """
    return authenticator.user_validation(json_request.password, _client_address(request))


@router.post("")
def auth(json_request: LoginRequestJson, request: Request):
    """
    Authenticate user with password and return a token
    """
    return authenticator.password_to_token(json_request.password, _client_address(request))


@router.post("/refresh", dependencies=[Depends(require_auth)])
def refresh():
    """
    A new session token for a signed-in dashboard, so a session that is used stays signed in.
    It also replaces the password-derived token older dashboards kept in the browser.
    """
    return JSONResponse({'auth_token': authenticator.issue_session_token()})


@router.post("/link-token", dependencies=[Depends(require_auth)])
def link_token():
    """
    A short-lived token for the URLs the browser opens without an Authorization header:
    the websocket, the code editor, downloads and chart images.
    """
    return JSONResponse({
        'token': authenticator.issue_link_token(),
        'expires_in': authenticator.LINK_TOKEN_SECONDS,
    })


@router.post("/mcp-token", dependencies=[Depends(require_auth)])
def mcp_token():
    """The never-expiring token AI assistants connect to the MCP endpoint with."""
    return JSONResponse({'token': authenticator.static_token()})


@router.post("/shutdown", dependencies=[Depends(require_auth)])
async def shutdown(background_tasks: BackgroundTasks):
    """
    Shutdown the application
    """

    background_tasks.add_task(jh.terminate_app)
    return JSONResponse({'message': 'Shutting down...'})


@router.post("/jesse-trade-token", dependencies=[Depends(require_auth)])
def jesse_trade_token():
    """
    Exchange LICENSE_API_TOKEN for jesse.trade bearer token

    A plain `def` so FastAPI runs the blocking licensing request in its threadpool, keeping
    the event loop free for other routes while jesse.trade answers.
    """

    if 'LICENSE_API_TOKEN' not in ENV_VALUES or not ENV_VALUES['LICENSE_API_TOKEN']:
        return JSONResponse({
            'status': 'error',
            'message': 'LICENSE_API_TOKEN not found in .env file'
        }, status_code=400)

    license_token = ENV_VALUES['LICENSE_API_TOKEN']
    
    try:
        response = requests.post(
            f'{JESSE_API2_URL}/auth/exchange-token',
            json={'license_api_token': license_token},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            return JSONResponse({
                'status': 'success',
                'access_token': data.get('access_token'),
                'user': data.get('user')
            })
        else:
            return JSONResponse({
                'status': 'error',
                'message': f'Failed to exchange token: {response.text}'
            }, status_code=response.status_code)
    except requests.exceptions.RequestException as e:
        return JSONResponse({
            'status': 'error',
            'message': f'Error connecting to jesse.trade: {str(e)}'
        }, status_code=500)
