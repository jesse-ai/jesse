from typing import Callable

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from jesse.services import project_files
from jesse.services.auth import require_auth
from jesse.services.web import (
    DeleteProjectPathRequestJson,
    ListProjectFilesRequestJson,
    ProjectPathRequestJson,
    ReadProjectFileRequestJson,
    TransferProjectPathRequestJson,
    WriteProjectFileRequestJson,
)

# File access for MCP assistants, limited to strategies/ and research_scripts/ in the project.
# See jesse.services.project_files for the confinement rules.
router = APIRouter(prefix="/project-files", tags=["Project Files"], dependencies=[Depends(require_auth)])


def respond(operation: Callable[..., dict], *args) -> JSONResponse:
    """Run a project file operation and return its result or its stable error type."""
    try:
        result = operation(*args)
    except project_files.ProjectFileError as e:
        return JSONResponse(
            {'status': 'error', 'error_type': e.error_type, 'message': e.message},
            status_code=e.status_code,
        )
    return JSONResponse({'status': 'success', **result})


@router.post("/list")
def list_project_files(json_request: ListProjectFilesRequestJson) -> JSONResponse:
    return respond(project_files.list_files, json_request.path, json_request.recursive, json_request.max_entries)


@router.post("/read")
def read_project_file(json_request: ReadProjectFileRequestJson) -> JSONResponse:
    return respond(project_files.read_text_file, json_request.path, json_request.start_line, json_request.max_lines)


@router.post("/write")
def write_project_file(json_request: WriteProjectFileRequestJson) -> JSONResponse:
    return respond(project_files.write_text_file, json_request.path, json_request.content, json_request.overwrite)


@router.post("/mkdir")
def create_project_directory(json_request: ProjectPathRequestJson) -> JSONResponse:
    return respond(project_files.make_directory, json_request.path)


@router.post("/move")
def move_project_path(json_request: TransferProjectPathRequestJson) -> JSONResponse:
    return respond(project_files.move_path, json_request.source, json_request.destination, json_request.overwrite)


@router.post("/copy")
def copy_project_path(json_request: TransferProjectPathRequestJson) -> JSONResponse:
    return respond(project_files.copy_path, json_request.source, json_request.destination, json_request.overwrite)


@router.post("/delete")
def delete_project_path(json_request: DeleteProjectPathRequestJson) -> JSONResponse:
    return respond(project_files.delete_path, json_request.path, json_request.recursive)
