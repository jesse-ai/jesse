import peewee
import json
from itertools import chain
import numpy as np
from jesse.services.db import database
import jesse.helpers as jh


# ASCII JSON keeps each SQL parameter at most 1 MiB, well below PostgreSQL's
# allocation limit even after quoting. Stream encoding avoids a second full copy.
_RESULT_CHUNK_SIZE = 1024 * 1024
_RESULT_CHUNKS_KEY = '_jesse_result_chunks_v1'


class _ResultEncoder(json.JSONEncoder):
    """Convert NumPy values lazily instead of copying every scenario recursively."""

    def default(self, obj):
        if isinstance(obj, (np.integer, np.floating, np.bool_)):
            return obj.item()
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


def _result_chunks(results: dict):
    """Yield bounded JSON fragments, including when one encoded value is large."""
    buffer = ''
    for token in _ResultEncoder(separators=(',', ':'), ensure_ascii=True).iterencode(results):
        offset = 0
        while offset < len(token):
            length = min(_RESULT_CHUNK_SIZE - len(buffer), len(token) - offset)
            buffer += token[offset:offset + length]
            offset += length
            if len(buffer) == _RESULT_CHUNK_SIZE:
                yield buffer
                buffer = ''
    if buffer:
        yield buffer


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
        s = json.loads(self.state)
        if isinstance(s, dict) and 'form' in s and isinstance(s['form'], dict):
            for key in ['debug_mode', 'export_chart', 'export_csv', 'export_json', 'fast_mode', 'benchmark']:
                if key in s['form']:
                    s['form'][key] = jh.normalize_bool(s['form'].get(key))
        return s

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
        return _load_results(self.id, self.results)

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
        return _load_results(self.id, self.results)

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


class MonteCarloResultChunk(peewee.Model):
    """Lossless result fragments keyed by the globally unique child session ID."""

    session_id = peewee.UUIDField()
    chunk_index = peewee.IntegerField()
    payload = peewee.TextField()

    class Meta:
        database = database.db
        primary_key = peewee.CompositeKey('session_id', 'chunk_index')


def _load_results(session_id, serialized: str) -> dict:
    """Read both legacy inline JSON and the chunked result representation."""
    results = json.loads(serialized) if serialized else {}
    chunk_count = results.get(_RESULT_CHUNKS_KEY)
    if chunk_count is None:
        return results
    query = (MonteCarloResultChunk.select(MonteCarloResultChunk.payload)
             .where(MonteCarloResultChunk.session_id == session_id)
             .order_by(MonteCarloResultChunk.chunk_index))
    chunks = [row.payload for row in query.iterator()]
    if len(chunks) != chunk_count:
        raise ValueError('Monte Carlo result chunks are incomplete')
    return json.loads(''.join(chunks))


def _store_results(model, session_id: str, completed: int, results: dict) -> None:
    """Commit fragments and their summary together, rolling back failed writes."""
    chunks = iter(_result_chunks(results))
    first = next(chunks)
    second = next(chunks, None)
    # A failed PostgreSQL write must roll back before the runner stores its
    # exception, and must not leave a manifest pointing to incomplete fragments.
    with model._meta.database.atomic():
        MonteCarloResultChunk.delete().where(MonteCarloResultChunk.session_id == session_id).execute()
        if second is None:
            serialized = first
        else:
            count = 0
            for count, payload in enumerate(chain((first, second), chunks), start=1):
                MonteCarloResultChunk.insert(
                    session_id=session_id, chunk_index=count - 1, payload=payload,
                ).execute()
            # Summary polling never needs to hydrate all curves and trade lists.
            summary = {key: value for key, value in results.items() if key not in {'original', 'scenarios'}}
            summary[_RESULT_CHUNKS_KEY] = count
            serialized = json.dumps(summary, cls=_ResultEncoder, separators=(',', ':'))
            # The summary uses the same SQL parameter bound as a data fragment.
            if len(serialized) > _RESULT_CHUNK_SIZE:
                raise ValueError('Monte Carlo summary exceeds 1 MiB; reduce the number of scenarios.')
        model.update(
            results=serialized,
            completed_scenarios=completed,
            updated_at=jh.now_to_timestamp(True),
        ).where(model.id == session_id).execute()


# Create tables if database is open
if database.is_open():
    MonteCarloSession.create_table()
    MonteCarloTradesSession.create_table()
    MonteCarloCandlesSession.create_table()
    MonteCarloResultChunk.create_table()


# # # # # # # # # # # # # # # # # # # # # # # # # # # 
# # # # # # # # # DB FUNCTIONS # # # # # # # # #
# # # # # # # # # # # # # # # # # # # # # # # # # # # 

# Parent Session Functions
def get_monte_carlo_session_by_id(id: str):
    try:
        session = MonteCarloSession.get(MonteCarloSession.id == id)
        return _reconcile_monte_carlo_session_status(session)
    except MonteCarloSession.DoesNotExist:
        return None


def get_monte_carlo_sessions(limit: int = 50, offset: int = 0, title_search: str = None, status_filter: str = None, date_filter: str = None):
    """
    Returns a list of MonteCarloSession objects sorted by most recently updated.
    Excludes draft sessions by default.
    """
    query = MonteCarloSession.select().where(MonteCarloSession.status != 'draft').order_by(MonteCarloSession.updated_at.desc())
    
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
    
    return [
        _reconcile_monte_carlo_session_status(session)
        for session in query.limit(limit).offset(offset)
    ]


def store_monte_carlo_session(id: str, status: str, state: dict = None, strategy_codes: dict = None) -> None:
    if isinstance(state, dict) and 'form' in state and isinstance(state['form'], dict):
        for key in ['debug_mode', 'export_chart', 'export_csv', 'export_json', 'fast_mode', 'benchmark']:
            if key in state['form']:
                state['form'][key] = jh.normalize_bool(state['form'].get(key))
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


def update_monte_carlo_session_state(id: str, state: dict, strategy_codes: dict = None) -> None:
    """
    Update or create (upsert) monte carlo session state. If session doesn't exist, creates as draft.
    """
    if isinstance(state, dict) and 'form' in state and isinstance(state['form'], dict):
        for key in ['debug_mode', 'export_chart', 'export_csv', 'export_json', 'fast_mode', 'benchmark']:
            if key in state['form']:
                state['form'][key] = jh.normalize_bool(state['form'].get(key))
    existing = MonteCarloSession.select().where(MonteCarloSession.id == id).first()
    
    if existing:
        # Update existing session's state
        d = {
            'state': json.dumps(state),
            'updated_at': jh.now_to_timestamp(True)
        }
        if strategy_codes is not None:
            d['strategy_codes'] = json.dumps(strategy_codes)
        MonteCarloSession.update(**d).where(MonteCarloSession.id == id).execute()
    else:
        # Create new draft session
        d = {
            'id': id,
            'status': 'draft',
            'state': json.dumps(state),
            'created_at': jh.now_to_timestamp(True),
            'updated_at': jh.now_to_timestamp(True)
        }
        MonteCarloSession.insert(**d).execute()


def delete_monte_carlo_session(id: str) -> bool:
    try:
        with MonteCarloSession._meta.database.atomic():
            # Child IDs are UUIDs shared with the chunk table; clean every run of a
            # resumed parent as well as the currently displayed child sessions.
            for model in (MonteCarloTradesSession, MonteCarloCandlesSession):
                child_ids = model.select(model.id).where(model.monte_carlo_session_id == id)
                MonteCarloResultChunk.delete().where(MonteCarloResultChunk.session_id.in_(child_ids)).execute()
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


def get_running_monte_carlo_session_id():
    try:
        session = MonteCarloSession.select().where(MonteCarloSession.status == 'running').order_by(MonteCarloSession.updated_at.desc()).first()
        if session:
            session = _reconcile_monte_carlo_session_status(session)
            return str(session.id) if session.status == 'running' else None
        return None
    except Exception as e:
        raise e


def _reconcile_monte_carlo_session_status(session: MonteCarloSession):
    if session.status != 'running' or jh.is_unit_testing():
        return session

    from jesse.services.redis import is_process_active

    if not is_process_active(str(session.id)):
        update_monte_carlo_session_status(str(session.id), 'stopped')
        session.status = 'stopped'

    return session

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
    if results is not None:
        _store_results(MonteCarloTradesSession, id, completed, results)
        return
    d = {
        'completed_scenarios': completed,
        'updated_at': jh.now_to_timestamp(True)
    }
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
    if results is not None:
        _store_results(MonteCarloCandlesSession, id, completed, results)
        return
    d = {
        'completed_scenarios': completed,
        'updated_at': jh.now_to_timestamp(True)
    }
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

