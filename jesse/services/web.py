from typing import Any, List, Dict, Optional
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel, ConfigDict, Field, model_validator


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
fastapi_app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=5)


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
    fast_mode: bool
    benchmark: bool
    theme: str = 'light'
    state: dict

    @model_validator(mode='after')
    def validate_date_range(self):
        """Reject malformed or reversed ranges before a worker is queued."""
        try:
            start = datetime.strptime(self.start_date, '%Y-%m-%d')
            finish = datetime.strptime(self.finish_date, '%Y-%m-%d')
        except ValueError:
            raise ValueError('start_date and finish_date must use the YYYY-MM-DD format')

        if start >= finish:
            raise ValueError('start_date must be earlier than finish_date')
        return self


class OptimizationRequestJson(BaseModel):
    id: Optional[str] = None
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


class SearchExchangeSymbolsRequestJson(BaseModel):
    exchange: str
    query: str
    limit: int = Field(default=50, ge=1, le=200)


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


class GetStrategyChartsRequestJson(BaseModel):
    id: str


class GetLiveSessionChartDataRequestJson(BaseModel):
    exchange: str
    symbol: str
    timeframe: str
    anchor_time: Optional[int] = None
    candle_count: int = 1000
    full_history: bool = False


class GetBacktestSessionChartDataRequestJson(BaseModel):
    exchange: str
    symbol: str
    timeframe: str


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


class StoreAiModelRequestJson(BaseModel):
    name: str
    provider: str
    base_url: str
    api_key: str
    model_id: str


class DeleteAiModelRequestJson(BaseModel):
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


class SaveStrategyReportRequestJson(BaseModel):
    name: str
    filename: str
    content: str
    overwrite: bool = False


class DeleteStrategyRequestJson(BaseModel):
    name: str


class ListProjectFilesRequestJson(BaseModel):
    path: str = ''
    recursive: bool = False
    max_entries: int = 200


class ReadProjectFileRequestJson(BaseModel):
    path: str
    start_line: int = 1
    max_lines: int = 400


class WriteProjectFileRequestJson(BaseModel):
    path: str
    content: str
    overwrite: bool = False


class ProjectPathRequestJson(BaseModel):
    path: str


class DeleteProjectPathRequestJson(BaseModel):
    path: str
    recursive: bool = False


class TransferProjectPathRequestJson(BaseModel):
    source: str
    destination: str
    overwrite: bool = False


class RunResearchScriptRequestJson(BaseModel):
    path: str
    args: List[str] = Field(default_factory=list)
    timeout_minutes: int = 60


class ResearchJobRequestJson(BaseModel):
    job_id: str = ''


class ResearchJobOutputRequestJson(BaseModel):
    job_id: str
    tail_lines: int = 200


class SessionResultsRequestJson(BaseModel):
    session_type: str
    session_id: str
    section: str = 'summary'
    offset: int = 0
    limit: int = 50


class LiveSessionsListRequestJson(BaseModel):
    limit: int = 20
    offset: int = 0
    status_filter: Optional[str] = None
    mode_filter: Optional[str] = None
    title_search: Optional[str] = None


class LiveHistoryRequestJson(BaseModel):
    # Loosely typed on purpose: jesse.services.live_history validates every field strictly (no
    # coercion of booleans or text to numbers) with messages that never repeat the value. Extra
    # fields are kept so a misspelled filter is refused instead of silently widening the selection.
    model_config = ConfigDict(extra='allow')

    start: Any = None
    end: Any = None
    recent_days: Any = None
    mode: Any = 'live'
    exchange: Any = None
    symbol: Any = None
    session_id: Any = None
    order: Any = 'newest_first'
    cursor: Any = None
    limit: Any = 100


class LiveOrdersHistoryRequestJson(LiveHistoryRequestJson):
    time_field: Any = 'created_at'
    status: Any = None


class AnalysisInputJson(BaseModel):
    # An input is a stored session (session_type + session_id) or a live history dataset
    # ({"dataset": "live_trades" | "live_orders", window and filters}); extra fields are kept so
    # jesse.services.analysis_jobs can refuse unknown dataset filters instead of dropping them.
    model_config = ConfigDict(extra='allow')

    session_type: Optional[str] = None
    session_id: Optional[str] = None
    name: Optional[str] = None
    dataset: Optional[str] = None


class RunAnalysisRequestJson(BaseModel):
    code: str
    inputs: List[AnalysisInputJson] = Field(default_factory=list)
    timeout_minutes: int = 5


class AnalysisJobRequestJson(BaseModel):
    job_id: str = ''
    tail_lines: int = 50


class AnalysisArtifactRequestJson(BaseModel):
    job_id: str
    path: str


class ForkStrategyRequestJson(BaseModel):
    new_name: str
    content: str


class ImportStrategyRequestJson(BaseModel):
    slug: str


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


class HelpSearchRequestJson(BaseModel):
    query: str


class DeleteCandlesRequestJson(BaseModel):
    exchange: str
    symbol: str


class PurgeCandlesRequestJson(BaseModel):
    exchanges: List[str]


class ExportCandlesToProjectRequestJson(BaseModel):
    exchange: str
    symbol: str
    # Project-relative CSV path under research_scripts/; defaults to research_scripts/candle_exports/<name>.csv.
    path: Optional[str] = None
    overwrite: bool = False


class CopyCandlesRequestJson(BaseModel):
    exchange: str
    symbol: str
    target_exchange: str
    # Defaults to the source symbol; override it when the target market uses another quote (USD vs USDT).
    target_symbol: Optional[str] = None
    delete_source: bool = False


class UpdateOptimizationSessionStateRequestJson(BaseModel):
    id: str
    state: dict


class UpdateOptimizationSessionStatusRequestJson(BaseModel):
    id: str
    status: str


class TerminateOptimizationRequestJson(BaseModel):
    id: str


class UpdateOptimizationSessionNotesRequestJson(BaseModel):
    id: str
    title: Optional[str] = None
    description: Optional[str] = None
    strategy_codes: Optional[dict] = None


class GetOptimizationSessionsRequestJson(BaseModel):
    limit: int = 50
    offset: int = 0
    title_search: Optional[str] = None
    status_filter: Optional[str] = None
    date_filter: Optional[str] = None


class UpdateBacktestSessionStateRequestJson(BaseModel):
    id: str
    state: dict


class GetBacktestSessionsRequestJson(BaseModel):
    limit: int = 50
    offset: int = 0
    title_search: Optional[str] = None
    status_filter: Optional[str] = None
    date_filter: Optional[str] = None


class UpdateBacktestSessionNotesRequestJson(BaseModel):
    id: str
    title: Optional[str] = None
    description: Optional[str] = None
    strategy_codes: Optional[dict] = None


class GetLiveSessionsRequestJson(BaseModel):
    limit: int = 50
    offset: int = 0
    title_search: Optional[str] = None
    status_filter: Optional[str] = None
    date_filter: Optional[str] = None
    mode_filter: Optional[str] = None


class UpdateLiveSessionNotesRequestJson(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    strategy_codes: Optional[dict] = None


class UpdateLiveSessionStateRequestJson(BaseModel):
    id: str
    state: dict
    # Refuse unless the session is still a draft (or new). The dashboard leaves it off so it can
    # keep saving the form of an ended tab; MCP draft edits set it.
    require_draft: bool = False


class GetEquityCurveRequestJson(BaseModel):
    session_id: str
    from_ms: Optional[int] = None
    to_ms: Optional[int] = None
    timeframe: str = 'auto'
    max_points: int = 1000


class MonteCarloRequestJson(BaseModel):
    id: Optional[str] = None
    exchange: str
    routes: List[Dict[str, str]]
    data_routes: List[Dict[str, str]]
    config: dict
    start_date: str
    finish_date: str
    run_trades: bool
    run_candles: bool
    num_scenarios: int
    fast_mode: bool
    cpu_cores: int
    pipeline_type: Optional[str] = 'moving_block_bootstrap'
    pipeline_params: Optional[dict] = None
    state: dict


class UpdateMonteCarloSessionStateRequestJson(BaseModel):
    id: str
    state: dict


class TerminateMonteCarloRequestJson(BaseModel):
    id: str


class CancelMonteCarloRequestJson(BaseModel):
    id: str


class UpdateMonteCarloSessionNotesRequestJson(BaseModel):
    id: str
    title: Optional[str] = None
    description: Optional[str] = None
    strategy_codes: Optional[dict] = None


class GetMonteCarloSessionsRequestJson(BaseModel):
    limit: int = 50
    offset: int = 0
    title_search: Optional[str] = None
    status_filter: Optional[str] = None
    date_filter: Optional[str] = None


class GetOrdersHistoryRequestJson(BaseModel):
    limit: int = 50
    offset: int = 0
    id_search: Optional[str] = None
    status_filter: Optional[str] = None
    symbol_filter: Optional[str] = None
    date_filter: Optional[str] = None
    exchange_filter: Optional[str] = None
    type_filter: Optional[str] = None
    side_filter: Optional[str] = None


class GetTradesHistoryRequestJson(BaseModel):
    limit: int = 50
    offset: int = 0
    id_search: Optional[str] = None
    status_filter: Optional[str] = None
    symbol_filter: Optional[str] = None
    date_filter: Optional[str] = None
    exchange_filter: Optional[str] = None
    type_filter: Optional[str] = None
    

class ImportApiKeyRequestJson(BaseModel):
    content: str


class SignificanceTestRequestJson(BaseModel):
    id: Optional[str] = None
    exchange: str
    routes: List[Dict[str, str]]
    data_routes: List[Dict[str, str]]
    config: dict
    start_date: str
    finish_date: str
    n_simulations: int = 1000
    random_seed: Optional[int] = None
    theme: str = 'light'
    state: dict


class CancelSignificanceTestRequestJson(BaseModel):
    id: str


class TerminateSignificanceTestRequestJson(BaseModel):
    id: str


class UpdateSignificanceTestSessionStateRequestJson(BaseModel):
    id: str
    state: dict


class UpdateSignificanceTestSessionNotesRequestJson(BaseModel):
    id: str
    title: Optional[str] = None
    description: Optional[str] = None
    strategy_codes: Optional[dict] = None


class GetSignificanceTestSessionsRequestJson(BaseModel):
    limit: int = 50
    offset: int = 0
    title_search: Optional[str] = None
    status_filter: Optional[str] = None
    date_filter: Optional[str] = None
