import peewee
import json
from jesse.services.db import database
import jesse.helpers as jh


if database.is_closed():
    database.open_connection()


class BacktestSession(peewee.Model):
    id = peewee.UUIDField(primary_key=True)
    
    # Status of the backtest session: running, finished, stopped, cancelled, or terminated
    status = peewee.CharField()
    
    # Backtest results data in JSON format
    metrics = peewee.TextField(null=True)
    equity_curve = peewee.TextField(null=True)
    trades = peewee.TextField(null=True)
    hyperparameters = peewee.TextField(null=True)
    chart_data = peewee.TextField(null=True)
    
    # Frontend state in JSON format - used for restoring UI state
    state = peewee.TextField(null=True)
    
    # User notes
    title = peewee.CharField(max_length=255, null=True)
    description = peewee.TextField(null=True)
    strategy_codes = peewee.TextField(null=True)
    
    # Error tracking
    exception = peewee.TextField(null=True)
    traceback = peewee.TextField(null=True)
    
    # Execution metrics
    execution_duration = peewee.FloatField(null=True)

    # Timestamps for session management
    created_at = peewee.BigIntegerField()
    updated_at = peewee.BigIntegerField()

    class Meta:
        from jesse.services.db import database

        database = database.db
        indexes = (
            (('id',), True),
            (('created_at',), False),
        )

    def __init__(self, attributes: dict = None, **kwargs) -> None:
        peewee.Model.__init__(self, attributes=attributes, **kwargs)

        if attributes is None:
            attributes = {}

        for a, value in attributes.items():
            setattr(self, a, value)
    
    @property
    def metrics_json(self):
        """
        Returns the metrics as a Python dictionary
        """
        if not self.metrics:
            return None
        return json.loads(self.metrics)
    
    @metrics_json.setter
    def metrics_json(self, metrics_dict):
        """
        Sets the metrics from a Python dictionary
        """
        self.metrics = json.dumps(metrics_dict) if metrics_dict else None
    
    @property
    def equity_curve_json(self):
        """
        Returns the equity curve data as a Python list
        """
        if not self.equity_curve:
            return []
        return json.loads(self.equity_curve)
    
    @equity_curve_json.setter
    def equity_curve_json(self, curve_data):
        """
        Sets the equity curve data from a Python list
        """
        self.equity_curve = json.dumps(curve_data) if curve_data else None
    
    @property
    def trades_json(self):
        """
        Returns the trades as a Python list
        """
        if not self.trades:
            return []
        return json.loads(self.trades)
    
    @trades_json.setter
    def trades_json(self, trades_list):
        """
        Sets the trades from a Python list
        """
        self.trades = json.dumps(trades_list) if trades_list else None
    
    @property
    def hyperparameters_json(self):
        """
        Returns the hyperparameters as a Python dictionary
        """
        if not self.hyperparameters:
            return {}
        return json.loads(self.hyperparameters)
    
    @hyperparameters_json.setter
    def hyperparameters_json(self, hp_dict):
        """
        Sets the hyperparameters from a Python dictionary
        """
        self.hyperparameters = json.dumps(hp_dict) if hp_dict else None
    
    @property
    def chart_data_json(self):
        """
        Returns the chart data as a Python dictionary
        """
        if not self.chart_data:
            return {}
        return json.loads(self.chart_data)
    
    @chart_data_json.setter
    def chart_data_json(self, data_dict):
        """
        Sets the chart data from a Python dictionary
        """
        self.chart_data = json.dumps(data_dict) if data_dict else None
    
    @property
    def state_json(self):
        """
        Returns the frontend state as a Python dictionary
        """
        if not self.state:
            return {}
        return json.loads(self.state)
    
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
        if not self.updated_at:
            # For running sessions, calculate duration up to now
            return jh.now_to_timestamp(True) - self.created_at
        
        # For completed sessions, use the stored timestamps
        return self.updated_at - self.created_at
    
    @property
    def net_profit_percentage(self):
        """
        Get the net profit percentage from metrics
        """
        metrics = self.metrics_json
        if not metrics:
            return None
            
        return metrics.get('net_profit_percentage', None)


# if database is open, create the table
if database.is_open():
    BacktestSession.create_table()

# # # # # # # # # # # # # # # # # # # # # # # # # # # 
# # # # # # # # # DB FUNCTIONS # # # # # # # # #
# # # # # # # # # # # # # # # # # # # # # # # # # # # 

def get_backtest_session_by_id(id: str):
    try:
        return BacktestSession.get(BacktestSession.id == id)
    except BacktestSession.DoesNotExist:
        return None


def store_backtest_session(
    id: str,
    status: str
) -> None:
    # Check if session already exists
    existing_session = get_backtest_session_by_id(id)
    
    if existing_session:
        # Update existing session - reset it to fresh state
        d = {
            'status': status,
            'metrics': None,
            'equity_curve': None,
            'trades': None,
            'hyperparameters': None,
            'chart_data': None,
            'state': None,
            'exception': None,
            'traceback': None,
            'execution_duration': None,
            'updated_at': jh.now_to_timestamp(True)
        }
        BacktestSession.update(**d).where(BacktestSession.id == id).execute()
    else:
        # Create a new session
        d = {
            'id': id,
            'status': status,
            'created_at': jh.now_to_timestamp(True),
            'updated_at': jh.now_to_timestamp(True)
        }
        BacktestSession.insert(**d).execute()
    

def update_backtest_session_status(id: str, status: str) -> None:
    d = {
        'status': status,
        'updated_at': jh.now_to_timestamp(True)
    }
    
    BacktestSession.update(**d).where(BacktestSession.id == id).execute()


def store_backtest_session_exception(id: str, exception: str, traceback: str) -> None:
    d = {
        'exception': exception,
        'traceback': traceback,
        'updated_at': jh.now_to_timestamp(True)
    }

    BacktestSession.update(**d).where(BacktestSession.id == id).execute()


def update_backtest_session_results(
    id: str, 
    metrics: dict = None,
    equity_curve: list = None,
    trades: list = None,
    hyperparameters: dict = None,
    chart_data: dict = None,
    execution_duration: float = None,
    strategy_codes: dict = None
) -> None:
    d = {
        'updated_at': jh.now_to_timestamp(True)
    }

    if metrics is not None:
        d['metrics'] = json.dumps(metrics)

    if equity_curve is not None:
        d['equity_curve'] = json.dumps(equity_curve)

    if trades is not None:
        d['trades'] = json.dumps(trades)

    if hyperparameters is not None:
        d['hyperparameters'] = json.dumps(hyperparameters)

    if chart_data is not None:
        d['chart_data'] = json.dumps(chart_data)

    if execution_duration is not None:
        d['execution_duration'] = execution_duration

    if strategy_codes is not None:
        d['strategy_codes'] = json.dumps(strategy_codes)

    BacktestSession.update(**d).where(BacktestSession.id == id).execute()


def get_backtest_sessions(limit: int = 50, offset: int = 0, title_search: str = None, status_filter: str = None, date_filter: str = None) -> list:
    """
    Returns a list of BacktestSession objects sorted by most recently updated
    """
    query = BacktestSession.select().order_by(BacktestSession.updated_at.desc())
    
    # Apply title filter (case-insensitive)
    if title_search:
        query = query.where(BacktestSession.title.contains(title_search))
    
    # Apply status filter
    if status_filter and status_filter != 'all':
        query = query.where(BacktestSession.status == status_filter)
    
    # Apply date filter
    if date_filter and date_filter != 'all_time':
        current_timestamp = jh.now_to_timestamp(True)
        
        if date_filter == '7_days':
            threshold = current_timestamp - (7 * 24 * 60 * 60 * 1000)
        elif date_filter == '30_days':
            threshold = current_timestamp - (30 * 24 * 60 * 60 * 1000)
        elif date_filter == '90_days':
            threshold = current_timestamp - (90 * 24 * 60 * 60 * 1000)
        else:
            threshold = 0
        
        if threshold > 0:
            query = query.where(BacktestSession.created_at >= threshold)
    
    return list(query.limit(limit).offset(offset))


def delete_backtest_session(id: str) -> bool:
    try:
        BacktestSession.delete().where(BacktestSession.id == id).execute()
        return True
    except Exception as e:
        print(f"Error deleting backtest session: {e}")
        return False


def purge_backtest_sessions(days_old: int = None) -> int:
    try:
        current_timestamp = jh.now_to_timestamp(True)
        
        if days_old is not None:
            days_old = int(days_old)
        
        if days_old is not None and days_old > 0:
            threshold = current_timestamp - (days_old * 24 * 60 * 60 * 1000)
            
            all_sessions = BacktestSession.select()
            sessions_to_delete = []
            
            for session in all_sessions:
                try:
                    session_updated_at = int(session.updated_at) if session.updated_at else 0
                    if session_updated_at < threshold:
                        sessions_to_delete.append(session.id)
                except (ValueError, TypeError):
                    continue
            
            deleted_count = 0
            for session_id in sessions_to_delete:
                try:
                    BacktestSession.delete().where(BacktestSession.id == session_id).execute()
                    deleted_count += 1
                except Exception:
                    pass
        else:
            deleted_count = BacktestSession.delete().execute()
        
        return deleted_count
    except Exception as e:
        print(f"Error purging backtest sessions: {e}")
        return 0


def update_backtest_session_state(id: str, state: dict) -> None:
    d = {
        'state': json.dumps(state),
        'updated_at': jh.now_to_timestamp(True)
    }
    
    BacktestSession.update(**d).where(BacktestSession.id == id).execute()


def update_backtest_session_notes(id: str, title: str = None, description: str = None, strategy_codes: dict = None) -> None:
    d = {
        'updated_at': jh.now_to_timestamp(True)
    }
    
    if title is not None:
        d['title'] = title
    
    if description is not None:
        d['description'] = description
    
    if strategy_codes is not None:
        d['strategy_codes'] = json.dumps(strategy_codes)
    
    BacktestSession.update(**d).where(BacktestSession.id == id).execute()


