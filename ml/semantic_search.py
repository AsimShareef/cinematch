import os
import json
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

# Module-level variables to cache heavyweight objects (Singleton pattern)
_model_instance = None
_index_instance = None
_mapping_instance = None
_reverse_mapping_instance = None

class SemanticSearchService:
    def __init__(self, index_path: str, mapping_path: str):
        global _model_instance, _index_instance, _mapping_instance, _reverse_mapping_instance
        
        if not os.path.exists(index_path) or os.path.getsize(index_path) == 0:
            raise FileNotFoundError(f"FAISS index not found at {index_path}. Run ml/build_faiss_index.py first.")
        if not os.path.exists(mapping_path) or os.path.getsize(mapping_path) == 0:
            raise FileNotFoundError(f"Mapping file not found at {mapping_path}. Run ml/build_faiss_index.py first.")

        # Load Sentence-BERT Model
        if _model_instance is None:
            _model_instance = SentenceTransformer('all-MiniLM-L6-v2')
        self.model = _model_instance

        # Load FAISS Index
        if _index_instance is None:
            _index_instance = faiss.read_index(index_path)
        self.index = _index_instance

        # Load JSON Mapping
        if _mapping_instance is None or _reverse_mapping_instance is None:
            with open(mapping_path, 'r') as f:
                _mapping_instance = json.load(f)
            # JSON keys are always strings, so we cast to int for the reverse mapping lookup
            _reverse_mapping_instance = {int(v): int(k) for k, v in _mapping_instance.items()}
        
        self.mapping = _mapping_instance
        self.reverse_mapping = _reverse_mapping_instance

    def search(self, query_text: str, top_k: int = 50) -> list[dict]:
        # Handle empty inputs and whitespace to prevent encoding failures
        if not query_text or not query_text.strip():
            raise ValueError("Query string cannot be empty or just whitespace.")

        cleaned_query = query_text.strip()
        
        # Encode and normalize to unit length for inner product
        query_vector = self.model.encode([cleaned_query], convert_to_numpy=True)
        faiss.normalize_L2(query_vector)

        distances, indices = self.index.search(query_vector, top_k)

        results = []
        for i in range(len(indices[0])):
            faiss_row = indices[0][i]
            
            # FAISS returns -1 if there are fewer elements in the index than top_k
            if faiss_row == -1: 
                continue
            
            movie_id = self.reverse_mapping.get(faiss_row)
            if movie_id is not None:
                results.append({
                    "movie_id": movie_id,
                    "score": float(distances[0][i])
                })
                
        return results

    def search_similar(self, movie_id: int, top_k: int = 20) -> list[dict]:
        # JSON keys are strings, so convert the DB integer ID
        faiss_row = self.mapping.get(str(movie_id))
        
        if faiss_row is None:
            raise ValueError(f"Movie ID {movie_id} not found in FAISS mapping.")

        # Extract the vector directly from the FAISS index
        try:
            vector = self.index.reconstruct(faiss_row)
        except RuntimeError as e:
            raise RuntimeError(f"Failed to reconstruct vector for movie_id {movie_id}: {str(e)}")

        # Reshape for search: FAISS expects a 2D array (1, Dimension)
        query_vector = np.expand_dims(vector, axis=0)

        # Retrieve top_k + 1 to account for the input movie itself appearing at index 0
        distances, indices = self.index.search(query_vector, top_k + 1)

        results = []
        for i in range(len(indices[0])):
            result_faiss_row = indices[0][i]
            
            if result_faiss_row == -1:
                continue
            
            result_movie_id = self.reverse_mapping.get(result_faiss_row)
            
            # Exclude the source movie from the similarity results
            if result_movie_id == movie_id:
                continue
                
            if result_movie_id is not None:
                results.append({
                    "movie_id": result_movie_id,
                    "score": float(distances[0][i])
                })
                
            if len(results) == top_k:
                break

        return results