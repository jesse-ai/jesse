import os
import re
import shutil
import stat
from uuid import uuid4
from starlette.responses import JSONResponse

from jesse.services.nofollow_fs import component_problem, extended_path

# Strategy folder names are class names, and imports from jesse.trade are sanitized to this
# same set. Rejecting everything else (path separators, dots) keeps the report path inside
# strategies/ (symlinked strategy folders are still followed; see save_report).
_REPORT_STRATEGY_NAME = re.compile(r'[A-Za-z0-9_-]+')
# A bare Markdown file name: without separators it cannot leave the reports folder, and
# without a leading dot it can never be a hidden file or one of save_report's temporary files.
_REPORT_FILENAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]*\.md')
# Keeps the temporary name used when overwriting (file name plus 38 characters) under the
# 255-byte file name limit of common filesystems.
_MAX_REPORT_FILENAME_LENGTH = 200


def generate(name: str) -> JSONResponse:
    path = f'strategies/{name}'

    # validation for name duplication
    exists = os.path.isdir(path)
    if exists:
        return JSONResponse({
            'status': 'error',
            'message': f'Strategy "{name}" already exists.'
        }, status_code=409)

    # generate from ExampleStrategy
    dirname, filename = os.path.split(os.path.abspath(__file__))

    shutil.copytree(f'{dirname}/ExampleStrategy', path)

    # replace 'ExampleStrategy' with the name of the new strategy
    with open(f"{path}/__init__.py", "rt") as fin:
        data = fin.read()
        data = data.replace('ExampleStrategy', name)
    with open(f"{path}/__init__.py", "wt") as fin:
        fin.write(data)
        
    # create the reports folder inside the startegy folder
    os.makedirs(f"{path}/reports", exist_ok=True)
        
    # return the location of generated strategy directory
    return JSONResponse({
        'status': 'success',
        'message': path
    })


def get_strategies() -> JSONResponse:
    path = 'strategies'
    directories = []

    # Iterate through the items in the specified path
    for item in os.listdir(path):
        # Construct full path
        full_path = os.path.join(path, item)
        # Check if the item is a directory
        if os.path.isdir(full_path):
            directories.append(item)

    return JSONResponse({
        'status': 'success',
        'strategies': directories
    })


def get_strategy(name: str) -> JSONResponse:
    path = f'strategies/{name}'
    exists = os.path.isdir(path)

    if not exists:
        return JSONResponse({
            'status': 'error',
            'message': f'Strategy "{name}" does not exist.'
        }, status_code=404)

    with open(f"{path}/__init__.py", "rt") as fin:
        content = fin.read()

    return JSONResponse({
        'status': 'success',
        'content': content
    })


def save_strategy(name: str, content: str) -> JSONResponse:
    path = f'strategies/{name}'
    exists = os.path.isdir(path)

    if not exists:
        return JSONResponse({
            'status': 'error',
            'message': f'Strategy "{name}" does not exist.'
        }, status_code=404)

    with open(f"{path}/__init__.py", "wt") as fin:
        fin.write(content)

    return JSONResponse({
        'status': 'success',
        'message': f'Strategy "{name}" has been saved.'
    })


def _report_error(message: str, status_code: int) -> JSONResponse:
    return JSONResponse({'status': 'error', 'message': message}, status_code=status_code)


def _is_link(path: str) -> bool:
    """
    True for a symbolic link, and on Windows also a junction or other reparse point: os.path.islink
    does not report junctions there, so the reparse attribute is checked as well.
    """
    if os.path.islink(path):
        return True
    if os.name != 'nt':
        return False
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return False
    return bool(getattr(st, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _write_new_file(path: str, content: str) -> None:
    """Create `path` holding `content`, raising FileExistsError if anything is already there."""
    # O_EXCL checks and creates in one step and refuses existing symlinks, so the write can
    # neither follow a link nor clobber a file that appeared after the caller's checks.
    # 0o666 is the mode open() uses; the process umask still applies.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
    try:
        # newline='' stores the text exactly as sent instead of translating line endings.
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as f:
            f.write(content)
    except BaseException:
        os.unlink(path)
        raise


def save_report(name: str, filename: str, content: str, overwrite: bool = False) -> JSONResponse:
    """
    Save a Markdown report as strategies/<name>/reports/<filename> on the Jesse host.

    MCP assistants may run on another machine, so this is how their reports reach the
    project. It only accepts a bare `.md` name inside an existing strategy's reports folder,
    which it creates on first use, so it can never touch strategy code or other files. An
    existing report is replaced only when `overwrite` is true. A symlinked `strategies` or
    strategy folder is followed, as it is when Jesse lists, edits and loads strategies, so the
    report then lands wherever that link points. A symlinked reports folder or report file is
    refused so the write cannot land outside the strategy folder. These checks run before the
    write, so they guard against misconfiguration rather than against a local process that
    swaps in a symlink concurrently.
    """
    if not _REPORT_STRATEGY_NAME.fullmatch(name):
        return _report_error(f'Invalid strategy name "{name}".', 400)
    # Extended paths can create literal device aliases (e.g. CON.md) that ordinary Win32 readers
    # interpret differently, so reports use the same Windows component rules as project files.
    if (len(filename) > _MAX_REPORT_FILENAME_LENGTH or not _REPORT_FILENAME.fullmatch(filename)
            or (os.name == 'nt' and component_problem(filename) is not None)):
        return _report_error(
            f'Invalid report file name "{filename}". Use a bare file name (no folders) of at most '
            f'{_MAX_REPORT_FILENAME_LENGTH} characters that uses only letters, digits, ".", "_" and "-", '
            'starts with a letter or digit, and ends in ".md", for example '
            '"BTCUSDT_sharpe_optimization_report.md".',
            400,
        )
    if not content.strip():
        return _report_error('Report content is empty.', 400)

    strategy_path = f'strategies/{name}'
    if not os.path.isdir(extended_path(strategy_path)):
        return _report_error(f'Strategy "{name}" does not exist.', 404)

    # The API reports relative paths. The file operations use extended_path, because the
    # temporary name used for an overwrite can push the full path past Windows' 260-character limit.
    # Links in the path are followed as before: a symlinked strategies or strategy folder is allowed.
    reports_path = f'{strategy_path}/reports'
    report_path = f'{reports_path}/{filename}'
    long_reports, long_report = extended_path(reports_path), extended_path(report_path)
    if _is_link(long_reports) or (os.path.lexists(long_reports) and not os.path.isdir(long_reports)):
        return _report_error(
            f'{reports_path} is a symlink or not a folder, so Jesse will not write reports into it.', 403
        )
    if _is_link(long_report) or (os.path.lexists(long_report) and not os.path.isfile(long_report)):
        return _report_error(
            f'{report_path} is a symlink or not a regular file, so Jesse will not replace it.', 403
        )

    exists_message = f'Report {report_path} already exists. Pass overwrite=true to replace it, or use a new file name.'
    existed = os.path.lexists(long_report)
    if existed and not overwrite:
        return _report_error(exists_message, 409)

    try:
        try:
            # mkdir rather than makedirs: a strategy deleted since the check above must not be
            # recreated as an empty folder just to hold its report.
            os.mkdir(long_reports)
        except FileExistsError:
            # Already there; anything other than a folder makes the write below fail.
            pass
        if overwrite:
            # Writing a temporary file first keeps the previous report intact if the save is
            # interrupted, and os.replace swaps the folder entry rather than following a symlink.
            temp_path = f'{reports_path}/.{filename}.{uuid4().hex}.tmp'
            long_temp = extended_path(temp_path)
            _write_new_file(long_temp, content)
            try:
                os.replace(long_temp, long_report)
            except BaseException:
                os.unlink(long_temp)
                raise
        else:
            _write_new_file(long_report, content)
    except FileExistsError:
        # Another save created the report between the checks above and the exclusive create.
        return _report_error(exists_message, 409)
    except OSError as e:
        return _report_error(f'Could not save report {report_path}: {e.strerror or e}', 500)

    return JSONResponse({
        'status': 'success',
        'message': f'Report saved to {report_path} in the Jesse project.',
        'path': report_path,
        'overwritten': existed,
        'size_bytes': len(content.encode('utf-8')),
    })


def fork_strategy(new_name: str, content: str) -> JSONResponse:
    import re
    path = f'strategies/{new_name}'

    if os.path.isdir(path):
        return JSONResponse({
            'status': 'error',
            'message': f'Strategy "{new_name}" already exists.'
        }, status_code=409)

    # Replace the class name in the code with the new strategy name
    updated_content = re.sub(r'(?m)^class\s+(\w+)\b', f'class {new_name}', content)

    os.makedirs(path, exist_ok=True)

    with open(f"{path}/__init__.py", "wt") as fin:
        fin.write(updated_content)

    return JSONResponse({
        'status': 'success',
        'message': f'Strategy "{new_name}" has been created.'
    })


def import_strategy(name: str, code: str) -> JSONResponse:
    import re
    
    # Sanitize strategy name to create valid folder name
    # Remove any characters that aren't alphanumeric, underscore, or hyphen
    sanitized_name = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
    # Replace multiple underscores with a single one
    sanitized_name = re.sub(r'_+', '_', sanitized_name)
    # Remove leading/trailing underscores
    sanitized_name = sanitized_name.strip('_')
    
    # Ensure name is not empty after sanitization
    if not sanitized_name:
        return JSONResponse({
            'status': 'error',
            'message': 'Invalid strategy name'
        }, status_code=400)
    
    path = f'strategies/{sanitized_name}'

    # Check if strategy already exists
    exists = os.path.isdir(path)
    if exists:
        # 'name' tells API clients such as the MCP import tool which local strategy collided.
        return JSONResponse({
            'status': 'error',
            'message': f'Strategy "{sanitized_name}" already exists.',
            'name': sanitized_name
        }, status_code=409)

    # Create strategy directory
    os.makedirs(path, exist_ok=True)

    # Write the strategy code to __init__.py
    with open(f"{path}/__init__.py", "wt") as f:
        f.write(code)

    return JSONResponse({
        'status': 'success',
        'message': f'Strategy "{sanitized_name}" has been imported.',
        'path': path,
        'name': sanitized_name
    })


def delete_strategy(name: str) -> JSONResponse:
    path = f'strategies/{name}'
    reports_path = f'{path}/reports'
    exists = os.path.isdir(path)

    if not exists:
        return JSONResponse({
            'status': 'error',
            'message': f'Strategy "{name}" does not exist.'
        }, status_code=404)

    # Explicitly remove report artifacts first, then the strategy directory.
    # This keeps behavior clear even if deletion logic changes later.
    if os.path.isdir(reports_path):
        shutil.rmtree(reports_path)

    shutil.rmtree(path)

    return JSONResponse({
        'status': 'success',
        'message': f'Strategy "{name}" has been deleted.'
    })
