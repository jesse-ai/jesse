import os
import json
import base64
from datetime import timedelta
from multiprocessing import cpu_count
import optuna
import ray
import numpy as np
import jesse.helpers as jh
import jesse.services.logger as logger
from jesse import exceptions
from jesse.services.redis import sync_publish
from jesse.modes.optimize_mode.fitness import get_fitness
from jesse.routes import router
from jesse.services.progressbar import Progressbar
from jesse.services.redis import is_process_active
from jesse.models.OptimizationSession import update_optimization_session_status, update_optimization_session_trials, get_optimization_session, get_optimization_session_by_id
import traceback

# Define a Ray-compatible remote function


@ray.remote
def ray_evaluate_trial(
    user_config,
    formatted_routes,
    formatted_data_routes,
    strategy_hp,
    hp,
    training_warmup_candles,
    training_candles,
    testing_warmup_candles,
    testing_candles,
    optimal_total,
    fast_mode,
    trial_number
):
    """Ray remote function to evaluate a trial"""
    try:
        # Calculate the fitness score using the provided hyperparameters
        score, training_metrics, testing_metrics = get_fitness(
            user_config,
            formatted_routes,
            formatted_data_routes,
            strategy_hp,
            hp,
            training_warmup_candles,
            training_candles,
            testing_warmup_candles,
            testing_candles,
            optimal_total,
            fast_mode
        )

        # Log the trial details if debugging is enabled
        if jh.is_debugging():
            logger.log_optimize_mode(f"Ray Trial {trial_number}: Score={score}, Params={hp}")

        return {
            'trial_number': trial_number,
            'score': score,
            'params': hp,
            'training_metrics': training_metrics,
            'testing_metrics': testing_metrics
        }
    except exceptions.RouteNotFound as e:
        # Convert RouteNotFound to a standard RuntimeError to avoid serialization issues
        error_msg = str(e)
        logger.log_optimize_mode(f"Ray Trial {trial_number} failed with RouteNotFound: {error_msg}")
        logger.log_optimize_mode(f"Trial {trial_number} hyperparameters: {hp}")
        raise RuntimeError(f"RouteNotFound: {error_msg}")
    except Exception as e:
        # Log and re-raise other exceptions
        logger.log_optimize_mode(f"Ray Trial {trial_number} failed with exception: {str(e)}")
        raise

# Optimizer class that uses Ray for hyperparameter optimization


class Optimizer:
    def __init__(
            self,
            session_id: str,
            user_config: dict,
            training_warmup_candles: dict,
            training_candles: dict,
            testing_warmup_candles: dict,
            testing_candles: dict,
            fast_mode: bool,
            optimal_total: int,
            cpu_cores: int,
    ) -> None:
        # Check for Python 3.13 first thing
        if jh.python_version() == (3, 13):
            raise ValueError(
                'Optimization is not supported on Python 3.13. The Ray library used for optimization does not support Python 3.13 yet. Please use Python 3.12 or lower.')

        self.session_id = session_id

        # Retrieve the target strategy and its hyperparameter configuration
        strategy_class = jh.get_strategy_class(router.routes[0].strategy_name)

        self.strategy_hp = strategy_class.hyperparameters(None)

        if not self.strategy_hp:
            update_optimization_session_status(self.session_id, 'stopped')
            raise exceptions.InvalidStrategy('Targeted strategy does not implement a valid hyperparameters() method.')

        # Create study storage for persistence
        os.makedirs('./storage/temp/optuna', exist_ok=True)
        self.storage_url = f"sqlite:///./storage/temp/optuna/optuna_study.db"
        # The study_name uniquely identifies the optimization session - changing it will create a new session
        self.study_name = f"{router.routes[0].strategy_name}_optuna_ray_{self.session_id}"

        self.solution_len = len(self.strategy_hp)
        self.start_time = jh.now_to_timestamp()
        self.fast_mode = fast_mode
        self.optimal_total = optimal_total
        self.training_warmup_candles = training_warmup_candles
        self.training_candles = training_candles
        self.testing_warmup_candles = testing_warmup_candles
        self.testing_candles = testing_candles
        self.user_config = user_config

        # Validate and set the number of CPU cores to use
        if cpu_cores < 1:
            raise ValueError('cpu_cores must be an integer value greater than 0.')
        available = cpu_count()
        self.cpu_cores = cpu_cores if cpu_cores <= available else available

        # Get number of trials from settings
        self.n_trials = self.solution_len * jh.get_config('env.optimization.trials', 200)

        # Create a progress bar instance to update the front end about optimization progress
        self.progressbar = Progressbar(self.n_trials)

        # Initialize best trials tracking
        self.best_trials = []

        # Trial counter and completed trials
        self.trial_counter = 0
        self.completed_trials = 0

        # Create or load the Optuna study for persistence
        self.study = optuna.create_study(
            direction='maximize',
            storage=self.storage_url,
            study_name=self.study_name,
            load_if_exists=True
        )

        # Buffer to accumulate objective curve data points (one point per trial)
        self.objective_curve_buffer = []
        self.total_objective_curve_buffer = []

        # Initialize Ray if not already
        if not ray.is_initialized():
            try:
                ray.init(num_cpus=self.cpu_cores, ignore_reinit_error=True)
                logger.log_optimize_mode(f"Successfully started optimization session with {self.cpu_cores} CPU cores")
            except Exception as e:
                logger.log_optimize_mode(f"Error initializing Ray: {e}. Falling back to 1 CPU.")
                self.cpu_cores = 1
                ray.init(num_cpus=1, ignore_reinit_error=True)

        # Setup a periodic termination check in case the user ends the session
        client_id = jh.get_session_id()
        from timeloop import Timeloop
        self.tl = Timeloop()

        @self.tl.job(interval=timedelta(seconds=1))
        def check_for_termination():
            if is_process_active(client_id) is False:
                # Update session status to 'stopped' in the database
                if get_optimization_session(self.session_id)['status'] != 'terminated':
                    update_optimization_session_status(self.session_id, 'stopped')
                raise exceptions.Termination
        self.tl.start()

        # Load existing trials from the Optuna study
        self._load_study_trials()

    def _load_study_trials(self):
        """Load trials from the database session"""
        session_data = get_optimization_session_by_id(self.session_id)

        def replace_inf_with_null(obj):
            if isinstance(obj, dict):
                return {k: replace_inf_with_null(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [replace_inf_with_null(item) for item in obj]
            elif isinstance(obj, float) and (obj == float('inf') or obj == float('-inf')):
                return None
            return obj
        try:
            # Get completed trials from the Optuna study
            completed_trials = session_data.completed_trials
            if not completed_trials:
                logger.log_optimize_mode("No previous trials found. Starting new optimization session.")
                return

            # Update completed trials count
            self.completed_trials = completed_trials
            logger.log_optimize_mode(f"Loaded {self.completed_trials} completed trials from previous session")
            self.best_trials = replace_inf_with_null(json.loads(session_data.best_trials))
            # Update best candidates display
            self._update_best_candidates()

            # Update progress bar efficiently
            self._set_progressbar_index(self.completed_trials)

            # Set trial counter to start from after the last trial
            self.trial_counter = completed_trials

            self.total_objective_curve_buffer = json.loads(session_data.objective_curve.replace('-Infinity', 'null').replace('Infinity', 'null'))
            # Update the database with loaded trials
            update_optimization_session_trials(
                self.session_id,
                self.completed_trials,
                self.best_trials,
                self.total_objective_curve_buffer,
                self.n_trials
            )

        except Exception as e:
            logger.log_optimize_mode(f"Error loading previous trials: {e}")
            # Reset counters in case of failure
            self.completed_trials = 0
            self.trial_counter = 0

    def _generate_trial_params(self):
        """Generate random hyperparameters for a trial"""
        hp = {}
        for param in self.strategy_hp:
            param_name = str(param['name'])
            param_type = param['type']
            # Convert to string whether input is type class or string
            if isinstance(param_type, type):
                param_type = param_type.__name__
            else:
                # Remove quotes if they exist
                param_type = param_type.strip("'").strip('"')

            if param_type == 'int':
                if 'step' in param and param['step'] is not None:
                    steps = (param['max'] - param['min']) // param['step'] + 1
                    value = param['min'] + np.random.randint(0, steps) * param['step']
                else:
                    value = np.random.randint(param['min'], param['max'] + 1)
                hp[param_name] = value
            elif param_type == 'float':
                if 'step' in param and param['step'] is not None:
                    steps = int((param['max'] - param['min']) / param['step']) + 1
                    value = param['min'] + np.random.randint(0, steps) * param['step']
                else:
                    value = np.random.uniform(param['min'], param['max'])
                hp[param_name] = value
            elif param_type == 'categorical':
                options = param['options']
                hp[param_name] = options[np.random.randint(0, len(options))]
            else:
                raise ValueError(f"Unsupported hyperparameter type: {param_type}")

        return hp

    def _create_optuna_trial(self, trial_number, params, score, training_metrics, testing_metrics):
        """Create and store an Optuna trial for persistence"""
        try:
            # Create distributions for the parameters
            distributions = {}
            for param in self.strategy_hp:
                param_name = str(param['name'])
                param_type = param['type']
                if isinstance(param_type, type):
                    param_type = param_type.__name__
                else:
                    param_type = param_type.strip("'").strip('"')

                if param_type == 'int':
                    if 'step' in param and param['step'] is not None:
                        distributions[param_name] = optuna.distributions.IntDistribution(
                            low=param['min'],
                            high=param['max'],
                            step=param['step']
                        )
                    else:
                        distributions[param_name] = optuna.distributions.IntDistribution(
                            low=param['min'],
                            high=param['max']
                        )
                elif param_type == 'float':
                    if 'step' in param and param['step'] is not None:
                        distributions[param_name] = optuna.distributions.FloatDistribution(
                            low=param['min'],
                            high=param['max'],
                            step=param['step']
                        )
                    else:
                        distributions[param_name] = optuna.distributions.FloatDistribution(
                            low=param['min'],
                            high=param['max']
                        )
                elif param_type == 'categorical':
                    distributions[param_name] = optuna.distributions.CategoricalDistribution(param['options'])

            # Create a new trial
            trial = optuna.create_trial(
                params=params,
                distributions=distributions,
                value=score,
                user_attrs={
                    'training_metrics': training_metrics,
                    'testing_metrics': testing_metrics
                }
            )

            # Add the trial to the study
            self.study.add_trial(trial)
            return True

        except Exception as e:
            logger.log_optimize_mode(f"Error creating Optuna trial: {e}")
            return False

    def _process_trial_result(self, result):
        """Process the result of a completed trial"""
        trial_number = result['trial_number']
        score = result['score']
        params = result['params']
        training_metrics = result['training_metrics']
        testing_metrics = result['testing_metrics']

        # Update progress
        self.completed_trials += 1
        self.progressbar.update()

        # Store trial in Optuna for persistence
        self._create_optuna_trial(trial_number, params, score, training_metrics, testing_metrics)

        # Update the dashboard with general information about the progress
        general_info = {
            'started_at': jh.timestamp_to_arrow(self.start_time).humanize(),
            'trial': f'{self.completed_trials}/{self.n_trials}',
            'objective_function': jh.get_config('env.optimization.objective_function', 'sharpe'),
            'exchange_type': self.user_config['exchange']['type'],
            'leverage_mode': self.user_config['exchange']['futures_leverage_mode'],
            'leverage': self.user_config['exchange']['futures_leverage'],
            'cpu_cores': self.cpu_cores,
        }
        sync_publish('general_info', general_info)

        # Update the progress bar and publish the current progress to the dashboard
        sync_publish('progressbar', {
            'current': self.progressbar.current,
            'estimated_remaining_seconds': self.progressbar.estimated_remaining_seconds
        })

        # Process trial metrics for objective curve
        self._process_trial_metrics(trial_number, training_metrics, testing_metrics)

        # Add to best trials if the score is valid
        if score > 0.0001:
            # Convert parameters to DNA (base64)
            params_str = json.dumps(params, sort_keys=True)
            dna = base64.b64encode(params_str.encode()).decode()

            # Create trial info dict
            current_trial_info = {
                'trial': trial_number,
                'params': params,
                'fitness': round(score, 4),
                'value': score,  # Used for sorting, not sent to frontend
                'dna': dna,
                'training_metrics': training_metrics,
                'testing_metrics': testing_metrics
            }

            # Debug log trial metrics
            if jh.is_debugging():
                jh.debug(f"Trial {trial_number} processed - fitness: {score}")
                jh.debug(f"Trial {trial_number} has training metrics: {bool(training_metrics)}")
                jh.debug(f"Trial {trial_number} has testing metrics: {bool(testing_metrics)}")

            # Insert into best_trials maintaining sorted order
            insert_idx = 0
            for idx, t in enumerate(self.best_trials):
                if score > t['value']:
                    insert_idx = idx
                    break
                else:
                    insert_idx = idx + 1

            if insert_idx < 20 or len(self.best_trials) < 20:
                self.best_trials.insert(insert_idx, current_trial_info)
                # Keep only top 20
                self.best_trials = self.best_trials[:20]

            # Update best candidates table
            self._update_best_candidates()

            # Update the database with the latest trials data
            # We do this every 5 trials to avoid too many database writes
            if self.completed_trials % 5 == 0:

                update_optimization_session_trials(
                    self.session_id,
                    self.completed_trials,
                    self.best_trials,
                    self.total_objective_curve_buffer,
                    self.n_trials
                )

    def _update_best_candidates(self):
        """Update the best candidates table in the dashboard"""
        # Get the objective function configuration
        objective_function_config = jh.get_config('env.optimization.objective_function', 'sharpe').lower()
        mapping = {
            'sharpe': 'sharpe_ratio',
            'calmar': 'calmar_ratio',
            'sortino': 'sortino_ratio',
            'omega': 'omega_ratio',
            'serenity': 'serenity_index',
            'smart sharpe': 'smart_sharpe',
            'smart sortino': 'smart_sortino'
        }
        metric_key = mapping.get(objective_function_config, objective_function_config)

        best_candidates = []
        for idx, t in enumerate(self.best_trials):
            train_value = t.get('training_metrics', {}).get(metric_key, None)
            test_value = t.get('testing_metrics', {}).get(metric_key, None)
            if isinstance(train_value, (int, float)):
                train_value = round(train_value, 2)
            if isinstance(test_value, (int, float)):
                test_value = round(test_value, 2)
            if train_value is None:
                train_value = "N/A"
            if test_value is None:
                test_value = "N/A"

            candidate_objective_metric = f"{train_value} / {test_value}"

            best_candidates.append({
                'rank': f"#{idx + 1}",
                'trial': f"Trial {t['trial']}",
                'params': t['params'],
                'fitness': t['fitness'],
                'dna': t['dna'],
                'training_metrics': t.get('training_metrics', {}),
                'testing_metrics': t.get('testing_metrics', {}),
                'objective_metric': candidate_objective_metric
            })

        # Send top candidates to the dashboard
        sync_publish('best_candidates', best_candidates)

    def _process_trial_metrics(self, trial_number, training_metrics, testing_metrics):
        """Process metrics from a completed trial to update objective curve"""
        # Only add to buffer if both metrics exist and are not empty
        if training_metrics and testing_metrics:
            data_point = {
                'trial': trial_number + 1,
                'training': training_metrics,
                'testing': testing_metrics
            }
            self.objective_curve_buffer.append(data_point)

            if jh.is_debugging():
                jh.debug(f"Added trial {trial_number + 1} to objective curve buffer with metrics")
        else:
            if jh.is_debugging():
                jh.debug(f"Skipped trial {trial_number + 1} - missing metrics. Training: {bool(training_metrics)}, Testing: {bool(testing_metrics)}")

        # Publish a batch every 5 trials or when buffer reaches 10 items
        buffer_size = len(self.objective_curve_buffer)
        if buffer_size >= 10 or (buffer_size > 0 and self.completed_trials % 5 == 0):
            if jh.is_debugging():
                jh.debug(f"Publishing objective curve LEN: {len(self.objective_curve_buffer)}")
            sync_publish('objective_curve', self.objective_curve_buffer)

            if len(self.objective_curve_buffer) > 0 and len(self.total_objective_curve_buffer) > 0:
                if self.objective_curve_buffer[0]['trial'] > self.total_objective_curve_buffer[-1]['trial']:
                    self.total_objective_curve_buffer.extend(self.objective_curve_buffer)
            else:
                self.total_objective_curve_buffer.extend(self.objective_curve_buffer)

            self.objective_curve_buffer = []

    def _set_progressbar_index(self, index):
        """Manually set the progressbar index for resuming sessions efficiently"""
        self.progressbar.index = index
        # Update UI to reflect progress
        sync_publish('progressbar', {
            'current': self.progressbar.current,
            'estimated_remaining_seconds': self.progressbar.estimated_remaining_seconds
        })

    def run(self) -> optuna.trial.FrozenTrial:
        # Log the start of the optimization session
        logger.log_optimize_mode(f"Optimization session started with {self.cpu_cores} CPU cores")

        if self.completed_trials > 0:
            logger.log_optimize_mode(f"Resuming from previous session with {self.completed_trials} trials already completed")
            # Make sure the progress bar is synchronized
            self._set_progressbar_index(self.completed_trials)

        # Track the best trial - handle empty study gracefully
        try:
            best_trial_value = self.study.best_value if self.study.trials else 0.0
            best_trial_params = self.study.best_params if self.study.trials else None
        except (ValueError, AttributeError) as e:
            logger.log_optimize_mode(f"Could not access best trial: {e}. Using default values.")
            best_trial_value = 0.0
            best_trial_params = None

        try:
            # Maximum number of active workers (slightly higher than CPU cores to keep CPUs busy)
            max_workers = min(self.cpu_cores * 2, self.n_trials - self.completed_trials)

            # Dictionary to keep track of active workers
            active_refs = {}
            # Begin optimization loop
            while self.completed_trials < self.n_trials:
                if self.completed_trials == 0:
                    update_optimization_session_trials(
                        self.session_id,
                        0,
                        [],
                        [],
                        self.n_trials
                    )
                # Launch new trials if we have capacity
                while len(active_refs) < max_workers and self.trial_counter < self.n_trials:
                    # Generate parameters for this trial
                    hp = self._generate_trial_params()

                    # Launch the trial evaluation
                    ref = ray_evaluate_trial.options(num_cpus=1).remote(
                        self.user_config,
                        router.formatted_routes,
                        router.formatted_data_routes,
                        self.strategy_hp,
                        hp,
                        self.training_warmup_candles,
                        self.training_candles,
                        self.testing_warmup_candles,
                        self.testing_candles,
                        self.optimal_total,
                        self.fast_mode,
                        self.trial_counter
                    )

                    # Store the reference
                    active_refs[ref] = self.trial_counter
                    self.trial_counter += 1

                # No more workers to launch, wait for results
                if not active_refs:
                    break

                # Wait for any trial to complete (with timeout to ensure responsiveness)
                done_refs, _ = ray.wait(list(active_refs.keys()), num_returns=1, timeout=0.5)

                # Process completed trials
                for ref in done_refs:
                    trial_number = active_refs.pop(ref)
                    try:
                        result = ray.get(ref)
                        # Process the result
                        self._process_trial_result(result)

                        # Update best trial if better
                        if result['score'] > best_trial_value:
                            best_trial_value = result['score']
                            best_trial_params = result['params']
                    except ray.exceptions.RayTaskError as e:
                        # Check if this is a RouteNotFound error converted to RuntimeError
                        if hasattr(e, 'cause') and isinstance(e.cause, RuntimeError) and 'RouteNotFound:' in str(e.cause):
                            raise e.cause
                        else:
                            jh.debug(f'Ray task error for trial {trial_number}: {e}')
                            original_exception = e.cause
                            raise
                    except Exception as e:
                        jh.debug(f'Exception raised in the ray method for trial {trial_number}: {e}')
                        raise e

            # Publish any remaining data in the buffer
            if self.objective_curve_buffer:
                jh.debug(f"Publishing remaining {len(self.objective_curve_buffer)} data points in buffer")
                sync_publish('objective_curve', self.objective_curve_buffer)
                self.objective_curve_buffer = []

            # Get the best trial from the study
            try:
                best_trial = self.study.best_trial
            except (ValueError, AttributeError) as e:
                logger.log_optimize_mode(f"Could not access best trial at the end: {e}")
                # Create a dummy trial if no best trial exists
                best_trial = None

            # Update the database with final results
            update_optimization_session_trials(
                self.session_id,
                self.completed_trials,
                self.best_trials,
                self.total_objective_curve_buffer,
                self.n_trials
            )

            # Update session status to 'finished'
            update_optimization_session_status(self.session_id, 'finished')

            # Publish completion alert
            sync_publish('alert', {
                'message': f"Finished {self.n_trials} trials. Check the \"Best Trials\" table for the best performing parameters.",
                'type': 'success'
            })

        except exceptions.Termination:
            # Handle user-initiated termination
            logger.log_optimize_mode("Optimization terminated by user")
            # Update session status to 'stopped'
            update_optimization_session_status(self.session_id, 'stopped')
            raise
        except Exception as e:
            logger.log_optimize_mode(f"Error during optimization: {e}")
            # Update session status to 'stopped' due to error
            update_optimization_session_status(self.session_id, 'stopped')
            from jesse.models.OptimizationSession import add_session_exception
            add_session_exception(self.session_id, str(e), str(traceback.format_exc()))
            raise
        finally:
            # Shutdown Ray
            ray.shutdown()

        # Create an empty FrozenTrial if best_trial is None
        if best_trial is None:
            logger.log_optimize_mode("No best trial found. Returning empty result.")
            from optuna.trial import FrozenTrial
            return FrozenTrial(
                number=0,
                trial_id=0,
                state=optuna.trial.TrialState.COMPLETE,
                value=0.0,
                datetime_start=None,
                datetime_complete=None,
                params={},
                distributions={},
                user_attrs={},
                system_attrs={},
                intermediate_values={},
            )
        return best_trial
