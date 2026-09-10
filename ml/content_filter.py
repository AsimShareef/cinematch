import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from app.models import Movie

# Module-level singletons for efficient caching
_tfidf_matrix_instance = None
_movie_mapping_instance = None
_reverse_mapping_instance = None
_last_movie_count = 0

class ContentBasedFilterService:
    def __init__(self):
        self.refresh()

    def refresh(self):
        """Builds or refits the TF-IDF matrix from database movies."""
        global _tfidf_matrix_instance, _movie_mapping_instance, _reverse_mapping_instance, _last_movie_count

        movies = Movie.query.all()
        current_count = len(movies)

        # Skip rebuilding if the movie count hasn't changed and matrix already exists
        if _tfidf_matrix_instance is not None and current_count == _last_movie_count:
            self.matrix = _tfidf_matrix_instance
            self.movie_mapping = _movie_mapping_instance
            self.reverse_mapping = _reverse_mapping_instance
            return

        corpus = []
        movie_ids = []

        for m in movies:
            title = (m.title or "").strip()
            overview = (m.overview or "").strip()
            
            genres = m.genres if isinstance(m.genres, list) else []
            genre_strings = [str(g.get('name', g)).strip() if isinstance(g, dict) else str(g).strip() for g in genres]
            genre_text = " ".join(genre_strings)

            cast = m.cast if isinstance(m.cast, list) else []
            cast_strings = [str(c.get('name', c)).strip() if isinstance(c, dict) else str(c).strip() for c in cast[:3]]
            cast_text = " ".join(cast_strings)

            combined_text = f"{title} {overview} {genre_text} {cast_text}".strip()
            corpus.append(combined_text)
            movie_ids.append(m.id)

        if not corpus:
            self.matrix = None
            self.movie_mapping = {}
            self.reverse_mapping = {}
            return

        vectorizer = TfidfVectorizer(max_features=15000, ngram_range=(1, 2))
        _tfidf_matrix_instance = vectorizer.fit_transform(corpus)
        
        _movie_mapping_instance = {movie_ids[i]: i for i in range(len(movie_ids))}
        _reverse_mapping_instance = {i: movie_ids[i] for i in range(len(movie_ids))}
        _last_movie_count = current_count

        self.matrix = _tfidf_matrix_instance
        self.movie_mapping = _movie_mapping_instance
        self.reverse_mapping = _reverse_mapping_instance

    def recommend_from_movie(self, movie_id: int, top_k: int = 50) -> list[dict]:
        row_idx = self.movie_mapping.get(movie_id)
        if row_idx is None or self.matrix is None:
            return []

        movie_vector = self.matrix[row_idx]
        similarities = cosine_similarity(movie_vector, self.matrix).flatten()

        # Sort indices by similarity descending
        sorted_indices = np.argsort(similarities)[::-1]

        results = []
        for idx in sorted_indices:
            sim_movie_id = self.reverse_mapping.get(idx)
            if sim_movie_id == movie_id:
                continue  # Skip the source movie itself
            
            results.append({
                "movie_id": sim_movie_id,
                "score": float(similarities[idx])
            })
            if len(results) == top_k:
                break

        return results

    def recommend_from_history(self, movie_ids: list[int], top_k: int = 50) -> list[dict]:
        if not movie_ids or self.matrix is None:
            return []

        valid_rows = [self.movie_mapping.get(mid) for mid in movie_ids if mid in self.movie_mapping]
        if not valid_rows:
            return []

        # Average the TF-IDF vectors of the user's history movies
        user_profile_vector = np.mean(self.matrix[valid_rows], axis=0)
        
        # Ensure it's 2D for cosine_similarity
        if isinstance(user_profile_vector, np.matrix):
            user_profile_vector = user_profile_vector.A

        similarities = cosine_similarity(user_profile_vector, self.matrix).flatten()
        sorted_indices = np.argsort(similarities)[::-1]

        input_set = set(movie_ids)
        results = []

        for idx in sorted_indices:
            sim_movie_id = self.reverse_mapping.get(idx)
            if sim_movie_id in input_set:
                continue  # Exclude items already in user history

            results.append({
                "movie_id": sim_movie_id,
                "score": float(similarities[idx])
            })
            if len(results) == top_k:
                break

        return results