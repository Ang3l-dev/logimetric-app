from __future__ import annotations

from urllib.parse import urlencode

from flask import current_app


def build_powerapp_task_url(task_id: int | None = None, task_token: str | None = None) -> str:
    """Build the Power App deep link for a task if configured."""
    base_url = (current_app.config.get('POWERAPP_URL') or '').strip()
    if not base_url:
        return ''

    param_name = (current_app.config.get('POWERAPP_TASK_ID_PARAM') or 'task_id').strip() or 'task_id'
    token_param_name = (current_app.config.get('POWERAPP_TASK_TOKEN_PARAM') or 'task_token').strip() or 'task_token'

    if task_id is None and not task_token:
        return base_url

    params = {}
    if task_id is not None:
        params[param_name] = str(task_id)
    if task_token:
        params[token_param_name] = str(task_token)

    separator = '&' if '?' in base_url else '?'
    return f"{base_url}{separator}{urlencode(params)}"
