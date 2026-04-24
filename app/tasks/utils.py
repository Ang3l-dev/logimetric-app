from __future__ import annotations

from urllib.parse import urlencode

from flask import current_app


def build_powerapp_task_url(task_id: int | None = None) -> str:
    """Build the Power App deep link for a task if configured."""
    base_url = (current_app.config.get('POWERAPP_URL') or '').strip()
    if not base_url:
        return ''

    param_name = (current_app.config.get('POWERAPP_TASK_ID_PARAM') or 'task_id').strip() or 'task_id'

    if task_id is None:
        return base_url

    separator = '&' if '?' in base_url else '?'
    return f"{base_url}{separator}{urlencode({param_name: str(task_id)})}"
