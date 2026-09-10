import os
import json
import numpy as np
import faiss
from tqdm import tqdm
from sentence_transformers import SentenceTransformer
from app import create_app
from app.extensions import db
from app.models import Movie

def build_index():
    app = create_app()
    with app.app_context():
        # 1. Load all movies from the SQLAlchemy Movie table
        print("Loading movies from database...")
        movies = Movie.query.all()
        
        if not movies:
            print("No movies found. Run the sync script first to populate the database.")
            return

        texts = []
        movie_ids = []
        
        for m in movies:
            title = (m.title or "").strip()
            overview = (m.overview or "").strip()
            
            genres = m.genres if isinstance(m.genres, list) else []
            # Extract names if genres is a list of dicts from TMDb, otherwise convert strings
            genre_strings = [str(g.get('name', g)).strip() if isinstance(g, dict) else str(g).strip() for g in genres]
            genre_text = " ".join(genre_strings)
            
            combined_text = f"{title}. {overview}. Genres: {genre_text}".strip()
            texts.append(combined_text)
            movie_ids.append(m.id)

        # 2. Encode using 'all-MiniLM-L6-v2' in batches of 64
        print("Loading Sentence-BERT model...")
        model = SentenceTransformer('all-MiniLM-L6-v2')
        
        print(f"Encoding {len(texts)} movies (Batch size: 64)...")
        embeddings = model.encode(
            texts, 
            batch_size=64, 
            show_progress_bar=True, 
            convert_to_numpy=True
        )

        # 3. Normalize all embeddings to unit length (for inner product / cosine similarity)
        print("Normalizing vectors to unit length...")
        faiss.normalize_L2(embeddings)

        # 4. Build faiss.IndexFlatIP and add embeddings
        dimension = embeddings.shape[1]
        print(f"Building FAISS IndexFlatIP (Dimension: {dimension})...")
        index = faiss.IndexFlatIP(dimension)
        index.add(embeddings)

        # 5. Save the index to a file path from config
        index_path = app.config.get('FAISS_INDEX_PATH')
        index_dir = os.path.dirname(index_path)
        os.makedirs(index_dir, exist_ok=True)
        
        faiss.write_index(index, index_path)
        print(f"Saved FAISS index to {index_path}")

        # 6. Save a JSON mapping file: {movie_db_id: faiss_row_index}
        mapping = {movie_ids[i]: i for i in range(len(movie_ids))}
        mapping_path = os.path.join(index_dir, 'faiss_mapping.json')
        
        with open(mapping_path, 'w') as f:
            json.dump(mapping, f, indent=4)
        print(f"Saved mapping file to {mapping_path}")

        # 7. Update the faiss_index column on each Movie row in the database
        print("Updating database records...")
        for i, movie in tqdm(enumerate(movies), total=len(movies), desc="Saving DB indices"):
            movie.faiss_index = i
            
        db.session.commit()
        print("Database commit successful. FAISS indexing complete.")


if __name__ == '__main__':
    build_index()