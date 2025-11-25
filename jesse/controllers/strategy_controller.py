from typing import Optional
from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse
import requests
import re

from jesse.services import auth as authenticator
from jesse.services.web import (
    NewStrategyRequestJson,
    GetStrategyRequestJson,
    SaveStrategyRequestJson,
    DeleteStrategyRequestJson,
    ImportStrategyRequestJson
)
import jesse.helpers as jh
from jesse.info import JESSE_API2_URL

router = APIRouter(prefix="/strategy", tags=["Strategy"])


@router.post("/make")
def make_strategy(json_request: NewStrategyRequestJson, authorization: Optional[str] = Header(None)) -> JSONResponse:
    """
    Create a new strategy
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.services import strategy_handler
    return strategy_handler.generate(json_request.name)


@router.get("/all")
def get_strategies(authorization: Optional[str] = Header(None)) -> JSONResponse:
    """
    Get all strategies
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.services import strategy_handler
    return strategy_handler.get_strategies()


@router.post("/get")
def get_strategy(
        json_request: GetStrategyRequestJson,
        authorization: Optional[str] = Header(None)
) -> JSONResponse:
    """
    Get a specific strategy
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.services import strategy_handler
    return strategy_handler.get_strategy(json_request.name)


@router.post("/save")
def save_strategy(
        json_request: SaveStrategyRequestJson,
        authorization: Optional[str] = Header(None)
) -> JSONResponse:
    """
    Save a strategy
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.services import strategy_handler
    return strategy_handler.save_strategy(json_request.name, json_request.content)


@router.post("/delete")
def delete_strategy(
        json_request: DeleteStrategyRequestJson,
        authorization: Optional[str] = Header(None)
) -> JSONResponse:
    """
    Delete a strategy
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    from jesse.services import strategy_handler
    return strategy_handler.delete_strategy(json_request.name)


@router.get("/index")
async def index_jesse_trade_strategies(
        period: str = Query(...),
        sort_by: str = Query("Sharpe Ratio"),
        submitted_after: Optional[str] = Query(None),
        submitted_before: Optional[str] = Query(None),
        authorization: Optional[str] = Header(None),
        jesse_trade_token: Optional[str] = Header(None, alias="X-Jesse-Trade-Token")
) -> JSONResponse:
    """
    Browse strategies from jesse.trade
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    try:
        headers = {}
        if jesse_trade_token:
            headers['Authorization'] = f'Bearer {jesse_trade_token}'
            
        params = {'period': period, 'sort_by': sort_by}
        if submitted_after:
            params['submitted_after'] = submitted_after
        if submitted_before:
            params['submitted_before'] = submitted_before

        response = requests.get(
            f'{JESSE_API2_URL}/strategies',
            params=params,
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            return JSONResponse(response.json())
        else:
            return JSONResponse({
                'status': 'error',
                'message': f'Failed to fetch strategies: {response.text}'
            }, status_code=response.status_code)
    except requests.exceptions.RequestException as e:
        return JSONResponse({
            'status': 'error',
            'message': f'Error connecting to jesse.trade: {str(e)}'
        },         status_code=500)


@router.get("/periods")
async def get_jesse_trade_periods(
        authorization: Optional[str] = Header(None)
) -> JSONResponse:
    """
    Get available trading periods from jesse.trade
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    try:
        response = requests.get(
            f'{JESSE_API2_URL}/strategies/periods',
            timeout=10
        )

        if response.status_code == 200:
            return JSONResponse(response.json())
        else:
            return JSONResponse({
                'status': 'error',
                'message': f'Failed to fetch periods: {response.text}'
            }, status_code=response.status_code)
    except requests.exceptions.RequestException as e:
        return JSONResponse({
            'status': 'error',
            'message': f'Error connecting to jesse.trade: {str(e)}'
        }, status_code=500)


@router.get("/jesse-trade/{slug}")
async def get_jesse_trade_strategy(
        slug: str,
        authorization: Optional[str] = Header(None),
        jesse_trade_token: Optional[str] = Header(None, alias="X-Jesse-Trade-Token")
) -> JSONResponse:
    """
    Get a specific strategy from jesse.trade
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    try:
        headers = {}
        if jesse_trade_token:
            headers['Authorization'] = f'Bearer {jesse_trade_token}'
            
        response = requests.get(
            f'{JESSE_API2_URL}/strategies/{slug}',
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            return JSONResponse(response.json())
        else:
            return JSONResponse({
                'status': 'error',
                'message': f'Failed to fetch strategy: {response.text}'
            }, status_code=response.status_code)
    except requests.exceptions.RequestException as e:
        return JSONResponse({
            'status': 'error',
            'message': f'Error connecting to jesse.trade: {str(e)}'
        }, status_code=500)


@router.get("/jesse-trade/{slug}/metrics")
async def get_jesse_trade_strategy_metrics(
        slug: str,
        period: str = Query(...),
        symbol: str = Query(...),
        timeframe: str = Query(...),
        authorization: Optional[str] = Header(None),
        jesse_trade_token: Optional[str] = Header(None, alias="X-Jesse-Trade-Token")
) -> JSONResponse:
    """
    Get metrics for a specific strategy from jesse.trade
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    try:
        headers = {}
        if jesse_trade_token:
            headers['Authorization'] = f'Bearer {jesse_trade_token}'
            
        response = requests.get(
            f'{JESSE_API2_URL}/strategies/{slug}/metrics',
            params={'period': period, 'symbol': symbol, 'timeframe': timeframe},
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            return JSONResponse(response.json())
        else:
            return JSONResponse({
                'status': 'error',
                'message': f'Failed to fetch strategy metrics: {response.text}'
            }, status_code=response.status_code)
    except requests.exceptions.RequestException as e:
        return JSONResponse({
            'status': 'error',
            'message': f'Error connecting to jesse.trade: {str(e)}'
        }, status_code=500)


@router.post("/import")
async def import_strategy(
        json_request: ImportStrategyRequestJson,
        authorization: Optional[str] = Header(None),
        jesse_trade_token: Optional[str] = Header(None, alias="X-Jesse-Trade-Token")
) -> JSONResponse:
    """
    Import a strategy from jesse.trade
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()

    try:
        # Fetch the strategy from jesse.trade
        headers = {}
        if jesse_trade_token:
            headers['Authorization'] = f'Bearer {jesse_trade_token}'
            
        response = requests.get(
            f'{JESSE_API2_URL}/strategies/{json_request.slug}',
            headers=headers,
            timeout=10
        )
        
        if response.status_code != 200:
            return JSONResponse({
                'status': 'error',
                'message': f'Failed to fetch strategy: {response.text}'
            }, status_code=response.status_code)
        
        strategy_data = response.json()
        
        # Check if code is available
        if not strategy_data.get('code'):
            return JSONResponse({
                'status': 'error',
                'message': 'Strategy code not available. You may not have access to this strategy.'
            }, status_code=403)

        # Extract the Python class name from the code
        code = strategy_data.get('code')
        class_match = re.search(r'class\s+(\w+)', code)
        if not class_match:
            return JSONResponse({
                'status': 'error',
                'message': 'No Python class definition found in strategy code. Cannot import strategy.'
            }, status_code=400)

        class_name = class_match.group(1)

        # Import the strategy
        from jesse.services import strategy_handler
        return strategy_handler.import_strategy(
            name=class_name,
            code=code
        )
        
    except requests.exceptions.RequestException as e:
        return JSONResponse({
            'status': 'error',
            'message': f'Error connecting to jesse.trade: {str(e)}'
        }, status_code=500)
