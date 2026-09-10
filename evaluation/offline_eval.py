import numpy as np
import pandas as pd

from app import create_app
from ml.train_svd import load_ratings_dataframe, build_surprise_dataset, train_svd_model, SVD_PARAMS
from ml.experiment_tracker import ExperimentTracker

TEST_HOLDOUT_N = 10
MIN_RATINGS_FOR_TEST = 15
TOP_K = 10
RELEVANCE_THRESHOLD = 4.0


def leave_last_n_out_split(df: pd.DataFrame, n: int = TEST_HOLDOUT_N, min_ratings: int = MIN_RATINGS_FOR_TEST):
    """Per-user, chronological split: last `n` ratings held out as test (only for
    users with at least `min_ratings` ratings total, so every test user still has
    a meaningful train history)."""
    df = df.sort_values(['user_id', 'timestamp'])
    train_parts, test_parts = [], []

    for _, group in df.groupby('user_id'):
        if len(group) < min_ratings:
            train_parts.append(group)
            continue
        train_parts.append(group.iloc[:-n])
        test_parts.append(group.iloc[-n:])

    train_df = pd.concat(train_parts, ignore_index=True)
    test_df = pd.concat(test_parts, ignore_index=True) if test_parts else pd.DataFrame(columns=df.columns)
    return train_df, test_df


def precision_at_k(recommended_ids, relevant_ids, k=TOP_K):
    top_k = recommended_ids[:k]
    if not top_k:
        return 0.0
    hits = sum(1 for mid in top_k if mid in relevant_ids)
    return hits / k


def ndcg_at_k(recommended_ids, relevance_map, k=TOP_K):
    top_k = recommended_ids[:k]
    dcg = sum(relevance_map.get(mid, 0.0) / np.log2(i + 2) for i, mid in enumerate(top_k))

    ideal_relevances = sorted(relevance_map.values(), reverse=True)[:k]
    idcg = sum(rel / np.log2(i + 2) for i, rel in enumerate(ideal_relevances))

    return (dcg / idcg) if idcg > 0 else 0.0


def score_ranking(ranked_ids, seen_ids, relevance_map, k=TOP_K):
    """Given a fully-ordered, best-first list of raw item ids, drop what this
    user has already seen, keep the top k, and score against their held-out
    test ratings. Shared by both the SVD model and the popularity baseline so
    the two are scored identically."""
    recommended = []
    for item_id in ranked_ids:
        if item_id in seen_ids:
            continue
        recommended.append(item_id)
        if len(recommended) == k:
            break

    relevant_ids = {mid for mid, r in relevance_map.items() if r >= RELEVANCE_THRESHOLD}
    return precision_at_k(recommended, relevant_ids, k), ndcg_at_k(recommended, relevance_map, k)


def evaluate_svd(model, trainset, train_items_by_user: dict, test_df: pd.DataFrame):
    global_mean = trainset.global_mean
    qi = model.qi
    bi = model.bi

    precisions, ndcgs = [], []

    for user_id, group in test_df.groupby('user_id'):
        try:
            inner_uid = trainset.to_inner_uid(user_id)
        except ValueError:
            continue  # user had no train ratings, can't be scored by this model

        pu = model.pu[inner_uid]
        bu = model.bu[inner_uid]
        scores = global_mean + bu + bi + (qi @ pu)

        ranked_inner = np.argsort(scores)[::-1]
        ranked_raw = [trainset.to_raw_iid(i) for i in ranked_inner]

        seen = train_items_by_user.get(user_id, set())
        relevance_map = dict(zip(group['movie_id'], group['rating']))

        precision, ndcg = score_ranking(ranked_raw, seen, relevance_map)
        precisions.append(precision)
        ndcgs.append(ndcg)

    return {
        "precision_at_10": float(np.mean(precisions)) if precisions else 0.0,
        "ndcg_at_10": float(np.mean(ndcgs)) if ndcgs else 0.0,
        "n_test_users": len(precisions),
    }


def evaluate_popularity_baseline(train_df: pd.DataFrame, train_items_by_user: dict, test_df: pd.DataFrame):
    """Non-personalized baseline: every user gets the same ranking, sorted by
    how many training-set ratings each movie received (most-rated first).
    This is the standard "are we actually better than just recommending
    what's popular?" sanity check for a recommender system."""
    popularity_ranking = (
        train_df.groupby('movie_id').size().sort_values(ascending=False).index.tolist()
    )

    precisions, ndcgs = [], []

    for user_id, group in test_df.groupby('user_id'):
        seen = train_items_by_user.get(user_id, set())
        relevance_map = dict(zip(group['movie_id'], group['rating']))

        precision, ndcg = score_ranking(popularity_ranking, seen, relevance_map)
        precisions.append(precision)
        ndcgs.append(ndcg)

    return {
        "baseline_precision_at_10": float(np.mean(precisions)) if precisions else 0.0,
        "baseline_ndcg_at_10": float(np.mean(ndcgs)) if ndcgs else 0.0,
        "n_test_users": len(precisions),
    }


def main():
    app = create_app()
    with app.app_context():
        movielens_dir = app.config['MOVIELENS_DATA_PATH']

        print("Loading ratings and building leave-last-N-out split...")
        df = load_ratings_dataframe(movielens_dir)
        train_df, test_df = leave_last_n_out_split(df)
        print(f"Train: {len(train_df)} ratings, Test: {len(test_df)} ratings "
              f"across {test_df['user_id'].nunique()} users.")

        train_items_by_user = train_df.groupby('user_id')['movie_id'].apply(set).to_dict()

        train_data = build_surprise_dataset(train_df)
        trainset = train_data.build_full_trainset()

        tracker = ExperimentTracker(tracking_uri=app.config.get('MLFLOW_TRACKING_URI'))
        with tracker.run(run_name="svd_offline_eval"):
            tracker.log_params(SVD_PARAMS)
            tracker.log_params({
                "test_holdout_n": TEST_HOLDOUT_N,
                "min_ratings_for_test": MIN_RATINGS_FOR_TEST,
                "top_k": TOP_K,
                "relevance_threshold": RELEVANCE_THRESHOLD,
            })

            print("Training SVD on the train split...")
            model = train_svd_model(trainset)

            print("Scoring test users against the SVD model...")
            svd_metrics = evaluate_svd(model, trainset, train_items_by_user, test_df)

            print("Scoring test users against the popularity baseline...")
            baseline_metrics = evaluate_popularity_baseline(train_df, train_items_by_user, test_df)

            precision_lift = (
                svd_metrics['precision_at_10'] / baseline_metrics['baseline_precision_at_10']
                if baseline_metrics['baseline_precision_at_10'] > 0 else float('inf')
            )
            ndcg_lift = (
                svd_metrics['ndcg_at_10'] / baseline_metrics['baseline_ndcg_at_10']
                if baseline_metrics['baseline_ndcg_at_10'] > 0 else float('inf')
            )

            print(f"\n{'Metric':<20}{'SVD':>10}{'Popularity':>14}{'Lift':>10}")
            print(f"{'Precision@' + str(TOP_K):<20}{svd_metrics['precision_at_10']:>10.4f}"
                  f"{baseline_metrics['baseline_precision_at_10']:>14.4f}{precision_lift:>9.2f}x")
            print(f"{'NDCG@' + str(TOP_K):<20}{svd_metrics['ndcg_at_10']:>10.4f}"
                  f"{baseline_metrics['baseline_ndcg_at_10']:>14.4f}{ndcg_lift:>9.2f}x")
            print(f"\nEvaluated over {svd_metrics['n_test_users']} users.")

            tracker.log_metrics(svd_metrics)
            tracker.log_metrics(baseline_metrics)
            tracker.log_metrics({
                "precision_at_10_lift_vs_popularity": precision_lift,
                "ndcg_at_10_lift_vs_popularity": ndcg_lift,
            })


if __name__ == '__main__':
    main()
