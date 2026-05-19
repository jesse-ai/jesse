import peewee
import json
from jesse.services.db import database
import jesse.helpers as jh


if database.is_closed():
    database.open_connection()


class SignificanceTestSession(peewee.Model):
    id = peewee.UUIDField(primary_key=True)
    status = peewee.CharField()
    state = peewee.TextField(null=True)
    title = peewee.CharField(max_length=255, null=True)
    description = peewee.TextField(null=True)
    strategy_codes = peewee.TextField(null=True)
    results = peewee.TextField(null=True)
    chart_path = peewee.CharField(null=True)
    exception = peewee.TextField(null=True)
    traceback = peewee.TextField(null=True)
    theme = peewee.CharField(default='light')
    created_at = peewee.BigIntegerField()
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

    @property
    def state_json(self):
        if not self.state:
            return {}
        s = json.loads(self.state)
        if isinstance(s, dict) and 'form' in s and isinstance(s['form'], dict):
            for key in ['debug_mode', 'export_chart', 'export_tradingview', 'export_csv', 'export_json', 'fast_mode', 'benchmark']:
                if key in s['form']:
                    s['form'][key] = jh.normalize_bool(s['form'].get(key))
        return s

    @state_json.setter
    def state_json(self, state_data):
        self.state = json.dumps(state_data)

    @property
    def strategy_codes_json(self):
        if not self.strategy_codes:
            return {}
        return json.loads(self.strategy_codes)

    @strategy_codes_json.setter
    def strategy_codes_json(self, codes_dict):
        self.strategy_codes = json.dumps(codes_dict) if codes_dict else None

    @property
    def results_json(self):
        if not self.results:
            return {}
        return json.loads(self.results)

    @results_json.setter
    def results_json(self, results_dict):
        self.results = json.dumps(results_dict) if results_dict else None


def get_significance_test_session_by_id(session_id: str):
    try:
        return SignificanceTestSession.get(SignificanceTestSession.id == session_id)
    except SignificanceTestSession.DoesNotExist:
        return None


def get_significance_test_sessions(
    limit: int = 50,
    offset: int = 0,
    title_search: str = None,
    status_filter: str = None,
    date_filter: str = None,
):
    import arrow
    query = SignificanceTestSession.select().order_by(SignificanceTestSession.updated_at.desc())

    if title_search:
        query = query.where(SignificanceTestSession.title.contains(title_search))

    if status_filter:
        query = query.where(SignificanceTestSession.status == status_filter)

    if date_filter:
        now = arrow.utcnow()
        days_map = {'7_days': 7, '30_days': 30, '90_days': 90}
        if date_filter in days_map:
            cutoff = now.shift(days=-days_map[date_filter]).int_timestamp * 1000
            query = query.where(SignificanceTestSession.created_at >= cutoff)

    return list(query.offset(offset).limit(limit))


def store_significance_test_session(id: str, status: str, state: dict, strategy_codes: dict = None, theme: str = 'light'):
    now = jh.now_to_timestamp()
    session = SignificanceTestSession.create(
        id=id,
        status=status,
        state=json.dumps(state) if state else None,
        strategy_codes=json.dumps(strategy_codes) if strategy_codes else None,
        theme=theme,
        created_at=now,
        updated_at=now,
    )
    return session


def update_significance_test_session_status(session_id: str, status: str):
    SignificanceTestSession.update(
        status=status,
        updated_at=jh.now_to_timestamp(),
    ).where(SignificanceTestSession.id == session_id).execute()


def update_significance_test_session_state(session_id: str, state: dict, strategy_codes: dict = None):
    update_data = {
        'state': json.dumps(state),
        'updated_at': jh.now_to_timestamp(),
    }
    if strategy_codes is not None:
        update_data['strategy_codes'] = json.dumps(strategy_codes)
    SignificanceTestSession.update(**update_data).where(SignificanceTestSession.id == session_id).execute()


def update_significance_test_session_results(session_id: str, results: dict, chart_path: str = None):
    update_data = {
        'results': json.dumps(results),
        'updated_at': jh.now_to_timestamp(),
    }
    if chart_path:
        update_data['chart_path'] = chart_path
    SignificanceTestSession.update(**update_data).where(SignificanceTestSession.id == session_id).execute()


def update_significance_test_session_notes(session_id: str, title: str = None, description: str = None, strategy_codes: dict = None):
    update_data = {'updated_at': jh.now_to_timestamp()}
    if title is not None:
        update_data['title'] = title
    if description is not None:
        update_data['description'] = description
    if strategy_codes is not None:
        update_data['strategy_codes'] = json.dumps(strategy_codes)
    SignificanceTestSession.update(**update_data).where(SignificanceTestSession.id == session_id).execute()


def store_significance_test_exception(session_id: str, error: str, traceback_str: str):
    SignificanceTestSession.update(
        exception=error,
        traceback=traceback_str,
        updated_at=jh.now_to_timestamp(),
    ).where(SignificanceTestSession.id == session_id).execute()


def delete_significance_test_session(session_id: str):
    try:
        session = SignificanceTestSession.get(SignificanceTestSession.id == session_id)
        # Clean up chart file if it exists
        if session.chart_path:
            import os
            try:
                os.remove(session.chart_path)
            except Exception:
                pass
        session.delete_instance()
        return True
    except SignificanceTestSession.DoesNotExist:
        return False


def purge_significance_test_sessions(days_old: int = None):
    import arrow
    if days_old is None:
        sessions = list(SignificanceTestSession.select())
    else:
        cutoff = arrow.utcnow().shift(days=-days_old).int_timestamp * 1000
        sessions = list(SignificanceTestSession.select().where(SignificanceTestSession.created_at < cutoff))

    count = 0
    for session in sessions:
        if session.chart_path:
            import os
            try:
                os.remove(session.chart_path)
            except Exception:
                pass
        session.delete_instance()
        count += 1
    return count


def get_running_significance_test_session_id():
    try:
        session = SignificanceTestSession.get(SignificanceTestSession.status == 'running')
        return str(session.id)
    except SignificanceTestSession.DoesNotExist:
        return None
