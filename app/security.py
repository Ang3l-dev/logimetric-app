from __future__ import annotations

import secrets
import time
from collections import defaultdict, deque
from typing import Iterable
from urllib.parse import urljoin, urlparse

from flask import current_app, jsonify, request, session, url_for


_CSRF_SESSION_KEY = '_csrf_token'
_rate_buckets: dict[str, deque[float]] = defaultdict(deque)


def generate_csrf_token() -> str:
    token = session.get(_CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[_CSRF_SESSION_KEY] = token
    return token


def validate_csrf_request() -> bool:
    expected = session.get(_CSRF_SESSION_KEY)
    supplied = (
        request.headers.get('X-CSRF-Token')
        or request.form.get('csrf_token')
        or request.headers.get('X-Csrftoken')
    )
    return bool(expected and supplied and secrets.compare_digest(str(expected), str(supplied)))


def csrf_error_response(message: str = 'Sessione non valida o token CSRF mancante.'):
    wants_json = (
        request.path.startswith('/api/')
        or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
        or 'application/json' in (request.headers.get('Accept') or '')
    )
    if wants_json:
        return jsonify({'ok': False, 'error': message}), 400
    return message, 400


def is_safe_redirect_target(target: str | None) -> bool:
    if not target:
        return False
    ref = urlparse(request.host_url)
    test = urlparse(urljoin(request.host_url, target))
    return test.scheme in ('http', 'https') and ref.netloc == test.netloc


# Simpler and clearer variant for common use.
def safe_redirect_target(target: str | None, fallback_endpoint: str = 'main.index') -> str:
    if target and is_safe_redirect_target(target):
        return target
    return url_for(fallback_endpoint)


class SimpleRateLimiter:
    def __init__(self, max_attempts: int, window_seconds: int):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds

    def hit(self, key: str) -> tuple[bool, int]:
        now = time.time()
        bucket = _rate_buckets[key]
        cutoff = now - self.window_seconds
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= self.max_attempts:
            retry_after = max(1, int(self.window_seconds - (now - bucket[0])))
            return False, retry_after
        bucket.append(now)
        return True, 0


DEFAULT_CSRF_EXEMPT_ENDPOINTS = {
    'tasks.respond_submit',
    'tasks.api_update',
    'tasks.api_update_by_id',
    'tasks.api_task_update_powerapp',
    'tasks.api_helper',
    'tasks.cron_reminders',

}


def should_enforce_csrf(method: str, endpoint: str | None, additional_exempt: Iterable[str] | None = None) -> bool:
    if method not in {'POST', 'PUT', 'PATCH', 'DELETE'}:
        return False
    exempt = set(DEFAULT_CSRF_EXEMPT_ENDPOINTS)
    if additional_exempt:
        exempt.update(additional_exempt)
    return bool(endpoint) and endpoint not in exempt
