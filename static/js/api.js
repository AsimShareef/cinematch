// Shared API/auth helper used by every page.

const TOKEN_KEY = 'access_token';
const REFRESH_KEY = 'refresh_token';
const USERNAME_KEY = 'username';

function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

function isLoggedIn() {
  return !!getToken();
}

function setSession({ access_token, refresh_token, user }) {
  if (access_token) localStorage.setItem(TOKEN_KEY, access_token);
  if (refresh_token) localStorage.setItem(REFRESH_KEY, refresh_token);
  if (user && user.username) localStorage.setItem(USERNAME_KEY, user.username);
}

function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
  localStorage.removeItem(USERNAME_KEY);
}

function logout() {
  clearSession();
  window.location.href = '/';
}

// Wrapper around fetch() that attaches the JWT and parses JSON.
async function apiFetch(path, options = {}) {
  const headers = Object.assign({ 'Content-Type': 'application/json' }, options.headers || {});
  const token = getToken();
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const response = await fetch(path, Object.assign({}, options, { headers }));

  if (response.status === 401) {
    clearSession();
  }

  let body = null;
  try {
    body = await response.json();
  } catch (e) {
    body = null;
  }

  return { ok: response.ok, status: response.status, body };
}

function requireAuth() {
  if (!isLoggedIn()) {
    window.location.href = '/login';
    return false;
  }
  return true;
}

function updateNavAuthState() {
  const inEls = document.querySelectorAll('#nav-auth-in, .nav-auth-in');
  const outEls = document.querySelectorAll('#nav-auth-out, .nav-auth-out');
  const usernameEls = document.querySelectorAll('.nav-username');

  const loggedIn = isLoggedIn();
  inEls.forEach((el) => (el.style.display = loggedIn ? '' : 'none'));
  outEls.forEach((el) => (el.style.display = loggedIn ? 'none' : ''));

  const username = localStorage.getItem(USERNAME_KEY);
  if (username) {
    usernameEls.forEach((el) => (el.textContent = username));
  }
}

function starRatingHtml(score, max = 5) {
  const rounded = Math.round(score || 0);
  let html = '';
  for (let i = 1; i <= max; i++) {
    html += i <= rounded ? '★' : '☆';
  }
  return html;
}

document.addEventListener('DOMContentLoaded', () => {
  updateNavAuthState();
  const logoutBtn = document.getElementById('logout-btn');
  if (logoutBtn) {
    logoutBtn.addEventListener('click', (e) => {
      e.preventDefault();
      logout();
    });
  }
});
