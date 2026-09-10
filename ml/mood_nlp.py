import logging
from transformers import pipeline

# Module-level singletons to cache the heavy pipeline instance
_pipeline_instance = None
_load_failed = False

class MoodNLPService:
    CANDIDATE_LABELS = [
        "comedy", "action", "drama", "horror", "romance", 
        "thriller", "animation", "documentary", "science fiction", "fantasy"
    ]

    def __init__(self):
        global _pipeline_instance, _load_failed
        
        if _pipeline_instance is None and not _load_failed:
            try:
                _pipeline_instance = pipeline(
                    "zero-shot-classification", 
                    model="facebook/bart-large-mnli"
                )
            except Exception as e:
                _load_failed = True
                logging.warning(f"Failed to load BART-MNLI model: {e}")
                
        self.classifier = _pipeline_instance

    def classify_mood(self, mood_text: str) -> dict:
        equal_weight = 1.0 / len(self.CANDIDATE_LABELS)
        equal_weights_dict = {label: equal_weight for label in self.CANDIDATE_LABELS}

        # Handle empty input or failed model load gracefully
        if not mood_text or not mood_text.strip() or self.classifier is None:
            return equal_weights_dict

        try:
            result = self.classifier(
                mood_text.strip(), 
                candidate_labels=self.CANDIDATE_LABELS, 
                multi_label=False
            )
            
            labels = result.get('labels', [])
            scores = result.get('scores', [])
            
            return {labels[i]: float(scores[i]) for i in range(len(labels))}
            
        except Exception as e:
            logging.warning(f"Zero-shot classification inference failed: {e}")
            return equal_weights_dict

    def get_genre_boost(self, mood_text: str, movie_genres: list) -> float:
        """Convenience wrapper for a single movie. Callers scoring many movies
        against the same mood_text should call classify_mood() once and reuse
        boost_from_scores() instead - each call here re-runs full BART-MNLI
        inference."""
        mood_scores = self.classify_mood(mood_text)
        return self.boost_from_scores(mood_scores, movie_genres)

    @staticmethod
    def boost_from_scores(mood_scores: dict, movie_genres: list) -> float:
        if not movie_genres or not mood_scores:
            return 0.0

        # Normalize movie genres to lowercase strings for safe matching
        normalized_genres = []
        for g in movie_genres:
            if isinstance(g, dict):
                genre_name = g.get('name', '')
            else:
                genre_name = str(g)
            normalized_genres.append(genre_name.lower().strip())

        matched_scores = []
        for g in normalized_genres:
            for label, score in mood_scores.items():
                if label in g or g in label:
                    matched_scores.append(score)

        if not matched_scores:
            return 0.0

        # Return the maximum score among matching genres as the boost factor (0.0 to 1.0)
        return float(max(matched_scores))