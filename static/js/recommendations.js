// Powers the "Recommended for you" feed + mood search (index.html)
// and the "Similar movies" section (movie_detail.html).

async function loadRecommendations(container, { q = '', mood = '' } = {}) {
  const params = new URLSearchParams();
  if (q) params.set('q', q);
  if (mood) params.set('mood', mood);

  container.innerHTML = cinemaLoaderHtml('Loading recommendations...');
  container.className = '';
  const { ok, body } = await apiFetch(`/recommendations/?${params.toString()}`);
  container.className = 'row';

  if (!ok) {
    container.innerHTML = '<div class="empty-state w-100">Could not load recommendations.</div>';
    return;
  }

  if (body.message) {
    container.innerHTML = `<div class="empty-state w-100">${escapeHtml(body.message)}</div>`;
    return;
  }

  renderMovieGrid(container, body.recommendations);
}

async function loadSimilarMovies(container, movieId) {
  container.innerHTML = cinemaLoaderHtml('Finding similar movies...');
  container.className = '';
  const { ok, body } = await apiFetch(`/recommendations/similar/${movieId}?top_k=8`);
  container.className = 'row';

  if (!ok || !body.similar || body.similar.length === 0) {
    container.innerHTML = '<div class="empty-state w-100">No similar movies found yet.</div>';
    return;
  }
  renderMovieGrid(container, body.similar);
}
