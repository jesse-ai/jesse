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
    exchange: str
    routes: List[Dict[str, str]]
    data_routes: List[Dict[str, str]]
    config: dict
    start_date: str
    finish_date: str
    debug_mode: bool
    export_csv: bool
    export_json: bool
    export_chart: bool
    export_tradingview: bool
    fast_mode: bool
    benchmark: bool


class OptimizationRequestJson(BaseModel):
    id: str
    exchange: str
    routes: List[Dict[str, str]]
    data_routes: List[Dict[str, str]]
    config: dict
    training_start_date: str
    training_finish_date: str
    testing_start_date: str
    testing_finish_date: str
    optimal_total: int
    fast_mode: bool
    cpu_cores: int
    state: dict


class ImportCandlesRequestJson(BaseModel):
    id: str
    exchange: str
    symbol: str
    start_date: str


class ExchangeSupportedSymbolsRequestJson(BaseModel):
    exchange: str


class CancelRequestJson(BaseModel):
    id: str


class LiveRequestJson(BaseModel):
    id: str
    config: dict
    exchange: str
    exchange_api_key_id: str
    notification_api_key_id: str
    routes: List[Dict[str, str]]
    data_routes: List[Dict[str, str]]
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
    type: str
    start_time: int


class GetOrdersRequestJson(BaseModel):
    id: str
    session_id: str


class StoreExchangeApiKeyRequestJson(BaseModel):
    exchange: str
    name: str
    api_key: str
    api_secret: str
    additional_fields: Optional[dict] = None
    general_notifications_id: Optional[str] = None
    error_notifications_id: Optional[str] = None


class StoreNotificationApiKeyRequestJson(BaseModel):
    name: str
    driver: str
    fields: dict


class DeleteExchangeApiKeyRequestJson(BaseModel):
    id: str


class DeleteNotificationApiKeyRequestJson(BaseModel):
    id: str


class ConfigRequestJson(BaseModel):
    current_config: dict


class LoginRequestJson(BaseModel):
    password: str


class LoginJesseTradeRequestJson(BaseModel):
    email: str
    password: str


class NewStrategyRequestJson(BaseModel):
    name: str


class GetStrategyRequestJson(BaseModel):
    name: str


class SaveStrategyRequestJson(BaseModel):
    name: str
    content: str


class DeleteStrategyRequestJson(BaseModel):
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


class DeleteCandlesRequestJson(BaseModel):
    exchange: str
    symbol: str


class UpdateOptimizationSessionStateRequestJson(BaseModel):
    id: str
    state: dict


class UpdateOptimizationSessionStatusRequestJson(BaseModel):
    id: str
    status: str


class TerminateOptimizationRequestJson(BaseModel):
    id: str
