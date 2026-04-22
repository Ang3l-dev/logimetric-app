'use strict';

const cfg = document.getElementById('weeklyData');
if (!cfg) throw new Error('weeklyData not found');

const CAN_WRITE  = cfg.dataset.canWrite === 'true';
const PRESET_URL = cfg.dataset.presetUrl;
const SAVE_URL   = cfg.dataset.saveUrl;
const DELETE_URL = cfg.dataset.deleteUrl;

// ── Auto data fine ─────────────────────────────────────────────────────────
function autoEndDate() {
  const start = document.getElementById('start_date')?.value;
  if (!start) return;
  const d = new Date(start);
  d.setDate(d.getDate() + 4);
  const end = document.getElementById('end_date');
  if (end) end.value = d.toISOString().split('T')[0];
}

// ── Flash ─────────────────────────────────────────────────────────────────
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

// ── Reset form ─────────────────────────────────────────────────────────────
function resetAll() {
  const form = document.getElementById('weeklyForm');
  if (form) form.reset();
  showFlash('File scaricato — campi azzerati.', 'success');
}

// ── Generazione via fetch ──────────────────────────────────────────────────
async function submitWeekly(e) {
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
      (data.errors || ['Errore durante la generazione.']).forEach(e => showFlash(e, 'error'));
      return;
    }

    const blob = await resp.blob();
    const cd   = resp.headers.get('Content-Disposition') || '';
    const match = cd.match(/filename="?([^"]+)"?/);
    const filename = match ? match[1] : 'ProgrammaSettimanale.xlsx';
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);

    resetAll();

  } catch(err) {
    showFlash('Errore di rete: ' + err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = '⬇ Genera ed esporta Excel';
  }
}

// ── Preset ─────────────────────────────────────────────────────────────────
function collectPayload() {
  const get = id => document.getElementById(id)?.value || '';
  return {
    full_name:      get('full_name'),
    start_date:     get('start_date'),
    end_date:       get('end_date'),
    day_location_1: document.querySelector('[name="day_location_1"]')?.value || '',
    day_location_2: document.querySelector('[name="day_location_2"]')?.value || '',
    day_location_3: document.querySelector('[name="day_location_3"]')?.value || '',
    day_location_4: document.querySelector('[name="day_location_4"]')?.value || '',
    day_location_5: document.querySelector('[name="day_location_5"]')?.value || '',
  };
}

function applyPayload(p) {
  const set = (name, val) => {
    const el = document.getElementById(name) || document.querySelector(`[name="${name}"]`);
    if (el) el.value = val || '';
  };
  set('full_name', p.full_name);
  set('start_date', p.start_date);
  set('end_date', p.end_date);
  for (let i = 1; i <= 5; i++) set(`day_location_${i}`, p[`day_location_${i}`]);
}

async function loadPreset() {
  const sel = document.getElementById('presetSelect');
  const id = sel.value;
  if (!id) return;
  const r = await fetch(PRESET_URL.replace('/0', `/${id}`));
  if (!r.ok) { showFlash('Errore caricamento preset.', 'error'); return; }
  applyPayload((await r.json()).payload);
}

async function savePreset() {
  const name = document.getElementById('presetName').value.trim();
  if (!name) { showFlash('Inserisci un nome.', 'error'); return; }
  const sel = document.getElementById('presetSelect');
  const existing = [...sel.options].find(o => o.text === name);
  const body = { name, payload: collectPayload(), preset_type: 'weekly' };
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
  if (!confirm(`Eliminare "${sel.options[sel.selectedIndex].text}"?`)) return;
  await fetch(DELETE_URL.replace('/0', `/${id}`), { method: 'DELETE' });
  sel.options[sel.selectedIndex].remove();
  sel.value = '';
}

// ── Init ───────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('start_date')?.addEventListener('change', autoEndDate);
  document.getElementById('loadPresetBtn')?.addEventListener('click', loadPreset);
  if (CAN_WRITE) {
    document.getElementById('savePresetBtn')?.addEventListener('click', savePreset);
    document.getElementById('deletePresetBtn')?.addEventListener('click', deletePreset);
    document.getElementById('weeklyForm')?.addEventListener('submit', submitWeekly);
  }
});

// ── Email panel init ──────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  if (!CAN_WRITE) return;
  const SEND_URL = cfg.dataset.sendUrl || '/settimanale/invia';

  initEmailPanel({
    formId:   'weeklyForm',
    sendUrl:  SEND_URL,
    getSubject: () => {
      const name = document.getElementById('full_name')?.value?.trim() || '';
      const date = document.getElementById('start_date')?.value || '';
      const fmt  = date ? new Date(date + 'T00:00:00').toLocaleDateString('it-IT') : '';
      return `Programma Settimanale${name ? ' - ' + name : ''}${fmt ? ' - ' + fmt : ''}`;
    },
    onSuccess:  resetAll,
    showFlash:  showFlash,
  });

  window._epGetSubject = () => {
    const name = document.getElementById('full_name')?.value?.trim() || '';
    const date = document.getElementById('start_date')?.value || '';
    const fmt  = date ? new Date(date + 'T00:00:00').toLocaleDateString('it-IT') : '';
    return `Programma Settimanale${name ? ' - ' + name : ''}${fmt ? ' - ' + fmt : ''}`;
  };
});
