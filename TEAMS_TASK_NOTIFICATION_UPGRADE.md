# Upgrade — Notifica Teams per nuovo task LogiMetric

## Obiettivo

Quando viene creato un nuovo task nel backend LogiMetric, il sistema continua a inviare l'email con il link alla Power App e, in aggiunta, chiama un flow Power Automate dedicato che pubblica un messaggio Teams diretto al destinatario.

## Architettura scelta

- Il task viene creato nel backend Flask.
- `app/tasks/routes.py` esegue `_notify_category(task)`.
- `_notify_category(task)` invia:
  - email tramite Brevo, come già avveniva;
  - payload JSON verso Power Automate tramite `app/teams_service.py`.
- Power Automate riceve il payload e usa Teams > Post message in a chat or channel.
- L'utente apre il task dalla Power App usando il link già generato dal backend.

## File modificati

- `app/config.py`
- `app/tasks/routes.py`
- `.env.example`
- nuovo file: `app/teams_service.py`

## Variabili ambiente da aggiungere su Render

```text
TEAMS_NOTIFICATIONS_ENABLED=1
TEAMS_FLOW_URL=<URL_DEL_TRIGGER_HTTP_POWER_AUTOMATE>
TEAMS_FLOW_API_KEY=<CHIAVE_INTERNA_A_SCELTA>
TEAMS_FLOW_TIMEOUT_SECONDS=15
APP_BASE_URL=https://www.logimetric.eu
```

`TEAMS_FLOW_API_KEY` è una chiave interna scelta da te. Deve coincidere con il controllo che inserisci nel flow Power Automate.

## Flow Power Automate da creare

Nome consigliato:

```text
LogiMetric - Teams - Notifica nuovo task
```

### 1. Trigger

Azione:

```text
When a HTTP request is received
```

Schema JSON:

```json
{
  "type": "object",
  "properties": {
    "event": { "type": "string" },
    "recipient_email": { "type": "string" },
    "task_id": { "type": "integer" },
    "task_ref": { "type": "string" },
    "title": { "type": "string" },
    "description": { "type": "string" },
    "category": { "type": "string" },
    "priority": { "type": "string" },
    "priority_label": { "type": "string" },
    "status": { "type": "string" },
    "status_label": { "type": "string" },
    "start_date": { "type": "string" },
    "start_date_display": { "type": "string" },
    "due_date": { "type": "string" },
    "due_date_display": { "type": "string" },
    "created_at": { "type": "string" },
    "created_by_name": { "type": "string" },
    "created_by_email": { "type": "string" },
    "powerapp_url": { "type": "string" },
    "relay_url": { "type": "string" },
    "open_url": { "type": "string" }
  },
  "required": ["recipient_email", "task_id", "title", "open_url"]
}
```

### 2. Controllo chiave interna

Aggiungi una condizione prima dell'invio Teams.

Espressione da usare nel lato sinistro:

```text
triggerOutputs()?['headers']?['X-LogiMetric-Key']
```

Operatore:

```text
is equal to
```

Lato destro:

```text
<stesso valore di TEAMS_FLOW_API_KEY>
```

Nel ramo `If no`, aggiungi `Response` con status code `401` e body:

```json
{ "ok": false, "error": "unauthorized" }
```

### 3. Messaggio Teams

Azione:

```text
Microsoft Teams > Post message in a chat or channel
```

Configurazione:

```text
Post as: Flow bot
Post in: Chat with Flow bot
Recipient: recipient_email
```

Corpo messaggio:

```html
<p><strong>Nuovo task assegnato</strong></p>
<p>Ti è stato assegnato un nuovo task in LogiMetric.</p>

<p>
<strong>Task:</strong> TASK-@{triggerBody()?['task_id']}<br>
<strong>Titolo:</strong> @{triggerBody()?['title']}<br>
<strong>Categoria:</strong> @{triggerBody()?['category']}<br>
<strong>Priorità:</strong> @{triggerBody()?['priority_label']}<br>
<strong>Scadenza:</strong> @{triggerBody()?['due_date_display']}
</p>

<p>
<a href="@{triggerBody()?['open_url']}">Apri il task in Power App</a>
</p>
```

### 4. Risposta HTTP finale

Azione:

```text
Response
```

Status code:

```text
200
```

Body:

```json
{
  "ok": true,
  "message": "Teams notification sent"
}
```

## Test rapido

Dopo aver salvato il flow, copia l'HTTP POST URL dentro `TEAMS_FLOW_URL` su Render.

Esegui un test PowerShell dal PC:

```powershell
$body = @{
  recipient_email = "tua.email@sielte.it"
  task_id = 999
  title = "Test notifica Teams LogiMetric"
  category = "Test"
  priority_label = "Media"
  due_date_display = "31/12/2026"
  open_url = "https://www.logimetric.eu/tasks/open/999"
} | ConvertTo-Json

Invoke-RestMethod -Method Post `
  -Uri "<TEAMS_FLOW_URL>" `
  -ContentType "application/json" `
  -Headers @{ "X-LogiMetric-Key" = "<TEAMS_FLOW_API_KEY>" } `
  -Body $body
```

## Nota sicurezza

La chiave `X-API-Key` del backend è visibile negli screenshot condivisi. Va rigenerata appena possibile e aggiornata sia su Render sia nei due flow Power Apps già esistenti.
