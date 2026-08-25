import { cosineSimilarity } from './domain.mjs';

export class OllamaClient {
  constructor(baseUrl, defaultModel = '') { this.baseUrl = baseUrl; this.defaultModel = defaultModel; }

  async models() {
    const response = await fetch(`${this.baseUrl}/api/tags`, { signal: AbortSignal.timeout(3500) });
    if (!response.ok) throw new Error(`Ollama ha risposto ${response.status}`);
    const data = await response.json();
    return (data.models || []).map(model => ({ name: model.name, size: model.size, modified_at: model.modified_at }));
  }

  async status() {
    try { const models = await this.models(); return { online: true, models }; }
    catch (error) { return { online: false, models: [], error: 'Ollama non è avviato. Avvialo sul PC e premi “Riprova collegamento”.' }; }
  }

  async chat({ prompt, model, system = '', images = [] }) {
    const selected = model || this.defaultModel;
    if (!selected) throw new Error('Seleziona prima un modello Ollama nelle impostazioni.');
    const messages = [];
    if (system) messages.push({ role: 'system', content: system });
    messages.push({ role: 'user', content: prompt, ...(images.length ? { images } : {}) });
    const response = await fetch(`${this.baseUrl}/api/chat`, {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ model: selected, stream: false, messages }), signal: AbortSignal.timeout(120000)
    });
    if (!response.ok) throw new Error(`Errore Ollama ${response.status}: ${await response.text()}`);
    const data = await response.json();
    return data.message?.content || '';
  }

  async extract(text, model, images = []) {
    const system = `Sei l'assistente locale del CRM immobiliare F1. Estrai solo dati esplicitamente presenti. Non inventare mai cognomi, telefoni, civici, prezzi o date. Rispondi esclusivamente con JSON valido nella forma {"records":[{"first_name":"","last_name":"","phone":"","email":"","comune":"","street":"","civic":"","full_address":"","property_type":"","current_price":null,"source":"","source_url":"","seller_signal":"","contact_status":"Da contattare","next_action":"","callback_at":null,"original_note":"","priority":"Media","confidence":0}],"warnings":[]}. confidence è tra 0 e 1.`;
    const raw = await this.chat({ model, system, images, prompt: `Analizza questo contenuto:\n\n${String(text).slice(0, 30000)}` });
    const jsonMatch = raw.match(/\{[\s\S]*\}/);
    if (!jsonMatch) throw new Error('Ollama non ha restituito JSON valido.');
    const parsed = JSON.parse(jsonMatch[0]);
    if (!Array.isArray(parsed.records)) throw new Error('Lo schema JSON di Ollama non contiene records.');
    return parsed;
  }

  async embed(text, model) {
    const selected = model || this.defaultModel;
    if (!selected) return [];
    const response = await fetch(`${this.baseUrl}/api/embed`, {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ model: selected, input: text }), signal: AbortSignal.timeout(120000)
    });
    if (!response.ok) return [];
    const data = await response.json();
    return data.embeddings?.[0] || [];
  }

  async answer(question, chunks, model) {
    const queryEmbedding = await this.embed(question, model);
    const terms = question.toLowerCase().split(/\W+/).filter(term => term.length > 2);
    const ranked = chunks.map(chunk => {
      const embedding = chunk.embedding_json ? JSON.parse(chunk.embedding_json) : [];
      const vectorScore = queryEmbedding.length ? cosineSimilarity(queryEmbedding, embedding) : 0;
      const lexical = terms.filter(term => chunk.content.toLowerCase().includes(term)).length / Math.max(terms.length, 1);
      return { ...chunk, score: vectorScore || lexical };
    }).sort((a, b) => b.score - a.score).slice(0, 6);
    const context = ranked.map((chunk, index) => `[Fonte ${index + 1}: ${chunk.source_name}, sezione ${chunk.chunk_index + 1}]\n${chunk.content}`).join('\n\n');
    const answer = await this.chat({ model, system: 'Rispondi in italiano usando soltanto le fonti fornite. Se il dato manca, dichiaralo. Cita le fonti come [Fonte N].', prompt: `Domanda: ${question}\n\nFonti:\n${context || 'Nessuna fonte disponibile.'}` });
    return { answer, sources: ranked.map(({ source_name, chunk_index, score }) => ({ source_name, section: chunk_index + 1, score })) };
  }
}
