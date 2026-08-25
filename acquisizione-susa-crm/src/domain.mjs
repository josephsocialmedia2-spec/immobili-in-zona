import crypto from 'node:crypto';

export function newId(prefix = 'id') {
  return `${prefix}_${crypto.randomUUID()}`;
}

export function nowIso() {
  return new Date().toISOString();
}

export function normalizePhone(value = '') {
  const cleaned = String(value).replace(/[^\d+]/g, '');
  if (cleaned.startsWith('00')) return `+${cleaned.slice(2)}`;
  return cleaned;
}

export function normalizeEmail(value = '') {
  return String(value).trim().toLowerCase();
}

export function normalizeText(value = '') {
  return String(value).normalize('NFD').replace(/[\u0300-\u036f]/g, '').trim().toLowerCase();
}

export function mondayKey(date = new Date()) {
  const copy = new Date(date);
  const day = copy.getDay();
  const distance = day === 0 ? -6 : 1 - day;
  copy.setDate(copy.getDate() + distance);
  return copy.toISOString().slice(0, 10);
}

export function isMonday(date = new Date()) {
  return date.getDay() === 1;
}

export function classifyPrequalification(answers = {}) {
  const text = Object.values(answers).join(' ').toLowerCase();
  const hasMotive = Boolean(String(answers.q3 || '').trim());
  const hasTiming = Boolean(String(answers.q4 || '').trim());
  const ownersKnown = Boolean(String(answers.q2 || '').trim());
  const decisionMakers = Boolean(String(answers.q12 || '').trim());
  const priceOpen = !/(non tratto|non discut|prezzo fisso|solo se)/i.test(`${answers.q9 || ''} ${answers.q10 || ''}`);
  const redFlags = /(solo valutazione|non sono proprietario|nessun progetto|non rispondo|non voglio dire)/i.test(text);
  const score = [hasMotive, hasTiming, ownersKnown, decisionMakers, priceOpen].filter(Boolean).length;
  if (!redFlags && score >= 5) return { class: 'A', action: 'Fissare l’appuntamento preferibilmente entro 72 ore.' };
  if (redFlags || score <= 1) return { class: 'C', action: 'Non è ancora il momento: concordare le condizioni minime per riparlarne.' };
  return { class: 'B', action: 'Concordare una prossima azione precisa e una data precisa.' };
}

export function requireContactNote(payload = {}) {
  const changed = Boolean(payload.contact_attempted || payload.contact_status);
  if (!changed) return null;
  if (String(payload.note || '').trim()) return null;
  if (String(payload.missing_note_reason || '').trim()) return null;
  return 'Dopo ogni contatto devi inserire una nota oppure spiegare perché la nota manca.';
}

export function parseCsv(text, delimiter) {
  const source = String(text || '').replace(/^\uFEFF/, '');
  const firstLine = source.split(/\r?\n/, 1)[0] || '';
  const sep = delimiter || (firstLine.split(';').length > firstLine.split(',').length ? ';' : ',');
  const rows = [];
  let row = [];
  let cell = '';
  let quoted = false;
  for (let i = 0; i < source.length; i += 1) {
    const char = source[i];
    if (char === '"') {
      if (quoted && source[i + 1] === '"') { cell += '"'; i += 1; }
      else quoted = !quoted;
    } else if (char === sep && !quoted) {
      row.push(cell.trim()); cell = '';
    } else if ((char === '\n' || char === '\r') && !quoted) {
      if (char === '\r' && source[i + 1] === '\n') i += 1;
      row.push(cell.trim());
      if (row.some(Boolean)) rows.push(row);
      row = []; cell = '';
    } else cell += char;
  }
  row.push(cell.trim());
  if (row.some(Boolean)) rows.push(row);
  if (!rows.length) return { headers: [], rows: [] };
  const headers = rows[0].map((h, index) => h || `colonna_${index + 1}`);
  return {
    headers,
    rows: rows.slice(1).map(values => Object.fromEntries(headers.map((header, index) => [header, values[index] || ''])))
  };
}

export function extractContacts(text = '') {
  const phones = [...new Set(String(text).match(/(?:\+39[\s.-]?)?(?:3\d{2}|0\d{1,3})[\s.-]?\d{3}[\s.-]?\d{3,4}/g) || [])];
  const emails = [...new Set(String(text).match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi) || [])];
  const prices = [...new Set(String(text).match(/(?:€\s?|euro\s?)\d{1,3}(?:[.\s]\d{3})*(?:,\d{2})?/gi) || [])];
  const urls = [...new Set(String(text).match(/https?:\/\/[^\s)>\]]+/gi) || [])];
  return { phones, emails, prices, urls };
}

export function chunkText(text = '', maxChars = 1200) {
  const paragraphs = String(text).split(/\n{2,}/).map(p => p.trim()).filter(Boolean);
  const chunks = [];
  let current = '';
  for (const paragraph of paragraphs) {
    if (current && current.length + paragraph.length + 2 > maxChars) {
      chunks.push(current); current = '';
    }
    current += `${current ? '\n\n' : ''}${paragraph}`;
  }
  if (current) chunks.push(current);
  return chunks;
}

export function cosineSimilarity(a = [], b = []) {
  if (!a.length || a.length !== b.length) return 0;
  let dot = 0; let aa = 0; let bb = 0;
  for (let i = 0; i < a.length; i += 1) { dot += a[i] * b[i]; aa += a[i] ** 2; bb += b[i] ** 2; }
  return aa && bb ? dot / (Math.sqrt(aa) * Math.sqrt(bb)) : 0;
}
