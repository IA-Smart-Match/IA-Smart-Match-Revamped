/* Direction B: Friendly Tech. Mockup behaviour for owner review, not app code.
   No libraries. Web Animations API + CSS only. */
(() => {
  'use strict';

  /* ---------- Helpers, storage (per-viewer conveniences only; guarded) ---------- */
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const html = document.documentElement;
  const store = {
    get(k, d = null) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* private mode: fine */ } },
    del(k) { try { localStorage.removeItem(k); } catch { /* ignore */ } },
  };
  const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const qs = new URLSearchParams(location.search);
  const mqRM = matchMedia('(prefers-reduced-motion: reduce)');
  const reduced = () => html.classList.contains('rm') || mqRM.matches;
  const TOUR_KEY = 'smartmatch.exercise.tour.v1';
  const DOCK_KEY = 'smartmatch.mockup-b.dock';

  const A = '../../mockup/assets/';
  const POSE = { guide: A + 'pose1-guide.webp', chill: A + 'pose2-chill.webp', explore: A + 'pose3-explore.webp', worker: A + 'pose4-worker.webp', celebrate: A + 'pose5-celebrate.webp' };
  const FACE = { happy: A + 'face1-happy.webp', surprised: A + 'face2-surprised.webp', curious: A + 'face3-curious.webp', laugh: A + 'face4-laugh.webp', calm: A + 'face5-calm.webp' };
  const icon = (id, cls = 'icon') => `<svg class="${cls}" aria-hidden="true"><use href="#${id}"/></svg>`;

  /* ---------- Fictional data ---------- */
  const FACTORS = ['same major', 'said they are interested in this topic', 'career goal fits this event', 'went to similar events before'];
  const YEAR_RANK = { Senior: 4, Junior: 3, Sophomore: 2, Freshman: 1 };
  const INFO = { 'completed card': 2, 'major plus events attended': 1, 'major only': 0 };
  const CIS = 'Computer Information Systems', IBM = 'International Business & Marketing', ACC = 'Accounting', MHR = 'Management & Human Resources', TOM = 'Technology & Operations Management', FIN = 'Finance, Real Estate & Law';
  const MC = 'completed card', ME = 'major plus events attended', MO = 'major only';
  // [name, major, year, marker, [same major, interested, career fits, similar events]]
  const PEOPLE = [
    ['Maya Tran', CIS, 'Senior', MC, [1, 1, 1, 0]], ['Daniel Okafor', IBM, 'Senior', MC, [1, 0, 1, 0]],
    ['Priya Patel', CIS, 'Junior', ME, [1, 0, 0, 1]], ['Jordan Kim', CIS, 'Senior', MO, [1, 0, 0, 0]],
    ['Alexis Rivera', CIS, 'Junior', MO, [1, 0, 0, 0]], ['Ethan Nguyen', IBM, 'Senior', ME, [1, 0, 0, 1]],
    ['Sofia Morales', TOM, 'Senior', MC, [0, 1, 1, 0]], ['Marcus Chen', IBM, 'Junior', MO, [1, 0, 0, 0]],
    ['Hannah Lee', IBM, 'Sophomore', MO, [1, 0, 0, 0]], ['Diego Garcia', ACC, 'Senior', ME, [0, 0, 0, 1]],
    ['Chloe Brooks', MHR, 'Junior', MC, [0, 1, 0, 1]], ['Ravi Shah', TOM, 'Senior', MC, [0, 1, 1, 1]],
    ['Grace Park', ACC, 'Junior', MC, [0, 1, 0, 0]], ['Tyler Reyes', CIS, 'Sophomore', ME, [1, 0, 0, 1]],
    ['Leila Haddad', IBM, 'Junior', MC, [1, 1, 0, 0]], ['Brandon Cole', MHR, 'Senior', ME, [0, 0, 0, 1]],
    ['Nina Vasquez', TOM, 'Sophomore', MC, [0, 1, 1, 0]], ['Kevin Yu', ACC, 'Senior', MO, [0, 0, 0, 0]],
    ['Aaliyah Johnson', CIS, 'Sophomore', MO, [1, 0, 0, 0]], ['Omar Farouk', IBM, 'Senior', MO, [1, 0, 0, 0]],
    ['Camila Ortiz', IBM, 'Junior', MC, [1, 0, 0, 0]], ['Hiro Tanaka', CIS, 'Junior', MO, [1, 0, 0, 0]],
    ['Fatima Rahman', FIN, 'Senior', MC, [0, 1, 0, 0]], ['Luis Mendoza', IBM, 'Sophomore', MO, [1, 0, 0, 0]],
    ['Jasmine Wright', CIS, 'Senior', MC, [1, 0, 1, 0]], ['Minh Pham', TOM, 'Junior', ME, [0, 0, 0, 1]],
    ['Isabella Cruz', IBM, 'Senior', ME, [1, 0, 0, 0]], ['Arjun Mehta', CIS, 'Junior', ME, [1, 0, 0, 1]],
    ['Sienna Walsh', MHR, 'Sophomore', MC, [0, 1, 1, 0]], ['Mateo Silva', IBM, 'Junior', MO, [1, 0, 0, 0]],
    ['Yuna Choi', ACC, 'Junior', ME, [0, 0, 0, 1]], ['Andre Thompson', CIS, 'Sophomore', MO, [1, 0, 0, 0]],
    ['Zoe Martinez', IBM, 'Sophomore', MO, [1, 0, 0, 0]], ['Gabriel Flores', TOM, 'Senior', MO, [0, 0, 0, 0]],
    ['Riya Kapoor', FIN, 'Junior', ME, [0, 0, 0, 1]], ['Samuel Adeyemi', CIS, 'Freshman', MO, [1, 0, 0, 0]],
    ['Hana Yoshida', IBM, 'Freshman', MO, [1, 0, 0, 0]], ['Victor Alvarez', MHR, 'Junior', MO, [0, 0, 0, 0]],
    ['Elena Petrova', CIS, 'Freshman', MO, [1, 0, 0, 0]], ['Jamal Carter', IBM, 'Freshman', MO, [1, 0, 0, 0]],
    ['Lucy Huang', ACC, 'Freshman', MO, [0, 0, 0, 0]], ['Noah Bennett', FIN, 'Sophomore', MO, [0, 0, 0, 0]],
    ['Olivia Bautista', CIS, 'Senior', MO, [1, 0, 0, 0]], ['Kenji Watanabe', IBM, 'Senior', MO, [1, 0, 0, 0]],
    ['Rosa Delgado', CIS, 'Junior', MO, [1, 0, 0, 0]], ['Tariq Hassan', IBM, 'Junior', MO, [1, 0, 0, 0]],
    ['Megan Foster', CIS, 'Senior', MO, [1, 0, 0, 0]], ['Eduardo Ramos', IBM, 'Senior', MO, [1, 0, 0, 0]],
    ['Anika Sharma', CIS, 'Junior', MO, [1, 0, 0, 0]], ['Brian Lam', IBM, 'Junior', MO, [1, 0, 0, 0]],
    ['Carmen Vega', CIS, 'Senior', ME, [1, 0, 0, 0]], ['Wei Zhang', IBM, 'Senior', ME, [1, 0, 0, 0]],
    ['Destiny Harris', CIS, 'Junior', ME, [1, 0, 0, 0]], ['Paolo Rossi', IBM, 'Sophomore', MO, [1, 0, 0, 0]],
    ['Julia Novak', MHR, 'Senior', MC, [0, 1, 1, 0]], ['Marco Esposito', FIN, 'Junior', MC, [0, 1, 1, 0]],
    ['Aisha Bello', ACC, 'Senior', MC, [0, 1, 1, 1]], ['Kyle Nakamura', TOM, 'Junior', MC, [0, 1, 0, 1]],
    ['Lena Fischer', MHR, 'Junior', MC, [0, 1, 1, 0]], ['Ahmed Karim', FIN, 'Senior', MC, [0, 0, 1, 1]],
    ['Sara Lindqvist', ACC, 'Sophomore', MC, [0, 1, 1, 0]], ['Diana Ochoa', TOM, 'Senior', ME, [0, 0, 0, 1]],
    ['Rahul Iyer', MHR, 'Senior', ME, [0, 0, 0, 1]], ['Tessa Morgan', FIN, 'Junior', MC, [0, 1, 0, 1]],
    ['Jin Park', ACC, 'Junior', MC, [0, 1, 1, 0]], ['Nadia Popescu', TOM, 'Sophomore', MC, [0, 1, 1, 1]],
    ['Chris Holloway', MHR, 'Junior', MC, [0, 1, 0, 0]], ['Imani Brooks', FIN, 'Sophomore', ME, [0, 0, 0, 1]],
  ];
  const ALL_300 = {
    marker: [[MO, 152], [ME, 78], [MC, 70]],
    major: [[ACC, 49], [CIS, 58], [FIN, 32], [IBM, 71], [MHR, 52], [TOM, 38]],
    year: [['Freshman', 62], ['Sophomore', 71], ['Junior', 80], ['Senior', 87]],
  };
  const LIMIT = 30;
  const rankOf = (w) => PEOPLE.map((p, idx) => ({ p, idx, s: p[4].reduce((a, f, i) => a + f * w[i], 0) }))
    .sort((a, b) => b.s - a.s || INFO[b.p[3]] - INFO[a.p[3]] || YEAR_RANK[b.p[2]] - YEAR_RANK[a.p[2]] || a.idx - b.idx)
    .slice(0, LIMIT).map((x) => x.p);
  function reasons(list, w) {
    let majorOnlySeen = false;
    return list.map((p) => {
      const on = FACTORS.filter((_, i) => p[4][i] && w[i] > 0);
      if (!on.length) return 'Nothing on file counted for this event.';
      if (on.length === 1 && on[0] === 'same major') {
        const r = majorOnlySeen ? 'Tied on major; ordered by year.' : 'Same major; nothing else on file.';
        majorOnlySeen = true; return r;
      }
      return `What counted: ${on.join('; ')}.`;
    });
  }

  /* ---------- State ---------- */
  const S = {
    screen: 'team', team: null,
    weights: [0.40, 0.25, 0.25, 0.10],
    saved: [{ name: 'Major first', w: [0.60, 0.15, 0.15, 0.10] }, { name: 'Interests first', w: [0.15, 0.45, 0.25, 0.15] }],
    pickAB: [0, 1], showB: false, showAll: false, loadingHold: false, results: 'locked', finalSetting: 0,
    ask: null, askArmed: null, askRan: false, hints: true, dockLeft: false, visited: new Set(['team']),
  };
  const ORDER = ['team', 'events', 'list', 'compare', 'results', 'asking'];

  /* ---------- Companion: face, hints, menu ---------- */
  const dock = $('#dock'), hint = $('#hint'), dockBtn = $('#dock-btn'), menu = $('#dock-menu');
  const HINTS = {
    team: ['happy', "Pick your team's number to start."],
    events: ['happy', 'Round 1 is Northline Analytics. Start there.'],
    list: ['curious', 'Who is missing from every list? Keep an eye on the pink line.'],
    compare: ['curious', 'Rows in pink are on both lists.'],
    results: ['calm', 'Results open when the instructor says so.'],
    asking: ['curious', 'Each way of asking has a price. Talk it over first.'],
  };
  let hintTimer = 0;
  function setFace(name) { $('#dock-face').src = FACE[name]; }
  function say(text, face = 'happy', ms = 6000) {
    setFace(face);
    if (!S.hints) return;
    hint.textContent = text; hint.hidden = false;
    hint.classList.remove('is-in'); void hint.offsetWidth; hint.classList.add('is-in');
    clearTimeout(hintTimer); hintTimer = setTimeout(() => { hint.hidden = true; setFace('happy'); }, ms);
  }
  const closeMenu = () => { menu.hidden = true; dockBtn.setAttribute('aria-expanded', 'false'); };
  dockBtn.addEventListener('click', () => {
    const open = menu.hidden; menu.hidden = !open; dockBtn.setAttribute('aria-expanded', String(open)); hint.hidden = true;
    if (open) $('button', menu).focus();
  });
  menu.addEventListener('keydown', (e) => {
    const items = $$('button', menu); const i = items.indexOf(document.activeElement);
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); items[(i + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length].focus(); }
    if (e.key === 'Escape') { closeMenu(); dockBtn.focus(); }
  });
  document.addEventListener('click', (e) => { if (!menu.hidden && !dock.contains(e.target)) closeMenu(); });
  $('#m-tour').addEventListener('click', () => { closeMenu(); openTour(0); });
  function applyDock() {
    dock.classList.toggle('is-left', S.dockLeft);
    $('#m-side-label').textContent = S.dockLeft ? 'Move to the right' : 'Move to the left';
    $('#m-mute-label').textContent = S.hints ? 'Turn off hints' : 'Turn on hints';
  }
  $('#m-side').addEventListener('click', () => { S.dockLeft = !S.dockLeft; applyDock(); store.set(DOCK_KEY, { left: S.dockLeft, hints: S.hints }); closeMenu(); dockBtn.focus(); });
  $('#m-mute').addEventListener('click', () => {
    S.hints = !S.hints; applyDock(); store.set(DOCK_KEY, { left: S.dockLeft, hints: S.hints }); closeMenu();
    if (!S.hints) { hint.hidden = true; setFace('calm'); } else say('Hints are back on.', 'happy', 3000);
    dockBtn.focus();
  });

  /* ---------- Screens and rail ---------- */
  function paintRail() {
    const i = ORDER.indexOf(S.screen);
    $$('.step').forEach((b, k) => {
      if (k === i) b.setAttribute('aria-current', 'step'); else b.removeAttribute('aria-current');
      b.classList.toggle('is-done', k < i);
    });
    const steps = $('#steps'); const cur = $$('.step')[i];
    if (cur && steps.offsetHeight > 36) steps.style.setProperty('--progress', String(Math.max(0, (cur.offsetTop + cur.offsetHeight / 2 - 18) / (steps.offsetHeight - 36))));
    $$('#rail-progress i').forEach((d, k) => d.classList.toggle('on', k <= i));
    $('#rail-count').textContent = `${i + 1} of 6`;
    $$('.review__nav button').forEach((b) => { if (b.dataset.go === S.screen) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current'); });
  }
  function showScreen(name, { focus = true, hintOn = true } = {}) {
    if (!ORDER.includes(name)) return;
    S.screen = name;
    $$('.screen').forEach((s) => { s.hidden = s.dataset.screen !== name; });
    document.body.classList.toggle('has-actionbar', !!$(`[data-screen="${name}"] .actionbar`));
    window.scrollTo({ top: 0, behavior: 'instant' });
    paintRail();
    if (name === 'list') renderList(false);
    if (name === 'compare') renderCompare();
    if (name === 'results') renderResults();
    if (name === 'asking') renderAsking();
    if (focus) $(`[data-screen="${name}"] .h1`)?.focus({ preventScroll: true });
    if (hintOn && !tour.open && !(name === 'results' && S.results !== 'locked')) say(HINTS[name][1], HINTS[name][0]);
  }
  document.addEventListener('click', (e) => {
    const go = e.target.closest('[data-go]');
    if (go) { e.preventDefault(); if (tour.open) closeTour('skipped', false); showScreen(go.dataset.go); }
  });

  /* ---------- 1 Team entry ---------- */
  const tiles = $('#tiles');
  for (let n = 1; n <= 6; n++) {
    const b = document.createElement('button');
    b.type = 'button'; b.className = 'tile num'; b.textContent = n; b.setAttribute('role', 'radio');
    b.setAttribute('aria-checked', 'false'); b.setAttribute('aria-label', `Team ${n}`); b.tabIndex = n === 1 ? 0 : -1;
    tiles.appendChild(b);
  }
  function pickTeam(n, focus) {
    S.team = n;
    $$('.tile', tiles).forEach((t, i) => { const on = i + 1 === n; t.setAttribute('aria-checked', String(on)); t.tabIndex = on ? 0 : -1; if (on && focus) t.focus(); });
    const btn = $('#open-team'); btn.setAttribute('aria-disabled', 'false');
    btn.firstChild.textContent = `Open team ${n}'s work`;
    $('#rail-team').hidden = false; $('#rail-team-n').textContent = n; $('#rail-team-n2').textContent = n;
    $('#save-name').value = 'Our own mix';
  }
  tiles.addEventListener('click', (e) => { const t = e.target.closest('.tile'); if (t) pickTeam(Number(t.textContent)); });
  tiles.addEventListener('keydown', (e) => {
    const i = $$('.tile', tiles).indexOf(document.activeElement); if (i < 0) return;
    const d = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
    if (d) { e.preventDefault(); pickTeam(((i + d + 6) % 6) + 1, true); }
    if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); pickTeam(i + 1, true); }
  });
  $('#open-team').addEventListener('click', () => {
    if (!S.team) { say("Pick your team's number first.", 'surprised', 3500); tiles.querySelector('.tile').focus(); return; }
    showScreen('events');
  });
  $$('.event').forEach((c) => c.addEventListener('click', () => showScreen('list')));

  /* ---------- 3 Weights + list ---------- */
  const sliders = $('#sliders');
  FACTORS.forEach((label, i) => {
    const id = `w${i}`;
    const row = document.createElement('div'); row.className = 'w';
    row.innerHTML = `<label for="${id}">${label}</label><div class="w__ctl"><input type="range" id="${id}" min="0" max="1" step="0.05" value="${S.weights[i]}"><input class="w__num" type="text" inputmode="decimal" aria-label="${label}, exact value" value="${S.weights[i].toFixed(2)}"></div>`;
    sliders.appendChild(row);
    const range = $('input[type=range]', row), num = $('.w__num', row);
    const paint = () => range.style.setProperty('--fill', `${range.value * 100}%`);
    paint();
    range.addEventListener('input', () => { S.weights[i] = Number(range.value); num.value = S.weights[i].toFixed(2); paint(); updateTotal(); });
    range.addEventListener('change', rebuild);
    num.addEventListener('change', () => {
      const v = Math.min(1, Math.max(0, Math.round((Number(num.value) || 0) * 20) / 20));
      S.weights[i] = v; range.value = v; num.value = v.toFixed(2); paint(); updateTotal(); rebuild();
    });
  });
  const total = () => S.weights.reduce((a, b) => a + b, 0);
  function updateTotal() {
    $('#total').textContent = `Total weight: ${total().toFixed(2)}`;
    const zero = total() === 0;
    $('#zero-err').hidden = !zero;
    $('#save-btn').setAttribute('aria-disabled', String(zero));
    if (zero) setFace('surprised');
  }
  function syncSliders() {
    $$('.w', sliders).forEach((row, i) => { const r = $('input[type=range]', row); r.value = S.weights[i]; r.style.setProperty('--fill', `${S.weights[i] * 100}%`); $('.w__num', row).value = S.weights[i].toFixed(2); });
    updateTotal();
  }
  const markerChip = (m) => {
    const map = { [MO]: ['major', 'i-circle'], [ME]: ['events', 'i-circle-dot'], [MC]: ['card', 'i-idcard'] };
    const [cls, ic] = map[m] || ['major', 'i-circle'];
    return `<span class="marker marker--${cls}">${icon(ic)}${esc(m)}</span>`;
  };
  function whoHtml(list) {
    const count = (key, val) => list.filter((p) => p[key] === val).length;
    const ics = { [MO]: 'i-circle', [ME]: 'i-circle-dot', [MC]: 'i-idcard' };
    const chips = ALL_300.marker.map(([m]) => `<span class="who__chip">${icon(ics[m], 'icon icon--sm')}<b class="num">${count(3, m)}</b>${esc(m)}</span>`).join('');
    const table = (cap, rows, key) => `<table><caption>${cap}</caption><thead><tr><th scope="col"></th><th scope="col">On this list</th><th scope="col">In all 300</th></tr></thead><tbody>${rows.map(([v, n]) => `<tr><th scope="row">${esc(v)}</th><td>${count(key, v)}</td><td>${n}</td></tr>`).join('')}</tbody></table>`;
    const missingYears = ALL_300.year.filter(([y]) => !count(2, y)).map(([y]) => `a ${y}`);
    const missingMajors = ALL_300.major.filter(([m]) => !count(1, m)).map(([m]) => `${/^[AEIOU]/.test(m) ? 'an' : 'a'} ${m} major`);
    const missing = [...missingYears, ...missingMajors];
    const cov = missing.length ? `<p class="coverage">${icon('i-users')}<span>Nobody on this list is ${missing.length > 1 ? missing.slice(0, -1).join(', ') + ' or ' + missing.at(-1) : missing[0]}.</span></p>` : '';
    return `${chips}<details class="disclosure"><summary>${icon('i-down')}Who is on the list</summary><div class="who-tables">${table('How much we know', ALL_300.marker, 3)}${table('By year', ALL_300.year, 2)}${table('By major', ALL_300.major, 1)}</div></details>${cov ? `<div style="flex-basis:100%">${cov}</div>` : ''}`;
  }
  function rowsHtml(list, w) {
    const rs = reasons(list, w);
    const n = S.showAll ? list.length : 6;
    return `<ol class="ranked" id="ranked" aria-label="The list, in order">${list.slice(0, n).map((p, i) => `<li class="row" data-name="${esc(p[0])}"><span class="row__rank">${i + 1}</span><div><div class="row__name">${esc(p[0])}</div><div class="row__meta">${esc(p[1])} · ${p[2]}</div></div>${markerChip(p[3])}<p class="row__reason">${esc(rs[i])}</p></li>`).join('')}</ol>
      <div class="list-foot"><button type="button" class="btn btn--quiet" id="show-all">${S.showAll ? 'Show the first 6' : `Show all ${list.length}`}</button></div>`;
  }
  function skeletonHtml() {
    return `<div class="working" role="status"><img class="m2d is-idle" src="${POSE.worker}" alt="" width="64" height="64">Rebuilding the list…</div><div class="skel" aria-hidden="true">${'<div class="skel__row"><i></i><i></i><i></i></div>'.repeat(5)}</div>`;
  }
  function renderList(animate) {
    const body = $('#list-body');
    if (S.loadingHold) { body.innerHTML = skeletonHtml(); $('#who').innerHTML = ''; return; }
    if (total() === 0) {
      $('#who').innerHTML = '';
      body.innerHTML = `<div class="working"><img src="${POSE.explore}" alt="" width="64" height="64" style="width:72px;height:auto">Nobody is on this list yet. Set a weight above 0 to build one.</div>`;
      return;
    }
    const first = new Map($$('.row', body).map((r) => [r.dataset.name, r.getBoundingClientRect().top]));
    const list = rankOf(S.weights);
    $('#who').innerHTML = whoHtml(list);
    body.innerHTML = rowsHtml(list, S.weights);
    $('#show-all').addEventListener('click', () => { S.showAll = !S.showAll; renderList(false); });
    if (!animate) return;
    $$('.row', body).forEach((r, k) => {
      const was = first.get(r.dataset.name);
      if (was === undefined) {
        r.animate([{ background: 'var(--pink-tint)', opacity: reduced() ? 1 : 0 }, { background: 'var(--pink-tint)', opacity: 1, offset: 0.25 }, { background: 'transparent' }], { duration: 1100, easing: 'ease-out' });
        return;
      }
      const dy = was - r.getBoundingClientRect().top;
      if (dy && !reduced()) r.animate([{ transform: `translateY(${dy}px)` }, { transform: 'translateY(0)' }], { duration: 520, delay: k * 12, easing: 'cubic-bezier(.34,1.25,.64,1)', fill: 'backwards' });
    });
  }
  let rebuildTimer = 0;
  function rebuild() {
    if (total() === 0) { renderList(false); return; }
    $('#rebuild-live').textContent = 'Rebuilding the list…';
    setFace('curious');
    clearTimeout(rebuildTimer);
    $('#ranked')?.style.setProperty('opacity', '.55');
    rebuildTimer = setTimeout(() => {
      renderList(true);
      $('#rebuild-live').textContent = 'The list was rebuilt.';
      setFace('happy');
    }, reduced() ? 60 : 320);
  }
  $('#save-btn').addEventListener('click', () => {
    if (total() === 0) { say('Set at least one weight above 0 before saving.', 'surprised', 4000); return; }
    const name = $('#save-name').value.trim();
    if (!name) { say('Give these weights a name first, so your team can find them.', 'surprised', 4000); $('#save-name').focus(); return; }
    if (S.saved.length >= 3) S.saved[2] = { name, w: [...S.weights] }; else S.saved.push({ name, w: [...S.weights] });
    S.pickAB = [S.saved.length - 1, 0];
    showScreen('compare', { hintOn: false });
    say(`Saved as “${name}”. Slot ${S.saved.length} of 3.`, 'laugh', 5000);
  });

  /* ---------- 4 Compare ---------- */
  const wStr = (w) => w.map((x) => x.toFixed(2)).join(' · ');
  function renderCompare() {
    const body = $('#compare-body');
    const saved = S.saved;
    const slots = [0, 1, 2].map((i) => {
      const s = saved[i];
      if (!s) return `<div class="slot slot--empty">Slot ${i + 1} of 3 is free. Save the weights on screen to fill it.</div>`;
      const k = S.pickAB.indexOf(i);
      return `<button type="button" class="slot" data-slot="${i}" aria-pressed="${k >= 0}"><span class="slot__badge" aria-hidden="true">${k === 0 ? 'A' : k === 1 ? 'B' : ''}</span><div class="slot__name">${esc(s.name)}</div><div class="slot__w" aria-label="Weights: ${FACTORS.map((f, j) => `${f} ${s.w[j].toFixed(2)}`).join(', ')}">${wStr(s.w)}</div></button>`;
    }).join('');
    const legend = `<p class="legend-line">Weights in order: same major · interested · career goal · similar events</p>`;
    if (saved.length < 2) {
      body.innerHTML = `${legend}<div class="slots">${slots}</div><div class="card empty" style="margin-top:16px"><img src="${POSE.explore}" alt="" width="180"><div><h2 class="h2">Save one more setting to compare.</h2><p>Try a different mix on the weights screen, name it, and save it. Then the two lists sit side by side here.</p><button type="button" class="btn btn--secondary" data-go="list">${icon('i-left')}Back to the weights</button></div></div>`;
      $('#compare-note').textContent = 'You can still run results with the one you saved.';
      bindSlots(); return;
    }
    const [a, b] = S.pickAB.map((i) => saved[i]);
    const la = rankOf(a.w), lb = rankOf(b.w);
    const setA = new Set(la.map((p) => p[0])), setB = new Set(lb.map((p) => p[0]));
    const both = la.filter((p) => setB.has(p[0])).length;
    const col = (tag, s, list, other) => `<div><h3><i>${tag}</i>${esc(s.name)}</h3><ol class="mini" aria-label="${esc(s.name)}, first 10">${list.slice(0, 10).map((p, k) => `<li class="${other.has(p[0]) ? 'is-both' : ''}"><b>${k + 1}</b><span>${esc(p[0])}</span>${other.has(p[0]) ? `<span class="both">${icon('i-link')}On both lists</span>` : ''}</li>`).join('')}</ol></div>`;
    body.innerHTML = `${legend}<div class="slots">${slots}</div>
      <p class="overlap"><b class="num">${both}</b> names are on both lists, highlighted in each.</p>
      <div class="seg seg-ab" role="radiogroup" aria-label="Which list to show"><label><input type="radio" name="ab" value="a" ${S.showB ? '' : 'checked'}>A · ${esc(a.name)}</label><label><input type="radio" name="ab" value="b" ${S.showB ? 'checked' : ''}>B · ${esc(b.name)}</label></div>
      <div class="card pair" data-show="${S.showB ? 'b' : 'a'}">${col('A', a, la, setB)}${col('B', b, lb, setA)}</div>`;
    $('#compare-note').textContent = 'Happy with a setting? Run results with it.';
    $$('input[name=ab]', body).forEach((r) => r.addEventListener('change', () => { S.showB = r.value === 'b'; $('.pair', body).dataset.show = r.value; }));
    bindSlots();
    if (!reduced()) $$('.mini li.is-both', body).forEach((li, k) => li.animate([{ background: 'transparent' }, { background: 'var(--pink-tint)' }], { duration: 420, delay: 120 + k * 35, easing: 'ease-out', fill: 'backwards' }));
  }
  function bindSlots() {
    $$('.slot[data-slot]').forEach((el) => el.addEventListener('click', () => {
      const i = Number(el.dataset.slot);
      if (S.pickAB.includes(i)) return;
      S.pickAB = [S.pickAB[1], i];
      renderCompare();
      $(`.slot[data-slot="${i}"]`)?.focus();
    }));
  }

  /* ---------- 5 Results ---------- */
  const R = { already: 8, added: 6, open: 46, team: [30, 9, 6], all: [300, 41, 27] };
  function renderResults() {
    const body = $('#results-body');
    const pickable = S.saved.slice(0, 3);
    if (S.results === 'locked') {
      body.innerHTML = `<div class="card state-card"><img class="m2d is-idle" src="${POSE.chill}" alt="" width="200"><div><span class="chip">${icon('i-lock')}Results are closed</span><h2>Waiting for the instructor</h2><p>The instructor has not opened results for this event yet.</p><button type="button" class="btn btn--mock" id="mock-unlock">Mockup only: the instructor opens results</button></div></div>`;
      $('#mock-unlock').addEventListener('click', () => { S.results = 'open'; syncReview(); renderResults(); say('Results are open.', 'laugh', 5000); });
      return;
    }
    if (S.results === 'open' || S.results === 'running') {
      body.innerHTML = `<div class="card"><span class="chip chip--open">${icon('i-unlock')}Results are open</span><h2 class="h2" style="margin-top:14px">Which setting is your team's final one?</h2><p class="muted" style="font-size:16px;margin-top:4px">Your team's invited list is built from the setting you choose.</p>
        <div class="picker" role="radiogroup" aria-label="Final setting">${pickable.map((s, i) => `<label class="pick"><input type="radio" name="final" value="${i}" ${i === S.finalSetting ? 'checked' : ''}><span><b>${esc(s.name)}</b><span>${wStr(s.w)}</span></span></label>`).join('')}</div>
        <p class="once">A team runs results once per event.</p></div>
        <div class="actionbar"><p class="actionbar__note" id="run-note">${S.results === 'running' ? '' : 'Ready when your team is.'}</p><button type="button" class="btn btn--primary" id="run-btn" ${S.results === 'running' ? 'aria-disabled="true"' : ''}>${S.results === 'running' ? 'Running…' : 'Run results for this event'}</button></div>`;
      document.body.classList.add('has-actionbar');
      $$('input[name=final]', body).forEach((r) => r.addEventListener('change', () => { S.finalSetting = Number(r.value); }));
      $('#run-btn').addEventListener('click', runResults);
      return;
    }
    // ran
    const s = pickable[S.finalSetting] || pickable[0];
    body.innerHTML = `<p class="headline" id="headline"><span><em>${R.already}</em> were already coming.</span><span>Your invitations added <em>${R.added}</em>.</span><span><em>${R.open}</em> seats are still open.</span></p>
      <div class="res-grid">
        <div class="card"><div class="front">Front of the room</div><div class="seats" id="seats" aria-hidden="true">${'<i class="seat"></i>'.repeat(60)}</div>
          <div class="legend"><span><i style="background:var(--seat-taken)"></i>Already coming<b>${R.already}</b></span><span><i style="background:var(--accent)"></i>Your invitations<b>${R.added}</b></span><span><i style="box-shadow:inset 0 0 0 1.5px var(--line-strong)"></i>Still open<b>${R.open}</b></span></div></div>
        <div class="card vs"><h2 class="h2">Beside “email everyone”</h2><p>Your team's final setting was “${esc(s.name)}”.</p>
          <table><thead><tr><th scope="col"></th><th scope="col">Your team's list</th><th scope="col">If you emailed everyone</th></tr></thead>
          <tbody>${['Invited', 'Signed up', 'Attended'].map((l, i) => `<tr><th scope="row">${l}</th><td class="team">${R.team[i]}</td><td>${R.all[i]}</td></tr>`).join('')}</tbody></table>
          <details class="disclosure" style="margin-top:12px"><summary>${icon('i-down')}See who came</summary><div class="people"><div><h3>Attended · ${R.team[2]}</h3><ul>${rankOf(s.w).slice(0, 6).map((p) => `<li>${esc(p[0])}</li>`).join('')}</ul></div><div><h3>Signed up, did not come · 3</h3><ul>${rankOf(s.w).slice(10, 13).map((p) => `<li>${esc(p[0])}</li>`).join('')}</ul></div></div></details>
        </div>
      </div>
      <div class="actionbar"><p class="actionbar__note">Talk with your team about why. Then ask for more.</p><button type="button" class="btn btn--primary" data-go="asking">Next: ask for more${icon('i-right')}</button></div>`;
    document.body.classList.add('has-actionbar');
    fillSeats();
  }
  async function runResults() {
    if (S.results === 'running') return;
    S.results = 'running'; renderResults();
    const body = $('#results-body');
    body.insertAdjacentHTML('afterbegin', `<div class="card working" style="margin-bottom:16px" role="status"><img class="m2d is-idle" src="${POSE.worker}" alt="" width="64" height="64">Running your team's list…</div>`);
    await wait(reduced() ? 200 : 1400);
    S.results = 'ran'; syncReview(); renderResults();
    celebrate();
  }
  async function fillSeats() {
    const seats = $$('#seats .seat');
    const paint = (i, c) => seats[i]?.classList.add(c);
    if (reduced()) { for (let i = 0; i < R.already; i++) paint(i, 'taken'); for (let i = R.already; i < R.already + R.added; i++) paint(i, 'yours'); return; }
    const lines = $$('#headline span'); lines.forEach((l) => { l.style.opacity = 0; });
    const show = (l) => l.animate([{ opacity: 0, transform: 'translateY(8px)' }, { opacity: 1, transform: 'none' }], { duration: 380, easing: 'cubic-bezier(.16,1,.3,1)', fill: 'forwards' });
    await wait(200);
    for (let i = 0; i < R.already; i++) setTimeout(() => paint(i, 'taken'), i * 30);
    show(lines[0]); await wait(520);
    for (let i = R.already; i < R.already + R.added; i++) setTimeout(() => { paint(i, 'yours'); seats[i].animate([{ transform: 'scale(.4)' }, { transform: 'scale(1.15)', offset: 0.6 }, { transform: 'scale(1)' }], { duration: 480, easing: 'cubic-bezier(.34,1.56,.64,1)' }); }, (i - R.already) * 90);
    show(lines[1]); await wait(760);
    show(lines[2]);
  }
  function celebrate() { say('Here is what happened. Look at the empty seats too.', 'laugh', 6000); }

  /* ---------- 6 Asking for more ---------- */
  const CHOICES = [
    ['better_recommendations', 'Promise better recommendations.', 'Tell them a card helps us suggest events worth their evening.'],
    ['small_reward', 'A small reward.', 'Offer something small for a completed card.'],
    ['required', 'Required.', 'Make the card a condition of hearing about events.'],
  ];
  const OUTCOME = { better_recommendations: [6, 0, 6], small_reward: [11, 0, 6], required: [16, 3, 6] };
  let armTimer = 0;
  function renderAsking() {
    const host = $('#choices');
    host.innerHTML = CHOICES.filter(([key]) => !S.ask || S.ask === key).map(([key, label, line]) => {
      const armed = S.askArmed === key, chosen = S.ask === key, dim = S.ask && !chosen;
      const bare = label.replace(/\.$/, '');
      const action = chosen ? `<span class="chosen-mark">${icon('i-check')}Your team's choice</span>`
        : S.ask ? '' : `<button type="button" class="btn ${armed ? 'btn--primary' : 'btn--secondary'}" data-choose="${key}" aria-describedby="ask-${key}-d">${armed ? `Confirm: ${esc(bare)}?` : 'Choose this way'}${armed && !reduced() ? '<span class="countdown" aria-hidden="true"></span>' : ''}</button>`;
      return `<div class="choice${armed ? ' is-armed' : ''}${chosen ? ' is-chosen' : ''}${dim ? ' is-dim' : ''}" role="radio" aria-checked="${chosen}" aria-labelledby="ask-${key}-l"><div><h2 id="ask-${key}-l">${esc(label)}</h2><p id="ask-${key}-d">${esc(line)}${armed && reduced() ? ' Press again within 5 seconds to confirm.' : ''}</p></div>${action}</div>`;
    }).join('');
    $$('[data-choose]', host).forEach((b) => {
      b.addEventListener('keydown', (e) => { if (e.repeat && (e.key === 'Enter' || e.key === ' ')) e.preventDefault(); });
      b.addEventListener('click', () => onChoose(b.dataset.choose));
    });
    const cd = $('.countdown', host);
    if (cd) cd.animate([{ transform: 'scaleX(1)' }, { transform: 'scaleX(0)' }], { duration: 5000, easing: 'linear', fill: 'forwards' });
    renderAskAfter();
  }
  function onChoose(key) {
    clearTimeout(armTimer);
    if (S.askArmed === key) {
      S.ask = key; S.askArmed = null;
      $('#ask-live').textContent = `Your team chose ${CHOICES.find((c) => c[0] === key)[1]}`;
      renderAsking(); say('Good. Now send the ask.', 'laugh', 4000);
      $('#ask-go')?.focus();
      return;
    }
    S.askArmed = key;
    const bare = CHOICES.find((c) => c[0] === key)[1].replace(/\.$/, '');
    $('#ask-live').textContent = `Press again to confirm ${bare}. Your team picks once.`;
    renderAsking();
    $(`[data-choose="${key}"]`)?.focus();
    armTimer = setTimeout(() => { S.askArmed = null; renderAsking(); }, 5000);
  }
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && S.askArmed) { clearTimeout(armTimer); const k = S.askArmed; S.askArmed = null; renderAsking(); $(`[data-choose="${k}"]`)?.focus(); } });
  function renderAskAfter() {
    const host = $('#ask-after');
    document.body.classList.toggle('has-actionbar', !!S.ask && !S.askRan);
    if (!S.ask) { host.innerHTML = ''; return; }
    if (!S.askRan) {
      host.innerHTML = `<div class="actionbar"><p class="actionbar__note">Your team chose: ${esc(CHOICES.find((c) => c[0] === S.ask)[1])}</p><button type="button" class="btn btn--primary" id="ask-go">Ask the people your team invited${icon('i-right')}</button></div>`;
      $('#ask-go').addEventListener('click', async () => {
        const b = $('#ask-go'); b.setAttribute('aria-disabled', 'true'); b.firstChild.textContent = 'Asking…'; setFace('curious');
        await wait(reduced() ? 100 : 900); S.askRan = true; renderAskAfter(); say("That's round one done.", 'laugh', 5000);
      });
      return;
    }
    const [cards, stopped, picked] = OUTCOME[S.ask];
    host.innerHTML = `<div class="card" style="margin-top:16px"><h2 class="h2">What changed</h2><div class="band"><div><b class="num" data-count="${cards}">${cards}</b><span>Cards filled in</span></div><div><b class="num" data-count="${stopped}">${stopped}</b><span>Stopped opening messages</span></div><div><b class="num" data-count="${picked}">${picked}</b><span>Picked up the first event's topics</span></div></div></div>
      <div class="card done"><div><h2>Round one is done.</h2><p>The markers on your list have changed. Next, your team builds a list for Harbor Consumer Brands.</p><button type="button" class="btn btn--primary" style="margin-top:20px" data-go="events">Go to round two${icon('i-right')}</button></div><img class="m2d" src="${POSE.celebrate}" alt="" width="190"></div>`;
    if (!reduced()) {
      $$('[data-count]', host).forEach((el) => { const n = Number(el.dataset.count); const t0 = performance.now(); const tick = (t) => { const k = Math.min(1, (t - t0) / 700); el.textContent = Math.round(n * (1 - (1 - k) ** 3)); if (k < 1) requestAnimationFrame(tick); }; requestAnimationFrame(tick); });
      const img = $('.done img', host); img.animate([{ transform: 'translateY(0) scale(1,1)' }, { transform: 'translateY(2px) scale(1.06,.92)', offset: 0.15 }, { transform: 'translateY(-22px) scale(.96,1.05)', offset: 0.45 }, { transform: 'translateY(0) scale(1.04,.95)', offset: 0.7 }, { transform: 'none' }], { duration: 1000, easing: 'cubic-bezier(.33,0,.2,1)' });
    }
  }

  /* ---------- Tour: steps as data, anchored by data-tour ---------- */
  const STEPS = [
    { screen: 'team', target: null, pose: 'guide', title: "Hi, I'm Bree", text: "I'll show you around the class exercise. It takes about a minute.", next: 'Show me around' },
    { screen: 'team', target: 'teams', pose: 'explore', title: 'Pick your team', text: "Pick your team's number. Your team's saved work is kept under that number." },
    { screen: 'team', target: 'open-team', pose: 'guide', title: 'Open your work', text: "Then open your team's work. You can come back and switch teams any time." },
    { screen: 'events', target: 'event-1', pose: 'explore', title: 'Choose an event', text: 'Choose one of the two events. Each one gets its own list.' },
    { screen: 'list', target: 'weights', pose: 'worker', title: 'Set how much each thing counts', text: 'Slide a weight and let go. The list is rebuilt from your numbers.' },
    { screen: 'list', target: 'list', pose: 'explore', title: 'Read the list', text: 'This is who your weights put first, and what counted for each person.' },
    { screen: 'list', target: 'save', pose: 'celebrate', title: "You're ready", text: 'Save weights you like, then run results. Replay this tour from the Tour button.', next: 'Finish' },
  ];
  const tour = { i: -1, open: false };
  const card = $('#tour'), spot = $('#spot'), blocks = $('#blocks');
  $('#tour-dots').innerHTML = STEPS.map(() => '<i></i>').join('');
  const seen = () => store.get(TOUR_KEY, null);
  let lastFocus = null;
  async function openTour(from = 0) {
    lastFocus = document.activeElement;
    tour.open = true; card.hidden = false; dock.hidden = true; hint.hidden = true; closeMenu();
    $('#tour-dont').checked = !!seen()?.dontShow;
    card.classList.remove('is-in'); void card.offsetWidth; if (!reduced()) card.classList.add('is-in');
    await goStep(from);
  }
  function closeTour(reason, toast = true) {
    tour.open = false; card.hidden = true; spot.classList.remove('is-on'); blocks.innerHTML = ''; dock.hidden = false;
    store.set(TOUR_KEY, { done: true, reason, dontShow: $('#tour-dont').checked, team: S.team, at: new Date().toISOString() });
    if (toast && reason === 'skipped') say('Tour closed. Find me under the Tour button whenever you want the walk-through.', 'calm', 5500);
    if (toast && reason === 'finished') say('Have a good session.', 'laugh', 4000);
    if (toast) dockBtn.focus({ preventScroll: true });
    void lastFocus;
  }
  async function goStep(i) {
    const s = STEPS[i]; if (!s) return;
    tour.i = i;
    if (S.screen !== s.screen) showScreen(s.screen, { focus: false, hintOn: false });
    $('#tour-count').textContent = `Step ${i + 1} of ${STEPS.length}`;
    $$('#tour-dots i').forEach((d, k) => d.classList.toggle('on', k === i));
    $('#tour-title').textContent = s.title; $('#tour-text').textContent = s.text;
    $('#tour-back').hidden = i === 0;
    $('#tour-next-label').textContent = s.next || 'Next';
    $('#tour-live').textContent = `Step ${i + 1} of ${STEPS.length}. ${s.title}. ${s.text}`;
    const img = $('#tour-img'); const src = POSE[s.pose];
    if (!img.src.endsWith(src.split('/').pop())) {
      img.src = src; try { await img.decode(); } catch { /* keep going */ }
      img.animate(reduced() ? [{ opacity: 0 }, { opacity: 1 }] : [{ opacity: 0, transform: 'translateY(14px) scale(.8)' }, { opacity: 1, transform: 'translateY(-3px) scale(1.04)', offset: 0.65 }, { opacity: 1, transform: 'none' }], { duration: reduced() ? 150 : 460, easing: 'cubic-bezier(.34,1.56,.64,1)' });
    }
    const el = s.target ? $(`[data-tour="${s.target}"]`) : null;
    if (el) {
      const r = el.getBoundingClientRect(); const narrow = innerWidth < 900;
      const want = narrow ? 170 : Math.max(90, (innerHeight - Math.min(r.height, innerHeight * 0.6)) / 2 - 80);
      window.scrollBy({ top: r.top - want, behavior: reduced() ? 'instant' : 'smooth' });
      await wait(reduced() ? 0 : 400);
    } else window.scrollTo({ top: 0, behavior: 'instant' });
    place();
    $('#tour-title').focus({ preventScroll: true });
  }
  function place() {
    if (!tour.open) return;
    const s = STEPS[tour.i];
    const el = s.target ? $(`[data-tour="${s.target}"]`) : null;
    const pad = 10, vw = innerWidth, vh = innerHeight;
    const top0 = $('.review').offsetHeight + 8;
    if (el) {
      const r = el.getBoundingClientRect();
      const x = r.left - pad, y = Math.max(r.top - pad, top0), w = r.width + pad * 2, h = Math.max(40, Math.min(r.bottom + pad, vh - 12) - y);
      Object.assign(spot.style, { left: `${x}px`, top: `${y}px`, width: `${w}px`, height: `${h}px` });
      spot.classList.remove('is-center');
      blocks.innerHTML = [[0, 0, vw, y], [0, y + h, vw, vh - y - h], [0, y, x, h], [x + w, y, vw - x - w, h]]
        .map(([l, t, bw, bh]) => `<div class="block" style="left:${l}px;top:${t}px;width:${Math.max(0, bw)}px;height:${Math.max(0, bh)}px"></div>`).join('');
    } else {
      Object.assign(spot.style, { left: `${vw / 2}px`, top: `${vh / 2}px`, width: '0px', height: '0px' });
      spot.classList.add('is-center');
      blocks.innerHTML = '<div class="block" style="inset:0"></div>';
    }
    spot.classList.add('is-on');
  }
  let placeRaf = 0;
  const requestPlace = () => { if (tour.open && !placeRaf) placeRaf = requestAnimationFrame(() => { placeRaf = 0; place(); }); };
  addEventListener('resize', requestPlace); addEventListener('scroll', requestPlace, { passive: true });
  $('#tour-next').addEventListener('click', () => (tour.i >= STEPS.length - 1 ? closeTour('finished') : goStep(tour.i + 1)));
  $('#tour-back').addEventListener('click', () => goStep(Math.max(0, tour.i - 1)));
  $('#tour-skip').addEventListener('click', () => closeTour('skipped'));
  $('#tour-dont').addEventListener('change', (e) => { store.set(TOUR_KEY, { ...(seen() || {}), dontShow: e.target.checked }); });
  card.addEventListener('keydown', (e) => {
    if (e.target.matches('input')) return;
    if (e.key === 'ArrowRight') { e.preventDefault(); $('#tour-next').click(); }
    if (e.key === 'ArrowLeft' && tour.i > 0) { e.preventDefault(); $('#tour-back').click(); }
  });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && tour.open) closeTour('skipped'); });

  /* ---------- Review controls ---------- */
  function applyTheme(v) { if (v === 'system') delete html.dataset.theme; else html.dataset.theme = v; }
  $$('input[name=theme]').forEach((r) => r.addEventListener('change', () => applyTheme(r.value)));
  $('#rv-rm').addEventListener('change', (e) => html.classList.toggle('rm', e.target.checked));
  function syncReview() { $$('input[name=res]').forEach((r) => { r.checked = r.value === (S.results === 'running' ? 'open' : S.results); }); }
  $$('input[name=res]').forEach((r) => r.addEventListener('change', () => { S.results = r.value; if (S.screen !== 'results') showScreen('results', { hintOn: false }); else renderResults(); if (r.value === 'ran') celebrate(); }));
  $('#rv-one').addEventListener('change', (e) => { S.saved = e.target.checked ? [S.saved[0]] : [{ name: 'Major first', w: [0.60, 0.15, 0.15, 0.10] }, { name: 'Interests first', w: [0.15, 0.45, 0.25, 0.15] }]; S.pickAB = [0, 1]; S.finalSetting = 0; showScreen('compare', { hintOn: false }); });
  let savedWeights = null;
  $('#rv-zero').addEventListener('change', (e) => {
    if (e.target.checked) { savedWeights = [...S.weights]; S.weights = [0, 0, 0, 0]; } else S.weights = savedWeights || [0.40, 0.25, 0.25, 0.10];
    syncSliders(); showScreen('list', { hintOn: false }); if (e.target.checked) setFace('surprised');
  });
  $('#rv-load').addEventListener('change', (e) => { S.loadingHold = e.target.checked; showScreen('list', { hintOn: false }); setFace(S.loadingHold ? 'curious' : 'happy'); });
  $('#rv-replay').addEventListener('click', () => { $('#ctl').open = false; openTour(0); });
  $('#rv-forget').addEventListener('click', () => { store.del(TOUR_KEY); $('#ctl').open = false; location.href = location.pathname; });

  /* ---------- Boot: deep links for review and screenshots ---------- */
  const dockPref = store.get(DOCK_KEY, {});
  S.dockLeft = !!dockPref.left; S.hints = dockPref.hints !== false; applyDock();
  const theme = qs.get('theme'); if (theme) { applyTheme(theme); $$('input[name=theme]').forEach((r) => { r.checked = r.value === theme; }); }
  if (qs.get('rm') === '1') { html.classList.add('rm'); $('#rv-rm').checked = true; }
  if (qs.get('hints') === 'off') S.hints = false;
  if (qs.get('team')) pickTeam(Number(qs.get('team')));
  if (qs.get('results')) S.results = qs.get('results');
  if (qs.get('compare') === 'one') { S.saved = [S.saved[0]]; $('#rv-one').checked = true; }
  if (qs.get('weights') === 'zero') { S.weights = [0, 0, 0, 0]; $('#rv-zero').checked = true; }
  if (qs.get('loading') === '1') { S.loadingHold = true; $('#rv-load').checked = true; }
  if (qs.get('ask')) { S.ask = qs.get('ask'); if (qs.get('asked') === '1') S.askRan = true; }
  syncSliders(); syncReview();
  showScreen(qs.get('screen') || 'team', { focus: false, hintOn: qs.get('hint') !== 'off' });
  const stepParam = qs.get('step');
  if (stepParam !== null) { if (stepParam !== 'none') openTour(Math.max(0, Number(stepParam) - 1)); }
  else if (!seen()?.done && !seen()?.dontShow) setTimeout(() => openTour(0), 700);
  mqRM.addEventListener('change', () => { if (S.screen === 'asking') renderAsking(); });
  window.__mockReady = true;
})();
