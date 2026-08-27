import crypto from 'node:crypto';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { config } from './config.mjs';
import { APP_NAME, CONTENTS_F1_URL, CONTACT_OUTCOMES, PREQUAL_QUESTIONS, PRIORITIES } from './constants.mjs';
import { chunkText, classifyPrequalification, extractContacts, isMonday, mondayKey, nowIso, parseCsv, requireContactNote } from './domain.mjs';
import { CrmStore } from './db.mjs';
import { extractFile, saveOriginal } from './extractors.mjs';
import { OllamaClient } from './ollama.mjs';
import { SupabaseSync } from './supabase.mjs';

const projectRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const publicDir = path.join(projectRoot, 'public');
fs.mkdirSync(config.dataDir, { recursive: true });

export const store = new CrmStore(path.join(config.dataDir, 'crm.sqlite'));
const ollama = new OllamaClient(config.ollamaBaseUrl, config.ollamaModel);
const supabase = new SupabaseSync({ url: config.supabaseUrl, anonKey: config.supabaseAnonKey, serviceKey: config.supabaseServiceKey, userId: config.supabaseUserId });
const sessions = new Map();

function json(res, status, body, headers = {}) {
  const data = Buffer.from(JSON.stringify(body));
  res.writeHead(status, { 'content-type': 'application/json; charset=utf-8', 'content-length': data.length, 'cache-control': 'no-store', ...headers });
  res.end(data);
}

function error(res, status, message, details) { json(res, status, { error: message, ...(details ? { details } : {}) }); }

async function readJson(req, maxBytes = 35 * 1024 * 1024) {
  const chunks = [];
  let size = 0;
  for await (const chunk of req) {
    size += chunk.length;
    if (size > maxBytes) throw Object.assign(new Error('File troppo grande. Limite 35 MB per elemento.'), { statusCode: 413 });
    chunks.push(chunk);
  }
  if (!chunks.length) return {};
  try { return JSON.parse(Buffer.concat(chunks).toString('utf8')); }
  catch { throw Object.assign(new Error('Corpo JSON non valido.'), { statusCode: 400 }); }
}

function cookies(req) {
  return Object.fromEntries(String(req.headers.cookie || '').split(';').map(item => item.trim().split('=').map(decodeURIComponent)).filter(parts => parts.length === 2));
}

function isAuthenticated(req) {
  if (!config.crmPin) return true;
  const token = cookies(req).crm_session;
  const expires = token ? sessions.get(token) : 0;
  if (!expires || expires < Date.now()) { if (token) sessions.delete(token); return false; }
  return true;
}

function safeEqual(a, b) {
  const left = crypto.createHash('sha256').update(String(a)).digest();
  const right = crypto.createHash('sha256').update(String(b)).digest();
  return crypto.timingSafeEqual(left, right);
}

function leadFromRow(row = {}) {
  const normalized = Object.fromEntries(Object.entries(row).map(([key, value]) => [key.toLowerCase().trim().replace(/[^a-z0-9à-ÿ]+/g, '_'), value]));
  const pick = (...keys) => keys.map(key => normalized[key]).find(value => value !== undefined && value !== '') || '';
  const firstName = pick('nome', 'first_name');
  const lastName = pick('cognome', 'last_name');
  const street = pick('via', 'indirizzo', 'strada', 'street');
  const civic = pick('civico', 'numero_civico', 'n_civico', 'civic');
  const currentPrice = String(pick('prezzo', 'prezzo_attuale', 'current_price')).replace(/[^\d,.-]/g, '').replace(/\./g, '').replace(',', '.');
  return {
    first_name: firstName, last_name: lastName, company: pick('azienda', 'societa', 'company'),
    phone: pick('telefono', 'telefono_1', 'tel', 'cellulare', 'cell', 'mobile', 'numero', 'numero_telefono', 'recapito', 'phone', 'phone_number'),
    email: pick('email', 'e_mail', 'mail', 'posta_elettronica'), comune: pick('comune', 'citta', 'city') || 'Susa',
    cap: pick('cap'), street, civic, full_address: pick('indirizzo_completo', 'full_address') || [street, civic, pick('comune', 'citta') || 'Susa'].filter(Boolean).join(', '),
    property_type: pick('tipologia', 'tipo_immobile', 'property_type'), sqm: Number(pick('mq', 'metri_quadri', 'sqm')) || null,
    rooms: pick('locali', 'rooms'), features: pick('caratteristiche', 'features'), current_price: Number(currentPrice) || null,
    source: pick('fonte', 'source'), source_url: pick('url', 'link', 'link_annuncio', 'source_url'), seller_signal: pick('seller_signal', 'segnale'),
    seller_type: pick('tipo_venditore', 'seller_type'), priority: pick('priorita', 'priority') || 'Media',
    contact_status: pick('stato_contatto', 'contact_status', 'esito') || 'Da contattare', next_action: pick('prossima_azione', 'next_action'),
    callback_at: pick('richiamo', 'data_richiamo', 'callback_at') || null, original_note: pick('note', 'nota', 'original_note')
  };
}

function proposalKey(record = {}) {
  const phone = String(record.phone || '').replace(/\D/g, '');
  const email = String(record.email || '').trim().toLowerCase();
  const address = String(record.full_address || '').trim().toLowerCase();
  return phone ? `p:${phone}` : email ? `e:${email}` : address ? `a:${address}` : '';
}

function makeTextProposal({ phone = '', email = '', found = {}, note = '' } = {}) {
  return {
    first_name: '', last_name: '', phone, email, comune: 'Susa',
    full_address: '', property_type: '', current_price: found.prices?.[0] ? Number(found.prices[0].replace(/[^\d]/g, '')) : null,
    source: 'Importazione locale', source_url: found.urls?.[0] || '', contact_status: 'Da contattare', next_action: '',
    priority: 'Media', confidence: 0.35, original_note: note.slice(0, 12000)
  };
}

function heuristicProposals(extracted) {
  if (extracted.rows?.length) return extracted.rows.slice(0, 1000).map(leadFromRow);
  const text = String(extracted.text || '').trim();
  if (!text) return [];

  const lines = text.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
  const proposals = [];
  const seen = new Set();

  for (let index = 0; index < lines.length && proposals.length < 1000; index += 1) {
    const found = extractContacts(lines[index]);
    const count = Math.max(found.phones.length, found.emails.length);
    if (!count) continue;
    const context = lines.slice(Math.max(0, index - 1), Math.min(lines.length, index + 2)).join('\n');
    for (let item = 0; item < count && proposals.length < 1000; item += 1) {
      const proposal = makeTextProposal({
        phone: found.phones[item] || '',
        email: found.emails[item] || (item === 0 ? found.emails[0] || '' : ''),
        found,
        note: context
      });
      const key = proposalKey(proposal) || `line:${index}:${item}`;
      if (seen.has(key)) continue;
      seen.add(key);
      proposals.push(proposal);
    }
  }

  if (proposals.length) return proposals;

  const found = extractContacts(text);
  const count = Math.max(found.phones.length, found.emails.length, 1);
  return Array.from({ length: Math.min(count, 1000) }, (_, index) => makeTextProposal({
    phone: found.phones[index] || '',
    email: found.emails[index] || (index === 0 ? found.emails[0] || '' : ''),
    found,
    note: text
  }));
}

function mergeProposals(base = [], aiRecords = []) {
  const merged = [];
  const positions = new Map();
  for (const record of [...base, ...(aiRecords || [])]) {
    if (!record || typeof record !== 'object') continue;
    const key = proposalKey(record);
    if (key && positions.has(key)) {
      const position = positions.get(key);
      const current = merged[position];
      merged[position] = Object.fromEntries(Object.keys({ ...current, ...record }).map(field => [field, record[field] !== undefined && record[field] !== '' && record[field] !== null ? record[field] : current[field]]));
      continue;
    }
    const next = { ...record };
    if (key) positions.set(key, merged.length);
    merged.push(next);
    if (merged.length >= 1000) break;
  }
  return merged;
}

function csvEscape(value) {
  const text = value == null ? '' : String(value);
  return /[",\n;]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function exportCsv(rows) {
  if (!rows.length) return '';
  const headers = Object.keys(rows[0]);
  return [headers.join(';'), ...rows.map(row => headers.map(header => csvEscape(row[header])).join(';'))].join('\r\n');
}

function exportExcelXml(snapshot) {
  const rows = snapshot.leads;
  const headers = rows.length ? Object.keys(rows[0]) : ['id'];
  const cell = value => `<Cell><Data ss:Type="String">${String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')}</Data></Cell>`;
  return `<?xml version="1.0"?><Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet" xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet"><Worksheet ss:Name="CRM Susa"><Table><Row>${headers.map(cell).join('')}</Row>${rows.map(row => `<Row>${headers.map(header => cell(row[header])).join('')}</Row>`).join('')}</Table></Worksheet></Workbook>`;
}

async function handleApi(req, res, url) {
  const method = req.method || 'GET';

  if (url.pathname === '/api/auth/status' && method === 'GET') return json(res, 200, { required: Boolean(config.crmPin), authenticated: isAuthenticated(req) });
  if (url.pathname === '/api/auth/login' && method === 'POST') {
    const body = await readJson(req);
    if (!config.crmPin || safeEqual(body.pin || '', config.crmPin)) {
      const token = crypto.randomBytes(32).toString('hex');
      sessions.set(token, Date.now() + 12 * 60 * 60 * 1000);
      return json(res, 200, { ok: true }, { 'set-cookie': `crm_session=${token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=43200` });
    }
    return error(res, 401, 'PIN non corretto.');
  }
  if (url.pathname === '/api/auth/logout' && method === 'POST') {
    const token = cookies(req).crm_session; if (token) sessions.delete(token);
    return json(res, 200, { ok: true }, { 'set-cookie': 'crm_session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0' });
  }
  if (!isAuthenticated(req)) return error(res, 401, 'Accesso richiesto.');

  if (url.pathname === '/api/meta' && method === 'GET') {
    const today = new Date(); const week = mondayKey(today);
    return json(res, 200, { app_name: APP_NAME, questions: PREQUAL_QUESTIONS, outcomes: CONTACT_OUTCOMES, priorities: PRIORITIES, contents_url: CONTENTS_F1_URL, monday: isMonday(today), monday_opened: store.mondayWasOpened(week), week_key: week, supabase_configured: supabase.configured });
  }
  if (url.pathname === '/api/monday/opened' && method === 'POST') { store.markMonday(mondayKey(new Date())); return json(res, 200, { ok: true }); }
  if (url.pathname === '/api/dashboard' && method === 'GET') return json(res, 200, store.dashboard());

  if (url.pathname === '/api/leads' && method === 'GET') return json(res, 200, store.listLeads({ query: url.searchParams.get('q') || '', status: url.searchParams.get('status') || '' }));
  if (url.pathname === '/api/leads' && method === 'POST') {
    const body = await readJson(req);
    const duplicates = store.findDuplicate(body);
    if (duplicates.length && !body.keep_separate) return json(res, 409, { error: 'Possibile duplicato: conferma “Mantieni separato” oppure apri la scheda esistente.', duplicates });
    return json(res, 201, store.createLead(body));
  }
  const leadMatch = url.pathname.match(/^\/api\/leads\/([^/]+)$/);
  if (leadMatch && method === 'GET') {
    const lead = store.getLead(leadMatch[1]); return lead ? json(res, 200, lead) : error(res, 404, 'Scheda non trovata.');
  }
  if (leadMatch && method === 'PATCH') {
    const body = await readJson(req);
    const current = store.getLead(leadMatch[1]);
    if (!current) return error(res, 404, 'Scheda non trovata.');
    const statusChanged = body.contact_status && body.contact_status !== current.contact_status;
    const noteError = requireContactNote({ ...body, contact_attempted: Boolean(body.contact_attempted || statusChanged) });
    if (noteError) return error(res, 422, noteError);
    const lead = store.updateLead(leadMatch[1], body);
    if (body.note || body.missing_note_reason) store.addNote(leadMatch[1], { body: body.note, missing_note_reason: body.missing_note_reason, outcome: body.contact_status, next_action: body.next_action, callback_at: body.callback_at, contact_type: body.contact_type });
    return json(res, 200, store.getLead(leadMatch[1]));
  }
  const notesMatch = url.pathname.match(/^\/api\/leads\/([^/]+)\/notes$/);
  if (notesMatch && method === 'POST') {
    const note = store.addNote(notesMatch[1], await readJson(req));
    return note ? json(res, 201, note) : error(res, 404, 'Scheda non trovata.');
  }
  const prequalMatch = url.pathname.match(/^\/api\/leads\/([^/]+)\/prequalification$/);
  if (prequalMatch && method === 'POST') {
    const body = await readJson(req); const classification = classifyPrequalification(body.answers || {});
    return json(res, 201, store.savePrequalification(prequalMatch[1], body.answers || {}, classification));
  }

  if (url.pathname === '/api/reminders' && method === 'GET') return json(res, 200, store.listReminders());
  if (url.pathname === '/api/reminders' && method === 'POST') return json(res, 201, store.createReminder(await readJson(req)));
  const reminderMatch = url.pathname.match(/^\/api\/reminders\/([^/]+)\/complete$/);
  if (reminderMatch && method === 'POST') return json(res, 200, store.completeReminder(reminderMatch[1]) || {});

  if (url.pathname === '/api/ollama/status' && method === 'GET') return json(res, 200, await ollama.status());
  if (url.pathname === '/api/settings' && method === 'GET') return json(res, 200, { ollama_model: store.getSetting('ollama_model', config.ollamaModel), ollama_base_url: config.ollamaBaseUrl, supabase_configured: supabase.configured });
  if (url.pathname === '/api/settings' && method === 'POST') {
    const body = await readJson(req); if (Object.hasOwn(body, 'ollama_model')) store.setSetting('ollama_model', body.ollama_model);
    return json(res, 200, { ok: true, ollama_model: store.getSetting('ollama_model', config.ollamaModel) });
  }

  if (url.pathname === '/api/imports' && method === 'GET') return json(res, 200, store.listImports());
  if (url.pathname === '/api/imports/analyze' && method === 'POST') {
    const body = await readJson(req);
    const filename = path.basename(body.filename || 'testo-incollato.txt');
    const buffer = body.base64 ? Buffer.from(body.base64, 'base64') : Buffer.from(String(body.text || ''), 'utf8');
    if (!buffer.length) return error(res, 400, 'Il file o il testo è vuoto.');
    const saved = saveOriginal(config.dataDir, filename, buffer);
    const previous = store.db.prepare('SELECT * FROM imports WHERE sha256=?').get(saved.hash);
    const extracted = await extractFile({ filename, mimeType: body.mime_type || '', buffer, savedPath: saved.target, projectRoot });
    let proposals = heuristicProposals(extracted);
    let model = '';
    if (body.use_ollama) {
      model = body.model || store.getSetting('ollama_model', config.ollamaModel);
      const images = extracted.type === 'image' ? [buffer.toString('base64')] : [];
      const ai = await ollama.extract(extracted.text || `Analizza l'immagine ${filename}`, model, images);
      proposals = mergeProposals(proposals, ai.records);
      extracted.warnings.push(...(ai.warnings || []));
    }
    const report = { rows: extracted.rows.length, warnings: extracted.warnings, contacts: extracted.contacts };
    const result = previous
      ? { ...store.getImport(previous.id), status: 'Da confermare', extracted_text: extracted.text, proposals, model, report, duplicate: false, reanalyzed: true }
      : store.createImport({ filename, mime_type: extracted.type, sha256: saved.hash, local_path: saved.target, extracted_text: extracted.text, proposals, model, report });
    if (extracted.text && !previous) store.addKnowledgeChunks(result.id, filename, chunkText(extracted.text));
    return json(res, previous ? 200 : 201, { ...result, extracted });
  }
  const importMatch = url.pathname.match(/^\/api\/imports\/([^/]+)$/);
  if (importMatch && method === 'GET') {
    const item = store.getImport(importMatch[1]); return item ? json(res, 200, item) : error(res, 404, 'Importazione non trovata.');
  }
  const confirmMatch = url.pathname.match(/^\/api\/imports\/([^/]+)\/confirm$/);
  if (confirmMatch && method === 'POST') {
    const body = await readJson(req); return json(res, 200, store.confirmImport(confirmMatch[1], body.proposals || []));
  }

  if (url.pathname === '/api/assistant/ask' && method === 'POST') {
    const body = await readJson(req); if (!body.question) return error(res, 400, 'Scrivi una domanda.');
    const model = body.model || store.getSetting('ollama_model', config.ollamaModel);
    return json(res, 200, await ollama.answer(body.question, store.listKnowledgeChunks(), model));
  }

  if (url.pathname === '/api/sync/supabase' && method === 'POST') return json(res, 200, { synced_at: nowIso(), counts: await supabase.syncSnapshot(store.exportData()) });

  if (url.pathname === '/api/export' && method === 'GET') {
    const format = url.searchParams.get('format') || 'json';
    const stamp = nowIso().replace(/[:.]/g, '-'); const snapshot = store.exportData();
    if (format === 'csv') {
      const data = Buffer.from(`\uFEFF${exportCsv(snapshot.leads)}`);
      res.writeHead(200, { 'content-type': 'text/csv; charset=utf-8', 'content-disposition': `attachment; filename="backup-crm-susa-${stamp}.csv"`, 'content-length': data.length }); return res.end(data);
    }
    if (format === 'excel') {
      const data = Buffer.from(exportExcelXml(snapshot));
      res.writeHead(200, { 'content-type': 'application/vnd.ms-excel; charset=utf-8', 'content-disposition': `attachment; filename="backup-crm-susa-${stamp}.xls"`, 'content-length': data.length }); return res.end(data);
    }
    const data = Buffer.from(JSON.stringify(snapshot, null, 2));
    res.writeHead(200, { 'content-type': 'application/json; charset=utf-8', 'content-disposition': `attachment; filename="backup-crm-susa-${stamp}.json"`, 'content-length': data.length }); return res.end(data);
  }
  return error(res, 404, 'Endpoint non trovato.');
}

function serveStatic(req, res, url) {
  const requested = url.pathname === '/' ? 'index.html' : decodeURIComponent(url.pathname.slice(1));
  const filename = path.resolve(publicDir, requested);
  if (!filename.startsWith(`${publicDir}${path.sep}`) && filename !== path.join(publicDir, 'index.html')) return error(res, 403, 'Percorso non consentito.');
  if (!fs.existsSync(filename) || fs.statSync(filename).isDirectory()) return serveStatic(req, res, new URL('/', 'http://local'));
  const types = { '.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.svg': 'image/svg+xml' };
  const data = fs.readFileSync(filename);
  res.writeHead(200, { 'content-type': types[path.extname(filename)] || 'application/octet-stream', 'content-length': data.length, 'cache-control': path.extname(filename) === '.html' ? 'no-store' : 'public, max-age=300', 'x-content-type-options': 'nosniff', 'content-security-policy': "default-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; form-action 'self'; frame-ancestors 'none'" });
  res.end(data);
}

export const server = http.createServer(async (req, res) => {
  const url = new URL(req.url || '/', `http://${req.headers.host || 'localhost'}`);
  try {
    if (url.pathname === '/api/health') return json(res, 200, { ok: true, app: APP_NAME, time: nowIso() });
    if (url.pathname.startsWith('/api/')) return await handleApi(req, res, url);
    return serveStatic(req, res, url);
  } catch (caught) {
    console.error(caught);
    return error(res, caught.statusCode || 500, caught.message || 'Errore interno.');
  }
});

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  server.listen(config.port, config.host, () => console.log(`${APP_NAME} disponibile su http://${config.host}:${config.port}`));
}
