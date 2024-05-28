from jesse.models.ExchangeApiKeys import ExchangeApiKeys
from jesse.models.NotificationApiKeys import NotificationApiKeys
import json


def get_exchange_api_key(exchange_api_key: ExchangeApiKeys) -> dict:
    if exchange_api_key.general_notifications_id:
        exchange_api_key.notifications = NotificationApiKeys.get(NotificationApiKeys.id == exchange_api_key.general_notifications_id)
    if exchange_api_key.error_notifications_id:
        exchange_api_key.error_notifications = NotificationApiKeys.get(NotificationApiKeys.id == exchange_api_key.error_notifications_id)

    result = {
        'id': str(exchange_api_key.id),
        'exchange': exchange_api_key.exchange_name,
        'name': exchange_api_key.name,
        'api_key': exchange_api_key.api_key[0:4] + '***...***' + exchange_api_key.api_key[-4:],
        'api_secret': exchange_api_key.api_secret[0:4] + '***...***' + exchange_api_key.api_secret[-4:],
        'created_at': exchange_api_key.created_at.isoformat(),
        'general_notifications': None if exchange_api_key.general_notifications_id is None else get_notification_api_key(exchange_api_key.general_notifications_id),
        'error_notifications': None if exchange_api_key.error_notifications_id is None else get_notification_api_key(exchange_api_key.error_notifications_id)
    }

    if type(exchange_api_key.additional_fields) == str:
        exchange_api_key.additional_fields = json.loads(exchange_api_key.additional_fields)

    # additional fields
    if exchange_api_key.additional_fields:
        for key, value in exchange_api_key.additional_fields.items():
            result[key] = value[0:4] + '***...***' + value[-4:]

    return result


def get_notification_api_key(api_key: NotificationApiKeys) -> dict:
    result = {
        'id': str(api_key.id),
        'name': api_key.name,
        'driver': api_key.driver,
        'created_at': api_key.created_at.isoformat()
    }

    # Parse the fields from the JSON string
    fields = json.loads(api_key.fields)

    # Add each field to the result
    for key, value in fields.items():
        result[key] = value[0:4] + '***...***' + value[-4:]

    return result
