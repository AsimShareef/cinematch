# app/blueprints/movies.py
from flask import Blueprint, request, jsonify
from sqlalchemy import cast, String
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.extensions import db, cache
from app.models import Movie, User
from app.services.tmdb import TMDbService

movies_bp = Blueprint('movies', __name__)

@movies_bp.route('/', methods=['GET'])
def list_movies():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    genre = request.args.get('genre', type=str)
    min_rating = request.args.get('min_rating', type=float)
    sort_by = request.args.get('sort_by', 'popularity', type=str)

    query = Movie.query

    # Apply filters
    if genre:
        # Cast JSON column to string for cross-database LIKE compatibility
        query = query.filter(cast(Movie.genres, String).ilike(f'%{genre.strip()}%'))
    
    if min_rating is not None:
        query = query.filter(Movie.avg_rating >= min_rating)

    # Apply sorting
    if sort_by == 'rating':
        query = query.order_by(Movie.avg_rating.desc())
    elif sort_by == 'title':
        query = query.order_by(Movie.title.asc())
    else:  # default to popularity
        query = query.order_by(Movie.vote_count.desc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        "movies": [{
            "id": m.id,
            "tmdb_id": m.tmdb_id,
            "title": m.title,
            "avg_rating": m.avg_rating,
            "vote_count": m.vote_count,
            "genres": m.genres
        } for m in pagination.items],
        "total": pagination.total,
        "pages": pagination.pages,
        "current_page": page
    }), 200


@movies_bp.route('/<int:movie_id>', methods=['GET'])
def get_movie(movie_id):
    movie = Movie.query.get_or_404(movie_id)
    
    # Check cache for poster URL to avoid hammering the TMDb API
    cache_key = f"movie_poster_{movie.tmdb_id}"
    poster_url = cache.get(cache_key)
    
    if not poster_url:
        poster_url = TMDbService.get_poster_url(movie.tmdb_id)
        if poster_url:
            cache.set(cache_key, poster_url, timeout=86400)  # Cache for 24 hours

    return jsonify({
        "id": movie.id,
        "tmdb_id": movie.tmdb_id,
        "title": movie.title,
        "overview": movie.overview,
        "genres": movie.genres,
        "cast": movie.cast,
        "director": movie.director,
        "avg_rating": movie.avg_rating,
        "vote_count": movie.vote_count,
        "poster_url": poster_url
    }), 200


@movies_bp.route('/search', methods=['GET'])
def search_movies():
    q = request.args.get('q', '', type=str)
    
    # Strip whitespace to prevent search failures caused by trailing/leading spaces
    q = q.strip()
    
    if not q:
        return jsonify({"movies": []}), 200

    search_term = f"%{q}%"
    movies = Movie.query.filter(
        (Movie.title.ilike(search_term)) | (Movie.overview.ilike(search_term))
    ).limit(50).all()

    return jsonify({"movies": [{
        "id": m.id,
        "title": m.title,
        "overview": m.overview,
        "avg_rating": m.avg_rating
    } for m in movies]}), 200


@movies_bp.route('/sync', methods=['POST'])
@jwt_required()
def sync_movies():
    current_user_id = int(get_jwt_identity())
    user = User.query.get(current_user_id)
    
    # Basic authorization placeholder (Replace with proper Role check if implemented)
    if not user:
        return jsonify({"error": "Admin access required"}), 403
        
    added_count = 0
    updated_count = 0
    
    try:
        # Fetch 5 pages of popular movies
        for page in range(1, 6):
            tmdb_movies = TMDbService.fetch_popular_movies(page=page)
            
            for tmdb_data in tmdb_movies:
                tmdb_id = tmdb_data.get('id')
                movie = Movie.query.filter_by(tmdb_id=tmdb_id).first()
                
                if movie:
                    movie.title = tmdb_data.get('title')
                    movie.overview = tmdb_data.get('overview')
                    movie.avg_rating = tmdb_data.get('vote_average')
                    movie.vote_count = tmdb_data.get('vote_count')
                    updated_count += 1
                else:
                    new_movie = Movie(
                        tmdb_id=tmdb_id,
                        title=tmdb_data.get('title'),
                        overview=tmdb_data.get('overview'),
                        avg_rating=tmdb_data.get('vote_average'),
                        vote_count=tmdb_data.get('vote_count'),
                        genres=tmdb_data.get('genre_ids', []), 
                    )
                    db.session.add(new_movie)
                    added_count += 1
                    
        db.session.commit()
        return jsonify({
            "message": "Sync complete",
            "added": added_count,
            "updated": updated_count
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Failed to sync with TMDb", "details": str(e)}), 500