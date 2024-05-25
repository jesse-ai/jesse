from jesse.models.ExchangeApiKeys import ExchangeApiKeys


def get_exchange_api_key(exchange_api_key: ExchangeApiKeys) -> dict:
    result = {
        'id': exchange_api_key.id,
        'exchange': exchange_api_key.exchange_name,
        'name': exchange_api_key.name,
        'api_key': exchange_api_key.api_key[0:4] + '***...***' + exchange_api_key.api_key[-4:],
        'api_secret': exchange_api_key.api_secret[0:4] + '***...***' + exchange_api_key.api_secret[-4:],
        'created_at': exchange_api_key.created_at.isoformat()
    }

    # additional fields
    if exchange_api_key.additional_fields:
        for key, value in exchange_api_key.additional_fields.items():
            result[key] = value[0:4] + '***...***' + value[-4:]

    return result
