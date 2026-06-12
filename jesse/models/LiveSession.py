import peewee
import json
from jesse.services.db import database
import jesse.helpers as jh


if database.is_closed():
    database.open_connection()


class LiveSession(peewee.Model):
    id = peewee.UUIDField(primary_key=True)
    
    # Status of the live session: running, stopped, or terminated
    status = peewee.CharField()
    
    # Session mode: livetrade or papertrade
    session_mode = peewee.CharField()
    
    # Exchange name
    exchange = peewee.CharField()
    
    # Frontend state in JSON format - used for restoring UI state
    state = peewee.TextField(null=True)
    
    # User notes
    title = peewee.CharField(max_length=255, null=True)
    description = peewee.TextField(null=True)
    strategy_codes = peewee.TextField(null=True)
    
    # Error tracking
    exception = peewee.TextField(null=True)
    traceback = peewee.TextField(null=True)
    
    # Timestamps for session management
    finished_at = peewee.BigIntegerField(null=True)
    created_at = peewee.BigIntegerField()
    updated_at = peewee.BigIntegerField()

    class Meta:
        from jesse.services.db import database

        database = database.db
        indexes = (
            (('id',), True),
            (('created_at',), False),
            (('updated_at',), False),
        )

    def __init__(self, attributes: dict = None, **kwargs) -> None:
        peewee.Model.__init__(self, attributes=attributes, **kwargs)

        if attributes is None:
            attributes = {}

        for a, value in attributes.items():
            setattr(self, a, value)
    
    @property
    def state_json(self):
        """
        Returns the frontend state as a Python dictionary
        """
        if not self.state:
            return {}
        s = json.loads(self.state)
        if isinstance(s, dict) and 'form' in s and isinstance(s['form'], dict):
            for key in ['debug_mode', 'export_chart', 'export_tradingview', 'export_csv', 'export_json', 'fast_mode', 'benchmark']:
                if key in s['form']:
                    s['form'][key] = jh.normalize_bool(s['form'].get(key))
        return s
    
    @state_json.setter
    def state_json(self, state_data):
        """
        Sets the frontend state from a Python dictionary
        """
        self.state = json.dumps(state_data) if state_data else None
    
    @property
    def strategy_codes_json(self):
        """
        Returns the strategy codes as a Python dictionary
        """
        if not self.strategy_codes:
            return {}
        return json.loads(self.strategy_codes)
    
    @strategy_codes_json.setter
    def strategy_codes_json(self, codes_dict):
        """
        Sets the strategy codes from a Python dictionary
        """
        self.strategy_codes = json.dumps(codes_dict) if codes_dict else None
    
    @property
    def duration(self):
        """
        Calculate the duration of the session in seconds
        """
        if self.finished_at:
            # For completed sessions, use the stored timestamps
            return self.finished_at - self.created_at
        else:
            # For running sessions, calculate duration up to now
            return jh.now_to_timestamp(True) - self.created_at


# if database is open, create the table
if database.is_open():
    LiveSession.create_table()

