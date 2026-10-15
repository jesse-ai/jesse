from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from jesse.controllers.project_files_controller import respond
from jesse.controllers.session_results_controller import respond_reading
from jesse.services import analysis_jobs
from jesse.services.auth import require_auth
from jesse.services.web import AnalysisArtifactRequestJson, AnalysisJobRequestJson, RunAnalysisRequestJson

# Temporary analysis jobs over stored session results, in storage/mcp/analysis/<job_id>/.
# The code is not sandboxed; see jesse.services.analysis_jobs.
router = APIRouter(prefix="/analysis", tags=["Analysis"], dependencies=[Depends(require_auth)])


@router.post("/run")
def run_analysis(json_request: RunAnalysisRequestJson) -> JSONResponse:
    inputs = [item.model_dump() for item in json_request.inputs]
    # Snapshots read sessions from the database, so report read failures like the results routes.
    return respond_reading(lambda: {'job': analysis_jobs.start_analysis(json_request.code, inputs, json_request.timeout_minutes)})


@router.post("/jobs")
def get_analysis_jobs(json_request: AnalysisJobRequestJson) -> JSONResponse:
    """One job with its artifacts and output tail when job_id is given, otherwise the newest jobs."""
    if json_request.job_id:
        return respond(analysis_jobs.get_job, json_request.job_id, json_request.tail_lines)
    return respond(lambda: {'jobs': analysis_jobs.list_jobs()})


@router.post("/cancel")
def cancel_analysis_job(json_request: AnalysisJobRequestJson) -> JSONResponse:
    return respond(analysis_jobs.cancel_job, json_request.job_id)


@router.post("/delete")
def delete_analysis_job(json_request: AnalysisJobRequestJson) -> JSONResponse:
    return respond(analysis_jobs.delete_job, json_request.job_id)


@router.post("/artifact")
def get_analysis_artifact(json_request: AnalysisArtifactRequestJson) -> JSONResponse:
    return respond(analysis_jobs.read_artifact, json_request.job_id, json_request.path)
