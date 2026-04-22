(function () {
  const getCsrfToken = () => document.querySelector('meta[name="csrf-token"]')?.content || '';

  // Auto-dismiss flash messages after 6s
  document.querySelectorAll('.flash').forEach(el => {
    setTimeout(() => el.remove(), 6000);
  });

  window.showGlobalFlash = function (message, type = 'info') {
    window.scrollTo({ top: 0, behavior: 'smooth' });
    let stack = document.querySelector('.flash-stack');
    if (!stack) {
      stack = document.createElement('div');
      stack.className = 'flash-stack';
      document.querySelector('.main-content')?.prepend(stack);
    }
    const div = document.createElement('div');
    div.className = `flash flash-${type}`;
    div.innerHTML = `<span>${message}</span><button class="flash-close" onclick="this.parentElement.remove()">✕</button>`;
    stack.prepend(div);
    setTimeout(() => div.remove(), 6000);
  };

  // Inject hidden CSRF token in all POST forms if not already present.
  document.querySelectorAll('form[method="post"], form[method="POST"]').forEach(form => {
    if (form.querySelector('input[name="csrf_token"]')) return;
    const input = document.createElement('input');
    input.type = 'hidden';
    input.name = 'csrf_token';
    input.value = getCsrfToken();
    form.appendChild(input);
  });

  // Patch fetch globally for same-origin unsafe methods.
  const originalFetch = window.fetch?.bind(window);
  if (originalFetch) {
    window.fetch = function (input, init = {}) {
      const request = new Request(input, init);
      const method = (request.method || 'GET').toUpperCase();
      const unsafe = ['POST', 'PUT', 'PATCH', 'DELETE'].includes(method);
      const url = new URL(request.url, window.location.origin);
      const sameOrigin = url.origin === window.location.origin;

      if (unsafe && sameOrigin) {
        const headers = new Headers(init.headers || request.headers || {});
        if (!headers.has('X-CSRF-Token')) {
          headers.set('X-CSRF-Token', getCsrfToken());
        }
        init.headers = headers;
      }
      return originalFetch(input, init);
    };
  }
})();
