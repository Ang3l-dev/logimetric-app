"""
Route Claude API per la Dispensa.
Il browser non chiama Claude direttamente — passa sempre per Flask
così la API key rimane sicura sul server.
"""
from __future__ import annotations
import base64
import json
import os
from datetime import date, timedelta

import anthropic
from flask import jsonify, request
from flask_login import current_user, login_required
from sqlalchemy import func

from . import dispensa_bp
from .. import db
from .models_dispensa import PantryProduct, PantryPurchase, PantryStock


def _get_client() -> anthropic.Anthropic | None:
    key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not key:
        return None
    return anthropic.Anthropic(api_key=key)


# ── Scan scontrino ────────────────────────────────────────────────────────────

@dispensa_bp.route('/api/claude/scan', methods=['POST'])
@login_required
def api_claude_scan():
    """
    Riceve un'immagine base64 dal browser,
    la manda a Claude vision e restituisce i prodotti estratti.
    """
    data = request.get_json(force=True)
    image_b64 = data.get('image_base64', '')
    media_type = data.get('media_type', 'image/jpeg')

    if not image_b64:
        return jsonify({'ok': False, 'error': 'Immagine mancante'}), 400

    client = _get_client()
    if not client:
        return jsonify({'ok': False, 'error': 'ANTHROPIC_API_KEY non configurata'}), 500

    prompt = """Analizza questo scontrino di un supermercato italiano ed estrai tutti i prodotti.
Rispondi SOLO con un oggetto JSON valido, nessun testo aggiuntivo, nessun markdown.

Formato richiesto:
{
  "negozio": "nome catena (es: Lidl, Esselunga, Conad)",
  "data": "YYYY-MM-DD",
  "prodotti": [
    {
      "nome": "nome prodotto leggibile in italiano",
      "quantita": 1,
      "prezzo_totale": 1.99,
      "categoria": "una delle categorie ammesse"
    }
  ],
  "totale": 77.70
}

Categorie ammesse: Frutta e Verdura, Carne e Pesce, Latticini e Uova, Pasta e Cereali,
Pane e Bakery, Conserve e Scatolame, Surgelati, Bevande, Pulizia Casa,
Igiene Personale, Snack e Dolci, Condimenti e Spezie, Altro.

Regole:
- Includi OGNI riga prodotto presente nello scontrino
- Traduci le abbreviazioni in nomi leggibili (es: MOZZ.BUFALA → Mozzarella di Bufala)
- Il prezzo è il numero a destra di ogni riga prodotto
- Ignora le righe: SUBTOTALE, TOTALE, IVA, pagamento, importo, documento
- Se un campo non è leggibile usa null
- Rispondi SOLO con il JSON"""

    try:
        message = client.messages.create(
            model='claude-sonnet-4-20250514',
            max_tokens=2048,
            messages=[{
                'role': 'user',
                'content': [
                    {
                        'type': 'image',
                        'source': {
                            'type': 'base64',
                            'media_type': media_type,
                            'data': image_b64,
                        },
                    },
                    {'type': 'text', 'text': prompt},
                ],
            }],
        )

        raw = message.content[0].text.strip()

        # Estrai il JSON dalla risposta
        import re
        match = re.search(r'\{[\s\S]*\}', raw)
        if not match:
            return jsonify({'ok': False, 'error': 'Risposta non JSON', 'raw': raw[:300]}), 500

        result = json.loads(match.group(0))
        return jsonify({'ok': True, 'data': result})

    except anthropic.APIError as e:
        return jsonify({'ok': False, 'error': f'Claude API error: {str(e)}'}), 500
    except json.JSONDecodeError as e:
        return jsonify({'ok': False, 'error': f'JSON parse error: {str(e)}', 'raw': raw[:300]}), 500
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


# ── Lista della spesa IA ──────────────────────────────────────────────────────

@dispensa_bp.route('/api/claude/shopping-list', methods=['POST'])
@login_required
def api_claude_shopping_list():
    """
    Genera la lista della spesa settimanale basandosi
    sullo storico degli ultimi 90 giorni.
    """
    client = _get_client()
    if not client:
        return jsonify({'ok': False, 'error': 'ANTHROPIC_API_KEY non configurata'}), 500

    # Recupera contesto dal DB
    cutoff = date.today() - timedelta(days=90)
    purchases = (db.session.query(PantryPurchase, PantryProduct)
                 .join(PantryProduct)
                 .filter(PantryPurchase.purchase_date >= cutoff)
                 .order_by(PantryPurchase.purchase_date.desc())
                 .all())

    stocks = (db.session.query(PantryStock, PantryProduct)
              .join(PantryProduct).all())

    # Compatta i dati per il prompt
    by_product: dict[str, dict] = {}
    for p, prod in purchases:
        k = prod.name
        if k not in by_product:
            by_product[k] = {'nome': k, 'categoria': prod.category, 'acquisti': []}
        by_product[k]['acquisti'].append({
            'data': p.purchase_date.strftime('%Y-%m-%d'),
            'qty': p.quantity,
            'euro': p.price_total,
        })

    stock_map = {prod.name: {
        'qty_attuale': s.quantity_current,
        'qty_minima': s.quantity_min,
        'esaurimento': s.is_low,
    } for s, prod in stocks}

    context = {
        'data_oggi': date.today().strftime('%Y-%m-%d'),
        'prodotti_acquistati_90gg': list(by_product.values()),
        'stock_attuale': stock_map,
    }

    prompt = f"""Sei un assistente per la gestione della spesa domestica italiana.
Analizza questi dati di acquisto degli ultimi 90 giorni e genera una lista della spesa
ottimale per la prossima settimana.

DATI:
{json.dumps(context, ensure_ascii=False, indent=2)}

Considera:
- La frequenza di acquisto di ogni prodotto (ogni quanti giorni viene ricomprato)
- Le quantità medie acquistate
- I prodotti con stock in esaurimento (esaurimento: true)
- La stagionalità e le abitudini della famiglia

Rispondi SOLO con un JSON valido in questo formato:
{{
  "lista": [
    {{
      "prodotto": "nome prodotto",
      "quantita": 2,
      "unita": "kg",
      "priorita": "alta|media|bassa",
      "motivo": "breve spiegazione (max 15 parole)"
    }}
  ],
  "note": "consiglio generale opzionale (max 30 parole)"
}}

Ordina per priorità (alta prima). Solo JSON, nessun testo aggiuntivo."""

    try:
        message = client.messages.create(
            model='claude-sonnet-4-20250514',
            max_tokens=1500,
            messages=[{'role': 'user', 'content': prompt}],
        )

        raw = message.content[0].text.strip()
        import re
        match = re.search(r'\{[\s\S]*\}', raw)
        result = json.loads(match.group(0)) if match else {}
        return jsonify({'ok': True, 'data': result})

    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


# ── Chat IA dispensa ──────────────────────────────────────────────────────────

@dispensa_bp.route('/api/claude/chat', methods=['POST'])
@login_required
def api_claude_chat():
    """
    Chat libera con Claude sul contesto della dispensa.
    """
    client = _get_client()
    if not client:
        return jsonify({'ok': False, 'error': 'ANTHROPIC_API_KEY non configurata'}), 500

    data = request.get_json(force=True)
    user_message = data.get('message', '').strip()
    if not user_message:
        return jsonify({'ok': False, 'error': 'Messaggio vuoto'}), 400

    # Contesto leggero: top 20 prodotti più acquistati
    cutoff = date.today() - timedelta(days=90)
    top = (db.session.query(
            PantryProduct.name,
            PantryProduct.category,
            func.sum(PantryPurchase.quantity).label('tot_qty'),
            func.sum(PantryPurchase.price_total).label('tot_euro'),
            func.count(PantryPurchase.id).label('n_acquisti'),
        )
        .join(PantryPurchase, PantryPurchase.product_id == PantryProduct.id)
        .filter(PantryPurchase.purchase_date >= cutoff)
        .group_by(PantryProduct.id)
        .order_by(func.count(PantryPurchase.id).desc())
        .limit(20).all())

    stocks_low = (db.session.query(PantryStock, PantryProduct)
                  .join(PantryProduct)
                  .filter(PantryStock.quantity_current <= PantryStock.quantity_min)
                  .all())

    ctx_summary = {
        'top_prodotti': [{'nome': r.name, 'cat': r.category, 'acquisti': r.n_acquisti,
                          'spesa_tot': round(float(r.tot_euro), 2)} for r in top],
        'prodotti_esaurimento': [p.name for _, p in stocks_low],
        'data_oggi': date.today().strftime('%Y-%m-%d'),
    }

    system = f"""Sei un assistente esperto di gestione della dispensa domestica italiana.
Hai accesso ai dati di acquisto della famiglia degli ultimi 90 giorni.

CONTESTO DISPENSA:
{json.dumps(ctx_summary, ensure_ascii=False, indent=2)}

Rispondi in italiano, in modo conciso e pratico. Se ti chiedono cosa comprare,
basa la risposta sui dati reali. Se ti chiedono ricette, tieni conto dei prodotti disponibili."""

    try:
        message = client.messages.create(
            model='claude-sonnet-4-20250514',
            max_tokens=800,
            system=system,
            messages=[{'role': 'user', 'content': user_message}],
        )
        return jsonify({'ok': True, 'reply': message.content[0].text})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
