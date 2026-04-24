# LogiMetric App

Applicazione web per la gestione operativa di LogiMetric.  
Stack: **Flask · SQLAlchemy · PostgreSQL · Brevo · Render**

---

## Funzionalità

| Modulo | Descrizione |
|--------|-------------|
| **Auth** | Login sicuro, registrazione con approvazione admin, reset password via email |
| **Gestione Utenti** | Approvazione registrazioni, permessi per modulo (visualizza / modifica) |
| **Modulo Trasferta** | Compilazione guidata, generazione Excel, preset salvati per utente |
| **Programma Settimanale** | Compilazione settimanale, generazione Excel con template originale |
| **Dashboard BI** | Embed di report Power BI |
| **Email** | Tutte le email transazionali via Brevo (welcome, approvazione, reset pw, alert) |

---

## Setup locale (prima volta)

### 1. Clona il repo
```bash
git clone https://github.com/TUO-USERNAME/logimetric-app.git
cd logimetric-app
```

### 2. Crea virtualenv e installa dipendenze
```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Configura le variabili d'ambiente
```bash
cp .env.example .env
# Apri .env e compila i valori (SECRET_KEY, BREVO_API_KEY, ADMIN_EMAIL)
```

### 4. Avvia in locale
```bash
flask run
# oppure
python app.py
```

Apri http://127.0.0.1:5000 — registrati con la tua `ADMIN_EMAIL` e il tuo account diventa automaticamente Admin.

Nota: in locale il bootstrap DB può essere automatico con `AUTO_DB_BOOTSTRAP=1`; in produzione è raccomandato tenerlo a `0` e usare migration gestite.

---

## Deploy su Render

### 1. Crea repo GitHub privato e fai push
```bash
git init
git add .
git commit -m "initial commit"
git remote add origin https://github.com/TUO-USERNAME/logimetric-app.git
git push -u origin main
```

### 2. Crea il database PostgreSQL su Render
- Dashboard Render → **New → PostgreSQL**
- Nome: `logimetric-db`
- Copia la **"External Database URL"** (ti serve al passo successivo)

### 3. Crea il Web Service
- **New → Web Service** → collega il repo GitHub
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app`
- Runtime: Python 3

### 4. Aggiungi variabili d'ambiente su Render
In **Environment** del Web Service aggiungi:

| Chiave | Valore |
|--------|--------|
| `SECRET_KEY` | stringa casuale lunga (es. `python -c "import secrets; print(secrets.token_hex(32))"`) |
| `DATABASE_URL` | URL copiato dal PostgreSQL Render |
| `BREVO_API_KEY` | la tua API key Brevo |
| `MAIL_SENDER` | `a.venticinque@logimetric.eu` |
| `ADMIN_EMAIL` | `a.venticinque@logimetric.eu` |

### 5. Collega il dominio Aruba
- Render → Settings → **Custom Domain** → aggiungi `www.logimetric.eu`
- Render ti mostra un valore CNAME da copiare
- Aruba → Gestione DNS → aggiungi record:
  - Tipo: `CNAME` · Host: `www` · Valore: `tuo-servizio.onrender.com`
- SSL viene gestito automaticamente da Render (Let's Encrypt)

### 6. Configura Brevo per il dominio
- Brevo → Senders & IPs → Domains → aggiungi `logimetric.eu`
- Brevo ti mostra record DNS (TXT + CNAME) da aggiungere su Aruba
- Questo evita che le email finiscano nello spam

---

## Aggiungere report Power BI alla Dashboard

1. Apri il report su [app.powerbi.com](https://app.powerbi.com)
2. **File → Incorpora report → Sito Web o portale**
3. Copia l'URL `src` dall'iframe
4. Modifica `app/templates/main/dashboard_bi.html`, aggiungi:
   ```html
   <option value="URL_COPIATO">Nome del Report</option>
   ```

---

## Struttura progetto

```
logimetric-app/
├── app.py                          # Entry point
├── requirements.txt
├── render.yaml                     # Config deploy Render
├── .env.example                    # Template variabili d'ambiente
├── templates_excel/                # Template .xls e .xlsx originali
│   ├── NEW - Mod. Trasferta.xls
│   └── Programma settimanale.xlsx
└── app/
    ├── __init__.py                 # Factory Flask
    ├── config.py                   # Configurazione dev/prod
    ├── models.py                   # User, Permission, Preset (SQLAlchemy)
    ├── email_service.py            # Brevo REST API
    ├── validation.py               # Validazione form
    ├── auth/                       # Blueprint: login, register, reset password
    ├── admin_bp/                   # Blueprint: gestione utenti e permessi
    ├── main/                       # Blueprint: moduli operativi
    ├── services/
    │   ├── data_models.py          # Dataclass per i form
    │   ├── excel_service.py        # Generazione Excel (openpyxl + win32com)
    │   ├── weekly_program_service.py
    │   └── presets_service.py
    ├── static/
    │   ├── css/app.css             # Dark theme LogiMetric completo
    │   ├── js/app.js
    │   ├── js/travel_form.js
    │   ├── js/weekly_program.js
    │   └── assets/                 # logo.svg, favicon.svg
    └── templates/
        ├── base.html               # Shell con sidebar
        ├── auth/                   # login, register, forgot/reset password
        ├── admin/                  # users, user_permissions
        └── main/                   # home, travel_form, weekly_program, dashboard_bi
```

---

## Note tecniche

- **Excel su Linux (Render):** la generazione del Modulo Trasferta usa `openpyxl` e produce un file `.xlsx` ben formattato. Il template `.xls` originale con COM automation funziona solo su Windows con Excel installato.
- **Database:** SQLite in locale (nessuna configurazione), PostgreSQL in produzione su Render.
- **Sessioni:** gestite da Flask-Login con cookie hardenizzati (`httponly`, `samesite`, `secure` in produzione).
- **CSRF:** protezione lato form e richieste fetch same-origin.
- **Healthcheck:** `GET /healthz` e `GET /readyz`.
- **Password:** hash bcrypt (12 rounds).
- **Reset password:** token HMAC con scadenza 1 ora (itsdangerous).
