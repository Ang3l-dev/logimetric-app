from __future__ import annotations

import logging
import requests
from flask import current_app

log = logging.getLogger(__name__)

TELEGRAM_SEND_URL = 'https://api.telegram.org/bot{token}/sendMessage'


def _enabled() -> bool:
    return current_app.config.get('TELEGRAM_ENABLED', False) and bool(current_app.config.get('TELEGRAM_BOT_TOKEN', '') and current_app.config.get('TELEGRAM_CHAT_ID', ''))


def send_telegram_message(text: str, *, disable_preview: bool = True) -> bool:
    token = current_app.config.get('TELEGRAM_BOT_TOKEN', '')
    chat_id = current_app.config.get('TELEGRAM_CHAT_ID', '')
    if not _enabled():
        log.info('Telegram disabled or missing credentials.')
        return False
    try:
        resp = requests.post(
            TELEGRAM_SEND_URL.format(token=token),
            json={
                'chat_id': chat_id,
                'text': text,
                'disable_web_page_preview': disable_preview,
            },
            timeout=15,
        )
        if not resp.ok:
            log.error('Telegram error %s: %s', resp.status_code, resp.text)
        return resp.ok
    except Exception as exc:
        log.error('Telegram request failed: %s', exc)
        return False


def send_task_update_notification(task, *, action: str, actor_name: str = '', actor_email: str = '', old_status: str = '', new_status: str = '', note: str = '', source: str = '', extra_lines: list[str] | None = None) -> bool:
    title = (task.title or '').strip()
    due = task.due_date.strftime('%d/%m/%Y') if getattr(task, 'due_date', None) else '—'
    category = task.category.name if getattr(task, 'category', None) else '—'
    actor = actor_name or actor_email or 'Sistema'
    lines = [
        '🔔 LogiMetric — aggiornamento task',
        f'Task #{task.id}: {title}',
        f'Azione: {action}',
        f'Categoria: {category}',
        f'Priorità: {getattr(task, "priority", "-")}',
        f'Stato attuale: {getattr(task, "status", "-")}',
        f'Scadenza: {due}',
        f'Attore: {actor}',
    ]
    if old_status or new_status:
        lines.append(f'Stato: {old_status or "—"} → {new_status or getattr(task, "status", "—")}')
    if source:
        lines.append(f'Origine: {source}')
    if note:
        compact_note = ' '.join(note.split())
        if len(compact_note) > 300:
            compact_note = compact_note[:297] + '...'
        lines.append(f'Nota: {compact_note}')
    if extra_lines:
        lines.extend([line for line in extra_lines if line])
    app_url = current_app.config.get('APP_BASE_URL', '').rstrip('/')
    if app_url:
        lines.append(f'Apri task: {app_url}/tasks/{task.id}')
    return send_telegram_message('\n'.join(lines))



def send_task_deadline_alert(*, overdue_tasks: list, due_today_tasks: list, due_tomorrow_tasks: list) -> bool:
    total = len(overdue_tasks) + len(due_today_tasks) + len(due_tomorrow_tasks)
    if total == 0:
        return False

    def _fmt(prefix: str, tasks: list) -> list[str]:
        rows: list[str] = []
        for task in tasks[:10]:
            due = task.due_date.strftime('%d/%m/%Y') if getattr(task, 'due_date', None) else '—'
            rows.append(f'{prefix} #{task.id} {task.title} [{task.status}] — {due}')
        return rows

    lines = [
        '⏰ LogiMetric — alert scadenze task',
        f'Scaduti: {len(overdue_tasks)}',
        f'In scadenza oggi: {len(due_today_tasks)}',
        f'In scadenza domani: {len(due_tomorrow_tasks)}',
    ]
    lines.extend(_fmt('🔴', overdue_tasks))
    lines.extend(_fmt('🟠', due_today_tasks))
    lines.extend(_fmt('🟡', due_tomorrow_tasks))
    app_url = current_app.config.get('APP_BASE_URL', '').rstrip('/')
    if app_url:
        lines.append(f'Board task: {app_url}/tasks')
    return send_telegram_message('\n'.join(lines))
