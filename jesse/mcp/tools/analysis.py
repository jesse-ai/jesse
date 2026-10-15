"""
Jesse Temporary Analysis Tools

Run assistant-written Python over snapshots of stored sessions on the machine running
Jesse, and fetch the charts and tables it produces:
- run_analysis: snapshot sessions into a new workspace and start the code
- get_analysis_job: status, artifacts, and console output (or the newest jobs)
- get_analysis_artifact: one artifact; images come back as MCP image content
- cancel_analysis_job, delete_analysis_job

Workspaces are temporary (storage/mcp/analysis/<job_id>/) and separate from
research_scripts/. The code is NOT sandboxed. Details: jesse://session_analysis.

The tools are async and run their API call in a worker thread (see offload.py), so a
snapshot or cleanup taking minutes does not stall other MCP requests on this worker.
"""
import json
from typing import Any, Dict, List, Optional

from mcp.types import CallToolResult, ImageContent, TextContent

from .offload import run_blocking
from .services import (
    cancel_analysis_job_service,
    delete_analysis_job_service,
    get_analysis_artifact_service,
    get_analysis_job_service,
    run_analysis_service,
)


def _text(payload: dict) -> TextContent:
    return TextContent(type='text', text=json.dumps(payload, indent=2, default=str))


def artifact_result(result: dict) -> CallToolResult:
    """
    Convert an artifact response into MCP content: images become ImageContent (with a short
    text part carrying their metadata), text and binary files a JSON text part, and errors a
    tool error.
    """
    if result.get('status') != 'success':
        return CallToolResult(content=[_text(result)], isError=True)
    if result.get('kind') == 'image':
        data = result.pop('data_base64')
        return CallToolResult(content=[
            _text(result),
            ImageContent(type='image', data=data, mimeType=result['mime_type']),
        ])
    return CallToolResult(content=[_text(result)])


def register_analysis_tools(mcp):
    """
    Register the temporary analysis tools.

    Args:
        mcp: The MCP server instance.
    """

    @mcp.tool()
    async def run_analysis(code: str, inputs: Optional[List[Dict[str, Any]]] = None, timeout_minutes: int = 5) -> dict:
        """
        Run Python that analyzes stored session results, in a temporary workspace on the
        machine running Jesse, and return a job ID immediately.

        Use it when the user asks to analyze, compare, or chart session results (backtests,
        optimizations, Monte Carlo, significance tests, live/paper sessions) or their live/paper
        trades or orders over a period (e.g. "analyze my trades of the last 7 days"). That request
        authorizes this temporary analysis only: it is NOT a request for a research script,
        so never create or edit files in research_scripts/ for it. Do not start backtests or
        other runs from analysis code; use the run tools for new results.

        Jesse first writes each requested input's complete data to inputs/<name>.json (plus
        inputs/manifest.json), then runs your code as analysis.py
        with the workspace as the working directory, using Jesse's Python and packages
        (numpy, pandas, matplotlib with the Agg backend). Read inputs with
        json.load(open("inputs/<name>.json")); save charts and tables under output/, e.g.
        plt.savefig("output/equity.png", dpi=110). Print short results; they appear in the
        job output. Keep images under 3 MiB and 8000 px per side. Snapshot layouts per
        session type and dataset are in jesse://session_analysis.

        The code is NOT sandboxed: it runs as the Jesse user with Jesse's files, database,
        credentials, and network. Only read the input snapshots and write to output/; never
        read .env or credentials, place orders, or contact exchanges.

        Parameters:
            code (str): Complete Python source, at most 256 KiB.
            inputs (list[dict], optional): Up to 10, each either
                - a session: {"session_type", "session_id", "name"}, session_type
                  "backtest", "optimization", "monte_carlo", "significance_test", or "live";
                  name defaults to "<session_type>_<first 8 id characters>"; or
                - live/paper history across sessions: {"dataset": "live_trades" or
                  "live_orders", "name", plus the window and filters of get_live_trades /
                  get_live_orders: "recent_days" or "start"/"end", "mode" (default "live"),
                  "exchange", "symbol", "session_id", and for orders "time_field",
                  "status"}; name defaults to the dataset. The snapshot holds EVERY matching
                  record (oldest first), read from one consistent database view per input,
                  or the run is refused ("too_many_records": over 100,000 records;
                  "too_many_orders": a trade with over 10,000 executed orders; narrow the
                  window); it is never cut.
                  Unknown fields are refused. The window is resolved once and the
                  manifest records its exact range, filters, and count.
                Names use letters, digits, "_", "-". Snapshots are capped at 64 MiB each and
                256 MiB together. Every snapshot is complete or the run is refused: a live
                session with more than 100,000 trades, 200,000 orders, or 600,000 equity
                points is refused with "too_many_records" (use dataset inputs by date).
            timeout_minutes (int): 1-30, default 5.

        Returns:
            dict: {"status": "success", "job": {"id", "status": "running", "inputs":
            [{"name", "file", "session_type", "session_id", "session_status", "title",
            "size_bytes"} or {"name", "file", "dataset", "range", "filters", "count",
            "size_bytes"}], "workspace", "lifetime", ...}} or an error with error_type
            "not_found" (a session), "too_many_jobs" (2 at once), "too_large",
            "too_many_records", "too_many_orders", "mode_mismatch", "read_failed",
            "live_plugin_unavailable", or
            "invalid_request".

        Next: poll get_analysis_job(job_id) until the status is not "running", then fetch
        charts with get_analysis_artifact. Fetch what you need soon: once 24 hours have
        passed since the job finished (its expires_at), the next run_analysis deletes the
        workspace, and it can go earlier when more than 50 finished jobs or 2 GiB are kept.
        """
        return await run_blocking(run_analysis_service, code, inputs, timeout_minutes)

    @mcp.tool()
    async def get_analysis_job(job_id: str = "", tail_lines: int = 50) -> dict:
        """
        Return an analysis job's status, its artifacts, and the end of its console output,
        or the 20 newest jobs when job_id is empty.

        status values: "running", "succeeded", "failed" (read the output's traceback, fix
        the code, and run again), "cancelled", "timed_out", "interrupted" (Jesse stopped).

        Parameters:
            job_id (str): From run_analysis.
            tail_lines (int): 1-2000 lines of stdout/stderr, default 50.

        Returns:
            dict: {"status": "success", "job": {..., "expires_at" (earliest deletion time;
            null while running), "lifetime"}, "artifacts": [{"path",
            "kind": "image|text|binary|symlink|other", "mime_type", "size_bytes"}],
            "output", "earlier_output_omitted", "output_truncated"}, or {"jobs": [...]}, or
            an error with error_type "not_found" (unknown or already cleaned up).
        """
        return await run_blocking(get_analysis_job_service, job_id, tail_lines)

    @mcp.tool()
    async def get_analysis_artifact(job_id: str, path: str) -> CallToolResult:
        """
        Return one file from an analysis job's output folder. PNG, JPEG, GIF, and WebP images
        are returned as image content you can see, with a text part giving path, size, and
        dimensions. Text files (CSV, JSON, Markdown) return their text (up to 128K
        characters). Other files return metadata only. Files stay on the Jesse host.

        Parameters:
            job_id (str): From run_analysis.
            path (str): Path inside output/, e.g. "equity.png" or "charts/drawdown.png"
                (a leading "output/" is accepted). Symlinks and paths outside output/ are
                refused.

        Errors (returned as a tool error with error_type): "not_found", "invalid_path",
        "unsafe_path" (symlink), "artifact_too_large" (over 3 MiB or 8000 px), "invalid_image".
        """
        return artifact_result(await run_blocking(get_analysis_artifact_service, job_id, path))

    @mcp.tool()
    async def cancel_analysis_job(job_id: str) -> dict:
        """
        Stop a running analysis job and every process it started (SIGTERM, then SIGKILL after
        5 seconds). Its workspace stays until cleanup removes it after it expires, or you
        delete it.

        Returns:
            dict: {"status": "success", "job", "cancel_requested", "message"} or an error.
        """
        return await run_blocking(cancel_analysis_job_service, job_id)

    @mcp.tool()
    async def delete_analysis_job(job_id: str) -> dict:
        """
        Delete a finished analysis job's workspace (snapshots, code, output) now instead of
        waiting for it to expire. Running jobs must be cancelled first ("job_running").

        Returns:
            dict: {"status": "success", "job_id", "deleted": true} or an error.
        """
        return await run_blocking(delete_analysis_job_service, job_id)
