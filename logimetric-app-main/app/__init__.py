from __future__ import annotations
import logging
from pathlib import Path

from flask import Flask, g, has_request_context, jsonify, request
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from werkzeug.middleware.proxy_fix import ProxyFix

from .security import (
    csrf_error_response,
    generate_csrf_token,
    should_enforce_csrf,
    validate_csrf_request,
)

load_dotenv()

db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()
migrate = Migrate()


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if has_request_context():
            record.request_id = getattr(g, 'request_id', '-')
            record.path = request.path
            record.method = request.method
        else:
            record.request_id = '-'
            record.path = '-'
            record.method = '-'
        return True


def _configure_logging(app: Flask) -> None:
    if app.logger.handlers:
        for handler in app.logger.handlers:
            handler.addFilter(RequestContextFilter())
        return

    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    handler.addFilter(RequestContextFilter())
    handler.setFormatter(logging.Formatter(
        '[%(asctime)s] %(levelname)s in %(module)s '
        '[req=%(request_id)s %(method)s %(path)s]: %(message)s'
    ))
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)




def _ensure_runtime_schema(app: Flask) -> None:
    """Aggiunge colonne mancanti sui database esistenti senza richiedere una migrazione manuale."""
    from sqlalchemy import inspect
    from .models import Task, TaskEvent, TaskRecipientResponse, TaskCategory, TaskAttachment

    dialect_name = db.engine.dialect.name

    def _ddl_type(type_name: str) -> str:
        upper = type_name.upper()
        if dialect_name == 'postgresql':
            if upper == 'DATETIME':
                return 'TIMESTAMP'
        return upper

    def _add_missing_columns(table_name: str, statements: list[tuple[str, str]]) -> None:
        inspector = inspect(db.engine)
        existing = {c['name'] for c in inspector.get_columns(table_name)}
        with db.engine.begin() as conn:
            for col_name, raw_ddl in statements:
                if col_name in existing:
                    continue
                ddl = raw_ddl.replace('DATETIME', _ddl_type('DATETIME'))
                conn.execute(db.text(f'ALTER TABLE {table_name} ADD COLUMN {ddl}'))
                app.logger.info('Schema bootstrap: added %s.%s', table_name, col_name)

    with app.app_context():
        db.create_all()
        _add_missing_columns('tasks', [
            ('created_by_user_id', 'created_by_user_id INTEGER'),
            ('created_by_name', 'created_by_name VARCHAR(120)'),
            ('created_by_email', 'created_by_email VARCHAR(200)'),
            ('completed_at', 'completed_at DATETIME'),
            ('completed_by_name', 'completed_by_name VARCHAR(120)'),
            ('completed_by_email', 'completed_by_email VARCHAR(200)'),
        ])
        _add_missing_columns('task_categories', [
            ('created_at', 'created_at DATETIME'),
        ])
        _add_missing_columns('task_events', [
            ('actor_name', 'actor_name VARCHAR(120)'),
            ('actor_email', 'actor_email VARCHAR(200)'),
        ])
        _add_missing_columns('task_recipient_responses', [
            ('created_at', 'created_at DATETIME'),
            ('reminder_2d_sent_at', 'reminder_2d_sent_at DATETIME'),
            ('reminder_1d_sent_at', 'reminder_1d_sent_at DATETIME'),
            ('reminder_0d_sent_at', 'reminder_0d_sent_at DATETIME'),
            ('reminder_2d_for_due_date', 'reminder_2d_for_due_date DATE'),
            ('reminder_1d_for_due_date', 'reminder_1d_for_due_date DATE'),
            ('reminder_0d_for_due_date', 'reminder_0d_for_due_date DATE'),
        ])
        # task_attachments è una tabella nuova creata da db.create_all(); nessun ALTER necessario qui.


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder='templates',
        static_folder='static',
    )
    app.config.from_object('app.config.Config')

    if app.config.get('ENABLE_PROXY_FIX', True):
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

    # Crea cartella data se SQLite locale
    if 'sqlite' in app.config['SQLALCHEMY_DATABASE_URI']:
        Path(app.config['BASE_DIR'] / 'data').mkdir(parents=True, exist_ok=True)

    _configure_logging(app)

    # Inizializza estensioni
    db.init_app(app)
    bcrypt.init_app(app)
    migrate.init_app(app, db)

    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Accedi per continuare.'
    login_manager.login_message_category = 'info'

    @login_manager.user_loader
    def load_user(user_id: str):
        from .models import User
        return db.session.get(User, int(user_id))

    @app.context_processor
    def inject_template_globals():
        return {
            'csrf_token': generate_csrf_token,
        }

    @app.before_request
    def before_request_security():
        import uuid
        g.request_id = request.headers.get('X-Request-ID') or uuid.uuid4().hex[:12]
        if should_enforce_csrf(request.method, request.endpoint) and not validate_csrf_request():
            app.logger.warning('CSRF validation failed for endpoint=%s', request.endpoint)
            return csrf_error_response()

    @app.after_request
    def after_request_headers(response):
        response.headers.setdefault('X-Request-ID', getattr(g, 'request_id', '-'))
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
        response.headers.setdefault('Permissions-Policy', 'geolocation=(), microphone=(), camera=()')
        if request.is_secure:
            response.headers.setdefault('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
        return response

    @app.errorhandler(400)
    def handle_bad_request(error):
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.path.startswith('/tasks/api/'):
            return jsonify({'ok': False, 'error': str(error)}), 400
        return error

    @app.errorhandler(403)
    def handle_forbidden(error):
        return 'Accesso negato.', 403

    @app.errorhandler(500)
    def handle_internal_error(error):
        db.session.rollback()
        app.logger.exception('Unhandled exception: %s', error)
        return 'Errore interno del server.', 500

    @app.get('/healthz')
    def healthz():
        return jsonify({'ok': True, 'status': 'healthy'})

    @app.get('/readyz')
    def readyz():
        try:
            db.session.execute(db.text('SELECT 1'))
            return jsonify({'ok': True, 'status': 'ready'})
        except Exception as exc:
            app.logger.exception('Readiness check failed: %s', exc)
            return jsonify({'ok': False, 'status': 'degraded'}), 503

    # Registra blueprint
    from .auth.routes import auth_bp
    from .admin_bp.routes import admin_bp
    from .main.routes import main_bp
    from .tasks.routes import tasks_bp
    from .aste.routes import aste_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(main_bp)
    app.register_blueprint(tasks_bp, url_prefix='/tasks')
    app.register_blueprint(aste_bp, url_prefix='/aste')

    # Allinea lo schema runtime anche in produzione per evitare mismatch tra codice e DB.
    _ensure_runtime_schema(app)

    # Bootstrap opzionale del DB; in produzione usare Flask-Migrate.
    with app.app_context():
        if app.config.get('AUTO_DB_BOOTSTRAP', False):
            db.create_all()
            _run_legacy_bootstrap_migrations(app)
            _seed_default_categories()
        else:
            app.logger.info('AUTO_DB_BOOTSTRAP disattivato: applicato comunque runtime schema sync per colonne/tabelle task.')

    return app


def _run_legacy_bootstrap_migrations(app: Flask):
    """
    Compatibilità con vecchi ambienti locali.
    In produzione è consigliato tenere AUTO_DB_BOOTSTRAP=0 e usare Alembic.
    """
    from sqlalchemy import inspect, text
    engine = db.engine
    inspector = inspect(engine)

    def col_exists(table: str, col: str) -> bool:
        try:
            cols = [c['name'] for c in inspector.get_columns(table)]
            return col in cols
        except Exception:
            return True

    migrations = [
        ('houses', 'assegno_anticipo', 'FLOAT DEFAULT 0'),
        ('houses', 'anticipo_pagato_da', 'INTEGER'),
        ('house_expenses', 'paid_by_user_id', 'INTEGER'),
        ('house_participants', 'quota_versata', 'BOOLEAN DEFAULT FALSE'),
        ('house_participants', 'versato_il', 'TIMESTAMP'),
        ('house_participants', 'credito_ricevuto', 'BOOLEAN DEFAULT FALSE'),
        ('house_participants', 'ricevuto_il', 'TIMESTAMP'),
        ('houses', 'note', 'TEXT'),
        # Queste tabelle sono create da db.create_all (tabelle nuove):
        #   task_recipient_responses, weekly_schedules
    ]

    with engine.begin() as conn:
        for table, column, col_type in migrations:
            if not col_exists(table, column):
                try:
                    conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {column} {col_type}'))
                    app.logger.info('Legacy bootstrap migration applied: %s.%s', table, column)
                except Exception as exc:
                    app.logger.warning('Legacy bootstrap migration skipped for %s.%s: %s', table, column, exc)


def _seed_default_categories():
    from .models import TaskCategory
    import json
    defaults = [
        {'name': 'Task Personali', 'color': '#1fa3ff', 'position': 0, 'notify_on_create': False},
        {'name': 'Task Magazzino', 'color': '#f5a623', 'position': 1, 'notify_on_create': True},
        {'name': 'Task DG', 'color': '#a855f7', 'position': 2, 'notify_on_create': True},
    ]
    for d in defaults:
        if not TaskCategory.query.filter_by(name=d['name']).first():
            cat = TaskCategory(
                name=d['name'], color=d['color'],
                position=d['position'], notify_on_create=d['notify_on_create'],
                email_recipients=json.dumps([]),
            )
            db.session.add(cat)
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
