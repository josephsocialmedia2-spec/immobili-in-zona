(() => {
  'use strict';
  const section = document.querySelector('[data-case247-properties]');
  if (!section) return;
  const grid = section.querySelector('.case247-property-grid');
  const status = section.querySelector('[role=status]');
  const money = new Intl.NumberFormat('it-IT', {style:'currency',currency:'EUR',maximumFractionDigits:0});
  const node = (tag, cls, text) => { const e=document.createElement(tag); if(cls)e.className=cls; if(text!==undefined)e.textContent=text; return e; };
  fetch('https://josephsocialmedia2-spec.github.io/joseph-link-in-bio-Copia/immobili/catalogo.json', {cache:'no-cache'})
    .then(response => {if(!response.ok)throw new Error('Catalogo non disponibile');return response.json();})
    .then(payload => {
      if (!Array.isArray(payload.items)) throw new Error('Catalogo non valido');
      const list=payload.items.filter(item=>section.dataset.case247Properties!=='business'||item.category==='Impresa').sort((a,b)=>String(b.published_at||'').localeCompare(String(a.published_at||''))).slice(0,4);
      grid.replaceChildren();
      for (const item of list) {
        const article=node('article'),photo=node('a','case247-photo');photo.href=item.url;photo.target='_blank';photo.rel='noopener noreferrer';
        const img=node('img');img.alt=item.title;img.loading='lazy';if(item.image){const url=new URL(item.image);url.searchParams.set('width','800');img.src=url.href;}photo.append(img);
        img.onerror=()=>{img.remove();photo.append(node('span','','Foto sul sito del partner'));};
        const info=node('div','case247-property-info'),source=node('div','case247-property-source');
        const link=node('a','','Vedi immobile su La Sacra ↗');link.href=item.url;link.target='_blank';link.rel='noopener noreferrer';
        source.append(node('span','','Partner · La Sacra Immobiliare'),link);
        info.append(node('div','case247-price',item.price===null?'Prezzo su richiesta':money.format(item.price)),node('h3','',item.title.charAt(0)+item.title.slice(1).toLowerCase()),source);article.append(photo,info);grid.append(article);
      }
      status.textContent='Catalogo aggiornato il '+new Date(payload.last_success_at).toLocaleString('it-IT',{timeZone:'Europe/Rome',dateStyle:'short',timeStyle:'short'});
    }).catch(()=>{status.textContent='Consulta gli immobili disponibili nel catalogo completo.';});
})();
