import fs from 'node:fs';
import path from 'node:path';
import { DatabaseSync } from 'node:sqlite';
import { newId, normalizeEmail, normalizePhone, nowIso } from './domain.mjs';

const LEAD_FIELDS = [
  'first_name', 'last_name', 'company', 'phone', 'email', 'comune', 'cap', 'street', 'civic',
  'full_address', 'property_type', 'sqm', 'rooms', 'features', 'current_price', 'previous_price',
  'source', 'source_url', 'seller_signal', 'seller_type', 'priority', 'confidence', 'contact_status',
  'next_action', 'callback_at', 'original_note', 'privacy_rule', 'qualification_class'
];

export class CrmStore {
  constructor(filename) {
    fs.mkdirSync(path.dirname(filename), { recursive: true });
    this.db = new DatabaseSync(filename);
    this.db.exec('PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON;');
    this.migrate();
  }

  migrate() {
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS leads (
        id TEXT PRIMARY KEY, first_name TEXT DEFAULT '', last_name TEXT DEFAULT '', company TEXT DEFAULT '',
        phone TEXT DEFAULT '', email TEXT DEFAULT '', comune TEXT DEFAULT 'Susa', cap TEXT DEFAULT '',
        street TEXT DEFAULT '', civic TEXT DEFAULT '', full_address TEXT DEFAULT '', property_type TEXT DEFAULT '',
        sqm REAL, rooms TEXT DEFAULT '', features TEXT DEFAULT '', current_price REAL, previous_price REAL,
        source TEXT DEFAULT '', source_url TEXT DEFAULT '', seller_signal TEXT DEFAULT '', seller_type TEXT DEFAULT '',
        priority TEXT DEFAULT 'Media', confidence REAL, contact_status TEXT DEFAULT 'Da contattare',
        next_action TEXT DEFAULT '', callback_at TEXT, original_note TEXT DEFAULT '', privacy_rule TEXT DEFAULT '',
        qualification_class TEXT DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
      );
      CREATE INDEX IF NOT EXISTS idx_leads_callback ON leads(callback_at);
      CREATE INDEX IF NOT EXISTS idx_leads_phone ON leads(phone);
      CREATE INDEX IF NOT EXISTS idx_leads_address ON leads(comune, street, civic);

      CREATE TABLE IF NOT EXISTS notes (
        id TEXT PRIMARY KEY, lead_id TEXT NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
        body TEXT NOT NULL, contact_type TEXT DEFAULT '', outcome TEXT DEFAULT '', next_action TEXT DEFAULT '',
        callback_at TEXT, missing_note_reason TEXT DEFAULT '', created_at TEXT NOT NULL
      );
      CREATE INDEX IF NOT EXISTS idx_notes_lead_created ON notes(lead_id, created_at DESC);

      CREATE TABLE IF NOT EXISTS reminders (
        id TEXT PRIMARY KEY, lead_id TEXT REFERENCES leads(id) ON DELETE CASCADE, title TEXT NOT NULL,
        due_at TEXT NOT NULL, status TEXT DEFAULT 'Aperto', priority TEXT DEFAULT 'Media',
        created_at TEXT NOT NULL, completed_at TEXT
      );
      CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(status, due_at);

      CREATE TABLE IF NOT EXISTS prequalifications (
        id TEXT PRIMARY KEY, lead_id TEXT NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
        answers_json TEXT NOT NULL, class TEXT NOT NULL, action TEXT NOT NULL, created_at TEXT NOT NULL
      );

      CREATE TABLE IF NOT EXISTS imports (
        id TEXT PRIMARY KEY, filename TEXT NOT NULL, mime_type TEXT DEFAULT '', sha256 TEXT NOT NULL,
        local_path TEXT DEFAULT '', status TEXT NOT NULL, extracted_text TEXT DEFAULT '', proposals_json TEXT DEFAULT '[]',
        model TEXT DEFAULT '', report_json TEXT DEFAULT '{}', created_at TEXT NOT NULL, confirmed_at TEXT
      );
      CREATE UNIQUE INDEX IF NOT EXISTS idx_imports_hash ON imports(sha256);

      CREATE TABLE IF NOT EXISTS knowledge_chunks (
        id TEXT PRIMARY KEY, import_id TEXT REFERENCES imports(id) ON DELETE CASCADE, source_name TEXT NOT NULL,
        chunk_index INTEGER NOT NULL, content TEXT NOT NULL, embedding_json TEXT DEFAULT '', created_at TEXT NOT NULL
      );

      CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS monday_activity (week_key TEXT PRIMARY KEY, opened_at TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS audit_log (
        id TEXT PRIMARY KEY, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL, action TEXT NOT NULL,
        snapshot_json TEXT NOT NULL, created_at TEXT NOT NULL
      );
    `);
  }

  close() { this.db.close(); }

  audit(entityType, entityId, action, snapshot) {
    this.db.prepare('INSERT INTO audit_log VALUES (?, ?, ?, ?, ?, ?)')
      .run(newId('audit'), entityType, entityId, action, JSON.stringify(snapshot), nowIso());
  }

  createLead(input = {}) {
    const id = newId('lead');
    const stamp = nowIso();
    const defaults = { comune: 'Susa', priority: 'Media', contact_status: 'Da contattare' };
    const data = Object.fromEntries(LEAD_FIELDS.map(field => [field, input[field] ?? defaults[field] ?? (['sqm', 'current_price', 'previous_price', 'confidence', 'callback_at'].includes(field) ? null : '')]));
    data.phone = normalizePhone(data.phone || '');
    data.email = normalizeEmail(data.email || '');
    if (!data.full_address) data.full_address = [data.street, data.civic, data.comune].filter(Boolean).join(', ');
    const fields = ['id', ...LEAD_FIELDS, 'created_at', 'updated_at'];
    const values = [id, ...LEAD_FIELDS.map(field => data[field]), stamp, stamp];
    this.db.prepare(`INSERT INTO leads (${fields.join(',')}) VALUES (${fields.map(() => '?').join(',')})`).run(...values);
    const lead = this.getLead(id);
    this.audit('lead', id, 'create', lead);
    return lead;
  }

  updateLead(id, input = {}) {
    const entries = LEAD_FIELDS.filter(field => Object.hasOwn(input, field)).map(field => [field, input[field]]);
    if (!entries.length) return this.getLead(id);
    for (const entry of entries) {
      if (entry[0] === 'phone') entry[1] = normalizePhone(entry[1] || '');
      if (entry[0] === 'email') entry[1] = normalizeEmail(entry[1] || '');
    }
    const stamp = nowIso();
    this.db.prepare(`UPDATE leads SET ${entries.map(([field]) => `${field}=?`).join(',')}, updated_at=? WHERE id=?`)
      .run(...entries.map(([, value]) => value), stamp, id);
    const lead = this.getLead(id);
    if (lead) this.audit('lead', id, 'update', lead);
    return lead;
  }

  getLead(id) {
    const lead = this.db.prepare('SELECT * FROM leads WHERE id=?').get(id);
    if (!lead) return null;
    return {
      ...lead,
      notes: this.db.prepare('SELECT * FROM notes WHERE lead_id=? ORDER BY created_at DESC').all(id),
      reminders: this.db.prepare('SELECT * FROM reminders WHERE lead_id=? ORDER BY due_at').all(id),
      prequalifications: this.db.prepare('SELECT * FROM prequalifications WHERE lead_id=? ORDER BY created_at DESC').all(id)
        .map(row => ({ ...row, answers: JSON.parse(row.answers_json) }))
    };
  }

  listLeads({ query = '', status = '', limit = 250 } = {}) {
    const filters = [];
    const params = [];
    if (status) { filters.push('contact_status=?'); params.push(status); }
    if (query) {
      const like = `%${query}%`;
      filters.push(`(first_name LIKE ? OR last_name LIKE ? OR company LIKE ? OR phone LIKE ? OR email LIKE ? OR full_address LIKE ? OR source LIKE ? OR original_note LIKE ? OR id IN (SELECT lead_id FROM notes WHERE body LIKE ?))`);
      params.push(...Array(9).fill(like));
    }
    params.push(Math.min(Number(limit) || 250, 1000));
    return this.db.prepare(`SELECT * FROM leads ${filters.length ? `WHERE ${filters.join(' AND ')}` : ''} ORDER BY CASE priority WHEN 'Urgente' THEN 1 WHEN 'Alta' THEN 2 WHEN 'Media' THEN 3 ELSE 4 END, updated_at DESC LIMIT ?`).all(...params);
  }

  findDuplicate(input = {}) {
    const phone = normalizePhone(input.phone || '');
    const email = normalizeEmail(input.email || '');
    const address = String(input.full_address || [input.street, input.civic, input.comune].filter(Boolean).join(', ')).trim();
    if (!phone && !email && !address) return [];
    return this.db.prepare(`SELECT * FROM leads WHERE (? <> '' AND phone=?) OR (? <> '' AND email=?) OR (? <> '' AND lower(full_address)=lower(?)) LIMIT 20`)
      .all(phone, phone, email, email, address, address);
  }

  addNote(leadId, input = {}) {
    const lead = this.getLead(leadId);
    if (!lead) return null;
    const id = newId('note');
    const stamp = nowIso();
    const body = String(input.body || '').trim();
    const reason = String(input.missing_note_reason || '').trim();
    if (!body && !reason) throw new Error('Inserisci la nota oppure il motivo per cui manca.');
    this.db.prepare('INSERT INTO notes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)')
      .run(id, leadId, body || `[Nota mancante: ${reason}]`, input.contact_type || '', input.outcome || '', input.next_action || '', input.callback_at || null, reason, stamp);
    const update = { updated_at: stamp };
    if (input.outcome) update.contact_status = input.outcome;
    if (input.next_action) update.next_action = input.next_action;
    if (input.callback_at) update.callback_at = input.callback_at;
    const fields = Object.keys(update);
    this.db.prepare(`UPDATE leads SET ${fields.map(field => `${field}=?`).join(',')} WHERE id=?`).run(...fields.map(field => update[field]), leadId);
    if (input.callback_at) this.createReminder({ lead_id: leadId, title: input.next_action || `Ricontattare ${[lead.first_name, lead.last_name].filter(Boolean).join(' ') || lead.full_address}`, due_at: input.callback_at, priority: lead.priority || 'Media' });
    const note = this.db.prepare('SELECT * FROM notes WHERE id=?').get(id);
    this.audit('note', id, 'append', note);
    return note;
  }

  createReminder(input = {}) {
    if (!input.title || !input.due_at) throw new Error('Titolo e data del promemoria sono obbligatori.');
    const row = { id: newId('rem'), lead_id: input.lead_id || null, title: input.title, due_at: input.due_at, status: 'Aperto', priority: input.priority || 'Media', created_at: nowIso(), completed_at: null };
    this.db.prepare('INSERT INTO reminders VALUES (?, ?, ?, ?, ?, ?, ?, ?)').run(...Object.values(row));
    this.audit('reminder', row.id, 'create', row);
    return row;
  }

  listReminders() {
    return this.db.prepare(`SELECT r.*, trim(coalesce(l.first_name,'') || ' ' || coalesce(l.last_name,'')) AS lead_name, l.full_address
      FROM reminders r LEFT JOIN leads l ON l.id=r.lead_id ORDER BY CASE r.status WHEN 'Aperto' THEN 1 ELSE 2 END, r.due_at`).all();
  }

  completeReminder(id) {
    this.db.prepare("UPDATE reminders SET status='Completato', completed_at=? WHERE id=?").run(nowIso(), id);
    const row = this.db.prepare('SELECT * FROM reminders WHERE id=?').get(id);
    if (row) this.audit('reminder', id, 'complete', row);
    return row;
  }

  savePrequalification(leadId, answers, classification) {
    const row = { id: newId('preq'), lead_id: leadId, answers_json: JSON.stringify(answers), class: classification.class, action: classification.action, created_at: nowIso() };
    this.db.prepare('INSERT INTO prequalifications VALUES (?, ?, ?, ?, ?, ?)').run(...Object.values(row));
    this.db.prepare('UPDATE leads SET qualification_class=?, updated_at=? WHERE id=?').run(row.class, row.created_at, leadId);
    this.audit('prequalification', row.id, 'create', row);
    return { ...row, answers };
  }

  dashboard(now = new Date()) {
    const start = new Date(now); start.setHours(0, 0, 0, 0);
    const end = new Date(start); end.setDate(end.getDate() + 1);
    const week = new Date(start); week.setDate(week.getDate() + 7);
    const open = "status='Aperto'";
    return {
      total_leads: this.db.prepare('SELECT count(*) AS n FROM leads').get().n,
      overdue: this.db.prepare(`SELECT count(*) AS n FROM reminders WHERE ${open} AND due_at < ?`).get(start.toISOString()).n,
      today: this.db.prepare(`SELECT count(*) AS n FROM reminders WHERE ${open} AND due_at >= ? AND due_at < ?`).get(start.toISOString(), end.toISOString()).n,
      next_7_days: this.db.prepare(`SELECT count(*) AS n FROM reminders WHERE ${open} AND due_at >= ? AND due_at < ?`).get(end.toISOString(), week.toISOString()).n,
      missing_next_action: this.db.prepare("SELECT count(*) AS n FROM leads WHERE trim(coalesce(next_action,''))='' OR callback_at IS NULL").get().n,
      missing_notes: this.db.prepare("SELECT count(*) AS n FROM leads l WHERE contact_status <> 'Da contattare' AND NOT EXISTS (SELECT 1 FROM notes n WHERE n.lead_id=l.id)").get().n,
      high_priority: this.db.prepare("SELECT count(*) AS n FROM leads WHERE priority IN ('Alta','Urgente')").get().n
    };
  }

  getSetting(key, fallback = '') { return this.db.prepare('SELECT value FROM settings WHERE key=?').get(key)?.value ?? fallback; }
  setSetting(key, value) {
    this.db.prepare(`INSERT INTO settings(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at`)
      .run(key, String(value), nowIso());
    return { key, value: String(value) };
  }

  markMonday(weekKey) {
    this.db.prepare('INSERT OR IGNORE INTO monday_activity VALUES (?, ?)').run(weekKey, nowIso());
  }
  mondayWasOpened(weekKey) { return Boolean(this.db.prepare('SELECT 1 FROM monday_activity WHERE week_key=?').get(weekKey)); }

  createImport(input) {
    const existing = this.db.prepare('SELECT * FROM imports WHERE sha256=?').get(input.sha256);
    if (existing) return { ...existing, duplicate: true };
    const row = { id: newId('imp'), filename: input.filename, mime_type: input.mime_type || '', sha256: input.sha256, local_path: input.local_path || '', status: input.status || 'Da confermare', extracted_text: input.extracted_text || '', proposals_json: JSON.stringify(input.proposals || []), model: input.model || '', report_json: JSON.stringify(input.report || {}), created_at: nowIso(), confirmed_at: null };
    this.db.prepare('INSERT INTO imports VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)').run(...Object.values(row));
    return { ...row, proposals: input.proposals || [], report: input.report || {}, duplicate: false };
  }

  listImports() {
    return this.db.prepare('SELECT id,filename,mime_type,sha256,status,model,report_json,created_at,confirmed_at FROM imports ORDER BY created_at DESC').all()
      .map(row => ({ ...row, report: JSON.parse(row.report_json || '{}') }));
  }
  getImport(id) {
    const row = this.db.prepare('SELECT * FROM imports WHERE id=?').get(id);
    return row ? { ...row, proposals: JSON.parse(row.proposals_json || '[]'), report: JSON.parse(row.report_json || '{}') } : null;
  }
  confirmImport(id, proposals = []) {
    const imported = []; const duplicates = [];
    for (const proposal of proposals) {
      const matches = this.findDuplicate(proposal);
      if (matches.length) duplicates.push({ proposal, matches });
      else imported.push(this.createLead(proposal));
    }
    const report = { imported: imported.length, duplicates: duplicates.length, rejected: 0, errors: 0 };
    this.db.prepare("UPDATE imports SET status='Confermato', proposals_json=?, report_json=?, confirmed_at=? WHERE id=?")
      .run(JSON.stringify(proposals), JSON.stringify(report), nowIso(), id);
    return { imported, duplicates, report };
  }

  addKnowledgeChunks(importId, sourceName, chunks, embeddings = []) {
    const insert = this.db.prepare('INSERT INTO knowledge_chunks VALUES (?, ?, ?, ?, ?, ?, ?)');
    chunks.forEach((content, index) => insert.run(newId('chunk'), importId || null, sourceName, index, content, embeddings[index] ? JSON.stringify(embeddings[index]) : '', nowIso()));
  }
  listKnowledgeChunks() { return this.db.prepare('SELECT * FROM knowledge_chunks ORDER BY created_at DESC').all(); }

  exportData() {
    return {
      exported_at: nowIso(),
      leads: this.db.prepare('SELECT * FROM leads ORDER BY created_at').all(),
      notes: this.db.prepare('SELECT * FROM notes ORDER BY created_at').all(),
      reminders: this.db.prepare('SELECT * FROM reminders ORDER BY created_at').all(),
      prequalifications: this.db.prepare('SELECT * FROM prequalifications ORDER BY created_at').all()
    };
  }
}
