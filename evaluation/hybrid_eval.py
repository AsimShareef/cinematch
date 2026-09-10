"""
End-to-end benchmark of the actual hybrid recommendation pipeline (collaborative
filtering + content-based + semantic + MMR diversity), not just the raw SVD
component in isolation.

Since the hybrid pipeline (`app.blueprints.recommendations._generate_recommendations`)
operates on real app Users/Ratings in the database, this simulates real users by
temporarily inserting synthetic User + Rating rows built from a sample of MovieLens
test users (mapped into our TMDb-synced catalog via the crosswalk), calls the exact
same production code path a live request would hit, scores it against each user's
held-out ratings, then deletes the synthetic rows again - even on failure.
"""
import numpy as np
import pandas as pd
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import db
from app.models import User, Movie, Rating
from ml.train_svd import load_ratings_dataframe
from ml.experiment_tracker import ExperimentTracker
from evaluation.offline_eval import (
    leave_last_n_out_split, score_ranking, TOP_K, RELEVANCE_THRESHOLD,
)

SAMPLE_USERS = 300
RANDOM_SEED = 42
SYNTHETIC_EMAIL_DOMAIN = "eval.local"


def build_ml_to_db_map(movielens_dir: str) -> dict:
    crosswalk = pd.read_csv(f"{movielens_dir}/ml_to_tmdb_map.csv")
    ml_to_tmdb = dict(zip(crosswalk['ml_movie_id'], crosswalk['tmdb_id']))

    tmdb_to_db = dict(Movie.query.with_entities(Movie.tmdb_id, Movie.id).all())

    ml_to_db = {}
    for ml_id, tmdb_id in ml_to_tmdb.items():
        db_id = tmdb_to_db.get(tmdb_id)
        if db_id is not None:
            ml_to_db[ml_id] = db_id
    return ml_to_db


def purge_leftover_synthetic_users():
    """Safety net in case a previous run crashed before its own cleanup ran."""
    stray = User.query.filter(User.email.like(f"%@{SYNTHETIC_EMAIL_DOMAIN}")).all()
    if stray:
        for u in stray:
            db.session.delete(u)
        db.session.commit()
        print(f"Purged {len(stray)} leftover synthetic users from a previous run.")


def evaluate_pipeline(generate_fn, sample_ids, train_df, test_df, ml_to_db, use_hybrid: bool):
    """Shared driver for both the hybrid pipeline and the popularity baseline,
    scored over the identical sample of users for a fair comparison.
    `generate_fn(user_id_or_none, seen_db_ids) -> ranked list of DB movie ids`."""
    precisions, ndcgs = [], []
    created_user_ids = []

    try:
        for ml_user_id in sample_ids:
            train_ratings = train_df[train_df['user_id'] == ml_user_id]
            test_group = test_df[test_df['user_id'] == ml_user_id]

            db_ratings = [
                (ml_to_db[row.movie_id], float(row.rating))
                for row in train_ratings.itertuples()
                if row.movie_id in ml_to_db
            ]
            relevance_map = {
                ml_to_db[row.movie_id]: row.rating
                for row in test_group.itertuples()
                if row.movie_id in ml_to_db
            }
            if not db_ratings or not relevance_map:
                continue

            seen_db_ids = {mid for mid, _ in db_ratings}

            if use_hybrid:
                user = User(
                    username=f"eval_user_{ml_user_id}",
                    email=f"eval-{ml_user_id}@{SYNTHETIC_EMAIL_DOMAIN}",
                    password_hash=generate_password_hash("evaluation-only"),
                )
                db.session.add(user)
                db.session.flush()
                created_user_ids.append(user.id)

                for movie_id, score in db_ratings:
                    db.session.add(Rating(user_id=user.id, movie_id=movie_id, score=score))
                user.update_cold_start_alpha()
                db.session.flush()

                ranked_ids = generate_fn(user.id)
            else:
                ranked_ids = generate_fn(seen_db_ids)

            precision, ndcg = score_ranking(ranked_ids, set(), relevance_map, k=TOP_K)
            precisions.append(precision)
            ndcgs.append(ndcg)
    finally:
        # Bulk Query.delete() bypasses the ORM cascade, so Ratings must be
        # dropped explicitly before their (synthetic) User rows.
        if created_user_ids:
            Rating.query.filter(Rating.user_id.in_(created_user_ids)).delete(synchronize_session=False)
            User.query.filter(User.id.in_(created_user_ids)).delete(synchronize_session=False)
            db.session.commit()

    return {
        "precision_at_10": float(np.mean(precisions)) if precisions else 0.0,
        "ndcg_at_10": float(np.mean(ndcgs)) if ndcgs else 0.0,
        "n_test_users": len(precisions),
    }


def main():
    from app.blueprints.recommendations import _generate_recommendations

    app = create_app()
    with app.app_context():
        purge_leftover_synthetic_users()

        movielens_dir = app.config['MOVIELENS_DATA_PATH']

        print("Loading ratings and building leave-last-N-out split...")
        df = load_ratings_dataframe(movielens_dir)
        train_df, test_df = leave_last_n_out_split(df)

        ml_to_db = build_ml_to_db_map(movielens_dir)
        print(f"{len(ml_to_db)} MovieLens movies are present in our TMDb-synced catalog.")

        popularity_ranking_ml = (
            train_df.groupby('movie_id').size().sort_values(ascending=False).index.tolist()
        )
        popularity_ranking_db = [ml_to_db[m] for m in popularity_ranking_ml if m in ml_to_db]

        test_user_ids = test_df['user_id'].unique()
        rng = np.random.default_rng(RANDOM_SEED)
        sample_ids = rng.choice(test_user_ids, size=min(SAMPLE_USERS, len(test_user_ids)), replace=False)
        print(f"Evaluating on a sample of {len(sample_ids)} test users "
              "(full hybrid pipeline is too slow to run over all 6,040).")

        print("\nScoring popularity baseline (same sample, same catalog)...")

        def popularity_fn(seen_db_ids):
            return [m for m in popularity_ranking_db if m not in seen_db_ids][:TOP_K]

        baseline_metrics = evaluate_pipeline(
            popularity_fn, sample_ids, train_df, test_df, ml_to_db, use_hybrid=False
        )

        print("Scoring hybrid pipeline WITH MMR diversity (collaborative + content + MMR)...")
        print("This creates temporary synthetic users, runs the real recommendation "
              "endpoint's logic, then deletes them again.")

        def hybrid_mmr_fn(user_id):
            results = _generate_recommendations(
                user_id, top_k=TOP_K, query_text=None, mood_text=None, diversify=True
            )
            return [r['movie_id'] for r in results]

        hybrid_mmr_metrics = evaluate_pipeline(
            hybrid_mmr_fn, sample_ids, train_df, test_df, ml_to_db, use_hybrid=True
        )

        print("Scoring hybrid pipeline WITHOUT MMR (pure relevance ranking, same candidates)...")

        def hybrid_no_mmr_fn(user_id):
            results = _generate_recommendations(
                user_id, top_k=TOP_K, query_text=None, mood_text=None, diversify=False
            )
            return [r['movie_id'] for r in results]

        hybrid_no_mmr_metrics = evaluate_pipeline(
            hybrid_no_mmr_fn, sample_ids, train_df, test_df, ml_to_db, use_hybrid=True
        )

        def lift(a, b):
            return (a / b) if b > 0 else float('inf')

        mmr_precision_lift = lift(hybrid_mmr_metrics['precision_at_10'], baseline_metrics['precision_at_10'])
        mmr_ndcg_lift = lift(hybrid_mmr_metrics['ndcg_at_10'], baseline_metrics['ndcg_at_10'])
        no_mmr_precision_lift = lift(hybrid_no_mmr_metrics['precision_at_10'], baseline_metrics['precision_at_10'])
        no_mmr_ndcg_lift = lift(hybrid_no_mmr_metrics['ndcg_at_10'], baseline_metrics['ndcg_at_10'])

        # How much accuracy MMR's diversity reranking costs, in isolation
        mmr_precision_cost = lift(hybrid_no_mmr_metrics['precision_at_10'], hybrid_mmr_metrics['precision_at_10'])
        mmr_ndcg_cost = lift(hybrid_no_mmr_metrics['ndcg_at_10'], hybrid_mmr_metrics['ndcg_at_10'])

        print(f"\n{'Metric':<22}{'Popularity':>12}{'Hybrid+MMR':>12}{'Hybrid noMMR':>14}")
        print(f"{'Precision@' + str(TOP_K):<22}{baseline_metrics['precision_at_10']:>12.4f}"
              f"{hybrid_mmr_metrics['precision_at_10']:>12.4f}{hybrid_no_mmr_metrics['precision_at_10']:>14.4f}")
        print(f"{'NDCG@' + str(TOP_K):<22}{baseline_metrics['ndcg_at_10']:>12.4f}"
              f"{hybrid_mmr_metrics['ndcg_at_10']:>12.4f}{hybrid_no_mmr_metrics['ndcg_at_10']:>14.4f}")

        print(f"\nHybrid+MMR   vs popularity: {mmr_precision_lift:.2f}x precision, {mmr_ndcg_lift:.2f}x NDCG")
        print(f"Hybrid noMMR vs popularity: {no_mmr_precision_lift:.2f}x precision, {no_mmr_ndcg_lift:.2f}x NDCG")
        print(f"MMR diversity 'cost' (noMMR / withMMR): "
              f"{mmr_precision_cost:.2f}x precision, {mmr_ndcg_cost:.2f}x NDCG")
        print(f"\nEvaluated over {hybrid_mmr_metrics['n_test_users']} users "
              f"(sampled {len(sample_ids)}, {hybrid_mmr_metrics['n_test_users']} had mappable ratings).")

        tracker = ExperimentTracker(tracking_uri=app.config.get('MLFLOW_TRACKING_URI'))
        with tracker.run(run_name="hybrid_offline_eval"):
            tracker.log_params({
                "sample_users": SAMPLE_USERS,
                "top_k": TOP_K,
                "relevance_threshold": RELEVANCE_THRESHOLD,
                "random_seed": RANDOM_SEED,
            })
            tracker.log_metrics({
                "baseline_precision_at_10": baseline_metrics['precision_at_10'],
                "baseline_ndcg_at_10": baseline_metrics['ndcg_at_10'],
                "hybrid_mmr_precision_at_10": hybrid_mmr_metrics['precision_at_10'],
                "hybrid_mmr_ndcg_at_10": hybrid_mmr_metrics['ndcg_at_10'],
                "hybrid_no_mmr_precision_at_10": hybrid_no_mmr_metrics['precision_at_10'],
                "hybrid_no_mmr_ndcg_at_10": hybrid_no_mmr_metrics['ndcg_at_10'],
                "mmr_precision_lift_vs_popularity": mmr_precision_lift,
                "mmr_ndcg_lift_vs_popularity": mmr_ndcg_lift,
                "no_mmr_precision_lift_vs_popularity": no_mmr_precision_lift,
                "no_mmr_ndcg_lift_vs_popularity": no_mmr_ndcg_lift,
                "mmr_precision_cost_ratio": mmr_precision_cost,
                "mmr_ndcg_cost_ratio": mmr_ndcg_cost,
                "n_test_users": hybrid_mmr_metrics['n_test_users'],
            })


if __name__ == '__main__':
    main()
