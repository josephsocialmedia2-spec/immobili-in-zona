import test from 'node:test';
import assert from 'node:assert/strict';
import { classifyPrequalification, extractContacts, isMonday, mondayKey, parseCsv, requireContactNote } from '../src/domain.mjs';

test('CSV italiano con punto e virgola e virgolette', () => {
  const parsed = parseCsv('Nome;Telefono;Note\nAnna;333 123 4567;"Villa, da vedere"');
  assert.deepEqual(parsed.headers, ['Nome', 'Telefono', 'Note']);
  assert.equal(parsed.rows[0].Note, 'Villa, da vedere');
});

test('la nota è obbligatoria dopo un contatto', () => {
  assert.match(requireContactNote({ contact_status: 'Richiamare' }), /nota/i);
  assert.equal(requireContactNote({ contact_status: 'Richiamare', note: 'Chiede di sentirci venerdì.' }), null);
  assert.equal(requireContactNote({ contact_status: 'Richiamare', missing_note_reason: 'Linea caduta.' }), null);
});

test('prequalifica completa produce classe A', () => {
  const result = classifyPrequalification({ q2: 'Unico proprietario', q3: 'Trasferimento', q4: 'Entro tre mesi', q9: 'Valutiamo i dati', q10: 'Confrontiamo', q12: 'Sì, tutti presenti' });
  assert.equal(result.class, 'A');
});

test('calcolo settimana del lunedì', () => {
  const date = new Date('2026-08-25T10:00:00Z');
  assert.equal(mondayKey(date), '2026-08-24');
  assert.equal(isMonday(new Date('2026-08-24T10:00:00Z')), true);
});

test('estrae contatti senza inventare dati', () => {
  const result = extractContacts('Scrivere a prova@example.it o chiamare +39 333 123 4567. Prezzo € 125.000');
  assert.equal(result.emails[0], 'prova@example.it');
  assert.match(result.phones[0], /333/);
  assert.match(result.prices[0], /125/);
});

test('estrae numeri italiani con slash, trattini e più contatti', () => {
  const result = extractContacts('Casa: 0122/622123; mobile 333.555.7788; ufficio 011-1234567');
  assert.equal(result.phones.length, 3);
  assert.ok(result.phones.includes('0122/622123'));
  assert.ok(result.phones.includes('333.555.7788'));
  assert.ok(result.phones.includes('011-1234567'));
});
