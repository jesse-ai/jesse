from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List
from jesse.repositories import open_tab_repository
from jesse.services.auth import require_auth


router = APIRouter(dependencies=[Depends(require_auth)])


class TabsListRequest(BaseModel):
    module: str


class TabsAddRequest(BaseModel):
    module: str
    id: str


class TabsRemoveRequest(BaseModel):
    module: str
    id: str


class TabsReorderRequest(BaseModel):
    module: str
    ids: List[str]


class TabsResponse(BaseModel):
    ids: List[str]


@router.post('/tabs/list', response_model=TabsResponse)
async def list_tabs(req: TabsListRequest):
    """
    Get ordered list of open tab session IDs for a module
    """
    
    session_ids = open_tab_repository.get_open_tab_session_ids(req.module)
    return TabsResponse(ids=session_ids)


@router.post('/tabs/add', response_model=TabsResponse)
async def add_tab(req: TabsAddRequest):
    """
    Add a new tab (or update if exists). Returns ordered list.
    For singleton modules, ensures only 1 tab exists.
    """
    
    session_ids = open_tab_repository.add_open_tab(req.module, req.id)
    return TabsResponse(ids=session_ids)


@router.post('/tabs/remove', response_model=TabsResponse)
async def remove_tab(req: TabsRemoveRequest):
    """
    Remove a tab and reorder remaining tabs. Returns ordered list.
    """
    
    session_ids = open_tab_repository.remove_open_tab(req.module, req.id)
    return TabsResponse(ids=session_ids)


@router.post('/tabs/reorder', response_model=TabsResponse)
async def reorder_tabs(req: TabsReorderRequest):
    """
    Reorder tabs to match the provided session_ids list.
    For singleton modules, ensures only 1 tab exists.
    """
    
    session_ids = open_tab_repository.reorder_open_tabs(req.module, req.ids)
    return TabsResponse(ids=session_ids)

