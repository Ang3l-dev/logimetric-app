"""
Blueprint: dispensa
Routes per la gestione della dispensa domestica con IA locale / servizi AI.
"""

from __future__ import annotations

from datetime import datetime, date, timedelta
from collections import defaultdict
from typing import Any

from flask import abort, current_app, jsonify, render_template, request
from flask_login import current_user, login_required
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from . import dispensa_bp
from .. import db
from .models_dispensa import (
    PantryProduct,
    PantryPurchase,
    PantryStock,
    PantryHousehold,
    PantryFamilyMember,
    PantryShoppingSession,
    PantryShoppingItem,
    PANTRY_CATEGORIES,
    PANTRY_UNITS,
)


# ── Guard helpers ─────────────────────────────────────────────────────────────

def _require_view() -> None:
    if not current_user.is_authenticated or not current_user.can_view("dispensa"):
        abort(403)


def _require_write() -> None:
    if not current_user.is_authenticated or not current_user.can_write("dispensa"):
        abort(403)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _json_payload() -> dict[str, Any]:
    """Legge il JSON senza mandare in errore Flask se il body è vuoto/non valido."""
    return request.get_json(silent=True) or {}


def _clean_text(value: Any, default: str = "") -> str:
    """Normalizza testo base evitando None."""
    if value is None:
        return default
    return str(value).strip()


def _normalize_product_name(value: Any) -> str:
    """
    Normalizzazione minima del nome prodotto.

    Nota:
    - Non usa lower() nella query SQL.
    - Salva un nome coerente in DB.
    - Evita differenze inutili tipo doppi spazi.
    """
    name = _clean_text(value)
    name = " ".join(name.split())
    return name.title()


def _safe_float(value: Any, default: float = 0.0) -> float:
    """
    Converte in float gestendo:
    - None
    - stringhe vuote
    - virgola decimale italiana
    """
    if value is None:
        return default

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text:
        return default

    # Gestione semplice formato italiano: "1,25" -> "1.25"
    text = text.replace(",", ".")

    try:
        return float(text)
    except (TypeError, ValueError):
        return default


def _safe_date(value: Any) -> date:
    """Converte una stringa YYYY-MM-DD in date; fallback a oggi."""
    raw = _clean_text(value, date.today().isoformat())

    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return date.today()


def _safe_category(value: Any) -> str:
    category = _clean_text(value, "Altro")
    return category if category in PANTRY_CATEGORIES else "Altro"


def _safe_unit(value: Any) -> str:
    unit = _clean_text(value, "pz")
    return unit if unit in PANTRY_UNITS else "pz"


def _ensure_stock(product_id: int) -> PantryStock:
    """Crea il record stock se non esiste ancora."""
    stock = PantryStock.query.filter_by(product_id=product_id).first()

    if stock:
        return stock

    stock = PantryStock(product_id=product_id)
    db.session.add(stock)
    db.session.flush()

    return stock


def _get_or_create_product(
    name: str,
    category: str = "Altro",
    unit: str = "pz",
) -> PantryProduct:
    """
    Recupera o crea un prodotto.

    Correzione importante:
    prima usavi:

        func.lower(PantryProduct.name) == name.lower()

    Questo può rendere la query più lenta e impedire l'uso corretto degli indici.
    Qui normalizziamo il nome lato Python e cerchiamo con filter_by(name=...).
    """
    clean_name = _normalize_product_name(name)

    if not clean_name:
        raise ValueError("Nome prodotto vuoto")

    clean_category = _safe_category(category)
    clean_unit = _safe_unit(unit)

    prod = PantryProduct.query.filter_by(name=clean_name).first()

    if prod:
        # Aggiorna categoria/unità solo se mancanti o generiche.
        if clean_category and (not prod.category or prod.category == "Altro"):
            prod.category = clean_category

        if clean_unit and not prod.unit:
            prod.unit = clean_unit

        return prod

    prod = PantryProduct(
        name=clean_name,
        category=clean_category,
        unit=clean_unit,
    )

    db.session.add(prod)

    try:
        db.session.flush()
    except IntegrityError:
        # Protezione in caso di doppio inserimento concorrente.
        db.session.rollback()

        prod = PantryProduct.query.filter_by(name=clean_name).first()
        if prod:
            return prod

        raise

    _ensure_stock(prod.id)

    return prod


# ── Main dashboard ────────────────────────────────────────────────────────────

@dispensa_bp.route("/")
@login_required
def index():
    _require_view()

    stocks = (
        db.session.query(PantryStock, PantryProduct)
        .join(PantryProduct, PantryStock.product_id == PantryProduct.id)
        .order_by(PantryProduct.category, PantryProduct.name)
        .all()
    )

    alerts = [(s, p) for s, p in stocks if s.is_low and s.quantity_current >= 0]

    recent = (
        PantryPurchase.query
        .order_by(
            PantryPurchase.purchase_date.desc(),
            PantryPurchase.created_at.desc(),
        )
        .limit(10)
        .all()
    )

    today = date.today()
    month_start = today.replace(day=1)

    month_spend = (
        db.session.query(func.sum(PantryPurchase.price_total))
        .filter(PantryPurchase.purchase_date >= month_start)
        .scalar()
    ) or 0.0

    return render_template(
        "dispensa/index.html",
        stocks=stocks,
        alerts=alerts,
        recent=recent,
        month_spend=month_spend,
        categories=PANTRY_CATEGORIES,
        units=PANTRY_UNITS,
    )


@dispensa_bp.route("/lista-spesa")
@login_required
def todo():
    _require_view()
    return render_template("dispensa/todo.html")


# ── Scanner scontrino ─────────────────────────────────────────────────────────

@dispensa_bp.route("/scan")
@login_required
def scan():
    _require_write()

    return render_template(
        "dispensa/scan.html",
        categories=PANTRY_CATEGORIES,
        units=PANTRY_UNITS,
    )


@dispensa_bp.route("/api/save-purchase", methods=["POST"])
@login_required
def api_save_purchase():
    """
    Salva un acquisto singolo o un batch da scontrino.

    Correzioni principali:
    - commit unico finale;
    - niente query ripetute per recuperare saved_ids;
    - parsing sicuro di quantità/prezzi;
    - rollback e log in caso di errore;
    - evita query SQL con lower().
    """
    _require_write()

    data = _json_payload()

    items = data.get("items") or []
    store = _clean_text(data.get("store")) or None
    purchase_date = _safe_date(data.get("date"))

    if not isinstance(items, list) or not items:
        return jsonify({
            "ok": False,
            "error": "Nessun prodotto da salvare.",
        }), 400

    saved_names: list[str] = []
    saved_ids: list[int] = []

    try:
        for item in items:
            if not isinstance(item, dict):
                continue

            name = _normalize_product_name(item.get("name"))
            qty = _safe_float(item.get("quantity"), 1.0)
            price = _safe_float(item.get("price_total"), 0.0)
            category = _safe_category(item.get("category"))
            unit = _safe_unit(item.get("unit"))

            if not name or qty <= 0:
                continue

            prod = _get_or_create_product(name, category, unit)
            stock = _ensure_stock(prod.id)

            purchase = PantryPurchase(
                product_id=prod.id,
                user_id=current_user.id,
                quantity=qty,
                price_total=price,
                purchase_date=purchase_date,
                store=store,
            )
            db.session.add(purchase)

            stock.quantity_current = _safe_float(stock.quantity_current, 0.0) + qty
            stock.updated_at = datetime.utcnow()

            saved_names.append(prod.name)
            saved_ids.append(prod.id)

        if not saved_ids:
            db.session.rollback()
            return jsonify({
                "ok": False,
                "error": "Nessun prodotto valido da salvare.",
            }), 400

        db.session.commit()

        return jsonify({
            "ok": True,
            "saved": saved_names,
            "count": len(saved_names),
            "product_ids": saved_ids,
        })

    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception("Errore durante il salvataggio dello scontrino")

        return jsonify({
            "ok": False,
            "error": str(exc),
        }), 500


@dispensa_bp.route("/api/products/delete", methods=["POST"])
@login_required
def api_product_delete():
    """Elimina un prodotto e tutto lo storico acquisti correlato."""
    _require_write()

    data = _json_payload()
    product_id = data.get("product_id")

    prod = db.session.get(PantryProduct, product_id)

    if not prod:
        return jsonify({
            "ok": False,
            "error": "Prodotto non trovato",
        }), 404

    try:
        db.session.delete(prod)
        db.session.commit()

        return jsonify({"ok": True})

    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception("Errore eliminazione prodotto")

        return jsonify({
            "ok": False,
            "error": str(exc),
        }), 500


# ── Stock API ─────────────────────────────────────────────────────────────────

@dispensa_bp.route("/api/stock", methods=["GET"])
@login_required
def api_stock():
    _require_view()

    rows = (
        db.session.query(PantryStock, PantryProduct)
        .join(PantryProduct)
        .order_by(PantryProduct.name)
        .all()
    )

    return jsonify([
        {
            "stock_id": s.id,
            "product_id": p.id,
            "name": p.name,
            "category": p.category,
            "unit": p.unit,
            "qty_current": s.quantity_current,
            "qty_min": s.quantity_min,
            "is_low": s.is_low,
            "updated_at": s.updated_at.strftime("%Y-%m-%d %H:%M") if s.updated_at else None,
        }
        for s, p in rows
    ])


@dispensa_bp.route("/api/stock/update", methods=["POST"])
@login_required
def api_stock_update():
    """Aggiorna manualmente la quantità in stock di un prodotto."""
    _require_write()

    data = _json_payload()
    stock_id = data.get("stock_id")
    qty = data.get("qty_current")
    qty_min = data.get("qty_min")

    stock = db.session.get(PantryStock, stock_id)

    if not stock:
        return jsonify({
            "ok": False,
            "error": "Stock non trovato",
        }), 404

    if qty is not None:
        stock.quantity_current = max(0.0, _safe_float(qty, 0.0))

    if qty_min is not None:
        stock.quantity_min = max(0.0, _safe_float(qty_min, 0.0))

    stock.updated_at = datetime.utcnow()

    try:
        db.session.commit()

        return jsonify({"ok": True})

    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception("Errore aggiornamento stock")

        return jsonify({
            "ok": False,
            "error": str(exc),
        }), 500


@dispensa_bp.route("/api/stock/consume", methods=["POST"])
@login_required
def api_stock_consume():
    """Decrementa lo stock quando si usa un prodotto dalla dispensa."""
    _require_write()

    data = _json_payload()
    product_id = data.get("product_id")
    qty = _safe_float(data.get("qty"), 1.0)

    if qty <= 0:
        return jsonify({
            "ok": False,
            "error": "Quantità non valida",
        }), 400

    stock = PantryStock.query.filter_by(product_id=product_id).first()

    if not stock:
        return jsonify({
            "ok": False,
            "error": "Stock non trovato",
        }), 404

    stock.quantity_current = max(0.0, _safe_float(stock.quantity_current, 0.0) - qty)
    stock.updated_at = datetime.utcnow()

    try:
        db.session.commit()

        return jsonify({
            "ok": True,
            "qty_current": stock.quantity_current,
        })

    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception("Errore consumo stock")

        return jsonify({
            "ok": False,
            "error": str(exc),
        }), 500


# ── Prodotti API ──────────────────────────────────────────────────────────────

@dispensa_bp.route("/api/products", methods=["GET"])
@login_required
def api_products():
    _require_view()

    q = _clean_text(request.args.get("q"))
    query = PantryProduct.query

    if q:
        query = query.filter(PantryProduct.name.ilike(f"%{q}%"))

    prods = query.order_by(PantryProduct.name).limit(50).all()

    return jsonify([
        {
            "id": p.id,
            "name": p.name,
            "category": p.category,
            "unit": p.unit,
        }
        for p in prods
    ])


@dispensa_bp.route("/api/products/add", methods=["POST"])
@login_required
def api_product_add():
    _require_write()

    data = _json_payload()
    name = _normalize_product_name(data.get("name"))

    if not name:
        return jsonify({
            "ok": False,
            "error": "Nome obbligatorio",
        }), 400

    try:
        prod = _get_or_create_product(
            name=name,
            category=data.get("category", "Altro"),
            unit=data.get("unit", "pz"),
        )

        db.session.commit()

        return jsonify({
            "ok": True,
            "product_id": prod.id,
            "name": prod.name,
        })

    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception("Errore aggiunta prodotto")

        return jsonify({
            "ok": False,
            "error": str(exc),
        }), 500


# ── AI context API ────────────────────────────────────────────────────────────

@dispensa_bp.route("/api/ai/context", methods=["GET"])
@login_required
def api_ai_context():
    """
    Restituisce il contesto degli acquisti degli ultimi 90 giorni
    in formato JSON compatto.
    """
    _require_view()

    cutoff = date.today() - timedelta(days=90)

    purchases = (
        db.session.query(PantryPurchase, PantryProduct)
        .join(PantryProduct)
        .filter(PantryPurchase.purchase_date >= cutoff)
        .order_by(PantryPurchase.purchase_date.desc())
        .all()
    )

    by_product: dict[str, dict[str, Any]] = {}

    for purchase, prod in purchases:
        key = prod.name

        if key not in by_product:
            by_product[key] = {
                "nome": prod.name,
                "categoria": prod.category,
                "unita": prod.unit,
                "acquisti": [],
            }

        by_product[key]["acquisti"].append({
            "data": purchase.purchase_date.strftime("%Y-%m-%d"),
            "qty": purchase.quantity,
            "euro": purchase.price_total,
        })

    stocks = (
        db.session.query(PantryStock, PantryProduct)
        .join(PantryProduct)
        .all()
    )

    stock_map = {
        prod.name: {
            "qty_attuale": stock.quantity_current,
            "qty_minima": stock.quantity_min,
            "in_esaurimento": stock.is_low,
        }
        for stock, prod in stocks
    }

    return jsonify({
        "data_oggi": date.today().strftime("%Y-%m-%d"),
        "periodo_giorni": 90,
        "prodotti": list(by_product.values()),
        "stock_attuale": stock_map,
    })


# ── Report ────────────────────────────────────────────────────────────────────

@dispensa_bp.route("/reports")
@login_required
def reports():
    _require_view()
    return render_template("dispensa/reports.html")


@dispensa_bp.route("/api/reports/data", methods=["GET"])
@login_required
def api_reports_data():
    _require_view()

    period = request.args.get("period", "month")
    today = date.today()

    if period == "week":
        cutoff = today - timedelta(days=7)
    elif period == "year":
        cutoff = today - timedelta(days=365)
    else:
        cutoff = today - timedelta(days=30)

    purchases = (
        db.session.query(PantryPurchase, PantryProduct)
        .join(PantryProduct)
        .filter(PantryPurchase.purchase_date >= cutoff)
        .order_by(PantryPurchase.purchase_date)
        .all()
    )

    daily: dict[str, float] = defaultdict(float)
    freq: dict[str, int] = defaultdict(int)
    spent: dict[str, float] = defaultdict(float)
    by_cat: dict[str, float] = defaultdict(float)

    for purchase, prod in purchases:
        daily[purchase.purchase_date.strftime("%Y-%m-%d")] += purchase.price_total
        freq[prod.name] += 1
        spent[prod.name] += purchase.price_total
        by_cat[prod.category] += purchase.price_total

    top_freq = sorted(freq.items(), key=lambda x: x[1], reverse=True)[:10]
    top_spent = sorted(spent.items(), key=lambda x: x[1], reverse=True)[:10]

    month_start = today.replace(day=1)
    previous_month_start = (month_start - timedelta(days=1)).replace(day=1)

    cur_month = (
        db.session.query(func.sum(PantryPurchase.price_total))
        .filter(PantryPurchase.purchase_date >= month_start)
        .scalar()
    ) or 0.0

    prev_month = (
        db.session.query(func.sum(PantryPurchase.price_total))
        .filter(
            PantryPurchase.purchase_date >= previous_month_start,
            PantryPurchase.purchase_date < month_start,
        )
        .scalar()
    ) or 0.0

    total = sum(p.price_total for p, _ in purchases)
    n_purchases = len(purchases)

    return jsonify({
        "period": period,
        "total": round(total, 2),
        "n_purchases": n_purchases,
        "daily": dict(sorted(daily.items())),
        "top_freq": [{"name": n, "count": c} for n, c in top_freq],
        "top_spent": [{"name": n, "total": round(t, 2)} for n, t in top_spent],
        "by_category": [
            {"cat": c, "total": round(t, 2)}
            for c, t in sorted(by_cat.items(), key=lambda x: x[1], reverse=True)
        ],
        "month_compare": {
            "current": round(cur_month, 2),
            "previous": round(prev_month, 2),
            "delta": round(cur_month - prev_month, 2),
        },
    })


# ── Nucleo familiare ──────────────────────────────────────────────────────────

@dispensa_bp.route("/api/family", methods=["GET"])
@login_required
def api_family_list():
    _require_view()

    members = PantryFamilyMember.query.order_by(PantryFamilyMember.created_at).all()

    return jsonify([
        {
            "id": m.id,
            "name": m.name,
            "member_type": m.member_type,
            "birth_year": m.birth_year,
            "age": m.age,
            "age_label": m.age_label,
        }
        for m in members
    ])


@dispensa_bp.route("/api/family/add", methods=["POST"])
@login_required
def api_family_add():
    _require_write()

    data = _json_payload()
    name = _clean_text(data.get("name"))

    if not name:
        return jsonify({
            "ok": False,
            "error": "Nome obbligatorio",
        }), 400

    member = PantryFamilyMember(
        name=name,
        member_type=data.get("member_type", "adult"),
        birth_year=data.get("birth_year") or None,
    )

    db.session.add(member)

    try:
        db.session.commit()

        return jsonify({
            "ok": True,
            "id": member.id,
            "age_label": member.age_label,
        })

    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception("Errore aggiunta membro famiglia")

        return jsonify({
            "ok": False,
            "error": str(exc),
        }), 500


@dispensa_bp.route("/api/family/delete", methods=["POST"])
@login_required
def api_family_delete():
    _require_write()

    data = _json_payload()
    member = db.session.get(PantryFamilyMember, data.get("id"))

    if not member:
        return jsonify({
            "ok": False,
            "error": "Membro non trovato",
        }), 404

    db.session.delete(member)

    try:
        db.session.commit()

        return jsonify({"ok": True})

    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception("Errore eliminazione membro famiglia")

        return jsonify({
            "ok": False,
            "error": str(exc),
        }), 500


# ── Classificazione prodotti ──────────────────────────────────────────────────

@dispensa_bp.route("/api/products/set-audience", methods=["POST"])
@login_required
def api_product_set_audience():
    """Aggiorna manualmente la classificazione adulti/bambini di un prodotto."""
    _require_write()

    data = _json_payload()
    prod = db.session.get(PantryProduct, data.get("product_id"))

    if not prod:
        return jsonify({
            "ok": False,
            "error": "Prodotto non trovato",
        }), 404

    prod.target_audience = data.get("target_audience", "all")
    prod.age_min = data.get("age_min") or None
    prod.age_max = data.get("age_max") or None

    try:
        db.session.commit()

        return jsonify({"ok": True})

    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception("Errore aggiornamento audience prodotto")

        return jsonify({
            "ok": False,
            "error": str(exc),
        }), 500


# ── Contesto famiglia per AI ──────────────────────────────────────────────────

@dispensa_bp.route("/api/family/context", methods=["GET"])
@login_required
def api_family_context():
    """Restituisce il profilo famiglia per l'AI."""
    _require_view()

    members = PantryFamilyMember.query.all()
    adults = [m for m in members if m.member_type == "adult"]
    children = [m for m in members if m.member_type == "child"]

    return jsonify({
        "totale_membri": len(members),
        "adulti": len(adults),
        "bambini": [
            {
                "nome": c.name,
                "eta": c.age,
            }
            for c in children
        ],
        "membri": [
            {
                "nome": m.name,
                "tipo": m.member_type,
                "eta": m.age,
            }
            for m in members
        ],
    })


# ── Household ─────────────────────────────────────────────────────────────────

@dispensa_bp.route("/api/household/join", methods=["POST"])
@login_required
def api_household_join():
    """Aggiunge l'utente corrente alla dispensa condivisa."""
    _require_write()

    existing = PantryHousehold.query.filter_by(user_id=current_user.id).first()

    if existing:
        return jsonify({
            "ok": True,
            "message": "Già membro",
        })

    member = PantryHousehold(user_id=current_user.id)
    db.session.add(member)

    try:
        db.session.commit()

        return jsonify({"ok": True})

    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception("Errore join household")

        return jsonify({
            "ok": False,
            "error": str(exc),
        }), 500


# ── Confronto supermercati ────────────────────────────────────────────────────

@dispensa_bp.route("/api/reports/store-compare", methods=["GET"])
@login_required
def api_store_compare():
    _require_view()

    period = request.args.get("period", "month")
    today = date.today()

    if period == "week":
        cutoff = today - timedelta(days=7)
    elif period == "year":
        cutoff = today - timedelta(days=365)
    else:
        cutoff = today - timedelta(days=30)

    rows = (
        db.session.query(
            PantryPurchase.store,
            PantryProduct.category,
            func.sum(PantryPurchase.price_total).label("total"),
            func.sum(PantryPurchase.quantity).label("qty"),
            func.count(PantryPurchase.id).label("n"),
        )
        .join(PantryProduct)
        .filter(
            PantryPurchase.purchase_date >= cutoff,
            PantryPurchase.store.isnot(None),
            PantryPurchase.store != "",
        )
        .group_by(PantryPurchase.store, PantryProduct.category)
        .all()
    )

    stores = sorted(set(r.store for r in rows))
    cats = sorted(set(r.category for r in rows))

    avg_table: dict[str, dict[str, float]] = {}
    total_table: dict[str, dict[str, float]] = {}

    for row in rows:
        total = float(row.total or 0.0)
        qty = float(row.qty or 0.0)

        avg_table.setdefault(row.category, {})[row.store] = round(total / qty, 2) if qty else 0.0
        total_table.setdefault(row.category, {})[row.store] = round(total, 2)

    return jsonify({
        "stores": stores,
        "categories": cats,
        "avg_price": avg_table,
        "total_spend": total_table,
    })


# ── Lista spesa Todo ──────────────────────────────────────────────────────────

@dispensa_bp.route("/api/shopping-session/active", methods=["GET"])
@login_required
def api_shopping_session_active():
    """Restituisce la sessione di spesa attiva, se esiste."""
    _require_view()

    session = (
        PantryShoppingSession.query
        .filter_by(is_active=True)
        .order_by(PantryShoppingSession.created_at.desc())
        .first()
    )

    if not session:
        return jsonify({
            "ok": True,
            "session": None,
        })

    items = session.items.all()

    return jsonify({
        "ok": True,
        "session": {
            "id": session.id,
            "created_at": session.created_at.strftime("%d/%m/%Y %H:%M"),
            "note": session.note,
            "items": [
                {
                    "id": item.id,
                    "product_name": item.product_name,
                    "quantity": item.quantity,
                    "unit": item.unit,
                    "checked": item.checked,
                    "sort_order": item.sort_order,
                }
                for item in items
            ],
            "total": len(items),
            "checked": sum(1 for item in items if item.checked),
        },
    })


@dispensa_bp.route("/api/shopping-session/create", methods=["POST"])
@login_required
def api_shopping_session_create():
    """Crea una nuova sessione con i prodotti dalla lista IA."""
    _require_write()

    data = _json_payload()
    items_data = data.get("items") or []
    note = _clean_text(data.get("note"))

    try:
        PantryShoppingSession.query.filter_by(is_active=True).update({
            "is_active": False,
            "closed_at": datetime.utcnow(),
        })

        session = PantryShoppingSession(note=note)
        db.session.add(session)
        db.session.flush()

        for index, item in enumerate(items_data):
            if not isinstance(item, dict):
                continue

            product_name = _clean_text(
                item.get("prodotto", item.get("product_name", ""))
            )

            if not product_name:
                continue

            db.session.add(PantryShoppingItem(
                session_id=session.id,
                product_name=product_name,
                quantity=_safe_float(item.get("quantita", item.get("quantity", 1)), 1.0),
                unit=_safe_unit(item.get("unita", item.get("unit", "pz"))),
                sort_order=index,
            ))

        db.session.commit()

        return jsonify({
            "ok": True,
            "session_id": session.id,
        })

    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception("Errore creazione sessione spesa")

        return jsonify({
            "ok": False,
            "error": str(exc),
        }), 500


@dispensa_bp.route("/api/shopping-session/toggle", methods=["POST"])
@login_required
def api_shopping_session_toggle():
    """Spunta/deseleziona un prodotto nella lista."""
    _require_write()

    data = _json_payload()
    item = db.session.get(PantryShoppingItem, data.get("item_id"))

    if not item:
        return jsonify({
            "ok": False,
            "error": "Item non trovato",
        }), 404

    item.checked = not item.checked

    try:
        db.session.commit()

        return jsonify({
            "ok": True,
            "checked": item.checked,
        })

    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception("Errore toggle item lista spesa")

        return jsonify({
            "ok": False,
            "error": str(exc),
        }), 500


@dispensa_bp.route("/api/shopping-session/add-item", methods=["POST"])
@login_required
def api_shopping_session_add_item():
    """Aggiunge un prodotto alla sessione attiva."""
    _require_write()

    data = _json_payload()

    session = (
        PantryShoppingSession.query
        .filter_by(is_active=True)
        .order_by(PantryShoppingSession.created_at.desc())
        .first()
    )

    if not session:
        return jsonify({
            "ok": False,
            "error": "Nessuna sessione attiva",
        }), 404

    product_name = _clean_text(data.get("product_name"))

    if not product_name:
        return jsonify({
            "ok": False,
            "error": "Nome prodotto obbligatorio",
        }), 400

    count = session.items.count()

    item = PantryShoppingItem(
        session_id=session.id,
        product_name=product_name,
        quantity=_safe_float(data.get("quantity"), 1.0),
        unit=_safe_unit(data.get("unit")),
        sort_order=count,
    )

    db.session.add(item)

    try:
        db.session.commit()

        return jsonify({
            "ok": True,
            "item_id": item.id,
        })

    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception("Errore aggiunta item lista spesa")

        return jsonify({
            "ok": False,
            "error": str(exc),
        }), 500


@dispensa_bp.route("/api/shopping-session/delete-item", methods=["POST"])
@login_required
def api_shopping_session_delete_item():
    """Elimina un prodotto dalla lista."""
    _require_write()

    data = _json_payload()
    item = db.session.get(PantryShoppingItem, data.get("item_id"))

    if not item:
        return jsonify({
            "ok": False,
            "error": "Item non trovato",
        }), 404

    db.session.delete(item)

    try:
        db.session.commit()

        return jsonify({"ok": True})

    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception("Errore eliminazione item lista spesa")

        return jsonify({
            "ok": False,
            "error": str(exc),
        }), 500


@dispensa_bp.route("/api/shopping-session/close", methods=["POST"])
@login_required
def api_shopping_session_close():
    """Chiude la sessione corrente."""
    _require_write()

    try:
        PantryShoppingSession.query.filter_by(is_active=True).update({
            "is_active": False,
            "closed_at": datetime.utcnow(),
        })

        db.session.commit()

        return jsonify({"ok": True})

    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception("Errore chiusura sessione spesa")

        return jsonify({
            "ok": False,
            "error": str(exc),
        }), 500
