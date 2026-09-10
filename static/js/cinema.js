// Shared cinematic UI helpers: curtain-reveal transition + film-reel loader.

function showCurtain() {
  const overlay = document.getElementById('curtain-overlay');
  if (!overlay) return;
  overlay.classList.add('curtain-active');
  overlay.classList.remove('curtain-open');
}

function openCurtain(delay = 250) {
  const overlay = document.getElementById('curtain-overlay');
  if (!overlay) return;
  setTimeout(() => {
    overlay.classList.add('curtain-open');
    setTimeout(() => overlay.classList.remove('curtain-active'), 1200);
  }, delay);
}

function cinemaLoaderHtml(label = 'Loading...') {
  return `
    <div class="cinema-loading">
      <svg class="reel-spinner" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="32" cy="32" r="26" stroke="currentColor" stroke-width="2.5"/>
        <circle cx="32" cy="32" r="7" stroke="currentColor" stroke-width="2.5"/>
        <circle cx="32" cy="14" r="5.5" stroke="currentColor" stroke-width="2.5"/>
        <circle cx="47.4" cy="23" r="5.5" stroke="currentColor" stroke-width="2.5"/>
        <circle cx="47.4" cy="41" r="5.5" stroke="currentColor" stroke-width="2.5"/>
        <circle cx="16.6" cy="41" r="5.5" stroke="currentColor" stroke-width="2.5"/>
        <circle cx="16.6" cy="23" r="5.5" stroke="currentColor" stroke-width="2.5"/>
      </svg>
      <div>${label}</div>
    </div>
  `;
}
