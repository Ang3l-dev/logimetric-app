from __future__ import annotations
import base64
import logging
from pathlib import Path
import requests
from flask import current_app, url_for

log = logging.getLogger(__name__)
BREVO_SEND_URL = 'https://api.brevo.com/v3/smtp/email'


def _send(to_email: str, to_name: str, subject: str, html: str,
          attachment_bytes: bytes | None = None,
          attachment_name: str | None = None) -> bool:
    api_key     = current_app.config.get('BREVO_API_KEY', '')
    sender_email = current_app.config.get('MAIL_SENDER', '')
    if not api_key or not sender_email:
        log.warning('BREVO_API_KEY o MAIL_SENDER non configurati.')
        return False

    payload: dict = {
        'sender': {'name': 'LogiMetric', 'email': sender_email},
        'to': [{'email': to_email, 'name': to_name or to_email}],
        'subject': subject,
        'htmlContent': html,
    }
    if attachment_bytes and attachment_name:
        payload['attachment'] = [{
            'content': base64.b64encode(attachment_bytes).decode('utf-8'),
            'name': attachment_name,
        }]

    try:
        resp = requests.post(
            BREVO_SEND_URL,
            json=payload,
            headers={'api-key': api_key, 'Content-Type': 'application/json'},
            timeout=15,
        )
        if not resp.ok:
            log.error('Brevo error %s: %s', resp.status_code, resp.text)
        return resp.ok
    except Exception as exc:
        log.error('Brevo request failed: %s', exc)
        return False


def _load_inline_powerapp_icon() -> str:
    try:
        icon_path = Path(current_app.root_path) / 'static' / 'img' / 'powerapp-icon.png'
        if not icon_path.exists():
            return ''
        encoded = base64.b64encode(icon_path.read_bytes()).decode('utf-8')
        return f'data:image/png;base64,{encoded}'
    except Exception:
        return ''

# ── Template HTML base ────────────────────────────────────────────────────────
def _base_template(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="it"><head><meta charset="UTF-8">
<style>
body{{margin:0;padding:0;background:#081120;font-family:'Segoe UI',Arial,sans-serif;color:#edf3fb}}
.wrap{{max-width:580px;margin:40px auto;background:#0d1830;border:1px solid rgba(255,255,255,.08);border-radius:16px;overflow:hidden}}
.header{{background:linear-gradient(135deg,#1fa3ff,#123b6d);padding:28px 32px;text-align:center}}
.header h1{{margin:0;font-size:22px;color:#fff}}.header p{{margin:4px 0 0;font-size:13px;color:rgba(255,255,255,.7)}}
.body{{padding:32px}}.body p{{margin:0 0 16px;color:#aab9d1;line-height:1.6}}
.body strong{{color:#edf3fb}}
.footer{{padding:20px 32px;border-top:1px solid rgba(255,255,255,.06);text-align:center;font-size:12px;color:#4a5c78}}
</style></head><body>
<div class="wrap">
  <div class="header"><h1>LogiMetric</h1><p>Dati, processi, performance.</p></div>
  <div class="body"><p style="font-size:18px;font-weight:700;color:#edf3fb;margin-bottom:20px">{title}</p>{body}</div>
  <div class="footer">LogiMetric &mdash; <a href="https://www.logimetric.eu" style="color:#1fa3ff">www.logimetric.eu</a><br>
  Questa è un'email automatica generata dall'applicazione LogiMetric.</div>
</div></body></html>"""


# ── Email documento con allegato ──────────────────────────────────────────────
def send_document(
    to_email: str,
    to_name: str,
    subject: str,
    user_message: str,
    sender_name: str,
    file_bytes: bytes,
    filename: str,
) -> bool:
    """Invia un documento Excel come allegato email."""
    msg_html = f'<p>{user_message}</p>' if user_message.strip() else ''
    body = f"""
    <p>Ciao,</p>
    {msg_html}
    <p>In allegato trovi il file <strong>{filename}</strong> generato tramite LogiMetric.</p>
    <p style="font-size:13px;color:#4a5c78">Inviato da: <strong>{sender_name}</strong></p>
    """
    return _send(
        to_email=to_email,
        to_name=to_name,
        subject=subject,
        html=_base_template(subject, body),
        attachment_bytes=file_bytes,
        attachment_name=filename,
    )


# ── Email transazionali auth ──────────────────────────────────────────────────
def send_registration_pending(user) -> bool:
    body = f"""
    <p>Ciao <strong>{user.name}</strong>,</p>
    <p>La tua richiesta di registrazione a <strong>LogiMetric</strong> è stata ricevuta.
    Riceverai un'email quando il tuo accesso sarà abilitato dall'amministratore.</p>
    <p style="color:#7cc7ff;font-size:13px">Account: {user.email}</p>
    """
    return _send(user.email, user.name,
                 'Registrazione ricevuta — in attesa di approvazione',
                 _base_template('Registrazione ricevuta ✓', body))


def send_admin_new_registration(admin_email: str, user) -> bool:
    try:
        link = url_for('admin.users', _external=True)
    except Exception:
        link = 'https://www.logimetric.eu/admin/users'
    body = f"""
    <p>Nuovo utente in attesa di approvazione:</p>
    <p><strong>{user.name}</strong><br><span style="color:#7cc7ff">{user.email}</span></p>
    <p><a href="{link}" style="display:inline-block;background:linear-gradient(135deg,#1fa3ff,#59c0ff);
    color:#07111f;padding:12px 24px;border-radius:999px;font-weight:700;text-decoration:none">
    Vai al pannello utenti</a></p>
    """
    return _send(admin_email, 'Admin LogiMetric',
                 f'Nuovo utente registrato: {user.name}',
                 _base_template('Nuovo utente in attesa', body))


def send_account_approved(user) -> bool:
    try:
        link = url_for('auth.login', _external=True)
    except Exception:
        link = 'https://www.logimetric.eu/login'
    body = f"""
    <p>Ciao <strong>{user.name}</strong>,</p>
    <p>Il tuo account <strong>LogiMetric</strong> è stato approvato.</p>
    <p><a href="{link}" style="display:inline-block;background:linear-gradient(135deg,#1fa3ff,#59c0ff);
    color:#07111f;padding:12px 24px;border-radius:999px;font-weight:700;text-decoration:none">
    Accedi a LogiMetric</a></p>
    """
    return _send(user.email, user.name,
                 'Account approvato — benvenuto su LogiMetric',
                 _base_template('Account approvato 🎉', body))


def send_account_rejected(user) -> bool:
    body = f"""
    <p>Ciao <strong>{user.name}</strong>,</p>
    <p>La tua richiesta di registrazione a <strong>LogiMetric</strong> non è stata approvata.</p>
    <p>Per informazioni contatta l'amministratore a
    <a href="mailto:{current_app.config['ADMIN_EMAIL']}" style="color:#1fa3ff">
    {current_app.config['ADMIN_EMAIL']}</a>.</p>
    """
    return _send(user.email, user.name,
                 'Registrazione non approvata — LogiMetric',
                 _base_template('Registrazione non approvata', body))


def send_password_reset(user, reset_url: str) -> bool:
    body = f"""
    <p>Ciao <strong>{user.name}</strong>,</p>
    <p>Hai richiesto il reset della password. Clicca per impostarne una nuova:</p>
    <p><a href="{reset_url}" style="display:inline-block;background:linear-gradient(135deg,#1fa3ff,#59c0ff);
    color:#07111f;padding:12px 24px;border-radius:999px;font-weight:700;text-decoration:none">
    Reimposta password</a></p>
    <p style="font-size:13px;color:#4a5c78">Il link è valido per <strong>1 ora</strong>.</p>
    """
    return _send(user.email, user.name,
                 'Reset password — LogiMetric',
                 _base_template('Reset password', body))


# ── Email task ────────────────────────────────────────────────────────────────
def send_task_notification(to_email, subject: str, tasks: list,
                           template_type: str, extra: dict | None = None) -> bool:
    """
    Invia notifiche task.
    to_email può essere str o list[str].
    template_type: new_task | reminder | weekly_report | external_reply | thread_update
    """
    from .models import TASK_STATUS_LABELS, TASK_PRIORITY_LABELS, TASK_STATUS_COLORS, TASK_PRIORITY_COLORS
    from .tasks.utils import build_powerapp_task_url

    PRIO_BADGE = {
        'critica': '#e05c5c', 'alta': '#f5a623',
        'media': '#1fa3ff',   'bassa': '#4a5c78',
    }
    STATUS_BADGE = {
        'da_fare': '#4a5c78',    'in_corso': '#1fa3ff',
        'in_attesa': '#f5a623',  'completato': '#3dbf7c',
        'annullato': '#555',
    }

    def _truncate(value: str | None, limit: int) -> str:
        value = (value or '').strip()
        if len(value) <= limit:
            return value
        return value[: max(0, limit - 1)].rstrip() + '…'

    def task_row(t):
        pcolor = PRIO_BADGE.get(t.priority, '#888')
        scolor = STATUS_BADGE.get(t.status, '#888')
        due = t.due_date.strftime('%d/%m/%Y') if t.due_date else '—'
        overdue = ' ⚠' if t.is_overdue else ''
        title_preview = _truncate(t.title, 52)
        category_name = _truncate(t.category.name if t.category else '', 28)
        return f"""
        <tr>
          <td style="padding:10px 14px;border-bottom:1px solid rgba(255,255,255,.05);max-width:320px">
            <div style="color:#edf3fb;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:320px">
              #{t.id} — {title_preview}
            </div>
            <span style="display:block;font-size:12px;color:#7a90b0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:320px">{category_name}</span>
          </td>
          <td style="padding:10px 14px;border-bottom:1px solid rgba(255,255,255,.05);text-align:center">
            <span style="background:{pcolor};color:#fff;padding:3px 10px;border-radius:999px;
                         font-size:11px;font-weight:700">
              {TASK_PRIORITY_LABELS.get(t.priority, t.priority).upper()}
            </span>
          </td>
          <td style="padding:10px 14px;border-bottom:1px solid rgba(255,255,255,.05);text-align:center">
            <span style="background:{scolor};color:#fff;padding:3px 10px;border-radius:999px;
                         font-size:11px;font-weight:700">
              {TASK_STATUS_LABELS.get(t.status, t.status)}
            </span>
          </td>
          <td style="padding:10px 14px;border-bottom:1px solid rgba(255,255,255,.05);
                     color:{'#e05c5c' if t.is_overdue else '#aab9d1'};text-align:center;
                     font-weight:{'700' if t.is_overdue else '400'}">
            {due}{overdue}
          </td>
        </tr>"""

    table_header = """
    <table width="100%" cellpadding="0" cellspacing="0"
           style="border-collapse:collapse;margin-top:16px">
      <thead>
        <tr style="background:rgba(255,255,255,.05)">
          <th style="padding:8px 14px;text-align:left;font-size:11px;color:#7a90b0;
                     text-transform:uppercase;letter-spacing:.08em">Task</th>
          <th style="padding:8px 14px;text-align:center;font-size:11px;color:#7a90b0;
                     text-transform:uppercase;letter-spacing:.08em">Priorità</th>
          <th style="padding:8px 14px;text-align:center;font-size:11px;color:#7a90b0;
                     text-transform:uppercase;letter-spacing:.08em">Stato</th>
          <th style="padding:8px 14px;text-align:center;font-size:11px;color:#7a90b0;
                     text-transform:uppercase;letter-spacing:.08em">Scadenza</th>
        </tr>
      </thead>
      <tbody>"""
    table_footer = "</tbody></table>"

    rows = ''.join(task_row(t) for t in tasks)

    if template_type == 'new_task':
        t = tasks[0]
        desc_html = ''
        if t.description:
            desc_preview = _truncate(' '.join(t.description.split()), 180)
            desc_html = f'''<div style="margin-top:14px;padding:14px 16px;background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.06);border-radius:12px;max-width:100%;overflow:hidden">
              <div style="font-size:11px;color:#7a90b0;text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px">Dettaglio task</div>
              <div style="color:#aab9d1;line-height:1.6;word-break:break-word">{desc_preview}</div>
            </div>'''

        # Deep link Power App — aggiunge task_id come parametro URL
        # La Power App legge Param("task_id") e apre direttamente quel task
        deep_link = build_powerapp_task_url(t.id)
        relay_link = url_for('tasks.open_in_powerapp', task_id=t.id, _external=True)

        prio_label  = {'bassa': 'Bassa', 'media': 'Media',
                       'alta': 'Alta', 'critica': '🔴 Critica'}.get(t.priority, t.priority)
        due_str     = t.due_date.strftime('%d/%m/%Y') if t.due_date else '—'

        icon_src = _load_inline_powerapp_icon()
        app_btn = ''
        if deep_link:
            # Bottone Gmail-safe: usa tabella HTML + background-color flat (no gradient)
            # Gmail rimuove linear-gradient ma supporta background-color e border
            icon_html = (f'<img src="{icon_src}" alt="" width="18" height="18" '
                         f'style="vertical-align:middle;margin-right:8px;border:0">'
                         if icon_src else '')
            app_btn = f"""
            <div style="margin-top:24px;text-align:center">
              <p style="margin:0 0 14px;font-size:13px;color:#aab9d1;text-align:center">
                Clicca per aprire direttamente il task nell&apos;app aziendale:
              </p>
              <!--[if mso]>
              <v:roundrect xmlns:v="urn:schemas-microsoft-com:vml"
                xmlns:w="urn:schemas-microsoft-com:office:word"
                href="{relay_link}" style="height:50px;v-text-anchor:middle;width:260px;"
                arcsize="50%" strokecolor="#1fa3ff" fillcolor="#1fa3ff">
                <w:anchorlock/>
                <center style="color:#ffffff;font-family:Arial,sans-serif;font-size:15px;font-weight:bold;">
                  Apri Task #{t.id} in Power App
                </center>
              </v:roundrect>
              <![endif]-->
              <!--[if !mso]><!-->
              <table role="presentation" cellpadding="0" cellspacing="0"
                     style="margin:0 auto;border-collapse:collapse">
                <tr>
                  <td align="center"
                      style="background-color:#1fa3ff;border-radius:999px;
                             padding:0;mso-padding-alt:0">
                    <a href="{relay_link}"
                       target="_blank"
                       style="display:inline-block;background-color:#1fa3ff;
                              color:#ffffff;font-family:Arial,sans-serif;
                              font-size:15px;font-weight:700;line-height:1;
                              padding:15px 32px;border-radius:999px;
                              text-decoration:none;border:2px solid #1fa3ff;
                              -webkit-text-size-adjust:none;mso-hide:all">
                      {icon_html}<span style="vertical-align:middle">Apri Task #{t.id} &rsaquo; Power App</span>
                    </a>
                  </td>
                </tr>
              </table>
              <!--<![endif]-->
              <p style="margin:12px 0 0;font-size:11px;color:#4a5c78;text-align:center">
                Accedi con il tuo account Office 365
              </p>
              <p style="margin:6px 0 0;font-size:10px;color:#3a4c60;text-align:center">
                Link non funziona?
                <a href="{relay_link}" style="color:#7cc7ff">Clicca qui</a>
              </p>
            </div>"""
        else:
            app_btn = """
            <p style="font-size:12px;color:#4a5c78;margin-top:16px">
              Aggiorna lo stato tramite l'app aziendale
              <strong style="color:#7cc7ff">LogiMetric Task</strong> su Teams o Power Apps.
            </p>"""


        body = f"""
        <p>È stato assegnato un nuovo task che richiede la vostra attenzione:</p>
        {table_header}{rows}{table_footer}
        {desc_html}
        {app_btn}
        <p style="font-size:11px;color:#3a4c60;margin-top:16px;text-align:center">
          Riferimento interno: <strong>[TASK-{t.id}]</strong>
        </p>"""

    elif template_type == 'reminder':
        body = f"""
        <p>Hai <strong>{len(tasks)}</strong> task urgenti (scaduti o in scadenza oggi/domani):</p>
        {table_header}{rows}{table_footer}"""

    elif template_type == 'weekly_report':
        body = f"""
        <p>Riepilogo settimanale — <strong>{len(tasks)}</strong> task aperti:</p>
        {table_header}{rows}{table_footer}"""

    elif template_type == 'external_reply':
        e = extra or {}
        body = f"""
        <p>Hai ricevuto una risposta esterna su un task:</p>
        {table_header}{rows}{table_footer}
        <p style="margin-top:16px"><strong>Da:</strong> {e.get('replied_by','—')}<br>
        <strong>Nuovo stato:</strong> {TASK_STATUS_LABELS.get(e.get('new_status',''), e.get('new_status',''))}<br>
        <strong>Note:</strong> {e.get('note','—')}</p>"""
    elif template_type == 'thread_update':
        e = extra or {}
        body = f"""
        <p>È stato inserito un aggiornamento nel task:</p>
        {table_header}{rows}{table_footer}
        <div style="margin-top:16px;padding:14px 16px;background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.06);border-radius:12px">
          <div style="font-size:11px;color:#7a90b0;text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px">Aggiornamento</div>
          <p style="margin:0 0 8px"><strong>Da:</strong> {e.get('actor_name') or e.get('actor_email') or '—'}</p>
          <p style="margin:0 0 8px"><strong>Stato:</strong> {TASK_STATUS_LABELS.get(e.get('new_status',''), e.get('new_status','—'))}</p>
          <p style="margin:0;color:#aab9d1;white-space:pre-wrap">{e.get('note') or '—'}</p>
        </div>"""
    else:
        body = f"{table_header}{rows}{table_footer}"

    html = _base_template(subject, body)

    if isinstance(to_email, list):
        ok = True
        for email in to_email:
            ok = ok and _send(email, '', subject, html)
        return ok
    return _send(to_email, '', subject, html)


def send_task_helper_response(to_email: str, tasks: list) -> bool:
    """Risponde all'utente helper con lista task — nessun link esterno."""
    from .models import TASK_STATUS_LABELS, TASK_PRIORITY_LABELS

    if not tasks:
        body = """
        <p>Non hai task aperti assegnati alla tua email al momento.</p>
        <p style="font-size:13px;color:#4a5c78">
          Se pensi ci sia un errore, contatta l'amministratore.
        </p>"""
        return _send(to_email, '', 'I tuoi task aperti — LogiMetric',
                     _base_template('Nessun task aperto ✓', body))

    PRIO_BADGE = {'critica':'#e05c5c','alta':'#f5a623','media':'#1fa3ff','bassa':'#4a5c78'}
    STATUS_BADGE = {'da_fare':'#4a5c78','in_corso':'#1fa3ff','in_attesa':'#f5a623',
                    'completato':'#3dbf7c','annullato':'#555'}

    rows = ''
    for t in tasks:
        due = t.due_date.strftime('%d/%m/%Y') if t.due_date else '—'
        overdue_style = 'color:#e05c5c;font-weight:700' if t.is_overdue else 'color:#aab9d1'
        overdue_mark  = ' ⚠ SCADUTO' if t.is_overdue else ''
        pc = PRIO_BADGE.get(t.priority, '#888')
        sc = STATUS_BADGE.get(t.status, '#888')

        rows += f"""
        <tr>
          <td style="padding:12px 14px;border-bottom:1px solid rgba(255,255,255,.05);
                     vertical-align:top">
            <strong style="color:#edf3fb;font-size:14px">
              [TASK-{t.id}] {t.title}
            </strong><br>
            <span style="font-size:12px;color:#7a90b0">
              {t.category.name if t.category else ''}
            </span>
            {f'<br><span style="font-size:12px;color:#aab9d1;white-space:pre-wrap">{t.description[:120]}{"…" if t.description and len(t.description)>120 else ""}</span>' if t.description else ''}
          </td>
          <td style="padding:12px 14px;border-bottom:1px solid rgba(255,255,255,.05);
                     text-align:center;vertical-align:top;white-space:nowrap">
            <span style="background:{pc};color:#fff;padding:3px 9px;border-radius:999px;
                         font-size:11px;font-weight:700">
              {TASK_PRIORITY_LABELS.get(t.priority,'').upper()}
            </span>
          </td>
          <td style="padding:12px 14px;border-bottom:1px solid rgba(255,255,255,.05);
                     text-align:center;vertical-align:top;white-space:nowrap">
            <span style="background:{sc};color:#fff;padding:3px 9px;border-radius:999px;
                         font-size:11px;font-weight:700">
              {TASK_STATUS_LABELS.get(t.status,'')}
            </span>
          </td>
          <td style="padding:12px 14px;border-bottom:1px solid rgba(255,255,255,.05);
                     text-align:center;vertical-align:top;{overdue_style};white-space:nowrap">
            {due}{overdue_mark}
          </td>
        </tr>"""

    body = f"""
    <p>Ecco i tuoi <strong>{len(tasks)}</strong> task aperti:</p>
    <table width="100%" cellpadding="0" cellspacing="0"
           style="border-collapse:collapse;margin-top:16px">
      <thead>
        <tr style="background:rgba(255,255,255,.05)">
          <th style="padding:8px 14px;text-align:left;font-size:11px;color:#7a90b0;
                     text-transform:uppercase;letter-spacing:.08em">Task</th>
          <th style="padding:8px 14px;text-align:center;font-size:11px;color:#7a90b0;
                     text-transform:uppercase;letter-spacing:.08em;white-space:nowrap">Priorità</th>
          <th style="padding:8px 14px;text-align:center;font-size:11px;color:#7a90b0;
                     text-transform:uppercase;letter-spacing:.08em">Stato</th>
          <th style="padding:8px 14px;text-align:center;font-size:11px;color:#7a90b0;
                     text-transform:uppercase;letter-spacing:.08em;white-space:nowrap">Scadenza</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>

    <div style="margin-top:24px;padding:16px;background:rgba(255,255,255,.03);
                border:1px solid rgba(255,255,255,.08);border-radius:10px">
      <p style="margin:0 0 10px;font-weight:700;color:#7cc7ff;font-size:13px">
        ✉ Per aggiornare un task, rispondete all'email originale del task
      </p>
      <p style="margin:0;color:#4a5c78;font-size:12px">
        Usate come prima riga una di queste parole chiave:<br>
        <strong style="color:#3dbf7c">PRESO IN CARICO</strong> &nbsp;·&nbsp;
        <strong style="color:#1fa3ff">IN CORSO</strong> &nbsp;·&nbsp;
        <strong style="color:#f5a623">BLOCCATO</strong> &nbsp;·&nbsp;
        <strong style="color:#3dbf7c">COMPLETATO</strong>
      </p>
    </div>
    <p style="font-size:12px;color:#4a5c78;margin-top:12px">
      Puoi richiedere questo riepilogo una volta al giorno.
    </p>"""

    subject = f'I tuoi task aperti ({len(tasks)}) — LogiMetric'
    return _send(to_email, '', subject, _base_template('I tuoi task aperti', body))

def send_aste_deadline_alert(to_email: str, house, deadlines: list) -> bool:
    """Alert scadenze aste ai partecipanti."""
    rows = ''
    for dl in deadlines:
        due = dl.data_scadenza.strftime('%d/%m/%Y') if dl.data_scadenza else '—'
        color = '#e05c5c' if dl.is_overdue else '#f5a623'
        tipo_lbl = 'Pre-asta' if dl.tipo == 'pre' else 'Post-asta'
        rows += f"""
        <tr>
          <td style="padding:10px 14px;border-bottom:1px solid rgba(255,255,255,.05)">
            <strong style="color:#edf3fb">{dl.titolo}</strong><br>
            <span style="font-size:12px;color:#7a90b0">{tipo_lbl}</span>
          </td>
          <td style="padding:10px 14px;border-bottom:1px solid rgba(255,255,255,.05);
                     color:{color};font-weight:700;text-align:center">
            {due}{'  ⚠ SCADUTA' if dl.is_overdue else ''}
          </td>
        </tr>"""

    body = f"""
    <p>Ci sono scadenze urgenti per la casa:</p>
    <p style="font-size:18px;font-weight:700;color:#edf3fb">
      {house.via}, {house.citta}
      {f'<span style="font-size:14px;color:#7a90b0"> — {house.mq} mq</span>' if house.mq else ''}
    </p>
    <table width="100%" cellpadding="0" cellspacing="0"
           style="border-collapse:collapse;margin-top:16px">
      <thead>
        <tr style="background:rgba(255,255,255,.05)">
          <th style="padding:8px 14px;text-align:left;font-size:11px;color:#7a90b0;
                     text-transform:uppercase">Scadenza</th>
          <th style="padding:8px 14px;text-align:center;font-size:11px;color:#7a90b0;
                     text-transform:uppercase">Data</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
    <p style="font-size:12px;color:#4a5c78;margin-top:16px">
      Accedi a LogiMetric per gestire le scadenze e aggiornare lo stato.
    </p>"""

    subject = f'⚠ Scadenze — {house.via}, {house.citta}'
    return _send(to_email, '', subject, _base_template('Scadenze urgenti', body))


def send_aste_expense_notification(to_email: str, to_name: str,
                                    house, expense, quota_spesa: float,
                                    payer_name: str, saldo: dict) -> bool:
    """Notifica partecipante di una nuova spesa e il suo saldo aggiornato."""
    from .models import EXPENSE_CATS
    cat_label = EXPENSE_CATS.get(expense.categoria, expense.categoria)
    saldo_val = saldo['saldo']
    saldo_color = '#3dbf7c' if saldo_val >= 0 else '#e05c5c'
    saldo_label = (f'Devi ricevere {abs(saldo_val):,.2f} €'.replace(',','X').replace('.',',').replace('X','.')
                   if saldo_val > 0 else
                   f'Devi versare {abs(saldo_val):,.2f} €'.replace(',','X').replace('.',',').replace('X','.'))
    imp_fmt  = lambda v: f'{v:,.2f} €'.replace(',','X').replace('.',',').replace('X','.')

    body = f"""
    <p>Ciao <strong>{to_name}</strong>,</p>
    <p>È stata registrata una nuova spesa per l'immobile
       <strong>{house.via}, {house.citta}</strong>:</p>

    <div style="margin:16px 0;padding:16px 20px;background:rgba(255,255,255,.04);
                border:1px solid rgba(255,255,255,.08);border-radius:12px">
      <div style="display:flex;justify-content:space-between;margin-bottom:8px">
        <span style="color:#7a90b0;font-size:13px">{cat_label}</span>
        <strong style="color:#edf3fb;font-size:18px">{imp_fmt(expense.importo)}</strong>
      </div>
      <div style="color:#aab9d1;font-size:13px">
        {expense.descrizione or ''}<br>
        Pagato da: <strong style="color:#edf3fb">{payer_name}</strong>
      </div>
    </div>

    <table width="100%" cellpadding="0" cellspacing="0"
           style="border-collapse:collapse;margin-top:16px;margin-bottom:20px">
      <tr style="background:rgba(255,255,255,.04)">
        <td style="padding:10px 14px;color:#7a90b0;font-size:12px;
                   text-transform:uppercase;letter-spacing:.08em">Voce</td>
        <td style="padding:10px 14px;color:#7a90b0;font-size:12px;
                   text-transform:uppercase;letter-spacing:.08em;text-align:right">Importo</td>
      </tr>
      <tr>
        <td style="padding:10px 14px;border-bottom:1px solid rgba(255,255,255,.05);color:#aab9d1">
          Tua quota di questa spesa ({house.n_partecipanti} partecipanti)</td>
        <td style="padding:10px 14px;border-bottom:1px solid rgba(255,255,255,.05);
                   text-align:right;font-weight:600;color:#edf3fb">{imp_fmt(quota_spesa)}</td>
      </tr>
      <tr>
        <td style="padding:10px 14px;border-bottom:1px solid rgba(255,255,255,.05);color:#aab9d1">
          Totale da te versato su questo immobile</td>
        <td style="padding:10px 14px;border-bottom:1px solid rgba(255,255,255,.05);
                   text-align:right;font-weight:600;color:#edf3fb">{imp_fmt(saldo['pagato'])}</td>
      </tr>
      <tr>
        <td style="padding:10px 14px;color:#aab9d1">Tua quota equa totale</td>
        <td style="padding:10px 14px;text-align:right;font-weight:600;color:#edf3fb">
          {imp_fmt(saldo['quota'])}</td>
      </tr>
    </table>

    <div style="padding:16px 20px;border-radius:12px;
                background:{saldo_color}15;border:1px solid {saldo_color}40;text-align:center">
      <div style="font-size:13px;color:#7a90b0;margin-bottom:4px">Il tuo saldo netto</div>
      <div style="font-size:22px;font-weight:800;color:{saldo_color}">{saldo_label}</div>
    </div>

    <p style="font-size:12px;color:#4a5c78;margin-top:16px">
      Accedi a LogiMetric → Gestione Aste → La mia scheda per il dettaglio completo.
    </p>"""

    subject = f'💰 Nuova spesa: {imp_fmt(expense.importo)} — {house.via}, {house.citta}'
    return _send(to_email, to_name, subject, _base_template('Nuova spesa registrata', body))


def send_weekly_schedule_reminder(
    to_email: str,
    to_name: str,
    schedule,          # WeeklySchedule instance
    next_monday: 'date',
    next_friday: 'date',
    confirm_url: str,
    modify_url: str,
) -> bool:
    """
    Email del mercoledì: chiede conferma all'utente prima di inviare il programma.
    Contiene due pulsanti: Sì procedi / No, modifica.
    """
    from datetime import date
    lun = next_monday.strftime('%d/%m/%Y')
    ven = next_friday.strftime('%d/%m/%Y')
    days_it = ['Lunedì','Martedì','Mercoledì','Giovedì','Venerdì']
    sedi_html = ''.join(
        f'<tr>'
        f'<td style="padding:7px 14px;border-bottom:1px solid rgba(255,255,255,.05);'
        f'color:#7a90b0;font-size:13px">{days_it[i]}</td>'
        f'<td style="padding:7px 14px;border-bottom:1px solid rgba(255,255,255,.05);'
        f'color:#edf3fb;font-weight:600">{loc or "—"}</td>'
        f'</tr>'
        for i, loc in enumerate(schedule.day_locations)
    )

    body = f"""
    <p>Ciao <strong>{to_name}</strong>,</p>
    <p>È mercoledì — è il momento di inviare il tuo programma settimanale.</p>

    <div style="margin:20px 0;padding:16px 20px;background:rgba(255,255,255,.04);
                border:1px solid rgba(255,255,255,.08);border-radius:12px">
      <div style="font-size:12px;color:#7a90b0;text-transform:uppercase;
                  letter-spacing:.08em;margin-bottom:12px">
        Programma settimana {lun} — {ven}
      </div>
      <div style="font-weight:700;color:#edf3fb;margin-bottom:12px">
        {schedule.full_name}
      </div>
      <table width="100%" cellpadding="0" cellspacing="0"
             style="border-collapse:collapse">
        {sedi_html}
      </table>
    </div>

    <p style="color:#aab9d1;font-size:13px">
      Vuoi che LogiMetric generi e invii automaticamente il file Excel
      con il programma della settimana <strong>{lun}–{ven}</strong>?
    </p>

    <!-- Pulsante SÌ -->
    <table role="presentation" cellpadding="0" cellspacing="0"
           style="margin:20px 0 12px;border-collapse:collapse">
      <tr>
        <td style="background-color:#1fa3ff;border-radius:999px;padding:0">
          <a href="{confirm_url}" target="_blank"
             style="display:inline-block;background-color:#1fa3ff;color:#ffffff;
                    font-family:Arial,sans-serif;font-size:15px;font-weight:700;
                    padding:14px 32px;border-radius:999px;text-decoration:none;
                    border:2px solid #1fa3ff">
            ✅ Sì, invia il programma
          </a>
        </td>
      </tr>
    </table>

    <!-- Pulsante NO -->
    <table role="presentation" cellpadding="0" cellspacing="0"
           style="margin:0;border-collapse:collapse">
      <tr>
        <td style="background-color:#2a3a54;border-radius:999px;
                   border:2px solid #4a5c78;padding:0">
          <a href="{modify_url}" target="_blank"
             style="display:inline-block;background-color:#2a3a54;color:#aab9d1;
                    font-family:Arial,sans-serif;font-size:14px;font-weight:600;
                    padding:12px 28px;border-radius:999px;text-decoration:none">
            ✏️ No, voglio modificare
          </a>
        </td>
      </tr>
    </table>

    <p style="font-size:11px;color:#3a4c60;margin-top:20px">
      I pulsanti scadono giovedì sera. Se non fai niente, mercoledì prossimo
      riceverai di nuovo questa email.
    </p>"""

    subject = f'📋 Programma settimanale {lun}–{ven} — conferma invio'
    return _send(to_email, to_name, subject, _base_template('Programma settimanale', body))


def send_weekly_schedule_done(
    to_email: str,
    to_name: str,
    filename: str,
    file_bytes: bytes,
    next_monday: 'date',
    next_friday: 'date',
) -> bool:
    """Invia il programma Excel confermato."""
    lun = next_monday.strftime('%d/%m/%Y')
    ven = next_friday.strftime('%d/%m/%Y')
    body = f"""
    <p>Ciao <strong>{to_name}</strong>,</p>
    <p>In allegato trovi il tuo programma settimanale generato automaticamente
       per la settimana <strong>{lun} — {ven}</strong>.</p>
    <p style="font-size:12px;color:#4a5c78">
      Generato da LogiMetric — Schedulazione automatica
    </p>"""

    subject = f'Programma settimanale {lun}–{ven}'
    return _send(
        to_email=to_email, to_name=to_name,
        subject=subject,
        html=_base_template('Programma settimanale', body),
        attachment_bytes=file_bytes,
        attachment_name=filename,
    )
