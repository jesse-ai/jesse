from typing import List, Optional
import json
import jesse.helpers as jh
from jesse.models.LiveSession import LiveSession
from jesse.services.db import database
from jesse.enums import live_session_statuses
from jesse.enums import live_session_modes



def _ensure_db_open() -> None:
    if not database.is_open():
        database.open_connection()


def get_live_session_by_id(session_id: str) -> Optional[LiveSession]:
    """
    Get a single live session by ID
    """
    if jh.is_unit_testing():
        return None
    
    _ensure_db_open()
    
    try:
        return LiveSession.select().where(LiveSession.id == session_id).first()
    except Exception:
        return None


def get_live_sessions(
    limit: int = 50,
    offset: int = 0,
    title_search: str = None,
    status_filter: str = None,
    date_filter: str = None,
    mode_filter: str = None
) -> List[LiveSession]:
    """
    Returns a list of LiveSession objects sorted by most recently updated with pagination and filters.
    Excludes draft sessions by default.
    """
    if jh.is_unit_testing():
        return []
    
    _ensure_db_open()
    
    
    query = LiveSession.select().where(LiveSession.status != live_session_statuses.DRAFT).order_by(LiveSession.updated_at.desc())
    
    # Apply title filter (case-insensitive)
    if title_search:
        query = query.where(LiveSession.title.contains(title_search))
    
    # Apply status filter
    if status_filter and status_filter != 'all':
        query = query.where(LiveSession.status == status_filter)
    
    # Apply mode filter
    if mode_filter and mode_filter != 'all':
        query = query.where(LiveSession.session_mode == mode_filter)
    
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
            query = query.where(LiveSession.created_at >= threshold)
    
    return list(query.limit(limit).offset(offset))


def store_live_session(
    id: str,
    status: str,
    session_mode: str,
    exchange: str,
    state: dict = None
) -> None:
    """
    Create or update a live session record
    """
    if jh.is_unit_testing():
        return
    
    _ensure_db_open()
    
    # Check if session already exists
    existing_session = get_live_session_by_id(id)
    
    if existing_session:
        # Update existing session - reset it to fresh state
        d = {
            'status': status,
            'session_mode': session_mode,
            'exchange': exchange,
            'state': json.dumps(state) if state else None,
            'finished_at': None,
            'exception': None,
            'traceback': None,
            'updated_at': jh.now_to_timestamp(True)
        }
        LiveSession.update(**d).where(LiveSession.id == id).execute()
    else:
        # Create a new session
        d = {
            'id': id,
            'status': status,
            'session_mode': session_mode,
            'exchange': exchange,
            'state': json.dumps(state) if state else None,
            'created_at': jh.now_to_timestamp(True),
            'updated_at': jh.now_to_timestamp(True)
        }
        LiveSession.insert(**d).execute()


def update_live_session_status(id: str, status: str) -> None:
    """
    Update the status of a live session
    """
    if jh.is_unit_testing():
        return
    
    _ensure_db_open()
    
    d = {
        'status': status,
        'updated_at': jh.now_to_timestamp(True)
    }
    
    LiveSession.update(**d).where(LiveSession.id == id).execute()


def update_live_session_state(id: str, state: dict) -> None:
    """
    Update the state of a live session
    """
    if jh.is_unit_testing():
        return
    
    _ensure_db_open()
    
    d = {
        'state': json.dumps(state),
        'updated_at': jh.now_to_timestamp(True)
    }
    
    LiveSession.update(**d).where(LiveSession.id == id).execute()


def upsert_live_session_state(id: str, state: dict) -> None:
    """
    Create or update the state of a live session. If session doesn't exist, creates as draft.
    """
    if jh.is_unit_testing():
        return
    
    _ensure_db_open()
    
    existing_session = get_live_session_by_id(id)
    
    if existing_session:
        # Update existing session's state
        d = {
            'state': json.dumps(state),
            'updated_at': jh.now_to_timestamp(True)
        }
        LiveSession.update(**d).where(LiveSession.id == id).execute()
    else:
        # Extract exchange from state.form if available
        exchange = state.get('form', {}).get('exchange', '')
        session_mode = live_session_modes.PAPERTRADE if state.get('form', {}).get('paper_mode', True) else live_session_modes.LIVETRADE
        
        d = {
            'id': id,
            'status': live_session_statuses.DRAFT,
            'session_mode': session_mode,
            'exchange': exchange,
            'state': json.dumps(state),
            'created_at': jh.now_to_timestamp(True),
            'updated_at': jh.now_to_timestamp(True)
        }
        LiveSession.insert(**d).execute()


def update_live_session_notes(
    id: str,
    title: str = None,
    description: str = None,
    strategy_codes: dict = None
) -> None:
    """
    Update the notes (title, description, strategy_codes) of a live session
    """
    if jh.is_unit_testing():
        return
    
    _ensure_db_open()
    
    d = {
        'updated_at': jh.now_to_timestamp(True)
    }
    
    if title is not None:
        d['title'] = title
    
    if description is not None:
        d['description'] = description
    
    if strategy_codes is not None:
        d['strategy_codes'] = json.dumps(strategy_codes)
    
    LiveSession.update(**d).where(LiveSession.id == id).execute()


def update_live_session_finished(id: str, finished_at: int = None) -> None:
    """
    Mark a live session as finished with the finish timestamp
    """
    if jh.is_unit_testing():
        return
    
    _ensure_db_open()
    
    d = {
        'finished_at': finished_at if finished_at else jh.now_to_timestamp(True),
        'updated_at': jh.now_to_timestamp(True)
    }
    
    LiveSession.update(**d).where(LiveSession.id == id).execute()


def store_live_session_exception(id: str, exception: str, traceback: str) -> None:
    """
    Store exception information for a live session
    """
    if jh.is_unit_testing():
        return
    
    _ensure_db_open()
    
    d = {
        'exception': exception,
        'traceback': traceback,
        'updated_at': jh.now_to_timestamp(True)
    }
    
    LiveSession.update(**d).where(LiveSession.id == id).execute()


def delete_live_session(session_id: str) -> bool:
    """
    Delete a live session from the database
    """
    if jh.is_unit_testing():
        return True
    
    _ensure_db_open()
    
    try:
        LiveSession.delete().where(LiveSession.id == session_id).execute()
        return True
    except Exception as e:
        jh.debug(f"Error deleting live session: {e}")
        return False


def purge_live_sessions(days_old: int = None) -> int:
    """
    Purge live sessions older than specified days
    Returns the number of sessions deleted
    """
    if jh.is_unit_testing():
        return 0
    
    _ensure_db_open()
    
    try:
        current_timestamp = jh.now_to_timestamp(True)
        
        if days_old is not None:
            days_old = int(days_old)
        
        if days_old is not None and days_old > 0:
            threshold = current_timestamp - (days_old * 24 * 60 * 60 * 1000)
            
            all_sessions = LiveSession.select()
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
                    LiveSession.delete().where(LiveSession.id == session_id).execute()
                    deleted_count += 1
                except Exception:
                    pass
        else:
            # Delete all sessions
            deleted_count = LiveSession.delete().execute()
        
        return deleted_count
    except Exception as e:
        jh.debug(f"Error purging live sessions: {e}")
        return 0

