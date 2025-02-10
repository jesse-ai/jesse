import os
from datetime import timedelta
from multiprocessing import cpu_count
import optuna
import jesse.helpers as jh
import jesse.services.logger as logger
from jesse import exceptions, sync_publish
from jesse.modes.optimize_mode.fitness import get_fitness
from jesse.routes import router
from jesse.services.progressbar import Progressbar
from jesse.services.redis import is_process_active
from jesse.store import store

# Optimizer class that uses Optuna for hyperparameter optimization
class Optimizer:
    def __init__(
            self,
            user_config: dict,
            training_warmup_candles: dict,
            training_candles: dict,
            testing_warmup_candles: dict,
            testing_candles: dict,
            fast_mode: bool,
            optimal_total: int,
            cpu_cores: int,
    ) -> None:
        # Retrieve the target strategy and its hyperparameter configuration
        strategy_class = jh.get_strategy_class(router.routes[0].strategy_name)
        
        self.strategy_hp = strategy_class.hyperparameters(None)
        
        if not self.strategy_hp:
            raise exceptions.InvalidStrategy('Targeted strategy does not implement a valid hyperparameters() method.')

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

        # Determine number of trials based on the number of hyperparameters
        self.n_trials = self.solution_len * 100
        
        # Create a progress bar instance to update the front end about optimization progress
        self.progressbar = Progressbar(self.n_trials)

        # Setup a periodic termination check in case the user ends the session
        client_id = jh.get_session_id()
        from timeloop import Timeloop
        self.tl = Timeloop()
        @self.tl.job(interval=timedelta(seconds=1))
        def check_for_termination():
            if is_process_active(client_id) is False:
                raise exceptions.Termination
        self.tl.start()

    def objective(self, trial: optuna.trial.Trial) -> float:
        # Build a hyperparameters dictionary using trial suggestions
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
                hp[param_name] = trial.suggest_int(
                    param_name, param['min'], param['max'], step=param.get('step', 1)
                )
            elif param_type == 'float':
                if 'step' in param and param['step'] is not None:
                    hp[param_name] = trial.suggest_float(
                        param_name, param['min'], param['max'], step=param['step']
                    )
                else:
                    hp[param_name] = trial.suggest_float(
                        param_name, param['min'], param['max']
                    )
            elif param_type == 'categorical':
                hp[param_name] = trial.suggest_categorical(param_name, param['options'])
            else:
                raise ValueError(f"Unsupported hyperparameter type: {param_type}")

        try:
            # Calculate the fitness score using the provided hyperparameters
            score, training_log, testing_log = get_fitness(
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
                self.fast_mode
            )
        except Exception as e:
            logger.log_optimize_mode(f"Trial evaluation failed: {e}")
            score = 0.0001
            training_log = {}
            testing_log = {}

        # Update the dashboard with general information about the progress
        trial_number = trial.number + 1
        general_info = {
            'started_at': jh.timestamp_to_arrow(self.start_time).humanize(),
            'trial': f'{trial_number}/{self.n_trials}',
        }
        sync_publish('general_info', general_info)

        # Update the progress bar and publish the current progress to the dashboard
        self.progressbar.update()
        sync_publish('progressbar', {
            'current': self.progressbar.current,
            'estimated_remaining_seconds': self.progressbar.estimated_remaining_seconds
        })

        # Log the trial details if debugging is enabled
        if jh.is_debugging():
            logger.log_optimize_mode(f"Trial {trial_number}: Score={score}, Params={hp}")

        return score

    def study_callback(self, study: optuna.study.Study, trial: optuna.trial.FrozenTrial) -> None:
        # Called after each trial to update the dashboard with the best candidate so far
        best_trial = study.best_trial
        best_candidate = {
            'trial': best_trial.number,
            'params': best_trial.params,
            'fitness': round(best_trial.value, 4) if best_trial.value is not None else None,
        }
        sync_publish('best_candidates', [best_candidate])
        # If a solution with a very high fitness score is reached, send an alert to the dashboard
        if best_trial.value and best_trial.value >= 1:
            sync_publish('alert', {
                'message': f'Fitness goal reached at trial {best_trial.number}',
                'type': 'success'
            })

    def run(self) -> optuna.trial.FrozenTrial:
        # Log the start of the optimization session
        logger.log_optimize_mode("Optimization session started with Optuna")
        
        # Create SQLite storage so that multiple processes can work concurrently on the study
        os.makedirs('./storage/temp/optuna', exist_ok=True)
        storage_url = "sqlite:///./storage/temp/optuna/optuna_study.db"
        
        # Create or load the study
        study = optuna.create_study(
            direction='maximize',
            storage=storage_url,
            study_name=f"{router.routes[0].strategy_name}_optuna",
            load_if_exists=True
        )
        # Run the optimization using multiple processes
        study.optimize(
            self.objective,
            n_trials=self.n_trials,
            n_jobs=self.cpu_cores,
            callbacks=[self.study_callback]
        )

        # Publish a completion alert to the dashboard
        sync_publish('alert', {
            'message': f"Finished {self.n_trials} trials. Check your best hyperparameter candidate.",
            'type': 'success'
        })

        return study.best_trial
