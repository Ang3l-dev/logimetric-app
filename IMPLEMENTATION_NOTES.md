# LogiMetric — note implementative task manager

## Contenuto incluso
1. Fix pulsanti **Modifica** in **Categorie Task** tramite `data-* attributes` e parsing JSON robusto.
2. Eliminazione categoria disponibile per admin anche con task associati:
   - i task **aperti** vengono spostati su `Categoria rimossa`
   - le risposte destinatari vengono eliminate
   - lo stato viene riallineato a `da_fare`
   - i task `completato` / `annullato` restano storicizzati
3. Rimozione del box residuale di test **Integrazione Power Automate** dalla pagina categorie.
4. Nuova dashboard amministrativa **/tasks/kpi** con:
   - card KPI
   - grafici sintetici
   - tabella “chi ha risposto”
   - task aperti scaduti
   - storico eventi recente
5. Tracciabilità estesa:
   - `created_by_*` sul task
   - `completed_*` sul task
   - `actor_*` sugli eventi
   - `created_at` su `task_recipient_responses`
6. Invio mail al creatore del task quando arrivano aggiornamenti/note da Power Automate / form pubblico.
7. Dettaglio task con storico aggiornamenti completo.

## Adeguamento Power Automate
Nel body HTTP verso LogiMetric inviare SEMPRE:
```json
{
  "task_id": 123,
  "status": "in_corso",
  "note": "Aggiornamento operativo o nota aggiuntiva",
  "replied_by": "Mario Rossi",
  "email": "m.rossi@azienda.it"
}
```

## Endpoint supportati
- `POST /tasks/api/task-update`
- `POST /tasks/api/<external_token>/update`

## Header richiesti
- `Content-Type: application/json`
- `X-API-Key: <TASKS_API_KEY>` se configurata

## Teams / user experience
In questo pacchetto la parte “chat” è implementata come thread di aggiornamenti tracciati lato task + mail al richiedente.
Non è stata aggiunta risposta del richiedente dalla UI web, come richiesto.

## Nota tecnica schema DB
Il bootstrap applicativo prova ad aggiungere automaticamente le nuove colonne mancanti ai database esistenti all’avvio.


## Telegram notifiche task

Variabili ambiente da impostare su Render:
- `TELEGRAM_ENABLED=1`
- `TELEGRAM_BOT_TOKEN=<token BotFather>`
- `TELEGRAM_CHAT_ID=<chat id utente o gruppo>`
- `APP_BASE_URL=https://logimetric.eu`

Copertura implementata:
- creazione task
- modifica task da UI web
- cambio stato rapido Kanban
- aggiornamenti da form pubblico
- aggiornamenti da Power Automate / Power App
- alert scadenze tramite endpoint cron `/tasks/api/cron/reminders?secret=...`
- endpoint admin di test: `POST /tasks/api/telegram/test`
