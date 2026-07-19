from fastapi import APIRouter, BackgroundTasks, Depends
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


@router.post("/login")
def login(json_request: LoginRequestJson):
    """
    Authenticate user with password and return a token
    """
    return authenticator.password_to_token(json_request.password)


@router.post("/user-validation")
def login(json_request: LoginRequestJson):
    """
    Authenticate user with password and return a token
    """
    return authenticator.user_validation(json_request.password)


@router.post("")
def auth(json_request: LoginRequestJson):
    """
    Authenticate user with password and return a token
    """
    return authenticator.password_to_token(json_request.password)


@router.post("/shutdown", dependencies=[Depends(require_auth)])
async def shutdown(background_tasks: BackgroundTasks):
    """
    Shutdown the application
    """

    background_tasks.add_task(jh.terminate_app)
    return JSONResponse({'message': 'Shutting down...'})


@router.post("/jesse-trade-token", dependencies=[Depends(require_auth)])
async def jesse_trade_token():
    """
    Exchange LICENSE_API_TOKEN for jesse.trade bearer token
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
