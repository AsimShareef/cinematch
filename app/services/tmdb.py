# app/services/tmdb.py
import requests
from flask import current_app

class TMDbService:
    BASE_URL = "https://api.themoviedb.org/3"
    IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"

    @classmethod
    def fetch_popular_movies(cls, page=1):
        """Fetches a page of popular movies from TMDb."""
        api_key = current_app.config.get('TMDB_API_KEY')
        url = f"{cls.BASE_URL}/movie/popular?api_key={api_key}&language=en-US&page={page}"
        
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        return response.json().get('results', [])

    @classmethod
    def get_movie_details(cls, tmdb_id):
        """Fetches full details + credits for a movie, for catalog sync."""
        api_key = current_app.config.get('TMDB_API_KEY')
        url = f"{cls.BASE_URL}/movie/{tmdb_id}?api_key={api_key}&language=en-US&append_to_response=credits"

        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return None

        data = response.json()

        cast = [c.get('name') for c in data.get('credits', {}).get('cast', [])[:3]]
        director = next(
            (c.get('name') for c in data.get('credits', {}).get('crew', [])
             if c.get('job') == 'Director'),
            None
        )

        return {
            "tmdb_id": data.get('id'),
            "title": data.get('title'),
            "overview": data.get('overview'),
            "genres": data.get('genres', []),
            "cast": cast,
            "director": director,
            "avg_rating": data.get('vote_average'),
            "vote_count": data.get('vote_count'),
        }

    @classmethod
    def get_poster_url(cls, tmdb_id):
        """Fetches the latest details for a movie to get its poster path."""
        api_key = current_app.config.get('TMDB_API_KEY')
        url = f"{cls.BASE_URL}/movie/{tmdb_id}?api_key={api_key}&language=en-US"
        
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                poster_path = response.json().get('poster_path')
                if poster_path:
                    return f"{cls.IMAGE_BASE_URL}{poster_path}"
        except requests.RequestException:
            pass
            
        return None