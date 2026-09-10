import logging
import os
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.models import Movie, Rating, Watchlist
from ml.collaborative_filter import CollaborativeFilterService
from ml.content_filter import ContentBasedFilterService
from ml.semantic_search import SemanticSearchService
from ml.hybrid_ranker import HybridRanker

recommendations_bp = Blueprint('recommendations', __name__)

_hybrid_ranker_instance = None

NO_SIGNAL_MESSAGE = "Not enough signal yet - rate a few movies or add to your watchlist."


def _get_hybrid_ranker():
    global _hybrid_ranker_instance
    if _hybrid_ranker_instance is None:
        _hybrid_ranker_instance = HybridRanker()
    return _hybrid_ranker_instance


def _get_collaborative_filter():
    try:
        return CollaborativeFilterService(
            model_path=current_app.config['SVD_MODEL_PATH'],
            movielens_dir=current_app.config['MOVIELENS_DATA_PATH'],
        )
    except FileNotFoundError as e:
        logging.warning(f"Collaborative filter unavailable: {e}")
        return None


def _get_semantic_search():
    index_path = current_app.config['FAISS_INDEX_PATH']
    mapping_path = os.path.join(os.path.dirname(index_path), 'faiss_mapping.json')
    try:
        return SemanticSearchService(index_path=index_path, mapping_path=mapping_path)
    except FileNotFoundError as e:
        logging.warning(f"Semantic search unavailable: {e}")
        return None


def _build_embeddings_map(semantic_service, movie_ids):
    """Reconstructs FAISS vectors for MMR's diversity penalty, keyed by DB movie id."""
    if semantic_service is None or not movie_ids:
        return {}

    movies = Movie.query.filter(
        Movie.id.in_(movie_ids), Movie.faiss_index.isnot(None)
    ).all()

    embeddings = {}
    for movie in movies:
        try:
            embeddings[movie.id] = semantic_service.index.reconstruct(movie.faiss_index)
        except RuntimeError:
            continue
    return embeddings


def _serialize_movies(ranked_results):
    movie_ids = [r['movie_id'] for r in ranked_results]
    movies_by_id = {m.id: m for m in Movie.query.filter(Movie.id.in_(movie_ids)).all()}

    output = []
    for r in ranked_results:
        movie = movies_by_id.get(r['movie_id'])
        if not movie:
            continue
        output.append({
            "id": movie.id,
            "tmdb_id": movie.tmdb_id,
            "title": movie.title,
            "overview": movie.overview,
            "genres": movie.genres,
            "avg_rating": movie.avg_rating,
            "vote_count": movie.vote_count,
            "score": r.get("hybrid_score", r.get("score"))
        })
    return output


def _generate_recommendations(user_id, top_k=20, query_text=None, mood_text=None, diversify=True):
    collab_service = _get_collaborative_filter()
    collab_scores = collab_service.recommend_for_user(user_id, top_k=100) if collab_service else []

    rated_ids = [r.movie_id for r in Rating.query.filter_by(user_id=user_id).all()]
    watchlist_ids = [w.movie_id for w in Watchlist.query.filter_by(user_id=user_id).all()]
    history_ids = list(set(rated_ids) | set(watchlist_ids))

    content_service = ContentBasedFilterService()
    content_scores = content_service.recommend_from_history(history_ids, top_k=100) if history_ids else []

    semantic_service = _get_semantic_search()
    semantic_scores = []
    if semantic_service and query_text:
        try:
            semantic_scores = semantic_service.search(query_text, top_k=100)
        except ValueError:
            semantic_scores = []

    ranker = _get_hybrid_ranker()
    merged = ranker.merge(
        user_id=user_id,
        collab_scores=collab_scores,
        content_scores=content_scores,
        semantic_scores=semantic_scores,
        mood_text=mood_text,
    )

    if not merged:
        return []

    if not diversify:
        return merged[:top_k]

    candidate_ids = [r['movie_id'] for r in merged[:100]]
    embeddings_map = _build_embeddings_map(semantic_service, candidate_ids)
    return ranker.apply_mmr(merged[:100], embeddings_map, lambda_param=0.7, top_k=top_k)


@recommendations_bp.route('/', methods=['GET'])
@jwt_required()
def get_recommendations():
    current_user_id = int(get_jwt_identity())
    top_k = request.args.get('top_k', 20, type=int)
    query_text = request.args.get('q', type=str)
    mood_text = request.args.get('mood', type=str)

    diversified = _generate_recommendations(current_user_id, top_k, query_text, mood_text)

    if not diversified:
        return jsonify({"recommendations": [], "message": NO_SIGNAL_MESSAGE}), 200

    return jsonify({"recommendations": _serialize_movies(diversified)}), 200


@recommendations_bp.route('/mood', methods=['POST'])
@jwt_required()
def get_mood_recommendations():
    current_user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    mood_text = (data.get('mood_text') or '').strip()
    top_k = data.get('top_k', 20)

    if not mood_text:
        return jsonify({"error": "mood_text is required"}), 400

    diversified = _generate_recommendations(current_user_id, top_k, query_text=None, mood_text=mood_text)

    if not diversified:
        return jsonify({"recommendations": [], "message": NO_SIGNAL_MESSAGE}), 200

    return jsonify({"recommendations": _serialize_movies(diversified)}), 200


@recommendations_bp.route('/similar/<int:movie_id>', methods=['GET'])
def get_similar_movies(movie_id):
    top_k = request.args.get('top_k', 20, type=int)

    if not Movie.query.get(movie_id):
        return jsonify({"error": "Movie not found"}), 404

    content_service = ContentBasedFilterService()
    content_scores = content_service.recommend_from_movie(movie_id, top_k=50)

    semantic_service = _get_semantic_search()
    semantic_scores = []
    if semantic_service:
        try:
            semantic_scores = semantic_service.search_similar(movie_id, top_k=50)
        except ValueError:
            semantic_scores = []

    # Simple additive blend (no user/cold-start context here, unlike the main feed)
    combined = {}
    for item in content_scores + semantic_scores:
        mid = item['movie_id']
        combined[mid] = combined.get(mid, 0.0) + item['score']

    ranked = [{"movie_id": mid, "hybrid_score": score} for mid, score in combined.items()]
    ranked.sort(key=lambda x: x['hybrid_score'], reverse=True)

    return jsonify({"similar": _serialize_movies(ranked[:top_k])}), 200
