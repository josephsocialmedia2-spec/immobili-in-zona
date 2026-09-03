(()=>{
  const SRC='data/cadastral_enrichment.csv';
  const esc=s=>String(s||'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
  function csv(text){
    let rows=[],r=[],v='',q=false;
    for(let i=0;i<text.length;i++){
      const c=text[i],n=text[i+1];
      if(c==='"'){if(q&&n==='"'){v+='"';i++;}else q=!q;}
      else if(c===','&&!q){r.push(v);v='';}
      else if((c==='\n'||c==='\r')&&!q){if(c==='\r'&&n==='\n')i++;r.push(v);v='';if(r.some(x=>x!==''))rows.push(r);r=[];}
      else v+=c;
    }
    if(v||r.length){r.push(v);rows.push(r);}
    if(!rows.length)return[];
    const h=rows.shift().map(x=>x.replace(/^\uFEFF/,''));
    return rows.map(a=>Object.fromEntries(h.map((k,i)=>[k,a[i]||''])));
  }
  function addStyle(){
    const s=document.createElement('style');
    s.textContent=`
      .seller-row.novita-row{outline:2px solid #39f28a;outline-offset:-2px;background:#102218}
      .novita-badge{display:inline-block;margin-top:5px;padding:4px 7px;border-radius:999px;background:#39f28a;color:#07100a;font-size:10px;font-weight:900}
      .catasto-ok{display:block;margin-top:6px;padding:5px 7px;border-radius:7px;background:#173922;color:#9ce8ad;font-size:10px;font-weight:800}
      .catasto-warn{display:block;margin-top:6px;padding:5px 7px;border-radius:7px;background:#3a3218;color:#e9d481;font-size:10px;font-weight:800}
      .novita-live{margin:16px 0;padding:14px;border:2px solid #39f28a;border-radius:13px;background:#0d1d12}
      .novita-live h2{margin:0 0 4px}.novita-live-grid{display:grid;gap:8px;margin-top:10px}
      .novita-live-card{padding:10px;border:1px solid #2d5c39;border-radius:10px;background:#101710}
      .novita-live-card b{color:#9ce8ad}.novita-live-card a{font-weight:800}
    `;
    document.head.appendChild(s);
  }
  function parcelLabel(x){
    if(x.CATASTO_LOCAL_ID){
      const fp=[x.FOGLIO_RAW&&`foglio ${x.FOGLIO_RAW}`,x.PARTICELLA&&`particella ${x.PARTICELLA}`].filter(Boolean).join(' · ');
      return `<span class="catasto-ok">MAPPALE VERIFICATO${fp?' · '+esc(fp):''}<br>${esc(x.CATASTO_LOCAL_ID)}</span>`;
    }
    if(x.TARGET_RICERCA==='SI')return `<span class="catasto-warn">CATASTO: ${esc(x.STATO_RICERCA||'DA VERIFICARE')}</span>`;
    return '';
  }
  async function run(){
    try{
      const r=await fetch(SRC+'?t='+Date.now(),{cache:'no-store'});if(!r.ok)return;
      const data=csv(await r.text());if(!data.length)return;
      addStyle();
      const byId=new Map(data.filter(x=>x.MASTER_660_ID).map(x=>[String(x.MASTER_660_ID),x]));
      document.querySelectorAll('.seller-row').forEach(tr=>{
        const x=byId.get(String(tr.dataset.masterId||''));if(!x)return;
        if(x.NOVITA==='SI'){
          tr.classList.add('novita-row');
          const first=tr.cells[0];if(first&&!first.querySelector('.novita-badge'))first.insertAdjacentHTML('beforeend','<br><span class="novita-badge">NOVITÀ</span>');
        }
        const addr=tr.cells[10];if(addr&&!addr.querySelector('.catasto-ok,.catasto-warn'))addr.insertAdjacentHTML('beforeend',parcelLabel(x));
      });
      const live=data.filter(x=>x.ORIGINE==='RADAR_LIVE'&&x.NOVITA==='SI'&&x.TARGET_RICERCA==='SI');
      if(live.length){
        const panel=document.createElement('section');panel.className='novita-live';
        panel.innerHTML=`<h2>NOVITÀ RADAR LIVE · ${live.length}</h2><div class="subtitle">Nuovi segnali: ricerca catastale avviata nello stesso ciclo.</div><div class="novita-live-grid">${live.map(x=>`<div class="novita-live-card"><b>${esc(x.COMUNE)} · ${esc(x.TIPOLOGIA)}</b><br>${esc(x.TITOLO)}<br>${esc(x.INDIRIZZO||'INDIRIZZO DA VERIFICARE')}${parcelLabel(x)}${x.URL_SEGNALE?`<br><a href="${esc(x.URL_SEGNALE)}" target="_blank" rel="noopener">APRI SEGNALE</a>`:''}</div>`).join('')}</div>`;
        const cards=document.querySelector('.cards');(cards||document.body.firstChild).parentNode.insertBefore(panel,cards||document.body.firstChild);
      }
    }catch(e){console.warn('F1 cadastral overlay',e);}
  }
  run();
})();
