"""
The worker process of a runner job (see services/runner.py).

It runs in the job's own folder, which holds the job's code (strategies/ and project modules from
its bundle) and an empty storage/. Python, Ray workers and Jesse's relative paths therefore all
use the job's code, never the runner project's strategies/ folder, and the files the run writes
(logs, charts) land in the job folder, from where the runner sends them to the hub.
"""

import json
import os
import sys


def _mode_function(function: str):
    if function == 'backtest':
        from jesse.modes.backtest_mode import run
    elif function == 'optimization':
        from jesse.modes.optimize_mode import run
    elif function == 'monte_carlo':
        from jesse.modes.monte_carlo_mode import run
    elif function == 'significance_test':
        from jesse.modes.significance_test_mode import run
    else:
        raise ValueError(f'Unknown runner function: {function}')
    return run


def _forget_project_modules(job_dir: str) -> None:
    """Drop modules a forked worker inherited from the runner's own project (same names as the job's)."""
    tops = {'strategies'} | {name.split('.')[0] for name in os.listdir(job_dir) if not name.startswith('.')}
    tops.discard('storage')
    for name in list(sys.modules):
        if name.split('.')[0] in tops:
            del sys.modules[name]


# Position of the cpu_cores argument of the modes that use several cores.
_CPU_CORES_ARGUMENT = {'optimization': 11, 'monte_carlo': 11}


def _fit_cpu_cores(function: str, arguments: list) -> None:
    """The hub chose cpu_cores for its own machine; use at most the cores this runner has."""
    from multiprocessing import cpu_count

    position = _CPU_CORES_ARGUMENT.get(function)
    available = max(1, cpu_count())
    if position is not None and isinstance(arguments[position], int) and arguments[position] > available:
        arguments[position] = available
    config = arguments[1] if isinstance(arguments[1], dict) else None
    if config is not None and isinstance(config.get('cpu_cores'), int) and config['cpu_cores'] > available:
        config['cpu_cores'] = available


def run_queued_job(session_id: str, function: str, arguments_json: str, job_dir: str, claim_id: str) -> None:
    from jesse.services import session_liveness

    os.chdir(job_dir)
    _forget_project_modules(job_dir)
    sys.path.insert(0, job_dir)
    # Ray and multiprocessing workers this run starts find the job's code too.
    os.environ['PYTHONPATH'] = os.pathsep.join(filter(None, [job_dir, os.environ.get('PYTHONPATH')]))
    session_liveness.set_claim(claim_id)

    arguments = json.loads(arguments_json)
    if str(arguments[0]) != str(session_id):
        raise ValueError('The job arguments do not belong to this session.')
    _fit_cpu_cores(function, arguments)
    _mode_function(function)(*arguments)
