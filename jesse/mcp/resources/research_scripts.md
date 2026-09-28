# Project Files and Research Scripts

Jesse's project file tools and research script tools work on the machine running Jesse,
inside the Jesse project, whichever computer the assistant runs on and also when Jesse runs
in Docker. Never use your own local file or shell tools for these folders; they would act on
your workspace, not on the Jesse project.

## When research scripts are allowed (read first)

Research scripts are opt-in. Create, edit, or run files in `research_scripts/` ONLY when the
user:

1. specifically asks for a script, or
2. asks for machine-learning research that needs a script or Jesse's research module (for
   example gathering ML features/labels from a strategy and training a model), or
3. explicitly asks to use Jesse's research module (`from jesse import research`).

A generic request to research, find, test, compare, or improve strategies is NOT such a
request and is never consent to write or run scripts. For those, use the existing tools:
`browse_strategy_catalog`, backtests, optimization, Monte Carlo, and rule significance tests.
If you believe a script would genuinely help, ask the user and wait for a yes first.

To analyze, compare, or chart results of sessions that already ran, use `run_analysis`
(`jesse://session_analysis`). It runs in a temporary workspace outside the project folders
and is not a research script.

## Security: scripts are not sandboxed

`run_research_script` executes Python as the same operating-system user as Jesse, with
Jesse's environment variables, working directory (the project root), database access,
network access, and filesystem permissions. A script can read `.env`, stored exchange API
keys, and any file that user can read, and could place orders through configured exchange
keys. The folder restrictions below apply to the file tools only, not to code a script runs.

- Read every script before you run it, and only run scripts you wrote for this task or the
  user asked you to run.
- Never write scripts that read `.env` or credentials, print secrets, place orders, or
  connect to live or paper exchange accounts.
- Do not install packages from a script. Use what the Jesse environment already has.

## File tools

Paths are project-relative and start with `strategies/` or `research_scripts/`.
Absolute paths, `..`, and backslashes are refused. Symlinks are never followed; a symlinked
root or strategy folder is refused (`error_type: "unsafe_path"`), and deleting a symlink
removes only the link.

| Tool | Purpose |
|------|---------|
| `list_project_files(path="", recursive=False, max_entries=200)` | List a folder (max 1000 entries; narrow the path when `truncated`) |
| `read_project_file(path, start_line=1, max_lines=400)` | Read text in pages; binary files return size/metadata only |
| `write_project_file(path, content, overwrite=False)` | Write a UTF-8 text file (max 2 MiB); creates missing parent folders |
| `create_project_directory(path)` | Create a folder and its parents |
| `move_project_path(source, destination, overwrite=False)` | Move or rename |
| `copy_project_path(source, destination, overwrite=False)` | Copy a file or folder (max 1 GiB / 10,000 entries) |
| `delete_project_path(path, recursive=False)` | Delete; folders must be empty unless `recursive=True` |

Rules:

- `overwrite=False` (default) refuses an existing destination with `already_exists`.
  `overwrite=True` replaces a file with a file only. Folders are never merged or replaced:
  delete the destination folder first if the user wants it replaced.
- Only the two root folders are protected: `strategies/` and `research_scripts/` cannot be
  moved, deleted, or replaced (`protected_path`), and `strategies/` is never created
  (`research_scripts/` is created on first write). Everything inside them, including whole
  strategy folders (`strategies/<Name>`), can be created, copied, renamed or moved, and
  deleted (`recursive=True` for a folder that is not empty).
- Moving or copying never edits code. After renaming or copying a strategy folder, rename
  the Strategy class in its `__init__.py` to the new folder name and update any imports of
  the old name (`read_strategy` / `write_strategy`). Jesse looks the class up by the folder
  name; when it is missing, loading the strategy renames the first class in the file, which
  may not be the Strategy class. Saved sessions keep the old strategy name.
- Prefer `create_strategy` or `import_catalog_strategy` for a new strategy (they write a
  matching class), `read_strategy` / `write_strategy` for a strategy's `__init__.py`, and
  `save_strategy_report` for reports. Writing into a strategy folder that does not exist
  creates it, so check strategy names.
- Deleting a strategy folder permanently removes its code, reports, and models. Only delete
  what the user asked you to delete or what you created in this task.

### If a call is cancelled or times out

A file or job call that your client cancels or gives up on may still finish on the Jesse
host; the cancellation reply does not say whether it did. Check before retrying: list or
read the path after a file operation, and after `run_research_script` list the newest jobs
with `get_research_job_status()`. A job that started anyway keeps running until it
finishes, reaches its timeout, or you stop it with `cancel_research_job`. A retry with
`overwrite=False` is safe: it refuses instead of replacing what the first call wrote.

## Running a script

```
run_research_script(path="research_scripts/ml/train.py", args=["--symbol", "BTC-USDT"], timeout_minutes=60)
→ {"status": "success", "job": {"id": "<job_id>", "status": "running", ...}}
get_research_job_status(job_id="<job_id>")      # running | succeeded | failed | cancelled | timed_out | interrupted
get_research_job_output(job_id="<job_id>", tail_lines=200)
cancel_research_job(job_id="<job_id>")          # stops the script and every process it started
```

- Jesse runs `python <path> <args...>` with its own interpreter (same packages as Jesse),
  from the project root, without a shell. Each `args` item reaches `sys.argv` unchanged; no
  quoting, globbing, pipes, or command substitution.
- Only `.py` files inside `research_scripts/` can be run. At most 2 jobs run at once
  (`too_many_jobs`). `timeout_minutes` is 1-720 (default 60).
- Output (stdout and stderr) is kept up to 20 MiB per job; read its end with
  `get_research_job_output`. A `failed` job's output ends with the Python traceback.
- Jobs are stopped when Jesse shuts down normally and then show as `interrupted`. After a
  crash they also show as `interrupted`, but their processes may still be running untracked.
- Poll at a sensible interval (for example every 15-60 seconds for long jobs) instead of
  continuously. Cancel jobs you no longer need.

Because the working directory is the project root, write outputs to project-relative paths
such as `research_scripts/ml/output/...`. `from jesse import research` works as in a notebook
opened at the project root, and `import strategies.<Name>` works from any sub-folder.

## Machine-learning workflow and promoting a model

Use this workflow only under the opt-in rule above.

1. The strategy defines `ml_features()` and, in gather mode (`self.ml_mode = "gather"`,
   the default), records features and labels. Edit it with `read_strategy` /
   `write_strategy`.
2. Write a gather/train script in `research_scripts/`, e.g. using
   `research.gather_ml_data(...)`, `research.load_ml_data_csv(...)`, and
   `research.train_model(data, estimator, task=..., save_to="research_scripts/ml/models/v1")`.
   `train_model` saves `model.pkl`, `scaler.pkl`, and `feature_importance.pkl` into `save_to`.
3. Run it with `run_research_script`, then read the metrics from the output.
4. Promote the model only when the user wants it deployed: copy each artifact into the
   strategy folder, where `ml_predict()` / `ml_predict_proba()` load it:

```
copy_project_path("research_scripts/ml/models/v1/model.pkl", "strategies/MyStrategy/model.pkl")
copy_project_path("research_scripts/ml/models/v1/scaler.pkl", "strategies/MyStrategy/scaler.pkl")
copy_project_path("research_scripts/ml/models/v1/feature_importance.pkl", "strategies/MyStrategy/feature_importance.pkl")
```

   Pass `overwrite=True` only when the user wants to replace the currently deployed model.
5. Switch the strategy to deploy mode (`self.ml_mode = "deploy"`) and verify it with a
   normal backtest through the backtest tools.

Model files are pickles: loading one runs code, so only promote artifacts produced by a
script you wrote or the user supplied.
