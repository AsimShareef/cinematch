from datetime import datetime, timezone
from app.extensions import db

class Movie(db.Model):
    __tablename__ = 'movies'

    id = db.Column(db.Integer, primary_key=True)
    tmdb_id = db.Column(db.Integer, unique=True, nullable=False)
    title = db.Column(db.String(255), nullable=False)
    overview = db.Column(db.Text)
    genres = db.Column(db.JSON)
    cast = db.Column(db.JSON)
    director = db.Column(db.String(128))
    avg_rating = db.Column(db.Float, default=0.0)
    vote_count = db.Column(db.Integer, default=0)
    faiss_index = db.Column(db.Integer, nullable=True)

    # Relationships
    ratings = db.relationship('Rating', backref='movie', lazy='dynamic', cascade='all, delete-orphan')
    reviews = db.relationship('Review', backref='movie', lazy='dynamic', cascade='all, delete-orphan')
    watchlisted_by = db.relationship('Watchlist', backref='movie', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f"<Movie {self.title} (TMDb: {self.tmdb_id})>"