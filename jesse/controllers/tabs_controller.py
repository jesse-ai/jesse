from jesse.services.auth import require_auth
from fastapi import APIRouter, Header, Depends
from pydantic import BaseModel
from typing import List, Optional
from jesse.repositories import open_tab_repository


router = APIRouter()


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
async def list_tabs(req: TabsListRequest, authorization: Optional[str] = Header(None),
    _auth: None = Depends(require_auth)):
    """
    Get ordered list of open tab session IDs for a module
    """
    
    session_ids = open_tab_repository.get_open_tab_session_ids(req.module)
    return TabsResponse(ids=session_ids)


@router.post('/tabs/add', response_model=TabsResponse)
async def add_tab(req: TabsAddRequest, authorization: Optional[str] = Header(None),
    _auth: None = Depends(require_auth)):
    """
    Add a new tab (or update if exists). Returns ordered list.
    For singleton modules, ensures only 1 tab exists.
    """
    
    session_ids = open_tab_repository.add_open_tab(req.module, req.id)
    return TabsResponse(ids=session_ids)


@router.post('/tabs/remove', response_model=TabsResponse)
async def remove_tab(req: TabsRemoveRequest, authorization: Optional[str] = Header(None),
    _auth: None = Depends(require_auth)):
    """
    Remove a tab and reorder remaining tabs. Returns ordered list.
    """
    
    session_ids = open_tab_repository.remove_open_tab(req.module, req.id)
    return TabsResponse(ids=session_ids)


@router.post('/tabs/reorder', response_model=TabsResponse)
async def reorder_tabs(req: TabsReorderRequest, authorization: Optional[str] = Header(None),
    _auth: None = Depends(require_auth)):
    """
    Reorder tabs to match the provided session_ids list.
    For singleton modules, ensures only 1 tab exists.
    """
    
    session_ids = open_tab_repository.reorder_open_tabs(req.module, req.ids)
    return TabsResponse(ids=session_ids)

