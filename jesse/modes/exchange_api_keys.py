from typing import Optional
from starlette.responses import JSONResponse
from jesse.info import live_trading_exchanges
import jesse.helpers as jh


def get_api_keys():
    from jesse.services.db import database
    database.open_connection()

    from jesse.models.ExchangeApiKeys import ExchangeApiKeys

    # fetch all the api keys
    api_keys = ExchangeApiKeys.select().dicts()

    database.close_connection()

    return JSONResponse({
        'api_keys': list(api_keys)
    }, status_code=200)


def store_api_keys(exchange: str, name: str, api_key: str, api_secret: str, additional_fields: Optional[dict] = None):
    # validate the exchange
    if exchange not in live_trading_exchanges:
        raise ValueError(f'Invalid exchange: {exchange}')

    from jesse.services.db import database
    database.open_connection()

    from jesse.models.ExchangeApiKeys import ExchangeApiKeys

    # check if the api key already exists
    if ExchangeApiKeys.select().where(ExchangeApiKeys.name == name).exists():
        raise ValueError(f'API key with the name "{name}" already exists. Please choose another name.')

    try:
        # create the record
        ExchangeApiKeys.create(
            exchange_name=exchange,
            name=name,
            api_key=api_key,
            api_secret=api_secret,
            additional_fields=additional_fields,
            created_at=jh.now(True)
        )
    except Exception as e:
        database.close_connection()
        return JSONResponse({
            'status': 'error',
            'message': str(e)
        }, status_code=500)

    database.close_connection()

    return JSONResponse({
        'status': 'success',
        'message': 'API key has been stored successfully.'
    }, status_code=200)


def delete_api_keys(exchange_api_key_id: str):
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
