from fastapi import APIRouter, UploadFile, Form, File, Depends

from jesse.services.auth import require_auth, require_auth_token, unauthorized_response
from jesse.modes import data_provider
from jesse.services.web import ImportApiKeyRequestJson, LoginRequestJson
from jesse.services.env import ENV_VALUES
import jesse.helpers as jh
router = APIRouter(prefix="/download", tags=["Download"])


@router.get("/{mode}/{file_type}/{session_id}", dependencies=[Depends(require_auth_token)])
def download(mode: str, file_type: str, session_id: str):
    """
    Download files such as logs or other generated files.
    Log files require session_id because there is one log per each session. Except for the optimize mode.
    """

    return data_provider.download_file(mode, file_type, session_id)


@router.post("/download-api-keys", dependencies=[Depends(require_auth)])
def download_api_keys(
    request_json: LoginRequestJson,
):
    """
    Download exchange API Keys - requires password verification
    """

    # Verify password for this sensitive operation
    if request_json.password != ENV_VALUES['PASSWORD']:
        return unauthorized_response()

    jh.validate_cwd()

    return data_provider.download_api_keys()


@router.post("/import-api-keys", dependencies=[Depends(require_auth)])
async def import_api_keys(
    request_json: ImportApiKeyRequestJson,
):
    """
    Import exchange API keys from CSV text received in the request body.
    """

    try:
        # remove leading/trailing whitespace
        csv_content = request_json.content.strip()           

        # validate CSV content
        if not data_provider.validate_csv_content(csv_content):
            return {
                'success': False,
                'error': 'Invalid CSV content or potential security threat detected'
            }

        # import exchange API keys
        result = data_provider.import_api_keys_from_csv(csv_content)

        return result
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


@router.post("/download-notification-api-keys", dependencies=[Depends(require_auth)])
def download_notification_api_keys(
    request_json: LoginRequestJson,
):
    """
    Download notification API keys - requires password verification
    """

    if request_json.password != ENV_VALUES['PASSWORD']:
        return unauthorized_response()

    jh.validate_cwd()

    return data_provider.download_notification_api_keys()


@router.post("/import-notification-api-keys", dependencies=[Depends(require_auth)])
async def import_notification_api_keys(
    request_json: ImportApiKeyRequestJson,
):
    """
    Import notification API keys from CSV text received in the request body.
    """

    try:
        csv_content = request_json.content.strip()

        if not data_provider.validate_notification_csv_content(csv_content):
            return {
                'success': False,
                'error': 'Invalid CSV content or potential security threat detected'
            }

        result = data_provider.import_notification_api_keys_from_csv(csv_content)
        return result
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }
