# Power Apps — correzioni da applicare fuori dal repo Flask

Questi due punti non sono contenuti nel codice Flask/GitHub, quindi non possono essere corretti dentro il repo web. Li lascio qui in forma operativa per allinearli al backend corretto.

## 1) Ricerca task da qualsiasi parola del titolo

Se oggi la ricerca usa `StartsWith(...)`, troverà solo l'inizio del titolo.
Sostituisci la formula `Items` della gallery task con una logica contenente `in` e `Lower`.

### Formula consigliata
```powerfx
With(
    { q: Lower(Trim(txtCercaTask.Text)) },
    SortByColumns(
        Filter(
            colMieiTask,
            IsBlank(q)
                || q in Lower(Coalesce(title, ""))
                || q in Lower(Coalesce(description, ""))
                || q in Lower(Coalesce(category, ""))
        ),
        "due_date",
        SortOrder.Ascending
    )
)
```

Se la sorgente non è `colMieiTask` ma un'altra collection/tabella, sostituisci solo il nome della sorgente.

## 2) Riga gallery cliccabile su tutta la larghezza

Il sintomo che descrivi indica che oggi la navigazione è agganciata a un solo controllo invisibile laterale.
La correzione più stabile è creare un controllo-hitzone che copra tutta la riga.

### Metodo consigliato
1. Dentro il template della gallery inserisci un pulsante o rettangolo trasparente.
2. Imposta:

```powerfx
X = 0
Y = 0
Width = Parent.TemplateWidth
Height = Parent.TemplateHeight
Fill = RGBA(0,0,0,0)
BorderThickness = 0
Text = ""
OnSelect = Set(varTask, ThisItem); Navigate(ScrAggiorna, ScreenTransition.Fade)
```

3. Per tutte le label/icona della riga che oggi non aprono il dettaglio, imposta:

```powerfx
OnSelect = Select(btnRowOpen)
```

Dove `btnRowOpen` è il nome del controllo trasparente che copre tutta la riga.

## 3) Nota importante sul backend

Il repo corretto ora normalizza le email destinatario in minuscolo e senza spazi prima di aggregare gli stati. Quindi la Power App deve continuare a inviare l'email dell'utente nel payload (`email`) insieme a `task_id`, `status`, `note`, `replied_by`.
