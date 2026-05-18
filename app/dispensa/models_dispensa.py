"""
Modelli per il modulo Dispensa.
Da importare in app/models.py oppure usare direttamente.
"""
from __future__ import annotations
from datetime import datetime
from .. import db


PANTRY_CATEGORIES = [
    'Frutta e Verdura', 'Carne e Pesce', 'Latticini e Uova',
    'Pasta e Cereali', 'Pane e Bakery', 'Conserve e Scatolame',
    'Surgelati', 'Bevande', 'Pulizia Casa', 'Igiene Personale',
    'Snack e Dolci', 'Condimenti e Spezie', 'Altro',
]

PANTRY_UNITS = ['pz', 'kg', 'g', 'l', 'ml', 'conf', 'bott', 'sc']


class PantryProduct(db.Model):
    """Catalogo prodotti della dispensa."""
    __tablename__ = 'pantry_products'

    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(200), nullable=False)
    category   = db.Column(db.String(100), default='Altro')
    unit       = db.Column(db.String(20), default='pz')
    barcode    = db.Column(db.String(60), unique=True, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    purchases = db.relationship('PantryPurchase', backref='product', lazy='dynamic',
                                cascade='all, delete-orphan')
    stock     = db.relationship('PantryStock', backref='product', uselist=False,
                                cascade='all, delete-orphan')

    def avg_price_per_unit(self) -> float:
        """Prezzo unitario medio degli ultimi 10 acquisti."""
        recent = (self.purchases
                  .order_by(PantryPurchase.purchase_date.desc())
                  .limit(10).all())
        if not recent:
            return 0.0
        vals = [p.price_total / p.quantity for p in recent if p.quantity > 0]
        return round(sum(vals) / len(vals), 2) if vals else 0.0

    def avg_days_between_purchases(self) -> float | None:
        """Giorni medi tra un acquisto e il successivo."""
        dates = [p.purchase_date for p in
                 self.purchases.order_by(PantryPurchase.purchase_date).all()]
        if len(dates) < 2:
            return None
        gaps = [(dates[i+1] - dates[i]).days for i in range(len(dates)-1)]
        return round(sum(gaps) / len(gaps), 1)

    def __repr__(self) -> str:
        return f'<PantryProduct {self.name}>'


class PantryPurchase(db.Model):
    """Ogni riga di scontrino registrata."""
    __tablename__ = 'pantry_purchases'

    id            = db.Column(db.Integer, primary_key=True)
    product_id    = db.Column(db.Integer, db.ForeignKey('pantry_products.id'), nullable=False)
    user_id       = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    quantity      = db.Column(db.Float, nullable=False)
    price_total   = db.Column(db.Float, nullable=False)   # prezzo totale (qty*unit)
    purchase_date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    store         = db.Column(db.String(200), nullable=True)
    notes         = db.Column(db.Text, nullable=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('pantry_purchases', lazy='dynamic'))

    @property
    def price_per_unit(self) -> float:
        return round(self.price_total / self.quantity, 2) if self.quantity else 0

    def __repr__(self) -> str:
        return f'<PantryPurchase {self.product_id} qty={self.quantity}>'


class PantryStock(db.Model):
    """Livello corrente di stock per prodotto."""
    __tablename__ = 'pantry_stock'

    id               = db.Column(db.Integer, primary_key=True)
    product_id       = db.Column(db.Integer, db.ForeignKey('pantry_products.id'),
                                 unique=True, nullable=False)
    quantity_current = db.Column(db.Float, default=0)
    quantity_min     = db.Column(db.Float, default=1)   # soglia alert
    updated_at       = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def is_low(self) -> bool:
        return self.quantity_current <= self.quantity_min

    def __repr__(self) -> str:
        return f'<PantryStock product={self.product_id} qty={self.quantity_current}>'


class PantryHousehold(db.Model):
    """Associa utenti a una dispensa condivisa (gruppo famiglia)."""
    __tablename__ = 'pantry_household'

    id        = db.Column(db.Integer, primary_key=True)
    user_id   = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    role      = db.Column(db.String(20), default='member')   # 'admin' | 'member'
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('pantry_household', uselist=False))

    def __repr__(self) -> str:
        return f'<PantryHousehold user={self.user_id} role={self.role}>'
