from fastapi import APIRouter, Depends
from pydantic import BaseModel, SecretStr
from starlette.responses import JSONResponse

from jesse.enums import data_providers
from jesse.repositories import data_provider_credentials_repository
from jesse.services.auth import require_auth
from jesse.services.historical_data.credential_validation import validate_massive_api_key
from jesse.services.historical_data.errors import (
    ProviderAuthenticationError,
    ProviderEntitlementError,
    ProviderRateLimitError,
    ProviderRequestError,
    ProviderUnavailableError,
)


router = APIRouter(
    prefix='/data-providers',
    tags=['Data Providers'],
    dependencies=[Depends(require_auth)],
)


class CredentialFieldResponse(BaseModel):
    key: str
    label: str
    secret: bool


class DataProviderCredentialStatusResponse(BaseModel):
    provider_id: str
    name: str
    credential_fields: list[CredentialFieldResponse]
    configured: bool
    created_at: int | None
    updated_at: int | None


class DataProviderCredentialsListResponse(BaseModel):
    data: list[DataProviderCredentialStatusResponse]


class DataProviderCredentialMutationResponse(BaseModel):
    status: str
    message: str
    data: DataProviderCredentialStatusResponse


class DataProviderCredentialValidationResponse(BaseModel):
    status: str
    message: str


class StoreDataProviderCredentialsRequest(BaseModel):
    provider_id: str
    api_key: SecretStr


class DeleteDataProviderCredentialsRequest(BaseModel):
    provider_id: str


class ValidateDataProviderCredentialsRequest(BaseModel):
    provider_id: str


def _unsupported_provider_response() -> JSONResponse:
    return JSONResponse({'message': 'Unsupported data provider'}, status_code=400)


@router.get('/credentials', response_model=DataProviderCredentialsListResponse)
def list_data_provider_credentials() -> DataProviderCredentialsListResponse | JSONResponse:
    try:
        statuses = data_provider_credentials_repository.get_data_provider_credential_statuses()
    except Exception:
        return JSONResponse({'message': 'Unable to load data provider credentials'}, status_code=500)
    return DataProviderCredentialsListResponse(data=statuses)


@router.post('/credentials/store', response_model=DataProviderCredentialMutationResponse)
def store_data_provider_credentials(
    request: StoreDataProviderCredentialsRequest,
) -> DataProviderCredentialMutationResponse | JSONResponse:
    if request.provider_id != data_providers.MASSIVE:
        return _unsupported_provider_response()
    api_key = request.api_key.get_secret_value().strip()
    if not api_key:
        return JSONResponse({'message': 'API key must not be empty'}, status_code=400)

    try:
        status = data_provider_credentials_repository.store_data_provider_credentials(
            request.provider_id,
            {'api_key': api_key},
        )
    except data_provider_credentials_repository.DataProviderCredentialsAlreadyConfigured:
        return JSONResponse(
            {'message': 'Delete the existing data provider credentials before adding new ones'},
            status_code=409,
        )
    except Exception:
        # Database exceptions may contain bound values, so never expose their text here.
        return JSONResponse({'message': 'Unable to store data provider credentials'}, status_code=500)
    return DataProviderCredentialMutationResponse(
        status='success',
        message='Data provider credentials have been stored successfully.',
        data=status,
    )


@router.post('/credentials/delete', response_model=DataProviderCredentialMutationResponse)
def delete_data_provider_credentials(
    request: DeleteDataProviderCredentialsRequest,
) -> DataProviderCredentialMutationResponse | JSONResponse:
    if request.provider_id != data_providers.MASSIVE:
        return _unsupported_provider_response()
    try:
        status = data_provider_credentials_repository.delete_data_provider_credentials(request.provider_id)
    except Exception:
        return JSONResponse({'message': 'Unable to delete data provider credentials'}, status_code=500)
    return DataProviderCredentialMutationResponse(
        status='success',
        message='Data provider credentials have been deleted successfully.',
        data=status,
    )


@router.post('/credentials/validate', response_model=DataProviderCredentialValidationResponse)
def validate_data_provider_credentials(
    request: ValidateDataProviderCredentialsRequest,
) -> DataProviderCredentialValidationResponse | JSONResponse:
    if request.provider_id != data_providers.MASSIVE:
        return _unsupported_provider_response()
    try:
        credentials = data_provider_credentials_repository.get_data_provider_credentials(request.provider_id)
    except Exception:
        return JSONResponse({'message': 'Unable to load data provider credentials'}, status_code=500)
    if credentials is None:
        return JSONResponse({'message': 'No API key is configured for this data provider'}, status_code=404)
    api_key = credentials.get('api_key')
    if not api_key:
        return JSONResponse({'message': 'The stored data provider credentials are invalid'}, status_code=500)

    try:
        validate_massive_api_key(api_key)
    except ProviderAuthenticationError:
        return JSONResponse({'message': 'Massive rejected the API key'}, status_code=401)
    except ProviderEntitlementError:
        return JSONResponse({'message': 'The API key cannot access Massive reference data'}, status_code=403)
    except ProviderRateLimitError:
        return JSONResponse({'message': 'Massive rate limit reached. Try again shortly.'}, status_code=429)
    except ProviderUnavailableError:
        return JSONResponse({'message': 'Massive is currently unavailable'}, status_code=503)
    except ProviderRequestError:
        return JSONResponse({'message': 'Massive could not validate the API key'}, status_code=502)

    return DataProviderCredentialValidationResponse(
        status='success',
        message='Massive API key is working.',
    )
