export class SupabaseSync {
  constructor({ url, anonKey, serviceKey, userId }) { this.url = url; this.key = serviceKey || anonKey; this.userId = userId; }
  get configured() { return Boolean(this.url && this.key && this.userId); }

  async upsert(table, rows) {
    if (!this.configured) throw new Error('Supabase non è configurato. Compila SUPABASE_URL e una chiave nel file .env.');
    if (!rows.length) return [];
    const response = await fetch(`${this.url}/rest/v1/${table}?on_conflict=id`, {
      method: 'POST',
      headers: { apikey: this.key, authorization: `Bearer ${this.key}`, 'content-type': 'application/json', prefer: 'resolution=merge-duplicates,return=representation' },
      body: JSON.stringify(rows.map(row => ({ ...row, owner_id: this.userId }))), signal: AbortSignal.timeout(30000)
    });
    if (!response.ok) throw new Error(`Supabase ${response.status}: ${await response.text()}`);
    return response.json();
  }

  async syncSnapshot(snapshot) {
    const result = {};
    for (const table of ['leads', 'notes', 'reminders', 'prequalifications']) result[table] = (await this.upsert(table, snapshot[table] || [])).length;
    return result;
  }
}
