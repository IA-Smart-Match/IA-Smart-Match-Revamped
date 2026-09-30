/* Direction A · Playful Learning — mockup behaviour. Plain JS, no libraries.
   Deep links: ?screen=entry|events|weights|compare|locked|open|ask|done
               &state=loading|error|empty  &step=N|none  &theme=dark  &rm=1  &tour=off */
(() => {
  'use strict';
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const html = document.documentElement;
  const A = '../../mockup/assets/';
  const qs = new URLSearchParams(location.search);
  const store = {
    get(k, d = null) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* private mode */ } },
    del(k) { try { localStorage.removeItem(k); } catch { /* ignore */ } },
  };
  const TOUR_KEY = 'smartmatch.exercise.tour.v1';
  const mqRM = matchMedia('(prefers-reduced-motion: reduce)');
  let simRM = qs.get('rm') === '1';
  const reduced = () => simRM || mqRM.matches;
  const wait = (ms) => new Promise((r) => setTimeout(r, reduced() ? 0 : ms));

  /* ------------------------------------------------------------------ data */
  const FACTORS = [
    { label: 'same major', icon: 'i-cap', tint: 'b-violet' },
    { label: 'said they are interested in this topic', icon: 'i-heart', tint: 'b-coral' },
    { label: 'career goal fits this event', icon: 'i-target', tint: 'b-sky' },
    { label: 'went to similar events before', icon: 'i-calendar', tint: 'b-violet' },
  ];
  const CIS = 'Computer Information Systems', IBM = 'International Business & Marketing', TOM = 'Technology & Operations Management', ACC = 'Accounting', MHR = 'Management & Human Resources', FIN = 'Finance';
  const MK = { major: ['major only', 'mk--major', 'i-circle'], events: ['major plus events attended', 'mk--events', 'i-calcheck'], card: ['completed card', 'mk--card', 'i-idcard'] };
  const INFO = { card: 3, events: 2, major: 1 };
  const YEARS = { Senior: 4, Junior: 3, Sophomore: 2, Freshman: 1 };
  const PEOPLE = [
    ['Maya Tran', CIS, 'Senior', 'card', [1, 1, 1, 0]], ['Priya Patel', CIS, 'Junior', 'events', [1, 0, 0, 1]],
    ['Jordan Kim', CIS, 'Senior', 'major', [1, 0, 0, 0]], ['Alexis Rivera', CIS, 'Junior', 'major', [1, 0, 0, 0]],
    ['Tyler Reyes', CIS, 'Sophomore', 'events', [1, 0, 0, 1]], ['Omar Farouk', CIS, 'Senior', 'card', [1, 0, 1, 1]],
    ['Lucia Benavides', CIS, 'Sophomore', 'major', [1, 0, 0, 0]], ['Wen Zhao', CIS, 'Junior', 'card', [1, 1, 0, 0]],
    ['Isaiah Brooks', CIS, 'Senior', 'major', [1, 0, 0, 0]], ['Marisol Ortega', CIS, 'Junior', 'major', [1, 0, 0, 0]],
    ['Kenji Watanabe', CIS, 'Sophomore', 'major', [1, 0, 0, 0]], ['Amara Nwosu', CIS, 'Senior', 'events', [1, 0, 0, 1]],
    ['Felix Moreau', CIS, 'Junior', 'major', [1, 0, 0, 0]], ['Daniel Okafor', IBM, 'Senior', 'card', [0, 0, 1, 0]],
    ['Ethan Nguyen', IBM, 'Senior', 'events', [0, 0, 0, 1]], ['Sofia Morales', TOM, 'Senior', 'card', [0, 1, 1, 0]],
    ['Marcus Chen', IBM, 'Junior', 'major', [0, 0, 0, 0]], ['Hannah Lee', IBM, 'Sophomore', 'major', [0, 0, 0, 0]],
    ['Diego Garcia', ACC, 'Senior', 'events', [0, 0, 0, 1]], ['Chloe Brooks', MHR, 'Junior', 'card', [0, 1, 0, 1]],
    ['Ravi Shah', TOM, 'Senior', 'card', [0, 1, 1, 1]], ['Grace Park', ACC, 'Junior', 'card', [0, 1, 0, 0]],
    ['Leila Haddad', IBM, 'Junior', 'card', [0, 1, 0, 0]], ['Brandon Cole', MHR, 'Senior', 'events', [0, 0, 0, 1]],
    ['Nina Vasquez', TOM, 'Sophomore', 'card', [0, 1, 1, 0]], ['Kevin Yu', ACC, 'Senior', 'major', [0, 0, 0, 0]],
    ['Talia Brennan', TOM, 'Junior', 'events', [0, 0, 0, 1]], ['Samuel Adeyemi', IBM, 'Senior', 'events', [0, 0, 0, 1]],
    ['Rosa Delgado', MHR, 'Sophomore', 'major', [0, 0, 0, 0]], ['Noah Fischer', FIN, 'Senior', 'events', [0, 0, 0, 1]],
    ['Ines Carvalho', FIN, 'Junior', 'major', [0, 0, 0, 0]], ['Julian Soto', TOM, 'Senior', 'major', [0, 0, 0, 0]],
    ['Aaliyah Grant', IBM, 'Junior', 'card', [0, 0, 1, 0]], ['Mateo Ruiz', ACC, 'Sophomore', 'major', [0, 0, 0, 0]],
    ['Hana Sato', FIN, 'Sophomore', 'major', [0, 0, 0, 0]], ['Owen Gallagher', MHR, 'Junior', 'major', [0, 0, 0, 0]],
  ];
  /* The whole data file (300), illustrative counts for the "who is on the list" table. */
  const ALL = {
    know: { 'major only': 186, 'major plus events attended': 44, 'completed card': 70 },
    major: { [CIS]: 52, [IBM]: 61, [TOM]: 38, [ACC]: 57, [MHR]: 44, [FIN]: 48 },
    year: { Senior: 78, Junior: 81, Sophomore: 74, Freshman: 67 },
  };
  const SETTINGS = [
    { name: 'Major first', w: [0.40, 0.25, 0.25, 0.10] },
    { name: 'Interests first', w: [0.15, 0.45, 0.25, 0.15] },
  ];

  const S = {
    screen: 'entry', team: null, event: null, weights: [0.40, 0.25, 0.25, 0.10],
    showAll: false, loading: false, compare: [0, 1], unlocked: false,
    ask: null, armed: false, yay: false, whoTab: 'know',
  };

  const rankOf = (w) => PEOPLE.map((p) => ({ p, s: p[4].reduce((a, f, i) => a + f * w[i], 0) }))
    .sort((a, b) => b.s - a.s || INFO[b.p[3]] - INFO[a.p[3]] || YEARS[b.p[2]] - YEARS[a.p[2]] || a.p[0].localeCompare(b.p[0]))
    .slice(0, 30).map((x) => x.p);
  function reasonFor(p, w) {
    const on = FACTORS.map((f) => f.label).filter((_, i) => p[4][i] && w[i] > 0);
    if (!on.length) return p[3] === 'major' ? 'Nothing on file counted for this event.' : 'What is on file did not count for this event.';
    if (on.length === 1 && on[0] === 'same major' && p[3] === 'major') return 'Same major; nothing else on file.';
    return `What counted: ${on.join('; ')}.`;
  }
  const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;');
  const marker = (k) => `<span class="mk ${MK[k][1]}"><svg class="icon" aria-hidden="true"><use href="#${MK[k][2]}"/></svg><span class="mk-text">${MK[k][0]}</span></span>`;

  /* ------------------------------------------------------------ screens */
  const ORDER = ['entry', 'events', 'weights', 'compare', 'results', 'ask', 'done'];
  const STEP_OF = { entry: 1, events: 2, weights: 3, compare: 4, results: 5, open: 5, ask: 6, done: 7 };
  const STEP_NAMES = ['Team', 'Event', 'Weights', 'Compare', 'Results', 'Ask'];
  const screenEl = (n) => $(`[data-screen="${n}"]`);
  const visibleName = () => (S.screen === 'results' && S.unlocked ? 'open' : S.screen);

  function show(name, { focus = true, animate = true } = {}) {
    if (name === 'open') { S.unlocked = true; name = 'results'; }
    if (name === 'locked') { S.unlocked = false; name = 'results'; resetLock(); }
    S.screen = name; S.yay = false; S.armed = false;
    const vis = visibleName();
    $$('.screen').forEach((s) => { s.hidden = s.dataset.screen !== vis; });
    const el = screenEl(vis);
    if (animate && !reduced()) { el.classList.remove('enter'); void el.offsetWidth; el.classList.add('enter'); }
    $$('.review__nav button').forEach((b) => {
      const j = b.dataset.jump; const on = j === vis || (j === 'locked' && vis === 'results');
      on ? b.setAttribute('aria-current', 'page') : b.removeAttribute('aria-current');
    });
    window.scrollTo({ top: 0, behavior: 'instant' });
    renderPath(); renderCheck();
    if (vis === 'weights' && total() > 0) renderList(false);
    if (vis === 'compare') renderCompare();
    if (vis === 'open') fillSeats();
    if (focus) $('.h1, .headline', el)?.focus({ preventScroll: true });
  }

  function renderPath() {
    const step = STEP_OF[visibleName()];
    const pct = step >= 7 ? 100 : Math.round(((step - 1) / 6) * 100 + 100 / 12);
    $('#path-fill').style.setProperty('--p', `${pct}%`);
    const p = $('#path');
    p.setAttribute('aria-valuenow', Math.min(step, 6));
    p.setAttribute('aria-valuetext', step >= 7 ? 'All 6 steps done' : `Step ${step} of 6: ${STEP_NAMES[step - 1]}`);
    $('#path-label').textContent = step >= 7 ? 'All 6 steps done' : `Step ${step} of 6 · ${STEP_NAMES[step - 1]}`;
    $('#back').disabled = S.screen === 'entry';
  }

  /* ------------------------------------------------ check bar per screen */
  const CHECK = {
    entry: { label: "Open this team's work", ok: () => !!S.team, hint: () => (S.team ? '' : 'Pick a team number first.'),
      yay: () => [`Team ${S.team} is in.`, 'Your saved work lives under that number.'], next: 'events' },
    events: { label: 'Build this list', ok: () => !!S.event, hint: () => (S.event ? '' : 'Pick one event.'),
      yay: () => [`${S.event === 'harbor' ? 'Harbor Consumer Brands' : 'Northline Analytics'} it is.`, 'Each event keeps its own list.'], next: 'weights' },
    weights: { label: 'Save these weights', ok: () => total() > 0 && !S.loading, hint: () => (total() > 0 ? 'Next: name it and compare.' : 'Move any slider above 0 first.'),
      yay: () => ['Saved as “Major first”.', 'Slot 1 of 3.'], next: 'compare' },
    compare: { label: 'Run results for this event', ok: () => true, hint: () => 'Your team gets one run per event.',
      yay: () => ['Final setting: “Major first”.', 'Results open when the instructor says so.'], next: 'results' },
    results: { label: 'Run results for this event', ok: () => false, hint: () => '' },
    open: { label: 'Next: asking for more', ok: () => true, hint: () => '', next: 'ask' },
    ask: { label: 'Choose this way', ok: () => !!S.ask, hint: () => (S.ask ? '' : 'Pick one way to ask.'),
      yay: () => ['Your team chose:', S.ask], next: 'done' },
    done: { label: 'Start round two', ok: () => true, hint: () => 'Harbor Consumer Brands is next.', next: 'events' },
  };
  const btn = $('#check-btn');
  function renderCheck() {
    const c = CHECK[visibleName()];
    const bar = $('#check');
    bar.classList.toggle('is-yay', S.yay);
    btn.classList.toggle('btn--coral', S.yay);
    btn.classList.toggle('btn--primary', !S.yay);
    if (S.yay) {
      const [t, x] = c.yay();
      $('#check-title').textContent = t; $('#check-text').textContent = x; $('#check-text').className = 'sub';
      $('#check-label').textContent = 'Continue';
      btn.setAttribute('aria-disabled', 'false');
      return;
    }
    $('#check-title').textContent = ''; $('#check-text').className = 'hint';
    $('#check-text').textContent = c.hint();
    let label = c.label;
    if (visibleName() === 'ask' && S.armed) label = `Confirm: ${S.ask.replace(/\.$/, '')}?`;
    $('#check-label').textContent = label;
    btn.setAttribute('aria-disabled', c.ok() ? 'false' : 'true');
  }
  let armTimer = 0, armAnim = null;
  btn.addEventListener('click', async () => {
    const name = visibleName(); const c = CHECK[name];
    if (btn.getAttribute('aria-disabled') === 'true') return;
    if (S.yay) { show(c.next); return; }
    if (name === 'ask' && !S.armed) { arm(); return; }
    if (name === 'ask') { disarm(false); $('#recap-ask').firstChild.textContent = `Asked with “${S.ask}”`; }
    if (!c.yay) { show(c.next); return; }
    S.yay = true; renderCheck(); celebrate();
  });
  function arm() {
    S.armed = true; renderCheck();
    $('#ask-live').textContent = `Press again to confirm ${S.ask.replace(/\.$/, '')}. Your team picks once.`;
    const line = document.createElement('span'); line.className = 'confirm-line'; line.id = 'confirm-line'; btn.appendChild(line);
    if (!reduced()) armAnim = line.animate([{ transform: 'scaleX(1)' }, { transform: 'scaleX(0)' }], { duration: 5000, easing: 'linear', fill: 'forwards' });
    clearTimeout(armTimer); armTimer = setTimeout(() => disarm(true), 5000);
  }
  function disarm(render) { S.armed = false; clearTimeout(armTimer); armAnim?.cancel(); $('#confirm-line')?.remove(); if (render) { $('#ask-live').textContent = ''; renderCheck(); } }
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && S.armed) disarm(true); });

  /* A small burst from the button and a hop from the face: the step-complete moment. */
  function celebrate() {
    const face = $('.check__face img');
    if (reduced()) { $('#check').animate([{ opacity: .6 }, { opacity: 1 }], { duration: 150 }); return; }
    face.classList.remove('pop'); void face.offsetWidth; face.classList.add('pop');
    burst($('#check-burst'), 14, 90);
    const art = $(`[data-screen="${visibleName()}"] .coach__art img`);
    if (art) { art.classList.remove('hop'); void art.offsetWidth; art.classList.add('hop'); }
  }
  const SPARK = ['var(--primary)', 'var(--coral)', 'var(--sky)', 'var(--sun)'];
  function burst(host, n, dist) {
    if (reduced()) return;
    for (let i = 0; i < n; i++) {
      const s = document.createElement('i'); s.className = 'spark';
      s.style.background = SPARK[i % 4]; if (i % 3 === 0) s.style.borderRadius = '50%';
      host.appendChild(s);
      const a = (i / n) * Math.PI * 2 + Math.random() * .4, d = dist * (.6 + Math.random() * .5);
      s.animate([
        { transform: 'translate(0,0) scale(.3) rotate(0)', opacity: 1 },
        { transform: `translate(${Math.cos(a) * d}px, ${Math.sin(a) * d * .7}px) scale(1) rotate(${a * 90}deg)`, opacity: 1, offset: .6 },
        { transform: `translate(${Math.cos(a) * d * 1.1}px, ${Math.sin(a) * d * .7 + 18}px) scale(.8) rotate(${a * 140}deg)`, opacity: 0 },
      ], { duration: 820, easing: 'cubic-bezier(.16,1,.3,1)' }).finished.then(() => s.remove(), () => s.remove());
    }
  }

  /* --------------------------------------------------------- 1 team entry */
  const tiles = $('#tiles');
  for (let n = 1; n <= 6; n++) {
    const b = document.createElement('button');
    b.type = 'button'; b.className = 'tile num'; b.setAttribute('role', 'radio'); b.setAttribute('aria-checked', 'false');
    b.dataset.n = n; b.tabIndex = n === 1 ? 0 : -1; b.textContent = n; b.setAttribute('aria-label', `Team ${n}`);
    tiles.appendChild(b);
  }
  function pickTeam(n, focus) {
    S.team = n;
    $$('.tile', tiles).forEach((t) => { const on = Number(t.dataset.n) === n; t.setAttribute('aria-checked', on); t.tabIndex = on ? 0 : -1; if (on && focus) t.focus(); if (on && !reduced()) { t.classList.remove('pop'); void t.offsetWidth; t.classList.add('pop'); } });
    $('#team-pill').hidden = false; $('#team-pill').textContent = `Team ${n}`;
    $('#entry-bubble').textContent = `Team ${n}. Your team's saved work is kept under that number.`;
    const img = $('[data-screen="entry"] .coach__art img');
    if (!reduced()) { img.classList.remove('wiggle'); void img.offsetWidth; img.classList.add('wiggle'); }
    renderCheck();
  }
  tiles.addEventListener('click', (e) => { const t = e.target.closest('.tile'); if (t) pickTeam(Number(t.dataset.n)); });
  function radioKeys(group, items, pick) {
    group.addEventListener('keydown', (e) => {
      const list = items(); const i = list.indexOf(document.activeElement); if (i < 0) return;
      const d = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
      if (d) { e.preventDefault(); pick(list[(i + d + list.length) % list.length], true); }
    });
  }
  radioKeys(tiles, () => $$('.tile', tiles), (t, f) => pickTeam(Number(t.dataset.n), f));

  /* ----------------------------------------------------------- 2 events */
  function pickEvent(b, focus) {
    S.event = b.dataset.event;
    $$('#event-opts .option').forEach((o) => { const on = o === b; o.setAttribute('aria-checked', on); o.tabIndex = on ? 0 : -1; });
    $('#more-northline').hidden = S.event !== 'northline'; $('#more-harbor').hidden = S.event !== 'harbor';
    if (focus) b.focus();
    renderCheck();
  }
  $$('#event-opts .option').forEach((o, i) => { o.tabIndex = i === 0 ? 0 : -1; o.addEventListener('click', () => pickEvent(o)); });
  radioKeys($('#event-opts'), () => $$('#event-opts .option'), pickEvent);
  function toggle(btnEl, panel) {
    btnEl.addEventListener('click', () => { const open = btnEl.getAttribute('aria-expanded') !== 'true'; btnEl.setAttribute('aria-expanded', open); panel.hidden = !open; });
  }
  toggle($('#past-btn'), $('#past'));
  toggle($('#pcard-btn'), $('#pcard'));
  toggle($('#came-btn'), $('#came'));

  /* ----------------------------------------------------- 3 weights + list */
  const total = () => S.weights.reduce((a, b) => a + b, 0);
  const factorsEl = $('#factors');
  FACTORS.forEach((f, i) => {
    const row = document.createElement('div'); row.className = 'factor';
    row.innerHTML = `<div class="factor__top"><span class="factor__icon ${f.tint}" aria-hidden="true"><svg class="icon"><use href="#${f.icon}"/></svg></span><label for="w${i}">${f.label}</label><input class="val" type="text" inputmode="decimal" aria-label="${f.label}, exact value" value="${S.weights[i].toFixed(2)}"></div><input type="range" id="w${i}" min="0" max="1" step="0.05" value="${S.weights[i]}">`;
    factorsEl.appendChild(row);
    const range = row.querySelector('input[type=range]'), val = row.querySelector('.val');
    const paint = () => range.style.setProperty('--fill', `${range.value * 100}%`);
    paint();
    range.addEventListener('input', () => { S.weights[i] = Number(range.value); val.value = S.weights[i].toFixed(2); paint(); updateTotal(); });
    range.addEventListener('change', rebuild);
    val.addEventListener('change', () => { const v = Math.min(1, Math.max(0, Number(val.value) || 0)); S.weights[i] = v; range.value = v; val.value = v.toFixed(2); paint(); updateTotal(); rebuild(); });
    row.syncFromState = () => { range.value = S.weights[i]; val.value = S.weights[i].toFixed(2); paint(); };
  });
  function updateTotal() {
    const t = total();
    $('#total').textContent = `Total weight: ${t.toFixed(2)}`;
    const bad = t <= 0;
    $('#oops').hidden = !bad;
    $('#rows').classList.toggle('is-stale', bad);
    $('#list-status').textContent = bad ? 'This is the list from before that change.' : $('#list-status').textContent;
    renderCheck();
  }
  async function rebuild() {
    if (total() <= 0) { setWorker('error'); return; }
    S.loading = true; renderCheck(); setWorker('loading');
    $('#list-status').className = 'status'; $('#list-status').textContent = 'Rebuilding the list…';
    $('#rows').innerHTML = Array.from({ length: 6 }, () => '<li class="skel" aria-hidden="true"></li>').join('');
    await wait(520);
    S.loading = false; renderList(true); setWorker('ok'); renderCheck();
    $('#list-status').className = 'status is-good';
    $('#list-status').innerHTML = '<svg class="icon" aria-hidden="true" style="width:18px;height:18px"><use href="#i-check"/></svg>The list was rebuilt.';
  }
  function setWorker(mode) {
    const b = $('#w-bubble'), art = $('#w-art'), img = art.querySelector('img');
    art.classList.toggle('is-idle', mode !== 'loading');
    art.parentElement.classList.toggle('coach--face', mode === 'error');
    const want = A + (mode === 'error' ? 'face2-surprised.webp' : 'pose4-worker.webp');
    if (!img.src.endsWith(want.slice(2))) { img.src = want; if (mode === 'error' && !reduced()) { img.classList.remove('wiggle'); void img.offsetWidth; img.classList.add('wiggle'); } }
    if (mode === 'loading') b.textContent = 'Rebuilding the list…';
    else if (mode === 'error') b.textContent = 'Hmm. With every weight at 0, I have nothing to sort by.';
    else b.textContent = 'The list is rebuilt when you let go of a slider or press Enter.';
    if (mode === 'loading' && !reduced()) art.querySelector('img').animate([{ transform: 'translateY(0)' }, { transform: 'translateY(-3px)' }, { transform: 'translateY(0)' }], { duration: 260, iterations: 2 });
  }
  function rowHtml(p, i, both) {
    const id = `more-${i}`;
    return `<li class="r${both ? ' is-both' : ''}" data-name="${esc(p[0])}"><span class="r__rank num">${i + 1}</span><div><div class="r__name">${esc(p[0])}</div><div class="r__why">${reasonFor(p, S.weights)}</div>${both ? '<span class="both"><svg class="icon" aria-hidden="true"><use href="#i-link"/></svg>On both lists</span>' : ''}<div class="r__more" id="${id}" hidden>${esc(p[1])} · ${p[2]}</div></div><div class="r__side">${marker(p[3])}<button type="button" class="r__toggle" aria-expanded="false" aria-controls="${id}" aria-label="More about ${esc(p[0])}"><svg class="icon" aria-hidden="true"><use href="#i-down"/></svg></button></div></li>`;
  }
  function compactRow(p, i, both, tag) {
    const id = `more-${tag}-${i}`;
    return `<li class="r r--compact${both ? ' is-both' : ''}"><span class="r__rank num">${i + 1}</span><div><div class="r__name">${esc(p[0])}</div><div class="r__more" id="${id}" hidden>${reasonFor(p, SETTINGS[S.compare[tag]].w)}<br>${esc(p[1])} · ${p[2]}</div></div>${both ? '<span class="both-dot" role="img" aria-label="On both lists"><svg class="icon" aria-hidden="true"><use href="#i-link"/></svg></span>' : '<span></span>'}<button type="button" class="r__toggle" aria-expanded="false" aria-controls="${id}" aria-label="More about ${esc(p[0])}"><svg class="icon" aria-hidden="true"><use href="#i-down"/></svg></button></li>`;
  }
  function renderList(animate) {
    const rows = $('#rows');
    const first = new Map($$('.r', rows).map((r) => [r.dataset.name, r.getBoundingClientRect().top]));
    const list = rankOf(S.weights);
    const shown = S.showAll ? list : list.slice(0, 8);
    rows.innerHTML = shown.map((p, i) => rowHtml(p, i, false)).join('');
    $('#all-btn').firstChild.textContent = S.showAll ? 'Show the first 8' : 'Show all 30';
    $('#all-btn').setAttribute('aria-expanded', S.showAll);
    renderWho(list);
    if (!animate || reduced()) return;
    $$('.r', rows).forEach((r, k) => {
      const was = first.get(r.dataset.name);
      if (was === undefined) { r.animate([{ opacity: 0, transform: 'translateY(8px)', background: 'var(--coral-tint)' }, { opacity: 1, transform: 'none', background: 'var(--coral-tint)', offset: .3 }, { background: 'transparent' }], { duration: 900, delay: k * 25, easing: 'ease-out' }); return; }
      const dy = was - r.getBoundingClientRect().top;
      if (dy) r.animate([{ transform: `translateY(${dy}px)` }, { transform: 'none' }], { duration: 340, easing: 'cubic-bezier(.2,.9,.25,1)' });
    });
  }
  $('#rows').addEventListener('click', (e) => {
    const t = e.target.closest('.r__toggle'); if (!t) return;
    const open = t.getAttribute('aria-expanded') !== 'true'; t.setAttribute('aria-expanded', open); $(`#${t.getAttribute('aria-controls')}`).hidden = !open;
  });
  $('#all-btn').addEventListener('click', () => { S.showAll = !S.showAll; renderList(false); });
  toggle($('#who-btn'), $('#who'));
  const menuBtn = $('#menu-btn');
  menuBtn.addEventListener('click', () => { const open = menuBtn.getAttribute('aria-expanded') !== 'true'; menuBtn.setAttribute('aria-expanded', open); $('#menu').hidden = !open; if (open) $('#dl-btn').focus(); });
  $('#dl-btn').addEventListener('click', () => { menuBtn.click(); toast('face1-happy.webp', 'List downloaded', 'A spreadsheet with all 30 names and reasons (mockup: no file is made).'); });
  document.addEventListener('click', (e) => { if (!e.target.closest('.menu') && menuBtn.getAttribute('aria-expanded') === 'true') { menuBtn.setAttribute('aria-expanded', 'false'); $('#menu').hidden = true; } });
  $$('.tabs button').forEach((b) => b.addEventListener('click', () => { S.whoTab = b.dataset.tab; $$('.tabs button').forEach((x) => x.setAttribute('aria-selected', x === b)); renderWho(rankOf(S.weights)); }));
  function renderWho(list) {
    const keyOf = { know: (p) => MK[p[3]][0], major: (p) => p[1], year: (p) => p[2] }[S.whoTab];
    const all = ALL[S.whoTab]; const counts = {};
    list.forEach((p) => { const k = keyOf(p); counts[k] = (counts[k] || 0) + 1; });
    const rows = Object.keys(all).map((k) => `<tr><td>${esc(k)}</td><td class="n${counts[k] ? '' : ' zero'}">${counts[k] || 0}</td><td class="n">${all[k]}</td></tr>`).join('');
    const none = Object.keys(all).filter((k) => !counts[k]);
    const note = none.length ? `<p class="who__note"><svg class="icon" aria-hidden="true" style="width:18px;height:18px"><use href="#i-info"/></svg>Nobody ${S.whoTab === 'year' ? 'in the year' : S.whoTab === 'major' ? 'from' : 'marked'} ${none.map((k) => (S.whoTab === 'year' && k === 'Freshman' ? 'Freshman' : k)).join(' or ')} is on this list.</p>` : '';
    $('#who-body').innerHTML = `<table><thead><tr><th scope="col">${{ know: 'How much we know', major: 'Major', year: 'Year' }[S.whoTab]}</th><th scope="col" class="n">On this list</th><th scope="col" class="n">All 300</th></tr></thead><tbody>${rows}</tbody></table>${note}`;
  }

  /* -------------------------------------------------------- 4 compare */
  const weightLine = (w) => w.map((x) => x.toFixed(2)).join(' · ');
  function renderCompare() {
    const slots = $('#slots');
    slots.innerHTML = SETTINGS.map((s, i) => `<button type="button" class="slot" aria-pressed="${S.compare.includes(i)}" data-i="${i}"><span class="box" aria-hidden="true"><svg class="icon"><use href="#i-check"/></svg></span>${esc(s.name)}</button>`).join('')
      + '<span class="slot slot--free">Slot 3 of 3 is free. Save the weights on screen to fill it.</span>';
    const body = $('#cmp-body');
    if (S.compare.length < 2) {
      body.innerHTML = `<div class="empty"><img src="${A}pose3-explore.webp" alt="" width="150" height="160"><div><h2 class="h2" style="margin-bottom:6px">Pick two to compare</h2><p class="muted" style="margin:0">Tick two saved settings above. Their lists appear side by side, and names on both lists are marked.</p></div></div>`;
      $('#cmp-bubble').textContent = 'Pick two saved settings. Names on both lists are marked.';
      return;
    }
    const [a, b] = S.compare.map((i) => SETTINGS[i]);
    const la = rankOf(a.w), lb = rankOf(b.w);
    const topA = la.slice(0, 10), topB = lb.slice(0, 10);
    const inB = new Set(topB.map((p) => p[0])), inA = new Set(topA.map((p) => p[0]));
    const shared = topA.filter((p) => inB.has(p[0])).length;
    const col = (s, list, other, tag) => `<div class="card list"><div class="list__head"><h2 class="h2">${esc(s.name)}</h2><span class="wline">${weightLine(s.w)}</span></div><ol class="rows">${list.map((p, i) => compactRow(p, i, other.has(p[0]), tag)).join('')}</ol><p class="small muted" style="margin:6px 0 0;font-weight:700">Showing 10 of 30.</p></div>`;
    body.innerHTML = `<p class="cmp-key"><span class="both-dot" aria-hidden="true"><svg class="icon"><use href="#i-link"/></svg></span>On both lists</p><div class="side" data-tour="side">${col(a, topA, inB, 0)}${col(b, topB, inA, 1)}</div>`;
    $('#cmp-bubble').innerHTML = `<b>${shared} names</b> are on both lists in the first 10. Who drops off when interests count more?`;
    if (!reduced()) $$('.r.is-both', body).forEach((r, i) => r.animate([{ background: 'var(--coral-tint)', transform: 'scale(1)' }, { transform: 'scale(1.01)', offset: .4 }, { transform: 'scale(1)' }], { duration: 420, delay: i * 40 }));
  }
  $('#cmp-body').addEventListener('click', (e) => {
    const t = e.target.closest('.r__toggle'); if (!t) return;
    const open = t.getAttribute('aria-expanded') !== 'true'; t.setAttribute('aria-expanded', open); $(`#${t.getAttribute('aria-controls')}`).hidden = !open;
  });
  $('#slots').addEventListener('click', (e) => {
    const s = e.target.closest('.slot[data-i]'); if (!s) return;
    const i = Number(s.dataset.i);
    S.compare = S.compare.includes(i) ? S.compare.filter((x) => x !== i) : [...S.compare, i].slice(-2);
    renderCompare();
  });
  $('#save-btn').addEventListener('click', () => {
    const name = $('#save-name').value.trim();
    if (!name) { toast('face2-surprised.webp', 'Give it a name first', 'Type a short name, like “Major first”, then save.'); $('#save-name').focus(); return; }
    toast('face1-happy.webp', `Saved as “${name}”`, 'Slot 1 of 3. Two slots are left.');
  });

  /* -------------------------------------------------------- 5/6 results */
  function resetLock() { const l = $('#lock'); l.classList.remove('is-open'); l.querySelector('use').setAttribute('href', '#i-lock'); }
  $('#unlock-btn').addEventListener('click', async () => {
    const l = $('#lock'); l.classList.add('is-open'); l.querySelector('use').setAttribute('href', '#i-unlock');
    if (!reduced()) { l.animate([{ transform: 'translateY(0) rotate(0)' }, { transform: 'translateY(-6px) rotate(-6deg)' }, { transform: 'none' }], { duration: 380, easing: 'cubic-bezier(.34,1.56,.64,1)' }); burst($('#lock-burst'), 12, 70); }
    toast('face4-laugh.webp', 'Results are open', 'See who came. Then talk with your team about why.');
    await wait(700);
    show('open');
  });
  function fillSeats() {
    const seats = $('#seats'); seats.innerHTML = '';
    for (let i = 0; i < 60; i++) { const s = document.createElement('i'); s.className = 'seat'; seats.appendChild(s); }
    const all = $$('.seat', seats);
    const paint = (i, c) => all[i].classList.add(c);
    if (reduced()) { for (let i = 0; i < 8; i++) paint(i, 'taken'); for (let i = 8; i < 14; i++) paint(i, 'yours'); return; }
    for (let i = 0; i < 8; i++) setTimeout(() => paint(i, 'taken'), 200 + i * 30);
    for (let i = 8; i < 14; i++) setTimeout(() => { paint(i, 'yours'); all[i].animate([{ transform: 'scale(.4)' }, { transform: 'scale(1.15)' }, { transform: 'scale(1)' }], { duration: 360, easing: 'cubic-bezier(.34,1.56,.64,1)' }); }, 600 + (i - 8) * 110);
  }

  /* ------------------------------------------------------------ 7 ask */
  function pickAsk(o, focus) {
    S.ask = o.dataset.choice; disarm(false); $('#ask-live').textContent = '';
    $$('#ask-opts .option').forEach((x) => { const on = x === o; x.setAttribute('aria-checked', on); x.tabIndex = on ? 0 : -1; });
    if (focus) o.focus();
    renderCheck();
  }
  $$('#ask-opts .option').forEach((o, i) => { o.tabIndex = i === 0 ? 0 : -1; o.addEventListener('click', () => pickAsk(o)); });
  radioKeys($('#ask-opts'), () => $$('#ask-opts .option'), pickAsk);

  /* --------------------------------------------------------- back + misc */
  $('#back').addEventListener('click', () => { const i = ORDER.indexOf(S.screen); if (i > 0) show(ORDER[i - 1]); });
  const fic = $('#fiction-btn');
  fic.addEventListener('click', () => { const open = fic.getAttribute('aria-expanded') !== 'true'; fic.setAttribute('aria-expanded', open); $('#fiction-pop').hidden = !open; });
  let toastTimer = 0;
  function toast(img, title, text) {
    const t = $('#toast'); $('#toast-img').src = A + img; $('#toast-title').textContent = title; $('#toast-text').textContent = text;
    t.hidden = false;
    if (!reduced()) t.animate([{ opacity: 0, transform: 'translateY(12px)' }, { opacity: 1, transform: 'none' }], { duration: 260, easing: 'cubic-bezier(.16,1,.3,1)' });
    clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, 5200);
  }

  /* ---------------------------------------------------------------- tour */
  const STEPS = [
    { screen: 'entry', target: null, img: 'pose1-guide.webp', title: "Hi, I'm Bree", text: "I'll walk you through the class exercise. It takes about a minute.", next: 'Show me around' },
    { screen: 'entry', target: 'teams', img: 'pose3-explore.webp', title: 'Pick your team', text: "Pick your team's number. Your team's saved work is kept under that number.", place: 'bottom' },
    { screen: 'entry', target: 'path', img: 'pose1-guide.webp', title: 'Follow the path', text: 'Six steps, one choice each. The bar shows where you are. It is not a score.', place: 'bottom' },
    { screen: 'weights', target: 'weights', img: 'pose4-worker.webp', title: 'Set how much each thing counts', text: 'Slide a weight and let go. The list is rebuilt from your numbers.', place: 'right' },
    { screen: 'weights', target: 'list', img: 'pose3-explore.webp', title: 'Read the list', text: 'Each name shows what counted and how much we know about that person.', place: 'left' },
    { screen: 'weights', target: 'next', img: 'pose4-worker.webp', title: 'One button at the bottom', text: 'The big button always does the next thing. Here it saves your weights.', place: 'top' },
    { screen: 'weights', target: null, img: 'pose5-celebrate.webp', title: "You're ready", text: 'Replay this tour any time from the Tour button.', next: 'Finish' },
  ];
  const T = { i: -1, open: false };
  const card = $('#t-card'), hole = $('#t-hole'), blocks = $('#t-blocks');
  $('#t-dots').innerHTML = STEPS.map(() => '<i></i>').join('');
  const seen = () => store.get(TOUR_KEY, null);
  async function openTour(from = 0) {
    T.open = true; card.hidden = false; $('#toast').hidden = true;
    $('#t-dont').checked = !!seen()?.dontShow;
    if (!reduced()) card.animate([{ opacity: 0, transform: 'translateY(16px) scale(.97)' }, { opacity: 1, transform: 'none' }], { duration: 320, easing: 'cubic-bezier(.16,1,.3,1)' });
    await goStep(from, true);
  }
  function closeTour(reason) {
    T.open = false; card.hidden = true; hole.classList.remove('is-on'); blocks.innerHTML = '';
    store.set(TOUR_KEY, { done: true, reason, dontShow: $('#t-dont').checked, team: S.team, at: new Date().toISOString() });
    if (reason === 'skipped') toast('pose2-chill.webp', 'Tour closed', 'Find me under the Tour button whenever you want the walk-through.');
    $('#launcher').focus({ preventScroll: true });
  }
  async function goStep(i, enter = false) {
    const s = STEPS[i]; if (!s) return;
    T.i = i;
    if (visibleName() !== s.screen) show(s.screen, { focus: false, animate: false });
    $('#t-count').textContent = `Step ${i + 1} of ${STEPS.length}`;
    $$('#t-dots i').forEach((d, k) => { d.className = k === i ? 'on' : k < i ? 'done' : ''; });
    $('#t-title').textContent = s.title; $('#t-text').textContent = s.text;
    $('#t-back').hidden = i === 0;
    $('#t-next-label').textContent = s.next || 'Next';
    $('#t-live').textContent = `Step ${i + 1} of ${STEPS.length}. ${s.title}. ${s.text}`;
    const img = $('#t-img');
    if (!img.src.endsWith(s.img) || enter) {
      img.src = A + s.img;
      if (!reduced()) img.animate([{ opacity: 0, transform: 'translateY(14px) scale(.7)' }, { opacity: 1, transform: 'translateY(-4px) scale(1.05)', offset: .65 }, { opacity: 1, transform: 'none' }], { duration: 440, easing: 'cubic-bezier(.34,1.56,.64,1)' });
    }
    const el = s.target ? $(`[data-tour="${s.target}"]`) : null;
    if (el && el.closest('.check, .lesson') === null) {
      const r = el.getBoundingClientRect(); const narrow = innerWidth < 760;
      const want = narrow ? 170 : Math.max(170, (innerHeight - r.height) / 2 - 40);
      window.scrollBy({ top: r.top - want, behavior: reduced() ? 'instant' : 'smooth' });
      await wait(380);
    } else if (!el) window.scrollTo({ top: 0, behavior: 'instant' });
    place();
    $('#t-title').focus({ preventScroll: true });
  }
  function place() {
    if (!T.open) return;
    const s = STEPS[T.i]; const el = s.target ? $(`[data-tour="${s.target}"]`) : null;
    const pad = 10, vw = innerWidth, vh = innerHeight, narrow = vw < 760;
    const r = el ? el.getBoundingClientRect() : null;
    if (r) {
      const x = r.left - pad, y = Math.max(r.top - pad, 50), w = r.width + pad * 2, h = Math.min(r.bottom + pad, vh - 6) - y;
      Object.assign(hole.style, { left: `${x}px`, top: `${y}px`, width: `${w}px`, height: `${h}px` });
      hole.classList.remove('is-center');
      blocks.innerHTML = [[0, 0, vw, Math.max(0, y)], [0, y + h, vw, Math.max(0, vh - y - h)], [0, y, Math.max(0, x), h], [x + w, y, Math.max(0, vw - x - w), h]]
        .map(([l, t, bw, bh]) => `<div class="t-block" style="left:${l}px;top:${t}px;width:${bw}px;height:${bh}px"></div>`).join('');
    } else {
      Object.assign(hole.style, { left: `${vw / 2}px`, top: `${vh / 2}px`, width: '0px', height: '0px' });
      hole.classList.add('is-center'); blocks.innerHTML = '<div class="t-block" style="inset:0"></div>';
    }
    hole.classList.add('is-on');
    if (narrow) { card.style.left = ''; card.style.top = ''; return; }
    const cw = card.offsetWidth, ch = card.offsetHeight, gap = 22;
    let left, top;
    if (!r) { left = (vw - cw) / 2; top = (vh - ch) / 2; }
    else {
      const p = s.place || 'bottom';
      const fitsBelow = r.bottom + gap + ch < vh - 12, fitsAbove = r.top - gap - ch > 60;
      if (p === 'right' && r.right + gap + cw < vw - 12) { left = r.right + gap; top = Math.min(Math.max(60, r.top + 30), vh - ch - 12); }
      else if (p === 'left' && r.left - gap - cw > 12) { left = r.left - gap - cw; top = Math.min(Math.max(60, r.top + 30), vh - ch - 12); }
      else if ((p === 'top' && fitsAbove) || (!fitsBelow && fitsAbove)) top = r.top - gap - ch;
      else if (fitsBelow) top = r.bottom + gap;
      else top = vh - ch - 16;
      if (left === undefined) left = Math.min(Math.max(16, r.left + r.width / 2 - cw / 2), vw - cw - 16);
    }
    card.style.left = `${left}px`; card.style.top = `${top}px`;
  }
  let raf = 0;
  const req = () => { if (T.open && !raf) raf = requestAnimationFrame(() => { raf = 0; place(); }); };
  addEventListener('resize', req); addEventListener('scroll', req, { passive: true });
  $('#t-next').addEventListener('click', () => (T.i >= STEPS.length - 1 ? closeTour('finished') : goStep(T.i + 1)));
  $('#t-back').addEventListener('click', () => goStep(Math.max(0, T.i - 1)));
  $('#t-skip').addEventListener('click', () => closeTour('skipped'));
  $('#t-dont').addEventListener('change', (e) => store.set(TOUR_KEY, { ...(seen() || {}), dontShow: e.target.checked }));
  card.addEventListener('keydown', (e) => {
    if (e.target.matches('input')) return;
    if (e.key === 'ArrowRight') { e.preventDefault(); $('#t-next').click(); }
    if (e.key === 'ArrowLeft' && T.i > 0) { e.preventDefault(); $('#t-back').click(); }
  });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && T.open) closeTour('skipped'); });
  $('#launcher').addEventListener('click', () => openTour(0));

  /* ------------------------------------------------------ review controls */
  $$('[data-jump]').forEach((b) => b.addEventListener('click', () => { applyState('none'); show(b.dataset.jump); }));
  function applyState(st) {
    $$('[data-state]').forEach((b) => b.setAttribute('aria-pressed', b.dataset.state === st && st !== 'none'));
    if (st === 'loading') {
      show('weights', { focus: false }); S.loading = true; setWorker('loading'); renderCheck();
      $('#list-status').className = 'status'; $('#list-status').textContent = 'Rebuilding the list…';
      $('#rows').innerHTML = Array.from({ length: 6 }, () => '<li class="skel" aria-hidden="true"></li>').join('');
    } else if (st === 'error') {
      S.weights = [0, 0, 0, 0]; $$('.factor').forEach((f) => f.syncFromState());
      show('weights', { focus: false }); updateTotal(); setWorker('error');
    } else if (st === 'empty') {
      S.compare = [0]; show('compare', { focus: false });
    } else {
      S.loading = false;
      if (total() <= 0) { S.weights = [0.40, 0.25, 0.25, 0.10]; $$('.factor').forEach((f) => f.syncFromState()); updateTotal(); setWorker('ok'); }
      if (S.compare.length < 2) S.compare = [0, 1];
    }
  }
  $$('[data-state]').forEach((b) => b.addEventListener('click', () => { applyState(b.dataset.state); $('.review__ctl').open = false; }));
  $('#rv-tour').addEventListener('click', () => { $('.review__ctl').open = false; openTour(0); });
  $('#rv-forget').addEventListener('click', () => { store.del(TOUR_KEY); location.reload(); });
  $('#rv-theme').addEventListener('click', () => { const dark = getComputedStyle(html).getPropertyValue('--page').trim().toLowerCase() === '#14112a'; html.dataset.theme = dark ? 'light' : 'dark'; });
  $('#rv-rm').addEventListener('click', (e) => { simRM = !simRM; html.classList.toggle('rm', simRM); e.currentTarget.setAttribute('aria-pressed', simRM); });

  /* ------------------------------------------------------------- start */
  if (qs.get('theme')) html.dataset.theme = qs.get('theme');
  html.classList.toggle('rm', simRM); $('#rv-rm').setAttribute('aria-pressed', simRM);
  if (qs.get('team')) pickTeam(Number(qs.get('team')), false);
  if (qs.get('event')) pickEvent($(`#event-opts [data-event="${qs.get('event')}"]`));
  if (qs.get('ask')) pickAsk($$('#ask-opts .option')[Number(qs.get('ask'))]);
  renderList(false);
  show(qs.get('screen') || 'entry', { focus: false, animate: false });
  if (qs.get('state')) applyState(qs.get('state'));
  if (qs.get('who') === '1') $('#who-btn').click();
  if (qs.get('yay') === '1') { S.yay = true; renderCheck(); }
  const step = qs.get('step');
  if (step !== null && step !== 'none') openTour(Math.max(0, Number(step) - 1));
  else if (step === null && qs.get('tour') !== 'off' && !seen()?.done && !seen()?.dontShow) setTimeout(() => openTour(0), 700);
  window.__mockReady = true;
})();
