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
    
    # Configuration in JSON format - includes all session parameters
    config = peewee.TextField()
    
    # Best trials data in JSON format
    best_trials = peewee.TextField(null=True)
    
    # Objective curve data in JSON format
    objective_curve = peewee.TextField(null=True)
    
    # Progress tracking
    completed_trials = peewee.IntegerField(default=0)
    total_trials = peewee.IntegerField(default=0)
    
    # Training period
    training_start_date = peewee.BigIntegerField()
    training_finish_date = peewee.BigIntegerField()
    
    # Testing period
    testing_start_date = peewee.BigIntegerField()
    testing_finish_date = peewee.BigIntegerField()
    
    # Timestamps for session management
    created_at = peewee.BigIntegerField()
    updated_at = peewee.BigIntegerField(null=True)

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
    def config_json(self):
        """
        Returns the config as a Python dictionary
        """
        return json.loads(self.config)
    
    @config_json.setter
    def config_json(self, config_dict):
        """
        Sets the config from a Python dictionary
        """
        self.config = json.dumps(config_dict)
    
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
    def duration(self):
        """
        Calculate the duration of the session in seconds
        """
        if not self.updated_at:
            # For running sessions, calculate duration up to now
            import jesse.helpers as jh
            return jh.now_to_timestamp() - self.created_at
        
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


def store_optimization_session(
    id: str,
    status: str,
    config: dict,
    training_start_date: int,
    training_finish_date: int,
    testing_start_date: int,
    testing_finish_date: int,
    total_trials: int
) -> None:
    # Create a new session
    d = {
        'id': id,
        'status': status,
        'config': json.dumps(config),
        'training_start_date': training_start_date,
        'training_finish_date': training_finish_date,
        'testing_start_date': testing_start_date,
        'testing_finish_date': testing_finish_date,
        'completed_trials': 0,
        'total_trials': total_trials,
        'created_at': jh.now_to_timestamp(),
    }
    
    # Save to database
    OptimizationSession.insert(**d).execute()
    

def update_optimization_session_status(id: str, status: str) -> None:
    d = {
        'status': status,
        'updated_at': jh.now_to_timestamp()
    }
    
    OptimizationSession.update(**d).where(OptimizationSession.id == id).execute()


def update_optimization_session_trials(
    id: str, 
    completed_trials: int, 
    best_trials: list = None,
    objective_curve: list = None
) -> None:
    d = {
        'completed_trials': completed_trials,
        'updated_at': jh.now_to_timestamp()
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
        'config': session.config_json,
        'best_trials': session.best_trials_json,
        'objective_curve': session.objective_curve_json,
        'completed_trials': session.completed_trials,
        'total_trials': session.total_trials,
        'training_start_date': session.training_start_date,
        'training_finish_date': session.training_finish_date,
        'testing_start_date': session.testing_start_date,
        'testing_finish_date': session.testing_finish_date,
        'created_at': session.created_at,
        'updated_at': session.updated_at,
        'duration': session.duration,
        'best_score': session.best_score
    }


def get_optimization_sessions(status: str = None, limit: int = 20, offset: int = 0) -> list:
    query = OptimizationSession.select().order_by(OptimizationSession.created_at.desc()).limit(limit).offset(offset)
    
    if status:
        query = query.where(OptimizationSession.status == status)
    
    sessions = []
    for session in query:
        sessions.append({
            'id': session.id,
            'status': session.status,
            'config': session.config_json,
            'completed_trials': session.completed_trials,
            'total_trials': session.total_trials,
            'created_at': session.created_at,
            'updated_at': session.updated_at,
            'duration': session.duration,
            'best_score': session.best_score
        })
    
    return sessions


def delete_optimization_session(id: str) -> bool:
    OptimizationSession.delete().where(OptimizationSession.id == id).execute()