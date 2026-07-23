import time
import uuid
from typing import List
import jesse.helpers as jh
from jesse.models.PeriodTemplate import PeriodTemplate
from jesse.services.db import database


def _now_ms() -> int:
    # millisecond precision: jh.now_to_timestamp() only has second resolution,
    # which ties templates saved within the same second and breaks recency order
    return int(time.time() * 1000)


def _ensure_db_open() -> None:
    if not database.is_open():
        database.open_connection()


def _serialize(template: PeriodTemplate) -> dict:
    return {
        'id': str(template.id),
        'start_date': template.start_date,
        'finish_date': template.finish_date,
        'last_used_at': template.last_used_at,
    }


def get_period_templates() -> List[dict]:
    """
    Get all saved period templates, most recently used first
    """
    if jh.is_unit_testing():
        return []

    _ensure_db_open()

    try:
        templates = PeriodTemplate.select().order_by(PeriodTemplate.last_used_at.desc(), PeriodTemplate.created_at.desc())
        return [_serialize(t) for t in templates]
    except Exception:
        return []


def add_period_template(start_date: str, finish_date: str) -> List[dict]:
    """
    Save a date range as a template. If the same range already exists,
    it is just marked as recently used. Returns the updated list.
    """
    if jh.is_unit_testing():
        return []

    _ensure_db_open()

    now = _now_ms()
    existing = PeriodTemplate.get_or_none(
        (PeriodTemplate.start_date == start_date) & (PeriodTemplate.finish_date == finish_date)
    )
    if existing:
        existing.last_used_at = now
        existing.save()
    else:
        PeriodTemplate.create(
            id=uuid.uuid4(),
            start_date=start_date,
            finish_date=finish_date,
            created_at=now,
            last_used_at=now,
        )

    return get_period_templates()


def remove_period_template(template_id: str) -> List[dict]:
    """
    Delete a saved period template. Returns the updated list.
    """
    if jh.is_unit_testing():
        return []

    _ensure_db_open()

    PeriodTemplate.delete().where(PeriodTemplate.id == template_id).execute()
    return get_period_templates()


def touch_period_template(template_id: str) -> List[dict]:
    """
    Mark a template as just used so it sorts to the front. Returns the updated list.
    """
    if jh.is_unit_testing():
        return []

    _ensure_db_open()

    PeriodTemplate.update(last_used_at=_now_ms()).where(
        PeriodTemplate.id == template_id
    ).execute()
    return get_period_templates()
