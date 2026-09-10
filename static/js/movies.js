// Shared helpers for rendering movie grids (used by index.html and search_results.html)

function movieCardHtml(movie) {
  const rating = movie.avg_rating ? movie.avg_rating.toFixed(1) : '—';
  const genres = (movie.genres || [])
    .slice(0, 2)
    .map((g) => (typeof g === 'object' ? g.name : g))
    .filter(Boolean);

  return `
    <div class="col-6 col-md-4 col-lg-3 mb-4">
      <a class="movie-card d-block" href="/movie/${movie.id}">
        <div class="poster-box mb-2">${escapeHtml(movie.title || '')}</div>
        <div class="card-title">${escapeHtml(movie.title || 'Untitled')}</div>
        <div class="small text-muted">
          ★ ${rating}${movie.vote_count ? ` (${movie.vote_count})` : ''}
        </div>
        <div class="mt-1">
          ${genres.map((g) => `<span class="badge bg-light text-dark border genre-badge me-1">${escapeHtml(g)}</span>`).join('')}
        </div>
      </a>
    </div>
  `;
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function renderMovieGrid(container, movies) {
  if (!movies || movies.length === 0) {
    container.innerHTML = '<div class="empty-state w-100">No movies found.</div>';
    return;
  }
  container.innerHTML = movies.map(movieCardHtml).join('');
}

async function fetchMovies({ page = 1, perPage = 20, genre = '', sortBy = 'popularity' } = {}) {
  const params = new URLSearchParams({ page, per_page: perPage, sort_by: sortBy });
  if (genre) params.set('genre', genre);
  return apiFetch(`/movies/?${params.toString()}`);
}

async function searchMovies(query) {
  const params = new URLSearchParams({ q: query });
  return apiFetch(`/movies/search?${params.toString()}`);
}
