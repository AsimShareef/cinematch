from contextlib import contextmanager
import mlflow

DEFAULT_EXPERIMENT_NAME = "movie-rec-platform"


class ExperimentTracker:
    """Thin wrapper around MLflow for experiment tracking."""

    def __init__(self, tracking_uri: str = None, experiment_name: str = DEFAULT_EXPERIMENT_NAME):
        if tracking_uri:
            mlflow.set_tracking_uri(tracking_uri)
        mlflow.set_experiment(experiment_name)

    @contextmanager
    def run(self, run_name: str = None):
        with mlflow.start_run(run_name=run_name) as active_run:
            yield active_run

    def log_params(self, params: dict):
        mlflow.log_params(params)

    def log_metrics(self, metrics: dict, step: int = None):
        mlflow.log_metrics(metrics, step=step)

    def log_artifact(self, local_path: str):
        mlflow.log_artifact(local_path)
