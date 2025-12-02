from typing import Optional
from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse

from jesse.services import auth as authenticator
from jesse.repositories import closed_trade_repository
from jesse.services.transformers import get_closed_trade_for_list, get_closed_trade_details

router = APIRouter(prefix="/closed-trades", tags=["Closed Trades"])


@router.get("/list")
def get_closed_trades(
    session_id: str = Query(...), 
    limit: int = Query(10, ge=1, le=1000),
    authorization: Optional[str] = Header(None)
) -> JSONResponse:
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()
    
    try:
        # Query trades for the session with limit
        trades = closed_trade_repository.find_by_session_id(session_id, limit=limit)
        
        # Transform trades for list view
        trades_list = [get_closed_trade_for_list(trade) for trade in trades]
        
        return JSONResponse({
            'data': trades_list
        }, status_code=200)
    except Exception as e:
        return JSONResponse({
            'error': str(e)
        }, status_code=500)


@router.get("/{trade_id}")
def get_closed_trade_by_id(trade_id: str, authorization: Optional[str] = Header(None)) -> JSONResponse:
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()
    
    try:
        # Fetch trade by ID
        trade = closed_trade_repository.find_by_id(trade_id)
        
        if not trade:
            return JSONResponse({
                'error': 'Trade not found'
            }, status_code=404)
        
        # Transform trade with full details including orders
        trade_details = get_closed_trade_details(trade)
        
        return JSONResponse({
            'data': trade_details
        }, status_code=200)
    except Exception as e:
        return JSONResponse({
            'error': str(e)
        }, status_code=500)

