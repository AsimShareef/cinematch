import os
import time
import pandas as pd
import requests
from tqdm import tqdm
from app import create_app
from app.extensions import db
from app.models import Movie
from app.services.tmdb import TMDbService

REQUEST_DELAY_SECONDS = 0.05
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2


def get_movie_details_with_retry(tmdb_id):
    """Wraps TMDbService.get_movie_details so a transient network blip doesn't
    kill an hours-long sync run - retries a few times, then gives up on this id."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return TMDbService.get_movie_details(tmdb_id)
        except requests.exceptions.RequestException:
            if attempt == MAX_RETRIES:
                return None
            time.sleep(RETRY_BACKOFF_SECONDS * attempt)
    return None


def sync_catalog():
    app = create_app()
    with app.app_context():
        if not app.config.get('TMDB_API_KEY'):
            print("TMDB_API_KEY is not set. Add it to .env before running this script.")
            return

        crosswalk_path = os.path.join(app.config['MOVIELENS_DATA_PATH'], 'ml_to_tmdb_map.csv')
        crosswalk = pd.read_csv(crosswalk_path)
        tmdb_ids = sorted(crosswalk['tmdb_id'].unique().tolist())

        existing_ids = {m.tmdb_id for m in Movie.query.with_entities(Movie.tmdb_id).all()}
        pending_ids = [tid for tid in tmdb_ids if tid not in existing_ids]

        print(f"{len(existing_ids)} movies already in DB, {len(pending_ids)} left to sync.")

        added = 0
        failed = 0

        for tmdb_id in tqdm(pending_ids, desc="Syncing TMDb movies"):
            details = get_movie_details_with_retry(int(tmdb_id))
            time.sleep(REQUEST_DELAY_SECONDS)

            if details is None or not details.get('title'):
                failed += 1
                continue

            movie = Movie(
                tmdb_id=details['tmdb_id'],
                title=details['title'],
                overview=details['overview'],
                genres=details['genres'],
                cast=details['cast'],
                director=details['director'],
                avg_rating=details['avg_rating'] or 0.0,
                vote_count=details['vote_count'] or 0,
            )
            db.session.add(movie)
            added += 1

            # Commit periodically so a crash mid-run doesn't lose all progress
            if added % 100 == 0:
                db.session.commit()

        db.session.commit()
        print(f"Sync complete. Added {added} movies, {failed} failed lookups.")


if __name__ == '__main__':
    sync_catalog()
