const state = { meta: null, leads: [], reminders: [], imports: [], selectedLead: null, currentImport: null, settings: null };

const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];
const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[char]);
const fmtDate = value => value ? new Intl.DateTimeFormat('it-IT', { dateStyle: 'medium', timeStyle: value.includes('T') ? 'short' : undefined }).format(new Date(value)) : '—';
const toLocalInput = value => value ? new Date(new Date(value).getTime() - new Date(value).getTimezoneOffset() * 60000).toISOString().slice(0, 16) : '';
const fromLocalInput = value => value ? new Date(value).toISOString() : null;

async function api(url, options = {}) {
  const response = await fetch(url, { ...options, headers: { ...(options.body ? { 'content-type': 'application/json' } : {}), ...(options.headers || {}) } });
  if (response.status === 401) { showLogin(); throw new Error('Accesso richiesto'); }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) { const error = new Error(data.error || `Errore ${response.status}`); error.data = data; throw error; }
  return data;
}

function toast(message, type = '') {
  const element = $('#toast'); element.textContent = message; element.className = `toast ${type}`;
  clearTimeout(toast.timer); toast.timer = setTimeout(() => element.classList.add('hidden'), 4000);
}

function showLogin() { $('#login').classList.remove('hidden'); setTimeout(() => $('#login-pin').focus(), 20); }
function hideLogin() { $('#login').classList.add('hidden'); }

function openModal(html, wide = false) {
  $('#modal-content').innerHTML = html; $('#modal').classList.remove('hidden');
  $('.modal-card').style.width = wide ? 'min(1080px, 100%)' : '';
}
function closeModal() { $('#modal').classList.add('hidden'); $('#modal-content').innerHTML = ''; }

function showView(name) {
  $$('.view').forEach(view => view.classList.toggle('active', view.id === `view-${name}`));
  $$('.nav-item').forEach(button => button.classList.toggle('active', button.dataset.view === name));
  $('.sidebar').classList.remove('open');
  if (name === 'leads') loadLeads();
  if (name === 'reminders') loadReminders();
  if (name === 'import') loadImports();
  if (name === 'settings') loadSettings();
}

function statusBadge(status) {
  const tone = /non risponde|scadut/i.test(status) ? 'danger' : /richiamare|appuntamento/i.test(status) ? 'warn' : '';
  return `<span class="badge ${tone}">${escapeHtml(status || 'Da contattare')}</span>`;
}

async function loadDashboard() {
  const [metrics, reminders] = await Promise.all([api('/api/dashboard'), api('/api/reminders')]);
  state.reminders = reminders;
  const cards = [
    ['Scaduti', metrics.overdue, 'alert'], ['Da fare oggi', metrics.today, 'warn'], ['Prossimi 7 giorni', metrics.next_7_days, ''],
    ['Senza prossima azione', metrics.missing_next_action, 'warn'], ['Priorità alta', metrics.high_priority, '']
  ];
  $('#dashboard-cards').innerHTML = cards.map(([label, value, tone]) => `<article class="metric ${tone}"><span>${label}</span><strong>${value}</strong></article>`).join('');
  const active = reminders.filter(item => item.status === 'Aperto').slice(0, 6);
  $('#today-reminders').innerHTML = active.length ? active.map(reminderRow).join('') : '<p class="empty">Nessuna attività aperta.</p>';
  $('#quality-list').innerHTML = [
    ['Schede senza prossima azione', metrics.missing_next_action], ['Contatti senza nota', metrics.missing_notes], ['Totale schede CRM', metrics.total_leads]
  ].map(([label, value]) => `<div class="quality-row"><span>${label}</span><strong>${value}</strong></div>`).join('');
}

function reminderRow(item) {
  const date = new Date(item.due_at); const overdue = item.status === 'Aperto' && date < new Date();
  return `<div class="list-row"><div class="date-box ${overdue ? 'overdue' : ''}"><strong>${date.getDate()}</strong><span>${date.toLocaleDateString('it-IT', { month: 'short' })}</span></div><div class="list-main"><strong>${escapeHtml(item.title)}</strong><span>${escapeHtml(item.lead_name || item.full_address || 'Attività generale')} · ${fmtDate(item.due_at)}</span></div>${item.status === 'Aperto' ? `<button class="check-complete" data-complete-reminder="${item.id}" title="Completa"></button>` : statusBadge('Completato')}</div>`;
}

async function loadLeads() {
  const query = $('#global-search').value.trim(); const status = $('#lead-status-filter').value;
  state.leads = await api(`/api/leads?q=${encodeURIComponent(query)}&status=${encodeURIComponent(status)}`);
  $('#lead-count').textContent = `${state.leads.length} schede trovate`;
  $('#leads-body').innerHTML = state.leads.map(lead => `<tr data-lead="${lead.id}"><td class="name-cell"><strong>${escapeHtml([lead.first_name, lead.last_name].filter(Boolean).join(' ') || lead.company || lead.property_type || 'Scheda senza nome')}</strong><span>${escapeHtml(lead.phone || lead.email || lead.source || '')}</span></td><td>${escapeHtml(lead.full_address || [lead.street, lead.civic, lead.comune].filter(Boolean).join(', ') || '—')}</td><td>${statusBadge(lead.contact_status)}</td><td>${escapeHtml(lead.next_action || 'Da definire')}<br><small>${fmtDate(lead.callback_at)}</small></td><td><span class="badge ${lead.priority === 'Urgente' ? 'danger' : lead.priority === 'Alta' ? 'warn' : 'neutral'}">${escapeHtml(lead.priority)}</span></td></tr>`).join('');
  $('#lead-cards').innerHTML = state.leads.map(lead => `<div class="lead-card" data-lead="${lead.id}"><strong>${escapeHtml([lead.first_name, lead.last_name].filter(Boolean).join(' ') || lead.property_type || 'Scheda senza nome')}</strong><span>${escapeHtml(lead.full_address || 'Indirizzo da completare')}</span><span>${statusBadge(lead.contact_status)} · ${fmtDate(lead.callback_at)}</span></div>`).join('') || '<p class="empty">Nessuna scheda.</p>';
}

function leadForm(lead = {}) {
  const field = (name, label, type = 'text', full = false) => `<label class="${full ? 'full' : ''}">${label}<input name="${name}" type="${type}" value="${escapeHtml(type === 'datetime-local' ? toLocalInput(lead[name]) : lead[name] ?? '')}"></label>`;
  return `<form id="lead-form"><p class="eyebrow">${lead.id ? 'Modifica' : 'Nuovo contatto'}</p><h1>${lead.id ? escapeHtml([lead.first_name, lead.last_name].filter(Boolean).join(' ') || lead.full_address || 'Scheda CRM') : 'Nuova scheda CRM'}</h1><p class="muted">Inserisci solo dati verificati. Per cambiare l’esito di un contatto usa la scheda “Note”.</p><div class="form-grid">${field('first_name','Nome')}${field('last_name','Cognome')}${field('phone','Telefono','tel')}${field('email','Email','email')}${field('comune','Comune')}${field('cap','CAP')}${field('street','Via')}${field('civic','Civico')}${field('full_address','Indirizzo completo','text',true)}${field('property_type','Tipologia immobile')}${field('sqm','Metri quadri','number')}${field('rooms','Locali')}${field('current_price','Prezzo','number')}${field('source','Fonte')}${field('source_url','Link fonte','url',true)}${lead.id ? '' : `<label>Stato<select name="contact_status">${state.meta.outcomes.map(value => `<option ${lead.contact_status === value ? 'selected' : ''}>${value}</option>`).join('')}</select></label>`}<label>Priorità<select name="priority">${state.meta.priorities.map(value => `<option ${lead.priority === value ? 'selected' : ''}>${value}</option>`).join('')}</select></label>${field('next_action','Prossima azione','text',true)}${field('callback_at','Data richiamo','datetime-local')}<label class="full">Nota iniziale<textarea name="original_note" rows="4">${escapeHtml(lead.original_note || '')}</textarea></label></div><div class="button-row"><button class="button primary" type="submit">${lead.id ? 'Salva modifiche' : 'Crea scheda'}</button><button class="button secondary" type="button" data-close> annulla </button></div></form>`;
}

function openNewLead() { openModal(leadForm({ comune: 'Susa', priority: 'Media', contact_status: 'Da contattare' })); bindLeadForm(); }

function formData(form) {
  const result = Object.fromEntries(new FormData(form));
  if ('callback_at' in result) result.callback_at = fromLocalInput(result.callback_at);
  for (const number of ['sqm', 'current_price', 'previous_price', 'confidence']) if (result[number] !== undefined) result[number] = result[number] ? Number(result[number]) : null;
  return result;
}

function bindLeadForm(id = null) {
  $('#lead-form').addEventListener('submit', async event => {
    event.preventDefault(); const button = event.submitter; button.disabled = true;
    try {
      const payload = formData(event.currentTarget);
      await api(id ? `/api/leads/${id}` : '/api/leads', { method: id ? 'PATCH' : 'POST', body: JSON.stringify(payload) });
      toast(id ? 'Scheda aggiornata.' : 'Scheda creata.'); closeModal(); await Promise.all([loadLeads(), loadDashboard()]);
    } catch (error) {
      if (error.data?.duplicates) toast('Possibile duplicato trovato: apri prima la scheda esistente.', 'error');
      else toast(error.message, 'error');
    } finally { button.disabled = false; }
  });
}

async function openLead(id) {
  const lead = await api(`/api/leads/${id}`); state.selectedLead = lead;
  const name = [lead.first_name, lead.last_name].filter(Boolean).join(' ') || lead.full_address || 'Scheda CRM';
  openModal(`<p class="eyebrow">Scheda completa</p><h1>${escapeHtml(name)}</h1><p class="muted">${escapeHtml(lead.full_address || 'Indirizzo da completare')} · ${escapeHtml(lead.phone || 'Telefono da completare')}</p><div class="tabs"><button class="tab active" data-tab="summary">Riepilogo</button><button class="tab" data-tab="notes">Note (${lead.notes.length})</button><button class="tab" data-tab="prequal">Prequalifica</button><button class="tab" data-tab="edit">Modifica</button></div><div id="tab-summary" class="tab-panel active">${leadSummary(lead)}</div><div id="tab-notes" class="tab-panel">${notesPanel(lead)}</div><div id="tab-prequal" class="tab-panel">${prequalPanel(lead)}</div><div id="tab-edit" class="tab-panel">${leadForm(lead)}</div>`, true);
  bindTabs(); bindNoteForm(lead.id); bindPrequalForm(lead.id); bindLeadForm(lead.id);
}

function leadSummary(lead) {
  const items = [['Stato', statusBadge(lead.contact_status)], ['Priorità', escapeHtml(lead.priority)], ['Prossima azione', escapeHtml(lead.next_action || 'Da definire')], ['Richiamo', fmtDate(lead.callback_at)], ['Tipologia', escapeHtml(lead.property_type || '—')], ['Prezzo', lead.current_price ? new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(lead.current_price) : '—'], ['Fonte', lead.source_url ? `<a href="${escapeHtml(lead.source_url)}" target="_blank" rel="noopener">${escapeHtml(lead.source || 'Apri fonte')} ↗</a>` : escapeHtml(lead.source || '—')], ['Classe', escapeHtml(lead.qualification_class || 'Da calcolare')]];
  return `<div class="quality-list">${items.map(([label, value]) => `<div class="quality-row"><span>${label}</span><strong>${value}</strong></div>`).join('')}</div>${lead.original_note ? `<h2>Nota iniziale</h2><div class="original-text">${escapeHtml(lead.original_note)}</div>` : ''}`;
}

function notesPanel(lead) {
  return `<form id="note-form"><h2>Registra il contatto</h2><div class="form-grid"><label>Tipo contatto<select name="contact_type"><option>Telefonata</option><option>WhatsApp</option><option>Email</option><option>Visita in zona</option><option>Appuntamento</option></select></label><label>Esito<select name="outcome">${state.meta.outcomes.map(value => `<option>${value}</option>`).join('')}</select></label><label class="full">Nota obbligatoria<textarea name="body" rows="4" placeholder="Che cosa ha detto il cliente? Quali obiezioni o informazioni nuove?" required></textarea></label><label class="full">Prossima azione<input name="next_action" placeholder="Es. richiamare dopo confronto con la sorella"></label><label>Data richiamo<input name="callback_at" type="datetime-local"></label></div><div class="button-row"><button class="button primary">Salva nota e attività</button></div></form><h2>Storico cronologico</h2><div class="timeline">${lead.notes.length ? lead.notes.map(note => `<div class="timeline-item"><small>${fmtDate(note.created_at)} · ${escapeHtml(note.contact_type || note.outcome || 'Nota')}</small><p>${escapeHtml(note.body)}</p>${note.next_action ? `<strong>Prossima azione: ${escapeHtml(note.next_action)}</strong>` : ''}</div>`).join('') : '<p class="empty">Nessuna nota. Dopo il prossimo contatto ricordati di inserirla.</p>'}</div>`;
}

function prequalPanel(lead) {
  const last = lead.prequalifications[0];
  return `${last ? `<div class="monday-banner"><div><span class="eyebrow">Ultima classificazione</span><strong>Classe ${last.class}</strong><small>${escapeHtml(last.action)}</small></div></div>` : ''}<form id="prequal-form"><p class="muted">Usa le domande dentro una conversazione naturale e scrivi subito le risposte.</p>${state.meta.questions.map((question, index) => `<div class="prequal-question"><label>${index + 1}. ${escapeHtml(question)}</label><textarea name="q${index + 1}" rows="2">${escapeHtml(last?.answers?.[`q${index + 1}`] || '')}</textarea></div>`).join('')}<div class="button-row"><button class="button primary">Salva e calcola classe</button></div></form>`;
}

function bindTabs() {
  $$('.tab').forEach(button => button.addEventListener('click', () => {
    $$('.tab').forEach(item => item.classList.toggle('active', item === button));
    $$('.tab-panel').forEach(panel => panel.classList.toggle('active', panel.id === `tab-${button.dataset.tab}`));
  }));
}

function bindNoteForm(leadId) {
  $('#note-form').addEventListener('submit', async event => {
    event.preventDefault(); const payload = formData(event.currentTarget);
    try { await api(`/api/leads/${leadId}/notes`, { method: 'POST', body: JSON.stringify(payload) }); toast('Nota salvata. Il richiamo è stato aggiornato.'); await openLead(leadId); await loadDashboard(); }
    catch (error) { toast(error.message, 'error'); }
  });
}

function bindPrequalForm(leadId) {
  $('#prequal-form').addEventListener('submit', async event => {
    event.preventDefault(); const answers = Object.fromEntries(new FormData(event.currentTarget));
    try { const result = await api(`/api/leads/${leadId}/prequalification`, { method: 'POST', body: JSON.stringify({ answers }) }); toast(`Prequalifica salvata: Classe ${result.class}.`); await openLead(leadId); }
    catch (error) { toast(error.message, 'error'); }
  });
}

async function loadReminders() {
  state.reminders = await api('/api/reminders'); const active = state.reminders.filter(item => item.status === 'Aperto');
  const start = new Date(); start.setHours(0, 0, 0, 0); const end = new Date(start); end.setDate(end.getDate() + 1);
  const groups = { overdue: active.filter(item => new Date(item.due_at) < start), today: active.filter(item => new Date(item.due_at) >= start && new Date(item.due_at) < end), upcoming: active.filter(item => new Date(item.due_at) >= end) };
  for (const [key, items] of Object.entries(groups)) $(`#reminders-${key}`).innerHTML = items.length ? items.map(reminderRow).join('') : '<p class="empty">Nessuna attività.</p>';
}

function openReminderForm() {
  openModal(`<p class="eyebrow">Agenda</p><h1>Nuovo promemoria</h1><form id="reminder-form"><div class="form-grid"><label class="full">Attività<input name="title" required placeholder="Es. richiamare proprietario"></label><label>Data e ora<input name="due_at" type="datetime-local" required></label><label>Priorità<select name="priority">${state.meta.priorities.map(value => `<option>${value}</option>`).join('')}</select></label><label class="full">Collega a una scheda<select name="lead_id"><option value="">Nessuna scheda</option>${state.leads.map(lead => `<option value="${lead.id}">${escapeHtml([lead.first_name, lead.last_name].filter(Boolean).join(' ') || lead.full_address)}</option>`).join('')}</select></label></div><div class="button-row"><button class="button primary">Crea promemoria</button></div></form>`);
  $('#reminder-form').addEventListener('submit', async event => { event.preventDefault(); const payload = formData(event.currentTarget); try { await api('/api/reminders', { method: 'POST', body: JSON.stringify(payload) }); toast('Promemoria creato.'); closeModal(); await Promise.all([loadReminders(), loadDashboard()]); } catch (error) { toast(error.message, 'error'); } });
}

async function fileToPayload(file) {
  const bytes = new Uint8Array(await file.arrayBuffer()); let binary = '';
  const size = 0x8000; for (let i = 0; i < bytes.length; i += size) binary += String.fromCharCode(...bytes.subarray(i, i + size));
  return { filename: file.name, mime_type: file.type, base64: btoa(binary), use_ollama: $('#use-ollama-import').checked, model: $('#ollama-model').value };
}

async function analyzePayload(payload) {
  $('#import-preview').innerHTML = '<article class="panel preview-card"><p>Analisi locale in corso…</p></article>';
  try { const result = await api('/api/imports/analyze', { method: 'POST', body: JSON.stringify(payload) }); state.currentImport = result; renderImportPreview(result); await loadImports(); }
  catch (error) { $('#import-preview').innerHTML = ''; toast(error.message, 'error'); }
}

function renderImportPreview(item) {
  if (item.duplicate) toast('Questo file era già stato importato: mostro il precedente risultato.', 'error');
  const proposals = item.proposals || [];
  $('#import-preview').innerHTML = `<article class="panel preview-card"><div class="panel-head"><div><p class="eyebrow">Anteprima obbligatoria</p><h2>${escapeHtml(item.filename)}</h2></div>${statusBadge(item.status)}</div><div class="preview-layout"><div><h3>Originale / testo estratto</h3><div class="original-text">${escapeHtml(item.extracted_text || item.extracted?.text || 'Nessun testo estratto. Il file originale resta sul PC.')}</div>${(item.report?.warnings || item.extracted?.warnings || []).map(w => `<p class="error-text">${escapeHtml(w)}</p>`).join('')}</div><div><h3>Dati proposti — correggi prima di confermare</h3><form id="confirm-import-form">${proposals.length ? proposals.map((proposal, index) => proposalEditor(proposal, index)).join('') : '<p class="empty">Nessuna scheda proposta. Puoi conservare il file e riprovare con Ollama.</p>'}<div class="button-row"><button class="button primary" ${proposals.length ? '' : 'disabled'}>Conferma nel CRM</button><button class="button danger" type="button" data-dismiss-import>Non importare</button></div></form></div></div></article>`;
  if ($('#confirm-import-form')) $('#confirm-import-form').addEventListener('submit', confirmImport);
  $('[data-dismiss-import]')?.addEventListener('click', () => { $('#import-preview').innerHTML = ''; state.currentImport = null; });
}

function proposalEditor(proposal, index) {
  const input = (name, label, full = false) => `<label class="${full ? 'full' : ''}">${label}<input name="p${index}_${name}" value="${escapeHtml(proposal[name] ?? '')}"></label>`;
  return `<div class="proposal" data-proposal="${index}"><strong>Proposta ${index + 1}</strong><div class="proposal-grid">${input('first_name','Nome')}${input('last_name','Cognome')}${input('phone','Telefono')}${input('email','Email')}${input('full_address','Indirizzo completo',true)}${input('property_type','Tipologia')}${input('current_price','Prezzo')}${input('source','Fonte')}${input('source_url','Link',true)}${input('next_action','Prossima azione',true)}<label class="full">Nota<textarea name="p${index}_original_note" rows="3">${escapeHtml(proposal.original_note || '')}</textarea></label></div></div>`;
}

async function confirmImport(event) {
  event.preventDefault(); const data = new FormData(event.currentTarget); const source = state.currentImport.proposals || [];
  const proposals = source.map((base, index) => { const copy = { ...base }; for (const key of ['first_name','last_name','phone','email','full_address','property_type','current_price','source','source_url','next_action','original_note']) if (data.has(`p${index}_${key}`)) copy[key] = data.get(`p${index}_${key}`); if (copy.current_price) copy.current_price = Number(String(copy.current_price).replace(/[^\d,.-]/g, '').replace(',', '.')) || null; return copy; });
  try { const result = await api(`/api/imports/${state.currentImport.id}/confirm`, { method: 'POST', body: JSON.stringify({ proposals }) }); toast(`${result.report.imported} schede importate; ${result.report.duplicates} duplicati da verificare.`); $('#import-preview').innerHTML = ''; state.currentImport = null; await Promise.all([loadImports(), loadLeads(), loadDashboard()]); }
  catch (error) { toast(error.message, 'error'); }
}

async function loadImports() {
  state.imports = await api('/api/imports');
  $('#import-history').innerHTML = state.imports.length ? state.imports.slice(0, 20).map(item => `<div class="list-row"><div class="list-main"><strong>${escapeHtml(item.filename)}</strong><span>${fmtDate(item.created_at)} · ${escapeHtml(item.mime_type)} · ${item.report?.imported ?? 0} inseriti</span></div>${statusBadge(item.status)}</div>`).join('') : '<p class="empty">Ancora nessuna importazione.</p>';
}

async function checkOllama() {
  $('#ollama-message').textContent = 'Verifica del collegamento locale…';
  try {
    const result = await api('/api/ollama/status'); const online = result.online;
    $('#connection-dot').className = `status-dot ${online ? 'online' : 'offline'}`; $('#connection-label').textContent = online ? 'Ollama collegato' : 'Ollama non avviato';
    $('#ollama-badge').className = `badge ${online ? '' : 'danger'}`; $('#ollama-badge').textContent = online ? 'Collegato' : 'Non disponibile'; $('#ollama-message').textContent = online ? `${result.models.length} modelli locali rilevati.` : result.error;
    const selected = state.settings?.ollama_model || ''; $('#ollama-model').innerHTML = `<option value="">Seleziona un modello</option>${result.models.map(model => `<option value="${escapeHtml(model.name)}" ${selected === model.name ? 'selected' : ''}>${escapeHtml(model.name)}</option>`).join('')}`;
  } catch (error) { $('#ollama-message').textContent = error.message; }
}

async function loadSettings() {
  state.settings = await api('/api/settings'); $('#supabase-badge').textContent = state.settings.supabase_configured ? 'Configurato' : 'Non configurato'; $('#supabase-badge').className = `badge ${state.settings.supabase_configured ? '' : 'neutral'}`; await checkOllama();
}

async function askAssistant(question) {
  const log = $('#chat-log'); log.insertAdjacentHTML('beforeend', `<div class="user-message"><p>${escapeHtml(question)}</p></div><div id="thinking" class="assistant-message"><p>Sto cercando nelle fonti locali…</p></div>`); log.scrollTop = log.scrollHeight;
  try { const result = await api('/api/assistant/ask', { method: 'POST', body: JSON.stringify({ question, model: $('#ollama-model').value || state.settings?.ollama_model }) }); $('#thinking').remove(); log.insertAdjacentHTML('beforeend', `<div class="assistant-message"><strong>Assistente F1</strong><p>${escapeHtml(result.answer)}</p></div>`); $('#assistant-sources').innerHTML = result.sources.length ? result.sources.map(source => `<div class="list-row"><div class="list-main"><strong>${escapeHtml(source.source_name)}</strong><span>Sezione ${source.section}</span></div></div>`).join('') : '<p class="empty">Nessuna fonte trovata.</p>'; }
  catch (error) { $('#thinking')?.remove(); toast(error.message, 'error'); }
  log.scrollTop = log.scrollHeight;
}

function bindEvents() {
  $$('.nav-item').forEach(button => button.addEventListener('click', () => showView(button.dataset.view)));
  $$('[data-view-jump]').forEach(button => button.addEventListener('click', () => showView(button.dataset.viewJump)));
  $('#mobile-menu').addEventListener('click', () => $('.sidebar').classList.toggle('open'));
  $('#new-lead').addEventListener('click', openNewLead); $('#new-lead-2').addEventListener('click', openNewLead);
  $('#modal-close').addEventListener('click', closeModal); $('#modal').addEventListener('click', event => { if (event.target === $('#modal')) closeModal(); });
  document.addEventListener('click', async event => {
    const leadTarget = event.target.closest('[data-lead]'); if (leadTarget) await openLead(leadTarget.dataset.lead);
    const close = event.target.closest('[data-close]'); if (close) closeModal();
    const complete = event.target.closest('[data-complete-reminder]'); if (complete) { await api(`/api/reminders/${complete.dataset.completeReminder}/complete`, { method: 'POST' }); toast('Attività completata.'); await Promise.all([loadReminders(), loadDashboard()]); }
  });
  let searchTimer; $('#global-search').addEventListener('input', () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => { showView('leads'); loadLeads(); }, 250); });
  $('#lead-status-filter').addEventListener('change', loadLeads); $('#new-reminder').addEventListener('click', openReminderForm);
  $('#file-input').addEventListener('change', async event => { const files = [...event.target.files]; $('#file-list').innerHTML = files.map(file => `<div class="file-chip"><span>${escapeHtml(file.name)}</span><span>${(file.size / 1024).toFixed(0)} KB</span></div>`).join(''); for (const file of files) await analyzePayload(await fileToPayload(file)); event.target.value = ''; });
  $('#analyze-paste').addEventListener('click', () => { const text = $('#paste-text').value.trim(); if (!text) return toast('Incolla prima un testo.', 'error'); analyzePayload({ filename: `testo-incollato-${Date.now()}.txt`, mime_type: 'text/plain', text, use_ollama: $('#use-ollama-import').checked, model: $('#ollama-model').value }); });
  $('#retry-ollama').addEventListener('click', checkOllama); $('#save-settings').addEventListener('click', async () => { await api('/api/settings', { method: 'POST', body: JSON.stringify({ ollama_model: $('#ollama-model').value }) }); state.settings.ollama_model = $('#ollama-model').value; toast('Modello Ollama salvato.'); });
  $('#sync-supabase').addEventListener('click', async event => { event.currentTarget.disabled = true; try { const result = await api('/api/sync/supabase', { method: 'POST' }); toast(`Sincronizzazione completata: ${Object.values(result.counts).reduce((a, b) => a + b, 0)} record.`); } catch (error) { toast(error.message, 'error'); } finally { event.currentTarget.disabled = false; } });
  $('#assistant-form').addEventListener('submit', event => { event.preventDefault(); const input = $('#assistant-question'); const question = input.value.trim(); if (question) { input.value = ''; askAssistant(question); } });
  $('#monday-link').addEventListener('click', () => api('/api/monday/opened', { method: 'POST' }).catch(() => {}));
  $('#login-form').addEventListener('submit', async event => { event.preventDefault(); try { await api('/api/auth/login', { method: 'POST', body: JSON.stringify({ pin: $('#login-pin').value }) }); hideLogin(); await boot(); } catch (error) { $('#login-error').textContent = error.message; } });
}

async function boot() {
  const auth = await api('/api/auth/status'); if (auth.required && !auth.authenticated) return showLogin(); hideLogin();
  state.meta = await api('/api/meta');
  $('#today-label').textContent = new Intl.DateTimeFormat('it-IT', { dateStyle: 'full' }).format(new Date());
  $('#lead-status-filter').innerHTML += state.meta.outcomes.map(value => `<option>${escapeHtml(value)}</option>`).join('');
  $('#monday-link').href = state.meta.contents_url;
  if (state.meta.monday) $('#monday-banner').classList.remove('hidden');
  await Promise.all([loadDashboard(), loadLeads(), loadReminders(), loadImports()]);
  state.settings = await api('/api/settings'); checkOllama();
}

bindEvents();
boot().catch(error => toast(error.message, 'error'));
