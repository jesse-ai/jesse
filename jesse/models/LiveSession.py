import peewee
import json
from jesse.services.db import database
import jesse.helpers as jh
import json


class LiveSession(peewee.Model):
    id = peewee.UUIDField(primary_key=True)

    # Status of the live session: running, paused, finished, or stopped
    routes = peewee.TextField(null=False)
    data_routes = peewee.TextField(null=False)
    exchange = peewee.TextField(null=False)
    notification_api_key_id = peewee.TextField(null=True)
    debug_mode = peewee.BooleanField(null=False, default=False)
    paper_mode = peewee.BooleanField(null=False, default=False)
    exception = peewee.TextField(null=True)
    traceback = peewee.TextField(null=True)

    status = peewee.CharField(choices=[
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('paused', 'Paused'),
        ('terminated', 'Terminated'),
        ('cancelled', 'Cancelled'),
    ], null=False, default='pending')

    daily_portfolio_balance = peewee.FloatField(null=False, default=0)


    # created_at timestamp
    created_at = peewee.BigIntegerField()

    # updated_at timestamp
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

# # # # # # # # # # # # # # # # # # # # # # # # # # #
# # # # # # # # # DB FUNCTIONS # # # # # # # # # # #
# # # # # # # # # # # # # # # # # # # # # # # # # # #


def get_live_sessions():
    return list(LiveSession.select().order_by(LiveSession.updated_at.desc()))

def get_live_session_by_id(id: str):
    try:
        return LiveSession.get(LiveSession.id == id)
    except LiveSession.DoesNotExist:
        return None


def get_live_session_by_id(id: str):
    try:
        return LiveSession.get(LiveSession.id == id)
    except LiveSession.DoesNotExist:
        return None


def reset_live_session(id: str):
    LiveSession.update(
        results=None,
        form=None,
        updated_at=jh.now_to_timestamp(True)
    ).where(LiveSession.id == id).execute()


def store_live_session(
        id: str,
        routes: list,
        data_routes: list,
        exchange: str,
        notification_api_key_id: str,
        debug_mode: bool,
        paper_mode: bool,
        status: str) -> None:
    LiveSession.create(
        id=id,
        routes=json.dumps(routes),
        data_routes=json.dumps(data_routes),
        exchange=exchange,
        notification_api_key_id=notification_api_key_id,
        debug_mode=debug_mode,
        paper_mode=paper_mode,
        status=status,
        created_at=jh.now_to_timestamp(True),
        updated_at=jh.now_to_timestamp(True)
    )


def update_live_session_status(id: str, status: str) -> None:
    LiveSession.update(
        status=status,
        updated_at=jh.now_to_timestamp(True)
    ).where(LiveSession.id == id).execute()


def update_live_session_daily_portfolio_balance(id: str, daily_portfolio_balance: float) -> None:
    LiveSession.update(
        daily_portfolio_balance=daily_portfolio_balance,
        updated_at=jh.now_to_timestamp(True)
    ).where(LiveSession.id == id).execute()
