from typing import Optional
from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse

from jesse.services import auth as authenticator
from jesse.services.web import StoreNotificationApiKeyRequestJson, DeleteNotificationApiKeyRequestJson

router = APIRouter(prefix="/notification", tags=["Notification"])


@router.get("/api-keys")
def get_notification_api_keys(authorization: Optional[str] = Header(None)) -> JSONResponse:
    """
    Get all notification API keys
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.modes.notification_api_keys import get_notification_api_keys

    return get_notification_api_keys()


@router.post("/api-keys/store")
def store_notification_api_keys(
        json_request: StoreNotificationApiKeyRequestJson,
        authorization: Optional[str] = Header(None)
) -> JSONResponse:
    """
    Store a new notification API key
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.modes.notification_api_keys import store_notification_api_keys

    return store_notification_api_keys(
        json_request.name, json_request.driver, json_request.fields
    )


@router.post("/api-keys/delete")
def delete_notification_api_keys(
        json_request: DeleteNotificationApiKeyRequestJson,
        authorization: Optional[str] = Header(None)
) -> JSONResponse:
    """
    Delete a notification API key
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.modes.notification_api_keys import delete_notification_api_keys

    return delete_notification_api_keys(json_request.id)
