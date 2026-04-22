/**
 * email_panel.js
 * Modulo condiviso per la sezione "Invia via email" nei form.
 * Carica la rubrica da /admin/rubrica/json e gestisce l'invio.
 */
'use strict';

const CONTACTS_URL = '/admin/rubrica/json';

// ── Costruisce il pannello email e lo inietta prima di .form-actions ─────────
async function initEmailPanel(cfg) {
  const {
    formId,        // id del <form>
    sendUrl,       // es. /trasferta/invia
    getSubject,    // function() → string  (oggetto precompilato)
    onSuccess,     // function()  chiamata dopo invio/download riuscito
    showFlash,     // function(msg, type)
  } = cfg;

  const form = document.getElementById(formId);
  if (!form) return;

  // Carica rubrica
  let contacts = [];
  try {
    const r = await fetch(CONTACTS_URL);
    if (r.ok) contacts = await r.json();
  } catch(e) {}

  // Costruisce le opzioni del select
  const contactOptions = contacts.map(c =>
    `<option value="${esc(c.email)}" data-name="${esc(c.name)}">${esc(c.name)} &lt;${esc(c.email)}&gt;</option>`
  ).join('');

  // Pannello HTML
  const panel = document.createElement('div');
  panel.className = 'card email-panel';
  panel.id = 'emailPanel';
  panel.innerHTML = `
    <div class="card-header compact" style="cursor:pointer" onclick="toggleEmailPanel()">
      <div>
        <h2 style="display:flex;align-items:center;gap:10px">
          <svg width="18" height="18" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7">
            <rect x="2" y="5" width="16" height="12" rx="2"/>
            <path d="M2 8l8 5 8-5"/>
          </svg>
          Invia via email
        </h2>
        <p>Genera il file e invialo direttamente a un destinatario.</p>
      </div>
      <span id="emailPanelToggleIcon" style="font-size:1.4rem;color:var(--muted)">﹀</span>
    </div>

    <div id="emailPanelBody" style="display:none;margin-top:4px">
      <div class="form-grid cols-2" style="margin-bottom:14px">

        <div class="field field-span-2">
          <label>Destinatario *</label>
          <div style="display:flex;gap:10px">
            <select id="epContactSelect" class="input" style="flex:1" onchange="onContactSelect()">
              <option value="">— Seleziona dalla rubrica —</option>
              ${contactOptions}
              <option value="__custom__">✏ Inserisci manualmente…</option>
            </select>
          </div>
          <div id="epCustomFields" style="display:none;margin-top:10px">
            <div class="form-grid cols-2">
              <div class="field">
                <label>Nome destinatario</label>
                <input id="epCustomName" type="text" class="input" placeholder="Mario Rossi">
              </div>
              <div class="field">
                <label>Email destinatario *</label>
                <input id="epCustomEmail" type="email" class="input" placeholder="mario@azienda.it">
              </div>
            </div>
          </div>
        </div>

        <div class="field field-span-2">
          <label>Oggetto *</label>
          <input id="epSubject" type="text" class="input" placeholder="Oggetto email…">
        </div>

        <div class="field field-span-2">
          <label>Messaggio <span class="label-hint">(opzionale)</span></label>
          <textarea id="epMessage" class="input textarea" rows="3"
                    placeholder="Testo aggiuntivo che verrà incluso nell'email…"></textarea>
        </div>

        <div class="field field-span-2">
          <label class="checkbox-label">
            <input type="checkbox" id="epAlsoDownload">
            Scarica il file anche sul mio PC
          </label>
        </div>
      </div>

      <div style="display:flex;gap:12px;align-items:center" id="epActions">
        <button type="button" class="btn btn-primary btn-lg" id="epSendBtn" onclick="submitEmail()">
          ✉ Genera e invia
        </button>
        <span id="epStatus" style="font-size:.9rem;color:var(--muted)"></span>
      </div>
    </div>
  `;

  // Inserisci prima di .form-actions
  const actions = form.querySelector('.form-actions');
  if (actions) form.insertBefore(panel, actions);
  else form.appendChild(panel);

  // Precompila oggetto quando cambiano nome/data
  const fillSubject = () => {
    const subj = document.getElementById('epSubject');
    if (subj && !subj.dataset.userEdited) {
      subj.value = getSubject();
    }
  };
  document.getElementById('epSubject')?.addEventListener('input', function() {
    this.dataset.userEdited = this.value ? '1' : '';
  });
  // Osserva cambiamenti nei campi rilevanti
  form.querySelectorAll('input[name="full_name"], input[name="start_date"]')
      .forEach(el => el.addEventListener('change', fillSubject));
  // Prima compilazione
  setTimeout(fillSubject, 300);

  // Funzione invio
  window._epSendUrl    = sendUrl;
  window._epGetFormFn  = () => form;
  window._epOnSuccess  = onSuccess;
  window._epShowFlash  = showFlash;
}

// ── Toggle pannello ──────────────────────────────────────────────────────────
window.toggleEmailPanel = function() {
  const body = document.getElementById('emailPanelBody');
  const icon = document.getElementById('emailPanelToggleIcon');
  const open = body.style.display === 'none';
  body.style.display = open ? 'block' : 'none';
  icon.textContent   = open ? '︿' : '﹀';
};

// ── Seleziona dalla rubrica ───────────────────────────────────────────────────
window.onContactSelect = function() {
  const sel = document.getElementById('epContactSelect');
  const custom = document.getElementById('epCustomFields');
  if (sel.value === '__custom__') {
    custom.style.display = 'block';
  } else {
    custom.style.display = 'none';
    if (sel.value) {
      const opt = sel.options[sel.selectedIndex];
      // Precompila oggetto se non editato
      const subj = document.getElementById('epSubject');
      if (subj && !subj.dataset.userEdited) subj.value = window._epGetSubject?.() || '';
    }
  }
};

// ── Invio ────────────────────────────────────────────────────────────────────
window.submitEmail = async function() {
  const sel         = document.getElementById('epContactSelect');
  const customEmail = document.getElementById('epCustomEmail');
  const customName  = document.getElementById('epCustomName');
  const subject     = document.getElementById('epSubject');
  const message     = document.getElementById('epMessage');
  const alsoDown    = document.getElementById('epAlsoDownload');
  const btn         = document.getElementById('epSendBtn');
  const status      = document.getElementById('epStatus');

  let toEmail = '', toName = '';
  if (sel.value === '__custom__') {
    toEmail = (customEmail?.value || '').trim().toLowerCase();
    toName  = (customName?.value  || '').trim();
  } else {
    toEmail = sel.value;
    const opt = sel.options[sel.selectedIndex];
    toName  = opt?.dataset?.name || '';
  }

  if (!toEmail || !toEmail.includes('@')) {
    window.scrollTo({ top: 0, behavior: 'smooth' });
    window._epShowFlash('Seleziona o inserisci un destinatario valido.', 'error');
    return;
  }
  if (!subject?.value.trim()) {
    window._epShowFlash('L\'oggetto email è obbligatorio.', 'error');
    return;
  }

  btn.disabled     = true;
  btn.textContent  = '⏳ Invio in corso…';
  status.textContent = '';

  const form = window._epGetFormFn();
  const fd   = new FormData(form);
  fd.set('to_email',       toEmail);
  fd.set('to_name',        toName);
  fd.set('email_subject',  subject.value.trim());
  fd.set('email_message',  message?.value.trim() || '');
  fd.set('also_download',  alsoDown?.checked ? '1' : '0');

  try {
    const resp = await fetch(window._epSendUrl, {
      method: 'POST',
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
      body: fd,
    });

    // Se la risposta è un file (also_download) → scarica
    const ct = resp.headers.get('Content-Type') || '';
    if (ct.includes('spreadsheetml') || ct.includes('octet-stream')) {
      const blob     = await resp.blob();
      const cd       = resp.headers.get('Content-Disposition') || '';
      const match    = cd.match(/filename="?([^"]+)"?/);
      const filename = match ? match[1] : 'file.xlsx';
      const url = URL.createObjectURL(blob);
      const a   = document.createElement('a');
      a.href = url; a.download = filename;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
      window._epShowFlash(`Email inviata a ${toEmail} e file scaricato ✓`, 'success');
    } else {
      const data = await resp.json();
      if (!resp.ok || !data.ok) {
        (data.errors || ['Errore nell\'invio.']).forEach(e => window._epShowFlash(e, 'error'));
        return;
      }
      window._epShowFlash(data.message || `Email inviata a ${toEmail} ✓`, 'success');
    }

    // Reset
    window._epOnSuccess?.();
    sel.value = '';
    if (customEmail)    customEmail.value = '';
    if (customName)     customName.value  = '';
    if (subject)        { subject.value = ''; delete subject.dataset.userEdited; }
    if (message)        message.value  = '';
    if (alsoDown)       alsoDown.checked = false;
    document.getElementById('epCustomFields').style.display = 'none';

  } catch(err) {
    window._epShowFlash('Errore di rete: ' + err.message, 'error');
  } finally {
    btn.disabled    = false;
    btn.textContent = '✉ Genera e invia';
  }
};

function esc(v) {
  return v ? String(v).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;') : '';
}
