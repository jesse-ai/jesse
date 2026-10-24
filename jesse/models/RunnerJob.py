"""
Tables of the research runners feature (see services/runner_queue.py): queued research jobs, the
runners that take them, the code files jobs carry, and the files runners send back.

All of them live in the database the machines share. They stay empty unless a hub turns the
feature on (RESEARCH_RUNNERS=true) and runners connect.
"""
import peewee

from jesse.services.db import database


class RunnerJob(peewee.Model):
    """One queued run of a research session (backtest, optimization, Monte Carlo, significance test)."""
    id = peewee.UUIDField(primary_key=True)
    session_id = peewee.UUIDField(index=True)
    kind = peewee.CharField(max_length=32)
    # queued -> running -> done | cancelled | failed
    status = peewee.CharField(max_length=16, index=True)
    # The worker call to make on the runner: which mode and its arguments (JSON).
    function = peewee.CharField(max_length=32)
    arguments = peewee.TextField()
    # {"strategies/Name/__init__.py": "<sha256>", ...}: the code the job runs, in CodeBlob.
    code_manifest = peewee.TextField()
    # Third-party packages the code imports; a runner without them does not take the job.
    packages = peewee.TextField(null=True)
    # A runner name, or null for any runner.
    target = peewee.CharField(max_length=255, null=True)
    # The hub's RUNNER_ORDER when it was queued ("macmini,macbook", "macmini,*"), or null for any.
    placement = peewee.TextField(null=True)
    jesse_version = peewee.CharField(max_length=32)
    claim_id = peewee.CharField(max_length=36, null=True)
    claimed_by = peewee.CharField(max_length=255, null=True)
    attempt = peewee.IntegerField(default=0)
    max_attempts = peewee.IntegerField(default=3)
    # ",runner-a,runner-b," : runners that cannot take it (a missing package).
    excluded = peewee.TextField(null=True)
    error = peewee.TextField(null=True)
    queued_at = peewee.BigIntegerField()
    claimed_at = peewee.BigIntegerField(null=True)
    finished_at = peewee.BigIntegerField(null=True)

    class Meta:
        database = database.db
        indexes = ((('status', 'queued_at'), False),)


class Runner(peewee.Model):
    """A machine that takes queued jobs. It keeps its own row fresh while it runs."""
    name = peewee.CharField(max_length=255, primary_key=True)
    host = peewee.CharField(max_length=255)
    # "hub" for the machine with RESEARCH_RUNNERS=true, else "runner".
    role = peewee.CharField(max_length=16, default='runner')
    slots = peewee.IntegerField()
    busy = peewee.IntegerField(default=0)
    cpu_cores = peewee.IntegerField()
    jesse_version = peewee.CharField(max_length=32)
    started_at = peewee.BigIntegerField()
    last_seen = peewee.BigIntegerField()
    # How busy the machine is (services/machine_stats.py), refreshed with last_seen.
    cpu_percent = peewee.FloatField(null=True)
    load_1m = peewee.FloatField(null=True)
    memory_total_bytes = peewee.BigIntegerField(null=True)
    memory_used_bytes = peewee.BigIntegerField(null=True)

    class Meta:
        database = database.db


class CodeBlob(peewee.Model):
    """One code or data file a job carries, stored once by the SHA-256 of its content."""
    hash = peewee.CharField(max_length=64, primary_key=True)
    content = peewee.BlobField()
    size = peewee.IntegerField()
    created_at = peewee.BigIntegerField()
    last_used_at = peewee.BigIntegerField()

    class Meta:
        database = database.db


class RunnerFile(peewee.Model):
    """A file a job wrote on its runner (a log, a chart), waiting for the hub to save it locally."""
    id = peewee.UUIDField(primary_key=True)
    session_id = peewee.UUIDField(index=True)
    path = peewee.CharField(max_length=1024)
    content = peewee.BlobField()
    created_at = peewee.BigIntegerField()

    class Meta:
        database = database.db


if database.is_open():
    database.db.create_tables([RunnerJob, Runner, CodeBlob, RunnerFile], safe=True)
