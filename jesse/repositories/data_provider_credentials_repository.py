import json
import time
from typing import Any

import peewee

from jesse.enums import data_providers
from jesse.models.DataProviderCredentials import DataProviderCredentials
from jesse.services.db import database


SUPPORTED_DATA_PROVIDERS: dict[str, dict[str, Any]] = {
    data_providers.MASSIVE: {
        'name': data_providers.MASSIVE,
        'credential_fields': (
            {'key': 'api_key', 'label': 'API Key', 'secret': True},
        ),
    },
}


class DataProviderCredentialsAlreadyConfigured(Exception):
    pass


def _ensure_db_open() -> None:
    if not database.is_open():
        database.open_connection()


def _model_database() -> peewee.Database:
    """Use the model connection so atomic blocks roll back before HTTP handlers suppress errors."""
    _ensure_db_open()
    return DataProviderCredentials._meta.database


def _now_ms() -> int:
    return int(time.time() * 1000)


def _provider_status(provider_id: str, record: DataProviderCredentials | None) -> dict[str, Any]:
    provider = SUPPORTED_DATA_PROVIDERS[provider_id]
    return {
        'provider_id': provider_id,
        'name': provider['name'],
        'credential_fields': provider['credential_fields'],
        'configured': record is not None,
        'created_at': record.created_at if record is not None else None,
        'updated_at': record.updated_at if record is not None else None,
    }


def get_data_provider_credential_statuses() -> list[dict[str, Any]]:
    """Return provider configuration state without exposing credential values."""
    with _model_database().atomic():
        records = {
            record.provider_id: record
            for record in DataProviderCredentials.select().where(
                DataProviderCredentials.provider_id.in_(tuple(SUPPORTED_DATA_PROVIDERS))
            )
        }
    return [
        _provider_status(provider_id, records.get(provider_id))
        for provider_id in SUPPORTED_DATA_PROVIDERS
    ]


def store_data_provider_credentials(provider_id: str, credentials: dict[str, str]) -> dict[str, Any]:
    """Store credentials only when the provider has no existing credential row."""
    now = _now_ms()
    serialized_credentials = json.dumps(credentials, separators=(',', ':'), sort_keys=True)
    try:
        with _model_database().atomic():
            DataProviderCredentials.create(
                provider_id=provider_id,
                credentials=serialized_credentials,
                created_at=now,
                updated_at=now,
            )
            record = DataProviderCredentials.get_by_id(provider_id)
    except peewee.IntegrityError as exc:
        raise DataProviderCredentialsAlreadyConfigured(
            'Delete the existing credentials before adding new ones'
        ) from exc
    return _provider_status(provider_id, record)


def delete_data_provider_credentials(provider_id: str) -> dict[str, Any]:
    with _model_database().atomic():
        DataProviderCredentials.delete_by_id(provider_id)
    return _provider_status(provider_id, None)


def get_data_provider_credentials(provider_id: str) -> dict[str, str] | None:
    """Return raw credentials for internal provider use only, never HTTP responses."""
    with _model_database().atomic():
        record = DataProviderCredentials.get_or_none(DataProviderCredentials.provider_id == provider_id)
    if record is None:
        return None
    credentials = json.loads(record.credentials)
    if not isinstance(credentials, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in credentials.items()
    ):
        raise ValueError(f'Invalid stored credential payload for provider {provider_id!r}')
    return credentials
