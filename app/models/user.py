from datetime import datetime, timezone
from app.extensions import db

class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    cold_start_alpha = db.Column(db.Float, default=0.0)

    # Relationships
    ratings = db.relationship('Rating', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    reviews = db.relationship('Review', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    watchlist = db.relationship('Watchlist', backref='user', lazy='dynamic', cascade='all, delete-orphan')

    def get_rating_count(self):
        """Returns the total number of ratings the user has submitted."""
        return self.ratings.count()

    def update_cold_start_alpha(self):
        """Updates alpha based on rating count (max 1.0 at 50 ratings).

        Uses a square-root curve rather than linear so early ratings buy
        proportionally more collaborative-filtering trust than later ones
        (diminishing returns) - e.g. 5 ratings -> 0.32 instead of 0.1, while
        still reaching full confidence at the same 50-rating point."""
        count = self.get_rating_count()
        self.cold_start_alpha = min(1.0, (count / 50.0) ** 0.5)

    def __repr__(self):
        return f"<User {self.username}>"