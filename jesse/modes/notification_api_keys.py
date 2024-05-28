import json
from starlette.responses import JSONResponse
import jesse.helpers as jh
from jesse.services import transformers


def get_notification_api_keys() -> JSONResponse:
    from jesse.services.db import database
    database.open_connection()

    from jesse.models.NotificationApiKeys import NotificationApiKeys

    try:
        # fetch all the notification api keys
        api_keys = NotificationApiKeys.select()
    except Exception as e:
        database.close_connection()
        return JSONResponse({
            'status': 'error',
            'message': str(e)
        }, status_code=500)

    # transform each api_key using transformers.get_notification_api_key()
    api_keys = [transformers.get_notification_api_key(api_key) for api_key in api_keys]

    database.close_connection()

    return JSONResponse({
        'data': api_keys
    }, status_code=200)


def store_notification_api_keys(
        name: str,
        driver: str,
        fields: dict
) -> JSONResponse:
    from jesse.services.db import database
    database.open_connection()

    from jesse.models.NotificationApiKeys import NotificationApiKeys

    # check if the api key already exists
    if NotificationApiKeys.select().where(NotificationApiKeys.name == name).exists():
        database.close_connection()
        return JSONResponse({
            'status': 'error',
            'message': f'API key for the name "{name}" already exists. Please choose another driver.'
        }, status_code=400)

    try:
        # create the record
        notification_api_key: NotificationApiKeys = NotificationApiKeys.create(
            id=jh.generate_unique_id(),
            name=name,
            driver=driver,
            fields=json.dumps(fields),
            created_at=jh.now_to_datetime()
        )
    except ValueError as e:
        database.close_connection()
        return JSONResponse({
            'status': 'error',
            'message': str(e)
        }, status_code=400)
    except Exception as e:
        database.close_connection()
        return JSONResponse({
            'status': 'error',
            'message': str(e)
        }, status_code=500)

    database.close_connection()

    return JSONResponse({
        'status': 'success',
        'message': 'Notification API key has been stored successfully.',
        'data': transformers.get_notification_api_key(notification_api_key)
    }, status_code=200)


def delete_notification_api_keys(notification_api_key_id: str) -> JSONResponse:
    from jesse.services.db import database
    database.open_connection()

    from jesse.models.NotificationApiKeys import NotificationApiKeys

    try:
        # delete the record
        NotificationApiKeys.delete().where(NotificationApiKeys.id == notification_api_key_id).execute()
    except Exception as e:
        database.close_connection()
        return JSONResponse({
            'status': 'error',
            'message': str(e)
        }, status_code=500)

    database.close_connection()

    return JSONResponse({
        'status': 'success',
        'message': 'Notification API key has been deleted successfully.'
    }, status_code=200)
