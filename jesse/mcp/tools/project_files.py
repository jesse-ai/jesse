"""
Jesse Project File Tools

MCP tools for files inside the Jesse project's strategies/ and research_scripts/ folders,
on the machine running Jesse:
- list_project_files, read_project_file: bounded listings and text reads
- write_project_file, create_project_directory: text files and folders
- move_project_path, copy_project_path, delete_project_path: explicit overwrite/recursive semantics

Strategy folders (strategies/<Name>) are ordinary folders for these tools: they can be
created, copied, renamed, and deleted like any other. Only the two root folders are
protected. Jesse never follows symlinks for these tools and they cannot reach any other
project file (.env, storage, the database). Full rules: jesse://research_scripts.

The tools are async and run their API call in a worker thread (see offload.py), so a copy,
move, or recursive delete taking minutes does not stall other MCP requests on this worker.
"""

from .offload import run_blocking
from .services import (
    copy_project_path_service,
    create_project_directory_service,
    delete_project_path_service,
    list_project_files_service,
    move_project_path_service,
    read_project_file_service,
    write_project_file_service,
)


def register_project_files_tools(mcp):
    """
    Register the project file tools.

    Args:
        mcp: The MCP server instance.
    """

    @mcp.tool()
    async def list_project_files(path: str = "", recursive: bool = False, max_entries: int = 200) -> dict:
        """
        List files and folders in the Jesse project's strategies/ or research_scripts/ folder.

        Runs on the machine running Jesse. Paths are project-relative and must start with
        "strategies/" or "research_scripts/"; an empty path lists those two roots.
        Symlinks are shown with type "symlink" and never followed.

        Parameters:
            path (str): Folder to list, e.g. "research_scripts" or "strategies/MyStrategy".
            recursive (bool): Also list sub-folders. Default False.
            max_entries (int): 1-1000, default 200. `truncated` is true when more exist;
                list a narrower folder instead of paging.

        Returns:
            dict: {"status": "success", "path", "entries": [{"path", "type":
            "file|directory|symlink|other", "size_bytes" (files), "modified_at"}], "truncated"}
            or {"status": "error", "error_type", "message"}. error_type values:
            "invalid_path", "not_found", "strategy_not_found", "wrong_type", "unsafe_path"
            (symlink), "permission_denied", "authentication_failed", "connection_error".
        """
        return await run_blocking(list_project_files_service, path, recursive, max_entries)

    @mcp.tool()
    async def read_project_file(path: str, start_line: int = 1, max_lines: int = 400) -> dict:
        """
        Read a text file from strategies/ or research_scripts/ in the Jesse project.

        Returns up to `max_lines` lines (1-2000) starting at `start_line` (1-based), and at
        most 256K characters. When `has_more` is true, call again with `next_start_line`.
        Binary files (models, pickles, images) return only kind "binary", size_bytes and
        modified_at, never their contents. Use read_strategy for a strategy's __init__.py.

        Returns:
            dict: {"status": "success", "path", "kind": "text", "content", "start_line",
            "end_line", "has_more", "next_start_line" (when has_more), "line_truncated"
            (one line longer than the limit was cut), "size_bytes", "modified_at"}, the
            binary metadata described above, or an error with error_type "not_found",
            "wrong_type" (a folder), "unsafe_path" (symlink), or "invalid_path".
        """
        return await run_blocking(read_project_file_service, path, start_line, max_lines)

    @mcp.tool()
    async def write_project_file(path: str, content: str, overwrite: bool = False) -> dict:
        """
        Write a UTF-8 text file in strategies/ or research_scripts/.

        Jesse writes it on the machine running Jesse; missing parent folders are created,
        including a strategy folder (check the strategy name: a typo creates a new folder).
        Use create_strategy for a new strategy, write_strategy for a strategy's __init__.py,
        and save_strategy_report for reports. At most 2 MiB; text is stored exactly as sent.

        Research scripts are opt-in: only write in research_scripts/ when the user
        specifically asks for a script, asks for machine-learning research that needs a
        script or Jesse's research module, or explicitly asks to use the research module.
        A generic request to research, find, test, or improve strategies is NOT such a
        request; use the catalog, backtest, optimization, Monte Carlo, and significance-test
        tools instead, and ask the user before switching to a script.

        Parameters:
            path (str): e.g. "research_scripts/ml/gather_data.py" or
                "strategies/MyStrategy/features.py".
            content (str): Complete file text.
            overwrite (bool): Default False refuses an existing file with error_type
                "already_exists". Pass True only to replace a file you intend to replace.

        Returns:
            dict: {"status": "success", "path", "size_bytes", "overwritten", "location"} or an
            error with error_type "already_exists", "protected_path" (a root folder),
            "unsafe_path" (symlink), "wrong_type", "too_large", or "invalid_path".
        """
        return await run_blocking(write_project_file_service, path, content, overwrite)

    @mcp.tool()
    async def create_project_directory(path: str) -> dict:
        """
        Create a folder (and missing parents) in strategies/ or research_scripts/ on the
        machine running Jesse, including a strategy folder such as "strategies/NewStrategy".
        An existing folder returns "created": false. The research-scripts opt-in rule of
        write_project_file applies. A new strategy also needs an __init__.py whose Strategy
        class has the folder's name; create_strategy makes both in one step.

        Returns:
            dict: {"status": "success", "path", "created"} or an error with error_type
            "protected_path" (a root folder), "wrong_type", "unsafe_path", or "invalid_path".
        """
        return await run_blocking(create_project_directory_service, path)

    @mcp.tool()
    async def move_project_path(source: str, destination: str, overwrite: bool = False) -> dict:
        """
        Move or rename a file or folder within or between strategies/ and research_scripts/,
        including a whole strategy folder, e.g. "strategies/Old" to "strategies/New".

        Root folders cannot be moved, and symlinks are never moved. Folders are never
        merged: a folder moves only to a path that does not exist. overwrite=True replaces an
        existing destination file with a source file only.

        Moving never edits code. After renaming a strategy folder, rename the Strategy class
        in its __init__.py to the new folder name and update imports that use the old name.
        Jesse looks the class up by folder name; when it is missing, loading the strategy
        renames the file's first class, which may not be the Strategy class. Saved sessions
        keep the old name.

        Returns:
            dict: {"status": "success", "source", "destination", "type", "overwritten"} or an
            error with error_type "not_found", "already_exists", "wrong_type",
            "protected_path", "unsafe_path", "cross_device", or "invalid_request".
        """
        return await run_blocking(move_project_path_service, source, destination, overwrite)

    @mcp.tool()
    async def copy_project_path(source: str, destination: str, overwrite: bool = False) -> dict:
        """
        Copy a file or folder within or between strategies/ and research_scripts/.

        Use this to promote artifacts a research script produced into the strategy that
        loads them, e.g. copy "research_scripts/ml/out/model.pkl" and "scaler.pkl" to
        "strategies/MyStrategy/model.pkl" and "strategies/MyStrategy/scaler.pkl" (the files
        ml_predict loads). Binary files are copied on the Jesse host; their bytes never pass
        through the assistant. The copy appears only when complete.

        A whole strategy folder can be copied to a new strategies/<Name> folder; as with a
        rename, then change the copied Strategy class name to the new folder name.

        overwrite=True replaces an existing destination file; folder copies never merge or
        overwrite, so the destination folder must not exist. A source containing a symlink
        is refused. Limits: 1 GiB and 10,000 entries per copy.

        Returns:
            dict: {"status": "success", "source", "destination", "type", "size_bytes",
            "overwritten"} or an error with error_type "already_exists", "not_found",
            "strategy_not_found" (source strategy folder), "protected_path", "unsafe_path",
            "too_large", or "invalid_request".
        """
        return await run_blocking(copy_project_path_service, source, destination, overwrite)

    @mcp.tool()
    async def delete_project_path(path: str, recursive: bool = False) -> dict:
        """
        Delete a file, symlink, or folder in strategies/ or research_scripts/, including a
        whole strategy folder with its code, reports, and models.

        A folder must be empty unless recursive=True, which deletes everything inside it.
        Deleting a symlink removes only the link, never its target. Root folders cannot be
        deleted. Deletion is permanent: only delete what the user asked for or what you
        created in this task.

        Returns:
            dict: {"status": "success", "path", "type", "deleted_files",
            "deleted_directories"} or an error with error_type "not_found",
            "directory_not_empty", "protected_path", "unsafe_path", or "invalid_path".
        """
        return await run_blocking(delete_project_path_service, path, recursive)
