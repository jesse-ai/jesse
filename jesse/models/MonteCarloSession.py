import peewee
import json
import numpy as np
from jesse.services.db import database
import jesse.helpers as jh


def _convert_numpy_types(obj):
    """Convert NumPy types to native Python types for JSON serialization"""
    if isinstance(obj, dict):
        return {k: _convert_numpy_types(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_convert_numpy_types(item) for item in obj]
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj


if database.is_closed():
    database.open_connection()


class MonteCarloSession(peewee.Model):
    id = peewee.UUIDField(primary_key=True)
    status = peewee.CharField()
    state = peewee.TextField(null=True)
    title = peewee.CharField(max_length=255, null=True)
    description = peewee.TextField(null=True)
    strategy_codes = peewee.TextField(null=True)
    created_at = peewee.BigIntegerField()
    updated_at = peewee.BigIntegerField()

    class Meta:
        from jesse.services.db import database

        database = database.db
        indexes = (
            (('id',), True),
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
        if not self.state:
            return {}
        return json.loads(self.state)

    @state_json.setter
    def state_json(self, state_data):
        self.state = json.dumps(state_data)

    @property
    def strategy_codes_json(self):
        if not self.strategy_codes:
            return {}
        return json.loads(self.strategy_codes)

    @strategy_codes_json.setter
    def strategy_codes_json(self, codes_dict):
        self.strategy_codes = json.dumps(codes_dict) if codes_dict else None

    @property
    def trades_session(self):
        try:
            return MonteCarloTradesSession.get(
                MonteCarloTradesSession.monte_carlo_session_id == self.id
            )
        except MonteCarloTradesSession.DoesNotExist:
            return None

    @property
    def candles_session(self):
        try:
            return MonteCarloCandlesSession.get(
                MonteCarloCandlesSession.monte_carlo_session_id == self.id
            )
        except MonteCarloCandlesSession.DoesNotExist:
            return None


class MonteCarloTradesSession(peewee.Model):
    id = peewee.UUIDField(primary_key=True)
    monte_carlo_session_id = peewee.UUIDField()
    num_scenarios = peewee.IntegerField()
    completed_scenarios = peewee.IntegerField(default=0)
    status = peewee.CharField()
    results = peewee.TextField(null=True)
    logs = peewee.TextField(null=True)
    exception = peewee.TextField(null=True)
    traceback = peewee.TextField(null=True)
    created_at = peewee.BigIntegerField()
    updated_at = peewee.BigIntegerField()

    class Meta:
        from jesse.services.db import database

        database = database.db
        indexes = (
            (('id',), True),
            (('monte_carlo_session_id',), False),
        )

    def __init__(self, attributes: dict = None, **kwargs) -> None:
        peewee.Model.__init__(self, attributes=attributes, **kwargs)

        if attributes is None:
            attributes = {}

        for a, value in attributes.items():
            setattr(self, a, value)

    @property
    def results_json(self):
        if not self.results:
            return {}
        return json.loads(self.results)

    @results_json.setter
    def results_json(self, results_data):
        self.results = json.dumps(results_data)


class MonteCarloCandlesSession(peewee.Model):
    id = peewee.UUIDField(primary_key=True)
    monte_carlo_session_id = peewee.UUIDField()
    num_scenarios = peewee.IntegerField()
    completed_scenarios = peewee.IntegerField(default=0)
    status = peewee.CharField()
    pipeline_type = peewee.CharField()
    pipeline_params = peewee.TextField(null=True)
    results = peewee.TextField(null=True)
    logs = peewee.TextField(null=True)
    exception = peewee.TextField(null=True)
    traceback = peewee.TextField(null=True)
    created_at = peewee.BigIntegerField()
    updated_at = peewee.BigIntegerField()

    class Meta:
        from jesse.services.db import database

        database = database.db
        indexes = (
            (('id',), True),
            (('monte_carlo_session_id',), False),
        )

    def __init__(self, attributes: dict = None, **kwargs) -> None:
        peewee.Model.__init__(self, attributes=attributes, **kwargs)

        if attributes is None:
            attributes = {}

        for a, value in attributes.items():
            setattr(self, a, value)

    @property
    def results_json(self):
        if not self.results:
            return {}
        return json.loads(self.results)

    @results_json.setter
    def results_json(self, results_data):
        self.results = json.dumps(results_data)

    @property
    def pipeline_params_json(self):
        if not self.pipeline_params:
            return {}
        return json.loads(self.pipeline_params)

    @pipeline_params_json.setter
    def pipeline_params_json(self, params_data):
        self.pipeline_params = json.dumps(params_data)


# Create tables if database is open
if database.is_open():
    MonteCarloSession.create_table()
    MonteCarloTradesSession.create_table()
    MonteCarloCandlesSession.create_table()


# # # # # # # # # # # # # # # # # # # # # # # # # # # 
# # # # # # # # # DB FUNCTIONS # # # # # # # # #
# # # # # # # # # # # # # # # # # # # # # # # # # # # 

# Parent Session Functions
def get_monte_carlo_session_by_id(id: str):
    try:
        return MonteCarloSession.get(MonteCarloSession.id == id)
    except MonteCarloSession.DoesNotExist:
        return None


def get_monte_carlo_sessions(limit: int = 50, offset: int = 0, title_search: str = None, status_filter: str = None, date_filter: str = None):
    """
    Returns a list of MonteCarloSession objects sorted by most recently updated
    """
    query = MonteCarloSession.select().order_by(MonteCarloSession.updated_at.desc())
    
    # Apply title filter (case-insensitive)
    if title_search:
        query = query.where(MonteCarloSession.title.contains(title_search))
    
    # Apply status filter
    if status_filter and status_filter != 'all':
        query = query.where(MonteCarloSession.status == status_filter)
    
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
            query = query.where(MonteCarloSession.created_at >= threshold)
    
    return list(query.limit(limit).offset(offset))


def store_monte_carlo_session(id: str, status: str, state: dict = None, strategy_codes: dict = None) -> None:
    d = {
        'id': id,
        'status': status,
        'state': json.dumps(state) if state else None,
        'created_at': jh.now_to_timestamp(True),
        'updated_at': jh.now_to_timestamp(True)
    }
    
    if strategy_codes is not None:
        d['strategy_codes'] = json.dumps(strategy_codes)
    
    MonteCarloSession.insert(**d).execute()


def update_monte_carlo_session_status(id: str, status: str) -> None:
    d = {
        'status': status,
        'updated_at': jh.now_to_timestamp(True)
    }
    MonteCarloSession.update(**d).where(MonteCarloSession.id == id).execute()


def update_monte_carlo_session_state(id: str, state: dict) -> None:
    d = {
        'state': json.dumps(state),
        'updated_at': jh.now_to_timestamp(True)
    }
    MonteCarloSession.update(**d).where(MonteCarloSession.id == id).execute()


def delete_monte_carlo_session(id: str) -> bool:
    try:
        # Delete child sessions first
        MonteCarloTradesSession.delete().where(
            MonteCarloTradesSession.monte_carlo_session_id == id
        ).execute()
        MonteCarloCandlesSession.delete().where(
            MonteCarloCandlesSession.monte_carlo_session_id == id
        ).execute()
        # Delete parent session
        MonteCarloSession.delete().where(MonteCarloSession.id == id).execute()
        return True
    except Exception as e:
        print(f"Error deleting Monte Carlo session: {e}")
        return False


def update_monte_carlo_session_notes(id: str, title: str = None, description: str = None, strategy_codes: dict = None) -> None:
    d = {
        'updated_at': jh.now_to_timestamp(True)
    }
    
    if title is not None:
        d['title'] = title
    
    if description is not None:
        d['description'] = description
    
    if strategy_codes is not None:
        d['strategy_codes'] = json.dumps(strategy_codes)
    
    MonteCarloSession.update(**d).where(MonteCarloSession.id == id).execute()


def purge_monte_carlo_sessions(days_old: int = None) -> int:
    try:
        current_timestamp = jh.now_to_timestamp(True)
        
        if days_old is not None:
            days_old = int(days_old)
        
        if days_old is not None and days_old > 0:
            threshold = current_timestamp - (days_old * 24 * 60 * 60 * 1000)
            
            all_sessions = MonteCarloSession.select()
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
                    if delete_monte_carlo_session(session_id):
                        deleted_count += 1
                except Exception:
                    pass
        else:
            # Delete all sessions
            all_sessions = MonteCarloSession.select()
            deleted_count = 0
            for session in all_sessions:
                try:
                    if delete_monte_carlo_session(str(session.id)):
                        deleted_count += 1
                except Exception:
                    pass
        
        return deleted_count
    except Exception as e:
        print(f"Error purging Monte Carlo sessions: {e}")
        return 0


# Trades Session Functions
def get_trades_session_by_parent_id(parent_id: str):
    try:
        return MonteCarloTradesSession.get(
            MonteCarloTradesSession.monte_carlo_session_id == parent_id
        )
    except MonteCarloTradesSession.DoesNotExist:
        return None


def store_trades_session(parent_id: str, num_scenarios: int) -> str:
    import uuid
    session_id = str(uuid.uuid4())
    d = {
        'id': session_id,
        'monte_carlo_session_id': parent_id,
        'num_scenarios': num_scenarios,
        'completed_scenarios': 0,
        'status': 'running',
        'created_at': jh.now_to_timestamp(True),
        'updated_at': jh.now_to_timestamp(True)
    }
    MonteCarloTradesSession.insert(**d).execute()
    return session_id


def update_trades_session_progress(id: str, completed: int, results: dict = None) -> None:
    d = {
        'completed_scenarios': completed,
        'updated_at': jh.now_to_timestamp(True)
    }
    if results is not None:
        # Convert NumPy types to native Python types before JSON serialization
        cleaned_results = _convert_numpy_types(results)
        d['results'] = json.dumps(cleaned_results)
    MonteCarloTradesSession.update(**d).where(MonteCarloTradesSession.id == id).execute()


def update_trades_session_status(id: str, status: str) -> None:
    d = {
        'status': status,
        'updated_at': jh.now_to_timestamp(True)
    }
    MonteCarloTradesSession.update(**d).where(MonteCarloTradesSession.id == id).execute()


# Candles Session Functions
def get_candles_session_by_parent_id(parent_id: str):
    try:
        return MonteCarloCandlesSession.get(
            MonteCarloCandlesSession.monte_carlo_session_id == parent_id
        )
    except MonteCarloCandlesSession.DoesNotExist:
        return None


def store_candles_session(parent_id: str, num_scenarios: int, pipeline_type: str, pipeline_params: dict) -> str:
    import uuid
    session_id = str(uuid.uuid4())
    d = {
        'id': session_id,
        'monte_carlo_session_id': parent_id,
        'num_scenarios': num_scenarios,
        'completed_scenarios': 0,
        'status': 'running',
        'pipeline_type': pipeline_type,
        'pipeline_params': json.dumps(pipeline_params),
        'created_at': jh.now_to_timestamp(True),
        'updated_at': jh.now_to_timestamp(True)
    }
    MonteCarloCandlesSession.insert(**d).execute()
    return session_id


def update_candles_session_progress(id: str, completed: int, results: dict = None) -> None:
    d = {
        'completed_scenarios': completed,
        'updated_at': jh.now_to_timestamp(True)
    }
    if results is not None:
        # Convert NumPy types to native Python types before JSON serialization
        cleaned_results = _convert_numpy_types(results)
        d['results'] = json.dumps(cleaned_results)
    MonteCarloCandlesSession.update(**d).where(MonteCarloCandlesSession.id == id).execute()


def update_candles_session_status(id: str, status: str) -> None:
    d = {
        'status': status,
        'updated_at': jh.now_to_timestamp(True)
    }
    MonteCarloCandlesSession.update(**d).where(MonteCarloCandlesSession.id == id).execute()


# Exception and Logs Functions
def store_session_exception(session_id: str, session_type: str, exception: str, traceback: str) -> None:
    d = {
        'exception': exception,
        'traceback': traceback,
        'status': 'stopped',
        'updated_at': jh.now_to_timestamp(True)
    }
    
    if session_type == 'trades':
        MonteCarloTradesSession.update(**d).where(MonteCarloTradesSession.id == session_id).execute()
    elif session_type == 'candles':
        MonteCarloCandlesSession.update(**d).where(MonteCarloCandlesSession.id == session_id).execute()


def append_session_logs(session_id: str, session_type: str, log_message: str) -> None:
    if session_type == 'trades':
        session = MonteCarloTradesSession.get(MonteCarloTradesSession.id == session_id)
        current_logs = session.logs or ''
        new_logs = current_logs + log_message + '\n'
        MonteCarloTradesSession.update(
            logs=new_logs,
            updated_at=jh.now_to_timestamp(True)
        ).where(MonteCarloTradesSession.id == session_id).execute()
    elif session_type == 'candles':
        session = MonteCarloCandlesSession.get(MonteCarloCandlesSession.id == session_id)
        current_logs = session.logs or ''
        new_logs = current_logs + log_message + '\n'
        MonteCarloCandlesSession.update(
            logs=new_logs,
            updated_at=jh.now_to_timestamp(True)
        ).where(MonteCarloCandlesSession.id == session_id).execute()


def append_monte_carlo_session_logs(session_id: str, log_message: str) -> None:
    """Append logs to the parent Monte Carlo session"""
    try:
        session = MonteCarloSession.get(MonteCarloSession.id == session_id)
        current_logs = session.logs or ''
        new_logs = current_logs + log_message + '\n'
        MonteCarloSession.update(
            logs=new_logs,
            updated_at=jh.now_to_timestamp(True)
        ).where(MonteCarloSession.id == session_id).execute()
    except Exception as e:
        # Session doesn't exist yet, silently fail
        jh.dump(f'exception: {e}')
        raise
        pass


