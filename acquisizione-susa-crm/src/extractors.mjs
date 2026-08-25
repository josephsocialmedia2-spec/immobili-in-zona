import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { extractContacts, parseCsv } from './domain.mjs';

const execFileAsync = promisify(execFile);

export function detectType(filename = '', mime = '', buffer = Buffer.alloc(0)) {
  const ext = path.extname(filename).toLowerCase();
  const head = buffer.subarray(0, 8).toString('hex');
  if (head.startsWith('89504e47')) return 'image';
  if (head.startsWith('ffd8ff')) return 'image';
  if (head.startsWith('25504446')) return 'pdf';
  if (head.startsWith('504b0304') && ext === '.xlsx') return 'xlsx';
  if (head.startsWith('504b0304') && ext === '.docx') return 'docx';
  if (/image\//.test(mime) || ['.jpg', '.jpeg', '.png', '.webp'].includes(ext)) return 'image';
  if (ext === '.pdf' || mime === 'application/pdf') return 'pdf';
  if (ext === '.xlsx') return 'xlsx';
  if (ext === '.docx') return 'docx';
  if (['.csv', '.tsv'].includes(ext) || /csv/.test(mime)) return 'csv';
  if (['.json'].includes(ext) || /json/.test(mime)) return 'json';
  if (['.txt', '.md', '.html', '.htm'].includes(ext) || /^text\//.test(mime)) return 'text';
  return 'unknown';
}

async function command(command, args, options = {}) {
  try { return (await execFileAsync(command, args, { maxBuffer: 20 * 1024 * 1024, ...options })).stdout; }
  catch { return ''; }
}

export async function extractFile({ filename, mimeType, buffer, savedPath, projectRoot }) {
  const type = detectType(filename, mimeType, buffer);
  let text = '';
  let rows = [];
  const warnings = [];
  if (type === 'text' || type === 'json') text = buffer.toString('utf8');
  else if (type === 'csv') {
    text = buffer.toString('utf8');
    const parsed = parseCsv(text, path.extname(filename).toLowerCase() === '.tsv' ? '\t' : undefined);
    rows = parsed.rows;
  } else if (type === 'xlsx') {
    const script = path.join(projectRoot, 'scripts', 'extract_xlsx.py');
    let stdout = await command('python3', [script, savedPath]);
    if (!stdout) stdout = await command('python', [script, savedPath]);
    if (!stdout && process.platform === 'win32') stdout = await command('py', ['-3', script, savedPath]);
    if (stdout) { const parsed = JSON.parse(stdout); rows = parsed.rows || []; text = parsed.text || ''; warnings.push(...(parsed.warnings || [])); }
    else warnings.push('Impossibile leggere XLSX: installa Python 3 oppure esporta il file in CSV.');
  } else if (type === 'docx') {
    const xml = await command('unzip', ['-p', savedPath, 'word/document.xml']);
    text = xml.replace(/<w:tab\/?[^>]*>/g, '\t').replace(/<\/w:p>/g, '\n').replace(/<[^>]+>/g, ' ').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>');
    if (!text.trim()) {
      const script = path.join(projectRoot, 'scripts', 'extract_docx.py');
      text = await command('python3', [script, savedPath]) || await command('python', [script, savedPath]);
      if (!text && process.platform === 'win32') text = await command('py', ['-3', script, savedPath]);
    }
    if (!text.trim()) warnings.push('DOCX non leggibile automaticamente su questo PC.');
  } else if (type === 'pdf') {
    text = await command('pdftotext', ['-layout', savedPath, '-']);
    if (!text.trim()) warnings.push('PDF scansionato o pdftotext non disponibile: prova OCR/Ollama locale.');
  } else if (type === 'image') {
    text = await command('tesseract', [savedPath, 'stdout', '-l', 'ita+eng']);
    if (!text.trim()) text = await command('tesseract', [savedPath, 'stdout']);
    if (!text.trim()) warnings.push('OCR locale non disponibile: usa “Analizza con Ollama” con un modello visivo.');
  } else warnings.push('Tipo di file non riconosciuto. Il file resta conservato localmente.');
  return { type, text: text.trim(), rows, contacts: extractContacts(text), warnings };
}

export function saveOriginal(dataDir, filename, buffer) {
  const hash = crypto.createHash('sha256').update(buffer).digest('hex');
  const safeName = path.basename(filename).replace(/[^\p{L}\p{N}._-]+/gu, '_').slice(0, 100) || 'file';
  const dir = path.join(dataDir, 'imports', hash.slice(0, 2));
  fs.mkdirSync(dir, { recursive: true });
  const target = path.join(dir, `${hash}_${safeName}`);
  if (!fs.existsSync(target)) fs.writeFileSync(target, buffer, { mode: 0o600 });
  return { hash, target };
}
