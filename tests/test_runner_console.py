"""What research runners print: the version check, the startup banners and the hub's cluster events."""
from jesse.services import runner_console as console


def _runner(name, alive=True, version='3.4.0', role='runner', slots=3, cores=8, seconds=2.0):
    return {'name': name, 'alive': alive, 'jesse_version': version, 'role': role, 'slots': slots, 'cpu_cores': cores,
            'compatible': version == '3.4.0', 'last_seen_seconds_ago': seconds}


def _job(job_id, status, claimed_by=None, attempt=1, error=None, target=None, kind='backtest'):
    return {'id': job_id, 'session_id': f'{job_id}-0000-session', 'kind': kind, 'status': status,
            'claimed_by': claimed_by, 'attempt': attempt, 'error': error, 'target': target}


def test_a_runner_on_another_version_than_the_hub_is_told_exactly_what_to_do():
    problem = console.version_problem('mini', '3.4.0', [_runner('macbook', version='3.4.1', role='hub')])

    assert 'This runner runs Jesse 3.4.0, but the hub "macbook" runs Jesse 3.4.1' in problem
    assert 'pip install jesse==3.4.1' in problem
    assert console.version_problem('mini', '3.4.0', [_runner('macbook', role='hub')]) is None
    assert console.version_problem('mini', '3.4.0', []) is None


def test_the_runner_banner_says_its_role_and_whether_the_hub_is_online():
    lines = console.runner_banner('mini', 3, 8, '3.4.0', '192.168.1.20:5432/jesse_db',
                                  [_runner('macbook', role='hub')], inside_server=False)

    assert lines[0] == 'Research runner "mini": 3 slot(s), 8 CPU cores, Jesse 3.4.0.'
    assert lines[1] == 'Takes research jobs from the database at 192.168.1.20:5432/jesse_db.'
    assert lines[2] == 'Hub "macbook" is online (Jesse 3.4.0).'
    waiting = console.runner_banner('mini', 3, 8, '3.4.0', 'db', [], inside_server=True)
    assert 'alongside this Jesse' in waiting[1] and waiting[2].startswith('The hub is not online yet')


def test_the_hub_banner_lists_its_runners_and_flags_a_version_mismatch():
    lines = console.hub_banner('macbook', 1, 'mini,macbook', '3.4.0', [
        _runner('macbook', role='hub', slots=1, cores=16),
        _runner('mini'),
        _runner('air', alive=False, version='3.3.9', seconds=7300),
    ])

    assert lines[0] == 'Research hub "macbook": Jesse 3.4.0, runs 1 job(s) itself, order: mini,macbook.'
    assert lines[1] == 'Runners:'
    assert lines[2] == '  - mini: online, 3 slot(s), 8 cores'
    assert lines[3] == '  - air: offline (last seen 2 h ago), 3 slot(s), 8 cores, Jesse 3.3.9: VERSION MISMATCH'
    alone = console.hub_banner('macbook', 0, None, '3.4.0', [_runner('macbook', role='hub')])
    assert 'only dispatches jobs' in alone[0] and 'any free runner' in alone[0]
    assert alone[1].startswith('No runners have connected yet')


def test_the_hub_reports_runners_connecting_dropping_and_mismatching_once():
    watcher = console.ClusterWatcher('macbook', '3.4.0')
    assert watcher.update([_runner('mini', alive=False)], []) == []  # baseline

    assert watcher.update([_runner('mini')], []) == [
        ('good', 'Runner "mini" connected: 3 slot(s), 8 cores, Jesse 3.4.0.')]
    assert watcher.update([_runner('mini', alive=False)], []) == [('warn', 'Runner "mini" went offline.')]
    events = watcher.update([_runner('mini'), _runner('air', version='3.3.9')], [])
    assert ('error', 'Runner "air" runs Jesse 3.3.9, this hub runs 3.4.0: it takes no jobs until both run the same '
                     'version.') in events
    assert not any(level == 'error' for level, _ in watcher.update([_runner('mini'), _runner('air', version='3.3.9')], []))


def test_the_hub_reports_each_jobs_journey():
    watcher = console.ClusterWatcher('macbook', '3.4.0')
    watcher.update([], [])
    titles = {'a-0000-session': 'oil variant 7'}

    assert watcher.update([], [_job('a', 'queued')], titles) == [
        ('info', 'Queued backtest a-0000-s "oil variant 7" for any runner.')]
    assert watcher.update([], [_job('a', 'running', 'mini')], titles) == [
        ('info', '"mini" took backtest a-0000-s "oil variant 7".')]
    assert watcher.update([], [_job('a', 'queued', error='Runner mini stopped answering; queued again.')], titles) == [
        ('warn', 'backtest a-0000-s "oil variant 7" went back to the queue: Runner mini stopped answering; queued again.')]
    assert watcher.update([], [_job('a', 'running', 'air', attempt=2)], titles) == [
        ('info', '"air" took backtest a-0000-s "oil variant 7" (attempt 2).')]
    assert watcher.update([], [_job('a', 'done', 'air', attempt=2)], titles) == [
        ('good', 'backtest a-0000-s "oil variant 7" finished on "air".')]
    assert watcher.update([], [_job('a', 'done', 'air', attempt=2)], titles) == []  # reported once

    # A job queued and taken between two checks still shows both steps, the hub's own runs included.
    events = watcher.update([], [_job('b', 'running', 'mini', kind='monte_carlo'), _job('c', 'running', 'macbook')])
    assert events == [('info', 'Queued Monte Carlo run b-0000-s for any runner.'),
                      ('info', '"mini" took Monte Carlo run b-0000-s.'),
                      ('info', 'Queued backtest c-0000-s for any runner.'),
                      ('info', '"macbook" took backtest c-0000-s.')]
    assert watcher.update([], [_job('b', 'failed', 'mini', error='No runner can run this job.', kind='monte_carlo')]) == [
        ('error', 'Monte Carlo run b-0000-s failed: No runner can run this job.')]


def test_the_hub_reports_a_runner_that_was_refused_between_two_checks():
    watcher = console.ClusterWatcher('macbook', '3.4.0')
    watcher.update([_runner('mini')], [])

    events = watcher.update([_runner('mini', alive=False, version='3.4.9')], [])

    assert ('error', 'Runner "mini" tried to start with Jesse 3.4.9 and stopped: this hub runs 3.4.0.') in events
    assert not any(level == 'error' for level, _ in watcher.update([_runner('mini', alive=False, version='3.4.9')], []))


def test_last_seen_reads_naturally():
    assert [console._ago(v) for v in (None, 45, 600, 7300, 3 * 86400, 1e9)] == [
        'never', '45s ago', '10 min ago', '2 h ago', '3 days ago', 'over a month ago']
