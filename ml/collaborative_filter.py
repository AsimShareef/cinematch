import os
import joblib
import numpy as np
import pandas as pd
from app.models import Movie, Rating

# Module-level singletons so the model/crosswalk are loaded once per process
_model_instance = None
_ml_to_tmdb_instance = None
_tmdb_to_ml_instance = None


class CollaborativeFilterService:
    """
    Serves recommendations from the SVD model trained in ml/train_svd.py.

    MovieLens's ~6,040 training users are not the app's real users, so instead of
    looking up a user by id in the trained model, we "fold in" a real user's ratings:
    given the item factors/biases the model already learned, solve (via ridge
    regression - one ALS step) for the latent vector that best explains that user's
    known ratings, then score every item against it.
    """

    def __init__(self, model_path: str, movielens_dir: str):
        global _model_instance, _ml_to_tmdb_instance, _tmdb_to_ml_instance

        if _model_instance is None:
            if not os.path.exists(model_path) or os.path.getsize(model_path) == 0:
                raise FileNotFoundError(
                    f"SVD model not found at {model_path}. Run ml/train_svd.py first."
                )
            _model_instance = joblib.load(model_path)

        if _ml_to_tmdb_instance is None:
            crosswalk_path = os.path.join(movielens_dir, 'ml_to_tmdb_map.csv')
            crosswalk = pd.read_csv(crosswalk_path)
            _ml_to_tmdb_instance = dict(zip(crosswalk['ml_movie_id'], crosswalk['tmdb_id']))
            _tmdb_to_ml_instance = dict(zip(crosswalk['tmdb_id'], crosswalk['ml_movie_id']))

        self.model = _model_instance
        self.ml_to_tmdb = _ml_to_tmdb_instance
        self.tmdb_to_ml = _tmdb_to_ml_instance

        self._db_id_to_ml_id = None
        self._ml_id_to_db_id = None

    def _build_db_mapping(self):
        """Lazily builds Movie.id <-> ml_movie_id, joined through tmdb_id."""
        if self._db_id_to_ml_id is not None:
            return

        rows = Movie.query.with_entities(Movie.id, Movie.tmdb_id).all()
        self._db_id_to_ml_id = {}
        self._ml_id_to_db_id = {}
        for db_id, tmdb_id in rows:
            ml_id = self.tmdb_to_ml.get(tmdb_id)
            if ml_id is not None:
                self._db_id_to_ml_id[db_id] = ml_id
                self._ml_id_to_db_id[ml_id] = db_id

    def _fold_in_user_vector(self, ml_ratings: dict, reg: float = 0.1):
        trainset = self.model.trainset
        n_factors = self.model.n_factors

        rows, targets = [], []
        for ml_movie_id, rating in ml_ratings.items():
            try:
                inner_iid = trainset.to_inner_iid(int(ml_movie_id))
            except ValueError:
                continue  # item wasn't present in the SVD training data
            rows.append(self.model.qi[inner_iid])
            targets.append(rating - trainset.global_mean - self.model.bi[inner_iid])

        if not rows:
            return None

        Q = np.vstack(rows)
        y = np.array(targets)

        # Ridge regression closed form: p_u = (Q^T Q + reg * I)^-1 Q^T y
        A = Q.T @ Q + reg * np.eye(n_factors)
        b = Q.T @ y
        return np.linalg.solve(A, b)

    def recommend_for_user(self, user_id: int, top_k: int = 50) -> list[dict]:
        self._build_db_mapping()

        user_ratings = Rating.query.filter_by(user_id=user_id).all()
        ml_ratings = {}
        rated_db_ids = set()
        for r in user_ratings:
            ml_id = self._db_id_to_ml_id.get(r.movie_id)
            if ml_id is not None:
                ml_ratings[ml_id] = r.score
                rated_db_ids.add(r.movie_id)

        if not ml_ratings:
            return []

        p_u = self._fold_in_user_vector(ml_ratings)
        if p_u is None:
            return []

        trainset = self.model.trainset
        scores = trainset.global_mean + self.model.bi + (self.model.qi @ p_u)

        results = []
        for inner_iid, score in enumerate(scores):
            ml_movie_id = trainset.to_raw_iid(inner_iid)
            db_id = self._ml_id_to_db_id.get(ml_movie_id)
            if db_id is None or db_id in rated_db_ids:
                continue
            results.append({
                "movie_id": db_id,
                "score": float(score),
                "predicted_rating": float(score)
            })

        results.sort(key=lambda x: x['score'], reverse=True)
        return results[:top_k]
