import time
import logging
import socket
import signal
import threading
import os
import sys
import io

import click
from importlib.metadata import version as get_version
import uvicorn

import jesse.helpers as jh

# Default Host and Port for the Jesse API server
HOST = "0.0.0.0"
PORT = 9000

@click.group()
@click.version_option(get_version("jesse"))
def cli() -> None:
    """CLI entrypoint for Jesse."""
    pass


@cli.command()
@click.option(
    "--strict/--no-strict",
    default=True,
    help="Default is the strict mode which will raise an exception if the values for license is not set.",
)
def install_live(strict: bool) -> None:
    """Install and configure the live trading plugin."""
    from jesse.services.installer import install

    install(is_live_plugin_already_installed=jh.has_live_trade_plugin(), strict=strict)


@cli.command()
@click.option('--compression/--no-compression', default=True, help='Automatically compress candle history older than 30 days.')
@click.option('--status', 'show_status', is_flag=True, help='Inspect storage without changing it.')
def enable_timescale(compression: bool, show_status: bool) -> None:
    """Opt in to TimescaleDB. Stop sessions and back up before converting history."""
    from jesse.services.db import database
    from jesse.services.timescale import enable, status
    import peewee

    jh.validate_cwd()
    database.open_connection()
    try:
        if show_status:
            click.echo(status())
        else:
            # Ensure candle storage exists without starting the server or clearing
            # coordinator membership from this standalone maintenance command.
            from jesse.models.Candle import Candle
            Candle.create_table(safe=True)
            click.echo(enable(migrate_existing=True, compression=compression))
    except (peewee.PeeweeException, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    finally:
        database.close_connection()


@cli.command()
@click.option(
    "--skip-agent-rules",
    is_flag=True,
    default=False,
    help="Skip syncing the agent rules file (AGENTS.md / CLAUDE.md / mcp-rules.md) in the project directory.",
)
@click.option(
    "--skip-lsp",
    is_flag=True,
    default=False,
    help="Skip the Python Language Server for this run (disables editor code intelligence).",
)
def run(skip_agent_rules: bool, skip_lsp: bool) -> None:
    """Own shared state for the server and shut down jobs before its service."""
    from jesse.services import coordination_runtime
    from jesse.services.env import ENV_VALUES

    if os.name == 'nt':
        # Redirected Windows output defaults to legacy code pages, which cannot
        # encode the dashboard banner. Keep launcher logs and spawned jobs UTF-8.
        os.environ['PYTHONIOENCODING'] = 'utf-8'
        for stream in (sys.stdout, sys.stderr):
            if isinstance(stream, io.TextIOWrapper):
                stream.reconfigure(encoding='utf-8')

    jh.validate_cwd()
    client = coordination_runtime.create_client(ENV_VALUES, owner=True)
    # Reserve the API listener before migrations or shared-state cleanup. A second
    # launch must fail without clearing an existing instance's worker membership.
    host = ENV_VALUES.get('APP_HOST', HOST)
    port = int(ENV_VALUES.get('APP_PORT', PORT))
    listener = socket.socket(socket.AF_INET6 if ':' in host else socket.AF_INET)
    if os.name == 'posix':
        # Match asyncio's listener behavior so TIME_WAIT does not block quick restarts.
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    elif hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
        # Windows otherwise permits some competing binds to an in-use listener.
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    owns_runtime = False
    # Uvicorn re-raises SIGTERM after its own shutdown. Convert that signal into
    # Python unwinding so jobs still drain before the coordinator's pipe closes.
    stop_signals = [signal.SIGTERM]
    if hasattr(signal, 'SIGBREAK'):
        stop_signals.append(signal.SIGBREAK)
    previous_signals = {sig: signal.getsignal(sig) for sig in [signal.SIGINT, *stop_signals]}
    handles_signals = threading.current_thread() is threading.main_thread()
    def terminate(signum, frame) -> None:
        raise SystemExit(128 + signum)
    if handles_signals:
        for sig in stop_signals:
            signal.signal(sig, terminate)
    try:
        listener.bind((host, port))
        listener.listen(2048)  # Match Uvicorn's default backlog.
        # Test schema reset is startup work, never an import-time side effect of
        # a duplicate command or a spawned session process.
        from jesse.services.e2e_database import reset_test_database_if_requested
        reset_test_database_if_requested()
        coordination_runtime.start(client)
        owns_runtime = True
        _run_server(skip_agent_rules, skip_lsp, listener)
        if coordination_runtime.failed():
            raise click.ClickException('The bundled coordinator stopped unexpectedly; restart Jesse')
    except KeyboardInterrupt:
        # Ctrl+C is a normal user-requested stop, including during startup.
        pass
    except OSError as exc:
        raise click.ClickException(str(exc)) from exc
    finally:
        try:
            if owns_runtime:
                try:
                    from jesse.services import research_jobs
                    research_jobs.shutdown()
                finally:
                    try:
                        from jesse.services.multiprocessing import process_manager
                        process_manager.shutdown()
                    finally:
                        try:
                            # Signals are not the only exit path: coordinator failure
                            # and startup errors must also reap the owned MCP worker.
                            from jesse.mcp import terminate_mcp_server
                            terminate_mcp_server()
                        finally:
                            from jesse.services.lsp import terminate_lsp_server
                            terminate_lsp_server()
        finally:
            try:
                coordination_runtime.stop()
            finally:
                listener.close()
                if handles_signals:
                    for sig, handler in previous_signals.items():
                        signal.signal(sig, handler)


def _run_server(skip_agent_rules: bool, skip_lsp: bool, listener: socket.socket) -> None:
    """Start the Jesse application server."""
    from jesse.app import fastapi_app
    from jesse.services.multiprocessing import process_manager
    from jesse.services.env import is_test_env

    # Display welcome message
    welcome_message = """
     ██╗███████╗███████╗███████╗███████╗
     ██║██╔════╝██╔════╝██╔════╝██╔════╝
     ██║█████╗  ███████╗███████╗█████╗  
██   ██║██╔══╝  ╚════██║╚════██║██╔══╝  
╚█████╔╝███████╗███████║███████║███████╗
 ╚════╝ ╚══════╝╚══════╝╚══════╝╚══════╝
                                        
    """
    version = get_version("jesse")
    print(welcome_message)

    version_line = (
        click.style("  Jesse ", fg="white")
        + click.style(f"v{version}", fg="yellow", bold=True)
    )

    if jh.has_live_trade_plugin():
        try:
            from jesse_live.version import __version__ as live_version
            version_line += (
                click.style("  ·  ", fg="white")
                + click.style("Live Plugin ", fg="white")
                + click.style(f"v{live_version}", fg="yellow", bold=True)
            )
        except ImportError:
            pass

    print(version_line)

    jh.validate_cwd()

    print("")

    # sync the agent rules file (AGENTS.md / CLAUDE.md / mcp-rules.md) with the bundled rules
    if not skip_agent_rules and not is_test_env():
        try:
            from jesse.mcp.agent_rules import sync_agent_rules

            sync_agent_rules()
            print("")
        except Exception as e:
            print(f"Could not sync agent rules: {str(e)}")
            print("")

    # run all the db migrations
    from jesse.services.migrator import run as run_migrations
    import peewee

    try:
        run_migrations()
    except peewee.OperationalError:
        sleep_seconds = 10
        print(f"Database wasn't ready. Sleep for {sleep_seconds} seconds and try again.")
        time.sleep(sleep_seconds)
        run_migrations()

    if skip_lsp:
        click.echo("Skipping Python Language Server for this run. Editor code intelligence will be unavailable.")

    if not is_test_env() and not skip_lsp:
        try:
            from jesse.services.lsp import install_lsp_server

            skip_lsp = not install_lsp_server(allow_skip=True)
        except Exception as e:
            print(jh.color(f"Error installing Python Language Server: {str(e)}", "red"))
            pass

    # read port from .env file and update the global variables port and host, if not found, use default
    global HOST, PORT
    from jesse.services.env import ENV_VALUES

    if "APP_PORT" in ENV_VALUES:
        PORT = int(ENV_VALUES["APP_PORT"])
    # HOST keeps default value of "0.0.0.0" if not specified

    if "APP_HOST" in ENV_VALUES:
        HOST = ENV_VALUES["APP_HOST"]

    # Resolve the public dashboard origin before starting any server, so an invalid
    # DASHBOARD_URL stops startup instead of producing links that do not work.
    from jesse.services.dashboard_url import InvalidDashboardUrlError, resolve_dashboard_url

    try:
        public_dashboard_url = resolve_dashboard_url(ENV_VALUES, HOST, PORT)
    except InvalidDashboardUrlError as e:
        raise click.ClickException(str(e))

    # Set global Jesse API configuration for MCP and other services

    if not is_test_env() and not skip_lsp:
        try:
            from jesse.services.lsp import run_lsp_server

            run_lsp_server()
        except Exception as e:
            print(jh.color(f"Error running Python Language Server: {str(e)}", "red"))
            pass
    
    # print dashboard box and suppress uvicorn's own "running on" line
    dashboard_url = public_dashboard_url
    _border = click.style("─" * (len(dashboard_url) + 34), fg="magenta", bold=True)
    print(click.style("┌" + _border + "┐", fg="magenta", bold=True))
    print(
        click.style("│  ", fg="magenta", bold=True)
        + click.style("⬡ Dashboard is available at ", fg="white", bold=True)
        + click.style(dashboard_url, fg="magenta", bold=True)
        + click.style("  │", fg="magenta", bold=True)
    )
    print(click.style("└" + _border + "┘", fg="magenta", bold=True))
    print()

    if not is_test_env():
        try:
            from jesse.mcp import run_mcp_server

            run_mcp_server(jesse_host=HOST, jesse_port=PORT, dashboard_url=public_dashboard_url)
        except Exception as e:
            print(jh.color(f"Error running MCP Server: {str(e)}", "red"))
            pass

    # run the main application
    process_manager.flush()

    class _SuppressUvicornStartup(logging.Filter):
        def filter(self, record):
            return "Uvicorn running on" not in record.getMessage()

    logging.getLogger("uvicorn.error").addFilter(_SuppressUvicornStartup())

    from jesse.services import coordination_runtime
    server = uvicorn.Server(uvicorn.Config(fastapi_app, host=HOST, port=PORT, log_level="info"))
    # An empty replacement would invalidate active locks; exit the whole instance instead.
    coordination_runtime.monitor(lambda: setattr(server, 'should_exit', True))
    server.run(sockets=[listener])
