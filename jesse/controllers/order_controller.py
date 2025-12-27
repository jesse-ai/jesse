from typing import Optional
from fastapi import APIRouter, Header, Body
from fastapi.responses import JSONResponse

from jesse.services import auth as authenticator
from jesse.repositories import order_repository
from jesse.services.transformers import get_order_details
from jesse.models.Order import Order
from jesse.services.web import GetOrdersHistoryRequestJson

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


@router.post("/live-history")
def get_orders_live_history(
    request_json: GetOrdersHistoryRequestJson = Body(...),
    authorization: Optional[str] = Header(None)
) -> JSONResponse:
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    try:
        # Fetch orders with filters
        orders = order_repository.find_by_filters(
            id_search=request_json.id_search,
            status_filter=request_json.status_filter,
            symbol_filter=request_json.symbol_filter,
            date_filter=request_json.date_filter,
            exchange_filter=request_json.exchange_filter,
            type_filter=request_json.type_filter,
            side_filter=request_json.side_filter,
            limit=request_json.limit,
            offset=request_json.offset
        )
        
        # Transform orders using transformer (handles UUID conversion)
        orders_list = [get_order_details(order) for order in orders]
        
        return JSONResponse({
            'orders': orders_list
        }, status_code=200)
    except Exception as e:
        import traceback
        import jesse.helpers as jh
        jh.debug(f"Error fetching orders history: {str(e)}")
        jh.debug(traceback.format_exc())
        return JSONResponse({
            'error': str(e)
        }, status_code=500)

