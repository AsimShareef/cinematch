import numpy as np
from app.models import User, Movie
from ml.mood_nlp import MoodNLPService

class HybridRanker:
    def __init__(self, alpha: float = 0.4, beta: float = 0.3, gamma: float = 0.3):
        if abs((alpha + beta + gamma) - 1.0) > 1e-5:
            raise ValueError("Weights alpha, beta, and gamma must sum to 1.0")
        
        self.alpha = alpha
        self.beta = beta
        self.gamma = gamma
        self.mood_service = MoodNLPService()

    def normalize_scores(self, scores: list[float]) -> list[float]:
        if not scores:
            return []
        
        min_s = min(scores)
        max_s = max(scores)
        
        # Handle edge case where all scores are equal
        if abs(max_s - min_s) < 1e-9:
            return [0.5 for _ in scores]
            
        return [(s - min_s) / (max_s - min_s) for s in scores]

    def merge(
        self, 
        user_id: int, 
        collab_scores: list[dict], 
        content_scores: list[dict], 
        semantic_scores: list[dict], 
        mood_text: str = None
    ) -> list[dict]:
        
        # 1. Normalize scores independently within each list
        def process_list(score_list):
            if not score_list:
                return {}
            m_ids = [item['movie_id'] for item in score_list]
            raw_vals = [item['score'] or item.get('predicted_rating', 0.0) for item in score_list]
            norm_vals = self.normalize_scores(raw_vals)
            return {m_ids[i]: norm_vals[i] for i in range(len(m_ids))}

        collab_map = process_list(collab_scores)
        content_map = process_list(content_scores)
        semantic_map = process_list(semantic_scores)

        # 2. Build unified candidate set (union of all movie_ids)
        all_movie_ids = set(collab_map.keys()).union(content_map.keys()).union(semantic_map.keys())

        if not all_movie_ids:
            return []

        # 3. Adjust alpha based on user's cold_start_alpha from DB
        user = User.query.get(user_id)
        cold_alpha = user.cold_start_alpha if user else 0.0
        
        # Renormalize weight across only the sources that actually returned
        # candidates - e.g. semantic search contributes nothing when there's
        # no text query, so its share must go to collab/content instead of
        # being wasted (it would otherwise scale every candidate's score down
        # uniformly by a fixed amount, diluting the sources that do have signal).
        raw_weights = {
            "collab": self.alpha * cold_alpha if collab_map else 0.0,
            "content": self.beta if content_map else 0.0,
            "semantic": self.gamma if semantic_map else 0.0,
        }
        weight_total = sum(raw_weights.values())

        if weight_total > 0:
            effective_alpha = raw_weights["collab"] / weight_total
            effective_beta = raw_weights["content"] / weight_total
            effective_gamma = raw_weights["semantic"] / weight_total
        else:
            effective_alpha = effective_beta = effective_gamma = 0.0

        # 4. Compute weighted hybrid scores
        results = []
        movies_db = {m.id: m for m in Movie.query.filter(Movie.id.in_(list(all_movie_ids))).all()}

        # Classify the mood once per request - not once per candidate movie,
        # since each classification is a full BART-MNLI forward pass.
        mood_scores = self.mood_service.classify_mood(mood_text) if mood_text else None

        for movie_id in all_movie_ids:
            c_score = collab_map.get(movie_id, 0.0)
            cnt_score = content_map.get(movie_id, 0.0)
            s_score = semantic_map.get(movie_id, 0.0)

            base_score = (effective_alpha * c_score) + (effective_beta * cnt_score) + (effective_gamma * s_score)

            # 5. Apply mood genre boost if mood_text is provided
            if mood_scores and movie_id in movies_db:
                movie = movies_db[movie_id]
                genres = movie.genres if isinstance(movie.genres, list) else []
                boost = self.mood_service.boost_from_scores(mood_scores, genres)
                # Blend mood boost multiplicatively or additively
                final_score = base_score * (1.0 + 0.3 * boost)
            else:
                final_score = base_score

            results.append({
                "movie_id": movie_id,
                "hybrid_score": float(final_score)
            })

        # Sort descending by hybrid score
        results.sort(key=lambda x: x["hybrid_score"], reverse=True)
        return results

    def apply_mmr(
        self, 
        candidates: list[dict], 
        embeddings_map: dict, 
        lambda_param: float = 0.7, 
        top_k: int = 20
    ) -> list[dict]:
        if not candidates:
            return []

        selected = []
        remaining = list(candidates)

        while remaining and len(selected) < top_k:
            best_score = -float('inf')
            best_candidate = None
            best_idx = -1

            for idx, cand in enumerate(remaining):
                movie_id = cand['movie_id']
                relevance = cand['hybrid_score']

                if not selected:
                    diversity_penalty = 0.0
                else:
                    cand_emb = embeddings_map.get(movie_id)
                    if cand_emb is not None:
                        max_sim = 0.0
                        for sel in selected:
                            sel_emb = embeddings_map.get(sel['movie_id'])
                            if sel_emb is not None:
                                # Assuming embeddings are already normalized, dot product = cosine similarity
                                sim = float(np.dot(cand_emb, sel_emb))
                                if sim > max_sim:
                                    max_sim = sim
                        diversity_penalty = max_sim
                    else:
                        diversity_penalty = 0.0

                mmr_score = (lambda_param * relevance) - ((1.0 - lambda_param) * diversity_penalty)

                if mmr_score > best_score:
                    best_score = mmr_score
                    best_candidate = cand
                    best_idx = idx

            if best_candidate is not None:
                selected.append(best_candidate)
                remaining.pop(best_idx)
            else:
                break

        return selected