(() => {
  const DEST = 'https://josephsocialmedia2-spec.github.io/launcher-dashboard/telefonate-oggi.html';
  const rows = [...document.querySelectorAll('.seller-row')];
  let added = 0;

  rows.forEach(row => {
    const cells = row.querySelectorAll('td');
    if (cells.length < 15) return;

    const master = (row.dataset.masterId || cells[0].textContent || '').trim();
    const comune = (row.dataset.comune || cells[6].textContent || '').trim();
    const indirizzo = (cells[10].textContent || '').trim();
    const actions = cells[14].querySelector('.actions') || cells[14];
    const source = cells[14].querySelector('a[href^="http"]');
    const sourceUrl = source ? source.href : '';

    if (!comune || !indirizzo || /DA VERIFICARE/i.test(indirizzo)) return;
    if (actions.querySelector('.microzone-call')) return;

    const qs = new URLSearchParams({ master, comune, indirizzo });
    if (sourceUrl) qs.set('url', sourceUrl);

    const a = document.createElement('a');
    a.className = 'remote microzone-call';
    a.href = `${DEST}?${qs.toString()}`;
    a.target = '_blank';
    a.rel = 'noopener';
    a.textContent = 'TELEFONI MICROZONA';
    a.style.background = '#234b63';
    actions.appendChild(a);
    added++;
  });

  document.documentElement.dataset.microzoneLinks = String(added);
})();
