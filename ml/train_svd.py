import os
import joblib
import pandas as pd
from surprise import Dataset, Reader, SVD, accuracy
from surprise.model_selection import train_test_split

from app import create_app
from ml.experiment_tracker import ExperimentTracker

SVD_PARAMS = {
    "n_factors": 100,
    "n_epochs": 20,
    "lr_all": 0.005,
    "reg_all": 0.02,
    "random_state": 42,
}


def load_ratings_dataframe(movielens_dir: str) -> pd.DataFrame:
    ratings_path = os.path.join(movielens_dir, 'ratings.dat')
    return pd.read_csv(
        ratings_path,
        sep='::',
        engine='python',
        names=['user_id', 'movie_id', 'rating', 'timestamp'],
        encoding='latin-1',
    )


def build_surprise_dataset(df: pd.DataFrame) -> Dataset:
    reader = Reader(rating_scale=(1, 5))
    return Dataset.load_from_df(df[['user_id', 'movie_id', 'rating']], reader)


def train_svd_model(trainset, params: dict = None) -> SVD:
    """Trains and returns a fitted surprise SVD model on the given trainset."""
    model = SVD(**(params or SVD_PARAMS))
    model.fit(trainset)
    return model


def main():
    app = create_app()
    with app.app_context():
        movielens_dir = app.config['MOVIELENS_DATA_PATH']
        model_path = app.config['SVD_MODEL_PATH']
        artifacts_dir = os.path.dirname(model_path)

        print("Loading MovieLens 1M ratings...")
        df = load_ratings_dataframe(movielens_dir)
        print(f"Loaded {len(df)} ratings from {df['user_id'].nunique()} users, "
              f"{df['movie_id'].nunique()} movies.")

        data = build_surprise_dataset(df)

        tracker = ExperimentTracker(tracking_uri=app.config.get('MLFLOW_TRACKING_URI'))
        with tracker.run(run_name="svd_train"):
            tracker.log_params(SVD_PARAMS)
            tracker.log_params({"n_ratings": len(df)})

            # Held-out split purely to report generalization metrics
            trainset, testset = train_test_split(data, test_size=0.2, random_state=42)
            eval_model = train_svd_model(trainset)
            predictions = eval_model.test(testset)

            rmse = accuracy.rmse(predictions, verbose=False)
            mae = accuracy.mae(predictions, verbose=False)
            print(f"Held-out RMSE: {rmse:.4f}, MAE: {mae:.4f}")
            tracker.log_metrics({"rmse": rmse, "mae": mae})

            # Refit on the full dataset to produce the model the app actually serves
            print("Refitting on full dataset for the production model...")
            full_trainset = data.build_full_trainset()
            final_model = train_svd_model(full_trainset)

            os.makedirs(artifacts_dir, exist_ok=True)
            joblib.dump(final_model, model_path)
            print(f"Saved SVD model to {model_path}")
            tracker.log_artifact(model_path)


if __name__ == '__main__':
    main()
