from typing import List
import jesse.helpers as jh
from jesse.models.OpenTab import OpenTab
from jesse.services.db import database
import peewee


def _ensure_db_open() -> None:
    if not database.is_open():
        database.open_connection()


def get_open_tabs(module: str) -> List[OpenTab]:
    """
    Get all open tabs for a module, ordered by order_index
    """
    if jh.is_unit_testing():
        return []
    
    _ensure_db_open()
    
    try:
        return list(OpenTab.select().where(OpenTab.module == module).order_by(OpenTab.order_index.asc()))
    except Exception:
        return []


def get_open_tab_session_ids(module: str) -> List[str]:
    """
    Get session IDs of all open tabs for a module, ordered by order_index
    """
    tabs = get_open_tabs(module)
    return [str(tab.session_id) for tab in tabs]


def add_open_tab(module: str, session_id: str) -> List[str]:
    """
    Add a new tab (or update if exists). Returns ordered list of session IDs.
    For singleton modules (optimization, monte_carlo), ensures only 1 tab exists.
    """
    if jh.is_unit_testing():
        return []
    
    _ensure_db_open()
    
    singleton_modules = ['optimization', 'monte_carlo']
    
    # For singleton modules, remove all existing tabs first
    if module in singleton_modules:
        OpenTab.delete().where(OpenTab.module == module).execute()
        order_index = 0
    else:
        # Check if tab already exists
        existing = OpenTab.select().where(
            (OpenTab.module == module) & (OpenTab.session_id == session_id)
        ).first()
        
        if existing:
            # Already exists, just return current order
            return get_open_tab_session_ids(module)
        
        # Get max order_index for this module
        max_order = OpenTab.select(peewee.fn.MAX(OpenTab.order_index)).where(
            OpenTab.module == module
        ).scalar()
        order_index = (max_order + 1) if max_order is not None else 0
    
    # Create new tab
    now = jh.now_to_timestamp(True)
    OpenTab.create(
        id=jh.generate_unique_id(),
        module=module,
        session_id=session_id,
        order_index=order_index,
        created_at=now,
        updated_at=now
    )
    
    return get_open_tab_session_ids(module)


def remove_open_tab(module: str, session_id: str) -> List[str]:
    """
    Remove a tab and reorder remaining tabs. Returns ordered list of session IDs.
    """
    if jh.is_unit_testing():
        return []
    
    _ensure_db_open()
    
    # Delete the tab
    OpenTab.delete().where(
        (OpenTab.module == module) & (OpenTab.session_id == session_id)
    ).execute()
    
    # Reorder remaining tabs
    tabs = get_open_tabs(module)
    for idx, tab in enumerate(tabs):
        if tab.order_index != idx:
            tab.order_index = idx
            tab.updated_at = jh.now_to_timestamp(True)
            tab.save()
    
    return get_open_tab_session_ids(module)


def reorder_open_tabs(module: str, session_ids: List[str]) -> List[str]:
    """
    Reorder tabs to match the provided session_ids list.
    For singleton modules, ensures only 1 tab exists.
    Returns ordered list of session IDs.
    """
    if jh.is_unit_testing():
        return []
    
    _ensure_db_open()
    
    singleton_modules = ['optimization', 'monte_carlo']
    
    # For singleton modules, keep only the first ID
    if module in singleton_modules:
        session_ids = session_ids[:1] if session_ids else []
        
        # Remove all tabs that aren't in the singleton list
        if session_ids:
            OpenTab.delete().where(
                (OpenTab.module == module) & (OpenTab.session_id != session_ids[0])
            ).execute()
        else:
            OpenTab.delete().where(OpenTab.module == module).execute()
    
    now = jh.now_to_timestamp(True)
    
    # Update order_index for each tab
    for idx, session_id in enumerate(session_ids):
        tab = OpenTab.select().where(
            (OpenTab.module == module) & (OpenTab.session_id == session_id)
        ).first()
        
        if tab:
            tab.order_index = idx
            tab.updated_at = now
            tab.save()
        else:
            # Create if doesn't exist
            OpenTab.create(
                id=jh.generate_unique_id(),
                module=module,
                session_id=session_id,
                order_index=idx,
                created_at=now,
                updated_at=now
            )
    
    # Remove tabs that aren't in the provided list
    OpenTab.delete().where(
        (OpenTab.module == module) & (OpenTab.session_id.not_in(session_ids))
    ).execute()
    
    return get_open_tab_session_ids(module)


def clear_open_tabs(module: str) -> None:
    """
    Remove all open tabs for a module
    """
    if jh.is_unit_testing():
        return
    
    _ensure_db_open()
    
    OpenTab.delete().where(OpenTab.module == module).execute()

