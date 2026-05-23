"""
Blueprint: dispensa
Routes per la gestione della dispensa domestica con IA locale (Ollama).
"""
from __future__ import annotations
import json
from datetime import datetime, date, timedelta
from collections import defaultdict

from flask import abort, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func

from . import dispensa_bp
from .. import db
from .models_dispensa import (
    PantryProduct, PantryPurchase, PantryStock, PantryHousehold,
    PANTRY_CATEGORIES, PANTRY_UNITS,
)


# ── Guard helpers ─────────────────────────────────────────────────────────────

def _require_view():
    if not current_user.is_authenticated or not current_user.can_view('dispensa'):
        abort(403)

def _require_write():
    if not current_user.is_authenticated or not current_user.can_write('dispensa'):
        abort(403)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ensure_stock(product_id: int) -> PantryStock:
    """Crea il record stock se non esiste ancora."""
    stock = PantryStock.query.filter_by(product_id=product_id).first()
    if not stock:
        stock = PantryStock(product_id=product_id)
        db.session.add(stock)
        db.session.flush()
    return stock


def _get_or_create_product(name: str, category: str = 'Altro',
                            unit: str = 'pz') -> PantryProduct:
    name = name.strip().title()
    prod = PantryProduct.query.filter(
        func.lower(PantryProduct.name) == name.lower()
    ).first()
    if not prod:
        prod = PantryProduct(name=name, category=category, unit=unit)
        db.session.add(prod)
        db.session.flush()
        _ensure_stock(prod.id)
    return prod


# ── Main dashboard ────────────────────────────────────────────────────────────

@dispensa_bp.route('/')
@login_required
def index():
    _require_view()

    # Stock con prodotto joinato
    stocks = (db.session.query(PantryStock, PantryProduct)
              .join(PantryProduct, PantryStock.product_id == PantryProduct.id)
              .order_by(PantryProduct.category, PantryProduct.name)
              .all())

    # Alert: prodotti sotto soglia
    alerts = [(s, p) for s, p in stocks if s.is_low and s.quantity_current >= 0]

    # Ultimi 10 acquisti
    recent = (PantryPurchase.query
              .order_by(PantryPurchase.purchase_date.desc(),
                        PantryPurchase.created_at.desc())
              .limit(10).all())

    # KPI mese corrente
    today = date.today()
    month_start = today.replace(day=1)
    month_spend = (db.session.query(func.sum(PantryPurchase.price_total))
                   .filter(PantryPurchase.purchase_date >= month_start)
                   .scalar()) or 0.0

    return render_template('dispensa/index.html',
                           stocks=stocks,
                           alerts=alerts,
                           recent=recent,
                           month_spend=month_spend,
                           categories=PANTRY_CATEGORIES,
                           units=PANTRY_UNITS)


# ── Scanner scontrino ─────────────────────────────────────────────────────────

@dispensa_bp.route('/scan')
@login_required
def scan():
    _require_write()
    return render_template('dispensa/scan.html',
                           categories=PANTRY_CATEGORIES,
                           units=PANTRY_UNITS)


@dispensa_bp.route('/api/save-purchase', methods=['POST'])
@login_required
def api_save_purchase():
    """Salva un acquisto (singolo prodotto o batch da scontrino)."""
    _require_write()
    data = request.get_json(force=True)

    items    = data.get('items', [])
    store    = data.get('store', '').strip()
    raw_date = data.get('date', str(date.today()))

    try:
        purchase_date = datetime.strptime(raw_date, '%Y-%m-%d').date()
    except ValueError:
        purchase_date = date.today()

    saved = []
    try:
        for item in items:
            name     = item.get('name', '').strip()
            qty      = float(item.get('quantity', 1))
            price    = float(item.get('price_total', 0))
            category = item.get('category', 'Altro')
            unit     = item.get('unit', 'pz')

            if not name or qty <= 0:
                continue

            prod  = _get_or_create_product(name, category, unit)
            stock = _ensure_stock(prod.id)

            purchase = PantryPurchase(
                product_id    = prod.id,
                user_id       = current_user.id,
                quantity      = qty,
                price_total   = price,
                purchase_date = purchase_date,
                store         = store or None,
            )
            db.session.add(purchase)

            # Aggiorna stock: aggiunge la quantità comprata
            stock.quantity_current += qty
            stock.updated_at = datetime.utcnow()

            saved.append(prod.name)

        db.session.commit()
        return jsonify({'ok': True, 'saved': saved, 'count': len(saved)})

    except Exception as exc:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(exc)}), 500



@dispensa_bp.route('/api/products/delete', methods=['POST'])
@login_required
def api_product_delete():
    """Elimina un prodotto e tutto lo storico acquisti correlato."""
    _require_write()
    data = request.get_json(force=True)
    product_id = data.get('product_id')
    prod = db.session.get(PantryProduct, product_id)
    if not prod:
        return jsonify({'ok': False, 'error': 'Prodotto non trovato'}), 404
    try:
        db.session.delete(prod)   # cascade elimina stock e purchases
        db.session.commit()
        return jsonify({'ok': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(e)}), 500

# ── Stock API ─────────────────────────────────────────────────────────────────

@dispensa_bp.route('/api/stock', methods=['GET'])
@login_required
def api_stock():
    _require_view()
    rows = (db.session.query(PantryStock, PantryProduct)
            .join(PantryProduct)
            .order_by(PantryProduct.name).all())
    return jsonify([{
        'stock_id':    s.id,
        'product_id':  p.id,
        'name':        p.name,
        'category':    p.category,
        'unit':        p.unit,
        'qty_current': s.quantity_current,
        'qty_min':     s.quantity_min,
        'is_low':      s.is_low,
        'updated_at':  s.updated_at.strftime('%Y-%m-%d %H:%M'),
    } for s, p in rows])


@dispensa_bp.route('/api/stock/update', methods=['POST'])
@login_required
def api_stock_update():
    """Aggiorna manualmente la quantità in stock di un prodotto."""
    _require_write()
    data       = request.get_json(force=True)
    stock_id   = data.get('stock_id')
    qty        = data.get('qty_current')
    qty_min    = data.get('qty_min')

    stock = db.session.get(PantryStock, stock_id)
    if not stock:
        return jsonify({'ok': False, 'error': 'Stock non trovato'}), 404

    if qty is not None:
        stock.quantity_current = max(0, float(qty))
    if qty_min is not None:
        stock.quantity_min = max(0, float(qty_min))
    stock.updated_at = datetime.utcnow()

    try:
        db.session.commit()
        return jsonify({'ok': True})
    except Exception as exc:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(exc)}), 500


@dispensa_bp.route('/api/stock/consume', methods=['POST'])
@login_required
def api_stock_consume():
    """Decrementa lo stock quando si usa un prodotto dalla dispensa."""
    _require_write()
    data       = request.get_json(force=True)
    product_id = data.get('product_id')
    qty        = float(data.get('qty', 1))

    stock = PantryStock.query.filter_by(product_id=product_id).first()
    if not stock:
        return jsonify({'ok': False, 'error': 'Stock non trovato'}), 404

    stock.quantity_current = max(0, stock.quantity_current - qty)
    stock.updated_at = datetime.utcnow()

    try:
        db.session.commit()
        return jsonify({'ok': True, 'qty_current': stock.quantity_current})
    except Exception as exc:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(exc)}), 500


# ── Prodotti API ──────────────────────────────────────────────────────────────

@dispensa_bp.route('/api/products', methods=['GET'])
@login_required
def api_products():
    _require_view()
    q = request.args.get('q', '').strip()
    query = PantryProduct.query
    if q:
        query = query.filter(PantryProduct.name.ilike(f'%{q}%'))
    prods = query.order_by(PantryProduct.name).limit(50).all()
    return jsonify([{
        'id':       p.id,
        'name':     p.name,
        'category': p.category,
        'unit':     p.unit,
    } for p in prods])


@dispensa_bp.route('/api/products/add', methods=['POST'])
@login_required
def api_product_add():
    _require_write()
    data = request.get_json(force=True)
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'ok': False, 'error': 'Nome obbligatorio'}), 400
    try:
        prod = _get_or_create_product(
            name,
            data.get('category', 'Altro'),
            data.get('unit', 'pz'),
        )
        db.session.commit()
        return jsonify({'ok': True, 'product_id': prod.id, 'name': prod.name})
    except Exception as exc:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(exc)}), 500


# ── AI context API (dati storici per Ollama nel browser) ──────────────────────

@dispensa_bp.route('/api/ai/context', methods=['GET'])
@login_required
def api_ai_context():
    """
    Restituisce il contesto degli acquisti degli ultimi 90 giorni
    in formato JSON compatto, pronto per essere passato al prompt di Ollama.
    """
    _require_view()
    cutoff = date.today() - timedelta(days=90)

    purchases = (db.session.query(PantryPurchase, PantryProduct)
                 .join(PantryProduct)
                 .filter(PantryPurchase.purchase_date >= cutoff)
                 .order_by(PantryPurchase.purchase_date.desc())
                 .all())

    # Raggruppa per prodotto
    by_product: dict[str, dict] = {}
    for p, prod in purchases:
        key = prod.name
        if key not in by_product:
            by_product[key] = {
                'nome':     prod.name,
                'categoria': prod.category,
                'unita':    prod.unit,
                'acquisti': [],
            }
        by_product[key]['acquisti'].append({
            'data':  p.purchase_date.strftime('%Y-%m-%d'),
            'qty':   p.quantity,
            'euro':  p.price_total,
        })

    # Stock attuale
    stocks = (db.session.query(PantryStock, PantryProduct)
              .join(PantryProduct).all())
    stock_map = {prod.name: {
        'qty_attuale': s.quantity_current,
        'qty_minima':  s.quantity_min,
        'in_esaurimento': s.is_low,
    } for s, prod in stocks}

    return jsonify({
        'data_oggi':    date.today().strftime('%Y-%m-%d'),
        'periodo_giorni': 90,
        'prodotti':    list(by_product.values()),
        'stock_attuale': stock_map,
    })


# ── Report ────────────────────────────────────────────────────────────────────

@dispensa_bp.route('/reports')
@login_required
def reports():
    _require_view()
    return render_template('dispensa/reports.html')


@dispensa_bp.route('/api/reports/data', methods=['GET'])
@login_required
def api_reports_data():
    _require_view()

    period = request.args.get('period', 'month')  # week | month | year
    today  = date.today()

    if period == 'week':
        cutoff = today - timedelta(days=7)
    elif period == 'year':
        cutoff = today - timedelta(days=365)
    else:  # month default
        cutoff = today - timedelta(days=30)

    purchases = (db.session.query(PantryPurchase, PantryProduct)
                 .join(PantryProduct)
                 .filter(PantryPurchase.purchase_date >= cutoff)
                 .order_by(PantryPurchase.purchase_date)
                 .all())

    # Spesa giornaliera per il grafico a linea
    daily: dict[str, float] = defaultdict(float)
    for p, _ in purchases:
        daily[p.purchase_date.strftime('%Y-%m-%d')] += p.price_total

    # Top prodotti per frequenza
    freq: dict[str, int] = defaultdict(int)
    spent: dict[str, float] = defaultdict(float)
    for p, prod in purchases:
        freq[prod.name] += 1
        spent[prod.name] += p.price_total

    top_freq  = sorted(freq.items(),  key=lambda x: x[1],  reverse=True)[:10]
    top_spent = sorted(spent.items(), key=lambda x: x[1],  reverse=True)[:10]

    # Spesa per categoria
    by_cat: dict[str, float] = defaultdict(float)
    for p, prod in purchases:
        by_cat[prod.category] += p.price_total

    # Confronto mese corrente vs precedente
    m_start  = today.replace(day=1)
    m1_start = (m_start - timedelta(days=1)).replace(day=1)

    cur_month = (db.session.query(func.sum(PantryPurchase.price_total))
                 .filter(PantryPurchase.purchase_date >= m_start)
                 .scalar()) or 0.0
    prev_month = (db.session.query(func.sum(PantryPurchase.price_total))
                  .filter(PantryPurchase.purchase_date >= m1_start,
                          PantryPurchase.purchase_date < m_start)
                  .scalar()) or 0.0

    total = sum(p.price_total for p, _ in purchases)
    n_purchases = len(purchases)

    return jsonify({
        'period':      period,
        'total':       round(total, 2),
        'n_purchases': n_purchases,
        'daily':       dict(sorted(daily.items())),
        'top_freq':    [{'name': n, 'count': c} for n, c in top_freq],
        'top_spent':   [{'name': n, 'total': round(t, 2)} for n, t in top_spent],
        'by_category': [{'cat': c, 'total': round(t, 2)}
                        for c, t in sorted(by_cat.items(), key=lambda x: x[1], reverse=True)],
        'month_compare': {
            'current':  round(cur_month, 2),
            'previous': round(prev_month, 2),
            'delta':    round(cur_month - prev_month, 2),
        },
    })


# ── Household ─────────────────────────────────────────────────────────────────

@dispensa_bp.route('/api/household/join', methods=['POST'])
@login_required
def api_household_join():
    """Aggiunge l'utente corrente alla dispensa condivisa."""
    _require_write()
    existing = PantryHousehold.query.filter_by(user_id=current_user.id).first()
    if existing:
        return jsonify({'ok': True, 'message': 'Già membro'})
    member = PantryHousehold(user_id=current_user.id)
    db.session.add(member)
    try:
        db.session.commit()
        return jsonify({'ok': True})
    except Exception as exc:
        db.session.rollback()
        return jsonify({'ok': False, 'error': str(exc)}), 500
