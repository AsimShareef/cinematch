// Star-rating widget + review list/form (movie_detail.html)

function renderStars(container, currentScore, onSelect) {
  container.innerHTML = '';
  // Inserted in reverse (5..1); .star-rating uses flex-direction: row-reverse
  // to display them 1..5 left-to-right while letting the CSS `~` sibling
  // hover trick fill "up to" the hovered star instead of "from" it.
  for (let i = 5; i >= 1; i--) {
    const span = document.createElement('span');
    span.className = 'star' + (i <= Math.round(currentScore || 0) ? ' filled' : '');
    span.textContent = '★';
    span.dataset.value = i;
    span.addEventListener('click', () => onSelect(i));
    container.appendChild(span);
  }
}

async function submitRating(movieId, score, statusEl) {
  if (!requireAuth()) return;
  statusEl.textContent = 'Saving...';
  const { ok, body } = await apiFetch('/reviews/rating', {
    method: 'POST',
    body: JSON.stringify({ movie_id: movieId, score }),
  });

  if (ok) {
    statusEl.textContent = `You rated this ${score} / 5.`;
  } else {
    statusEl.textContent = (body && body.error) || 'Could not save rating.';
  }
}

async function loadReviews(movieId, container) {
  const { ok, body } = await apiFetch(`/reviews/movie/${movieId}`);
  if (!ok || !body.reviews || body.reviews.length === 0) {
    container.innerHTML = '<div class="empty-state">No reviews yet. Be the first!</div>';
    return;
  }

  container.innerHTML = body.reviews
    .map(
      (r) => `
      <div class="border-bottom py-3">
        <div class="fw-semibold">${escapeHtml(r.username || 'Anonymous')}</div>
        <div class="text-muted small mb-1">${new Date(r.created_at).toLocaleDateString()}</div>
        <div>${escapeHtml(r.body)}</div>
      </div>
    `
    )
    .join('');
}

async function submitReview(movieId, text, statusEl, reviewsContainer) {
  if (!requireAuth()) return;
  const { ok, body } = await apiFetch('/reviews/', {
    method: 'POST',
    body: JSON.stringify({ movie_id: movieId, body: text }),
  });

  if (ok) {
    statusEl.textContent = '';
    loadReviews(movieId, reviewsContainer);
  } else {
    statusEl.textContent = (body && body.error) || 'Could not post review.';
  }
}
