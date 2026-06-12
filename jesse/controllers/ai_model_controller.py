from typing import Optional
from fastapi import APIRouter, Header
from starlette.responses import JSONResponse

import jesse.helpers as jh
from jesse.services import auth as authenticator
from jesse.services import transformers
from jesse.services.web import StoreAiModelRequestJson, DeleteAiModelRequestJson


router = APIRouter(prefix="/ai-models", tags=["AI Models"])


@router.get('')
def get_ai_models_endpoint(authorization: Optional[str] = Header(None)) -> JSONResponse:
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.services.db import database
    database.open_connection()

    from jesse.models.AiModel import AiModel

    try:
        models = AiModel.select()
    except Exception as e:
        database.close_connection()
        return JSONResponse({
            'status': 'error',
            'message': str(e)
        }, status_code=500)

    models = [transformers.get_ai_model(m) for m in models]

    database.close_connection()

    return JSONResponse({
        'data': models
    }, status_code=200)


@router.post('/store')
def store_ai_model_endpoint(json_request: StoreAiModelRequestJson,
                            authorization: Optional[str] = Header(None)) -> JSONResponse:
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.services.db import database
    database.open_connection()

    from jesse.models.AiModel import AiModel

    try:
        ai_model: AiModel = AiModel.create(
            id=jh.generate_unique_id(),
            name=json_request.name,
            provider=json_request.provider,
            base_url=json_request.base_url,
            api_key=json_request.api_key,
            model_id=json_request.model_id,
            created_at=jh.now_to_datetime(),
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
        'message': 'Model has been stored successfully.',
        'data': transformers.get_ai_model(ai_model)
    }, status_code=200)


@router.post('/delete')
def delete_ai_model_endpoint(json_request: DeleteAiModelRequestJson,
                             authorization: Optional[str] = Header(None)) -> JSONResponse:
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.services.db import database
    database.open_connection()

    from jesse.models.AiModel import AiModel

    try:
        AiModel.delete().where(AiModel.id == json_request.id).execute()
    except Exception as e:
        database.close_connection()
        return JSONResponse({
            'status': 'error',
            'message': str(e)
        }, status_code=500)

    database.close_connection()

    return JSONResponse({
        'status': 'success',
        'message': 'Model has been deleted successfully.'
    }, status_code=200)
