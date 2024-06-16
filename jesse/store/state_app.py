import arrow
from jesse.models.ExchangeApiKeys import get_exchange_api_key, ExchangeApiKeys


class AppState:
    def __init__(self):
        self.time = arrow.utcnow().int_timestamp * 1000
        self.starting_time = None
        self.daily_balance = []

        # used as placeholders for detecting open trades metrics
        self.total_open_trades = 0
        self.total_open_pl = 0
        self.total_liquidations = 0

        self.session_id = ''
        self.session_info = {}

        # live only
        self.exchange_api_key: ExchangeApiKeys = None

    def set_session_id(self, session_id) -> None:
        if self.session_id != '':
            raise ValueError('session_id has already been set')

        self.session_id = session_id

    def set_exchange_api_key(self, exchange_api_key_id: str) -> None:
        self.exchange_api_key = get_exchange_api_key(exchange_api_key_id)
