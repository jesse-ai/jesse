"""Publish explicit execution stages without inventing completion percentages."""
import jesse.helpers as jh
from jesse.services.redis import sync_publish


def publish_status(message: str, *, event: str = 'progressbar', total: int | None = None, current: float = 0) -> None:
    """Describe an untimed stage; current preserves measured work during finalization."""
    if jh.is_unit_testing():
        return
    payload = {
        'current': current,
        'estimated_remaining_seconds': 0,
        'message': message,
        'indeterminate': True,
    }
    if total is not None:
        payload['total'] = total
    sync_publish(event, payload)
