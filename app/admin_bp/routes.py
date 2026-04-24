from __future__ import annotations
from functools import wraps

from flask import abort, flash, redirect, render_template, request, url_for, jsonify
from flask_login import current_user, login_required

from .. import db
from ..models import User, Permission, MODULES, BiReport, Contact, Task, TaskCategory, TaskEvent, TaskRecipientResponse
from ..email_service import send_account_approved, send_account_rejected
from . import admin_bp


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


# ── Utenti ────────────────────────────────────────────────────────────────────
@admin_bp.get('/users')
@login_required
@admin_required
def users():
    pending  = User.query.filter_by(is_approved=False).order_by(User.created_at).all()
    approved = User.query.filter_by(is_approved=True).order_by(User.name).all()
    return render_template('admin/users.html', pending=pending, approved=approved, modules=MODULES)


@admin_bp.post('/users/<int:user_id>/approve')
@login_required
@admin_required
def approve_user(user_id: int):
    user = User.query.get_or_404(user_id)
    user.is_approved = True
    db.session.commit()
    try: send_account_approved(user)
    except Exception: pass
    flash(f'Account di {user.name} approvato.', 'success')
    return redirect(url_for('admin.users'))


@admin_bp.post('/users/<int:user_id>/reject')
@login_required
@admin_required
def reject_user(user_id: int):
    user = User.query.get_or_404(user_id)
    try: send_account_rejected(user)
    except Exception: pass
    db.session.delete(user)
    db.session.commit()
    flash('Registrazione rifiutata e utente rimosso.', 'info')
    return redirect(url_for('admin.users'))


@admin_bp.post('/users/<int:user_id>/delete')
@login_required
@admin_required
def delete_user(user_id: int):
    user = User.query.get_or_404(user_id)
    if user.is_admin:
        flash('Non puoi eliminare un account amministratore.', 'error')
        return redirect(url_for('admin.users'))
    db.session.delete(user)
    db.session.commit()
    flash(f'Utente {user.name} eliminato.', 'info')
    return redirect(url_for('admin.users'))


@admin_bp.get('/users/<int:user_id>/permissions')
@login_required
@admin_required
def user_permissions(user_id: int):
    user = User.query.get_or_404(user_id)
    perms = user.get_permissions_dict()
    return render_template('admin/user_permissions.html',
                           managed_user=user, perms=perms, modules=MODULES)


@admin_bp.post('/users/<int:user_id>/permissions')
@login_required
@admin_required
def save_permissions(user_id: int):
    user = User.query.get_or_404(user_id)
    for module in MODULES:
        can_view  = bool(request.form.get(f'{module}_view'))
        can_write = bool(request.form.get(f'{module}_write'))
        if can_write: can_view = True
        perm = user.permissions.filter_by(module=module).first()
        if perm is None:
            perm = Permission(user_id=user.id, module=module)
            db.session.add(perm)
        perm.can_view  = can_view
        perm.can_write = can_write
    db.session.commit()
    flash(f'Permessi di {user.name} aggiornati.', 'success')
    return redirect(url_for('admin.users'))


@admin_bp.post('/users/<int:user_id>/permissions/toggle')
@login_required
@admin_required
def toggle_permission(user_id: int):
    user = User.query.get_or_404(user_id)
    data   = request.get_json(force=True)
    module = data.get('module')
    field  = data.get('field')
    if module not in MODULES or field not in ('can_view', 'can_write'):
        return jsonify({'ok': False}), 400
    perm = user.permissions.filter_by(module=module).first()
    if perm is None:
        perm = Permission(user_id=user.id, module=module)
        db.session.add(perm)
    new_val = not getattr(perm, field)
    setattr(perm, field, new_val)
    if field == 'can_view' and not new_val: perm.can_write = False
    if field == 'can_write' and new_val:    perm.can_view  = True
    db.session.commit()
    return jsonify({'ok': True, 'can_view': perm.can_view, 'can_write': perm.can_write})


# ── Rubrica contatti ──────────────────────────────────────────────────────────
@admin_bp.get('/rubrica')
@login_required
@admin_required
def contacts():
    all_contacts = Contact.query.order_by(Contact.name).all()
    return render_template('admin/contacts.html', contacts=all_contacts)


@admin_bp.post('/rubrica')
@login_required
@admin_required
def contacts_save():
    contact_id = request.form.get('contact_id', '').strip()
    name       = request.form.get('name', '').strip()
    email      = request.form.get('email', '').strip().lower()
    notes      = request.form.get('notes', '').strip()

    if not name or not email or '@' not in email:
        flash('Nome e email valida sono obbligatori.', 'error')
        return redirect(url_for('admin.contacts'))

    if contact_id:
        c = Contact.query.get_or_404(int(contact_id))
        existing = Contact.query.filter(Contact.email == email, Contact.id != c.id).first()
        if existing:
            flash(f'Email {email} già presente nella rubrica.', 'error')
            return redirect(url_for('admin.contacts'))
        c.name = name; c.email = email; c.notes = notes
    else:
        if Contact.query.filter_by(email=email).first():
            flash(f'Email {email} già presente nella rubrica.', 'error')
            return redirect(url_for('admin.contacts'))
        c = Contact(name=name, email=email, notes=notes)
        db.session.add(c)

    db.session.commit()
    flash(f'Contatto "{name}" salvato.', 'success')
    return redirect(url_for('admin.contacts'))


@admin_bp.post('/rubrica/<int:contact_id>/toggle')
@login_required
@admin_required
def contact_toggle(contact_id: int):
    c = Contact.query.get_or_404(contact_id)
    c.is_active = not c.is_active
    db.session.commit()
    return jsonify({'ok': True, 'is_active': c.is_active})


@admin_bp.post('/rubrica/<int:contact_id>/delete')
@login_required
@admin_required
def contact_delete(contact_id: int):
    c = Contact.query.get_or_404(contact_id)
    db.session.delete(c)
    db.session.commit()
    flash(f'Contatto "{c.name}" eliminato.', 'info')
    return redirect(url_for('admin.contacts'))


# API JSON per i form (carica rubrica in JS)
@admin_bp.get('/rubrica/json')
@login_required
def contacts_json():
    contacts = Contact.query.filter_by(is_active=True).order_by(Contact.name).all()
    return jsonify([{'id': c.id, 'name': c.name, 'email': c.email} for c in contacts])


# ── Report BI ─────────────────────────────────────────────────────────────────
@admin_bp.get('/bi-reports')
@login_required
@admin_required
def bi_reports():
    reports = BiReport.query.order_by(BiReport.position, BiReport.name).all()
    return render_template('admin/bi_reports.html', reports=reports)


@admin_bp.post('/bi-reports')
@login_required
@admin_required
def bi_reports_save():
    name      = request.form.get('name', '').strip()
    embed_url = request.form.get('embed_url', '').strip()
    position  = int(request.form.get('position', 0) or 0)
    report_id = request.form.get('report_id', '').strip()
    if not name or not embed_url:
        flash('Nome e URL sono obbligatori.', 'error')
        return redirect(url_for('admin.bi_reports'))
    if report_id:
        r = BiReport.query.get_or_404(int(report_id))
        r.name = name; r.embed_url = embed_url; r.position = position
    else:
        r = BiReport(name=name, embed_url=embed_url, position=position)
        db.session.add(r)
    db.session.commit()
    flash(f'Report "{name}" salvato.', 'success')
    return redirect(url_for('admin.bi_reports'))


@admin_bp.post('/bi-reports/<int:report_id>/toggle')
@login_required
@admin_required
def bi_report_toggle(report_id: int):
    r = BiReport.query.get_or_404(report_id)
    r.is_active = not r.is_active
    db.session.commit()
    return jsonify({'ok': True, 'is_active': r.is_active})


@admin_bp.post('/bi-reports/<int:report_id>/delete')
@login_required
@admin_required
def bi_report_delete(report_id: int):
    r = BiReport.query.get_or_404(report_id)
    db.session.delete(r)
    db.session.commit()
    flash(f'Report "{r.name}" eliminato.', 'info')
    return redirect(url_for('admin.bi_reports'))


# ── Categorie Task ────────────────────────────────────────────────────────────
import json as _json


@admin_bp.get('/task-categories')
@login_required
@admin_required
def task_categories():
    cats = TaskCategory.query.order_by(TaskCategory.position, TaskCategory.name).all()
    return render_template('admin/task_categories.html', categories=cats)


@admin_bp.post('/task-categories')
@login_required
@admin_required
def task_categories_save():
    cat_id   = request.form.get('cat_id', '').strip()
    name     = request.form.get('name', '').strip()
    color    = request.form.get('color', '#1fa3ff').strip()
    position = int(request.form.get('position', 0) or 0)
    notify   = bool(request.form.get('notify_on_create'))
    emails_raw = request.form.get('email_recipients', '').strip()
    emails = [e.strip() for e in emails_raw.replace(',', '\n').splitlines() if e.strip() and '@' in e]

    if not name:
        flash('Il nome è obbligatorio.', 'error')
        return redirect(url_for('admin.task_categories'))

    if cat_id:
        c = TaskCategory.query.get_or_404(int(cat_id))
        existing = TaskCategory.query.filter(TaskCategory.name == name, TaskCategory.id != c.id).first()
        if existing:
            flash(f'Categoria "{name}" già esistente.', 'error')
            return redirect(url_for('admin.task_categories'))
        c.name = name; c.color = color; c.position = position
        c.notify_on_create = notify
        c.email_recipients = _json.dumps(emails)
    else:
        if TaskCategory.query.filter_by(name=name).first():
            flash(f'Categoria "{name}" già esistente.', 'error')
            return redirect(url_for('admin.task_categories'))
        c = TaskCategory(name=name, color=color, position=position,
                         notify_on_create=notify,
                         email_recipients=_json.dumps(emails))
        db.session.add(c)

    db.session.commit()
    flash(f'Categoria "{name}" salvata.', 'success')
    return redirect(url_for('admin.task_categories'))


@admin_bp.post('/task-categories/<int:cat_id>/delete')
@login_required
@admin_required
def task_category_delete(cat_id: int):
    c = TaskCategory.query.get_or_404(cat_id)
    protected_statuses = {'completato', 'annullato'}

    fallback = TaskCategory.query.filter_by(name='Categoria rimossa').first()
    if fallback is None:
        fallback = TaskCategory(
            name='Categoria rimossa',
            color='#4a5c78',
            position=9999,
            notify_on_create=False,
            email_recipients='[]',
        )
        db.session.add(fallback)
        db.session.flush()

    moved_open = 0
    preserved_closed = 0
    deleted_responses = 0

    tasks = c.tasks.order_by(Task.id.asc()).all()
    for task in tasks:
        old_category_name = c.name
        old_status = task.status
        task.category_id = fallback.id
        if task.status in protected_statuses:
            preserved_closed += 1
            db.session.add(TaskEvent(
                task_id=task.id,
                event_type='category_deleted',
                note=f'Categoria "{old_category_name}" eliminata da admin. Task storico conservato su "{fallback.name}".',
                source='system',
                actor_name=current_user.name,
                actor_email=current_user.email,
            ))
            continue

        responses = task.recipient_responses.all()
        deleted_responses += len(responses)
        for resp in responses:
            db.session.delete(resp)

        task.status = 'da_fare'
        db.session.add(TaskEvent(
            task_id=task.id,
            event_type='category_deleted',
            old_status=old_status,
            new_status='da_fare',
            note=f'Categoria "{old_category_name}" eliminata da admin. Destinatari rimossi e avanzamento ricalcolato.',
            source='system',
            actor_name=current_user.name,
            actor_email=current_user.email,
        ))
        moved_open += 1

    db.session.delete(c)
    db.session.commit()
    flash(
        f'Categoria eliminata. Task aperti riallineati: {moved_open}, task storici conservati: {preserved_closed}, risposte rimosse: {deleted_responses}.',
        'success'
    )
    return redirect(url_for('admin.task_categories'))
