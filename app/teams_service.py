from __future__ import annotations

import logging
from datetime import date, datetime
from html import unescape
from typing import Any

import requests
from flask import current_app, url_for

from .models import TASK_PRIORITY_LABELS, TASK_STATUS_LABELS, Task
from .tasks.utils import build_powerapp_task_url

log = logging.getLogger(__name__)


def _safe_str(value: Any) -> str:
    if value is None:
        return ''
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value).strip()


def _display_date(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime('%d/%m/%Y %H:%M')
    if isinstance(value, date):
        return value.strftime('%d/%m/%Y')
    return '—'


def _relay_url(task_id: int) -> str:
    try:
        return url_for('tasks.open_in_powerapp', task_id=task_id, _external=True)
    except Exception:
        base = (current_app.config.get('APP_BASE_URL') or '').rstrip('/')
        return f'{base}/tasks/open/{task_id}' if base else ''


def _payload_for_task(task: Task, recipient_email: str, *, action: str = 'new_task') -> dict:
    powerapp_url = build_powerapp_task_url(task.id) or ''
    relay_url = _relay_url(task.id)
    priority_label = TASK_PRIORITY_LABELS.get(task.priority, task.priority or '')
    status_label = TASK_STATUS_LABELS.get(task.status, task.status or '')

    return {
        'event': action,
        'recipient_email': (recipient_email or '').strip().lower(),
        'task_id': task.id,
        'task_ref': f'TASK-{task.id}',
        'title': task.title or '',
        'description': task.description or '',
        'category': task.category.name if task.category else '',
        'priority': task.priority or '',
        'priority_label': priority_label,
        'status': task.status or '',
        'status_label': status_label,
        'start_date': _safe_str(task.start_date),
        'start_date_display': _display_date(task.start_date),
        'due_date': _safe_str(task.due_date),
        'due_date_display': _display_date(task.due_date),
        'created_at': _safe_str(task.created_at),
        'created_by_name': task.created_by_name or '',
        'created_by_email': task.created_by_email or '',
        'powerapp_url': powerapp_url,
        'relay_url': relay_url,
        'open_url': relay_url or powerapp_url,
    }


def _post_to_teams_flow(payload: dict) -> bool:
    flow_url = (current_app.config.get('TEAMS_FLOW_URL') or '').strip()
    if not flow_url:
        log.warning('TEAMS_FLOW_URL non configurato.')
        return False

    headers = {'Content-Type': 'application/json'}
    flow_api_key = (current_app.config.get('TEAMS_FLOW_API_KEY') or '').strip()
    if flow_api_key:
        headers['X-LogiMetric-Key'] = flow_api_key

    timeout = int(current_app.config.get('TEAMS_FLOW_TIMEOUT_SECONDS', 15) or 15)
    try:
        response = requests.post(flow_url, json=payload, headers=headers, timeout=timeout)
        if not response.ok:
            log.error('Teams Flow error %s: %s', response.status_code, response.text[:1000])
        return response.ok
    except Exception as exc:
        log.error('Teams Flow request failed: %s', exc)
        return False


def send_task_teams_notification(task: Task, recipient_email: str, *, action: str = 'new_task') -> bool:
    """
    Invia a Power Automate i dati necessari per pubblicare un messaggio Teams
    diretto all'utente destinatario.

    Il backend non parla direttamente con Microsoft Teams: chiama un flow dedicato
    con trigger HTTP, così non servono permessi Graph/Azure lato Flask.
    """
    if not current_app.config.get('TEAMS_NOTIFICATIONS_ENABLED', False):
        return False

    recipient = (recipient_email or '').strip().lower()
    if not recipient or '@' not in recipient:
        log.warning('Teams notification skipped: recipient non valido: %r', recipient_email)
        return False

    payload = _payload_for_task(task, recipient, action=action)
    return _post_to_teams_flow(payload)


def send_task_teams_notifications(task: Task, recipients: list[str], *, action: str = 'new_task') -> dict:
    """Invia una notifica Teams per ogni destinatario e ritorna un riepilogo."""
    results: dict[str, bool] = {}
    for recipient in recipients or []:
        email = (recipient or '').strip().lower()
        if not email:
            continue
        results[email] = send_task_teams_notification(task, email, action=action)
    return {
        'sent': sum(1 for ok in results.values() if ok),
        'failed': sum(1 for ok in results.values() if not ok),
        'details': results,
    }
