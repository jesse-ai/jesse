from typing import Optional
from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse

from jesse.services import auth as authenticator
from jesse.repositories import order_repository
from jesse.services.transformers import get_order_details
from jesse.models.Order import Order

router = APIRouter(prefix="/orders", tags=["Orders"])


@router.get("/{order_id}")
def get_order_by_id(order_id: str, authorization: Optional[str] = Header(None)) -> JSONResponse:
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    try:
        # Fetch order by ID
        order: Order | None = order_repository.find_by_id(order_id)
        
        if not order:
            return JSONResponse({
                'error': 'Order not found'
            }, status_code=404)
        
        # Transform order with details
        order_details = get_order_details(order)
        
        return JSONResponse({
            'data': order_details
        }, status_code=200)
    except Exception as e:
        import traceback
        import jesse.helpers as jh
        jh.debug(f"Error fetching order {order_id}: {str(e)}")
        jh.debug(traceback.format_exc())
        return JSONResponse({
            'error': str(e)
        }, status_code=500)

