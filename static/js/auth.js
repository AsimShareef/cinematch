// Login / register form handling

async function handleLogin(email, password, errorEl) {
  const { ok, body } = await apiFetch('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });

  if (ok) {
    setSession(body);
    window.location.href = '/';
  } else {
    errorEl.textContent = (body && body.error) || 'Login failed.';
  }
}

async function handleRegister(username, email, password, errorEl) {
  const { ok, body } = await apiFetch('/auth/register', {
    method: 'POST',
    body: JSON.stringify({ username, email, password }),
  });

  if (ok) {
    setSession(body);
    window.location.href = '/';
  } else {
    errorEl.textContent = (body && body.error) || 'Registration failed.';
  }
}
