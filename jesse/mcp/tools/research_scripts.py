"""
Jesse Research Script Tools

MCP tools that run Python scripts from the project's research_scripts/ folder in the
background on the machine running Jesse:
- run_research_script: start a script and return a job ID immediately
- get_research_job_status: one job's status, or the newest jobs
- get_research_job_output: the end of a job's combined stdout/stderr
- cancel_research_job: stop a job and every process it started

Scripts are opt-in (see jesse://research_scripts) and are NOT sandboxed.

The tools are async and run their API call in a worker thread (see offload.py), so waiting
up to ~12 seconds for a cancelled job to stop does not stall other MCP requests.
"""
from typing import List, Optional

from .offload import run_blocking
from .services import (
    cancel_research_job_service,
    get_research_job_output_service,
    get_research_job_status_service,
    run_research_script_service,
)


def register_research_scripts_tools(mcp):
    """
    Register the research script tools.

    Args:
        mcp: The MCP server instance.
    """

    @mcp.tool()
    async def run_research_script(path: str, args: Optional[List[str]] = None, timeout_minutes: int = 60) -> dict:
        """
        Run a Python script from research_scripts/ in the background on the machine running Jesse.

        ONLY use this when the user specifically asked for a script, asked for
        machine-learning research that needs a script or Jesse's research module (for
        example gathering ML data and training a model), or explicitly asked to use the
        research module. A generic request to research, find, test, compare, or improve
        strategies is NOT such a request and is never consent to write or run scripts: use
        the strategy catalog, backtest, optimization, Monte Carlo, and significance-test
        tools instead, and ask the user before switching to a script.

        Jesse runs `python <path> <args...>` with its own Python interpreter, from the
        project root (so `from jesse import research`, `.env`, and `strategies/` work as in
        a notebook), without a shell: each list item is passed to the script as one
        argument, with no quoting, globbing, or command substitution.

        The script is NOT sandboxed. It runs as the same user, with the same environment
        variables, files, database, network, and saved exchange keys as Jesse, so it can do
        anything Jesse can. The project file tools' folder restrictions do not apply to the
        code it runs. Never run a script you have not read, and never write scripts that read
        secrets, place orders, or reach live exchange accounts.

        Parameters:
            path (str): A .py file inside research_scripts/, e.g. "research_scripts/ml/train.py".
            args (list[str]): Optional arguments, at most 64, each up to 4096 characters.
            timeout_minutes (int): 1-720, default 60. The job and every process it started
                are stopped at the deadline (status "timed_out").

        Returns:
            dict: {"status": "success", "job": {"id", "script", "args", "status": "running",
            "pid", "started_at", "timeout_minutes", "log_path"}} or an error with error_type
            "too_many_jobs" (at most 2 run at once), "not_found", "invalid_path" (not a .py
            file in research_scripts/), "unsafe_path" (symlink), or "invalid_request".

        Next: poll get_research_job_status(job_id) and read get_research_job_output(job_id).
        Jobs keep running if the chat ends; cancel ones you no longer need.
        """
        return await run_blocking(run_research_script_service, path, args, timeout_minutes)

    @mcp.tool()
    async def get_research_job_status(job_id: str = "") -> dict:
        """
        Return a research job's status, or the 20 newest jobs when job_id is empty.

        status values: "running", "succeeded" (exit code 0), "failed" (non-zero exit code or
        a Python exception; read the output), "cancelled", "timed_out", and "interrupted"
        (Jesse stopped or restarted while it ran).

        Returns:
            dict: {"status": "success", "job": {"id", "script", "args", "status", "pid",
            "exit_code", "started_at", "finished_at", "timeout_minutes", "output_truncated",
            "log_path"}} or {"status": "success", "jobs": [...]}, or an error with error_type
            "not_found" or "invalid_request".
        """
        return await run_blocking(get_research_job_status_service, job_id)

    @mcp.tool()
    async def get_research_job_output(job_id: str, tail_lines: int = 200) -> dict:
        """
        Return the last lines of a research job's combined stdout and stderr.

        Works while the job runs and after it ends. Returns at most `tail_lines` lines (1-2000)
        from the last 256 KiB. Jesse keeps up to 20 MiB of output per job; later output is
        discarded and "output_truncated" is true.

        Returns:
            dict: {"status": "success", "job_id", "job_status", "output", "lines_returned",
            "output_size_bytes", "earlier_output_omitted", "output_truncated"} or an error
            with error_type "not_found" or "invalid_request".
        """
        return await run_blocking(get_research_job_output_service, job_id, tail_lines)

    @mcp.tool()
    async def cancel_research_job(job_id: str) -> dict:
        """
        Stop a running research job and every process it started.

        Sends SIGTERM to the job's process group and SIGKILL 5 seconds later if needed,
        waiting up to about 12 seconds for the final status.

        Returns:
            dict: {"status": "success", "job": {...}, "cancel_requested", "message"} or an
            error with error_type "not_found" or "invalid_request".
        """
        return await run_blocking(cancel_research_job_service, job_id)
