from __future__ import annotations
import io
from functools import wraps

from flask import (abort, current_app, flash, jsonify, redirect,
                   render_template, request, send_file, url_for)
from flask_login import current_user, login_required

from .  import main_bp
from ..services.data_models import from_form, weekly_from_form
from ..services.travel_template_service import TravelTemplateService
from ..services.weekly_program_service import WeeklyProgramTemplateService
from ..services.presets_service import list_presets, get_preset, upsert_preset, delete_preset
from ..validation import validate_form, validate_weekly
from ..models import BiReport
from ..email_service import send_document


def require_view(module: str):
    def decorator(f):
        @wraps(f)
        def inner(*args, **kwargs):
            if not current_user.can_view(module):
                abort(403)
            return f(*args, **kwargs)
        return inner
    return decorator


def require_write(module: str):
    def decorator(f):
        @wraps(f)
        def inner(*args, **kwargs):
            if not current_user.can_write(module):
                abort(403)
            return f(*args, **kwargs)
        return inner
    return decorator


# ── Home ──────────────────────────────────────────────────────────────────────
@main_bp.get('/')
@login_required
def index():
    return render_template('main/home.html')


# ── Helpers comuni ────────────────────────────────────────────────────────────
def _is_fetch():
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'


def _json_errors(errors):
    return jsonify({'ok': False, 'errors': errors}), 422


def _travel_template_path():
    return current_app.config['BASE_DIR'] / 'templates_excel' / 'Trasferta_template.xlsx'


def _weekly_template_path():
    return current_app.config['WEEKLY_TEMPLATE_XLSX']


# ── Modulo Trasferta — pagina ─────────────────────────────────────────────────
@main_bp.get('/trasferta')
@login_required
@require_view('travel_form')
def travel_form():
    presets = list_presets(preset_type='travel')
    return render_template('main/travel_form.html', presets=presets,
                           form_data=_default_travel())


# ── Genera trasferta (download) ───────────────────────────────────────────────
@main_bp.post('/trasferta/genera')
@login_required
@require_write('travel_form')
def generate_travel():
    data = from_form(request.form)
    errors = validate_form(data)
    if errors:
        return (_json_errors(errors) if _is_fetch()
                else (_flash_errors(errors) or render_template(
                    'main/travel_form.html', presets=list_presets('travel'),
                    form_data=request.form.to_dict())))

    xlsx_bytes, filename, err = _build_travel(data)
    if err:
        return (jsonify({'ok': False, 'errors': [err]}), 500) if _is_fetch() else (
            flash(err, 'error') or render_template(
                'main/travel_form.html', presets=list_presets('travel'),
                form_data=request.form.to_dict()))

    return send_file(io.BytesIO(xlsx_bytes),
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True, download_name=filename)


# ── Invia trasferta via email (+ opzionalmente scarica) ───────────────────────
@main_bp.post('/trasferta/invia')
@login_required
@require_write('travel_form')
def send_travel():
    data = from_form(request.form)
    errors = validate_form(data)

    to_email     = (request.form.get('to_email') or '').strip().lower()
    to_name      = (request.form.get('to_name') or '').strip()
    subject      = (request.form.get('email_subject') or '').strip()
    message      = (request.form.get('email_message') or '').strip()
    also_download = request.form.get('also_download') == '1'

    if not to_email or '@' not in to_email:
        errors.append('Inserisci un indirizzo email destinatario valido.')
    if not subject:
        errors.append('L\'oggetto email è obbligatorio.')

    if errors:
        return _json_errors(errors)

    xlsx_bytes, filename, err = _build_travel(data)
    if err:
        return jsonify({'ok': False, 'errors': [err]}), 500

    ok = send_document(
        to_email=to_email, to_name=to_name or to_email,
        subject=subject, user_message=message,
        sender_name=current_user.name,
        file_bytes=xlsx_bytes, filename=filename,
    )
    if not ok:
        return jsonify({'ok': False, 'errors': ['Errore nell\'invio dell\'email. Controlla la configurazione Brevo.']}), 500

    if also_download:
        # Restituisce il file; il JS lo scarica e poi mostra il flash
        resp = send_file(io.BytesIO(xlsx_bytes),
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                         as_attachment=True, download_name=filename)
        resp.headers['X-Email-Sent'] = '1'
        return resp

    return jsonify({'ok': True, 'message': f'Email inviata a {to_email} ✓'})


# ── Preset trasferta ──────────────────────────────────────────────────────────
@main_bp.get('/trasferta/preset/<int:preset_id>')
@login_required
@require_view('travel_form')
def get_travel_preset(preset_id: int):
    p = get_preset(preset_id)
    return jsonify(p) if p else (jsonify({'error': 'not found'}), 404)


@main_bp.post('/trasferta/preset')
@login_required
@require_write('travel_form')
def save_travel_preset():
    body = request.get_json(force=True)
    pid  = upsert_preset(name=body.get('name', '').strip(),
                         payload=body.get('payload', {}),
                         preset_type='travel', preset_id=body.get('id'))
    return jsonify({'id': pid})


@main_bp.delete('/trasferta/preset/<int:preset_id>')
@login_required
@require_write('travel_form')
def delete_travel_preset(preset_id: int):
    delete_preset(preset_id)
    return jsonify({'ok': True})


# ── Programma Settimanale — pagina ────────────────────────────────────────────
@main_bp.get('/settimanale')
@login_required
@require_view('weekly_program')
def weekly_program():
    from ..models import WeeklySchedule
    from flask import session
    presets  = list_presets(preset_type='weekly')
    schedule = WeeklySchedule.query.filter_by(user_id=current_user.id).first()
    # Leggi prefill da session (arriva dal link "modifica" dell'email)
    prefill  = session.pop('weekly_prefill', None)
    form_data = prefill or _default_weekly()
    return render_template('main/weekly_program.html', presets=presets,
                           form_data=form_data, schedule=schedule)


# ── Genera settimanale (download) ─────────────────────────────────────────────
@main_bp.post('/settimanale/genera')
@login_required
@require_write('weekly_program')
def generate_weekly():
    data = weekly_from_form(request.form)
    errors = validate_weekly(data)
    if errors:
        return (_json_errors(errors) if _is_fetch()
                else (_flash_errors(errors) or render_template(
                    'main/weekly_program.html', presets=list_presets('weekly'),
                    form_data=request.form.to_dict())))

    xlsx_bytes, filename, err = _build_weekly(data)
    if err:
        return (jsonify({'ok': False, 'errors': [err]}), 500) if _is_fetch() else (
            flash(err, 'error') or render_template(
                'main/weekly_program.html', presets=list_presets('weekly'),
                form_data=request.form.to_dict()))

    return send_file(io.BytesIO(xlsx_bytes),
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True, download_name=filename)


# ── Invia settimanale via email ───────────────────────────────────────────────
@main_bp.post('/settimanale/invia')
@login_required
@require_write('weekly_program')
def send_weekly():
    data = weekly_from_form(request.form)
    errors = validate_weekly(data)

    to_email      = (request.form.get('to_email') or '').strip().lower()
    to_name       = (request.form.get('to_name') or '').strip()
    subject       = (request.form.get('email_subject') or '').strip()
    message       = (request.form.get('email_message') or '').strip()
    also_download = request.form.get('also_download') == '1'

    if not to_email or '@' not in to_email:
        errors.append('Inserisci un indirizzo email destinatario valido.')
    if not subject:
        errors.append('L\'oggetto email è obbligatorio.')

    if errors:
        return _json_errors(errors)

    xlsx_bytes, filename, err = _build_weekly(data)
    if err:
        return jsonify({'ok': False, 'errors': [err]}), 500

    ok = send_document(
        to_email=to_email, to_name=to_name or to_email,
        subject=subject, user_message=message,
        sender_name=current_user.name,
        file_bytes=xlsx_bytes, filename=filename,
    )
    if not ok:
        return jsonify({'ok': False, 'errors': ['Errore nell\'invio. Controlla configurazione Brevo.']}), 500

    if also_download:
        resp = send_file(io.BytesIO(xlsx_bytes),
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                         as_attachment=True, download_name=filename)
        resp.headers['X-Email-Sent'] = '1'
        return resp

    return jsonify({'ok': True, 'message': f'Email inviata a {to_email} ✓'})


# ── Preset settimanale ────────────────────────────────────────────────────────
@main_bp.get('/settimanale/preset/<int:preset_id>')
@login_required
@require_view('weekly_program')
def get_weekly_preset(preset_id: int):
    p = get_preset(preset_id)
    return jsonify(p) if p else (jsonify({'error': 'not found'}), 404)


@main_bp.post('/settimanale/preset')
@login_required
@require_write('weekly_program')
def save_weekly_preset():
    body = request.get_json(force=True)
    pid  = upsert_preset(name=body.get('name', '').strip(),
                         payload=body.get('payload', {}),
                         preset_type='weekly', preset_id=body.get('id'))
    return jsonify({'id': pid})


@main_bp.delete('/settimanale/preset/<int:preset_id>')
@login_required
@require_write('weekly_program')
def delete_weekly_preset(preset_id: int):
    delete_preset(preset_id)
    return jsonify({'ok': True})


# ── Dashboard BI ──────────────────────────────────────────────────────────────
@main_bp.get('/dashboard')
@login_required
@require_view('dashboard_bi')
def dashboard_bi():
    reports = BiReport.query.filter_by(is_active=True).order_by(BiReport.position, BiReport.name).all()
    return render_template('main/dashboard_bi.html', reports=reports)


# ── Builder interni ───────────────────────────────────────────────────────────
def _build_travel(data):
    """Genera il file trasferta. Ritorna (bytes, filename, error_str|None)."""
    try:
        svc   = TravelTemplateService(_travel_template_path())
        bytes = svc.generate_bytes(data)
        return bytes, f'{data.safe_filename_base}.xlsx', None
    except Exception as exc:
        return None, None, str(exc)


def _build_weekly(data):
    """Genera il file settimanale. Ritorna (bytes, filename, error_str|None)."""
    import tempfile, os
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            svc    = WeeklyProgramTemplateService(_weekly_template_path())
            result = svc.generate(data, tmpdir)
            with open(result['xlsx'], 'rb') as f:
                bytes = f.read()
            return bytes, os.path.basename(result['xlsx']), None
    except Exception as exc:
        return None, None, str(exc)


def _flash_errors(errors):
    for e in errors:
        flash(e, 'error')
    return None  # sempre None così il chiamante può fare `or render_template`


# ── Default payloads ──────────────────────────────────────────────────────────
def _default_travel() -> dict:
    return {
        'travel_type': 'mista', 'start_date': '', 'end_date': '',
        'full_name': '', 'employee_id': '', 'business_line': '',
        'cost_center': '', 'hiring_location': '', 'travel_reason': '',
        'pickup_location': '', 'pickup_date': '', 'pickup_time': '',
        'dropoff_location': '', 'dropoff_date': '', 'dropoff_time': '',
        'vehicle_category': '', 'employee_signature_name': '', 'employee_signature_date': '',
        'transfers': [{'from_location': '', 'to_location': '', 'travel_date': '',
                       'departure_time': '', 'transport': '', 'notes': ''}],
        'stays': [{'location': '', 'check_in': '', 'check_out': ''}],
    }


def _default_weekly() -> dict:
    return {
        'full_name': '', 'start_date': '', 'end_date': '',
        'day_location_1': '', 'day_location_2': '', 'day_location_3': '',
        'day_location_4': '', 'day_location_5': '',
    }


# ── Schedulazione Programma Settimanale ──────────────────────────────────────
# Helper per calcolare lun/ven della settimana prossima
def _next_week_monday_friday():
    """Restituisce (monday, friday) della settimana successiva a oggi."""
    from datetime import date, timedelta
    today = date.today()
    # Giorni al prossimo lunedì (se oggi è lun=0, prossimo lun è +7)
    days_to_monday = (7 - today.weekday()) % 7
    if days_to_monday == 0:
        days_to_monday = 7
    next_monday = today + timedelta(days=days_to_monday)
    next_friday  = next_monday + timedelta(days=4)
    return next_monday, next_friday


def _build_weekly_from_schedule(schedule) -> tuple:
    """Genera Excel da uno WeeklySchedule con date settimana prossima."""
    from ..services.data_models import WeeklyProgramData
    next_monday, next_friday = _next_week_monday_friday()
    data = WeeklyProgramData(
        full_name     = schedule.full_name,
        start_date    = next_monday,
        end_date      = next_friday,
        day_locations = schedule.day_locations,
    )
    return _build_weekly(data)


# ── GET/POST /settimanale/schedulazione ──────────────────────────────────────
@main_bp.get('/settimanale/schedulazione')
@login_required
@require_view('weekly_program')
def weekly_schedule_view():
    from ..models import WeeklySchedule
    schedule = WeeklySchedule.query.filter_by(user_id=current_user.id).first()
    presets  = list_presets(preset_type='weekly')
    return render_template('main/weekly_program.html',
                           presets=presets,
                           form_data=_default_weekly(),
                           schedule=schedule)


@main_bp.post('/settimanale/schedulazione/salva')
@login_required
@require_write('weekly_program')
def weekly_schedule_save():
    """Salva / aggiorna la configurazione della schedulazione."""
    from ..models import WeeklySchedule
    from .. import db

    schedule = WeeklySchedule.query.filter_by(user_id=current_user.id).first()
    if not schedule:
        schedule = WeeklySchedule(user_id=current_user.id)
        db.session.add(schedule)

    schedule.full_name      = request.form.get('sched_full_name', '').strip()
    schedule.day_location_1 = request.form.get('sched_day_1', '').strip()
    schedule.day_location_2 = request.form.get('sched_day_2', '').strip()
    schedule.day_location_3 = request.form.get('sched_day_3', '').strip()
    schedule.day_location_4 = request.form.get('sched_day_4', '').strip()
    schedule.day_location_5 = request.form.get('sched_day_5', '').strip()
    schedule.active         = request.form.get('sched_active') == '1'

    db.session.commit()
    flash('Schedulazione salvata.' + (' Attiva ✓' if schedule.active else ' Disattivata.'), 'success')
    return redirect(url_for('main.weekly_program'))


@main_bp.post('/settimanale/schedulazione/toggle')
@login_required
@require_write('weekly_program')
def weekly_schedule_toggle():
    """Attiva/disattiva la schedulazione via AJAX."""
    from ..models import WeeklySchedule
    from .. import db

    schedule = WeeklySchedule.query.filter_by(user_id=current_user.id).first()
    if not schedule:
        return jsonify({'ok': False, 'error': 'Schedulazione non configurata'}), 404

    schedule.active = not schedule.active
    db.session.commit()
    return jsonify({'ok': True, 'active': schedule.active})


# ── GET /settimanale/conferma/<token> ─────────────────────────────────────────
@main_bp.get('/settimanale/conferma/<token>')
def weekly_schedule_confirm(token: str):
    """
    L'utente clicca "Sì, invia" nell'email del mercoledì.
    Genera l'Excel con le date della settimana prossima e lo invia.
    """
    from ..models import WeeklySchedule
    from .. import db
    from ..email_service import send_weekly_schedule_done
    from datetime import datetime

    schedule = WeeklySchedule.query.filter_by(confirm_token=token).first()
    if not schedule:
        return render_template('main/schedule_feedback.html',
                               success=False,
                               message='Link non valido o già utilizzato.')

    if not schedule.is_token_valid():
        return render_template('main/schedule_feedback.html',
                               success=False,
                               message='Il link è scaduto. Riceverai una nuova email mercoledì prossimo.')

    # Genera Excel
    next_monday, next_friday = _next_week_monday_friday()
    xlsx_bytes, filename, err = _build_weekly_from_schedule(schedule)
    if err:
        return render_template('main/schedule_feedback.html',
                               success=False,
                               message=f'Errore nella generazione del file: {err}')

    # Invia email
    ok = send_weekly_schedule_done(
        to_email    = schedule.user.email,
        to_name     = schedule.user.name,
        filename    = filename,
        file_bytes  = xlsx_bytes,
        next_monday = next_monday,
        next_friday = next_friday,
    )
    if not ok:
        return render_template('main/schedule_feedback.html',
                               success=False,
                               message='Errore nell\'invio email. Controlla la configurazione.')

    # Invalida il token (usa UUID unico → rigenera)
    schedule.last_sent_at = datetime.utcnow()
    schedule.refresh_token()   # nuovo token per la prossima settimana
    db.session.commit()

    lun = next_monday.strftime('%d/%m/%Y')
    ven = next_friday.strftime('%d/%m/%Y')
    return render_template('main/schedule_feedback.html',
                           success=True,
                           message=f'Programma inviato a {schedule.user.email} ✓',
                           detail=f'Settimana {lun} — {ven}')


# ── GET /settimanale/modifica/<token> ─────────────────────────────────────────
@main_bp.get('/settimanale/modifica/<token>')
def weekly_schedule_modify(token: str):
    """
    L'utente clicca "No, modifica" nell'email del mercoledì.
    Reindirizza al form con dati pre-compilati dallo schedule.
    La schedulazione rimane attiva per la settimana successiva.
    """
    from ..models import WeeklySchedule
    schedule = WeeklySchedule.query.filter_by(confirm_token=token).first()
    if not schedule or not schedule.is_token_valid():
        # Token scaduto/invalido — porta al form vuoto
        flash('Il link è scaduto o non valido. Compila il form manualmente.', 'warning')
        return redirect(url_for('main.weekly_program'))

    # Pre-compila il form con i dati dello schedule + date settimana prossima
    next_monday, next_friday = _next_week_monday_friday()
    form_data = {
        'full_name':      schedule.full_name,
        'start_date':     next_monday.isoformat(),
        'end_date':       next_friday.isoformat(),
        'day_location_1': schedule.day_location_1,
        'day_location_2': schedule.day_location_2,
        'day_location_3': schedule.day_location_3,
        'day_location_4': schedule.day_location_4,
        'day_location_5': schedule.day_location_5,
    }
    # Usa session per passare i dati pre-compilati
    from flask import session
    session['weekly_prefill'] = form_data
    flash('Modifica i dati e poi scarica o invia il programma.', 'info')
    return redirect(url_for('main.weekly_program'))


# ── GET /main/api/cron/weekly-schedule ────────────────────────────────────────
@main_bp.get('/api/cron/weekly-schedule')
def cron_weekly_schedule():
    """
    Chiamato da cron-job.org ogni mercoledì alle 14:00 (13:00 UTC).
    Invia il reminder di conferma a tutti gli utenti con schedule attivo.
    """
    secret = current_app.config.get('CRON_SECRET', '')
    if secret and request.args.get('secret') != secret:
        return jsonify({'error': 'unauthorized'}), 401

    from ..models import WeeklySchedule
    from ..email_service import send_weekly_schedule_reminder
    from .. import db
    from datetime import datetime

    schedules = WeeklySchedule.query.filter_by(active=True).all()
    sent = 0
    skipped = 0
    errors = []

    next_monday, next_friday = _next_week_monday_friday()

    for sched in schedules:
        if sched.already_reminded_this_week():
            skipped += 1
            continue

        if not sched.user:
            continue

        # Rigenera token per questa settimana
        sched.refresh_token()
        sched.last_reminded_at = datetime.utcnow()
        db.session.flush()

        confirm_url = url_for('main.weekly_schedule_confirm',
                              token=sched.confirm_token, _external=True)
        modify_url  = url_for('main.weekly_schedule_modify',
                              token=sched.confirm_token, _external=True)

        try:
            ok = send_weekly_schedule_reminder(
                to_email    = sched.user.email,
                to_name     = sched.user.name,
                schedule    = sched,
                next_monday = next_monday,
                next_friday = next_friday,
                confirm_url = confirm_url,
                modify_url  = modify_url,
            )
            if ok:
                sent += 1
            else:
                errors.append(f'{sched.user.email}: invio fallito')
        except Exception as exc:
            errors.append(f'{sched.user.email}: {exc}')

    db.session.commit()

    return jsonify({
        'ok':      True,
        'sent':    sent,
        'skipped': skipped,
        'errors':  errors,
        'next_week': f'{next_monday.isoformat()} — {next_friday.isoformat()}',
    })
