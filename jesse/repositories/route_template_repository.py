import hashlib
import json
import time
import uuid
from typing import Any

import peewee

from jesse.models.RouteTemplate import RouteTemplate
from jesse.services.db import database


class RouteTemplateConflict(Exception):
    pass


class RouteTemplateNotFound(Exception):
    pass


def _now_ms() -> int:
    return int(time.time() * 1000)


def _ensure_db_open() -> None:
    if not database.is_open():
        database.open_connection()


def _json(value: list[dict[str, str]]) -> str:
    return json.dumps(value, separators=(',', ':'), ensure_ascii=False)


def _fingerprint(routes: list[dict[str, str]], data_routes: list[dict[str, str]]) -> str:
    payload = json.dumps(
        {'routes': routes, 'data_routes': data_routes},
        separators=(',', ':'),
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def _serialize(template: RouteTemplate) -> dict[str, Any]:
    return {
        'id': str(template.id),
        'name': template.name,
        'routes': json.loads(template.routes),
        'data_routes': json.loads(template.data_routes),
        'created_at': template.created_at,
        'updated_at': template.updated_at,
        'last_used_at': template.last_used_at,
    }


def get_route_templates() -> list[dict[str, Any]]:
    _ensure_db_open()
    templates = RouteTemplate.select().order_by(
        RouteTemplate.last_used_at.desc(),
        RouteTemplate.created_at.desc(),
    )
    return [_serialize(template) for template in templates]


def add_route_template(
    name: str,
    routes: list[dict[str, str]],
    data_routes: list[dict[str, str]],
) -> list[dict[str, Any]]:
    _ensure_db_open()
    now = _now_ms()
    fingerprint = _fingerprint(routes, data_routes)
    existing = RouteTemplate.get_or_none(RouteTemplate.fingerprint == fingerprint)

    if existing is not None:
        existing.last_used_at = now
        existing.save()
        return get_route_templates()

    try:
        RouteTemplate.create(
            id=uuid.uuid4(),
            name=name,
            name_key=name.casefold(),
            routes=_json(routes),
            data_routes=_json(data_routes),
            fingerprint=fingerprint,
            created_at=now,
            updated_at=now,
            last_used_at=now,
        )
    except peewee.IntegrityError as exc:
        existing = RouteTemplate.get_or_none(RouteTemplate.fingerprint == fingerprint)
        if existing is not None:
            existing.last_used_at = now
            existing.save()
            return get_route_templates()
        raise RouteTemplateConflict('A route setup with this name already exists') from exc

    return get_route_templates()


def update_route_template(
    template_id: uuid.UUID,
    name: str,
    routes: list[dict[str, str]],
    data_routes: list[dict[str, str]],
) -> list[dict[str, Any]]:
    _ensure_db_open()
    template = RouteTemplate.get_or_none(RouteTemplate.id == template_id)
    if template is None:
        raise RouteTemplateNotFound('Route setup not found')

    now = _now_ms()
    template.name = name
    template.name_key = name.casefold()
    template.routes = _json(routes)
    template.data_routes = _json(data_routes)
    template.fingerprint = _fingerprint(routes, data_routes)
    template.updated_at = now
    template.last_used_at = now

    try:
        template.save()
    except peewee.IntegrityError as exc:
        raise RouteTemplateConflict(
            'A route setup with this name or configuration already exists'
        ) from exc

    return get_route_templates()


def remove_route_template(template_id: uuid.UUID) -> list[dict[str, Any]]:
    _ensure_db_open()
    deleted = RouteTemplate.delete().where(RouteTemplate.id == template_id).execute()
    if deleted == 0:
        raise RouteTemplateNotFound('Route setup not found')
    return get_route_templates()


def touch_route_template(template_id: uuid.UUID) -> list[dict[str, Any]]:
    _ensure_db_open()
    updated = RouteTemplate.update(last_used_at=_now_ms()).where(
        RouteTemplate.id == template_id
    ).execute()
    if updated == 0:
        raise RouteTemplateNotFound('Route setup not found')
    return get_route_templates()
