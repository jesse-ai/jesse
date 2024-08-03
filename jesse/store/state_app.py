import arrow
from jesse.models.ExchangeApiKeys import ExchangeApiKeys
from jesse.models.NotificationApiKeys import NotificationApiKeys


class AppState:
    def __init__(self):
        self.time = arrow.utcnow().int_timestamp * 1000
        self.starting_time = None
        self.ending_time = None
        self.daily_balance = []

        # used as placeholders for detecting open trades metrics
        self.total_open_trades = 0
        self.total_open_pl = 0
        self.total_liquidations = 0

        self.session_id = ''
        self.session_info = {}

        # live only
        self.exchange_api_key = None
        self.notifications_api_key = None

    def set_session_id(self, session_id) -> None:
        self.session_id = session_id

    def set_exchange_api_key(self, exchange_api_key_id: str) -> None:
        if self.exchange_api_key is not None:
            raise ValueError('exchange_api_key has already been set')

        self.exchange_api_key = ExchangeApiKeys.get_or_none(ExchangeApiKeys.id == exchange_api_key_id)

    def set_notifications_api_key(self, notifications_api_key_id: str) -> None:
        if self.notifications_api_key is not None:
            raise ValueError('notifications_api_key has already been set')

        if notifications_api_key_id == '':
            return

        self.notifications_api_key = NotificationApiKeys.get_or_none(NotificationApiKeys.id == notifications_api_key_id)
