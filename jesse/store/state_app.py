import arrow
import jesse.helpers as jh


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

    def set_session_id(self) -> None:
        """
        Generated and sets session_id. Used to prevent overriding of the session_id
        """
        if self.session_id == '':
            self.session_id = jh.generate_unique_id()
