import threading
import time
from typing import List
import multiprocessing as mp
import traceback
from jesse.services.redis import sync_publish, sync_redis
from jesse.services.failure import terminate_session
import jesse.helpers as jh
from jesse.services.env import ENV_VALUES
import os
import signal

# set multiprocessing process type to spawn
mp.set_start_method('spawn', force=True)


class Process(mp.Process):
    def __init__(self, *args, **kwargs):
        # Extract PostHog config and auth token if provided
        self._posthog_config = kwargs.pop('posthog_config', None)
        self._posthog_auth_token = kwargs.pop('posthog_auth_token', None)
        mp.Process.__init__(self, *args, **kwargs)

    def run(self):
        try:
            mp.Process.run(self)
        except Exception as e:
            if type(e).__name__ == 'Termination':
                sync_publish('termination', {})
                jh.terminate_app()
            else:
                
                # Send to PostHog if client is available
                try:
                    from jesse.services.posthog import get_posthog_service
                    svc = get_posthog_service()
                    
                    # Initialize PostHog in child process if config is provided & client is not initialized yet
                    # this checking is to avoid re-initializing posthog in child processes on each exception --- only the first exception in a process will initialize posthog
                    if self._posthog_config and svc._client is None:
                        # Set the config and initialize
                        svc._api_key = self._posthog_config.get('api_key')
                        svc._host = self._posthog_config.get('host', 'https://eu.i.posthog.com')
                        svc._initialize()
                        
                        # identify user to posthog using the auth token
                        svc.identify_user(self._posthog_auth_token)
                    
                    ctx = {
                        'source': 'multiprocessing_exception_handler',
                        'process_name': getattr(self, 'name', 'Unknown'),
                        'process_pid': getattr(self, 'pid', 'Unknown'),
                        'traceback': str(traceback.format_exc())
                    }
                    svc.capture_exception(e, ctx)
                except Exception:
                    # Don't let PostHog errors affect the main exception handling
                    pass
                
                sync_publish(
                    'exception',
                    {
                        'error': f'{type(e).__name__}: {e}',
                        'traceback': str(traceback.format_exc()),
                    },
                )

                print('Unhandled exception in the process:')
                print(traceback.format_exc())

                terminate_session()


class ProcessManager:
    def __init__(self):
        self._workers: List[Process] = []
        self._pid_to_client_id_map = {}
        self.client_id_to_pid_to_map = {}
        try:
            port = ENV_VALUES.get('APP_PORT', '9000')
        except:
            port = '9000'
            
        self._active_workers_key = f"{port}|active-processes"
        self._cleanup_thread = threading.Thread(target=self._cleanup_finished_workers, daemon=True)
        self._cleanup_thread.start()

    def _reset(self):
        self._workers = []
        self._pid_to_client_id_map = {}
        self.client_id_to_pid_to_map = {}
        # clear all process status
        sync_redis.delete(self._active_workers_key)

    @staticmethod
    def _prefixed_pid(pid):
        return f"{ENV_VALUES['APP_PORT']}|{pid}"

    @staticmethod
    def _prefixed_client_id(client_id):
        return f"{ENV_VALUES['APP_PORT']}|{client_id}"

    def _add_process(self, client_id):
        sync_redis.sadd(self._active_workers_key, client_id)

    def add_task(self, function, *args):
        client_id = args[0]
        
        # Get PostHog config and auth token from parent process if PostHog is initialized
        posthog_config = None
        posthog_auth_token = None
        try:
            from jesse.services.posthog import get_posthog_service
            parent_posthog_svc = get_posthog_service()
            if parent_posthog_svc._client is not None:
                # PostHog is initialized in parent(user has turned on JesseMonitoring in the Dashboard), pass config to child
                from jesse.config import config
                posthog_config = config.get('env', {}).get('posthog', {})
                # Pass the auth token for user identification in child processes
                posthog_auth_token = parent_posthog_svc._current_user_token
        except Exception:
            # If we can't get config, continue without PostHog
            pass
        
        w = Process(target=function, args=args, posthog_config=posthog_config, posthog_auth_token=posthog_auth_token)
        self._workers.append(w)
        w.start()

        self._pid_to_client_id_map[self._prefixed_pid(w.pid)] = self._prefixed_client_id(client_id)
        self.client_id_to_pid_to_map[self._prefixed_client_id(client_id)] = self._prefixed_pid(w.pid)
        self._add_process(client_id)

    def get_client_id(self, pid):
        try:
            client_id: str = self._pid_to_client_id_map[self._prefixed_pid(pid)]
        except KeyError:
            return None
        return jh.string_after_character(client_id, '|')

    def get_pid(self, client_id):
        return self.client_id_to_pid_to_map[self._prefixed_client_id(client_id)]

    def cancel_process(self, client_id):
        sync_redis.srem(self._active_workers_key, client_id)

    def flush(self):
        for w in self._workers:
            try:
                # Try terminate first
                w.terminate()
                # Give it a moment to terminate gracefully
                w.join(timeout=3)
                
                # If still alive, wait a brief moment then force kill
                if w.is_alive():
                    time.sleep(0.5)  # Give terminate a chance to complete
                    os.kill(w.pid, signal.SIGKILL)
                    
                w.close()
            except Exception as e:
                jh.debug(f"Error while terminating process: {str(e)}")
                
        self._reset()

    def _cleanup_finished_workers(self):
        while True:
            try:
                for w in self._workers[:]:  # Create a copy of the list to avoid modification during iteration
                    if not w.is_alive():
                        try:
                            w.join(timeout=1)
                            w.close()
                            self._workers.remove(w)
                        except Exception as e:
                            jh.debug(f"Error during worker cleanup: {str(e)}")
            except Exception as e:
                jh.debug(f"Error in cleanup thread: {str(e)}")
            time.sleep(5)

    @property
    def active_workers(self) -> set:
        """
        Returns the set of all the processes client_id as a list of strings
        """
        return {client_id.decode('utf-8') for client_id in sync_redis.smembers(self._active_workers_key)}


process_manager = ProcessManager()
# flush all processes on startup to avoid any leftover processes
# process_manager.flush()
