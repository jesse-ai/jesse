# Jesse Repository Guide for AI Agents

## Overview
The jesse repository is the **core open-source framework** of the Jesse trading system. It contains the main Python codebase for backtesting trading strategies, importing historical data from crypto exchanges, running optimizations, and providing the API backend for the dashboard. It glues together the other repositories and makes them work together.

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
   cd-jesse && pytest
   ```
5. **Consider jesse-live** - Does this affect live trading?
6. **Update API routes** if needed - Follow FastAPI patterns
7. **Don't restart server** unless specifically asked

### Python Environment
Use the Jesse Python interpreter:
```
/Users/salehmir/miniconda3/envs/jesse3.12/bin/python
```

### Running Jesse Backend
The API server provides routes for the dashboard:
```bash
# Stop any running process
pkill -f "jesse run"

# Start Jesse from bot directory (not jesse/)
cd /Users/salehmir/codes/jesse/dev-jesse/bot
/Users/salehmir/miniconda3/envs/jesse3.12/bin/jesse run > /tmp/jesse-output.log 2>&1 &

# Server runs at http://localhost:9001

# Check logs
tail -f /tmp/jesse-output.log
```

**Important**: Don't restart Jesse after code changes unless explicitly requested.

### Running Tests
Run the test suite after changes if asked.
```bash
cd-jesse && pytest
```

If you've updated jesse-rust, run tests after building:
```bash
cd /Users/salehmir/Codes/jesse/dev-jesse/jesse-rust
./build-local.sh

cd /Users/salehmir/Codes/jesse/dev-jesse/jesse
pytest
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
   cd /Users/salehmir/Codes/jesse/dev-jesse/jesse
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
- Don't write comments for functions unless asked
- Never try to install new packages - assume they're already installed. if need to install new packages, ask me first.
- Follow existing patterns and conventions
- Maintain consistency with the current codebase
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
- **bot** - Jesse project instance that runs the framework
- **laravel-jesse-trade** - Laravel project that contains the api1 backend of the jesse-trade website.
- **go-jesse-trade/backend** - Go project that contains the api2 backend of the jesse-trade website.
- **go-jesse-trade/frontend** - NuxtJS project that contains the frontend of the jesse-trade website.
- **strategy-executor** - Go project that contains the strategy executor microservice used to execute strategies submitted by the users of the website.

