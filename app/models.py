from __future__ import annotations
from datetime import datetime
from flask_login import UserMixin
from . import db, bcrypt

# ── Moduli disponibili nell'app ──────────────────────────────────────────────
MODULES = {
    'travel_form':    'Modulo Trasferta',
    'weekly_program': 'Programma Settimanale',
    'dashboard_bi':   'Dashboard BI',
    'task_manager':   'Task Manager',
    'gestione_aste':  'Gestione Aste',
    'dispensa':       'Dispensa',
}


# ── Utenti ───────────────────────────────────────────────────────────────────
class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(120), nullable=False)
    email       = db.Column(db.String(200), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role        = db.Column(db.String(20), default='user')     # 'admin' | 'user'
    is_approved = db.Column(db.Boolean, default=False)
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)

    permissions = db.relationship('Permission', back_populates='user',
                                  cascade='all, delete-orphan', lazy='dynamic')
    presets     = db.relationship('Preset', back_populates='user',
                                  cascade='all, delete-orphan', lazy='dynamic')

    def set_password(self, password: str) -> None:
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password: str) -> bool:
        return bcrypt.check_password_hash(self.password_hash, password)

    @property
    def is_admin(self) -> bool:
        return self.role == 'admin'

    def can_view(self, module: str) -> bool:
        if self.is_admin:
            return True
        perm = self.permissions.filter_by(module=module).first()
        return perm.can_view if perm else False

    def can_write(self, module: str) -> bool:
        if self.is_admin:
            return True
        perm = self.permissions.filter_by(module=module).first()
        return perm.can_write if perm else False

    def get_permissions_dict(self) -> dict:
        """Restituisce {module: {can_view, can_write}} per tutti i moduli."""
        result = {m: {'can_view': False, 'can_write': False} for m in MODULES}
        if self.is_admin:
            return {m: {'can_view': True, 'can_write': True} for m in MODULES}
        for perm in self.permissions.all():
            if perm.module in result:
                result[perm.module] = {
                    'can_view': perm.can_view,
                    'can_write': perm.can_write,
                }
        return result

    def __repr__(self) -> str:
        return f'<User {self.email} [{self.role}]>'


# ── Permessi per modulo ───────────────────────────────────────────────────────
class Permission(db.Model):
    __tablename__ = 'permissions'
    __table_args__ = (db.UniqueConstraint('user_id', 'module'),)

    id        = db.Column(db.Integer, primary_key=True)
    user_id   = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    module    = db.Column(db.String(50), nullable=False)
    can_view  = db.Column(db.Boolean, default=False)
    can_write = db.Column(db.Boolean, default=False)

    user = db.relationship('User', back_populates='permissions')


# ── Gestione Aste ─────────────────────────────────────────────────────────────

HOUSE_STATI = {
    'in_asta':         'In asta',
    'acquistata':      'Acquistata',
    'attesa_consegna': 'In attesa consegna',
    'di_proprieta':    'Di proprietà',
    'venduta':         'Venduta',
}
HOUSE_STATI_COLORS = {
    'in_asta':         '#f5a623',
    'acquistata':      '#1fa3ff',
    'attesa_consegna': '#a855f7',
    'di_proprieta':    '#3dbf7c',
    'venduta':         '#4a5c78',
}
EXPENSE_CATS = {
    'notarile':         'Notarile / Legale',
    'tasse':            'Tasse / Imposte',
    'ristrutturazione': 'Ristrutturazione',
    'altro':            'Altro',
}


class House(db.Model):
    __tablename__ = 'houses'

    id                    = db.Column(db.Integer, primary_key=True)
    via                   = db.Column(db.String(200), nullable=False)
    citta                 = db.Column(db.String(100), nullable=False)
    mq                    = db.Column(db.Float)
    garage                = db.Column(db.Boolean, default=False)
    data_asta             = db.Column(db.Date)
    prezzo_base           = db.Column(db.Float, default=0)
    prezzo_aggiudicazione = db.Column(db.Float, default=0)
    assegno_anticipo      = db.Column(db.Float, default=0)          # NON sommato all'aggiudicazione
    anticipo_pagato_da    = db.Column(db.Integer, db.ForeignKey('users.id'))
    stima_vendita         = db.Column(db.Float, default=0)
    ricavo_consuntivo     = db.Column(db.Float, default=0)
    stato                 = db.Column(db.String(30), default='in_asta')
    note                  = db.Column(db.Text)
    created_by            = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at            = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at            = db.Column(db.DateTime, default=datetime.utcnow,
                                      onupdate=datetime.utcnow)

    expenses        = db.relationship('HouseExpense',     back_populates='house',
                                      cascade='all, delete-orphan', lazy='dynamic')
    deadlines       = db.relationship('HouseDeadline',    back_populates='house',
                                      cascade='all, delete-orphan', lazy='dynamic')
    participants    = db.relationship('HouseParticipant', back_populates='house',
                                      cascade='all, delete-orphan', lazy='dynamic')
    audit_log       = db.relationship('HouseAudit',       back_populates='house',
                                      cascade='all, delete-orphan', lazy='dynamic')
    creator         = db.relationship('User', foreign_keys=[created_by])
    anticipo_payer  = db.relationship('User', foreign_keys=[anticipo_pagato_da])

    @property
    def spese_totali(self) -> float:
        """Somma spese accessorie (escluso anticipo che è già nell'aggiudicazione)."""
        return sum(e.importo or 0 for e in self.expenses.all())

    @property
    def costo_totale(self) -> float:
        """Aggiudicazione + spese accessorie (anticipo già incluso nell'aggiudicazione)."""
        return (self.prezzo_aggiudicazione or 0) + self.spese_totali

    @property
    def totale_da_dividere(self) -> float:
        """Totale che il gruppo deve coprire: aggiudicazione + spese + anticipo (che è spesa separata)."""
        return (self.prezzo_aggiudicazione or 0) + (self.assegno_anticipo or 0) + self.spese_totali

    @property
    def guadagno_stimato(self) -> float:
        return (self.stima_vendita or 0) - self.costo_totale

    @property
    def guadagno_reale(self) -> float:
        return (self.ricavo_consuntivo or 0) - self.costo_totale

    @property
    def n_partecipanti(self) -> int:
        return max(self.participants.count(), 1)

    @property
    def quota_pro_capite(self) -> float:
        return self.totale_da_dividere / self.n_partecipanti

    def saldo_utente(self, user_id: int) -> dict:
        """
        Calcola dare/avere per un singolo partecipante.

        saldo > 0 → gli altri gli devono soldi (CREDITORE)
        saldo < 0 → lui deve soldi al gruppo (DEBITORE)

        I flag di liquidazione (quota_versata / credito_ricevuto) non modificano
        il calcolo matematico, ma vengono restituiti per guidare la UI.
        """
        n     = self.n_partecipanti
        quota = self.totale_da_dividere / n

        anticipo_pagato = (self.assegno_anticipo or 0) if self.anticipo_pagato_da == user_id else 0
        spese_pagate    = sum(e.importo or 0 for e in self.expenses.all()
                              if e.paid_by_user_id == user_id)

        pagato = anticipo_pagato + spese_pagate
        saldo  = pagato - quota

        # Recupera i flag di liquidazione del partecipante
        part = self.participants.filter_by(user_id=user_id).first()
        quota_versata    = part.quota_versata    if part else False
        credito_ricevuto = part.credito_ricevuto if part else False

        # Saldo "visibile" — azzerato se il creditore ha confermato la ricezione
        saldo_display = 0.0 if (saldo > 0 and credito_ricevuto) else saldo

        return {
            'quota':            quota,
            'pagato':           pagato,
            'saldo':            saldo,            # saldo matematico reale
            'saldo_display':    saldo_display,     # saldo da mostrare in UI
            'deve_ricevere':    saldo > 0,
            'deve_dare':        saldo < 0,
            'quota_versata':    quota_versata,
            'credito_ricevuto': credito_ricevuto,
            'liquidato':        (saldo == 0)
                                or (saldo < 0 and quota_versata and credito_ricevuto is False)
                                or (saldo > 0 and credito_ricevuto),
        }

    @property
    def scadenze_urgenti(self) -> list:
        from datetime import date, timedelta
        today = date.today()
        return [d for d in self.deadlines.filter_by(completata=False).all()
                if d.data_scadenza and d.data_scadenza <= today + timedelta(days=7)]

    def __repr__(self):
        return f'<House {self.via}, {self.citta}>'


class HouseParticipant(db.Model):
    __tablename__ = 'house_participants'
    __table_args__ = (db.UniqueConstraint('house_id', 'user_id'),)

    id               = db.Column(db.Integer, primary_key=True)
    house_id         = db.Column(db.Integer, db.ForeignKey('houses.id'), nullable=False)
    user_id          = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    ruolo            = db.Column(db.String(50), default='partecipante')
    quota_versata    = db.Column(db.Boolean, default=False)   # debitore: ho versato la mia quota
    versato_il       = db.Column(db.DateTime)
    credito_ricevuto = db.Column(db.Boolean, default=False)   # creditore: ho ricevuto le quote
    ricevuto_il      = db.Column(db.DateTime)

    house = db.relationship('House', back_populates='participants')
    user  = db.relationship('User')


class HouseExpense(db.Model):
    __tablename__ = 'house_expenses'

    id               = db.Column(db.Integer, primary_key=True)
    house_id         = db.Column(db.Integer, db.ForeignKey('houses.id'), nullable=False)
    categoria        = db.Column(db.String(30), default='altro')
    descrizione      = db.Column(db.String(200))
    importo          = db.Column(db.Float, default=0)
    data             = db.Column(db.Date)
    paid_by_user_id  = db.Column(db.Integer, db.ForeignKey('users.id'))   # chi ha fisicamente pagato
    created_by       = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)

    house    = db.relationship('House', back_populates='expenses')
    paid_by  = db.relationship('User', foreign_keys=[paid_by_user_id])
    creator  = db.relationship('User', foreign_keys=[created_by])


class HouseDeadline(db.Model):
    __tablename__ = 'house_deadlines'

    id            = db.Column(db.Integer, primary_key=True)
    house_id      = db.Column(db.Integer, db.ForeignKey('houses.id'), nullable=False)
    titolo        = db.Column(db.String(200), nullable=False)
    data_scadenza = db.Column(db.Date)
    giorni_alert  = db.Column(db.Integer, default=7)
    tipo          = db.Column(db.String(10), default='post')  # pre | post
    completata    = db.Column(db.Boolean, default=False)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    house = db.relationship('House', back_populates='deadlines')

    @property
    def is_urgent(self) -> bool:
        from datetime import date, timedelta
        if not self.data_scadenza or self.completata:
            return False
        return self.data_scadenza <= date.today() + timedelta(days=self.giorni_alert)

    @property
    def is_overdue(self) -> bool:
        from datetime import date
        return (self.data_scadenza is not None
                and self.data_scadenza < date.today()
                and not self.completata)


class HouseAudit(db.Model):
    __tablename__ = 'house_audit'

    id           = db.Column(db.Integer, primary_key=True)
    house_id     = db.Column(db.Integer, db.ForeignKey('houses.id'), nullable=False)
    user_id      = db.Column(db.Integer, db.ForeignKey('users.id'))
    campo        = db.Column(db.String(80))
    valore_prima = db.Column(db.Text)
    valore_dopo  = db.Column(db.Text)
    modified_at  = db.Column(db.DateTime, default=datetime.utcnow)

    house = db.relationship('House', back_populates='audit_log')
    user  = db.relationship('User', foreign_keys=[user_id])


class HouseExpenseSettlement(db.Model):
    """Traccia il saldo di ogni singola spesa per ogni partecipante."""
    __tablename__ = 'house_expense_settlements'
    __table_args__ = (db.UniqueConstraint('expense_id', 'user_id'),)

    id          = db.Column(db.Integer, primary_key=True)
    expense_id  = db.Column(db.Integer, db.ForeignKey('house_expenses.id'), nullable=False)
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    versato     = db.Column(db.Boolean, default=False)   # debitore: ho versato
    versato_il  = db.Column(db.DateTime)
    ricevuto    = db.Column(db.Boolean, default=False)   # creditore: ho ricevuto
    ricevuto_il = db.Column(db.DateTime)

    expense = db.relationship('HouseExpense', backref=db.backref('settlements', lazy='dynamic'))
    user    = db.relationship('User')


# ── Task Management ────────────────────────────────────────────────────────────
import uuid as _uuid

TASK_STATUS_LABELS = {
    'da_fare':    'Da fare',
    'in_corso':   'In corso',
    'in_attesa':  'In attesa',
    'completato': 'Completato',
    'annullato':  'Annullato',
}
TASK_STATUS_COLORS = {
    'da_fare':    '#4a5c78',
    'in_corso':   '#1fa3ff',
    'in_attesa':  '#f5a623',
    'completato': '#3dbf7c',
    'annullato':  '#555',
}
TASK_PRIORITY_LABELS  = {'bassa': 'Bassa', 'media': 'Media', 'alta': 'Alta', 'critica': 'Critica'}
TASK_PRIORITY_COLORS  = {'bassa': '#4a5c78', 'media': '#1fa3ff', 'alta': '#f5a623', 'critica': '#e05c5c'}
TASK_STATUS_ORDER     = ['da_fare', 'in_corso', 'in_attesa', 'completato', 'annullato']


class TaskCategory(db.Model):
    __tablename__ = 'task_categories'

    id               = db.Column(db.Integer, primary_key=True)
    name             = db.Column(db.String(80), unique=True, nullable=False)
    color            = db.Column(db.String(20), default='#1fa3ff')
    email_recipients = db.Column(db.Text, default='[]')   # JSON list
    notify_on_create = db.Column(db.Boolean, default=False)
    position         = db.Column(db.Integer, default=0)
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)

    tasks = db.relationship('Task', back_populates='category', lazy='dynamic')

    def get_recipients(self) -> list:
        import json
        try:
            return json.loads(self.email_recipients or '[]')
        except Exception:
            return []

    def __repr__(self):
        return f'<TaskCategory {self.name}>'


class Task(db.Model):
    __tablename__ = 'tasks'

    id             = db.Column(db.Integer, primary_key=True)
    title          = db.Column(db.String(200), nullable=False)
    description    = db.Column(db.Text)
    category_id    = db.Column(db.Integer, db.ForeignKey('task_categories.id'), nullable=False)
    priority       = db.Column(db.String(20), default='media')
    status         = db.Column(db.String(20), default='da_fare')
    start_date     = db.Column(db.Date)
    due_date       = db.Column(db.Date)
    external_token = db.Column(db.String(36), unique=True,
                               default=lambda: str(_uuid.uuid4()))
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at     = db.Column(db.DateTime, default=datetime.utcnow,
                               onupdate=datetime.utcnow)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_by_name    = db.Column(db.String(120))
    created_by_email   = db.Column(db.String(200), index=True)
    completed_at       = db.Column(db.DateTime)
    completed_by_name  = db.Column(db.String(120))
    completed_by_email = db.Column(db.String(200), index=True)

    category             = db.relationship('TaskCategory', back_populates='tasks')
    events               = db.relationship('TaskEvent', back_populates='task',
                                           cascade='all, delete-orphan',
                                           order_by='TaskEvent.created_at')
    recipient_responses  = db.relationship('TaskRecipientResponse', back_populates='task',
                                           cascade='all, delete-orphan', lazy='dynamic')

    @property
    def is_overdue(self) -> bool:
        from datetime import date
        return (self.due_date is not None
                and self.due_date < date.today()
                and self.status not in ('completato', 'annullato'))

    @property
    def due_soon(self) -> bool:
        from datetime import date, timedelta
        return (self.due_date is not None
                and date.today() <= self.due_date <= date.today() + timedelta(days=1)
                and self.status not in ('completato', 'annullato'))

    # ── Tracciamento risposte per destinatario ────────────────────────────────

    def _recipients(self) -> list[str]:
        """Lista email destinatari della categoria, normalizzata e deduplicata."""
        if not self.category:
            return []

        normalized: list[str] = []
        seen: set[str] = set()
        for raw in self.category.get_recipients() or []:
            email = (raw or '').strip().lower()
            if not email or email in seen:
                continue
            seen.add(email)
            normalized.append(email)
        return normalized

    @property
    def progress_percent(self):
        """
        % destinatari che hanno avanzato OLTRE lo stato attuale del task.
        None se la categoria ha 0 o 1 destinatario (% non significativa).
        """
        recipients = self._recipients()
        n = len(recipients)
        if n <= 1:
            return None

        order = TASK_STATUS_ORDER
        try:
            current_idx = order.index(self.status)
        except ValueError:
            current_idx = 0

        responses = {
            (r.recipient_email or '').strip().lower(): r.status
            for r in self.recipient_responses.all()
        }

        ahead = 0
        for email in recipients:
            r_status = responses.get(email, 'da_fare')
            try:
                r_idx = order.index(r_status)
            except ValueError:
                r_idx = 0
            if r_idx > current_idx:
                ahead += 1

        return round(ahead / n * 100)

    def compute_aggregate_status(self) -> str:
        """
        Stato aggregato = il minimo tra tutti i destinatari.
        Il task avanza solo quando TUTTI hanno raggiunto lo stesso livello.
        """
        recipients = self._recipients()
        if not recipients:
            return self.status

        order = TASK_STATUS_ORDER
        responses = {
            (r.recipient_email or '').strip().lower(): r.status
            for r in self.recipient_responses.all()
        }

        statuses = [responses.get(email, 'da_fare') for email in recipients]

        min_idx = min(
            order.index(s) if s in order else 0
            for s in statuses
        )
        return order[min_idx]

    @property
    def active_recipients(self) -> list[str]:
        return self._recipients()

    @property
    def first_response_at(self):
        first = self.recipient_responses.order_by(TaskRecipientResponse.updated_at.asc()).first()
        return first.updated_at if first else None

    @property
    def completed_in_time(self) -> bool | None:
        if self.status != 'completato' or not self.completed_at or not self.due_date:
            return None
        return self.completed_at.date() <= self.due_date

    @property
    def is_late_completion(self) -> bool:
        return self.status == 'completato' and bool(self.completed_at and self.due_date and self.completed_at.date() > self.due_date)

    def __repr__(self):
        return f'<Task #{self.id} {self.title[:40]}>'


class TaskRecipientResponse(db.Model):
    """
    Risposta individuale di ogni destinatario a un task.
    Ogni email che ha ricevuto la notifica ha la propria riga.
    """
    __tablename__ = 'task_recipient_responses'
    __table_args__ = (db.UniqueConstraint('task_id', 'recipient_email'),)

    id              = db.Column(db.Integer, primary_key=True)
    task_id         = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False)
    recipient_email = db.Column(db.String(200), nullable=False, index=True)
    status          = db.Column(db.String(20), default='da_fare')
    note            = db.Column(db.Text)
    replied_by      = db.Column(db.String(200))   # nome libero opzionale
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at      = db.Column(db.DateTime, default=datetime.utcnow,
                                onupdate=datetime.utcnow)

    task = db.relationship('Task', back_populates='recipient_responses')


class TaskEvent(db.Model):
    __tablename__ = 'task_events'

    id         = db.Column(db.Integer, primary_key=True)
    task_id    = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False)
    event_type = db.Column(db.String(30))   # created|status_changed|comment|external_reply
    old_status = db.Column(db.String(20))
    new_status = db.Column(db.String(20))
    note       = db.Column(db.Text)
    source     = db.Column(db.String(20), default='manual')  # manual|powerautomate|aggregate|system
    actor_name = db.Column(db.String(120))
    actor_email = db.Column(db.String(200), index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    task = db.relationship('Task', back_populates='events')


class TaskHelperRequest(db.Model):
    """Rate limiting per le richieste al helper email (1/giorno per email)."""
    __tablename__ = 'task_helper_requests'

    id               = db.Column(db.Integer, primary_key=True)
    requester_email  = db.Column(db.String(200), nullable=False, index=True)
    requested_at     = db.Column(db.DateTime, default=datetime.utcnow)


# ── Rubrica contatti ──────────────────────────────────────────────────────────
class Contact(db.Model):
    __tablename__ = 'contacts'

    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(120), nullable=False)
    email      = db.Column(db.String(200), unique=True, nullable=False)
    notes      = db.Column(db.String(255))
    is_active  = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Contact {self.name} <{self.email}>>'


# ── Report Power BI ───────────────────────────────────────────────────────────
class BiReport(db.Model):
    __tablename__ = 'bi_reports'

    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(120), nullable=False)
    embed_url  = db.Column(db.Text, nullable=False)
    position   = db.Column(db.Integer, default=0)
    is_active  = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<BiReport {self.name}>'


# ── Preset form ───────────────────────────────────────────────────────────────
class Preset(db.Model):
    __tablename__ = 'presets'
    __table_args__ = (db.UniqueConstraint('user_id', 'name', 'preset_type'),)

    id          = db.Column(db.Integer, primary_key=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name        = db.Column(db.String(120), nullable=False)
    preset_type = db.Column(db.String(30), default='travel')   # 'travel' | 'weekly'
    payload     = db.Column(db.Text, nullable=False)           # JSON
    created_at  = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at  = db.Column(db.DateTime, default=datetime.utcnow,
                            onupdate=datetime.utcnow)

    user = db.relationship('User', back_populates='presets')


# ── Schedulazione Programma Settimanale ──────────────────────────────────────
import uuid as _uuid2

class WeeklySchedule(db.Model):
    """
    Una sola riga per utente. Contiene i dati fissi del programma settimanale
    e il token monouso per conferma/modifica via email.
    """
    __tablename__ = 'weekly_schedules'

    id              = db.Column(db.Integer, primary_key=True)
    user_id         = db.Column(db.Integer, db.ForeignKey('users.id'),
                                nullable=False, unique=True)

    # Dati fissi del programma
    full_name       = db.Column(db.String(200), default='')
    day_location_1  = db.Column(db.String(100), default='')
    day_location_2  = db.Column(db.String(100), default='')
    day_location_3  = db.Column(db.String(100), default='')
    day_location_4  = db.Column(db.String(100), default='')
    day_location_5  = db.Column(db.String(100), default='')

    # Stato schedulazione
    active          = db.Column(db.Boolean, default=False)

    # Token per i link email (generato ogni mercoledì)
    confirm_token   = db.Column(db.String(64), unique=True, index=True,
                                default=lambda: str(_uuid2.uuid4()))
    token_expires_at = db.Column(db.DateTime)   # giovedì dopo il cron

    # Timestamp operazioni
    last_reminded_at = db.Column(db.DateTime)   # ultimo mercoledì in cui è stato inviato il reminder
    last_sent_at     = db.Column(db.DateTime)   # ultima conferma avvenuta
    created_at       = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at       = db.Column(db.DateTime, default=datetime.utcnow,
                                  onupdate=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('weekly_schedule', uselist=False))

    @property
    def day_locations(self) -> list[str]:
        return [
            self.day_location_1 or '',
            self.day_location_2 or '',
            self.day_location_3 or '',
            self.day_location_4 or '',
            self.day_location_5 or '',
        ]

    def refresh_token(self) -> None:
        """Genera nuovo token e imposta scadenza al giovedì seguente."""
        from datetime import date, timedelta
        self.confirm_token = str(_uuid2.uuid4())
        # Scade giovedì prossimo alle 23:59 (5 giorni di validità dal mercoledì)
        today = date.today()
        days_to_thursday = (3 - today.weekday()) % 7 + 1  # 0=lun … 3=gio
        self.token_expires_at = datetime.combine(
            today + timedelta(days=days_to_thursday),
            datetime.max.time().replace(hour=23, minute=59, second=59)
        )

    def is_token_valid(self) -> bool:
        if not self.token_expires_at:
            return False
        return datetime.utcnow() < self.token_expires_at

    def already_reminded_this_week(self) -> bool:
        """True se è già stato mandato il reminder questa settimana (lun-dom)."""
        if not self.last_reminded_at:
            return False
        from datetime import date, timedelta
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        return self.last_reminded_at.date() >= week_start

    def __repr__(self):
        return f'<WeeklySchedule user={self.user_id} active={self.active}>'
