from fastapi import APIRouter, Query, Header
from typing import Optional

from jesse.services import auth as authenticator
from jesse.modes import data_provider
import jesse.helpers as jh
router = APIRouter(prefix="/download", tags=["Download"])


@router.get("/{mode}/{file_type}/{session_id}")
def download(mode: str, file_type: str, session_id: str, token: str = Query(...)):
    """
    Download files such as logs or other generated files.
    Log files require session_id because there is one log per each session. Except for the optimize mode.
    """
    if not authenticator.is_valid_token(token):
        return authenticator.unauthorized_response()

    return data_provider.download_file(mode, file_type, session_id)


@router.post("/download-api-keys")
def download_api_keys(authorization: Optional[str] = Header(None)):
    """
    Download API Keys
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    jh.validate_cwd()

    return data_provider.download_api_keys()
