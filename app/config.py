from __future__ import annotations
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


class Config:
    # Core
    FLASK_ENV = os.environ.get('FLASK_ENV', 'development')
    SECRET_KEY = os.environ.get('SECRET_KEY') or (
        secrets.token_urlsafe(32) if FLASK_ENV != 'production' else None
    )
    if not SECRET_KEY:
        raise RuntimeError('SECRET_KEY mancante in produzione.')

    # Deployment / proxy
    PREFERRED_URL_SCHEME = os.environ.get('PREFERRED_URL_SCHEME', 'https' if FLASK_ENV == 'production' else 'http')
    FORCE_HTTPS_COOKIES = os.environ.get('FORCE_HTTPS_COOKIES', '1' if FLASK_ENV == 'production' else '0') == '1'
    ENABLE_PROXY_FIX = os.environ.get('ENABLE_PROXY_FIX', '1') == '1'
    TRUSTED_HOSTS = [h.strip() for h in os.environ.get('TRUSTED_HOSTS', '').split(',') if h.strip()]

    # Security / session
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.environ.get('SESSION_COOKIE_SAMESITE', 'Lax')
    SESSION_COOKIE_SECURE = FORCE_HTTPS_COOKIES
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = os.environ.get('REMEMBER_COOKIE_SAMESITE', 'Lax')
    REMEMBER_COOKIE_SECURE = FORCE_HTTPS_COOKIES
    PERMANENT_SESSION_LIFETIME = int(os.environ.get('PERMANENT_SESSION_LIFETIME_SECONDS', 60 * 60 * 24 * 7))

    # Database: PostgreSQL in prod, SQLite in locale
    _db_url = os.environ.get('DATABASE_URL', '')
    if _db_url.startswith('postgres://'):
        _db_url = _db_url.replace('postgres://', 'postgresql://', 1)
    SQLALCHEMY_DATABASE_URI = _db_url or f'sqlite:///{BASE_DIR / "data" / "logimetric.db"}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
    }

    # Bootstrap control
    AUTO_DB_BOOTSTRAP = os.environ.get('AUTO_DB_BOOTSTRAP', '1' if FLASK_ENV != 'production' else '0') == '1'

    # Email (Brevo)
    BREVO_API_KEY = os.environ.get('BREVO_API_KEY', '')
    MAIL_SENDER = os.environ.get('MAIL_SENDER', 'a.venticinque@logimetric.eu')
    ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'a.venticinque@logimetric.eu')

    # Percorsi file
    BASE_DIR = BASE_DIR
    TEMPLATE_XLS = BASE_DIR / 'templates_excel' / 'NEW - Mod. Trasferta.xls'
    WEEKLY_TEMPLATE_XLSX = BASE_DIR / 'templates_excel' / 'Programma settimanale.xlsx'

    # Form limits
    MAX_TRANSFERS = 8
    MAX_STAYS = 3

    # Task Manager
    TASKS_API_KEY = os.environ.get('TASKS_API_KEY', '')
    CRON_SECRET = os.environ.get('CRON_SECRET', '')
    POWERAPP_URL = os.environ.get('POWERAPP_URL', '')
    POWERAPP_TASK_ID_PARAM = os.environ.get('POWERAPP_TASK_ID_PARAM', 'task_id')
    RESET_TOKEN_MAX_AGE = int(os.environ.get('RESET_TOKEN_MAX_AGE', '3600'))

    # Telegram notifiche task
    TELEGRAM_ENABLED = os.environ.get('TELEGRAM_ENABLED', '0') == '1'
    TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
    TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')
    APP_BASE_URL = os.environ.get('APP_BASE_URL', '')

    # Teams notifiche task via Power Automate
    # Il backend chiama un flow dedicato con trigger HTTP; il flow pubblica
    # il messaggio Teams diretto all'utente tramite Flow bot.
    TEAMS_NOTIFICATIONS_ENABLED = os.environ.get('TEAMS_NOTIFICATIONS_ENABLED', '0') == '1'
    TEAMS_FLOW_URL = os.environ.get('TEAMS_FLOW_URL', '')
    TEAMS_FLOW_API_KEY = os.environ.get('TEAMS_FLOW_API_KEY', '')
    TEAMS_FLOW_TIMEOUT_SECONDS = int(os.environ.get('TEAMS_FLOW_TIMEOUT_SECONDS', '15'))

    # Rate limiting
    LOGIN_RATE_LIMIT_ATTEMPTS = int(os.environ.get('LOGIN_RATE_LIMIT_ATTEMPTS', '8'))
    LOGIN_RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get('LOGIN_RATE_LIMIT_WINDOW_SECONDS', '900'))
    RESET_RATE_LIMIT_ATTEMPTS = int(os.environ.get('RESET_RATE_LIMIT_ATTEMPTS', '5'))
    RESET_RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get('RESET_RATE_LIMIT_WINDOW_SECONDS', '3600'))
