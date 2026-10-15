from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List
from jesse.repositories import period_template_repository
from jesse.services.auth import require_auth


router = APIRouter(dependencies=[Depends(require_auth)])


class PeriodTemplateAddRequest(BaseModel):
    start_date: str
    finish_date: str


class PeriodTemplateIdRequest(BaseModel):
    id: str


class PeriodTemplatesResponse(BaseModel):
    templates: List[dict]


@router.post('/period-templates/list', response_model=PeriodTemplatesResponse)
async def list_period_templates():
    """
    Get all saved period templates, most recently used first
    """

    templates = period_template_repository.get_period_templates()
    return PeriodTemplatesResponse(templates=templates)


@router.post('/period-templates/add', response_model=PeriodTemplatesResponse)
async def add_period_template(req: PeriodTemplateAddRequest):
    """
    Save a date range as a template (or mark it as used if it already exists).
    Returns the updated list.
    """

    templates = period_template_repository.add_period_template(req.start_date, req.finish_date)
    return PeriodTemplatesResponse(templates=templates)


@router.post('/period-templates/remove', response_model=PeriodTemplatesResponse)
async def remove_period_template(req: PeriodTemplateIdRequest):
    """
    Delete a saved period template. Returns the updated list.
    """

    templates = period_template_repository.remove_period_template(req.id)
    return PeriodTemplatesResponse(templates=templates)


@router.post('/period-templates/touch', response_model=PeriodTemplatesResponse)
async def touch_period_template(req: PeriodTemplateIdRequest):
    """
    Mark a template as just used so it sorts to the front. Returns the updated list.
    """

    templates = period_template_repository.touch_period_template(req.id)
    return PeriodTemplatesResponse(templates=templates)
