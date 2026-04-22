'use strict';

const cfg = document.getElementById('travelFormData');
if (!cfg) throw new Error('travelFormData element not found');

const MAX_TRANSFERS = parseInt(cfg.dataset.maxTransfers) || 8;
const MAX_STAYS     = parseInt(cfg.dataset.maxStays) || 3;
const CAN_WRITE     = cfg.dataset.canWrite === 'true';
const PRESET_URL    = cfg.dataset.presetUrl;
const SAVE_URL      = cfg.dataset.saveUrl;
const DELETE_URL    = cfg.dataset.deleteUrl;

let initialData = {};
try { initialData = JSON.parse(cfg.dataset.initial || '{}'); } catch(e) {}

let transferCount = 0;
let stayCount = 0;

// ── Righe dinamiche ────────────────────────────────────────────────────────
function addTransfer(data = {}) {
  if (transferCount >= MAX_TRANSFERS) return;
  const idx = transferCount++;
  const container = document.getElementById('transfersContainer');
  const div = document.createElement('div');
  div.className = 'dynamic-row';
  div.id = `transfer-${idx}`;
  div.innerHTML = `
    <div class="dynamic-row-header">
      <span class="dynamic-row-title">Trasferimento ${idx + 1}</span>
      <button type="button" class="btn btn-danger btn-sm" onclick="removeRow('transfer-${idx}')">Rimuovi</button>
    </div>
    <div class="form-grid cols-3">
      <div class="field"><label>Da *</label>
        <input class="input" type="text" name="transfers-${idx}-from_location" value="${esc(data.from_location)}"></div>
      <div class="field"><label>A *</label>
        <input class="input" type="text" name="transfers-${idx}-to_location" value="${esc(data.to_location)}"></div>
      <div class="field"><label>Data *</label>
        <input class="input" type="date" name="transfers-${idx}-travel_date" value="${esc(data.travel_date)}"></div>
      <div class="field"><label>Orario partenza</label>
        <input class="input" type="time" name="transfers-${idx}-departure_time" value="${esc(data.departure_time)}"></div>
      <div class="field"><label>Mezzo di trasporto</label>
        <input class="input" type="text" name="transfers-${idx}-transport" value="${esc(data.transport)}"></div>
      <div class="field"><label>Note</label>
        <input class="input" type="text" name="transfers-${idx}-notes" value="${esc(data.notes)}"></div>
    </div>`;
  container.appendChild(div);
}

function addStay(data = {}) {
  if (stayCount >= MAX_STAYS) return;
  const idx = stayCount++;
  const container = document.getElementById('staysContainer');
  const div = document.createElement('div');
  div.className = 'dynamic-row';
  div.id = `stay-${idx}`;
  div.innerHTML = `
    <div class="dynamic-row-header">
      <span class="dynamic-row-title">Pernottamento ${idx + 1}</span>
      <button type="button" class="btn btn-danger btn-sm" onclick="removeRow('stay-${idx}')">Rimuovi</button>
    </div>
    <div class="form-grid cols-3">
      <div class="field"><label>Città / Hotel</label>
        <input class="input" type="text" name="stays-${idx}-location" value="${esc(data.location)}"></div>
      <div class="field"><label>Check-in</label>
        <input class="input" type="date" name="stays-${idx}-check_in" value="${esc(data.check_in)}"></div>
      <div class="field"><label>Check-out</label>
        <input class="input" type="date" name="stays-${idx}-check_out" value="${esc(data.check_out)}"></div>
    </div>`;
  container.appendChild(div);
}

function removeRow(id) {
  document.getElementById(id)?.remove();
}

// ── Reset form ─────────────────────────────────────────────────────────────
function resetAll() {
  const form = document.getElementById('travelForm');
  if (!form) return;
  form.reset();
  document.getElementById('transfersContainer').innerHTML = '';
  transferCount = 0;
  document.getElementById('staysContainer').innerHTML = '';
  stayCount = 0;
  addTransfer();
  addStay();
  // radio default
  const mista = form.querySelector('[name="travel_type"][value="mista"]');
  if (mista) mista.checked = true;
  showFlash('File scaricato — campi azzerati.', 'success');
}

// ── Generazione via fetch ──────────────────────────────────────────────────
async function submitTravel(e) {
  e.preventDefault();
  const form = e.target;
  const btn  = form.querySelector('[type="submit"]');
  btn.disabled = true;
  btn.textContent = '⏳ Generazione…';

  try {
    const resp = await fetch(form.action, {
      method: 'POST',
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
      body: new FormData(form),
    });

    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      const errors = data.errors || ['Errore durante la generazione.'];
      errors.forEach(e => showFlash(e, 'error'));
      return;
    }

    // Scarica il file
    const blob = await resp.blob();
    const cd   = resp.headers.get('Content-Disposition') || '';
    const match = cd.match(/filename="?([^"]+)"?/);
    const filename = match ? match[1] : 'Trasferta.xlsx';
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);

    // Svuota i campi
    resetAll();

  } catch(err) {
    showFlash('Errore di rete: ' + err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = '⬇ Genera ed esporta Excel';
  }
}

// ── Flash inline ───────────────────────────────────────────────────────────
function showFlash(msg, type = 'info') {
  window.scrollTo({ top: 0, behavior: 'smooth' });
  let stack = document.querySelector('.flash-stack');
  if (!stack) {
    stack = document.createElement('div');
    stack.className = 'flash-stack';
    document.querySelector('.main-content').prepend(stack);
  }
  const div = document.createElement('div');
  div.className = `flash flash-${type}`;
  div.innerHTML = `<span>${msg}</span>
    <button class="flash-close" onclick="this.parentElement.remove()">✕</button>`;
  stack.prepend(div);
  setTimeout(() => div.remove(), 6000);
}

// ── Preset ─────────────────────────────────────────────────────────────────
function collectPayload() {
  const fd = new FormData(document.getElementById('travelForm'));
  const out = {};
  for (const [k, v] of fd.entries()) out[k] = v;
  const transfers = [];
  for (let i = 0; i < transferCount; i++) {
    transfers.push({
      from_location:  fd.get(`transfers-${i}-from_location`) || '',
      to_location:    fd.get(`transfers-${i}-to_location`) || '',
      travel_date:    fd.get(`transfers-${i}-travel_date`) || '',
      departure_time: fd.get(`transfers-${i}-departure_time`) || '',
      transport:      fd.get(`transfers-${i}-transport`) || '',
      notes:          fd.get(`transfers-${i}-notes`) || '',
    });
  }
  out.transfers = transfers;
  const stays = [];
  for (let i = 0; i < stayCount; i++) {
    stays.push({
      location:  fd.get(`stays-${i}-location`) || '',
      check_in:  fd.get(`stays-${i}-check_in`) || '',
      check_out: fd.get(`stays-${i}-check_out`) || '',
    });
  }
  out.stays = stays;
  return out;
}

function applyPayload(payload) {
  const set = (name, val) => {
    const el = document.querySelector(`[name="${name}"]`);
    if (!el) return;
    if (el.type === 'radio') {
      document.querySelectorAll(`[name="${name}"]`).forEach(r => r.checked = r.value === val);
    } else { el.value = val || ''; }
  };
  ['travel_type','start_date','end_date','full_name','employee_id','business_line',
   'cost_center','hiring_location','travel_reason','pickup_location','pickup_date',
   'pickup_time','dropoff_location','dropoff_date','dropoff_time','vehicle_category',
   'employee_signature_name','employee_signature_date'].forEach(f => set(f, payload[f]));

  document.getElementById('transfersContainer').innerHTML = '';
  transferCount = 0;
  const transfers = payload.transfers || [];
  if (!transfers.length) addTransfer(); else transfers.forEach(t => addTransfer(t));

  document.getElementById('staysContainer').innerHTML = '';
  stayCount = 0;
  const stays = payload.stays || [];
  if (!stays.length) addStay(); else stays.forEach(s => addStay(s));
}

async function loadPreset() {
  const sel = document.getElementById('presetSelect');
  const id = sel.value;
  if (!id) return;
  const r = await fetch(PRESET_URL.replace('/0', `/${id}`));
  if (!r.ok) { showFlash('Errore nel caricamento del preset.', 'error'); return; }
  const data = await r.json();
  applyPayload(data.payload);
}

async function savePreset() {
  const name = document.getElementById('presetName').value.trim();
  if (!name) { showFlash('Inserisci un nome per il preset.', 'error'); return; }
  const sel = document.getElementById('presetSelect');
  const existing = [...sel.options].find(o => o.text === name);
  const body = { name, payload: collectPayload(), preset_type: 'travel' };
  if (existing) body.id = parseInt(existing.value);
  const r = await fetch(SAVE_URL, {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
  });
  const data = await r.json();
  if (!existing) sel.add(new Option(name, data.id));
  sel.value = data.id;
  document.getElementById('presetName').value = '';
  showFlash('Preset salvato.', 'success');
}

async function deletePreset() {
  const sel = document.getElementById('presetSelect');
  const id = sel.value;
  if (!id) return;
  if (!confirm(`Eliminare il preset "${sel.options[sel.selectedIndex].text}"?`)) return;
  await fetch(DELETE_URL.replace('/0', `/${id}`), { method: 'DELETE' });
  sel.options[sel.selectedIndex].remove();
  sel.value = '';
}

function esc(v) {
  return v ? String(v).replace(/"/g, '&quot;').replace(/</g, '&lt;') : '';
}

// ── Init ───────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('addTransferBtn')?.addEventListener('click', () => addTransfer());
  document.getElementById('addStayBtn')?.addEventListener('click', () => addStay());
  document.getElementById('loadPresetBtn')?.addEventListener('click', loadPreset);
  if (CAN_WRITE) {
    document.getElementById('savePresetBtn')?.addEventListener('click', savePreset);
    document.getElementById('deletePresetBtn')?.addEventListener('click', deletePreset);
    document.getElementById('travelForm')?.addEventListener('submit', submitTravel);
  }

  const transfers = initialData.transfers || [];
  if (!transfers.length) addTransfer(); else transfers.forEach(t => addTransfer(t));
  const stays = initialData.stays || [];
  if (!stays.length) addStay(); else stays.forEach(s => addStay(s));
});

// ── Email panel init ──────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  if (!CAN_WRITE) return;
  const SEND_URL = cfg.dataset.sendUrl || '/trasferta/invia';

  initEmailPanel({
    formId:   'travelForm',
    sendUrl:  SEND_URL,
    getSubject: () => {
      const name  = document.querySelector('[name="full_name"]')?.value?.trim() || '';
      const date  = document.querySelector('[name="start_date"]')?.value || '';
      const fmt   = date ? new Date(date + 'T00:00:00').toLocaleDateString('it-IT') : '';
      return `Modulo Trasferta${name ? ' - ' + name : ''}${fmt ? ' - ' + fmt : ''}`;
    },
    onSuccess:  resetAll,
    showFlash:  showFlash,
  });

  window._epGetSubject = () => {
    const name = document.querySelector('[name="full_name"]')?.value?.trim() || '';
    const date = document.querySelector('[name="start_date"]')?.value || '';
    const fmt  = date ? new Date(date + 'T00:00:00').toLocaleDateString('it-IT') : '';
    return `Modulo Trasferta${name ? ' - ' + name : ''}${fmt ? ' - ' + fmt : ''}`;
  };
});
