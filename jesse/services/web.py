from typing import List, Dict, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

fastapi_app = FastAPI()

origins = [
    "*",
]

fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class BacktestRequestJson(BaseModel):
    id: str
    routes: List[Dict[str, str]]
    extra_routes: List[Dict[str, str]]
    config: dict
    start_date: str
    finish_date: str
    debug_mode: bool
    export_csv: bool
    export_json: bool
    export_chart: bool
    export_tradingview: bool
    export_full_reports: bool


class OptimizationRequestJson(BaseModel):
    id: str
    routes: List[Dict[str, str]]
    extra_routes: List[Dict[str, str]]
    config: dict
    start_date: str
    finish_date: str
    optimal_total: int
    debug_mode: bool
    export_csv: bool
    export_json: bool


class ImportCandlesRequestJson(BaseModel):
    id: str
    exchange: str
    symbol: str
    start_date: str


class CancelRequestJson(BaseModel):
    id: str


class LiveRequestJson(BaseModel):
    id: str
    config: dict
    routes: List[Dict[str, str]]
    extra_routes: List[Dict[str, str]]
    debug_mode: bool
    paper_mode: bool


class LiveCancelRequestJson(BaseModel):
    id: str
    paper_mode: bool


class GetCandlesRequestJson(BaseModel):
    id: str
    exchange: str
    symbol: str
    timeframe: str


class GetLogsRequestJson(BaseModel):
    id: str
    session_id: str
    type: str


class GetOrdersRequestJson(BaseModel):
    id: str
    session_id: str


class ConfigRequestJson(BaseModel):
    current_config: dict


class LoginRequestJson(BaseModel):
    password: str


class LoginJesseTradeRequestJson(BaseModel):
    email: str
    password: str


class NewStrategyRequestJson(BaseModel):
    name: str


class FeedbackRequestJson(BaseModel):
    description: str
    email: Optional[str] = None


class ReportExceptionRequestJson(BaseModel):
    description: str
    traceback: str
    mode: str
    attach_logs: bool
    session_id: Optional[str] = None
    email: Optional[str] = None
