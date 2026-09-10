// Watchlist toggle button (movie_detail.html) + full watchlist list (profile.html)

async function isInWatchlist(movieId) {
  const { ok, body } = await apiFetch('/profile/watchlist');
  if (!ok) return false;
  return (body.watchlist || []).some((w) => w.movie_id === movieId);
}

async function refreshWatchlistButton(movieId, buttonEl) {
  if (!isLoggedIn()) {
    buttonEl.textContent = 'Log in to add to watchlist';
    buttonEl.disabled = false;
    return;
  }

  const inList = await isInWatchlist(movieId);
  buttonEl.textContent = inList ? '− Remove from watchlist' : '+ Add to watchlist';
  buttonEl.dataset.inList = inList ? '1' : '0';
  buttonEl.disabled = false;
}

async function toggleWatchlist(movieId, buttonEl) {
  if (!requireAuth()) return;

  buttonEl.disabled = true;
  const inList = buttonEl.dataset.inList === '1';
  const method = inList ? 'DELETE' : 'POST';
  const { ok } = await apiFetch(`/profile/watchlist/${movieId}`, { method });

  if (ok) {
    await refreshWatchlistButton(movieId, buttonEl);
  } else {
    buttonEl.disabled = false;
  }
}

async function renderWatchlist(container) {
  const { ok, body } = await apiFetch('/profile/watchlist');
  if (!ok || !body.watchlist || body.watchlist.length === 0) {
    container.innerHTML = '<div class="empty-state">Your watchlist is empty.</div>';
    return;
  }

  container.innerHTML = body.watchlist
    .map(
      (w) => `
      <a class="movie-card d-block col-6 col-md-4 col-lg-3 mb-4" href="/movie/${w.movie_id}">
        <div class="poster-box mb-2">${escapeHtml(w.title || '')}</div>
        <div class="card-title">${escapeHtml(w.title || 'Untitled')}</div>
      </a>
    `
    )
    .join('');
  container.className = 'row';
}
