import json
from typing import Optional
from starlette.responses import JSONResponse
from jesse.info import live_trading_exchanges
import jesse.helpers as jh
from jesse.services import transformers


def get_exchange_api_keys() -> JSONResponse:
    from jesse.services.db import database
    database.open_connection()

    from jesse.models.ExchangeApiKeys import ExchangeApiKeys

    try:
        # fetch all the api keys
        api_keys = ExchangeApiKeys.select()
    except Exception as e:
        database.close_connection()
        return JSONResponse({
            'status': 'error',
            'message': str(e)
        }, status_code=500)

    # transform each api_key using transformers.get_exchange_api_key()
    api_keys = [transformers.get_exchange_api_key(api_key) for api_key in api_keys]

    database.close_connection()

    return JSONResponse({
        'data': api_keys
    }, status_code=200)


def store_exchange_api_keys(
        exchange: str,
        name: str,
        api_key: str,
        api_secret: str,
        additional_fields: Optional[dict] = None,
        general_notifications_id: Optional[str] = None,
        error_notifications_id: Optional[str] = None,
) -> JSONResponse:
    # validate the exchange
    if exchange not in live_trading_exchanges:
        return JSONResponse({
            'status': 'error',
            'message': f'Invalid exchange: {exchange}'
        }, status_code=400)

    from jesse.services.db import database
    database.open_connection()

    from jesse.models.ExchangeApiKeys import ExchangeApiKeys

    # check if the api key already exists
    if ExchangeApiKeys.select().where(ExchangeApiKeys.name == name).exists():
        database.close_connection()
        return JSONResponse({
            'status': 'error',
            'message': f'API key with the name "{name}" already exists. Please choose another name.'
        }, status_code=400)

    # Ensure additional_fields is a dictionary
    if additional_fields is None:
        additional_fields = {}

    try:
        # create the record
        exchange_api_key: ExchangeApiKeys = ExchangeApiKeys.create(
            id=jh.generate_unique_id(),
            exchange_name=exchange,
            name=name,
            api_key=api_key,
            api_secret=api_secret,
            additional_fields=json.dumps(additional_fields),
            created_at=jh.now_to_datetime(),
            general_notifications_id=general_notifications_id if general_notifications_id else None,
            error_notifications_id=error_notifications_id if error_notifications_id else None
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
        'message': 'API key has been stored successfully.',
        'data': transformers.get_exchange_api_key(exchange_api_key)
    }, status_code=200)


def delete_exchange_api_keys(exchange_api_key_id: str) -> JSONResponse:
    from jesse.services.db import database
    database.open_connection()

    from jesse.models.ExchangeApiKeys import ExchangeApiKeys

    try:
        # delete the record
        ExchangeApiKeys.delete().where(ExchangeApiKeys.id == exchange_api_key_id).execute()
    except Exception as e:
        database.close_connection()
        return JSONResponse({
            'status': 'error',
            'message': str(e)
        }, status_code=500)

    database.close_connection()

    return JSONResponse({
        'status': 'success',
        'message': 'API key has been deleted successfully.'
    }, status_code=200)
