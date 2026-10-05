# Jesse Repository Guide for AI Agents

## Overview
The jesse repository is the **core open-source framework** of the Jesse trading system. It contains the main Python codebase for backtesting trading strategies, importing historical data from crypto exchanges, running optimizations, and providing the API backend for the dashboard. It glues together the other repositories and makes them work together.

## Skills

This repo stores shared **Agent Skills** in `.claude/skills/` — focused, task-specific playbooks used by Claude Code and Codex. Codex also discovers them through the repository-relative `.agents/skills` symlink.

Before starting a task, scan the YAML frontmatter of every `.claude/skills/*/SKILL.md`. When a skill's `description` matches the task, read that `SKILL.md` completely before acting. A matching skill is the authoritative reference for what it covers, and its details are deliberately kept out of this file. This scan is the cross-platform fallback if native skill discovery or symlink support is unavailable.

- **`jesse-strategy-tests`** — conventions for writing Jesse strategy and engine tests.

## Key Characteristics

### Central Framework
- **jesse-live depends on this** - Changes here affect live trading
- **jesse-rust integrates here** - Rust functions are called from this codebase
- **dashboard consumes this API** - Frontend uses the FastAPI routes and controller files. 

### Technology Stack
- **Python** - Primary language
- **FastAPI** - API framework for all routes
- **NumPy** - Array operations and calculations
- **keewee** - ORM for the database

## Development Workflow

### Making Changes
When implementing features or fixing bugs:

1. **Understand the scope** - Determine if other repositories such as the dashboard need updates
2. **Implement the code** in the appropriate module
3. **Write/update tests** - Maintain test coverage
4. **Run tests** to verify changes:
   ```bash
   python -m pytest
   ```
5. **Consider jesse-live** - Does this affect live trading?
6. **Update API routes** if needed - Follow FastAPI patterns
7. Follow the user's local workspace instructions for restarting a development server.

### Python Environment
Use the project's active virtual environment or Conda environment. Run the commands
below from the repository root unless another working directory is specified.
`python`, `jesse`, and `pyrefly` should resolve to that environment's tools.

Verify that the interpreter meets the repository's Python version requirements.
If a compatible interpreter or the intended environment cannot be found, ask the
user which interpreter or environment to use before proceeding. Do not install
Python, create an environment, or install packages to work around a missing or
incompatible environment without explicit user authorization. Likewise, if a
required dependency or tool is missing, ask the user before installing it.

### Running Jesse Backend
Run Jesse from a Jesse project directory containing its configuration and strategies,
rather than from this framework's source directory:
```bash
jesse run
```

Use the project's configured port and log location. Restart only when authorized by
the user or local workspace instructions. Identify the process by its port and
working directory and stop only that instance gracefully; never use a broad
`pkill`. Check for active live/paper sessions and defer a disruptive restart while
they are running. Preserve unrelated processes and services. After restarting,
verify an authenticated API read succeeds on the project's configured port.

### Running Tests
Run the test suite after changes if asked.
```bash
python -m pytest
```

Dashboard Playwright tests start Jesse from a disposable project through
`dashboard-v1/tests/e2e/backend.mjs`. That process selects a dedicated env file
with `JESSE_ENV_FILE`, enables `IS_TEST_ENV=TRUE`, and uses a non-public
`POSTGRES_SCHEMA` containing `e2e`, `test`, or `testing`. Test-only reset/seed
routes are registered only in that mode and still require normal dashboard
authentication. Never enable `RESET_TEST_DATABASE` against `public` or a normal
development schema; the runtime guard intentionally rejects it.

If you've updated jesse-rust, build it from its own checkout using the same Python
environment, then run Jesse's tests. For sibling checkouts:
```bash
cd ../jesse-rust
./build-local.sh

cd ../jesse
python -m pytest
```

## Publishing the Docker Image

When the user asks to **"push a docker build for Jesse"** (or to "release"/"publish"
Jesse), publish by pushing a version git tag. The build runs on GitHub Actions
(`.github/workflows/docker-publish.yml`) and, on a `v*` tag push, publishes to **PyPI** and
**Docker Hub in parallel**: it uploads the package to PyPI and (independently) builds the
multi-arch `linux/amd64` + `linux/arm64` Docker image, publishing `salehmir/jesse:<version>`
and `salehmir/jesse:latest`. The two are independent — if one fails the other still
publishes; just cut a new version to retry the failed half.

Steps (run from inside `jesse/`):

1. Read the current version from `setup.py` (the `VERSION = "x.y.z"` line). Do **not**
   hardcode it — always read it fresh.
2. Tell the user which version you're about to tag and push (e.g. "Pushing docker build
   for v2.2.0").
3. Confirm the tag doesn't already exist (`git tag -l v<version>` and
   `git ls-remote --tags origin v<version>`). If it already exists, stop and ask the user
   whether to bump the version in `setup.py` (and `version.py`) first.
4. Create and push the tag:
   ```bash
   git tag v<version>
   git push origin v<version>
   ```
5. The `push: tags: ['v*']` trigger starts the workflow automatically. Optionally watch it:
   ```bash
   gh run watch --repo jesse-ai/jesse
   ```
6. When done, verify both architectures are present:
   ```bash
   docker buildx imagetools inspect salehmir/jesse:latest
   ```

Notes:
- Pushing a `v*` tag publishes **both PyPI and Docker** via this one workflow — PyPI first,
  Docker second. Do **not** also publish to PyPI manually (e.g. `twine upload`), or the tag
  push will fail on a duplicate-version upload.
- Required `jesse-ai/jesse` GitHub repo secrets: `PYPI_API_TOKEN` (PyPI),
  `DOCKERHUB_USERNAME` + `DOCKERHUB_TOKEN` (Docker Hub), and optionally
  `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` (build notification). Nothing to configure locally.
- A manual run (`gh workflow run docker-publish.yml --repo jesse-ai/jesse`) **skips PyPI**
  and only rebuilds/pushes `salehmir/jesse:latest` — useful as a credentials smoke test.

## Important Notes

### Debugging
- **Use `jh.debug()` for all debugging output** - Never use plain `print()`
- **Log format**: `[2024-12-06 18:23:12] ==> Your message here`
- Logs include timestamps and `==>` prefix
- Essential for debugging backtests and live trading sessions

### API Routes
- **Default to POST endpoints** unless specifically asked for GET
- Use FastAPI decorators and patterns
- Follow the structure of existing routes in `jesse/routes/`
- Return proper HTTP status codes and JSON responses
- Handle errors gracefully

### Code Style
- Add concise comments and docstrings for non-obvious intent, provider quirks, safety boundaries,
  invariants, and tradeoffs. Before handoff, audit every changed file for unexplained thresholds,
  constants, fallback or retry behavior, and test fakes that encode external responses. Keep the
  rationale in the code rather than only in the conversation; do not add comments that merely
  narrate what the code already says.
- Use existing dependencies. Ask the user before installing additional packages.
- Follow existing patterns and conventions
- Maintain consistency with the current codebase

### Type Annotations (strategy-facing typing)
User strategies are type-checked in editors, so annotations on anything strategies touch — indicators, `Strategy` properties/attributes, models like `Route` and `Position` — must be precise. Loose framework types surface as false-positive errors in every user's strategy file.

- **Indicators**: any indicator with a `sequential` param that returns `Union[<scalar>, np.ndarray]` must ship this `@overload` trio directly above the implementation (all existing ones already do — keep new ones consistent):
  ```python
  @overload
  def sma(candles: np.ndarray, period: int = ..., source_type: str = ..., sequential: Literal[False] = ...) -> float: ...
  @overload
  def sma(candles: np.ndarray, period: int = ..., source_type: str = ..., sequential: Literal[True] = ...) -> np.ndarray: ...
  @overload
  def sma(candles: np.ndarray, period: int = ..., source_type: str = ..., sequential: bool = ...) -> Union[float, np.ndarray]: ...
  ```
  When changing an indicator's parameters, update all three overloads too — callers only see the overloads, not the implementation signature.
- **Namedtuple-returning indicators** (macd, supertrend, bollinger_bands, …) intentionally keep untyped (Any) fields — don't type their fields piecemeal; it would need a proper generic design to distinguish sequential from non-sequential fields.
- **Late-initialized attributes** that the router/engine sets right after instantiation (`Strategy.name/symbol/exchange/timeframe/position/broker`, `Route.strategy`): declare the real post-initiation type with the `None` default silenced — e.g. `self.position: Position = None  # type: ignore` — instead of `Optional[...]`, so user strategies don't need `is not None` narrowing. `Strategy.hp` is always a `dict` (empty when the strategy has no hyperparameters); check it with falsiness (`if not self.hp`), never `is None`.
- Verify strategy-facing typing changes with Pyrefly:
  ```bash
  pyrefly check 'jesse/indicators/*.py' jesse/strategies/Strategy.py --search-path .
  ```
  For a broader regression check, run it over `'jesse/strategies/*/__init__.py'` (the test strategies must report 0 errors).
- Try to import only at the top of the file.

### Jesse-Rust Integration
- When using Rust functions, **assume they exist** - don't add existence checks
- Update Python code to call new Rust implementations
- Build jesse-rust locally and run tests to verify integration
- Performance-critical code should be delegated to jesse-rust when possible

## File Structure
- `jesse/` - Main source code
  - `indicators/` - Technical indicators
  - `modes/` - Backtest, optimize, import modes, monte carlo, etc
  - `routes/` - FastAPI route handlers
  - `services/` - data services, etc
  - `strategies/` - Base strategy classes
  - `store/` - State management
- `tests/` - Test suite
- `storage/` - Logs and temporary files
- `requirements.txt` - Python dependencies
- `setup.py` - Package configuration

## Testing Strategy

### Unit Tests
- Run `pytest` after every change if asked in the conversation.
- Maintain or improve test coverage
- Add tests for new features if asked in the conversation.
- Fix failing tests immediately

## Related Repositories
This repository is the foundation of the Jesse ecosystem:
- **jesse-live** - Depends heavily on jesse for live trading
- **jesse-rust** - Performance layer integrated into jesse
- **dashboard-v1** - Frontend that consumes jesse's API
- **Jesse projects** - Separate project directories that run the framework with their own configuration and strategies
- **laravel-jesse-trade** - Laravel project that contains the api1 backend of the jesse-trade website.
- **go-jesse-trade/backend** - Go project that contains the api2 backend of the jesse-trade website.
- **go-jesse-trade/frontend** - NuxtJS project that contains the frontend of the jesse-trade website.
- **strategy-executor** - Go project that contains the strategy executor microservice used to execute strategies submitted by the users of the website.
