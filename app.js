'use strict';
const $ = id => document.getElementById(id);

function mb(n) { return (n / 1048576).toFixed(1).replace('.', ',') + ' MB'; }
function fara(s) { return (s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase(); }
function pad3(n) { return String(n).padStart(3, '0'); }
const mem = {
  get(k, d) { try { const v = localStorage.getItem('rs.' + k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem('rs.' + k, JSON.stringify(v)); } catch (e) { } }
};

let anuntT = 0;
function anunt(t) {
  const el = $('anunt');
  el.textContent = '';
  clearTimeout(anuntT);
  anuntT = setTimeout(() => { el.textContent = t; }, 60);
}
function alerta(t) { $('alerta').textContent = ''; setTimeout(() => { $('alerta').textContent = t; }, 60); }

async function api(cale, corp) {
  const r = await fetch(cale, corp === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corp) });
  let d;
  try { d = await r.json(); } catch (e) { throw new Error('Răspuns greșit de la aplicație.'); }
  if (!r.ok) throw new Error(d.eroare || 'Eroare');
  return d;
}
function q(o) { return Object.entries(o).map(([k, v]) => k + '=' + encodeURIComponent(v)).join('&'); }

function umple(sel, optiuni, valoare) {
  sel.innerHTML = '';
  for (const [v, t] of optiuni) {
    const o = document.createElement('option'); o.value = v; o.textContent = t; sel.appendChild(o);
  }
  if (valoare !== undefined && optiuni.some(o => o[0] === valoare)) sel.value = valoare;
}
function linii(ul, L) {
  ul.innerHTML = '';
  for (const t of L) { const li = document.createElement('li'); li.textContent = t || ' '; ul.appendChild(li); }
}

// ------------------------------------------------------------------ lucrări în fundal
let lucrez = false;
async function lucrare(cale, corp, rezUl, rezTitlu, dupa) {
  if (lucrez) { alerta('Încă lucrez la ceva. Așteaptă să termin.'); return; }
  let jid;
  try { jid = (await api(cale, corp)).job; } catch (e) { alerta(e.message); return; }
  lucrez = true;
  anunt('Se lucrează.');
  let ultim = 0, mesaj = '';
  const pas = async () => {
    let j;
    try { j = await api('/api/job?id=' + jid); } catch (e) { lucrez = false; alerta(e.message); return; }
    if (j.stare === 'lucrez') {
      const p = Math.floor(j.procent / 10) * 10;
      if (p > ultim || (j.mesaj && j.mesaj !== mesaj)) {
        ultim = Math.max(ultim, p); mesaj = j.mesaj;
        anunt('Se lucrează: ' + ultim + ' la sută. ' + (j.mesaj || ''));
      }
      setTimeout(pas, 700);
      return;
    }
    lucrez = false;
    linii(rezUl, j.jurnal);
    if (j.stare === 'gata') {
      anunt('Gata. Rezultatul e mai jos.');
      setTimeout(() => rezTitlu.focus(), 1200);
      if (dupa) dupa();
    } else {
      alerta('Nu a mers: ' + j.eroare);
      setTimeout(() => rezTitlu.focus(), 1500);
    }
  };
  setTimeout(pas, 500);
}

// ------------------------------------------------------------------ o secțiune (Kronos sau Pa)
function Sectiune(cfg) {
  const P = cfg.p, B = cfg.baza;
  const el = n => $(P + '-' + n);
  const S = { seturi: [], elemente: [], bifate: new Map() };

  const cheie = e => e.tip + '|' + e.banca + '|' + e.nr;
  const pozitie = e => cfg.kronos ? e.banca + ' ' + pad3(e.nr) : e.banca + ' ' + (e.nr + 1);

  async function incarcaSeturi() {
    try { S.seturi = await api(B + '/seturi'); } catch (e) { alerta(e.message); return; }
    const opt = S.seturi.map(s => [s.id, s.nume]);
    umple(el('sursa'), opt, mem.get(P + '.sursa'));
    const ot = cfg.kronos ? opt : [['', 'Un set nou gol (doar cu ce aduc)']].concat(opt);
    const pref = (S.seturi.find(x => /set ?22/i.test(x.nume)) || S.seturi.find(x => x.id !== el('sursa').value) || S.seturi[0] || {}).id || '';
    const vt = mem.get(P + '.tinta', null);
    umple(el('tinta'), ot, ot.some(o => o[0] === vt) ? vt : (cfg.kronos ? pref : ''));
    if (!S.seturi.length) {
      linii(el('rez'), ['Nu am găsit niciun set. Vezi în Setări folderele în care caut.']);
      return;
    }
    numeImplicit();
    await incarcaBanci();
    await incarcaDest();
  }

  function numeTinta() {
    const s = S.seturi.find(x => x.id === el('tinta').value);
    return s ? s.nume : 'Set nou';
  }
  function numeImplicit() {
    const d = new Date();
    const luni = ['ian', 'feb', 'mar', 'apr', 'mai', 'iun', 'iul', 'aug', 'sep', 'oct', 'nov', 'dec'];
    el('nume').value = numeTinta() + ' ' + d.getDate() + ' ' + luni[d.getMonth()];
  }

  async function incarcaBanci() {
    const s = el('sursa').value, tip = el('tip').value;
    if (!s) return;
    anunt('Se încarcă băncile.');
    let L;
    try { L = await api(B + '/banci?' + q({ set: s, tip })); } catch (e) { alerta(e.message); return; }
    const opt = L.filter(b => b.ocupate > 0).map(b => [b.banca, b.banca + ', ' + cfg.cate(b.ocupate, tip) + (b.exi ? ', EXi' : '')]);
    if (!opt.length) opt.push(['', 'nicio bancă cu ceva în ea']);
    umple(el('banca'), opt, mem.get(P + '.banca.' + tip));
    await incarcaLista(false);
  }

  async function incarcaLista(anuntaCate) {
    const s = el('sursa').value, tip = el('tip').value, banca = el('banca').value;
    el('lista').innerHTML = '';
    S.elemente = [];
    if (!s || !banca) { el('lista-titlu').textContent = 'Lista e goală'; return; }
    anunt('Se încarcă lista.');
    try { S.elemente = await api(B + '/elemente?' + q({ set: s, tinta: el('tinta').value, tip, banca })); }
    catch (e) { alerta(e.message); return; }
    deseneazaLista();
    if (anuntaCate !== false) anunt(el('lista-titlu').textContent);
    else anunt('');
  }

  function eticheta(e) {
    let t = pozitie(e) + ' ' + e.nume + ', ' + mb(e.cost);
    if (e.exi) t += ', EXi';
    if (e.sunete !== undefined) t += ', ' + e.sunete + (e.sunete === 1 ? ' sunet' : ' sunete');
    if (e.note && e.note.length) t += ', ' + e.note.join(', ');
    return t;
  }

  function deseneazaLista() {
    const f = fara(el('cauta').value.trim());
    const L = el('lista');
    L.innerHTML = '';
    let n = 0;
    for (const e of S.elemente) {
      if (f && !fara(e.nume).includes(f)) continue;
      n++;
      const d = document.createElement('div');
      const c = document.createElement('input');
      c.type = 'checkbox'; c.id = P + '-e-' + e.banca + '-' + e.nr;
      c.checked = S.bifate.has(cheie(e));
      c.addEventListener('change', () => bifeaza(e, c.checked));
      const l = document.createElement('label');
      l.htmlFor = c.id; l.textContent = eticheta(e);
      d.appendChild(c); d.appendChild(l); L.appendChild(d);
    }
    const tipN = cfg.numeTip[el('tip').value];
    el('lista-titlu').textContent = n ? (n + ' ' + tipN + ' în ' + el('banca').value + (f ? ' care conțin „' + el('cauta').value.trim() + '”' : '')) : 'Nimic în listă';
  }

  let costNr = 0;
  async function bifeaza(e, da, liniste) {
    const k = cheie(e);
    if (da) S.bifate.set(k, { tip: e.tip, banca: e.banca, nr: e.nr, nume: e.nume });
    else S.bifate.delete(k);
    const nr = ++costNr;
    const r = await actualizeazaBifate();
    if (!r || nr !== costNr || liniste) return;
    if (da) {
      const lin = r.linii.find(x => x.eticheta.startsWith(pozitie(e) + ' '));
      let t = 'Bifat. Costă ' + mb(lin ? lin.cost : e.cost) + '.';
      if (lin && lin.imparte.length) t += ' Împarte sample-uri cu: ' + lin.imparte.join(', ') + '.';
      if (S.bifate.size > 1) t += ' Toate ' + S.bifate.size + ' împreună: ' + mb(r.impreuna) + '.';
      anunt(t);
    } else {
      anunt('Debifat. ' + (S.bifate.size ? 'Rămân ' + S.bifate.size + ', împreună ' + mb(r.impreuna) + '.' : 'Nu mai e nimic bifat.'));
    }
  }

  async function actualizeazaBifate() {
    const alese = [...S.bifate.values()];
    el('bifate-titlu').textContent = 'Ce am bifat (' + alese.length + ')';
    if (!alese.length) { linii(el('bifate'), ['Nimic.']); return { linii: [], impreuna: 0, separat: 0 }; }
    let r;
    try { r = await api(B + '/cost', { sursa: el('sursa').value, tinta: el('tinta').value, elemente: alese }); }
    catch (e) { alerta(e.message); return null; }
    const L = r.linii.map(l => l.eticheta + ', ' + mb(l.cost) + (l.imparte.length ? ', împarte sample-uri cu: ' + l.imparte.join(', ') : ''));
    L.push('Toate împreună: ' + mb(r.impreuna) + (r.separat !== r.impreuna ? ' (luate separat ar fi ' + mb(r.separat) + ', dar au sample-uri comune)' : '') + '.');
    linii(el('bifate'), L);
    return r;
  }

  async function bifTot(da) {
    const f = fara(el('cauta').value.trim());
    let n = 0;
    for (const e of S.elemente) {
      if (f && !fara(e.nume).includes(f)) continue;
      if (da) S.bifate.set(cheie(e), { tip: e.tip, banca: e.banca, nr: e.nr, nume: e.nume });
      else S.bifate.delete(cheie(e));
      n++;
    }
    if (!da) S.bifate.clear();
    deseneazaLista();
    const r = await actualizeazaBifate();
    anunt(da ? 'Am bifat ' + n + '. Toate bifate împreună: ' + (r ? mb(r.impreuna) : '') + '.' : 'Am debifat tot.');
  }

  async function incarcaDest() {
    if (cfg.kronos) {
      const t = el('tinta').value;
      if (!t) return;
      try {
        const pb = await api(B + '/banci?' + q({ set: t, tip: 'prog' }));
        const cb = await api(B + '/banci?' + q({ set: t, tip: 'combi' }));
        const lab = b => [b.banca, b.banca + ', ' + b.ocupate + ' ocupate'];
        const hd = pb.filter(b => b.banca.startsWith('U-') && !b.exi).map(lab);
        umple(el('b-prog'), hd, mem.get('k.b-prog', 'U-A'));
        umple(el('b-timbre'), hd, mem.get('k.b-timbre', 'U-D'));
        umple(el('b-combi'), cb.filter(b => b.banca.startsWith('U-')).map(lab), mem.get('k.b-combi', 'U-A'));
      } catch (e) { alerta(e.message); }
    } else {
      const tip = el('tip').value;
      let L;
      try { L = await api(B + '/banci?' + q({ set: el('tinta').value, tip })); } catch (e) { alerta(e.message); return; }
      umple(el('b-dest'), [['', 'Aceeași bancă ca în setul de unde iau']].concat(L.map(b => [b.banca, b.banca + ', ' + cfg.cate(b.ocupate, tip)])), '');
    }
  }

  function corpComun() {
    const nou = el('salv-nou').checked;
    return { sursa: el('sursa').value, tinta: el('tinta').value, elemente: [...S.bifate.values()], in_loc: !nou, nume_nou: el('nume').value };
  }

  async function dupaLucru() {
    S.bifate.clear();
    const s = el('sursa').value, t = el('tinta').value;
    await incarcaSeturi();
    if (S.seturi.some(x => x.id === s)) el('sursa').value = s;
    if ([...el('tinta').options].some(o => o.value === t)) el('tinta').value = t;
    await incarcaBanci();
    actualizeazaBifate();
  }

  // --- evenimente
  el('sursa').addEventListener('change', async () => {
    mem.set(P + '.sursa', el('sursa').value);
    S.bifate.clear(); actualizeazaBifate();
    await incarcaBanci();
  });
  el('tinta').addEventListener('change', async () => {
    mem.set(P + '.tinta', el('tinta').value);
    numeImplicit();
    await incarcaDest();
    await incarcaLista(false);
    actualizeazaBifate();
  });
  el('tip').addEventListener('change', async () => { await incarcaBanci(); if (!cfg.kronos) incarcaDest(); });
  el('banca').addEventListener('change', () => { mem.set(P + '.banca.' + el('tip').value, el('banca').value); incarcaLista(); });
  let cautT = 0;
  el('cauta').addEventListener('input', () => {
    clearTimeout(cautT);
    cautT = setTimeout(() => { deseneazaLista(); anunt(el('lista-titlu').textContent); }, 500);
  });
  el('bif-tot').addEventListener('click', () => bifTot(true));
  el('debif-tot').addEventListener('click', () => bifTot(false));
  for (const r of [el('salv-nou'), el('salv-loc')]) r.addEventListener('change', () => { el('nume-rand').hidden = !el('salv-nou').checked; });
  for (const id of ['b-prog', 'b-timbre', 'b-combi']) if (el(id)) el(id).addEventListener('change', () => mem.set(P + '.' + id, el(id).value));

  el('adu').addEventListener('click', () => {
    if (!S.bifate.size) { alerta('Nu ai bifat nimic.'); return; }
    const c = corpComun();
    if (cfg.kronos) {
      if (c.in_loc && !confirm('Scriu direct în ' + numeTinta() + '. Ai backup? Apasă OK ca să continui.')) return;
      Object.assign(c, { sw_octava: el('sw').checked, banca_prog: el('b-prog').value, banca_combi: el('b-combi').value, banca_timbre: el('b-timbre').value });
    } else {
      if (c.in_loc && !c.tinta) { alerta('Ca să scriu direct, alege un set în care pun.'); return; }
      if (c.in_loc && !confirm('Scriu direct în ' + numeTinta() + '. Ai backup? Apasă OK ca să continui.')) return;
      const b = {}; b[el('tip').value] = el('b-dest').value;
      Object.assign(c, { peste: el('peste').checked, cu_sunete: el('cu-sunete').checked, banca: b });
    }
    lucrare(B + '/transfer', c, el('rez'), el('rez-titlu'), dupaLucru);
  });

  if (!cfg.kronos) {
    el('raport').addEventListener('click', () => lucrare(B + '/raport', { sursa: el('sursa').value }, el('rez'), el('rez-titlu')));
    el('verifica').addEventListener('click', () => lucrare(B + '/verifica', { sursa: el('sursa').value }, el('rez'), el('rez-titlu')));
    el('curata').addEventListener('click', () => {
      const alese = [...S.bifate.values()].filter(e => e.tip === 'sunet');
      const c = corpComun(); c.elemente = alese.length ? alese : [{ tip: 'nimic', banca: '', nr: 0 }];
      if (c.in_loc && !confirm('Curăț direct setul de unde iau. Ai backup? Apasă OK ca să continui.')) return;
      if (!c.in_loc) c.nume_nou = (S.seturi.find(x => x.id === c.sursa) || { nume: 'Set' }).nume + ' curatat';
      lucrare(B + '/curatenie', c, el('rez'), el('rez-titlu'), dupaLucru);
    });
  }

  return { incarcaSeturi, actualizeazaBifate };
}

const kronos = Sectiune({
  p: 'k', baza: '/api/kronos', kronos: true,
  numeTip: { combi: 'combi-uri', prog: 'programe' },
  cate: (n, tip) => n + ' ocupate'
});
const pa = Sectiune({
  p: 'p', baza: '/api/pa', kronos: false,
  numeTip: { sunet: 'sunete', perf: 'performance-uri', style: 'style-uri', pad: 'pad-uri' },
  cate: (n, tip) => n ? n + ' ' + ({ sunet: 'sunete', perf: 'performance-uri', style: 'style-uri', pad: 'pad-uri' }[tip]) : 'goală'
});

// ------------------------------------------------------------------ taburi
const taburi = [...document.querySelectorAll('[role=tab]')];
function arataTab(t, focus) {
  for (const x of taburi) {
    const da = x === t;
    x.setAttribute('aria-selected', da ? 'true' : 'false');
    x.tabIndex = da ? 0 : -1;
    $(x.getAttribute('aria-controls')).hidden = !da;
  }
  if (focus) t.focus();
  mem.set('tab', t.id);
}
taburi.forEach((t, i) => {
  t.addEventListener('click', () => arataTab(t, true));
  t.addEventListener('keydown', ev => {
    let j = null;
    if (ev.key === 'ArrowRight') j = (i + 1) % taburi.length;
    if (ev.key === 'ArrowLeft') j = (i + taburi.length - 1) % taburi.length;
    if (ev.key === 'Home') j = 0;
    if (ev.key === 'End') j = taburi.length - 1;
    if (j !== null) { ev.preventDefault(); arataTab(taburi[j], true); }
  });
});
document.addEventListener('keydown', ev => {
  if (ev.altKey && !ev.ctrlKey && ['1', '2', '3'].includes(ev.key)) {
    ev.preventDefault(); arataTab(taburi[+ev.key - 1], true);
  }
});

// ------------------------------------------------------------------ setări
let SET = null;
function deseneazaSetari() {
  for (const [k, ul] of [['kronos_dirs', $('s-kronos')], ['pa_dirs', $('s-pa')]]) {
    ul.innerHTML = '';
    for (const d of SET[k]) {
      const li = document.createElement('li');
      li.appendChild(document.createTextNode(d + ' '));
      const b = document.createElement('button');
      b.textContent = 'Scoate'; b.setAttribute('aria-label', 'Scoate ' + d);
      b.addEventListener('click', async () => { SET[k] = SET[k].filter(x => x !== d); await salveazaSetari('Am scos folderul.'); });
      li.appendChild(b); ul.appendChild(li);
    }
    if (!SET[k].length) { const li = document.createElement('li'); li.textContent = 'Niciun folder.'; ul.appendChild(li); }
  }
  $('s-kronos-out').textContent = 'Seturile Kronos noi: ' + SET.kronos_out;
  $('s-pa-out').textContent = 'Seturile Pa noi: ' + SET.pa_out;
}
async function salveazaSetari(mesaj) {
  try { SET = await api('/api/setari/salveaza', SET); } catch (e) { alerta(e.message); return; }
  deseneazaSetari(); anunt(mesaj);
  kronos.incarcaSeturi(); pa.incarcaSeturi();
}
async function alege(titlu) {
  anunt('Se deschide fereastra de ales folderul.');
  try { return (await api('/api/alege_folder', { titlu })).cale; } catch (e) { alerta(e.message); return null; }
}
$('s-kronos-add').addEventListener('click', async () => { const c = await alege('Folder cu seturi Kronos'); if (c) { SET.kronos_dirs.push(c); salveazaSetari('Am adăugat folderul.'); } });
$('s-pa-add').addEventListener('click', async () => { const c = await alege('Folder cu seturi Pa'); if (c) { SET.pa_dirs.push(c); salveazaSetari('Am adăugat folderul.'); } });
$('s-kronos-out-b').addEventListener('click', async () => { const c = await alege('Unde fac seturile Kronos noi'); if (c) { SET.kronos_out = c; salveazaSetari('Am schimbat folderul.'); } });
$('s-pa-out-b').addEventListener('click', async () => { const c = await alege('Unde fac seturile Pa noi'); if (c) { SET.pa_out = c; salveazaSetari('Am schimbat folderul.'); } });
$('s-reincarca').addEventListener('click', async () => { await kronos.incarcaSeturi(); await pa.incarcaSeturi(); anunt('Am căutat din nou seturile.'); });
$('s-inchide').addEventListener('click', async () => {
  try { await api('/api/inchide', {}); } catch (e) { }
  document.body.innerHTML = '<h1>Synth Set Manager s-a închis.</h1><p>Poți închide fereastra.</p>';
});

// ------------------------------------------------------------------ pornire
(async () => {
  try { SET = await api('/api/setari'); deseneazaSetari(); } catch (e) { alerta('Aplicația nu răspunde. Pornește din nou Synth Set Manager.'); return; }
  const t = taburi.find(x => x.id === mem.get('tab', 'tab-kronos')) || taburi[0];
  arataTab(t, false);
  await kronos.incarcaSeturi();
  await pa.incarcaSeturi();
  kronos.actualizeazaBifate(); pa.actualizeazaBifate();
  anunt('Synth Set Manager e gata.');
  setInterval(() => api('/api/ping').catch(() => { }), 30000);
})();
