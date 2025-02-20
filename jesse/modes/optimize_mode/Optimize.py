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
            score, training_metrics, testing_metrics = get_fitness(
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
            
            # Store logs in trial user attributes for later use in callback
            trial.set_user_attr('training_metrics', training_metrics)
            trial.set_user_attr('testing_metrics', testing_metrics)
            
        except Exception as e:
            logger.log_optimize_mode(f"Trial evaluation failed: {e}")
            score = 0.0001
            trial.set_user_attr('training_metrics', {})
            trial.set_user_attr('testing_metrics', {})

        # Update the dashboard with general information about the progress
        trial_number = trial.number + 1
        general_info = {
            'started_at': jh.timestamp_to_arrow(self.start_time).humanize(),
            'trial': f'{trial_number}/{self.n_trials}',
            'objective_function': jh.get_config('env.optimization.objective_function', 'sharpe'),
            'exchange_type': self.user_config['exchange']['type'],
            'leverage_mode': self.user_config['exchange']['futures_leverage_mode'],
            'leverage': self.user_config['exchange']['futures_leverage'],
            'cpu_cores': self.cpu_cores,
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
        # Get the current trial's value
        current_value = trial.value if trial.value is not None else float('-inf')
        
        # Initialize or get the cached best trials from study user attributes
        best_trials = study.user_attrs.get('best_trials', [])
        
        # Only process if the current trial is complete and has a value
        if trial.state == optuna.trial.TrialState.COMPLETE and current_value > float('-inf'):
            # Convert parameters to DNA (base64)
            import json
            import base64
            params_str = json.dumps(trial.params, sort_keys=True)
            dna = base64.b64encode(params_str.encode()).decode()
            
            # Create trial info dict
            current_trial_info = {
                'trial': trial.number,
                'params': trial.params,
                'fitness': round(current_value, 4),
                'value': current_value,  # Used for sorting, not sent to frontend
                'dna': dna,
                'training_metrics': trial.user_attrs.get('training_metrics', {}),
                'testing_metrics': trial.user_attrs.get('testing_metrics', {})
            }
            
            # Insert into best_trials maintaining sorted order
            insert_idx = 0
            for idx, t in enumerate(best_trials):
                if current_value > t['value']:
                    insert_idx = idx
                    break
                else:
                    insert_idx = idx + 1
            
            if insert_idx < 20:
                best_trials.insert(insert_idx, current_trial_info)
                # Keep only top 20
                best_trials = best_trials[:20]
                # Update cache in study user attributes
                study.set_user_attr('best_trials', best_trials)

        # Format for dashboard (exclude 'value' key used for sorting)
        best_candidates = []
        for idx, t in enumerate(best_trials):
            # Generate DNA for existing trials if they don't have it
            if 'dna' not in t:
                params_str = json.dumps(t['params'], sort_keys=True)
                t['dna'] = base64.b64encode(params_str.encode()).decode()
            
            best_candidates.append({
                'rank': f"#{idx + 1}",
                'trial': f"Trial {t['trial']}",
                'params': t['params'],
                'fitness': t['fitness'],
                'dna': t['dna'],
                'training_metrics': t.get('training_metrics', {}),
                'testing_metrics': t.get('testing_metrics', {})
            })
        
        jh.debug(f"best_candidates: {best_candidates}")
        
        # Send to dashboard
        sync_publish('best_candidates', best_candidates)
        
        # If a solution with a very high fitness score is reached, send an alert
        if study.best_trial.value and study.best_trial.value >= 1:
            sync_publish('alert', {
                'message': f'Fitness goal reached at trial {study.best_trial.number}',
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
            study_name=f"{router.routes[0].strategy_name}_optuna3",
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
