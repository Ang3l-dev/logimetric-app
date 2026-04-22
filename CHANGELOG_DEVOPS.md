# Hardened build notes

## Interventi applicati
- introdotta protezione CSRF lato form e fetch same-origin
- introdotti header di hardening (`X-Frame-Options`, `nosniff`, `Referrer-Policy`, `Permissions-Policy`, HSTS su HTTPS)
- aggiunto `ProxyFix` per deploy dietro reverse proxy / Render
- aggiunti endpoint `GET /healthz` e `GET /readyz`
- migliorata la configurazione dei cookie di sessione/remember
- eliminato il bootstrap DB aggressivo in produzione (`AUTO_DB_BOOTSTRAP=0` su Render)
- mantenuta una modalità legacy di bootstrap solo per ambienti locali/esistenti
- aggiunto logging con request id
- aggiunto rate limiting base su login e reset password
- chiuso il redirect post-login con validazione safe del parametro `next`
- aggiornati `.env.example` e `render.yaml`

## Note operative
- in produzione è raccomandato usare Flask-Migrate/Alembic per gli upgrade schema
- il rate limiting attuale è process-local: è sufficiente per MVP / singola istanza, non per cluster avanzati
- le route pubbliche tokenizzate del modulo task restano esenti da CSRF per compatibilità con i link esterni già previsti

## Verifica eseguita
- compilazione Python completata con successo (`python -m compileall app app.py wsgi.py`)
- il runtime Flask completo non è stato eseguito in questo ambiente perché le dipendenze web non sono installate nel container di lavoro
