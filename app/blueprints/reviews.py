from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import db
from app.models import Movie, Rating, Review, User

reviews_bp = Blueprint('reviews', __name__)


def _recalculate_movie_stats(movie_id):
    movie = Movie.query.get(movie_id)
    if not movie:
        return

    ratings = Rating.query.filter_by(movie_id=movie_id).all()
    movie.vote_count = len(ratings)
    movie.avg_rating = (sum(r.score for r in ratings) / len(ratings)) if ratings else 0.0


@reviews_bp.route('/rating', methods=['POST'])
@jwt_required()
def upsert_rating():
    current_user_id = int(get_jwt_identity())
    data = request.get_json() or {}

    movie_id = data.get('movie_id')
    score = data.get('score')

    if movie_id is None or score is None:
        return jsonify({"error": "movie_id and score are required"}), 400

    try:
        score = float(score)
    except (TypeError, ValueError):
        return jsonify({"error": "score must be a number"}), 400

    if not (0.5 <= score <= 5.0):
        return jsonify({"error": "score must be between 0.5 and 5.0"}), 400

    movie = Movie.query.get(movie_id)
    if not movie:
        return jsonify({"error": "Movie not found"}), 404

    rating = Rating.query.filter_by(user_id=current_user_id, movie_id=movie_id).first()
    if rating:
        rating.score = score
    else:
        rating = Rating(user_id=current_user_id, movie_id=movie_id, score=score)
        db.session.add(rating)

    _recalculate_movie_stats(movie_id)

    user = User.query.get(current_user_id)
    if user:
        user.update_cold_start_alpha()

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Failed to save rating", "details": str(e)}), 500

    return jsonify({
        "movie_id": movie_id,
        "score": score,
        "movie_avg_rating": movie.avg_rating,
        "movie_vote_count": movie.vote_count
    }), 200


@reviews_bp.route('/rating/<int:movie_id>', methods=['DELETE'])
@jwt_required()
def delete_rating(movie_id):
    current_user_id = int(get_jwt_identity())
    rating = Rating.query.filter_by(user_id=current_user_id, movie_id=movie_id).first()

    if not rating:
        return jsonify({"error": "Rating not found"}), 404

    db.session.delete(rating)
    _recalculate_movie_stats(movie_id)

    user = User.query.get(current_user_id)
    if user:
        user.update_cold_start_alpha()

    db.session.commit()
    return jsonify({"message": "Rating removed"}), 200


@reviews_bp.route('/', methods=['POST'])
@jwt_required()
def create_review():
    current_user_id = int(get_jwt_identity())
    data = request.get_json() or {}

    movie_id = data.get('movie_id')
    body = (data.get('body') or '').strip()

    if not movie_id or not body:
        return jsonify({"error": "movie_id and body are required"}), 400

    if not Movie.query.get(movie_id):
        return jsonify({"error": "Movie not found"}), 404

    review = Review(user_id=current_user_id, movie_id=movie_id, body=body)
    db.session.add(review)
    db.session.commit()

    return jsonify({
        "id": review.id,
        "movie_id": review.movie_id,
        "body": review.body,
        "created_at": review.created_at.isoformat()
    }), 201


@reviews_bp.route('/<int:review_id>', methods=['PUT'])
@jwt_required()
def update_review(review_id):
    current_user_id = int(get_jwt_identity())
    review = Review.query.get_or_404(review_id)

    if str(review.user_id) != str(current_user_id):
        return jsonify({"error": "You can only edit your own reviews"}), 403

    data = request.get_json() or {}
    body = (data.get('body') or '').strip()
    if not body:
        return jsonify({"error": "body is required"}), 400

    review.body = body
    db.session.commit()

    return jsonify({"id": review.id, "body": review.body}), 200


@reviews_bp.route('/<int:review_id>', methods=['DELETE'])
@jwt_required()
def delete_review(review_id):
    current_user_id = int(get_jwt_identity())
    review = Review.query.get_or_404(review_id)

    if str(review.user_id) != str(current_user_id):
        return jsonify({"error": "You can only delete your own reviews"}), 403

    db.session.delete(review)
    db.session.commit()

    return jsonify({"message": "Review deleted"}), 200


@reviews_bp.route('/movie/<int:movie_id>', methods=['GET'])
def list_reviews_for_movie(movie_id):
    reviews = Review.query.filter_by(movie_id=movie_id).order_by(Review.created_at.desc()).all()

    return jsonify({"reviews": [{
        "id": r.id,
        "user_id": r.user_id,
        "username": r.user.username if r.user else None,
        "body": r.body,
        "created_at": r.created_at.isoformat()
    } for r in reviews]}), 200
