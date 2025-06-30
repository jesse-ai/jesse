from fastapi import APIRouter, Query

from jesse.services import auth as authenticator
from jesse.modes import data_provider


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
