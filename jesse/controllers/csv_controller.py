"""
CSV Data Controller for Jesse trading framework.
Handles API endpoints for managing CSV data sources.
"""

from typing import Optional, List, Dict
from fastapi import APIRouter, Header, Query, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from jesse.services import auth as authenticator
from jesse.modes.data_provider import (
    get_available_csv_symbols,
    import_csv_symbol_to_database,
    get_csv_candles
)
from jesse.services.csv_data_provider import csv_data_provider
import jesse.helpers as jh


router = APIRouter(prefix="/csv", tags=["CSV Data"])


class CSVImportRequest(BaseModel):
    symbol: str
    timeframe: str = "1m"
    exchange: str = "custom"
    start_date: Optional[str] = None
    finish_date: Optional[str] = None


class CSVSymbolInfo(BaseModel):
    symbol: str
    start_time: int
    end_time: int
    start_date: str
    end_date: str
    file_path: str
    file_size: int


@router.get("/symbols")
def get_symbols(authorization: Optional[str] = Header(None)):
    """
    Get list of available CSV symbols.
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()
    
    try:
        symbols = get_available_csv_symbols()
        return JSONResponse({'symbols': symbols}, status_code=200)
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)


@router.get("/symbols/{symbol}/info")
def get_symbol_info(symbol: str, authorization: Optional[str] = Header(None)):
    """
    Get information about a specific CSV symbol.
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()
    
    try:
        info = csv_data_provider.get_symbol_info(symbol)
        if info is None:
            return JSONResponse({'error': f'Symbol {symbol} not found'}, status_code=404)
        
        return JSONResponse({'info': info}, status_code=200)
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)


@router.get("/symbols/{symbol}/timeframes")
def get_available_timeframes(symbol: str, authorization: Optional[str] = Header(None)):
    """
    Get available timeframes for a CSV symbol.
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()
    
    try:
        timeframes = csv_data_provider.get_available_timeframes(symbol)
        return JSONResponse({'timeframes': timeframes}, status_code=200)
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)


@router.post("/import")
def import_symbol(request: CSVImportRequest, authorization: Optional[str] = Header(None)):
    """
    Import a CSV symbol to Jesse database.
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()
    
    try:
        # Convert date strings to timestamps if provided
        start_date = None
        finish_date = None
        
        if request.start_date:
            start_date = jh.date_to_timestamp(request.start_date)
        if request.finish_date:
            finish_date = jh.date_to_timestamp(request.finish_date)
        
        # Import symbol to database
        success = import_csv_symbol_to_database(
            symbol=request.symbol,
            timeframe=request.timeframe,
            exchange=request.exchange,
            start_date=start_date,
            finish_date=finish_date
        )
        
        if success:
            return JSONResponse({
                'message': f'Successfully imported {request.symbol} to database',
                'symbol': request.symbol,
                'timeframe': request.timeframe,
                'exchange': request.exchange
            }, status_code=200)
        else:
            return JSONResponse({
                'error': f'Failed to import {request.symbol} to database'
            }, status_code=500)
            
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)


@router.get("/candles")
def get_candles(
    symbol: str,
    timeframe: str = "1m",
    exchange: str = "custom",
    start_date: Optional[str] = Query(None),
    finish_date: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None)
):
    """
    Get candles from CSV data source.
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()
    
    try:
        # Convert date strings to timestamps if provided
        start_timestamp = None
        finish_timestamp = None
        
        if start_date:
            start_timestamp = jh.date_to_timestamp(start_date)
        if finish_date:
            finish_timestamp = jh.date_to_timestamp(finish_date)
        
        # Get candles
        candles = get_csv_candles(
            exchange=exchange,
            symbol=symbol,
            timeframe=timeframe,
            start_date=start_timestamp,
            finish_date=finish_timestamp
        )
        
        return JSONResponse({
            'candles': candles,
            'count': len(candles),
            'symbol': symbol,
            'timeframe': timeframe,
            'exchange': exchange
        }, status_code=200)
        
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)


@router.post("/clear-cache")
def clear_cache(authorization: Optional[str] = Header(None)):
    """
    Clear CSV data cache.
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()
    
    try:
        csv_data_provider.clear_cache()
        return JSONResponse({'message': 'Cache cleared successfully'}, status_code=200)
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)


@router.get("/preview/{symbol}")
def preview_data(
    symbol: str,
    limit: int = Query(100, ge=1, le=1000),
    authorization: Optional[str] = Header(None)
):
    """
    Preview CSV data for a symbol (first N rows).
    """
    if not authenticator.is_valid_token(authorization):
        return authenticator.unauthorized_response()
    
    try:
        # Load tick data
        tick_data = csv_data_provider.load_tick_data(symbol)
        
        if tick_data is None:
            return JSONResponse({'error': f'No data found for symbol {symbol}'}, status_code=404)
        
        # Get preview data
        preview = tick_data.head(limit).to_dict('records')
        
        return JSONResponse({
            'preview': preview,
            'total_rows': len(tick_data),
            'symbol': symbol,
            'limit': limit
        }, status_code=200)
        
    except Exception as e:
        return JSONResponse({'error': str(e)}, status_code=500)
