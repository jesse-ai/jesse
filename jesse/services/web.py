from typing import List, Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

fastapi_app = FastAPI()

origins = [
    "*",
    "http://localhost:8080",
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


class LoginRequestJson(BaseModel):
    password: str
