from typing import Optional
from fastapi import APIRouter, Header, BackgroundTasks
from fastapi.responses import JSONResponse

from jesse.services import auth as authenticator
from jesse.services.multiprocessing import process_manager
from jesse.services.web import LoginRequestJson
import jesse.helpers as jh

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login")
def login(json_request: LoginRequestJson):
    """
    Authenticate user with password and return a token
    """
    return authenticator.password_to_token(json_request.password)


@router.post("/terminate-all")
async def terminate_all(authorization: Optional[str] = Header(None)):
    """
    Terminate all running processes
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    process_manager.flush()
    return JSONResponse({'message': 'terminating all tasks...'})


@router.post("/shutdown")
async def shutdown(background_tasks: BackgroundTasks, authorization: Optional[str] = Header(None)):
    """
    Shutdown the application
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    background_tasks.add_task(jh.terminate_app)
    return JSONResponse({'message': 'Shutting down...'})
