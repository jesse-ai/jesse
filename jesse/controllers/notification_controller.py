from jesse.services.auth import require_auth
from typing import Optional
from fastapi import APIRouter, Header, Depends
from fastapi.responses import JSONResponse

from jesse.services.web import StoreNotificationApiKeyRequestJson, DeleteNotificationApiKeyRequestJson

router = APIRouter(prefix="/notification", tags=["Notification"])


@router.get("/api-keys")
def get_notification_api_keys(authorization: Optional[str] = Header(None),
    _auth: None = Depends(require_auth)) -> JSONResponse:
    """
    Get all notification API keys
    """

    from jesse.modes.notification_api_keys import get_notification_api_keys

    return get_notification_api_keys()


@router.post("/api-keys/store")
def store_notification_api_keys(
        json_request: StoreNotificationApiKeyRequestJson,
        authorization: Optional[str] = Header(None),
    _auth: None = Depends(require_auth)
) -> JSONResponse:
    """
    Store a new notification API key
    """

    from jesse.modes.notification_api_keys import store_notification_api_keys

    return store_notification_api_keys(
        json_request.name, json_request.driver, json_request.fields
    )


@router.post("/api-keys/delete")
def delete_notification_api_keys(
        json_request: DeleteNotificationApiKeyRequestJson,
        authorization: Optional[str] = Header(None),
    _auth: None = Depends(require_auth)
) -> JSONResponse:
    """
    Delete a notification API key
    """

    from jesse.modes.notification_api_keys import delete_notification_api_keys

    return delete_notification_api_keys(json_request.id)
