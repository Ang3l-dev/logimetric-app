"""
Route Claude API per la Dispensa.
Usa requests direttamente invece dell'SDK anthropic
per compatibilità con Python 3.14 su Render.
"""
from __future__ import annotations
import json
import os
import re
from datetime import date, timedelta

import requests
from flask import jsonify, request
from flask_login import current_user, login_required
from sqlalchemy import func

from . import dispensa_bp
from .. import db
from .models_dispensa import PantryProduct, PantryPurchase, PantryStock

ANTHROPIC_API_URL = 'https://api.anthropic.com/v1/messages'
ANTHROPIC_VERSION = '2023-06-01'
MODEL = 'claude-sonnet-4-20250514'
MODEL_FAST = 'claude-haiku-4-5-20251001'


def _headers() -> dict:
    return {
        'x-api-key': os.environ.get('ANTHROPIC_API_KEY', ''),
        'anthropic-version': ANTHROPIC_VERSION,
        'content-type': 'application/json',
    }


def _claude(messages: list, system: str = '', max_tokens: int = 2048,
            fast: bool = False) -> str:
    """Chiama Claude API e restituisce il testo della risposta."""
    payload = {
        'model': MODEL_FAST if fast else MODEL,
        'max_tokens': max_tokens,
        'messages': messages,
    }
    if system:
        payload['system'] = system

    r = requests.post(ANTHROPIC_API_URL, headers=_headers(),
                      json=payload, timeout=90)
    r.raise_for_status()
    return r.json()['content'][0]['text'].strip()


# ── Diagnostica ───────────────────────────────────────────────────────────────

@dispensa_bp.route('/api/claude/status', methods=['GET'])
@login_required
def api_claude_status():
    key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not key:
        return jsonify({'ok': False, 'error': 'ANTHROPIC_API_KEY mancante'})
    try:
        text = _claude(
            messages=[{'role': 'user', 'content': 'Rispondi solo: OK'}],
            fast=True, max_tokens=5
        )
        return jsonify({'ok': True, 'reply': text, 'key_prefix': key[:15] + '...'})
    except requests.HTTPError as e:
        return jsonify({'ok': False, 'error': f'HTTP {e.response.status_code}: {e.response.text[:200]}'})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e), 'type': type(e).__name__})


# ── Scan scontrino ────────────────────────────────────────────────────────────

@dispensa_bp.route('/api/claude/scan', methods=['POST'])
@login_required
def api_claude_scan():
    data = request.get_json(force=True)
    image_b64 = data.get('image_base64', '')
    media_type = data.get('media_type', 'image/jpeg')

    if not image_b64:
        return jsonify({'ok': False, 'error': 'Immagine mancante'}), 400

    if not os.environ.get('ANTHROPIC_API_KEY'):
        return jsonify({'ok': False, 'error': 'ANTHROPIC_API_KEY non configurata'}), 500

    prompt = """Analizza questo scontrino di un supermercato italiano ed estrai tutti i prodotti.
Rispondi SOLO con un oggetto JSON valido, nessun testo aggiuntivo, nessun markdown.

Formato:
{"negozio":"nome catena","data":"YYYY-MM-DD","prodotti":[{"nome":"nome leggibile","quantita":1,"prezzo_totale":1.99,"categoria":"Categoria"}],"totale":77.70}

Categorie: Frutta e Verdura, Carne e Pesce, Latticini e Uova, Pasta e Cereali,
Pane e Bakery, Conserve e Scatolame, Surgelati, Bevande, Pulizia Casa,
Igiene Personale, Snack e Dolci, Condimenti e Spezie, Altro.

Regole: includi OGNI prodotto, traduci abbreviazioni in nomi leggibili,
il prezzo e il numero a DESTRA di ogni riga, ignora SUBTOTALE/TOTALE/IVA/pagamento,
usa null se non leggibile. Solo JSON."""

    try:
        raw = _claude(messages=[{
            'role': 'user',
            'content': [
                {'type': 'image', 'source': {
                    'type': 'base64',
                    'media_type': media_type,
                    'data': image_b64,
                }},
                {'type': 'text', 'text': prompt},
            ],
        }], max_tokens=2048)

        match = re.search(r'\{[\s\S]*\}', raw)
        if not match:
            return jsonify({'ok': False, 'error': 'Risposta non JSON', 'raw': raw[:300]}), 500

        result = json.loads(match.group(0))
        return jsonify({'ok': True, 'data': result})

    except requests.HTTPError as e:
        return jsonify({'ok': False, 'error': f'HTTP {e.response.status_code}: {e.response.text[:200]}'}), 500
    except json.JSONDecodeError as e:
        return jsonify({'ok': False, 'error': f'JSON parse error: {e}'}), 500
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e), 'type': type(e).__name__}), 500


# ── Lista della spesa ─────────────────────────────────────────────────────────

@dispensa_bp.route('/api/claude/shopping-list', methods=['POST'])
@login_required
def api_claude_shopping_list():
    if not os.environ.get('ANTHROPIC_API_KEY'):
        return jsonify({'ok': False, 'error': 'ANTHROPIC_API_KEY non configurata'}), 500

    # dry_run per il check status
    data = request.get_json(force=True) or {}
    if data.get('dry_run'):
        return jsonify({'ok': True, 'data': {'lista': [], 'note': ''}})

    cutoff = date.today() - timedelta(days=90)
    purchases = (db.session.query(PantryPurchase, PantryProduct)
                 .join(PantryProduct)
                 .filter(PantryPurchase.purchase_date >= cutoff)
                 .order_by(PantryPurchase.purchase_date.desc()).all())

    stocks = db.session.query(PantryStock, PantryProduct).join(PantryProduct).all()

    by_product: dict[str, dict] = {}
    for p, prod in purchases:
        k = prod.name
        if k not in by_product:
            by_product[k] = {'nome': k, 'categoria': prod.category, 'acquisti': []}
        by_product[k]['acquisti'].append({
            'data': p.purchase_date.strftime('%Y-%m-%d'),
            'qty': p.quantity, 'euro': p.price_total,
        })

    stock_map = {prod.name: {
        'qty_attuale': s.quantity_current,
        'esaurimento': s.is_low,
    } for s, prod in stocks}

    context = {
        'data_oggi': date.today().strftime('%Y-%m-%d'),
        'prodotti': list(by_product.values()),
        'stock': stock_map,
    }

    prompt = f"""Sei un assistente per la spesa domestica italiana.
Analizza questi dati e genera la lista della spesa per la prossima settimana.

DATI: {json.dumps(context, ensure_ascii=False)}

Rispondi SOLO con JSON:
{{"lista":[{{"prodotto":"nome","quantita":1,"unita":"kg","priorita":"alta|media|bassa","motivo":"max 15 parole"}}],"note":"consiglio opzionale"}}

Ordina per priorità. Solo JSON."""

    try:
        raw = _claude(messages=[{'role': 'user', 'content': prompt}], max_tokens=1500)
        match = re.search(r'\{[\s\S]*\}', raw)
        result = json.loads(match.group(0)) if match else {'lista': [], 'note': ''}
        return jsonify({'ok': True, 'data': result})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


# ── Chat ──────────────────────────────────────────────────────────────────────

@dispensa_bp.route('/api/claude/chat', methods=['POST'])
@login_required
def api_claude_chat():
    if not os.environ.get('ANTHROPIC_API_KEY'):
        return jsonify({'ok': False, 'error': 'ANTHROPIC_API_KEY non configurata'}), 500

    data = request.get_json(force=True)
    user_message = data.get('message', '').strip()
    if not user_message:
        return jsonify({'ok': False, 'error': 'Messaggio vuoto'}), 400

    cutoff = date.today() - timedelta(days=90)
    top = (db.session.query(
            PantryProduct.name, PantryProduct.category,
            func.count(PantryPurchase.id).label('n'),
            func.sum(PantryPurchase.price_total).label('tot'),
        )
        .join(PantryPurchase, PantryPurchase.product_id == PantryProduct.id)
        .filter(PantryPurchase.purchase_date >= cutoff)
        .group_by(PantryProduct.id)
        .order_by(func.count(PantryPurchase.id).desc())
        .limit(20).all())

    stocks_low = (db.session.query(PantryStock, PantryProduct)
                  .join(PantryProduct)
                  .filter(PantryStock.quantity_current <= PantryStock.quantity_min).all())

    ctx = {
        'top_prodotti': [{'nome': r.name, 'acquisti': r.n,
                          'spesa': round(float(r.tot), 2)} for r in top],
        'esaurimento': [p.name for _, p in stocks_low],
        'data': date.today().strftime('%Y-%m-%d'),
    }

    system = f"""Sei un assistente per la dispensa domestica italiana.
Dati reali degli ultimi 90 giorni: {json.dumps(ctx, ensure_ascii=False)}
Rispondi in italiano, conciso e pratico."""

    try:
        reply = _claude(
            messages=[{'role': 'user', 'content': user_message}],
            system=system, max_tokens=600, fast=True
        )
        return jsonify({'ok': True, 'reply': reply})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
