from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import db
from app.models import Movie, Rating, User, Watchlist

profile_bp = Blueprint('profile', __name__)


@profile_bp.route('/', methods=['GET'])
@jwt_required()
def get_profile():
    current_user_id = int(get_jwt_identity())
    user = User.query.get(current_user_id)

    if not user:
        return jsonify({"error": "User not found"}), 404

    return jsonify({
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "cold_start_alpha": user.cold_start_alpha,
        "rating_count": user.get_rating_count(),
        "watchlist_count": user.watchlist.count(),
        "review_count": user.reviews.count()
    }), 200


@profile_bp.route('/ratings', methods=['GET'])
@jwt_required()
def get_ratings():
    current_user_id = int(get_jwt_identity())
    ratings = Rating.query.filter_by(user_id=current_user_id).order_by(Rating.rated_at.desc()).all()

    return jsonify({"ratings": [{
        "movie_id": r.movie_id,
        "title": r.movie.title if r.movie else None,
        "score": r.score,
        "rated_at": r.rated_at.isoformat()
    } for r in ratings]}), 200


@profile_bp.route('/watchlist', methods=['GET'])
@jwt_required()
def get_watchlist():
    current_user_id = int(get_jwt_identity())
    entries = Watchlist.query.filter_by(user_id=current_user_id).order_by(Watchlist.added_at.desc()).all()

    return jsonify({"watchlist": [{
        "movie_id": w.movie_id,
        "title": w.movie.title if w.movie else None,
        "added_at": w.added_at.isoformat()
    } for w in entries]}), 200


@profile_bp.route('/watchlist/<int:movie_id>', methods=['POST'])
@jwt_required()
def add_to_watchlist(movie_id):
    current_user_id = int(get_jwt_identity())

    if not Movie.query.get(movie_id):
        return jsonify({"error": "Movie not found"}), 404

    existing = Watchlist.query.filter_by(user_id=current_user_id, movie_id=movie_id).first()
    if existing:
        return jsonify({"message": "Movie already in watchlist"}), 200

    entry = Watchlist(user_id=current_user_id, movie_id=movie_id)
    db.session.add(entry)
    db.session.commit()

    return jsonify({"message": "Added to watchlist", "movie_id": movie_id}), 201


@profile_bp.route('/watchlist/<int:movie_id>', methods=['DELETE'])
@jwt_required()
def remove_from_watchlist(movie_id):
    current_user_id = int(get_jwt_identity())
    entry = Watchlist.query.filter_by(user_id=current_user_id, movie_id=movie_id).first()

    if not entry:
        return jsonify({"error": "Movie not in watchlist"}), 404

    db.session.delete(entry)
    db.session.commit()

    return jsonify({"message": "Removed from watchlist"}), 200
