from __future__ import annotations
import logging
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from flask import (current_app, flash, redirect, render_template,
                   request, url_for)
from flask_login import current_user, login_required, login_user, logout_user

from .. import db
from ..models import User
from ..email_service import (send_registration_pending, send_admin_new_registration,
                              send_account_approved, send_password_reset)
from ..security import SimpleRateLimiter, safe_redirect_target
from . import auth_bp

log = logging.getLogger(__name__)


def _make_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'])


def _client_ip() -> str:
    forwarded = request.headers.get('X-Forwarded-For', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr or 'unknown'


def _login_limiter() -> SimpleRateLimiter:
    return SimpleRateLimiter(
        current_app.config['LOGIN_RATE_LIMIT_ATTEMPTS'],
        current_app.config['LOGIN_RATE_LIMIT_WINDOW_SECONDS'],
    )


def _reset_limiter() -> SimpleRateLimiter:
    return SimpleRateLimiter(
        current_app.config['RESET_RATE_LIMIT_ATTEMPTS'],
        current_app.config['RESET_RATE_LIMIT_WINDOW_SECONDS'],
    )


# ── Login ─────────────────────────────────────────────────────────────────────
@auth_bp.get('/login')
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    return render_template('auth/login.html')


@auth_bp.post('/login')
def login_post():
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')
    remember = bool(request.form.get('remember'))

    allowed, retry_after = _login_limiter().hit(f'login:{_client_ip()}:{email}')
    if not allowed:
        flash(f'Troppi tentativi di accesso. Riprova tra circa {retry_after} secondi.', 'error')
        return render_template('auth/login.html', email=email), 429

    user = User.query.filter_by(email=email).first()

    if not user or not user.check_password(password):
        log.warning('Tentativo login fallito per email=%s ip=%s', email, _client_ip())
        flash('Email o password non corretti.', 'error')
        return render_template('auth/login.html', email=email), 401

    if not user.is_approved:
        flash("Il tuo account è in attesa di approvazione da parte dell'amministratore.", 'warning')
        return render_template('auth/login.html', email=email), 403

    login_user(user, remember=remember)
    next_page = request.args.get('next')
    return redirect(safe_redirect_target(next_page, 'main.index'))


# ── Logout ────────────────────────────────────────────────────────────────────
@auth_bp.get('/logout')
@login_required
def logout():
    logout_user()
    flash('Disconnesso con successo.', 'success')
    return redirect(url_for('auth.login'))


# ── Registrazione ─────────────────────────────────────────────────────────────
@auth_bp.get('/register')
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    return render_template('auth/register.html')


@auth_bp.post('/register')
def register_post():
    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')
    password2 = request.form.get('password2', '')

    errors = []
    if not name:
        errors.append('Il nome è obbligatorio.')
    if not email or '@' not in email:
        errors.append('Email non valida.')
    if len(password) < 8:
        errors.append('La password deve essere di almeno 8 caratteri.')
    if password != password2:
        errors.append('Le password non coincidono.')
    if User.query.filter_by(email=email).first():
        errors.append('Esiste già un account con questa email.')

    if errors:
        for err in errors:
            flash(err, 'error')
        return render_template('auth/register.html', name=name, email=email), 422

    admin_email = current_app.config.get('ADMIN_EMAIL', '').lower()
    is_admin = (email == admin_email)

    user = User(name=name, email=email, role='admin' if is_admin else 'user',
                is_approved=is_admin)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    if is_admin:
        flash('Account amministratore creato. Puoi accedere ora.', 'success')
        return redirect(url_for('auth.login'))

    try:
        send_registration_pending(user)
        admin_user = User.query.filter_by(email=admin_email).first()
        notify_email = admin_user.email if admin_user else admin_email
        send_admin_new_registration(notify_email, user)
    except Exception as exc:
        log.warning('Email non inviata: %s', exc)

    flash("Registrazione completata! Riceverai un'email quando il tuo account sarà approvato.", 'success')
    return redirect(url_for('auth.login'))


# ── Forgot password ───────────────────────────────────────────────────────────
@auth_bp.get('/forgot-password')
def forgot_password():
    return render_template('auth/forgot_password.html')


@auth_bp.post('/forgot-password')
def forgot_password_post():
    email = request.form.get('email', '').strip().lower()

    allowed, retry_after = _reset_limiter().hit(f'forgot:{_client_ip()}:{email}')
    if not allowed:
        flash(f'Troppe richieste di reset. Riprova tra circa {retry_after} secondi.', 'error')
        return redirect(url_for('auth.forgot_password'))

    user = User.query.filter_by(email=email).first()

    flash("Se l'email è registrata, riceverai un link per reimpostare la password.", 'info')

    if user and user.is_approved:
        s = _make_serializer()
        token = s.dumps(user.email, salt='reset-password')
        reset_url = url_for('auth.reset_password', token=token, _external=True)
        try:
            send_password_reset(user, reset_url)
        except Exception as exc:
            log.warning('Email reset non inviata: %s', exc)

    return redirect(url_for('auth.login'))


@auth_bp.get('/reset-password/<token>')
def reset_password(token: str):
    s = _make_serializer()
    try:
        email = s.loads(token, salt='reset-password',
                        max_age=current_app.config['RESET_TOKEN_MAX_AGE'])
    except SignatureExpired:
        flash('Il link è scaduto. Richiedine uno nuovo.', 'error')
        return redirect(url_for('auth.forgot_password'))
    except BadSignature:
        flash('Link non valido.', 'error')
        return redirect(url_for('auth.forgot_password'))

    user = User.query.filter_by(email=email).first()
    if not user:
        flash('Utente non trovato.', 'error')
        return redirect(url_for('auth.login'))

    return render_template('auth/reset_password.html', token=token)


@auth_bp.post('/reset-password/<token>')
def reset_password_post(token: str):
    allowed, retry_after = _reset_limiter().hit(f'reset:{_client_ip()}:{token[:12]}')
    if not allowed:
        flash(f'Troppi tentativi di reset. Riprova tra circa {retry_after} secondi.', 'error')
        return redirect(url_for('auth.forgot_password'))

    s = _make_serializer()
    try:
        email = s.loads(token, salt='reset-password',
                        max_age=current_app.config['RESET_TOKEN_MAX_AGE'])
    except (SignatureExpired, BadSignature):
        flash('Link non valido o scaduto.', 'error')
        return redirect(url_for('auth.forgot_password'))

    user = User.query.filter_by(email=email).first()
    if not user:
        flash('Utente non trovato.', 'error')
        return redirect(url_for('auth.login'))

    password = request.form.get('password', '')
    password2 = request.form.get('password2', '')

    if len(password) < 8:
        flash('La password deve essere di almeno 8 caratteri.', 'error')
        return render_template('auth/reset_password.html', token=token), 422
    if password != password2:
        flash('Le password non coincidono.', 'error')
        return render_template('auth/reset_password.html', token=token), 422

    user.set_password(password)
    db.session.commit()
    flash('Password aggiornata. Puoi accedere ora.', 'success')
    return redirect(url_for('auth.login'))
