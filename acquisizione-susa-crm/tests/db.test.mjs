import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import assert from 'node:assert/strict';
import { CrmStore } from '../src/db.mjs';

function withStore(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'crm-susa-test-'));
  const store = new CrmStore(path.join(dir, 'test.sqlite'));
  t.after(() => { store.close(); fs.rmSync(dir, { recursive: true, force: true }); });
  return store;
}

test('crea scheda, nota append-only e promemoria', t => {
  const store = withStore(t);
  const lead = store.createLead({ first_name: 'Cliente', phone: '333 111 2222', street: 'Via Demo', civic: '1', comune: 'Susa' });
  assert.equal(store.listLeads().length, 1);
  const callback = new Date(Date.now() + 86400000).toISOString();
  store.addNote(lead.id, { body: 'Richiamare dopo verifica documenti.', outcome: 'Richiamare', next_action: 'Verifica documenti', callback_at: callback });
  const updated = store.getLead(lead.id);
  assert.equal(updated.notes.length, 1);
  assert.equal(updated.reminders.length, 1);
  assert.equal(updated.contact_status, 'Richiamare');
});

test('intercetta duplicato per telefono normalizzato', t => {
  const store = withStore(t);
  store.createLead({ first_name: 'Cliente', phone: '+39 333 111 2222' });
  assert.equal(store.findDuplicate({ phone: '+39-333-111-2222' }).length, 1);
});

test('esporta soltanto dati strutturati', t => {
  const store = withStore(t);
  store.createLead({ property_type: 'Immobile prova', comune: 'Susa' });
  const data = store.exportData();
  assert.equal(data.leads.length, 1);
  assert.ok(Array.isArray(data.notes));
  assert.equal('imports' in data, false);
});
