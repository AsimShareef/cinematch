# CineMatch

A full-stack movie recommendation platform with a hybrid ML core — SVD collaborative
filtering, semantic search, and mood-based reranking — served through a Flask REST API.

## How it works

Every recommendation request runs a two-stage pipeline.

**Retrieval** — three independent services each return ~100 candidate movies:

- **Collaborative filtering** — SVD (regularized matrix factorization) trained on
  MovieLens 1M, with a closed-form ridge-regression *fold-in* so brand-new users get
  real predictions without retraining.
- **Content-based** — TF-IDF over title / overview / genres / cast, cosine similarity
  against the user's taste profile.
- **Semantic search** — Sentence-BERT embeddings (`all-MiniLM-L6-v2`, 384-d) in a FAISS
  index.

**Ranking** — `HybridRanker` normalizes and blends the three signals (weighted by a
per-user cold-start factor), an optional BART-MNLI zero-shot classifier reranks by mood,
and MMR trims the final slate for diversity.

Training and evaluation runs are tracked in MLflow.

## Stack

Flask · SQLAlchemy · Flask-JWT-Extended · Flask-Migrate · scikit-surprise ·
sentence-transformers · faiss-cpu · transformers (BART-MNLI) · MLflow · SQLite ·
Bootstrap 5

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows  (POSIX: source .venv/bin/activate)
pip install -r requirements.txt

copy .env.example .env            # then add your TMDb API key
set FLASK_APP=run.py
flask db upgrade                  # create the SQLite schema
```

Download [MovieLens 1M](https://grouplens.org/datasets/movielens/) into
`data/movielens/` (`ratings.dat`, `movies.dat`, `links.csv`), then build the models:

```bash
python -m scripts.build_crosswalk   # MovieLens <-> TMDb id map
python -m scripts.sync_tmdb         # populate the catalog (~3,800 films)
python -m ml.train_svd              # train SVD                -> ml/artifacts/
python -m ml.build_faiss_index      # embed + index every movie
python -m evaluation.offline_eval   # Precision@10 / NDCG@10 vs a popularity baseline
python -m evaluation.hybrid_eval    # end-to-end pipeline eval + MMR ablation

python run.py                       # http://127.0.0.1:5000
```

## Results

SVD on the MovieLens 1M held-out split: **RMSE 0.873**, **MAE 0.685** — in line with
published baselines.

On strict full-catalog top-N ranking, both SVD alone and the full hybrid pipeline trail
a popularity baseline (Precision@10 ≈ 0.6× and ≈ 0.4× of popularity). This is a
documented recommender-systems phenomenon — RMSE-optimized models are not thereby
optimized for ranking (Cremonesi et al., 2010) — not a bug. `evaluation/hybrid_eval.py`
runs the full ablation.

## Layout

```
app/            Flask app — blueprints, models, services, templates
ml/             SVD training, hybrid ranker, content / semantic / mood filters
evaluation/     offline + end-to-end evaluation harnesses
scripts/        TMDb sync, MovieLens crosswalk
```

## Notes

MovieLens 1M covers ratings from 1995–2000, so the catalog is intentionally scoped to
that era — the collaborative model can only score movies its training data contains.

Dataset: F. M. Harper & J. A. Konstan, *The MovieLens Datasets: History and Context*,
ACM TiiS (2015).
