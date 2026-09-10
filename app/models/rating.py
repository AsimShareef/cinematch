from datetime import datetime, timezone
from app.extensions import db

class Rating(db.Model):
    __tablename__ = 'ratings'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    movie_id = db.Column(db.Integer, db.ForeignKey('movies.id'), nullable=False)
    score = db.Column(db.Float, nullable=False)
    rated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint('user_id', 'movie_id', name='_user_movie_rating_uc'),
    )

    def __repr__(self):
        return f"<Rating {self.score} by User {self.user_id} for Movie {self.movie_id}>"