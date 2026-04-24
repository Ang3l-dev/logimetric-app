# Task Manager — upgrade aprile 2026

Questa patch aggiorna il backend Flask/LogiMetric su tre fronti:

1. **Apertura task da email / cold start più robusta**
2. **Allegati task e allegati risposta via link OneDrive/SharePoint**
3. **Reminder automatici a T-2, T-1 e giorno di scadenza alle 08:00**

## 1) Apertura task da email più robusta

### Cosa è stato aggiunto nel repo
- relay page `/tasks/open/<task_id>` con warm-up visivo e redirect differito a Power App
- endpoint pubblico leggero `/tasks/api/warmup?task_id=...&task_token=...`
- deep link Power App con **sia task_id sia task_token**
- endpoint backend di update che accetta sia `task_id` sia `task_token`

### Perché serve
Se il servizio web è appena stato riattivato, l'utente può aprire la mail prima che il backend sia completamente pronto. La pagina relay evita il click “a vuoto” e mostra uno stato di caricamento prima di aprire la Power App.

### Adeguamento consigliato in Power Apps
Nel `OnStart` / `OnVisible` della schermata principale:
- continua a leggere `Param("task_id")`
- aggiungi anche `Param("task_token")`
- se `task_id` non è subito disponibile ma `task_token` sì, usa l'endpoint `GET /tasks/api/task/by-token/<token>`

## 2) Allegati via OneDrive / SharePoint

### Backend introdotto
- nuova tabella `task_attachments`
- allegati di tipo `task` (apertura task)
- allegati di tipo `response` (risposta/aggiornamento)
- serializzazione allegati negli endpoint task per Power App

### Formato supportato
Nel web form e nella risposta pubblica:
- una riga per allegato
- formato consigliato: `Etichetta | https://...`

Esempio:
```
Distinta materiali | https://tenant.sharepoint.com/...
Foto cantiere | https://onedrive.live.com/...
```

### Endpoint update Power App / Power Automate
`POST /tasks/api/task-update`

Campi supportati oltre ai già esistenti:
- `attachments` (lista JSON di oggetti `{label,url}`)
- `attachment_url` + `attachment_label`
- `attachment_links` (testo multilinea nel formato sopra)

### Adeguamento consigliato in Power Automate
Nel body HTTP puoi usare, per esempio:
```json
{
  "task_id": "@{triggerBody()['text']}",
  "task_token": "@{triggerBody()['text_1']}",
  "status": "@{triggerBody()['text_2']}",
  "note": "@{triggerBody()['text_3']}",
  "replied_by": "@{triggerBody()['text_4']}",
  "email": "@{triggerBody()['text_4']}",
  "attachment_links": "@{triggerBody()['text_5']}"
}
```

> Mappa effettivamente i campi ai nomi interni del tuo trigger V2, perché Power Automate può rinominarli in `text`, `text_1`, ecc.

## 3) Reminder automatici

### Cosa fa ora il backend
L'endpoint cron:
- `/tasks/api/cron/reminders?secret=...`

invia reminder ai destinatari assegnati per task aperti con scadenza:
- **tra 2 giorni**
- **domani**
- **oggi**

Mantiene anche il riepilogo admin / Telegram già presente per i task urgenti.

### Deduplica
Per ogni coppia `task + recipient` vengono tracciati:
- `reminder_2d_sent_at`, `reminder_2d_for_due_date`
- `reminder_1d_sent_at`, `reminder_1d_for_due_date`
- `reminder_0d_sent_at`, `reminder_0d_for_due_date`

### Render cron
Il `render.yaml` include un job:
- `logimetric-task-reminders`
- schedule: `0 8 * * *`

Il job richiama internamente:
- `http://<hostport>/tasks/api/cron/reminders?secret=...`

## Checklist post-push

### Render
1. Push repo
2. Sync blueprint / apply `render.yaml`
3. Verifica variabili:
   - `BREVO_API_KEY`
   - `MAIL_SENDER`
   - `ADMIN_EMAIL`
   - `TASKS_API_KEY`
   - `CRON_SECRET`
   - `POWERAPP_URL`
   - `POWERAPP_TASK_ID_PARAM=task_id`
   - `POWERAPP_TASK_TOKEN_PARAM=task_token`

### Power Apps / Power Automate
1. Aggiorna il flow `Aggiorna task` per usare i campi trigger corretti
2. Aggiungi `task_token` e `attachment_links` se vuoi sfruttare le nuove capacità
3. In Power Apps, se vuoi la massima robustezza, conserva `varTask.token` oltre a `varTask.id`
