from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from jesse.services.auth import require_auth
from jesse.services.web import StoreNotificationApiKeyRequestJson, DeleteNotificationApiKeyRequestJson

router = APIRouter(prefix="/notification", tags=["Notification"], dependencies=[Depends(require_auth)])


@router.get("/api-keys")
def get_notification_api_keys() -> JSONResponse:
    """
    Get all notification API keys
    """

    from jesse.modes.notification_api_keys import get_notification_api_keys

    return get_notification_api_keys()


@router.post("/api-keys/store")
def store_notification_api_keys(
        json_request: StoreNotificationApiKeyRequestJson,
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
) -> JSONResponse:
    """
    Delete a notification API key
    """

    from jesse.modes.notification_api_keys import delete_notification_api_keys

    return delete_notification_api_keys(json_request.id)
