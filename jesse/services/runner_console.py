"""
What the research runners feature prints in the terminal (see services/runner.py): the startup
banner of a hub or runner, the Jesse version check between them, and on the hub a one-line event
for each change across the cluster (a runner connecting or going offline, a job taken, finished,
handed to another runner). The functions here only turn database rows into lines; runner.py prints.
"""

from typing import Optional

LEVEL_COLORS = {'info': 'cyan', 'good': 'green', 'warn': 'yellow', 'error': 'red'}
_ENDED_JOB = ('done', 'failed', 'cancelled')


def _short(session_id) -> str:
    return str(session_id)[:8]


def _kind(kind: str) -> str:
    return {'monte_carlo': 'Monte Carlo run', 'significance_test': 'significance test'}.get(kind, kind)


def version_problem(my_name: str, my_version: str, hubs: list) -> Optional[str]:
    """A message when an online hub runs another Jesse version than this runner, else None."""
    for hub in hubs:
        if hub['name'] != my_name and hub['jesse_version'] != my_version:
            return (f'This runner runs Jesse {my_version}, but the hub "{hub["name"]}" runs Jesse '
                    f'{hub["jesse_version"]}. Runners only take jobs from the same version: install Jesse '
                    f'{hub["jesse_version"]} here (pip install jesse=={hub["jesse_version"]}), or upgrade the hub, '
                    'then start the runner again.')
    return None


def runner_banner(name: str, budget: int, cores: int, version: str, database: str, hubs: list,
                  inside_server: bool) -> list:
    lines = [
        f'Research runner "{name}": uses {budget} of its {cores} CPU cores for jobs, Jesse {version}.',
        f'Takes research jobs from the database at {database}'
        + (' (alongside this Jesse\'s own dashboard).' if inside_server else '.'),
    ]
    online = [hub for hub in hubs if hub['alive']]
    if online:
        hub = online[0]
        lines.append(f'Hub "{hub["name"]}" is online (Jesse {hub["jesse_version"]}).')
    else:
        lines.append('The hub is not online yet; jobs start once it queues them.')
    return lines


def hub_banner(name: str, budget: int, order: Optional[str], version: str, runners: list) -> list:
    own = f'runs jobs itself on {budget} core(s)' if budget else 'only dispatches jobs (RUNNER_CORES=0)'
    lines = [f'Research hub "{name}": Jesse {version}, {own}, order: {order or "any free runner"}.']
    others = [runner for runner in runners if runner['name'] != name]
    if not others:
        lines.append('No runners have connected yet. Start `jesse runner` on another machine to add one.')
        return lines
    lines.append('Runners:')
    for runner in others:
        state = 'online' if runner['alive'] else f'offline (last seen {_ago(runner["last_seen_seconds_ago"])})'
        version_note = '' if runner['compatible'] else f', Jesse {runner["jesse_version"]}: VERSION MISMATCH'
        lines.append(f'  - {runner["name"]}: {state}, {runner["cores_budget"]} of {runner["cpu_cores"]} cores for jobs'
                     f'{version_note}')
    return lines


def _ago(seconds: Optional[float]) -> str:
    if seconds is None:
        return 'never'
    if seconds < 120:
        return f'{seconds:.0f}s ago'
    if seconds < 7200:
        return f'{seconds / 60:.0f} min ago'
    if seconds < 2 * 86400:
        return f'{seconds / 3600:.0f} h ago'
    if seconds < 30 * 86400:
        return f'{seconds / 86400:.0f} days ago'
    return 'over a month ago'


class ClusterWatcher:
    """
    Turns successive snapshots of the runners and jobs into one-line events for the hub's terminal.
    The first snapshot only sets the baseline (the banner already showed it).
    """

    def __init__(self, me: str, hub_version: str):
        self.me = me
        self.hub_version = hub_version
        self.runners: Optional[dict] = None
        self.jobs: dict = {}
        self.warned_versions: set = set()

    def update(self, runners: list, jobs: list, titles: Optional[dict] = None) -> list:
        """`runners`: rows of runners_payload(); `jobs`: dicts with id, session_id, kind, status,
        claimed_by, attempt, error, target. Returns [(level, text)]."""
        titles = titles or {}
        events = []
        baseline = self.runners is None
        current = {runner['name']: runner for runner in runners if runner['name'] != self.me}
        if self.runners is not None:
            for name, runner in current.items():
                before = self.runners.get(name)
                if runner['alive'] and (before is None or not before['alive']):
                    events.append(('good', f'Runner "{name}" connected: {runner["cores_budget"]} of '
                                           f'{runner["cpu_cores"]} cores for jobs, Jesse {runner["jesse_version"]}.'))
                elif before is not None and before['alive'] and not runner['alive']:
                    events.append(('warn', f'Runner "{name}" went offline.'))
        for name, runner in current.items():
            key = (name, runner['jesse_version'])
            if runner['jesse_version'] == self.hub_version or key in self.warned_versions:
                continue
            before = (self.runners or {}).get(name)
            if runner['alive']:
                self.warned_versions.add(key)
                events.append(('error', f'Runner "{name}" runs Jesse {runner["jesse_version"]}, this hub runs '
                                        f'{self.hub_version}: it takes no jobs until both run the same version.'))
            elif not baseline and (before is None or before['jesse_version'] != runner['jesse_version']):
                # It came and went between two checks: a standalone runner exits on a mismatch.
                self.warned_versions.add(key)
                events.append(('error', f'Runner "{name}" tried to start with Jesse {runner["jesse_version"]} and '
                                        f'stopped: this hub runs {self.hub_version}.'))
        self.runners = current

        snapshot = {job['id']: job for job in jobs}
        if baseline:
            self.jobs = {job_id: job for job_id, job in snapshot.items() if job['status'] not in _ENDED_JOB}
            return events
        for job_id, job in snapshot.items():
            before = self.jobs.get(job_id)
            label = f'{_kind(job["kind"])} {_short(job["session_id"])}'
            if job['session_id'] in titles and titles[job['session_id']]:
                label += f' "{titles[job["session_id"]]}"'
            if before is None:
                if job['status'] in _ENDED_JOB:
                    continue  # ended before this hub saw it waiting (or reported already)
                where = f'runner "{job["target"]}"' if job.get('target') else 'any runner'
                events.append(('info', f'Queued {label} for {where}.'))
                if job['status'] == 'queued':
                    continue
                before = dict(job, status='queued', claimed_by=None)
            if before['status'] == job['status'] and before.get('claimed_by') == job.get('claimed_by'):
                continue
            if job['status'] == 'running':
                attempt = f' (attempt {job["attempt"]})' if job.get('attempt', 1) > 1 else ''
                events.append(('info', f'"{job["claimed_by"]}" took {label}{attempt}.'))
            elif job['status'] == 'queued' and before['status'] == 'running':
                events.append(('warn', f'{label} went back to the queue: {job.get("error") or "its runner let it go."}'))
            elif job['status'] == 'done':
                events.append(('good', f'{label} finished on "{job.get("claimed_by")}".'))
            elif job['status'] == 'failed':
                events.append(('error', f'{label} failed: {job.get("error") or "see its session for the error."}'))
            elif job['status'] == 'cancelled':
                events.append(('warn', f'{label} was cancelled.'))
        self.jobs = {job_id: job for job_id, job in snapshot.items() if job['status'] not in _ENDED_JOB}
        return events
