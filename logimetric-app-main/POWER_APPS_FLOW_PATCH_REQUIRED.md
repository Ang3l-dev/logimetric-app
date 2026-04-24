# Patch esterna al repo — Power Apps / Power Automate

Questa parte non vive nel repo Flask, ma va allineata al backend appena aggiornato.

## Flow `LogiMetric - Aggiorna task`

Nel trigger Power Apps V2 usa campi testuali espliciti per:
- task_id
- task_token
- status
- note
- replied_by
- attachment_links

### Body HTTP consigliato
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

> Sostituisci `text`, `text_1`, ecc. con i nomi interni reali del tuo trigger, se diversi.

## Power Apps

### Apertura task
Mantieni in memoria entrambi:
- `varTask.id`
- `varTask.token`

### Invio aggiornamento
Passa al flow:
- `varTask.id`
- `varTask.token`
- stato scelto
- nota
- utente corrente
- `attachment_links` (testo multilinea)

### Formato allegati suggerito
Una riga per allegato:
```text
Etichetta | https://tenant.sharepoint.com/...
Foto cantiere | https://onedrive.live.com/...
```

## UX suggerita
Quando arrivi da mail tramite il bottone LogiMetric, ora il backend apre una pagina relay che attende il warm-up del servizio prima di reindirizzare alla Power App. Questo riduce gli errori del primo click a freddo.
