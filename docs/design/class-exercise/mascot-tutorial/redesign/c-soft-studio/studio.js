/* Soft Studio mockup: plain script, no libraries. Per-viewer conveniences only in localStorage. */
(function () {
  'use strict';

  /* ---------- helpers ---------- */
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const html = document.documentElement;
  const store = {
    get(k, d = null) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* private mode */ } },
    del(k) { try { localStorage.removeItem(k); } catch (e) { /* ignore */ } },
  };
  const qs = new URLSearchParams(location.search);
  const mqRM = matchMedia('(prefers-reduced-motion: reduce)');
  let simRM = qs.get('rm') === '1' || !!store.get('softstudio.rm', false);
  const reduced = () => simRM || mqRM.matches;
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const A = '../../mockup/assets/';
  const ART = {
    guide: A + 'pose1-guide.webp', chill: A + 'pose2-chill.webp', explore: A + 'pose3-explore.webp',
    worker: A + 'pose4-worker.webp', celebrate: A + 'pose5-celebrate.webp',
    happy: A + 'face1-happy.webp', surprised: A + 'face2-surprised.webp', curious: A + 'face3-curious.webp',
    laugh: A + 'face4-laugh.webp', calm: A + 'face5-calm.webp',
  };
  const MOVES = {
    wave: [[{ transform: 'rotate(0)' }, { transform: 'rotate(-5deg)' }, { transform: 'rotate(4deg)' }, { transform: 'rotate(-3deg)' }, { transform: 'rotate(0)' }], { duration: 1200, easing: 'ease-in-out' }],
    hop: [[{ transform: 'translateY(0) scale(1,1)' }, { transform: 'translateY(2px) scale(1.08,.9)', offset: .15 }, { transform: 'translateY(-24px) scale(.95,1.06)', offset: .4 }, { transform: 'translateY(0) scale(1.05,.93)', offset: .62 }, { transform: 'translateY(-10px) scale(.98,1.03)', offset: .8 }, { transform: 'translateY(0) scale(1,1)' }], { duration: 1100, easing: 'cubic-bezier(.33,0,.2,1)' }],
    peek: [[{ transform: 'rotate(0) translateX(0)' }, { transform: 'rotate(-4deg) translateX(-5px)', offset: .4 }, { transform: 'rotate(2deg) translateX(3px)', offset: .75 }, { transform: 'rotate(0)' }], { duration: 1200, easing: 'ease-in-out' }],
    pop: [[{ opacity: 0, transform: 'translateY(16px) scale(.7)' }, { opacity: 1, transform: 'translateY(-4px) scale(1.05)', offset: .65 }, { opacity: 1, transform: 'none' }], { duration: 460, easing: 'cubic-bezier(.34,1.56,.64,1)' }],
    nod: [[{ transform: 'rotate(0)' }, { transform: 'rotate(-8deg)' }, { transform: 'rotate(6deg)' }, { transform: 'rotate(0)' }], { duration: 520, easing: 'ease-out' }],
  };
  function move(el, name) {
    if (!el || !el.animate) return null;
    if (reduced()) { if (name === 'pop') el.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 150 }); return null; }
    const m = MOVES[name]; return m ? el.animate(m[0], m[1]) : null;
  }
  function applyRM() { html.classList.toggle('rm', simRM); $('#sim-rm').checked = simRM; }

  /* ---------- fictional data: 300 profiles, fixed seed ---------- */
  function rng(seed) { return function () { seed |= 0; seed = seed + 0x6D2B79F5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
  const R = rng(20260928);
  const FIRST = ['Maya', 'Daniel', 'Priya', 'Jordan', 'Alexis', 'Ethan', 'Sofia', 'Marcus', 'Hannah', 'Diego', 'Chloe', 'Ravi', 'Grace', 'Tyler', 'Leila', 'Brandon', 'Nina', 'Kevin', 'Amara', 'Julian', 'Tessa', 'Omar', 'Lucia', 'Wesley', 'Imani', 'Caleb', 'Yuna', 'Mateo', 'Anika', 'Rowan', 'Farah', 'Luis', 'Keiko', 'Dominic', 'Zara', 'Andre', 'Mireya', 'Theo', 'Nadia', 'Isaac'];
  const LAST = ['Tran', 'Okafor', 'Patel', 'Kim', 'Rivera', 'Nguyen', 'Morales', 'Chen', 'Lee', 'Garcia', 'Brooks', 'Shah', 'Park', 'Reyes', 'Haddad', 'Cole', 'Vasquez', 'Yu', 'Mensah', 'Castillo', 'Ibarra', 'Sato', 'Delgado', 'Whitfield', 'Abara', 'Lindqvist', 'Farouk', 'Quintero', 'Oduya', 'Tanaka', 'Ramos', 'Bishop', 'Novak', 'Acosta', 'Pham', 'Estrada', 'Hughes', 'Salazar', 'Moreno', 'Adeyemi'];
  const MAJORS = [['Computer Information Systems', 50], ['International Business & Marketing', 60], ['Accounting', 50], ['Finance, Real Estate & Law', 45], ['Management & Human Resources', 45], ['Technology & Operations Management', 50]];
  const YEARS = [['Senior', 90], ['Junior', 80], ['Sophomore', 70], ['Freshman', 60]];
  const YEAR_RANK = { Senior: 4, Junior: 3, Sophomore: 2, Freshman: 1 };
  const MARK = { card: 'completed card', events: 'major plus events attended', major: 'major only' };
  const MARK_RANK = { card: 2, events: 1, major: 0 };
  const TARGET = 'Computer Information Systems';
  const expand = (pairs) => pairs.flatMap(([v, n]) => Array(n).fill(v));
  const majors = expand(MAJORS), years = expand(YEARS);
  const shuffle = (a) => { for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(R() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; };
  shuffle(majors); shuffle(years);
  const PEOPLE = Array.from({ length: 300 }, (_, i) => {
    const card = R() < 0.235, attended = R() < 0.33;
    const mark = card ? 'card' : attended ? 'events' : 'major';
    const major = majors[i], year = years[i];
    const f = [major === TARGET ? 1 : 0, card && R() < 0.5 ? 1 : 0, card && R() < 0.42 ? 1 : 0, attended && R() < 0.55 ? 1 : 0];
    return { i, name: `${FIRST[i % 40]} ${LAST[(Math.floor(i / 40) * 11 + i * 7 + 3) % 40]}`, major, year, mark, f };
  });
  const FACTORS = ['same major', 'said they are interested in this topic', 'career goal fits this event', 'went to similar events before'];
  const LIMIT = 30;
  function rankOf(w) {
    const tot = w.reduce((a, b) => a + b, 0) || 1;
    return PEOPLE.map((p) => ({ p, s: p.f.reduce((a, x, k) => a + x * w[k], 0) / tot }))
      .sort((a, b) => b.s - a.s || MARK_RANK[b.p.mark] - MARK_RANK[a.p.mark] || YEAR_RANK[b.p.year] - YEAR_RANK[a.p.year] || a.p.i - b.p.i)
      .slice(0, LIMIT).map((x) => x.p);
  }
  function reasonFor(p, w) {
    const on = FACTORS.filter((_, k) => p.f[k] && w[k] > 0);
    if (!on.length) return 'Nothing on file counted for this event.';
    if (on.length === 1 && on[0] === 'same major') return p.mark === 'major' ? 'Same major; nothing else on file.' : 'Tied on major; ordered by year.';
    return `What counted: ${on.join('; ')}.`;
  }

  /* ---------- screens + storybook deck ---------- */
  const STEP_OF = { team: 0, event: 1, build: 2, compare: 2, results: 3, ask: 4 };
  let screen = 'team';
  const walker = $('#walker');
  let walkerX = null;
  function placeWalker(animate) {
    const cur = $('.deck__card[aria-current="step"]'); if (!cur) return;
    const deck = $('.deck');
    const d = deck.getBoundingClientRect(), c = cur.getBoundingClientRect();
    const w = walker.getBoundingClientRect().width || 50;
    const x = Math.round(c.left - d.left + c.width / 2 - w / 2);
    if (walkerX === x) return;
    const goingLeft = walkerX !== null && x < walkerX;
    if (!animate || reduced() || walkerX === null) {
      walker.style.transition = 'none'; walker.style.setProperty('--wx', `${x}px`); walker.getBoundingClientRect(); walker.style.transition = '';
    } else {
      walker.classList.toggle('is-flipped', goingLeft);
      walker.classList.add('is-walking');
      walker.style.setProperty('--wx', `${x}px`);
      clearTimeout(placeWalker.t); placeWalker.t = setTimeout(() => { walker.classList.remove('is-walking', 'is-flipped'); }, 900);
    }
    walkerX = x;
  }
  function paintDeck() {
    const step = STEP_OF[screen];
    $$('.deck__card').forEach((b) => {
      const n = Number(b.dataset.step);
      if (n === step) b.setAttribute('aria-current', 'step'); else b.removeAttribute('aria-current');
      b.classList.toggle('is-done', n < step);
      const label = b.querySelector('.deck__label').textContent;
      b.setAttribute('aria-label', `${label}${n < step ? ', done' : n === step ? ', current step' : ''}`);
    });
  }
  function show(name, { focus = true, animate = true } = {}) {
    if (!$(`[data-screen="${name}"]`)) return;
    const changed = name !== screen;
    screen = name;
    $$('.screen').forEach((s) => { s.hidden = s.dataset.screen !== name; });
    $$('.review__nav button').forEach((b) => { if (b.dataset.go === name) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current'); });
    paintDeck();
    requestAnimationFrame(() => placeWalker(animate && changed));
    if (changed) window.scrollTo({ top: 0, behavior: 'instant' });
    const el = $(`[data-screen="${name}"]`);
    if (changed && animate && !reduced()) el.animate([{ opacity: 0, transform: 'translateY(10px)' }, { opacity: 1, transform: 'none' }], { duration: 320, easing: 'cubic-bezier(.16,1,.3,1)' });
    if (focus) el.querySelector('.h1')?.focus({ preventScroll: true });
    onScreen(name, changed);
  }
  document.addEventListener('click', (e) => {
    const go = e.target.closest('[data-go]');
    if (!go || go.matches('[aria-disabled="true"]')) return;
    if (go.tagName === 'A') e.preventDefault();
    show(go.dataset.go);
  });
  function onScreen(name, changed) {
    if (name === 'team' && changed) move($('#hero-mascot'), 'wave');
    if (name === 'build') renderWho();
    if (name === 'compare') renderCompare();
  }

  /* ---------- 1 Team ---------- */
  let team = null;
  const tiles = $('#tiles');
  for (let n = 1; n <= 6; n++) {
    const b = document.createElement('button');
    b.type = 'button'; b.className = 'tile'; b.textContent = n; b.setAttribute('role', 'radio');
    b.setAttribute('aria-checked', 'false'); b.setAttribute('aria-label', `Team ${n}`); b.tabIndex = n === 1 ? 0 : -1;
    tiles.appendChild(b);
  }
  function pickTeam(n, focus) {
    team = n;
    $$('.tile', tiles).forEach((t, k) => { const on = k + 1 === n; t.setAttribute('aria-checked', String(on)); t.tabIndex = on ? 0 : -1; if (on && focus) t.focus(); });
    const open = $('#open-team');
    open.setAttribute('aria-disabled', 'false'); open.firstChild.textContent = `Open team ${n}'s work`;
    $('#team-nudge').hidden = true;
    $('#team-chip').hidden = false; $('#team-chip-n').textContent = `Team ${n}`;
    requestAnimationFrame(() => placeWalker(false));
  }
  tiles.addEventListener('click', (e) => { const t = e.target.closest('.tile'); if (t) pickTeam(Number(t.textContent)); });
  tiles.addEventListener('keydown', (e) => {
    const k = $$('.tile', tiles).indexOf(document.activeElement); if (k < 0) return;
    const d = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
    if (d) { e.preventDefault(); pickTeam(((k + d + 6) % 6) + 1, true); }
  });
  $('#open-team').addEventListener('click', (e) => {
    if (team) { show('event'); return; }
    const n = $('#team-nudge'); n.hidden = false; move(n.querySelector('img'), 'nod');
    $$('.tile', tiles)[0].focus();
  });

  /* ---------- 2 Event: past events on demand ---------- */
  $('#past').innerHTML = ['Deloitte Day: Audit in Practice', 'Retail Futures Panel', 'Supply Chain Night', 'Data Careers Mixer', 'Women in Finance Breakfast', 'Startup Pitch Hour', 'Marketing Analytics Workshop', 'Real Estate Walkthrough', 'HR Leaders Q&A', 'Cloud Skills Bootcamp']
    .map((t) => `<li>${t}</li>`).join('');

  /* ---------- 3 Weights + list ---------- */
  const weights = [0.25, 0.25, 0.25, 0.25];
  const sliders = $('#sliders');
  FACTORS.forEach((label, k) => {
    const id = `w${k}`;
    const row = document.createElement('div'); row.className = 'w-row';
    const nice = label.charAt(0).toUpperCase() + label.slice(1);
    row.innerHTML = `<label for="${id}"><span>${nice}</span><output class="w-val" for="${id}">${weights[k].toFixed(2)}</output></label><input type="range" id="${id}" min="0" max="1" step="0.05" value="${weights[k]}" aria-valuetext="${weights[k].toFixed(2)}">`;
    sliders.appendChild(row);
    const range = row.querySelector('input'), out = row.querySelector('output');
    const paint = () => { range.style.setProperty('--fill', `${range.value * 100}%`); out.textContent = Number(range.value).toFixed(2); range.setAttribute('aria-valuetext', Number(range.value).toFixed(2)); };
    paint();
    range.addEventListener('input', () => { weights[k] = Number(range.value); paint(); updateTotal(); });
    range.addEventListener('change', rebuild);
    range.addEventListener('keyup', (e) => { if (e.key === 'Enter') rebuild(); });
  });
  function updateTotal() {
    const t = weights.reduce((a, b) => a + b, 0);
    $('#total').textContent = `Total weight: ${t.toFixed(2)}`;
    const z = $('#zero-nudge'); const was = z.hidden; z.hidden = t > 0; $('#ranked').classList.toggle('is-busy', t <= 0);
    if (was && !z.hidden) move(z.querySelector('img'), 'nod');
  }
  const ranked = $('#ranked');
  let whoBy = 'major';
  let showAll = false, lastNames = null;
  const markerHtml = (m) => `<span class="marker marker--${m}"><svg class="icon" aria-hidden="true"><use href="#i-${m === 'card' ? 'idcard' : m === 'events' ? 'dot' : 'ring'}"/></svg>${MARK[m]}</span>`;
  function renderList(animate) {
    const first = new Map($$('.row', ranked).map((r) => [r.dataset.name, r.getBoundingClientRect().top]));
    const list = rankOf(weights);
    const shown = showAll ? list : list.slice(0, 10);
    ranked.innerHTML = shown.map((p, k) => `<li class="row" data-name="${p.name}"><button type="button" class="row__main" aria-expanded="false"><span class="rank">${k + 1}</span><span><span class="row__line"><span class="name">${p.name}</span>${markerHtml(p.mark)}</span><span class="reason">${reasonFor(p, weights)}</span></span></button><p class="row__more" hidden><span>${p.major}</span><span>${p.year}</span></p></li>`).join('');
    const prev = lastNames; lastNames = new Set(list.map((p) => p.name));
    renderWho();
    if (!animate) return;
    $$('.row', ranked).forEach((r) => {
      const was = first.get(r.dataset.name);
      if (was === undefined) {
        if (prev && !prev.has(r.dataset.name)) { r.classList.add('is-new'); setTimeout(() => r.classList.remove('is-new'), 1400); }
        return;
      }
      const dy = was - r.getBoundingClientRect().top;
      if (dy && !reduced()) r.animate([{ transform: `translateY(${dy}px)` }, { transform: 'none' }], { duration: 420, easing: 'cubic-bezier(.2,.9,.25,1)' });
    });
  }
  ranked.addEventListener('click', (e) => {
    const b = e.target.closest('.row__main'); if (!b) return;
    const open = b.getAttribute('aria-expanded') !== 'true';
    b.setAttribute('aria-expanded', String(open)); b.nextElementSibling.hidden = !open;
  });
  $('#show-all').addEventListener('click', (e) => {
    showAll = !showAll; e.currentTarget.textContent = showAll ? 'Show the first 10' : 'Show all 30'; e.currentTarget.setAttribute('aria-expanded', String(showAll));
    renderList(false);
  });
  async function rebuild() {
    if (weights.reduce((a, b) => a + b, 0) <= 0) return;
    const w = $('#working');
    ranked.classList.add('is-busy'); w.classList.add('is-on'); $('#rebuild-live').textContent = 'Re-sorting the list…';
    await wait(reduced() ? 150 : 650);
    renderList(true);
    ranked.classList.remove('is-busy'); w.classList.remove('is-on'); $('#rebuild-live').textContent = 'The list was re-sorted.';
  }
  renderList(false);

  /* Who is on the list: counts only, never shares */
  function renderWho() {
    const list = rankOf(weights);
    const groups = whoBy === 'major' ? MAJORS.map((m) => m[0]) : whoBy === 'year' ? ['Freshman', 'Sophomore', 'Junior', 'Senior'] : ['major', 'events', 'card'];
    const key = whoBy === 'major' ? 'major' : whoBy === 'year' ? 'year' : 'mark';
    const label = (g) => whoBy === 'known' ? MARK[g] : g;
    const rows = groups.map((g) => { const on = list.filter((p) => p[key] === g).length, all = PEOPLE.filter((p) => p[key] === g).length; return { g, on, all }; });
    $('#who-panel').innerHTML = `<table class="who"><thead><tr><th scope="col">${whoBy === 'known' ? 'How much we know' : whoBy === 'year' ? 'Year' : 'Major'}</th><th scope="col">On this list</th><th scope="col">All 300</th></tr></thead><tbody>${rows.map((r) => `<tr><th scope="row">${label(r.g)}</th><td class="${r.on === 0 ? 'zero' : ''}">${r.on}</td><td>${r.all}</td></tr>`).join('')}</tbody></table>`;
    const missingYears = ['Freshman', 'Sophomore', 'Junior', 'Senior'].filter((y) => !list.some((p) => p.year === y));
    const missingMajors = MAJORS.map((m) => m[0]).filter((m) => !list.some((p) => p.major === m));
    const miss = [...missingYears.map((y) => `a ${y}`), ...missingMajors.map((m) => `${/^[AEIOU]/.test(m) ? 'an' : 'a'} ${m} major`)];
    const note = $('#gap-note');
    if (miss.length) { note.hidden = false; $('#gap-text').textContent = `Nobody on this list is ${miss.slice(0, 2).join(' or ')}.`; } else note.hidden = true;
  }
  const tabs = $$('.tabs [role="tab"]');
  function pickTab(t, focus) {
    tabs.forEach((x) => { const on = x === t; x.setAttribute('aria-selected', String(on)); x.tabIndex = on ? 0 : -1; });
    $('#who-panel').setAttribute('aria-labelledby', t.id); whoBy = t.dataset.by; renderWho(); if (focus) t.focus();
  }
  tabs.forEach((t) => t.addEventListener('click', () => pickTab(t)));
  $('.tabs').addEventListener('keydown', (e) => {
    const k = tabs.indexOf(document.activeElement); const d = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
    if (k >= 0 && d) { e.preventDefault(); pickTab(tabs[(k + d + tabs.length) % tabs.length], true); }
  });

  /* Save: success toast with the happy face */
  const saved = [
    { name: 'Major first', w: [0.55, 0.15, 0.15, 0.15] },
    { name: 'Interests first', w: [0.15, 0.45, 0.25, 0.15] },
  ];
  $('#save-form').addEventListener('submit', (e) => {
    e.preventDefault();
    const name = $('#save-name').value.trim() || 'Untitled';
    if (saved.length < 3) saved.push({ name, w: weights.slice() }); else saved[2] = { name, w: weights.slice() };
    toast('happy', `Saved as “${name}”. Slot ${Math.min(saved.length, 3)} of 3.`);
    $('#save-more').open = false;
  });
  let toastT = 0;
  function toast(face, text) {
    const t = $('#toast'); $('#toast-face').src = ART[face]; $('#toast-text').textContent = text; t.hidden = false;
    if (!reduced()) { t.animate([{ opacity: 0, transform: 'translateY(14px) scale(.96)' }, { opacity: 1, transform: 'none' }], { duration: 300, easing: 'cubic-bezier(.34,1.56,.64,1)' }); move($('#toast-face'), 'nod'); }
    clearTimeout(toastT); toastT = setTimeout(() => { t.hidden = true; }, 4200);
  }

  /* ---------- 4 Save + compare ---------- */
  function renderCompare() {
    const slots = $('#slots');
    const card = (s, k) => `<article class="slot" data-slot="${k ? 'b' : 'a'}"><div class="slot__top"><span class="slot__tag">${k ? 'B' : 'A'}</span><h2 class="slot__name">${s.name}</h2><span class="slot__on">Comparing</span></div><details><summary><svg class="icon" aria-hidden="true"><use href="#i-chev"/></svg>Weights</summary><dl>${FACTORS.map((f, j) => `<dt>${f.charAt(0).toUpperCase() + f.slice(1)}</dt><dd>${s.w[j].toFixed(2)}</dd>`).join('')}</dl></details></article>`;
    const third = saved[2]
      ? `<article class="slot"><div class="slot__top"><span class="slot__tag" style="background:var(--sunk);color:var(--ink)">3</span><h2 class="slot__name">${saved[2].name}</h2></div><details><summary><svg class="icon" aria-hidden="true"><use href="#i-chev"/></svg>Weights</summary><dl>${FACTORS.map((f, j) => `<dt>${f}</dt><dd>${saved[2].w[j].toFixed(2)}</dd>`).join('')}</dl></details></article>`
      : `<article class="slot slot--empty"><div class="plate plate--peach"><img class="mascot" src="${ART.explore}" alt="" width="264" height="303"></div><div><p>Slot 3 is free.</p><button type="button" class="btn btn--text btn--sm" data-go="build">Save weights to fill it</button></div></article>`;
    slots.innerHTML = card(saved[0], 0) + card(saved[1], 1) + third;
    const a = rankOf(saved[0].w), b = rankOf(saved[1].w);
    const inB = new Set(b.map((p) => p.name)), inA = new Set(a.map((p) => p.name));
    const both = a.filter((p) => inB.has(p.name)).length;
    $('#overlap').innerHTML = `<svg class="icon" aria-hidden="true"><use href="#i-link"/></svg>${both} names are on both lists.`;
    const li = (p, k, shared) => `<li class="${shared ? 'is-both' : ''}"><span class="rank">${k + 1}</span><span class="nm">${p.name}</span><span class="both"><svg class="icon" aria-hidden="true"><use href="#i-link"/></svg>On both</span></li>`;
    $('#cmp-a-h').innerHTML = `<span class="slot__tag">A</span>${saved[0].name}`;
    $('#cmp-b-h').innerHTML = `<span class="slot__tag">B</span>${saved[1].name}`;
    $('#cmp-a').innerHTML = a.map((p, k) => li(p, k, inB.has(p.name))).join('');
    $('#cmp-b').innerHTML = b.map((p, k) => li(p, k, inA.has(p.name))).join('');
  }
  $$('.ab-switch [role="tab"]').forEach((t) => t.addEventListener('click', () => {
    $$('.ab-switch [role="tab"]').forEach((x) => { const on = x === t; x.setAttribute('aria-selected', String(on)); x.tabIndex = on ? 0 : -1; });
    $('#compare').dataset.show = t.dataset.show;
  }));

  /* ---------- 5 Results: locked -> open -> running -> done ---------- */
  const seatsEl = $('#seats');
  for (let k = 0; k < 60; k++) { const s = document.createElement('i'); s.className = 'seat'; seatsEl.appendChild(s); }
  const LEADS = {
    locked: 'Results open when your instructor says so.',
    open: 'Run your team’s final setting once to see who came.',
    running: 'Run your team’s final setting once to see who came.',
    done: 'Here is who came, next to emailing all 300.',
  };
  let rstate = 'locked';
  async function setResults(st, { animate = true } = {}) {
    rstate = st;
    const map = { locked: '#st-locked', open: '#st-open', running: '#st-running', done: '#st-done' };
    Object.entries(map).forEach(([k, sel]) => { $(sel).hidden = k !== st; });
    $('#results-lead').textContent = LEADS[st];
    $$('input[name="rstate"]').forEach((r) => { r.checked = r.value === (st === 'running' ? 'open' : st); });
    const shown = $(map[st]).querySelector('.mascot');
    if (animate && screen === 'results') move(shown, st === 'done' ? 'hop' : 'pop');
    if (st === 'locked' || st === 'open') { $(map[st]).querySelector('.mascot')?.classList.add('is-idle'); }
    if (st === 'done') await fillSeats(animate);
  }
  async function fillSeats(animate) {
    const seats = $$('.seat', seatsEl); seats.forEach((s) => { s.className = 'seat'; });
    const out = $('#sentences'); out.innerHTML = '';
    const lines = ['8 were already coming.', 'Your list added 6.', '46 seats are still empty.'];
    if (!animate || reduced()) {
      for (let k = 0; k < 8; k++) seats[k].classList.add('taken');
      for (let k = 8; k < 14; k++) seats[k].classList.add('yours');
      out.innerHTML = lines.map((l) => `<p>${l}</p>`).join('');
      return;
    }
    const say = (l) => { const p = document.createElement('p'); p.textContent = l; out.appendChild(p); p.animate([{ opacity: 0, transform: 'translateY(8px)' }, { opacity: 1, transform: 'none' }], { duration: 280, easing: 'cubic-bezier(.16,1,.3,1)' }); };
    await wait(200);
    for (let k = 0; k < 8; k++) setTimeout(() => seats[k].classList.add('taken'), k * 40);
    say(lines[0]); await wait(620);
    for (let k = 8; k < 14; k++) setTimeout(() => { seats[k].classList.add('yours'); seats[k].animate([{ transform: 'scale(.6)' }, { transform: 'scale(1.12)' }, { transform: 'scale(1)' }], { duration: 340, easing: 'cubic-bezier(.34,1.56,.64,1)' }); }, (k - 8) * 90);
    say(lines[1]); await wait(800);
    seats.slice(14).forEach((s, k) => s.animate([{ opacity: 1 }, { opacity: .35 }, { opacity: 1 }], { duration: 500, delay: k * 6 }));
    say(lines[2]);
  }
  $('#mock-unlock').addEventListener('click', () => setResults('open'));
  $('#run').addEventListener('click', async () => {
    await setResults('running');
    await wait(reduced() ? 300 : 1500);
    await setResults('done');
    $('#celebrate').focus?.();
  });
  $$('input[name="rstate"]').forEach((r) => r.addEventListener('change', () => { setResults(r.value, { animate: false }); if (screen !== 'results') show('results'); }));

  /* ---------- 6 Asking for more: Duolingo-style check bar ---------- */
  let choice = null, asked = false;
  const choices = $$('.choice');
  const CHOICE_NAME = { 1: 'promising better recommendations', 2: 'offering a small reward', 3: 'making it required' };
  function pick(n, focus) {
    choice = n;
    choices.forEach((c) => { const on = Number(c.dataset.choice) === n; c.setAttribute('aria-checked', String(on)); c.tabIndex = on ? 0 : -1; if (on && focus) c.focus(); });
    if (!asked) setCheck('idle');
  }
  choices.forEach((c) => c.addEventListener('click', () => pick(Number(c.dataset.choice))));
  $('#choices').addEventListener('keydown', (e) => {
    const k = choices.indexOf(document.activeElement);
    const d = { ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1 }[e.key];
    if (k >= 0 && d) { e.preventDefault(); pick(((k + d + 3) % 3) + 1, true); }
  });
  document.addEventListener('keydown', (e) => {
    if (screen !== 'ask' || tour.open || asked || e.target.matches('input, textarea')) return;
    if (['1', '2', '3'].includes(e.key)) pick(Number(e.key), true);
  });
  function setCheck(st, text) {
    const bar = $('#checkbar'); bar.dataset.state = st;
    const face = { error: 'surprised', asked: 'laugh', idle: 'surprised' }[st];
    $('#check-face').src = ART[face]; $('#check-text').textContent = text || '';
    const btn = $('#ask-go');
    btn.textContent = st === 'asked' ? 'Refresh our profiles' : 'Ask this way';
    if (st !== 'idle') move($('#check-face'), st === 'error' ? 'nod' : 'pop');
  }
  $('#ask-go').addEventListener('click', async () => {
    if (asked) {
      $('#ask-main').hidden = true; $('#checkbar').hidden = true; $('#ask-done').hidden = false;
      move($('#ask-done .mascot'), 'hop'); $('#h-done').focus({ preventScroll: true }); window.scrollTo({ top: 0, behavior: 'instant' });
      return;
    }
    if (!choice) { setCheck('error', 'Pick one way first.'); return; }
    asked = true; choices.forEach((c) => { c.setAttribute('aria-disabled', 'true'); });
    setCheck('asked', `Asked by ${CHOICE_NAME[choice]}.`);
  });
  function resetAsk() {
    asked = false; choice = null;
    choices.forEach((c) => { c.setAttribute('aria-checked', 'false'); c.removeAttribute('aria-disabled'); });
    $('#ask-main').hidden = false; $('#checkbar').hidden = false; $('#ask-done').hidden = true; setCheck('idle');
  }

  /* ---------- Tour ---------- */
  const TOUR_KEY = 'softstudio.tour.v1';
  const STEPS = [
    { screen: 'team', target: null, art: 'guide', move: 'wave', title: "Hi, I'm Bree", text: "I'll show you around the class exercise. It takes about a minute.", next: 'Show me around' },
    { screen: 'team', target: 'teams', art: 'explore', move: 'peek', title: 'Pick your team', text: "Your team's saved work is kept under its number.", place: 'bottom' },
    { screen: 'team', target: 'deck', art: 'chill', move: 'pop', title: 'Follow the path', text: 'Five steps, left to right. I walk along so you always know where you are.', place: 'bottom' },
    { screen: 'build', target: 'weights', art: 'worker', move: 'pop', title: 'Decide what counts', text: 'Slide a weight and let go. What matters is how the weights compare.', place: 'right' },
    { screen: 'build', target: 'list', art: 'explore', move: 'peek', title: 'Read the list', text: 'Each name shows what counted, and how much we know about them. Tap a name for more.', place: 'left' },
    { screen: 'build', target: 'summary', art: 'curious', move: 'nod', title: 'Look for who is missing', text: 'Count the list by major, year and how much we know, next to all 300.', place: 'left' },
    { screen: 'build', target: 'run', art: 'celebrate', move: 'hop', title: "You're ready", text: 'Save the weights you like, then go to results. Replay me from the Tour button.', place: 'top', next: 'Finish' },
  ];
  const tour = { i: -1, open: false };
  const card = $('#tour'), hole = $('#tour-hole'), blocks = $('#tour-blocks');
  $('#tour-dots').innerHTML = STEPS.map(() => '<i></i>').join('');
  const seen = () => store.get(TOUR_KEY, null);
  async function openTour(from) {
    tour.open = true; card.hidden = false; $('#launcher').setAttribute('aria-expanded', 'true'); $('#toast').hidden = true;
    $('#tour-dont').checked = !!(seen() && seen().dontShow);
    if (!reduced()) card.animate([{ opacity: 0, transform: 'translateY(16px) scale(.97)' }, { opacity: 1, transform: 'none' }], { duration: 320, easing: 'cubic-bezier(.16,1,.3,1)' });
    await goStep(from || 0, true);
  }
  function closeTour(reason) {
    tour.open = false; card.hidden = true; hole.classList.remove('is-on'); blocks.innerHTML = ''; $('#launcher').setAttribute('aria-expanded', 'false');
    store.set(TOUR_KEY, { done: true, reason, dontShow: $('#tour-dont').checked, at: new Date().toISOString() });
    if (reason === 'skipped') toast('calm', 'Tour closed. Find me under Tour, top right.');
    $('#launcher').focus({ preventScroll: true });
  }
  async function goStep(k, enter) {
    const s = STEPS[k]; if (!s) return;
    tour.i = k;
    if (screen !== s.screen) show(s.screen, { focus: false });
    $('#tour-count').textContent = `Step ${k + 1} of ${STEPS.length}`;
    $$('#tour-dots i').forEach((d, j) => d.classList.toggle('on', j === k));
    $('#tour-title').textContent = s.title; $('#tour-text').textContent = s.text;
    $('#tour-back').hidden = k === 0;
    $('#tour-next-label').textContent = s.next || 'Next';
    $('#tour-live').textContent = `Step ${k + 1} of ${STEPS.length}. ${s.title}. ${s.text}`;
    const img = $('#tour-img');
    if (img.getAttribute('src') !== ART[s.art]) { img.src = ART[s.art]; try { await img.decode(); } catch (e) { /* keep going */ } }
    const el = s.target ? $(`[data-tour="${s.target}"]`) : null;
    if (el) {
      const r = el.getBoundingClientRect(); const narrow = innerWidth < 760;
      const want = narrow ? 110 : Math.max(90, (innerHeight - Math.min(r.height, innerHeight * .7)) / 2 - 20);
      window.scrollBy({ top: r.top - want, behavior: reduced() ? 'instant' : 'smooth' });
      await wait(reduced() ? 0 : 380);
    } else window.scrollTo({ top: 0, behavior: 'instant' });
    place();
    move(img, enter ? 'pop' : s.move);
    $('#tour-title').focus({ preventScroll: true });
  }
  function place() {
    if (!tour.open) return;
    const s = STEPS[tour.i];
    const el = s.target ? $(`[data-tour="${s.target}"]`) : null;
    const pad = 10, vw = innerWidth, vh = innerHeight, narrow = vw < 760;
    const r = el ? el.getBoundingClientRect() : null;
    if (r) {
      const x = r.left - pad, y = Math.max(r.top - pad, 56), w = r.width + pad * 2, h = Math.max(40, Math.min(r.bottom + pad, vh - 12) - y);
      Object.assign(hole.style, { left: `${x}px`, top: `${y}px`, width: `${w}px`, height: `${h}px` });
      hole.classList.remove('is-center');
      blocks.innerHTML = [[0, 0, vw, Math.max(0, y)], [0, y + h, vw, Math.max(0, vh - y - h)], [0, y, Math.max(0, x), h], [x + w, y, Math.max(0, vw - x - w), h]]
        .map(([l, t, bw, bh]) => `<div class="tour-block" style="left:${l}px;top:${t}px;width:${bw}px;height:${bh}px"></div>`).join('');
    } else {
      Object.assign(hole.style, { left: `${vw / 2}px`, top: `${vh / 2}px`, width: '0px', height: '0px' });
      hole.classList.add('is-center'); blocks.innerHTML = '<div class="tour-block" style="inset:0"></div>';
    }
    hole.classList.add('is-on');
    if (narrow) { card.style.left = ''; card.style.top = ''; return; }
    const cw = card.offsetWidth, ch = card.offsetHeight, gap = 18;
    let left, top;
    if (!r) { left = (vw - cw) / 2; top = (vh - ch) / 2; }
    else {
      const p = s.place || 'bottom';
      const below = r.bottom + gap + ch < vh - 12, above = r.top - gap - ch > 60;
      if (p === 'right' && r.right + gap + cw < vw - 12) { left = r.right + gap; top = Math.min(Math.max(64, r.top + 20), vh - ch - 12); }
      else if (p === 'left' && r.left - gap - cw > -60) { left = Math.max(16, r.left - gap - cw); top = Math.min(Math.max(64, r.top + 20), vh - ch - 12); }
      else if ((p === 'top' && above) || (!below && above)) top = r.top - gap - ch;
      else if (below) top = r.bottom + gap;
      else top = vh - ch - 16;
      if (left === undefined) left = Math.min(Math.max(16, r.left + r.width / 2 - cw / 2), vw - cw - 16);
    }
    card.style.left = `${left}px`; card.style.top = `${top}px`;
  }
  let raf = 0;
  const req = () => { if (!raf) raf = requestAnimationFrame(() => { raf = 0; if (tour.open) place(); placeWalker(false); }); };
  addEventListener('resize', req); addEventListener('scroll', () => { if (tour.open) req(); }, { passive: true });
  $('#tour-next').addEventListener('click', () => (tour.i >= STEPS.length - 1 ? closeTour('finished') : goStep(tour.i + 1)));
  $('#tour-back').addEventListener('click', () => goStep(Math.max(0, tour.i - 1)));
  $('#tour-skip').addEventListener('click', () => closeTour('skipped'));
  $('#tour-dont').addEventListener('change', (e) => store.set(TOUR_KEY, Object.assign({}, seen() || {}, { dontShow: e.target.checked })));
  card.addEventListener('keydown', (e) => {
    if (e.target.matches('input')) return;
    if (e.key === 'ArrowRight') { e.preventDefault(); $('#tour-next').click(); }
    if (e.key === 'ArrowLeft' && tour.i > 0) { e.preventDefault(); $('#tour-back').click(); }
    if (e.key === 'Tab') { // keep focus inside the card while it is open
      const f = $$('button:not([hidden]), input, [tabindex="-1"]#tour-title', card).filter((x) => !x.closest('[hidden]'));
      const first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && tour.open) closeTour('skipped'); });
  $('#launcher').addEventListener('click', () => openTour(0));

  /* ---------- Review controls ---------- */
  $('#sim-rm').addEventListener('change', (e) => { simRM = e.target.checked; store.set('softstudio.rm', simRM); applyRM(); });
  $('#ctl-tour').addEventListener('click', () => { $('#review-ctl').open = false; openTour(0); });
  $('#ctl-reset').addEventListener('click', () => { store.del(TOUR_KEY); location.search = ''; });
  $('#ctl-theme').addEventListener('click', () => {
    const dark = getComputedStyle(html).getPropertyValue('--page').trim().toLowerCase() === '#1c1513';
    html.dataset.theme = dark ? 'light' : 'dark';
  });
  mqRM.addEventListener('change', applyRM);
  applyRM();

  /* ---------- Deep links: ?screen=build&team=4&results=done&ask=2&asked=1&step=3|none&theme=dark&rm=1&all=1 ---------- */
  if (qs.get('theme')) html.dataset.theme = qs.get('theme');
  if (qs.get('team')) pickTeam(Number(qs.get('team')));
  if (qs.get('all') === '1') $('#show-all').click();
  const rs = qs.get('results'); setResults(rs && ['locked', 'open', 'running', 'done'].includes(rs) ? rs : 'locked', { animate: false });
  if (qs.get('ask')) { pick(Number(qs.get('ask'))); if (qs.get('asked') === '1') $('#ask-go').click(); if (qs.get('asked') === 'done') { $('#ask-go').click(); $('#ask-go').click(); } }
  if (qs.get('askerr') === '1') setCheck('error', 'Pick one way first.');
  if (qs.get('nudge') === '1') $('#open-team').click();
  if (qs.get('zero') === '1') { weights.fill(0); $$('#sliders input').forEach((r) => { r.value = 0; r.dispatchEvent(new Event('input')); }); }
  show(qs.get('screen') || 'team', { focus: false, animate: false });
  $('#hero-mascot').classList.add('is-idle');
  if (qs.get('toast')) toast('happy', 'Saved as “Major first”. Slot 1 of 3.');
  document.fonts && document.fonts.ready.then(() => placeWalker(false));
  addEventListener('load', () => placeWalker(false));
  const stepParam = qs.get('step');
  if (stepParam !== null) { if (stepParam !== 'none') setTimeout(() => openTour(Math.max(0, Number(stepParam) - 1)), 50); }
  else if (!(seen() && (seen().done || seen().dontShow))) setTimeout(() => openTour(0), 700);
  window.__resetAsk = resetAsk;
  window.__ready = true;
})();
