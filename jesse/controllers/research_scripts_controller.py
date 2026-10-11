from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from jesse.controllers.project_files_controller import respond
from jesse.services import research_jobs
from jesse.services.auth import require_auth
from jesse.services.web import (
    ResearchJobOutputRequestJson,
    ResearchJobRequestJson,
    RunResearchScriptRequestJson,
)

# Background runs of Python scripts from research_scripts/. The scripts are not sandboxed;
# see jesse.services.research_jobs.
router = APIRouter(prefix="/research-scripts", tags=["Research Scripts"], dependencies=[Depends(require_auth)])


@router.post("/run")
def run_research_script(json_request: RunResearchScriptRequestJson) -> JSONResponse:
    return respond(
        lambda: {'job': research_jobs.start_job(json_request.path, json_request.args, json_request.timeout_minutes)}
    )


@router.post("/jobs")
def get_research_jobs(json_request: ResearchJobRequestJson) -> JSONResponse:
    """One job's record when job_id is given, otherwise the newest records."""
    if json_request.job_id:
        return respond(lambda: {'job': research_jobs.get_job(json_request.job_id)})
    return respond(lambda: {'jobs': research_jobs.list_jobs()})


@router.post("/output")
def get_research_job_output(json_request: ResearchJobOutputRequestJson) -> JSONResponse:
    return respond(research_jobs.read_output, json_request.job_id, json_request.tail_lines)


@router.post("/cancel")
def cancel_research_job(json_request: ResearchJobRequestJson) -> JSONResponse:
    return respond(research_jobs.cancel_job, json_request.job_id)
