from fastapi import APIRouter, Query, Header, UploadFile, Form, File
from typing import Optional

from jesse.services import auth as authenticator
from jesse.modes import data_provider
from jesse.services.web import ImportApiKeyRequestJson
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


@router.post("/import-api-keys")
async def import_api_keys(
    request_json: ImportApiKeyRequestJson,
    authorization: Optional[str] = Header(None)
):
    """
    Import API keys from CSV text received in the request body.
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    try:
        csv_content = request_json.content.strip()           # remove leading/trailing whitespace

        # Validate CSV content
        if not data_provider.validate_csv_content(csv_content):
            return {
                'success': False,
                'error': 'Invalid CSV content or potential security threat detected'
            }

        # Import API keys
        result = data_provider.import_api_keys_from_csv(csv_content)

        return result
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }
