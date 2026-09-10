import pandas as pd
import os

# Paths (assuming you run this from the project root)
data_dir = os.path.join('data', 'movielens')
movies_1m_path = os.path.join(data_dir, 'movies.dat')
links_25m_path = os.path.join(data_dir, 'links.csv')
output_path = os.path.join(data_dir, 'ml_to_tmdb_map.csv')

# 1. Load the 1M movies
# Using latin-1 encoding because the 1M dataset contains older character sets
movies_1m = pd.read_csv(
    movies_1m_path, 
    sep='::', 
    engine='python', 
    encoding='latin-1',
    names=['ml_movie_id', 'title', 'genres']
)

# 2. Load the 25M links (contains movieId, imdbId, tmdbId)
links_25m = pd.read_csv(links_25m_path)
links_25m = links_25m.rename(columns={'movieId': 'ml_movie_id', 'tmdbId': 'tmdb_id'})

# 3. Merge them to get TMDb IDs for the 1M dataset
crosswalk = movies_1m.merge(links_25m[['ml_movie_id', 'tmdb_id']], on='ml_movie_id', how='left')

# 4. Clean up missing values
missing_tmdb = crosswalk['tmdb_id'].isna().sum()
print(f"Found {missing_tmdb} movies in 1M without a TMDb ID. Dropping them.")

crosswalk = crosswalk.dropna(subset=['tmdb_id'])
crosswalk['tmdb_id'] = crosswalk['tmdb_id'].astype(int)

# 5. Save the final map
crosswalk[['ml_movie_id', 'tmdb_id']].to_csv(output_path, index=False)
print(f"Successfully saved {len(crosswalk)} mappings to {output_path}")