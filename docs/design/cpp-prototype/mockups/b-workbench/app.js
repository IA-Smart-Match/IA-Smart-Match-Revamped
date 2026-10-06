/* Smart Match CPP — Direction B: Workbench. Static mockup, no network, no build step.
 * Layout of this file (DESIGN.md section 10.3): helpers, motion, state, copy, one function per
 * component (render*), one per screen (screen*), then the shell, the switcher, the guide and boot.
 * All people, events and numbers come from window.SMC (../../shared/data.js). */
(function () {
  "use strict";
  const SMC = window.SMC, gsap = window.gsap, Flip = window.Flip;
  gsap.registerPlugin(Flip);

  /* ---------- motion tokens (DESIGN.md 8.2) ---------- */
  const SM_MOTION = {
    dur: { instant: 0.10, fast: 0.16, base: 0.22, move: 0.28, max: 0.40, wash: 0.90 },
    ease: { out: "expo.out", inOut: "power2.inOut", in: "power2.in" },
    stagger: 0.03
  };
  const D = SM_MOTION.dur, E = SM_MOTION.ease;
  const KEY = "smc.b.v1";
  const HONEST = ".sm-status,.sm-marker,.sm-scripted,.sm-logo"; /* these never animate (8.4) */
  const NS = "http://www.w3.org/2000/svg";
  const params = new URLSearchParams(location.search);
  const root = document.documentElement;
  const $ = (sel, el) => (el || document).querySelector(sel);

  /* ---------- DOM helpers: createElement and textContent only, never innerHTML ---------- */
  function add(el, kids) {
    for (const c of kids.flat(Infinity)) if (c != null && c !== false) el.append(c.nodeType ? c : document.createTextNode(String(c)));
    return el;
  }
  function h(tag, props, ...kids) {
    const el = document.createElement(tag);
    for (const k in props || {}) {
      const v = props[k];
      if (v == null || v === false) continue;
      if (k === "class") el.className = v;
      else if (k === "text") el.textContent = v;
      else if (k.slice(0, 2) === "on") el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? "" : v);
    }
    return add(el, kids);
  }
  function svg(tag, attrs, ...kids) {
    const el = document.createElementNS(NS, tag);
    for (const k in attrs || {}) el.setAttribute(k, attrs[k]);
    kids.forEach(k => el.append(k));
    return el;
  }
  /* Lucide icon from the sprite in index.html. Beside its words it is aria-hidden; alone it gets a name. */
  function icon(name, size, label) {
    const a = { class: "sm-icon", width: size || 20, height: size || 20, viewBox: "0 0 24 24", focusable: "false" };
    if (label) { a.role = "img"; a["aria-label"] = label; } else a["aria-hidden"] = "true";
    return svg("svg", a, svg("use", { href: "#i-" + name }));
  }
  const vh = text => h("span", { class: "sm-vh", text });
  const rich = s => s.split("**").map((t, i) => (i % 2 ? h("strong", { text: t }) : t));
  const isOff = el => el.getAttribute("aria-disabled") === "true";

  /* ---------- motion engine ---------- */
  let reduced = params.get("rm") === "1" || root.dataset.motion === "reduced";
  const forced = reduced;
  gsap.matchMedia().add({ reduce: "(prefers-reduced-motion: reduce)", full: "(prefers-reduced-motion: no-preference)" }, ctx => {
    reduced = forced || !!ctx.conditions.reduce;
    root.dataset.motion = reduced ? "reduced" : "full";
  });
  const live = new Set(); /* tweens tied to a primary action; any key or click completes them (8.7) */
  function track(t, done) { live.add(t); t.eventCallback("onComplete", () => { live.delete(t); if (done) done(); }); return t; }
  function settle() { [...live].forEach(t => t.progress(1)); live.clear(); }
  /* The largest subtrees of a node that hold no honesty component, so those stay still. */
  function parts(node) {
    if (Array.isArray(node)) return node.flatMap(parts);
    if (!node || node.matches(HONEST)) return [];
    if (!node.querySelector(HONEST)) return [node];
    return [...node.children].flatMap(parts);
  }
  /* Arrival: opacity and a short rise. Reduced motion: opacity only, 150ms. */
  function enter(node, y, dur, delay) {
    const els = parts(node);
    if (!els.length) return null;
    return track(gsap.fromTo(els, { opacity: 0, y: reduced ? 0 : y },
      { opacity: 1, y: 0, duration: reduced ? 0.15 : dur, delay: reduced ? 0 : delay || 0, ease: E.out, clearProps: "opacity,transform" }));
  }
  let memo = {}; /* last value shown per figure, so a change tweens from where it was */
  function count(el, key, val, fmt) {
    fmt = fmt || String;
    const from = memo[key];
    memo[key] = val;
    el.textContent = fmt(val);
    if (reduced || from == null || from === val) return;
    const o = { v: from };
    el.textContent = fmt(from);
    gsap.to(o, { v: val, duration: D.max, ease: E.out, snap: { v: 1 }, onUpdate: () => { el.textContent = fmt(o.v); } });
  }
  let fxq = []; /* effects a component asks for; run once the screen is in the document */
  const fx = fn => fxq.push(fn);
  function runFx(arrival) { const q = fxq; fxq = []; q.forEach(fn => fn(arrival)); }

  /* ---------- state (DESIGN.md 3.7) ---------- */
  const fresh = () => ({
    v: 1, portal: null, page: { student: "interview", hub: "overview", partner: "talk" },
    ivStep: 0, ivLog: [], ivDone: false, iv4: "", picks: [], goal: "", cardPointsGiven: false,
    registered: [], lastRegistered: null, selfChecks: {}, helpPanel: null, bot: [],
    hubEvent: "E11", weights: Object.assign({}, SMC.DEFAULT_WEIGHTS), search: "", guideOpen: false, theme: "light"
  });
  let state, students, grace;
  let ui = { msg: {}, flash: {}, hint: {}, focus: null };
  function load() {
    try {
      const s = JSON.parse(localStorage.getItem(KEY));
      if (s && s.v === 1) return Object.assign(fresh(), s);
    } catch (e) { /* storage blocked: the page still works, it just forgets on reload */ }
    return fresh();
  }
  function save() { try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) { /* see load() */ } }
  function syncGrace() {
    grace.interests = state.ivDone ? state.picks.slice() : [];
    grace.goal = state.goal;
    grace.viaAI = state.ivDone;
  }
  /* The single way state changes. how: "nav" (screen change), "none", or undefined (re-render the screen). */
  function setState(patch, how) {
    state = Object.assign({}, state, patch);
    syncGrace();
    save();
    if (how === "nav") navigate(); else if (how !== "none") refresh();
  }
  const cur = () => (state.portal ? state.page[state.portal] : "entry");
  const points = () => 20 + (state.cardPointsGiven ? 20 : 0) + 10 * state.registered.length + 5 * Object.values(state.selfChecks).filter(Boolean).length;
  const eventById = id => SMC.UPCOMING.find(e => e.id === id);
  function go(id, extra) {
    if (id === "entry") return setState(Object.assign({ portal: null }, extra), "nav");
    const portal = SCREENS[id].portal;
    setState(Object.assign({ portal, page: Object.assign({}, state.page, { [portal]: id }) }, extra), "nav");
  }

  /* ---------- copy: Dr. Wang's wording, verbatim (DESIGN.md section 2) ---------- */
  const N1 = "Design for the next phase — made-up data";
  const N2 = "Scripted for this demo. Not a live AI.";
  const FULL = "In the full version these connect to the Career Hub's real booking, messaging and resource pages. Shown here as a demo.";
  const TECH = "Technology / information systems", ENT = "Entertainment / sports / media";
  const EXPLORING = "Exploring consulting or data roles";
  const BOOK = "Book a 30-minute appointment with a CBACH advisor";
  const STOPS = ["entry", "interview", "recs", "readiness", "growth", "overview", "records", "match", "talk"];
  const PORTALS = {
    student: { name: "Student portal", who: "Signed in as Grace Delgado · Accounting · Junior", screens: ["interview", "recs", "readiness", "growth"] },
    hub: { name: "Career Hub portal", who: "CBA Career Hub (CBACH) staff", screens: ["overview", "records", "match"] },
    partner: { name: "Partner portal", who: "Dana Whitfield · Senior Data Lead, Northline Analytics · CPP alumna, 2014", screens: ["talk"] }
  };
  const DOORS = [
    ["student", "user-round", "For students", "Activate your profile through a short AI interview, get events picked for you, and see your growth record.", "Enter as Grace Delgado"],
    ["hub", "building-2", "For CBACH staff", "Student records, matching students to an event, and term reports for the college.", "Enter as Career Hub staff"],
    ["partner", "handshake", "For industry partners", "See who came to your talk, what students asked, and how to stay involved.", "Enter as Dana Whitfield"]
  ];
  const IV = [
    { say: "Hi Grace! I can see from your college record that you're an Accounting junior, and you came to **Brand Building at a Streaming Studio** and the **Cybersecurity and Cloud Jobs Q&A**. What made you go to the cloud jobs session?",
      opts: ["I'm curious about tech jobs", "A friend brought me", "My professor offered extra credit"] },
    { say: "Thanks. Which industries would you like to hear more about? Pick as many as you like. I've pre-selected ones that fit what you've told me and the events you went to.", multi: true },
    { say: "Got it. What would you like your next step to be after graduation?",
      opts: ["Accounting or audit role (CPA path)", "Data, analytics or IT role", "Finance or real estate role", "Graduate school", "Not sure yet"] },
    { a: { say: "That's very common for juniors. You picked consulting and technology among your interests. Would you like me to suggest events that help you compare consulting and data roles?", opts: ["Yes, help me compare", "No thanks"] },
      b: { say: "Great, I'll look for events that fit that goal. One last thing: is it OK to suggest events outside the Accounting department?", opts: ["Yes", "Only accounting events"] } },
    { say: "All set. Your profile card is filled in on the right. You can change it any time, and each event you attend will keep it up to date. Ready to see the events I picked for you?", opts: ["Show my events"] }
  ];
  const GUIDED = ["I'm curious about tech jobs", null, "Not sure yet", "Yes, help me compare", "Show my events"];
  const BOT_HELLO = "Hi Grace! I'm the CBACH assistant bot, an AI that answers quick questions. For advice on your plans, you can message or book a CBACH advisor.";
  const BOT_ASK = ["Where is the resume template?", "How do I get my resume reviewed?", "What counts as an employer event?", "Talk to a person"];
  const SLOTS = ["Mon Oct 12 · 10:00 am", "Tue Oct 13 · 2:30 pm", "Thu Oct 15 · 11:00 am"];
  const LEVELS = ["I checked myself", "I did it", "Someone confirmed it"];
  const MARKERS = [
    ["resume", "Resume ready", ["I have a one-page resume for my field", "Attended a resume workshop", "Resume reviewed by the Career Hub"], "Resume guide and templates"],
    ["interview", "Interview ready", ["I feel confident answering common interview questions", "Completed a practice interview", "Rated ready by staff or a speaker"], "Practice interview tool"],
    ["network", "Networking ready", ["My LinkedIn profile is complete", "Attended 2 or more employer events", "Follow-up conversation with a speaker or alum"], "LinkedIn profile checklist"],
    ["ethics", "Professional ethics ready", ["Answered the workplace scenarios check", "Attended a professional ethics session", "Signed off by an instructor or the Career Hub"], "Workplace ethics scenarios"],
    ["direction", "Career direction", ["Profile card completed", "Career goal stated", "Met with a career advisor"], "Career exploration guide"],
    ["experience", "Work experience", ["Listed relevant experience", "Internship, job or project recorded", "Confirmed by a supervisor or faculty member"], "Internship listings on Handshake"]
  ];
  const WEIGHTS = [["major", "Same major"], ["interest", "Said they're interested"], ["goal", "Career goal fits"], ["past", "Went to similar events"]];
  const TALK_INVITED = [["Accounting", 8], ["Computer Info Systems", 7], ["Finance, RE & Law", 6], ["IB & Marketing", 5], ["Management & HR", 4]];
  const TALK_FUNNEL = [["Invited personally", 30], ["Signed up", 19], ["Attended", 14]];
  const TALK_ACTS = [["Offer another talk", "Offer sent to the Career Hub", "primary"], ["Meet interested students", "Students who asked to connect will be notified", "secondary"], ["Post an internship", "Internship post sent to the Career Hub for review", "secondary"]];
  const GUIDE = {
    entry: ["Opening (Chau)", "Start here. One sentence on the problem, then pick a door.",
      ["Problem: events struggle to fill seats, contacts sit with individual staff, and nobody can see a student's growth.", "Explain the three doors: one app, three kinds of users, each with its own sign-in.", "Click Student portal."],
      "Smart Match brings the right events to the right students, and keeps a record of how each student grows."],
    interview: ["Student · AI interview (Chau)", "Show that the app already knows the student's record, and the interview fills in the rest.",
      ["Point to the right side: major, year and events come from college records.", "Answer the chat: curious about tech jobs → Done → Not sure yet → Yes, help me compare.", "Watch the profile card fill in as she answers.", "Say clearly: this interview is scripted for today; a live AI version is planned."],
      "Most students never fill in a form. A two-minute conversation does it for them."],
    recs: ["Student · Events for me (Chau)", "Show events coming to the student, each with a reason.",
      ["Read one 'Why you' line out loud.", "Mention: before the interview, the app only suggested the audit event because she's an accounting major.", "Click Register on the top event to show the check-in code and points."],
      "Every suggestion says why. Staff and students can see it isn't a black box."],
    readiness: ["Student · My readiness (Janice)", "Points show effort; readiness shows progress toward being job-ready.",
      ["Point to the ring: readiness now versus the gold mark for a junior.", "Tick one self-check (for example, LinkedIn) and show the % move a little.", "Explain why: confirmed steps count double, so self-checks alone can't raise it much.", "Say the markers are a draft and will follow the college's official list.", "Show the four help options: assistant bot (AI) for quick questions, message an advisor, book an advisor, digital resources. Ask the bot How do I get my resume reviewed? and it hands off to a real advisor."],
      "Grace can see where she stands for her year and exactly what to do next."],
    growth: ["Student · My growth (Janice)", "The record that stays after graduation.",
      ["Walk the timeline from sophomore year to after graduation.", "Point out that her events lean toward media and technology, which her major alone would never show."],
      "Over four years this becomes the college's best evidence of what helps students."],
    overview: ["Career Hub · Term overview (Janice)", "What the college can report each term.",
      ["These numbers come from the 300 made-up student records in the class file.", "Point to 'students never reached by an event' as the opportunity.", "Readiness charts are illustrative."],
      "For the first time, the Career Hub can see who it isn't reaching."],
    records: ["Career Hub · Student records (Janice)", "Every student is on file from day one.",
      ["Type 'Delgado' in search to find Grace; her card shows 'AI interview · today'."],
      "Students don't sign up from scratch; they activate a record that already exists."],
    match: ["Career Hub · Match students to an event (Chau)", "How staff fill an event.",
      ["Northline is selected: Grace is #4 because of her interview answers.", "Move the 'Same major' slider up and show CIS majors take over the list.", "Close: invite the top 30 personally."],
      "Students from any major who said they care about the topic get invited, not only the obvious major."],
    talk: ["Partner · My talk (Chau)", "Why industry partners would come back.",
      ["Show who was invited, from five majors.", "Show the turnout compared with a mass email.", "Ask the board: 'Would you use this? What would make you speak again?'"],
      "Your contact stays with the college, and you see the difference your talk made."]
  };

  /* ---------- shared components ---------- */
  const STATUS_ICON = { working: "circle-check", partly: "circle-dot", planned: "circle-dashed" };
  function renderStatus(p) {
    return h("span", { class: "sm-status", "data-kind": p.kind }, icon(STATUS_ICON[p.kind], 16), h("span", { text: p.text }));
  }
  function renderScripted() { return h("p", { class: "sm-scripted" }, icon("info", 16), h("span", { text: N2 })); }
  function renderButton(p) {
    return h("button", Object.assign({ class: "sm-button", type: "button", "data-variant": p.variant || "primary", "data-fk": p.fk, onclick: p.onClick }, p.attrs),
      p.icon && icon(p.icon, 20), h("span", { text: p.label }), p.iconEnd && icon(p.iconEnd, 20));
  }
  function renderChip(p) {
    return h("button", { class: "sm-chip", type: "button", "data-kind": p.toggle ? "toggle" : "option", "data-fk": p.fk,
      "aria-pressed": p.toggle ? String(!!p.pressed) : null, onclick: p.onClick }, p.toggle && icon("check", 16), h("span", { text: p.label }));
  }
  function renderPill(p) { return h("span", { class: "sm-pill", "data-tone": p.tone || "plain", text: p.text }); }
  function renderMessage(text) { return text ? h("p", { class: "sm-message", role: "status" }, icon("circle-check", 20), h("span", { text })) : null; }
  function renderStat(p) {
    const fig = h("strong", { class: "sm-stat__fig" });
    count(fig, p.key, p.value, p.fmt);
    return h("div", { class: "sm-stat" }, fig, " ", h("span", { class: "sm-stat__label", text: p.label }));
  }
  function renderBars(p) {
    const fills = [];
    const list = h("ul", { class: "sm-bars", "data-tone": p.gold ? "gold" : "green" }, p.rows.map(r => {
      const fill = h("span", { class: "sm-bars__fill", style: "width:" + Math.max(0, Math.min(100, r[1] / p.max * 100)) + "%" });
      fills.push(fill);
      return h("li", { class: "sm-bars__row" }, h("span", { class: "sm-bars__label", text: r[0] }),
        h("span", { class: "sm-bars__track", "aria-hidden": "true" }, fill), h("span", { class: "sm-bars__val", text: r[1] + (p.suffix || "") }));
    }));
    fx(arrival => { if (arrival && !reduced) track(gsap.from(fills, { scaleX: 0, transformOrigin: "left center", duration: D.base, ease: E.out, stagger: SM_MOTION.stagger, clearProps: "transform" })); });
    return list;
  }
  function renderFunnel(p) {
    return h("ul", { class: "sm-funnel" }, p.steps.map(s =>
      h("li", { class: "sm-funnel__row" }, h("span", { class: "sm-funnel__bar", style: "width:" + Math.max(16, 70 * s[1] / 30) + "%", text: String(s[1]) }), h("span", { class: "sm-funnel__label", text: s[0] }))));
  }
  function renderBlock(label, ...kids) { return h("section", { class: "sm-card" }, h("h2", { class: "sm-label", text: label }), kids); }
  function renderRing(p) {
    const R = 66, C = 2 * Math.PI * R, rad = (p.target / 100 * 360 - 90) * Math.PI / 180;
    const pt = r => [80 + r * Math.cos(rad), 80 + r * Math.sin(rad)];
    const tick = (cls, w) => svg("line", { class: cls, x1: pt(57)[0], y1: pt(57)[1], x2: pt(75)[0], y2: pt(75)[1], "stroke-width": w });
    const arc = svg("circle", { class: "sm-ring__arc", cx: 80, cy: 80, r: R, "stroke-dasharray": C, transform: "rotate(-90 80 80)" });
    const off = v => C * (1 - v / 100), from = memo.ring;
    memo.ring = p.pct;
    arc.style.strokeDashoffset = off(p.pct);
    fx(arrival => {
      const start = arrival ? 0 : from;
      if (reduced || start == null || start === p.pct) return;
      gsap.fromTo(arc, { strokeDashoffset: off(start) }, { strokeDashoffset: off(p.pct), duration: D.max, ease: E.out });
    });
    const fig = h("strong", { class: "sm-ring__fig" });
    count(fig, "ringfig", p.pct, v => v + "%");
    return h("div", { class: "sm-ring" },
      svg("svg", { viewBox: "0 0 160 160", role: "img", "aria-label": p.pct + "% career ready. Target for a " + p.year + ": " + p.target + "%." },
        svg("circle", { class: "sm-ring__track", cx: 80, cy: 80, r: R }), arc, tick("sm-ring__key", 6), tick("sm-ring__target", 4)),
      h("div", { class: "sm-ring__text", "aria-hidden": "true" }, fig, h("span", { text: "career ready" })));
  }
  function renderQr(eventId) {
    const q = SMC.qrCells(eventId), g = svg("svg", { class: "sm-qr", viewBox: "0 0 29 29", role: "img", "aria-label": "Sample check-in code", "shape-rendering": "crispEdges" });
    const rect = (x, y, s, cls) => g.append(svg("rect", { x, y, width: s, height: s, class: cls }));
    rect(0, 0, 29, "sm-qr__plate");
    q.cells.forEach(c => rect(c[0], c[1], 1, "sm-qr__ink"));
    q.finders.forEach(f => { rect(f[0], f[1], 7, "sm-qr__ink"); rect(f[0] + 1, f[1] + 1, 5, "sm-qr__plate"); rect(f[0] + 2, f[1] + 2, 3, "sm-qr__ink"); });
    return g;
  }
  /* A free-text row: hidden label, her placeholder, Send that is aria-disabled while empty (N8). */
  function renderAsk(p) {
    const hint = h("p", { class: ui.hint[p.id] ? "sm-hint" : "sm-vh", id: p.id + "-hint", text: p.hint });
    const input = h("input", { class: "sm-field__input", id: p.id, type: "text", autocomplete: "off", placeholder: p.placeholder, "data-fk": p.id });
    const send = renderButton({ label: "Send", icon: "send", fk: p.id + "-send", attrs: { type: "submit", "aria-disabled": "true", "aria-describedby": p.id + "-hint" } });
    input.addEventListener("input", () => {
      send.setAttribute("aria-disabled", String(!input.value.trim()));
      if (input.value.trim()) { hint.className = "sm-vh"; ui.hint[p.id] = false; }
    });
    return h("form", { class: "sm-ask", novalidate: true, onsubmit: e => {
      e.preventDefault();
      const v = input.value.trim();
      if (!v) { ui.hint[p.id] = true; hint.className = "sm-hint"; return; }
      p.onSend(v);
    } }, h("label", { class: "sm-vh", for: p.id, text: p.label }), input, send, hint);
  }
  function renderTurn(t, speaker) {
    if (t.me != null) return h("div", { class: "sm-turn", "data-who": "student" }, h("p", null, vh("Grace: "), t.me));
    return h("div", { class: "sm-turn", "data-who": "assistant" }, h("p", { class: "sm-turn__who", text: speaker }), h("p", null, rich(t.ai)),
      t.book && renderButton({ label: BOOK, variant: "inline", fk: "bot-book-" + t.n, onClick: () => openHelp("book", true) }));
  }
  /* Keeps the newest turns in view, always starting at the top of a turn, never mid-line (7.10). */
  function pinLog(log) {
    const turns = [...log.querySelectorAll(".sm-turn")], pad = $(".sm-log__pad", log);
    if (!turns.length) return;
    pad.style.height = "0px";
    const end = turns[turns.length - 1].offsetTop + turns[turns.length - 1].offsetHeight, room = log.clientHeight - 32;
    let first = turns.length - 1;
    while (first > 0 && end - turns[first - 1].offsetTop <= room) first--;
    const top = Math.max(0, turns[first].offsetTop - 12);
    pad.style.height = Math.max(0, top + log.clientHeight - log.scrollHeight) + "px";
    log.scrollTop = top;
  }
  function renderLog(p) {
    const log = h("div", { class: "sm-log", "data-scroll": p.id }, p.turns.map(t => renderTurn(t, p.speaker)), h("div", { class: "sm-log__pad", "aria-hidden": "true" }));
    const sr = h("div", { class: "sm-vh", role: "log", "aria-live": "polite" });
    fx(() => {
      pinLog(log);
      if (!ui.flash[p.id]) return;
      const turns = [...log.querySelectorAll(".sm-turn")], last = turns[turns.length - 1], prev = turns[turns.length - 2];
      if (last && last.dataset.who === "assistant") sr.textContent = last.children[1].textContent; /* newest turn only, once */
      if (prev && prev.dataset.who === "student" && ui.flash[p.id] === 2) enter(prev, 6, D.fast);
      if (last) enter([last].concat(p.reply ? [p.reply()] : []), 6, D.base, ui.flash[p.id] === 2 ? 0.08 : 0);
    });
    return [log, sr];
  }

  /* ---------- tables that re-rank (sm-rerank, sm-wash): one read phase, then one write phase ---------- */
  const mq = { sm: window.matchMedia("(max-width: 639px)"), fit: window.matchMedia("(min-width: 1024px) and (min-height: 560px)") };
  function renderTable(p) {
    const sm = mq.sm.matches;
    const body = h(sm ? p.ordered ? "ol" : "ul" : "tbody", { class: sm ? "sm-rows" : null });
    const cols = h("colgroup", null, p.cols.map(c => h("col", { style: "width:" + c.w })));
    const table = sm ? body : h("table", { class: "sm-table" }, h("caption", { class: "sm-vh", text: p.caption }), cols,
      h("thead", null, h("tr", null, p.cols.map(c => h("th", { scope: "col", text: c.label })))), body);
    const empty = h("p", { class: "sm-empty", hidden: true, text: p.empty });
    const ghosts = h("div", { class: "sm-ghosts", "aria-hidden": "true" });
    const box = h("div", { class: "sm-tablebox", tabindex: "0", role: "region", "aria-label": p.caption }, table, empty, ghosts);
    return { box, body, cols, empty, ghosts, sm, rows: new Map(), defs: p.cols, tl: null };
  }
  function tableRow(t, id, vals, hl) {
    let row = t.rows.get(id);
    if (!row) {
      row = h(t.sm ? "li" : "tr", { class: "sm-row", "data-flip-id": id, "data-grace": hl ? "true" : null });
      row._v = t.defs.map((c, i) => {
        const v = h("span", { class: "sm-row__v" });
        row.append(h(t.sm ? "div" : "td", { class: "sm-cell", "data-col": c.key }, t.sm && h("span", { class: "sm-row__k", text: c.label }), i === 1 && hl && [icon("id-card", 20), vh("Grace Delgado, the student from the demo ")], v));
        return v;
      });
      row._t = [];
      t.rows.set(id, row);
    }
    vals.forEach((v, i) => { /* write only what changed */
      if (v && v.nodeType) { if (row._t[i] !== v.textContent) { row._v[i].replaceChildren(v); row._t[i] = v.textContent; } }
      else if (row._t[i] !== v) { row._v[i].textContent = v; row._t[i] = v; }
    });
    return row;
  }
  function wash(rows) { /* sm-wash: one tween for every row that just arrived */
    const spans = rows.map(row => {
      if (row._wash) row._wash.remove();
      row._wash = h("span", { class: "sm-wash", "aria-hidden": "true" });
      row.firstElementChild.prepend(row._wash);
      return row._wash;
    });
    if (spans.length) gsap.fromTo(spans, { opacity: 1 }, { opacity: 0, duration: D.wash, ease: "power1.out", onComplete: () => spans.forEach(w => w.remove()) });
  }
  function reorder(body, next, leaving) { /* move only the nodes that are out of place */
    leaving.forEach(n => n.remove());
    let ref = body.firstChild;
    next.forEach(n => { if (n === ref) ref = ref.nextSibling; else body.insertBefore(n, ref); });
  }
  /* Put `next` rows in the table. Rows that stay travel (GSAP Flip, transform only); rows that enter
   * fade in and get the wash; rows that leave fade out as ghosts. A second call while rows are still
   * moving starts from where they are: the state is read first, then the old flight is killed.
   * Cost per change is kept low by moving only the nodes that are out of place (reorder), one tween
   * for all washes, row nodes built ahead in idle time (warmTable) and storage written after the drag. */
  function setRows(t, next, instant) {
    const prev = [...t.body.children];
    t.empty.hidden = next.length > 0;
    if (prev.length === next.length && prev.every((n, i) => n === next[i])) return;
    if (instant || reduced) {
      t.body.replaceChildren(...next);
      if (!instant) gsap.fromTo(t.body, { opacity: 0 }, { opacity: 1, duration: 0.15, clearProps: "opacity", overwrite: true });
      return;
    }
    const keep = new Set(next), had = new Set(prev);
    const leaving = prev.filter(n => !keep.has(n)), entering = next.filter(n => !had.has(n));
    /* read */
    const flipState = Flip.getState(prev, { simple: true });
    const base = t.box.getBoundingClientRect(), sx = t.box.scrollLeft, sy = t.box.scrollTop;
    const gone = leaving.map(n => { const r = n.getBoundingClientRect(); return [n, r.top - base.top + sy, r.left - base.left + sx, r.width]; });
    /* write */
    if (t.tl && t.tl.isActive()) { /* interrupted mid-flight: the state above already holds where each row is */
      t.tl.kill();
      gsap.killTweensOf(prev);
      gsap.set(prev, { clearProps: "transform,opacity" });
    }
    while (t.ghosts.childElementCount > 30) t.ghosts.firstElementChild.remove();
    gone.forEach(g => {
      const clone = g[0].cloneNode(true);
      clone.removeAttribute("data-flip-id");
      const holder = t.sm ? h("ul", { class: "sm-rows sm-ghost" }, clone) : h("table", { class: "sm-table sm-ghost" }, t.cols.cloneNode(true), h("tbody", null, clone));
      holder.style.cssText = "top:" + g[1] + "px;left:" + g[2] + "px;width:" + g[3] + "px";
      t.ghosts.append(holder);
      gsap.to(holder, { opacity: 0, duration: D.fast, ease: E.in, onComplete: () => holder.remove() });
    });
    reorder(t.body, next, leaving);
    wash(entering);
    t.tl = Flip.from(flipState, {
      targets: next, duration: D.move, ease: E.inOut, absolute: false, simple: true, overwrite: true,
      onEnter: els => gsap.fromTo(els, { opacity: 0 }, { opacity: 1, duration: D.base, ease: E.out, clearProps: "opacity" })
    });
  }

  /* Builds the row nodes ahead of the first drag, in idle time, and runs Flip once on rows at rest,
   * so the first real re-rank costs the same as every later one (8.7). */
  function warmTable(t, make) {
    const idle = window.requestIdleCallback || (fn => setTimeout(fn, 60));
    let i = 0;
    const step = () => {
      if (!t.body.isConnected) return;
      for (const end = Math.min(i + 30, students.length); i < end; i++) make(students[i]);
      if (i < students.length) return idle(step);
      if (!reduced && !(t.tl && t.tl.isActive())) Flip.from(Flip.getState([...t.body.children], { simple: true }), { duration: 0, simple: true });
    };
    idle(step);
  }

  /* ---------- screen: entry ---------- */
  function screenEntry() {
    return h("div", { class: "b-entry" },
      h("h1", { class: "b-entry__title", id: "title", tabindex: "-1", text: "Smart Match CPP" }),
      h("p", { class: "b-entry__lede", text: "A student-built app for the CBA Career Hub. Events find the right students, students build a record of their career growth, and industry partners see who they reached." }),
      h("div", { class: "b-doors" }, DOORS.map(d => h("button", { class: "sm-door", type: "button", "data-fk": "door-" + d[0], onclick: () => go(state.page[d[0]]) },
        h("span", { class: "sm-door__icon" }, icon(d[1], 24)),
        h("span", { class: "sm-door__text" }, h("span", { class: "sm-label", text: d[2] }), h("span", { class: "sm-door__title", text: PORTALS[d[0]].name }), h("span", { class: "sm-door__body", text: d[3] })),
        h("span", { class: "sm-door__go" }, h("span", { text: d[4] }), icon("arrow-right", 20))))),
      h("p", { class: "b-entry__demo", text: "Concept prototype. All students, partners, events and numbers are made up; the 300 student records come from the class exercise file." }));
  }

  /* ---------- screen: Student · Activate my profile ---------- */
  function pickGoal(text) {
    const t = text.trim().toLowerCase(), key = Object.keys(SMC.GOALTOPIC).find(k => k.toLowerCase() === t);
    if (key) return key;
    if (t === "graduate school") return "Graduate school"; /* fix F2 */
    if (/data|analytic|it\b/i.test(text)) return "Data, analytics or IT role";
    if (/account|audit|cpa/i.test(text)) return "Accounting or audit role (CPA path)";
    return "Undecided";
  }
  const ivTurn = (step, v) => (step === 3 ? IV[3][v] : IV[step]);
  const ivStart = () => ({ ivStep: 0, ivLog: [{ ai: IV[0].say }], ivDone: false, iv4: "", picks: [], goal: "" });
  /* Her script as a pure step: the state after the answer `text` (null on turn 2 means "Done"). */
  function ivNext(s, text) {
    let picks = s.picks.slice(), goal = s.goal, iv4 = s.iv4;
    const step = s.ivStep + 1;
    if (s.ivStep === 0) {
      if (/tech|data|cloud|cyber|curious/i.test(text) && !picks.includes(TECH)) picks.push(TECH);
      [TECH, ENT].forEach(t => { if (!picks.includes(t)) picks.push(t); });
    }
    if (s.ivStep === 1) text = picks.map(SMC.short).join(", ") || "None of these";
    if (s.ivStep === 2) { goal = pickGoal(text); iv4 = goal === "Undecided" ? "a" : "b"; }
    if (s.ivStep === 3 && iv4 === "a" && /yes|compare/i.test(text)) goal = EXPLORING;
    const log = s.ivLog.concat({ me: text }, step < 5 ? { ai: ivTurn(step, iv4).say } : []);
    return { ivStep: step, ivLog: log, picks, goal, iv4, ivDone: step === 5, cardPointsGiven: s.cardPointsGiven || step === 5 };
  }
  function ivAnswer(text) {
    const next = ivNext(state, text);
    ui.flash.iv = 2;
    ui.focus = ".sm-reply .sm-chip"; /* keyboard: carry on from the first reply option */
    if (!next.ivDone) return setState(next);
    go("recs", next);
    toast("Profile card saved. 20 points added.");
  }
  function togglePick(topic) {
    setState({ picks: state.picks.includes(topic) ? state.picks.filter(t => t !== topic) : state.picks.concat(topic) });
  }
  function renderReply() {
    const step = state.ivStep;
    if (step >= 5) return h("div", { class: "sm-reply" }, h("p", { class: "sm-reply__done", text: "Interview finished." }),
      renderButton({ label: "Start over", variant: "secondary", icon: "rotate-ccw", fk: "iv-over", onClick: () => { ui.flash.iv = 1; ui.focus = ".sm-reply .sm-chip"; setState(ivStart()); } }));
    const t = ivTurn(step, state.iv4);
    if (t.multi) return h("div", { class: "sm-reply" }, h("div", { class: "sm-chips" }, SMC.TOPICS.map(topic =>
      renderChip({ label: SMC.short(topic), toggle: true, pressed: state.picks.includes(topic), fk: "pick-" + topic, onClick: () => togglePick(topic) }))),
      h("div", { class: "sm-reply__row" }, renderButton({ label: "Done", fk: "iv-done", onClick: () => ivAnswer(null) })));
    return h("div", { class: "sm-reply" },
      h("div", { class: "sm-chips" }, t.opts.map((o, i) => renderChip({ label: o, fk: "iv-opt-" + i, onClick: () => ivAnswer(o) }))),
      renderAsk({ id: "iv-text", label: "Type an answer", placeholder: "Or type your own answer…", hint: "Type an answer first.", onSend: ivAnswer }));
  }
  const goalText = g => (g === EXPLORING ? "Undecided · exploring consulting or data roles" : g);
  function renderProfileCard() {
    const dd = (k, v) => h("div", { class: "b-dl__row" }, h("dt", { text: k }), h("dd", null, v));
    const none = () => h("span", { class: "sm-none", text: "Not yet" });
    const had = memo.picks || state.picks, hadGoal = memo.goal;
    const pills = state.picks.map(t => { const el = renderPill({ text: SMC.short(t), tone: "fresh" }); el._new = !had.includes(t); return el; });
    const goal = h("span", { class: state.goal ? null : "sm-none", text: state.goal ? goalText(state.goal) : "Not yet" });
    fx(arrival => { /* sm-card-fill */
      memo.picks = state.picks; memo.goal = state.goal;
      if (arrival) return;
      const fresh = pills.filter(el => el._new);
      if (fresh.length) gsap.from(fresh, { opacity: 0, scale: reduced ? 1 : 0.9, duration: reduced ? 0.15 : D.base, ease: E.out, clearProps: "opacity,transform" });
      if (hadGoal !== undefined && hadGoal !== state.goal) gsap.from(goal, { opacity: 0, duration: reduced ? 0.15 : D.base, ease: E.out, clearProps: "opacity" });
    });
    return h("section", { class: "b-inspector", "aria-labelledby": "card-name" },
      h("div", { class: "b-inspector__head" }, h("span", { class: "sm-avatar", "aria-hidden": "true", text: "GD" }),
        h("div", null, h("h2", { id: "card-name", text: "Grace Delgado" }), h("p", { class: "sm-help-text", text: "Profile card" }))),
      h("h3", { class: "sm-label", text: "From college records (already on file)" }),
      h("dl", { class: "b-dl" }, dd("Major", grace.major), dd("Year", grace.year), dd("Events", grace.events.map(e => h("span", { class: "b-dl__line", text: SMC.PAST[e][0] })))),
      h("h3", { class: "sm-label", text: "From the interview" }),
      h("dl", { class: "b-dl" }, dd("Interests", pills.length ? h("span", { class: "sm-pills" }, pills) : none()), dd("Next step", goal)),
      h("p", { class: "sm-help-text", text: "Later: students can answer by voice or by typing." }));
  }
  function screenInterview() {
    if (!state.ivLog.length) { state = Object.assign({}, state, ivStart(), { ivDone: false }); syncGrace(); save(); }
    const reply = renderReply();
    return h("div", { class: "b-split", "data-split": "interview" },
      h("section", { class: "sm-transcript", "aria-label": "Smart Match assistant" }, renderScripted(),
        renderLog({ id: "iv", speaker: "Smart Match assistant", turns: state.ivLog, reply: () => reply }), reply),
      renderProfileCard());
  }

  /* ---------- screen: Student · Events for me ---------- */
  function register(id) {
    if (state.registered.includes(id)) return;
    ui.flash.reg = id;
    ui.flash.checkin = !state.registered.length;
    setState({ registered: state.registered.concat(id), lastRegistered: id });
    toast("Registered. 10 points added.");
  }
  function renderEventRow(p) {
    const done = state.registered.includes(p.ev.id);
    const check = done ? icon("check", 20) : null;
    if (done && ui.flash.reg === p.ev.id) fx(() => { if (!reduced) gsap.from(check, { scale: 0.5, opacity: 0, duration: D.fast, ease: E.out, transformOrigin: "50% 50%", clearProps: "transform,opacity" }); });
    return h("li", { class: "sm-event" },
      h("div", { class: "sm-event__date" }, h("strong", { text: p.ev.d }), h("span", { text: p.ev.m })),
      h("div", { class: "sm-event__main" }, h("h3", { text: p.ev.title }),
        h("p", { class: "sm-event__meta", text: p.ev.host + " · " + p.ev.when + " · 60 seats" }),
        h("p", { class: "sm-event__why" }, h("strong", { text: "Why you:" }), " " + SMC.whyYou(p.ev))),
      h("div", { class: "sm-event__act" }, h("span", { class: "sm-event__match", text: "match " + p.ev.total + " of 10" }),
        h("button", { class: "sm-button", type: "button", "data-variant": done ? "confirmed" : "secondary", "data-fk": "reg-" + p.ev.id,
          "aria-disabled": done ? "true" : null, onclick: () => register(p.ev.id) }, h("span", { text: done ? "Registered" : "Register" }), check)));
  }
  function renderCheckin() {
    const ev = eventById(state.lastRegistered), fig = h("strong", { class: "sm-stat__fig" });
    count(fig, "points", points());
    const card = h("section", { class: "sm-checkin", "aria-labelledby": "checkin-label" },
      h("div", { class: "sm-checkin__code" }, renderQr(ev.id)),
      h("div", { class: "sm-checkin__text" }, h("h2", { class: "sm-label", id: "checkin-label" }, icon("qr-code", 16), "Check-in code"),
        h("p", { class: "sm-checkin__event", text: ev.title + " · " + ev.when }),
        h("p", { text: "Scanned at the door. Attendance goes on her record and points are added. Sample code only." }),
        renderStatus({ kind: "planned", text: "Planned" })),
      h("div", { class: "sm-checkin__points" }, h("h2", { class: "sm-label", text: "Career points" }), fig, h("p", { class: "sm-help-text", text: "Points exist in the early version" })));
    fx(() => {
      if (!ui.flash.reg) return;
      if (ui.flash.checkin) enter(card, 8, D.base);
      card.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "nearest" });
    });
    return card;
  }
  function screenRecs() {
    return h("div", { class: "b-recs", "data-checkin": String(!!state.lastRegistered) },
      h("div", { class: "b-recs__list" },
        !state.ivDone && h("div", { class: "sm-callout" }, h("p", { text: "Finish the short interview to get better suggestions." }),
          renderButton({ label: "Activate my profile", variant: "inline", fk: "recs-go", onClick: () => go("interview") })),
        h("section", { class: "sm-card sm-card--flush", "aria-labelledby": "recs-h" }, h("h2", { class: "sm-vh", id: "recs-h", text: "Events for me" }),
          h("ol", { class: "sm-events" }, SMC.rankEvents(grace).map(ev => renderEventRow({ ev }))))),
      state.lastRegistered && renderCheckin());
  }

  /* ---------- screen: Student · My readiness ---------- */
  function steps() {
    const c = state.selfChecks, d = state.ivDone, o = {};
    MARKERS.forEach(m => { o[m[0]] = [!!c[m[0]], false, false]; });
    o.network[1] = true;
    o.direction = [d, d, false];
    return o;
  }
  const readiness = st => Math.round(Object.values(st).reduce((a, s) => a + (s[0] ? 1 : 0) + (s[1] ? 1 : 0) + (s[2] ? 2 : 0), 0) / 24 * 100);
  function openHelp(which, force) {
    const open = force || state.helpPanel !== which;
    ui.flash.panel = true;
    ui.focus = open ? "#help-label" : null;
    ui.msg = {};
    setState({ helpPanel: open ? which : null });
  }
  function botSay(me, ai, book) {
    ui.flash.bot = me ? 2 : 1;
    ui.focus = "#bot-text";
    setState({ bot: state.bot.concat(me ? { me } : [], { ai, book: !!book, n: state.bot.length }) });
  }
  function botAsk(q) {
    const t = q.toLowerCase();
    if (t.includes("template") || t.includes("resume guide")) return botSay(q, "The resume guide and templates are in Career Hub digital resources. Pick the accounting or general business template.");
    if (t.includes("review")) return botSay(q, "A CBACH advisor can review your resume in a 30-minute appointment. Bring your latest version.", true);
    if (t.includes("employer event") || t.includes("count")) return botSay(q, "Info sessions, industry panels, career fairs and employer talks all count. You have 2 so far, which meets the networking step.");
    if (/person|human|advisor|talk/.test(t)) return botSay(q, "Sure. You can message a CBACH advisor or book a 30-minute appointment.", true);
    botSay(q, "I can help with quick questions about events, resources and your readiness card. For this one, a CBACH advisor is the best person to ask.", true);
  }
  function renderHelpPanel(which) {
    const label = t => h("h2", { class: "sm-label", id: "help-label", tabindex: "-1", text: t });
    const foot = t => h("p", { class: "sm-help-text", text: t });
    const say = text => { ui.msg = { panel: text }; refresh(); };
    let kids;
    if (which === "chat") {
      const ask = renderAsk({ id: "bot-text", label: "Ask the assistant bot", placeholder: "Ask a quick question…", hint: "Type a question first.", onSend: botAsk });
      kids = [h("h2", { class: "sm-label", id: "help-label", tabindex: "-1" }, icon("bot", 16), "CBACH assistant bot (AI) · for quick questions"), renderScripted(),
        renderLog({ id: "bot", speaker: "CBACH assistant bot · AI", turns: [{ ai: BOT_HELLO }].concat(state.bot) }),
        h("div", { class: "sm-chips" }, BOT_ASK.map((q, i) => renderChip({ label: q, fk: "bot-q-" + i, onClick: () => botAsk(q) }))), ask,
        foot("The bot answers quick questions. For advice, it sends you to a CBACH advisor. " + FULL)];
    } else if (which === "msg") {
      const area = h("textarea", { class: "sm-field__input", id: "msg-text", rows: "3", "data-fk": "msg-text" });
      area.value = "Hi, could someone review my resume? I'm an accounting junior interested in data and consulting roles.";
      const hint = h("p", { class: "sm-vh", id: "msg-hint", text: "Type a message first." });
      const send = renderButton({ label: "Send message", icon: "send", fk: "msg-send", attrs: { "aria-describedby": "msg-hint" }, onClick: () => {
        if (!area.value.trim()) { hint.className = "sm-hint"; return; }
        ui.msg = { help: "Sent. A CBACH advisor usually replies within one business day." };
        ui.focus = '[data-fk="help-msg"]';
        setState({ helpPanel: null });
      } });
      area.addEventListener("input", () => { send.setAttribute("aria-disabled", String(!area.value.trim())); if (area.value.trim()) hint.className = "sm-vh"; });
      kids = [label("Message a CBACH advisor (a person on the Career Hub staff)"),
        h("div", { class: "sm-field" }, h("label", { for: "msg-text", text: "Your message" }), area),
        h("label", { class: "sm-check" }, h("input", { type: "checkbox", checked: true, "data-fk": "msg-share" }), h("span", { text: "Share my readiness card with the advisor so they can see where I am" })),
        h("div", { class: "sm-reply__row" }, send), hint,
        foot("Messages go to Career Hub staff, not to the bot. " + FULL)];
    } else if (which === "book") {
      kids = [label("Book a 30-minute appointment with a CBACH advisor (a person on the Career Hub staff)"),
        h("div", { class: "sm-chips" }, SLOTS.map((s, i) => renderChip({ label: s, fk: "slot-" + i, onClick: () => say("Booked: " + s + " with a CBACH advisor. A reminder will be sent.") }))),
        renderMessage(ui.msg.panel), foot(FULL)];
    } else {
      kids = [label("Career Hub digital resources"),
        h("div", { class: "sm-chips" }, MARKERS.map((m, i) => renderChip({ label: m[3], fk: "res-" + i, onClick: () => say("Opens: " + m[3]) }))),
        renderMessage(ui.msg.panel), foot(FULL)];
    }
    const panel = h("section", { class: "sm-card sm-helppanel", id: "help-panel", "aria-labelledby": "help-label", "data-panel": which }, kids);
    fx(() => { if (ui.flash.panel) enter(panel, 8, D.base); });
    return panel;
  }
  function renderMarkerCard(p) {
    const on = p.steps, id = p.m[0], dots = on.map((v, i) => h("span", { class: "sm-dots__dot", "data-state": v ? "on" : "off", "data-gold": i === 2 ? "true" : null }));
    const mark = v => h("span", { class: "sm-mark", "data-state": v ? "on" : "off" }, v && icon("check", 16), vh(v ? "done " : "not yet "));
    const step = (i, control) => h("li", { class: "sm-step" }, control, h("span", { class: "sm-step__level", text: LEVELS[i] }));
    const self = id === "direction" ? h("span", { class: "sm-step__line" }, mark(on[0]), h("span", { text: p.m[2][0] })) :
      h("label", { class: "sm-check" }, h("input", { type: "checkbox", checked: on[0], "data-fk": "self-" + id, onchange: e => {
        setState({ selfChecks: Object.assign({}, state.selfChecks, { [id]: e.target.checked }) });
        if (e.target.checked) toast("Self-check saved. 5 points added.");
      } }), h("span", { text: p.m[2][0] }));
    return h("section", { class: "sm-marker-card" },
      h("div", { class: "sm-marker-card__head" }, h("h3", { text: p.m[1] }), h("span", { class: "sm-dots", "aria-hidden": "true" }, dots)),
      h("ul", { class: "sm-steps" }, step(0, self), [1, 2].map(i => step(i, h("span", { class: "sm-step__line" }, mark(on[i]), h("span", { text: p.m[2][i] }))))),
      h("div", { class: "sm-marker-card__links" },
        renderButton({ label: p.m[3], variant: "link", fk: "mres-" + id, onClick: () => { ui.msg = { ["m-" + id]: "Opens the Career Hub page: " + p.m[3] }; refresh(); } }),
        renderButton({ label: "Ask the assistant bot", variant: "link", fk: "mbot-" + id, onClick: () => {
          ui.flash.panel = state.helpPanel !== "chat"; ui.flash.bot = 1; ui.focus = "#bot-text"; ui.msg = {};
          setState({ helpPanel: "chat", bot: state.bot.concat({ ai: "You're looking at **" + p.m[1] + "**. I can point you to resources, or help you book a CBACH advisor.", n: state.bot.length }) });
        } })),
      renderMessage(ui.msg["m-" + id]));
  }
  function screenReadiness() {
    const st = steps(), pct = readiness(st), tg = SMC.TARGET[grace.year], gap = tg - pct, year = grace.year.toLowerCase();
    const next = !state.ivDone ? ["Finish your profile interview", "Adds about 8% and 20 points", "interview"] :
      !st.resume[1] ? ["Sign up for a resume workshop", "The Career Hub can then review your resume", "recs"] :
        ["Book a practice interview", "Interview ready is your lowest marker", "recs"];
    const lead = gap <= 0 ? "On track for your year." : gap <= 20 ? "A little behind for a junior." : "Behind for a junior, and that's fixable.";
    const helpBtn = (which, text, variant) => renderButton({ label: text, variant, fk: "help-" + which, onClick: () => openHelp(which),
      attrs: { "aria-expanded": String(state.helpPanel === which), "aria-controls": "help-panel" } });
    return h("div", { class: "b-readiness" },
      h("section", { class: "sm-card b-rtop" }, renderRing({ pct, target: tg, year }),
        h("div", { class: "b-rtop__side" },
          h("div", { class: "b-tiles" }, renderStat({ key: "pct", value: pct, fmt: v => v + "%", label: "readiness now" }),
            renderStat({ key: "tg", value: tg, fmt: v => v + "%", label: "target for a " + year + " (gold mark)" }),
            renderStat({ key: "points", value: points(), label: "career points" })),
          h("div", { class: "sm-callout" }, h("p", null, h("strong", { text: lead }), " Next step: " + next[0] + ". ", h("span", { class: "sm-callout__note", text: next[1] })),
            renderButton({ label: "Go", variant: "inline", fk: "ready-go", onClick: () => go(next[2]) })))),
      h("section", { class: "sm-card sm-help" }, h("span", { class: "sm-avatar", "aria-hidden": "true", text: "CB" }),
        h("div", { class: "sm-help__main" }, h("h2", { text: "Need help with any marker? The CBA Career Hub (CBACH) is here." }),
          h("p", { text: "The assistant bot (AI) answers quick questions any time. CBACH advisors, real people on the Career Hub staff, answer messages and meet with you to review resumes, run practice interviews and help you choose a direction." }),
          h("div", { class: "sm-help__groups" },
            h("div", { class: "sm-help__group" }, h("h3", { class: "sm-label", text: "Help yourself, any time" }),
              h("div", { class: "sm-chips" }, helpBtn("chat", "Chat with the CBACH assistant bot", "primary"), helpBtn("res", "Career Hub digital resources", "primary"))),
            h("div", { class: "sm-help__group" }, h("h3", { class: "sm-label", text: "Talk to a person" }),
              h("div", { class: "sm-chips" }, helpBtn("msg", "Message a CBACH advisor", "secondary"), helpBtn("book", BOOK, "secondary")))),
          renderMessage(ui.msg.help))),
      state.helpPanel && renderHelpPanel(state.helpPanel),
      h("div", { class: "b-grid", "data-cols": "3", "data-shift": "markers" }, MARKERS.map(m => renderMarkerCard({ m, steps: st[m[0]] }))),
      h("p", { class: "b-closing", "data-shift": "closing", text: "Draft markers for discussion. If the college has official Career Success Markers, the names here should match them. Readiness is private to the student and her advisor unless she chooses to share it." }));
  }

  /* ---------- screen: Student · My growth ---------- */
  function screenGrowth() {
    const reg = state.registered.map(eventById), tally = new Map();
    grace.events.map(e => SMC.PAST[e][2]).concat(reg.map(e => e.topics)).flat().forEach(t => tally.set(SMC.short(t), (tally.get(SMC.short(t)) || 0) + 1));
    const topics = [...tally].sort((a, b) => b[1] - a[1]);
    const tag = t => renderPill({ text: t });
    const term = (name, future, lines) => h("li", { class: "sm-timeline__term", "data-when": future ? "future" : "past" }, h("span", { class: "sm-timeline__dot", "aria-hidden": "true" }),
      h("div", null, h("h3", { text: name }), lines.map(l => h("p", { class: "sm-timeline__line" }, h("span", { class: l[2] ? "sm-none" : null, text: l[0] }), l[1] && [" ", tag(l[1])]))));
    return h("div", { class: "b-growth" },
      h("div", { class: "b-grid", "data-cols": "2" },
        renderBlock("Timeline", h("ol", { class: "sm-timeline" },
          term("Fall 2025 · Sophomore", false, [["Brand Building at a Streaming Studio", "attended"]]),
          term("Spring 2026", false, [["Cybersecurity and Cloud Jobs Q&A", "attended"]]),
          term("Fall 2026 · Junior", false, [state.ivDone ? ["Profile card completed through AI interview", "+20 points"] : ["Profile card not yet completed", null, true]].concat(reg.map(e => [e.title, "registered"]))),
          term("Summer 2027", true, [["Internship", "recorded later"]]),
          term("After graduation", true, [["First job and employer", "recorded later"]]))),
        h("section", { class: "sm-card" }, h("h2", { class: "sm-label", text: "Topics she has explored" }),
          renderBars({ rows: topics, max: Math.max(3, topics[0][1]) }),
          h("div", { class: "b-tiles", "data-count": "2" }, renderStat({ key: "ev", value: 2 + reg.length, label: "events attended or registered" }), renderStat({ key: "points", value: points(), label: "career points" })))),
      h("p", { class: "b-closing", text: "An Accounting major whose events lean toward media and technology. Her record shows a path her major alone would never reveal." }));
  }

  /* ---------- screen: Career Hub · Term overview ---------- */
  function screenOverview() {
    const o = SMC.overviewStats(students), r = SMC.hubReadiness(students);
    const chart = (label, note, bars) => h("section", { class: "sm-card" }, h("h2", { class: "sm-label", text: label }), note && h("p", { class: "sm-help-text", text: note }), renderBars(bars));
    return h("div", { class: "b-overview" },
      h("div", { class: "b-tiles", "data-count": "4" }, renderStat({ key: "n", value: o.n, label: "student records loaded" }), renderStat({ key: "att", value: o.attended, label: "students who attended at least one event" }),
        renderStat({ key: "cards", value: o.cards, label: "students with a profile card" }), renderStat({ key: "never", value: o.neverReached, label: "students never reached by an event" })),
      h("div", { class: "b-grid", "data-cols": "2" },
        chart("Event attendance by major", null, { rows: o.attendanceByMajor, max: 46 }),
        chart("Events that brought in first-time students", "Share of each event's attendees for whom it was their first career event.", { rows: o.firstTimers, max: 100, suffix: "%", gold: true }),
        chart("Average readiness by year (illustrative)", null, { rows: r.map(y => [y[0] + " (" + y[3] + ")", y[1]]), max: 100, suffix: "%" }),
        chart("Share on track for their year (illustrative)", "Targets: freshman 20%, sophomore 40%, junior 60%, senior 85%. Shows where the Career Hub should focus, for example seniors who are behind.", { rows: r.map(y => [y[0], y[2]]), max: 100, suffix: "%", gold: true })),
      renderBlock("How student data is handled (proposed)", h("ul", { class: "sm-list" },
        ["Students activate their own profile; the interview is optional.", "The college owns the records, and they stay after students graduate.", "Reports show group totals. Partners never see individual student records."].map(t => h("li", { text: t })))));
  }

  /* ---------- screen: Career Hub · Student records ---------- */
  let rec = null;
  function recordsUpdate(first) {
    const q = state.search.trim().toLowerCase();
    const hits = students.filter(s => (s.name + " " + s.major + " " + s.id).toLowerCase().includes(q));
    rec.count.textContent = hits.length + " of 300 records";
    rec.more.hidden = hits.length <= 25;
    clearTimeout(rec.timer);
    rec.timer = setTimeout(() => { rec.sr.textContent = rec.count.textContent; }, 400);
    setRows(rec.t, hits.slice(0, 25).map(s => {
      const card = s.viaAI ? renderPill({ text: "AI interview · today", tone: "fresh" }) : s.interests.length || s.goal ? renderPill({ text: "Completed", tone: "done" }) : h("span", { class: "sm-none", text: "Not yet" });
      return tableRow(rec.t, s.id, [s.id, s.name, s.major, s.year, String(s.events.length), card], s.id === SMC.GRACE_ID);
    }), first);
  }
  function screenRecords() {
    const t = renderTable({ caption: "Student records", empty: "No records match that search.", cols: [
      { key: "id", label: "ID", w: "9%" }, { key: "name", label: "Name", w: "21%" }, { key: "major", label: "Major", w: "32%" },
      { key: "year", label: "Year", w: "13%" }, { key: "events", label: "Events", w: "9%" }, { key: "card", label: "Profile card", w: "16%" }] });
    const input = h("input", { class: "sm-field__input", id: "search", type: "search", placeholder: "Try Delgado", autocomplete: "off", "data-fk": "search" });
    input.value = state.search;
    input.addEventListener("input", () => { state = Object.assign({}, state, { search: input.value }); save(); recordsUpdate(); });
    rec = { t, count: h("p", { class: "b-count" }), sr: h("p", { class: "sm-vh", role: "status" }),
      more: h("p", { class: "sm-help-text b-more", text: "Showing the first 25. Search to narrow the list." }), timer: 0 };
    fx(() => recordsUpdate(true));
    return h("div", { class: "b-records" },
      h("div", { class: "b-toolbar" }, h("div", { class: "sm-field sm-field--search" }, h("label", { for: "search", text: "Search by name, major or ID" }), h("span", { class: "sm-field__wrap" }, icon("search", 20), input)), rec.count, rec.sr),
      t.box, rec.more);
  }

  /* ---------- screen: Career Hub · Match students to an event (the showpiece) ---------- */
  let mt = null, raf = 0, saveTimer = 0;
  function matchUpdate(first) {
    const ranked = SMC.rankStudents(students, eventById(state.hubEvent), state.weights);
    const at = ranked.findIndex(r => r.s.id === SMC.GRACE_ID), key = at < 0 ? (grace.viaAI ? "out" : "none") : grace.viaAI ? "in-ai" : "in";
    if (mt.lineKey !== key) { /* the sentence changes; otherwise only the numeral counts */
      mt.lineKey = key;
      mt.num = h("span", { class: "b-graceline__num" });
      memo.rank = undefined;
      mt.line.replaceChildren(...(at < 0 ? [grace.viaAI ? "Grace Delgado is not in the top 30 for this event." : "Grace has not done her interview yet, so the app knows little about her."] :
        ["Grace Delgado is ", mt.num, " on this list" + (grace.viaAI ? " because of her interview answers." : ".")]));
    }
    if (at >= 0) count(mt.num, "rank", at + 1, v => "#" + v);
    const text = at < 0 ? mt.line.textContent : "Grace Delgado is #" + (at + 1) + " on this list" + (grace.viaAI ? " because of her interview answers." : ".");
    clearTimeout(mt.timer);
    mt.timer = setTimeout(() => { mt.sr.textContent = text; }, 600);
    setRows(mt.t, ranked.slice(0, 15).map((r, i) => tableRow(mt.t, r.s.id,
      [String(i + 1), r.s.name, r.s.major, r.reason, r.s.viaAI ? "Profile card (AI interview)" : r.info], r.s.id === SMC.GRACE_ID)), first);
  }
  function matchChange(patch) { /* weights and event: state now, one render per animation frame (8.7) */
    state = Object.assign({}, state, patch);
    if (ui.msg.invite) { ui.msg = {}; mt.msg.replaceChildren(); }
    if (raf) return;
    clearTimeout(saveTimer);
    saveTimer = setTimeout(save, 200); /* storage is written after the drag, not inside a frame */
    raf = requestAnimationFrame(() => { raf = 0; if (cur() === "match" && mt) matchUpdate(); });
  }
  function renderWeight(p) {
    const id = "w-" + p.key, out = h("output", { class: "sm-weight__val", for: id, text: String(p.value) });
    const input = h("input", { id, type: "range", min: "0", max: "10", step: "1", "data-fk": id, style: "--v:" + p.value });
    input.value = p.value;
    input.addEventListener("input", () => { out.textContent = input.value; input.style.setProperty("--v", input.value); p.onInput(+input.value); });
    input.addEventListener("keydown", e => { /* Page keys move a weight by 2 and never change stop (7.8) */
      if (e.key !== "PageUp" && e.key !== "PageDown") return;
      e.preventDefault();
      input.value = Math.max(0, Math.min(10, +input.value + (e.key === "PageUp" ? 2 : -2)));
      input.dispatchEvent(new Event("input"));
    });
    return h("div", { class: "sm-weight" }, h("div", { class: "sm-weight__head" }, h("label", { for: id, text: p.label }), out), input);
  }
  /* A native select from 640px up. At 390 the option text would be cut, so it is a radio list there. */
  function renderEventPicker(p) {
    if (mq.sm.matches) return h("fieldset", { class: "sm-event-picker" }, h("legend", null, icon("calendar-days", 16), "Event"),
      SMC.UPCOMING.map(e => h("label", { class: "sm-check" }, h("input", { type: "radio", name: "ev", value: e.id, checked: e.id === p.value, onchange: () => p.onChange(e.id) }), h("span", { text: e.title + " · " + e.when }))));
    const sel = h("select", { class: "sm-field__input", id: "ev", onchange: e => p.onChange(e.target.value) },
      SMC.UPCOMING.map(e => h("option", { value: e.id, text: e.title + " · " + e.when })));
    sel.value = p.value;
    return h("div", { class: "sm-event-picker" }, h("label", { for: "ev" }, icon("calendar-days", 16), "Event"), sel);
  }
  function screenMatch() {
    const t = renderTable({ caption: "Match students to an event", ordered: true, empty: "No student matches with these weights. Raise at least one weight above 0.", cols: [
      { key: "rank", label: "#", w: "68px" }, { key: "name", label: "Student", w: "17%" }, { key: "major", label: "Major", w: "24%" },
      { key: "why", label: "Why on the list", w: "43%" }, { key: "know", label: "What we know", w: "16%" }] });
    mt = { t, line: h("span"), lineKey: "", num: null, sr: h("p", { class: "sm-vh", role: "status" }), msg: h("div", { class: "b-tablefoot__msg" }, renderMessage(ui.msg.invite)), timer: 0 };
    fx(() => { matchUpdate(true); warmTable(t, s => t.rows.has(s.id) || tableRow(t, s.id, ["", s.name, s.major, "", ""], s.id === SMC.GRACE_ID)); });
    return h("div", { class: "b-split", "data-split": "match" },
      h("div", { class: "b-weights" },
        h("div", { class: "b-weights__list" }, WEIGHTS.map(w => renderWeight({ key: w[0], label: w[1], value: state.weights[w[0]],
          onInput: v => matchChange({ weights: Object.assign({}, state.weights, { [w[0]]: v }) }) }))),
        h("p", { class: "b-graceline" }, icon("id-card", 20), mt.line), mt.sr),
      h("div", { class: "b-tablepane" }, t.box,
        h("div", { class: "b-tablefoot" }, h("p", { class: "b-tablefoot__count", text: "Showing 15 of the top 30." }),
          renderButton({ label: "Send personal invitations to top 30", icon: "send", fk: "invite", onClick: () => {
            ui.msg = { invite: "In the full version, each student gets a personal invitation and a reminder." };
            mt.msg.replaceChildren(renderMessage(ui.msg.invite));
          } }), mt.msg)));
  }

  /* ---------- screen: Partner · My talk ---------- */
  function screenTalk() {
    return h("div", { class: "b-talk" }, h("div", { class: "b-grid", "data-cols": "2" },
      renderBlock("Who was invited", h("p", { class: "sm-help-text", text: "Students who said they're interested in technology or data, from every major, not only Computer Information Systems." }), renderBars({ rows: TALK_INVITED, max: 8 })),
      renderBlock("How your talk filled", renderFunnel({ steps: TALK_FUNNEL }), h("p", { class: "sm-help-text", text: "A mass email to all students for a similar talk brought about 6 people." })),
      renderBlock("What students asked you",
        h("blockquote", { class: "sm-quote", text: "\"What should an accounting student learn first to move into data work?\"" }),
        h("blockquote", { class: "sm-quote", text: "\"Does Northline hire interns from outside computer science?\"" }),
        h("p", { class: "sm-help-text", text: "Average rating 4.6 of 5 from 14 students." })),
      renderBlock("Stay involved",
        h("div", { class: "sm-chips" }, TALK_ACTS.map((a, i) => renderButton({ label: a[0], variant: a[2], fk: "talk-" + i, onClick: () => { ui.msg = { talk: a[1] }; refresh(); } }))),
        renderMessage(ui.msg.talk),
        h("p", { class: "sm-help-text", text: "You see totals and questions, never individual student records. Your contact stays with the college, not with one staff member." }))));
  }

  /* ---------- screens registry (DESIGN.md 2.1) ---------- */
  const SCREENS = {
    entry: { render: screenEntry },
    interview: { portal: "student", menu: "Activate my profile", title: "Activate my profile", status: ["planned", "Planned · scripted for this demo"], fit: true, render: screenInterview,
      desc: () => "The app already has Grace's college record. A short AI interview fills in the rest of her profile card, so event suggestions fit her, not just her major." },
    recs: { portal: "student", menu: "Events for me", title: "Events picked for Grace", status: ["working", "Matching works in class version"], render: screenRecs,
      desc: () => "Events come to the student, each with a plain reason. " + (state.ivDone ? "These use her profile card." : "Right now the app only knows her major and past events.") },
    readiness: { portal: "student", menu: "My readiness", title: "Grace's career readiness", status: ["planned", "Planned · draft markers"], render: screenReadiness,
      desc: () => "Points show effort. Readiness shows how many success markers she has reached, and confirmed steps count double so it can't be raised by self-checks alone." },
    growth: { portal: "student", menu: "My growth", title: "Grace's career growth record", status: ["planned", "Planned"], render: screenGrowth,
      desc: () => "Each event attended adds to a record the student can see. The record stays with the college after she graduates, so the college can study what helps students." },
    overview: { portal: "hub", menu: "Term overview", title: "Term overview", status: ["partly", "Partly built"], render: screenOverview,
      desc: () => "What the college can report each term, drawn from the student records. Shown here for the made-up student body of 300." },
    records: { portal: "hub", menu: "Student records", title: "Student records", status: ["working", "Working in class version"], fit: true, render: screenRecords,
      desc: () => "Every student is on file from day one with major, year and events attended. The profile card fills in when the student activates through the AI interview." },
    match: { portal: "hub", menu: "Match students to an event", title: "Match students to an event", status: ["working", "Working in class version"], fit: true, render: screenMatch,
      tools: () => renderEventPicker({ value: state.hubEvent, onChange: v => matchChange({ hubEvent: v }) }),
      desc: () => "Pick an event and the app ranks all 300 students. Staff can adjust how much each factor counts, then invite the top 30 personally." },
    talk: { portal: "partner", menu: "My talk", title: "Your talk: Northline Analytics", status: ["partly", "Partly built"], render: screenTalk,
      desc: () => "Behind the Business series · Thu Mar 4, 2027 · what an industry partner sees after speaking. Numbers are illustrative." }
  };

  /* ---------- shell: sidebar, page header, main (7.1, 13.4) ---------- */
  const el = {};
  ["shell", "main", "work", "entryLogo", "sideLogo", "sideTop", "portalName", "portalWho", "navSlot", "switchBtn", "switchLayer", "switchPop", "switchInput", "switchList", "guideBtn", "guideBtnLabel", "guide", "toast", "kbdMod", "skip"]
    .forEach(id => { el[id] = document.getElementById(id); });
  let lastPortal;
  function renderNav(p) {
    return h("nav", { class: "sm-nav", "aria-label": PORTALS[p].name }, h("ul", null, PORTALS[p].screens.map(id =>
      h("li", null, h("button", { type: "button", class: "sm-nav__item", "aria-current": id === cur() ? "page" : null, onclick: () => go(id) }, h("span", { text: SCREENS[id].menu }))))));
  }
  function renderChrome(id) {
    const p = state.portal;
    el.shell.dataset.portal = p || "entry";
    el.shell.dataset.screen = id;
    el.shell.dataset.fit = String(!!SCREENS[id].fit);
    el.entryLogo.hidden = !!p;
    el.sideTop.hidden = !p;
    if (p) { el.portalName.textContent = PORTALS[p].name; el.portalWho.textContent = PORTALS[p].who; }
    el.navSlot.replaceChildren(...(p ? [renderNav(p)] : []));
    if (p && lastPortal && lastPortal !== p && !reduced) gsap.from([...el.navSlot.querySelectorAll("span"), el.portalName, el.portalWho], { opacity: 0, duration: 0.12, clearProps: "opacity" });
    lastPortal = p;
    renderGuide(true);
  }
  function renderHead(id) {
    const sc = SCREENS[id];
    return h("div", { class: "sm-pagehead" },
      h("div", { class: "sm-pagehead__row" }, h("h1", { id: "title", tabindex: "-1", text: sc.title }), renderStatus({ kind: sc.status[0], text: sc.status[1] }), sc.tools && sc.tools()),
      h("p", { class: "sm-pagehead__desc", id: "desc", text: sc.desc() }));
  }
  /* sm-screen / sm-portal: the old body leaves as a ghost (fast), the new one arrives (base). The sidebar never moves. */
  function navigate(quiet) {
    settle();
    const id = cur(), old = $(".sm-body", el.main);
    ui.msg = {}; ui.hint = {}; memo = {};
    $(".sm-ghostbody", el.work) && $(".sm-ghostbody", el.work).remove();
    let wait = 0;
    if (old && !reduced && !quiet) {
      const a = old.getBoundingClientRect(), b = el.work.getBoundingClientRect(), ghost = old.cloneNode(true);
      ghost.className += " sm-ghostbody";
      ghost.setAttribute("aria-hidden", "true");
      ghost.inert = true;
      ghost.querySelectorAll("[id]").forEach(n => n.removeAttribute("id"));
      ghost.querySelectorAll(HONEST).forEach(n => { n.style.visibility = "hidden"; });
      ghost.style.cssText = "top:" + (a.top - b.top) + "px;left:" + (a.left - b.left) + "px;width:" + a.width + "px;height:" + Math.min(a.height, window.innerHeight) + "px";
      el.work.append(ghost);
      track(gsap.to(ghost, { opacity: 0, duration: D.fast, ease: E.in }), () => ghost.remove());
      wait = D.fast;
    }
    renderChrome(id);
    fxq = [];
    const body = h("div", { class: "sm-body", "data-screen": id }, SCREENS[id].render());
    el.main.replaceChildren(h("div", { class: "sm-view" }, id !== "entry" && renderHead(id), body));
    window.scrollTo(0, 0);
    if (!quiet) { $("#title").focus({ preventScroll: true }); enter(body, 8, D.base, wait); }
    runFx(true);
    ui.flash = {};
  }
  /* Re-render the current screen in place, keeping focus and scroll. Used for every in-screen change. */
  function refresh() {
    const id = cur(), body = $(".sm-body", el.main), active = document.activeElement;
    const fk = active && active.dataset ? active.dataset.fk : null;
    const scrolls = [...body.querySelectorAll("[data-scroll]")].map(n => [n.dataset.scroll, n.scrollTop]);
    const tops = ui.flash.panel && !reduced ? [...body.querySelectorAll("[data-shift]")].map(n => [n.dataset.shift, n.getBoundingClientRect().top]) : [];
    fxq = [];
    body.replaceChildren(SCREENS[id].render());
    const desc = $("#desc");
    if (desc && desc.textContent !== SCREENS[id].desc()) desc.textContent = SCREENS[id].desc();
    scrolls.forEach(s => { const n = $('[data-scroll="' + s[0] + '"]', body); if (n) n.scrollTop = s[1]; });
    const target = (ui.focus && $(ui.focus)) || (fk && $('[data-fk="' + CSS.escape(fk) + '"]', body));
    if (target) target.focus({ preventScroll: !ui.focus });
    tops.forEach(tp => { /* sm-panel: what sits below jumps, then is FLIP-ed with a transform */
      const n = $('[data-shift="' + tp[0] + '"]', body), dy = n ? tp[1] - n.getBoundingClientRect().top : 0;
      if (dy) track(gsap.from(n, { y: dy, duration: D.move, ease: E.inOut, clearProps: "transform" }));
    });
    runFx(false);
    ui.flash = {}; ui.focus = null;
  }

  /* ---------- toast (points only, 7.11) ---------- */
  let toastTimer = 0;
  function hideToast() {
    if (el.toast.dataset.state !== "open") return;
    el.toast.dataset.state = "closed";
    gsap.to(el.toast, { opacity: 0, y: reduced ? 0 : 8, duration: reduced ? 0.15 : D.fast, ease: E.in, overwrite: true, onComplete: () => { el.toast.hidden = true; } });
  }
  function toast(text) {
    clearTimeout(toastTimer);
    el.toast.hidden = false;
    el.toast.textContent = text;
    el.toast.dataset.state = "open";
    gsap.fromTo(el.toast, { opacity: 0, y: reduced ? 0 : 8 }, { opacity: 1, y: 0, duration: reduced ? 0.15 : D.base, ease: E.out, overwrite: true });
    toastTimer = setTimeout(hideToast, 4000);
  }
  el.toast.hidden = true;
  gsap.set(el.toast, { xPercent: -50 });
  el.toast.addEventListener("pointerenter", () => clearTimeout(toastTimer));
  el.toast.addEventListener("pointerleave", () => { toastTimer = setTimeout(hideToast, 4000); });

  /* ---------- switcher: a non-modal combobox with a listbox, not a dialog (13.4) ---------- */
  let swItems = [], swAt = 0;
  const swOpen = () => !el.switchLayer.hidden;
  function switchItems(q) {
    const all = [{ label: "Smart Match CPP", id: "entry" }];
    Object.keys(PORTALS).forEach(p => PORTALS[p].screens.forEach(id => {
      all.push({ group: PORTALS[p].name, label: SCREENS[id].menu, id });
      if (id === "match") SMC.UPCOMING.forEach(e => all.push({ group: PORTALS[p].name, label: e.title + " · " + e.when, id, ev: e.id }));
    }));
    return all.filter(i => (i.label + " " + (i.group || "")).toLowerCase().includes(q.trim().toLowerCase()));
  }
  function renderSwitchList() {
    swItems = switchItems(el.switchInput.value);
    swAt = Math.max(0, Math.min(swAt, swItems.length - 1));
    const groups = [];
    swItems.forEach((it, i) => {
      let g = groups[groups.length - 1];
      if (!g || g.name !== it.group) { g = { name: it.group, nodes: [] }; groups.push(g); }
      const here = it.id === cur() && (!it.ev || it.ev === state.hubEvent);
      g.nodes.push(h("div", { class: "b-switch__opt", role: "option", id: "sw-" + i, "aria-selected": String(i === swAt), "data-sub": it.ev ? "true" : null, "data-here": here && !it.ev ? "true" : null,
        onpointerdown: e => e.preventDefault(), onclick: () => switchGo(i), onpointermove: () => { if (swAt !== i) { swAt = i; markSwitch(); } } },
        it.ev && icon("calendar-days", 16), h("span", { text: it.label })));
    });
    el.switchList.replaceChildren(...groups.flatMap((g, gi) => g.name ?
      h("div", { role: "group", "aria-labelledby": "swg-" + gi }, h("p", { class: "sm-label", id: "swg-" + gi, role: "presentation", text: g.name }), g.nodes) : g.nodes));
    markSwitch();
  }
  function markSwitch() {
    el.switchList.querySelectorAll("[role=option]").forEach((n, i) => n.setAttribute("aria-selected", String(i === swAt)));
    const on = $("#sw-" + swAt);
    if (on) { el.switchInput.setAttribute("aria-activedescendant", on.id); on.scrollIntoView({ block: "nearest" }); }
    else el.switchInput.removeAttribute("aria-activedescendant");
  }
  function openSwitch() {
    el.switchLayer.hidden = false;
    el.switchBtn.setAttribute("aria-expanded", "true");
    el.switchInput.value = "";
    swAt = Math.max(0, switchItems("").findIndex(i => i.id === cur() && (!i.ev || i.ev === state.hubEvent)));
    renderSwitchList();
    el.switchInput.focus();
    gsap.fromTo(el.switchPop, { opacity: 0, scale: reduced ? 1 : 0.98 }, { opacity: 1, scale: 1, duration: reduced ? 0.15 : D.fast, ease: E.out, transformOrigin: "0 0", clearProps: "transform,opacity", overwrite: true });
  }
  function closeSwitch(refocus) {
    if (!swOpen()) return;
    el.switchLayer.hidden = true;
    el.switchBtn.setAttribute("aria-expanded", "false");
    if (refocus) (state.portal ? el.switchBtn : $("#title")).focus();
  }
  function switchGo(i) {
    const it = swItems[i];
    if (!it) return;
    closeSwitch(false);
    go(it.id, it.ev ? { hubEvent: it.ev } : null);
  }
  el.switchBtn.addEventListener("click", () => (swOpen() ? closeSwitch(true) : openSwitch()));
  el.switchInput.addEventListener("input", () => { swAt = 0; renderSwitchList(); });
  el.switchInput.addEventListener("keydown", e => {
    const n = swItems.length, k = e.key;
    if (k === "ArrowDown" || k === "ArrowUp") { e.preventDefault(); if (n) { swAt = (swAt + (k === "ArrowDown" ? 1 : n - 1)) % n; markSwitch(); } }
    else if (k === "Home" || k === "End") { e.preventDefault(); swAt = k === "Home" ? 0 : n - 1; markSwitch(); }
    else if (k === "Enter") { e.preventDefault(); switchGo(swAt); }
  });
  el.switchLayer.addEventListener("focusout", e => { if (!el.switchLayer.contains(e.relatedTarget) && e.relatedTarget !== el.switchBtn) closeSwitch(false); });
  document.addEventListener("pointerdown", e => { if (swOpen() && !el.switchPop.contains(e.target) && !el.switchBtn.contains(e.target)) closeSwitch(false); });

  /* ---------- presenter guide (7.16) ---------- */
  let armed = 0;
  function moveStop(d) {
    const i = STOPS.indexOf(cur()) + d;
    if (i >= 0 && i < STOPS.length) go(STOPS[i]);
  }
  function disarm() { clearTimeout(armed); armed = 0; renderGuide(); }
  function resetDemo() {
    if (!armed) { armed = setTimeout(disarm, 5000); renderGuide(); $('[data-fk="reset"]', el.guide).focus(); return; }
    clearTimeout(armed); armed = 0;
    try { localStorage.removeItem(KEY); } catch (err) { /* nothing was stored */ }
    students = SMC.makeStudents(); grace = students.find(s => s.id === SMC.GRACE_ID);
    setState(Object.assign(fresh(), { guideOpen: state.guideOpen, theme: state.theme }), "nav");
  }
  function setTheme(t) { root.dataset.theme = t; setState({ theme: t }, "none"); renderGuide(); $('[data-fk="theme-' + t + '"]', el.guide).focus(); }
  function renderGuide(swap) {
    const id = cur(), g = GUIDE[id], n = STOPS.indexOf(id) + 1, open = state.guideOpen;
    el.guideBtn.setAttribute("aria-expanded", String(open));
    el.guideBtnLabel.textContent = open ? "Hide presenter guide" : "Presenter guide";
    el.guide.dataset.state = open ? "open" : "closed";
    el.shell.dataset.guide = open ? "open" : "closed"; /* from 1440px the shell reserves a column, so the guide covers nothing */
    const nav = (label, d, ic, end) => renderButton({ label, variant: "secondary", icon: end ? null : ic, iconEnd: end ? ic : null, fk: "stop-" + d, onClick: e => { if (!isOff(e.currentTarget)) moveStop(d); },
      attrs: { "aria-disabled": (d < 0 ? n === 1 : n === 9) ? "true" : null, "aria-describedby": "stop-count" } });
    const reset = renderButton({ label: armed ? "Press again to reset" : "Reset demo", variant: "secondary", icon: "rotate-ccw", fk: "reset", onClick: resetDemo, attrs: { "data-state": armed ? "armed" : "idle" } });
    reset.addEventListener("keydown", e => { if (e.repeat) e.preventDefault(); }); /* a held key never confirms */
    if (armed && !reduced) { const bar = h("span", { class: "sm-confirm", "aria-hidden": "true" }); reset.append(bar); gsap.fromTo(bar, { scaleX: 1 }, { scaleX: 0, duration: 5, ease: "none", transformOrigin: "left center" }); }
    const theme = t => h("button", { class: "sm-seg__btn", type: "button", "aria-pressed": String(state.theme === t), "data-fk": "theme-" + t, onclick: () => setTheme(t) }, icon(t === "light" ? "sun" : "moon", 16), h("span", { text: t === "light" ? "Light" : "Dark" }));
    const body = h("div", { class: "sm-guide__body" }, h("h2", { text: g[0] }), h("p", { text: g[1] }), h("ol", null, g[2].map(s => h("li", { text: s }))),
      h("p", { class: "sm-guide__say" }, h("strong", { text: "Say:" }), " \"" + g[3] + "\""));
    el.guide.replaceChildren(h("p", { class: "sm-label" }, icon("presentation", 16), "Presenter guide"), body,
      h("div", { class: "sm-guide__stops" }, h("p", { class: "sm-guide__count", id: "stop-count", text: "Stop " + n + " of 9" }), nav("Back", -1, "chevron-left"), nav("Next", 1, "chevron-right", true)),
      h("div", { class: "sm-guide__tools" }, reset, h("div", { class: "sm-seg", role: "group" }, theme("light"), theme("dark"))));
    if (swap && open) gsap.from(body, { opacity: 0, duration: 0.12, clearProps: "opacity" });
  }
  function toggleGuide(refocus) {
    const open = !state.guideOpen;
    setState({ guideOpen: open }, "none");
    if (armed) { clearTimeout(armed); armed = 0; }
    gsap.killTweensOf(el.guide);
    if (open) {
      el.guide.hidden = false;
      renderGuide();
      gsap.fromTo(el.guide, { opacity: 0, y: reduced ? 0 : 12, scale: reduced ? 1 : 0.98 }, { opacity: 1, y: 0, scale: 1, duration: reduced ? 0.15 : D.base, ease: E.out, transformOrigin: "100% 100%", clearProps: "transform,opacity" });
    } else {
      renderGuide();
      gsap.to(el.guide, { opacity: 0, y: reduced ? 0 : 12, duration: reduced ? 0.15 : D.fast, ease: E.in, onComplete: () => { el.guide.hidden = true; gsap.set(el.guide, { clearProps: "transform,opacity" }); } });
      if (refocus) el.guideBtn.focus();
    }
  }
  el.guideBtn.addEventListener("click", () => toggleGuide(false));

  /* ---------- keys (7.16, 9.2) ---------- */
  document.addEventListener("pointerdown", settle, true);
  document.addEventListener("keydown", e => {
    const t = e.target, tag = t.tagName;
    const text = (tag === "INPUT" && !/^(range|checkbox|radio|button|submit)$/.test(t.type)) || tag === "TEXTAREA";
    const slider = tag === "INPUT" && t.type === "range";
    if (e.key !== "Tab" && e.key !== "Shift") settle();
    if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === "k") {
      if (text && t !== el.switchInput) return;
      e.preventDefault();
      if (swOpen()) closeSwitch(true); else openSwitch();
      return;
    }
    if (e.key === "Escape") {
      if (swOpen()) closeSwitch(true);
      else if (armed) disarm();
      else if (state.guideOpen) toggleGuide(true);
      return;
    }
    if (e.ctrlKey || e.metaKey || e.altKey || text || slider) return;
    if (e.key === "PageDown" || e.key === "PageUp") { e.preventDefault(); if (!e.repeat) moveStop(e.key === "PageDown" ? 1 : -1); }
    else if ((e.key === "g" || e.key === "G") && tag !== "SELECT") toggleGuide(false);
  });
  el.skip.addEventListener("click", e => { e.preventDefault(); el.main.focus(); });
  const rebuild = () => { if (state) navigate(true); };
  mq.sm.addEventListener("change", rebuild);

  /* ---------- boot: saved state, then the review deep links (3.7) ---------- */
  function boot() {
    if (params.get("reset") === "1") { try { localStorage.removeItem(KEY); } catch (e) { /* nothing stored */ } }
    students = SMC.makeStudents();
    grace = students.find(s => s.id === SMC.GRACE_ID);
    state = load();
    const p = params.get("p"), s = params.get("s"), w = (params.get("w") || "").split(",").map(Number);
    if (params.get("iv") === "done") { let st = Object.assign({}, state, ivStart()); GUIDED.forEach(a => { st = Object.assign(st, ivNext(st, a)); }); state = st; }
    if (p === "entry") state.portal = null;
    if (PORTALS[p]) state.portal = p;
    if (SCREENS[s] && s !== "entry") { state.portal = SCREENS[s].portal; state.page = Object.assign({}, state.page, { [state.portal]: s }); }
    if (s === "entry") state.portal = null;
    const reg = params.get("reg");
    if (reg && eventById(reg) && !state.registered.includes(reg)) { state.registered = state.registered.concat(reg); state.lastRegistered = reg; }
    if (/^(chat|msg|book|res)$/.test(params.get("help") || "")) state.helpPanel = params.get("help");
    if (w.length === 4 && w.every(n => Number.isInteger(n) && n >= 0 && n <= 10)) state.weights = { major: w[0], interest: w[1], goal: w[2], past: w[3] };
    if (eventById(params.get("ev"))) state.hubEvent = params.get("ev");
    if (params.has("q")) state.search = params.get("q");
    if (params.has("guide")) state.guideOpen = params.get("guide") === "1";
    if (/^(light|dark)$/.test(params.get("theme") || "")) state.theme = params.get("theme");
    root.dataset.theme = state.theme;
    syncGrace();
    save();
    [el.entryLogo, el.sideLogo].forEach(n => n.append(h("img", { src: SMC.LOGO, alt: "Cal Poly Pomona" })));
    if (/Mac|iPhone|iPad/.test(navigator.platform)) el.kbdMod.textContent = "⌘";
    el.guide.hidden = !state.guideOpen;
    navigate(true);
  }
  boot();
})();
