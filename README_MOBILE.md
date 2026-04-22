# LogiMetric — Mobile PWA Patch

## Cosa contiene questo pacchetto

Questo pacchetto trasforma LogiMetric in una **Progressive Web App (PWA)**
installabile sull'iPhone come app nativa, con navigazione bottom-tab ottimizzata
per lo schermo del telefono.

---

## Come applicare il patch (5 minuti)

### 1. Sostituisci i file nel tuo progetto

Copia i file mantenendo la struttura delle cartelle:

```
app/
├── templates/
│   └── base.html           ← sostituisce il vecchio
└── static/
    ├── css/
    │   └── mobile.css      ← NUOVO
    ├── sw.js               ← NUOVO (service worker)
    ├── manifest.json       ← NUOVO (manifest PWA)
    └── assets/
        ├── icon-192.png    ← NUOVO
        ├── icon-512.png    ← NUOVO
        └── apple-touch-icon.png  ← NUOVO
```

### 2. Servire `sw.js` dalla root

Il service worker deve essere raggiungibile da `/sw.js`.
Aggiungi questa route in `app/__init__.py` oppure crea un endpoint dedicato
(opzionale, funziona anche via static):

```python
# Già gestito automaticamente grazie al path /static/sw.js
# Non serve nessuna modifica se usi la route standard Flask
```

### 3. Deploy

Fai il push sul tuo repository e Render aggiornerà automaticamente.

---

## Installare l'app su iPhone

1. Apri Safari e vai all'URL del tuo sito LogiMetric
2. Tocca il pulsante **Condividi** (quadrato con freccia in su)
3. Scorri e tocca **"Aggiungi alla schermata Home"**
4. Dai il nome **LogiMetric** e tocca **Aggiungi**

✅ Da ora in poi si apre come un'app vera, senza la barra di Safari!

---

## Cosa cambia nell'interfaccia mobile

| Desktop | Mobile |
|---------|--------|
| Sidebar laterale | **Bottom tab bar** (stile iOS) |
| Navigazione sidebar | **Home / Task / Aste / BI / Altro** |
| Voci extra (Trasferta, Ammin.) | **Sheet "Altro"** che sale dal basso |
| Avatar utente sidebar | **Pulsante in alto a destra** → drawer |

### Funzionalità mobile aggiuntive
- 🔵 **Safe areas** per iPhone con notch e Dynamic Island
- 📱 **Standalone mode** — niente barra Safari
- 💾 **Cache offline** per asset statici (CSS, JS, immagini)
- 🔔 **Banner "Installa"** che appare automaticamente su iOS
- 👆 **Touch feedback** su tutti i pulsanti
- 📏 **Font size 16px** sugli input (evita lo zoom automatico di iOS)
- 📜 **Kanban board** con scroll orizzontale

---

## Compatibilità

- ✅ iPhone (iOS 14+) — Safari
- ✅ Android — Chrome
- ✅ Desktop — comportamento invariato (sidebar classica)
