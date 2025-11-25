import peewee
import json
from jesse.services.db import database
import jesse.helpers as jh
import json


if database.is_closed():
    database.open_connection()


class OptimizationSession(peewee.Model):
    id = peewee.UUIDField(primary_key=True)
    
    # Status of the optimization session: running, paused, finished, or stopped
    status = peewee.CharField()
    
    # Best trials data in JSON format
    best_trials = peewee.TextField(null=True)
    
    # Objective curve data in JSON format
    objective_curve = peewee.TextField(null=True)
    
    # Frontend state in JSON format - used for restoring UI state
    state = peewee.TextField(null=True)
    
    # Progress tracking
    completed_trials = peewee.IntegerField(default=0)
    total_trials = peewee.IntegerField(default=0)
    exception = peewee.TextField(null=True)
    traceback = peewee.TextField(null=True)
    
    # User notes
    title = peewee.CharField(max_length=255, null=True)
    description = peewee.TextField(null=True)
    strategy_codes = peewee.TextField(null=True)

    # Timestamps for session management
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
    def best_trials_json(self):
        """
        Returns the best trials as a Python list
        """
        if not self.best_trials:
            return []
        return json.loads(self.best_trials)
    
    @best_trials_json.setter
    def best_trials_json(self, trials_list):
        """
        Sets the best trials from a Python list
        """
        self.best_trials = json.dumps(trials_list)
    
    @property
    def objective_curve_json(self):
        """
        Returns the objective curve data as a Python list
        """
        if not self.objective_curve:
            return []
        return json.loads(self.objective_curve)
    
    @objective_curve_json.setter
    def objective_curve_json(self, curve_data):
        """
        Sets the objective curve data from a Python list
        """
        self.objective_curve = json.dumps(curve_data)
    
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
        self.state = json.dumps(state_data)
    
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
            import jesse.helpers as jh
            return jh.now_to_timestamp(True) - self.created_at
        
        # For completed sessions, use the stored timestamps
        return self.updated_at - self.created_at
    
    @property
    def best_score(self):
        """
        Get the best score from the best trials
        """
        trials = self.best_trials_json
        if not trials:
            return None
            
        # The first trial in the list should be the best one
        # (assuming trials are sorted by score)
        return trials[0].get('fitness', None)


# if database is open, create the table
if database.is_open():
    OptimizationSession.create_table()

# # # # # # # # # # # # # # # # # # # # # # # # # # # 
# # # # # # # # # DB FUNCTIONS # # # # # # # # #
# # # # # # # # # # # # # # # # # # # # # # # # # # # 

def get_optimization_session_by_id(id: str):
    try:
        return OptimizationSession.get(OptimizationSession.id == id)
    except OptimizationSession.DoesNotExist:
        return None


def reset_optimization_session(id: str):
    OptimizationSession.update(
        status='running',
        completed_trials=0,
        best_trials=None,
        objective_curve=None,
        exception=None,
        traceback=None,
        updated_at=jh.now_to_timestamp(True)
    ).where(OptimizationSession.id == id).execute()


def store_optimization_session(
    id: str,
    status: str,
    strategy_codes: dict = None
) -> None:
    # Create a new session
    d = {
        'id': id,
        'status': status,
        'completed_trials': 0,
        'created_at': jh.now_to_timestamp(True),
        'updated_at': jh.now_to_timestamp(True)
    }
    
    if strategy_codes is not None:
        d['strategy_codes'] = json.dumps(strategy_codes)
    
    # Save to database
    OptimizationSession.insert(**d).execute()
    

def update_optimization_session_status(id: str, status: str) -> None:
    d = {
        'status': status,
        'updated_at': jh.now_to_timestamp(True)
    }
    
    OptimizationSession.update(**d).where(OptimizationSession.id == id).execute()


def add_session_exception(id: str, exception: str, traceback: str) -> None:
    d = {
        'exception': exception,
        'traceback': traceback,
        'updated_at': jh.now_to_timestamp(True)
    }

    OptimizationSession.update(**d).where(OptimizationSession.id == id).execute()


def update_optimization_session_trials(
    id: str, 
    completed_trials: int, 
    best_trials: list = None,
    objective_curve: list = None,
    total_trials: int = None
) -> None:
    d = {
        'completed_trials': completed_trials,
        'total_trials': total_trials,
        'updated_at': jh.now_to_timestamp(True)
    }

    if best_trials is not None:
        d['best_trials'] = json.dumps(best_trials)

    if objective_curve is not None:
        d['objective_curve'] = json.dumps(objective_curve)

    OptimizationSession.update(**d).where(OptimizationSession.id == id).execute()
    

def get_optimization_session(id: str) -> dict:
    session = OptimizationSession.get(OptimizationSession.id == id)
    return {
        'id': session.id,
        'status': session.status,
        'best_trials': session.best_trials_json,
        'objective_curve': session.objective_curve_json,
        'completed_trials': session.completed_trials,
        'created_at': session.created_at,
        'updated_at': session.updated_at,
        'best_score': session.best_score,
        'state': session.state_json
    }


def get_optimization_sessions(limit: int = 50, offset: int = 0, title_search: str = None, status_filter: str = None, date_filter: str = None) -> list:
    """
    Returns a list of OptimizationSession objects sorted by most recently updated
    """
    query = OptimizationSession.select().order_by(OptimizationSession.updated_at.desc())
    
    # Apply title filter (case-insensitive)
    if title_search:
        query = query.where(OptimizationSession.title.contains(title_search))
    
    # Apply status filter
    if status_filter and status_filter != 'all':
        query = query.where(OptimizationSession.status == status_filter)
    
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
            query = query.where(OptimizationSession.created_at >= threshold)
    
    return list(query.limit(limit).offset(offset))


def delete_optimization_session(id: str) -> bool:
    try:
        OptimizationSession.delete().where(OptimizationSession.id == id).execute()
        return True
    except Exception as e:
        print(f"Error deleting optimization session: {e}")
        return False


def update_optimization_session_state(id: str, state: dict) -> None:
    d = {
        'state': json.dumps(state),
        'updated_at': jh.now_to_timestamp(True)
    }
    
    OptimizationSession.update(**d).where(OptimizationSession.id == id).execute()


def update_optimization_session_notes(id: str, title: str = None, description: str = None, strategy_codes: dict = None) -> None:
    d = {
        'updated_at': jh.now_to_timestamp(True)
    }
    
    if title is not None:
        d['title'] = title
    
    if description is not None:
        d['description'] = description
    
    if strategy_codes is not None:
        d['strategy_codes'] = json.dumps(strategy_codes)
    
    OptimizationSession.update(**d).where(OptimizationSession.id == id).execute()


def purge_optimization_sessions(days_old: int = None) -> int:
    try:
        current_timestamp = jh.now_to_timestamp(True)
        
        if days_old is not None:
            days_old = int(days_old)
        
        if days_old is not None and days_old > 0:
            threshold = current_timestamp - (days_old * 24 * 60 * 60 * 1000)
            
            all_sessions = OptimizationSession.select()
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
                    OptimizationSession.delete().where(OptimizationSession.id == session_id).execute()
                    deleted_count += 1
                except Exception:
                    pass
        else:
            deleted_count = OptimizationSession.delete().execute()
        
        return deleted_count
    except Exception as e:
        print(f"Error purging optimization sessions: {e}")
        return 0