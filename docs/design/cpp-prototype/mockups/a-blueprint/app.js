/* Smart Match CPP · Direction A: Blueprint
 * Static mockup. Data and matching come from ../../shared/data.js (window.SMC); nothing is re-implemented here.
 * Layout of this file: helpers -> motion -> state -> components (one function each) -> screens -> shell -> boot.
 */
(function () {
  "use strict";

  const SMC = window.SMC, gsap = window.gsap, Flip = window.Flip;
  gsap.registerPlugin(Flip);

  /* ------------------------------------------------------------------ helpers */

  const SVG_NS = "http://www.w3.org/2000/svg";
  const $ = (sel, root) => (root || document).querySelector(sel);

  function add(el, kids) {
    kids.flat(Infinity).forEach(k => {
      if (k == null || k === false) return;
      el.append(k.nodeType ? k : document.createTextNode(String(k)));
    });
    return el;
  }

  /* h("p", { class: "x", text: "..." }, child, ...). Text always goes in as text, never as markup. */
  function h(tag, props, ...kids) {
    const el = document.createElement(tag);
    for (const k in (props || {})) {
      const v = props[k];
      if (v == null || v === false) continue;
      if (k === "class") el.className = v;
      else if (k === "text") el.textContent = v;
      else if (k === "on") for (const e in v) el.addEventListener(e, v[e]);
      else el.setAttribute(k, v === true ? "" : v);
    }
    return add(el, kids);
  }

  function sv(tag, attrs, ...kids) {
    const el = document.createElementNS(SVG_NS, tag);
    for (const k in (attrs || {})) el.setAttribute(k, attrs[k]);
    return add(el, kids);
  }

  /* Lucide icons (ISC), inlined. Constant strings only. */
  const ICONS = {
    "arrow-right": '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "circle-check": '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
    "circle-dot": '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="1"/>',
    "circle-dashed": '<path d="M10.1 2.182a10 10 0 0 1 3.8 0"/><path d="M13.9 21.818a10 10 0 0 1-3.8 0"/><path d="M17.609 3.721a10 10 0 0 1 2.69 2.7"/><path d="M2.182 13.9a10 10 0 0 1 0-3.8"/><path d="M20.279 17.609a10 10 0 0 1-2.7 2.69"/><path d="M21.818 10.1a10 10 0 0 1 0 3.8"/><path d="M3.721 6.391a10 10 0 0 1 2.7-2.69"/><path d="M6.391 20.279a10 10 0 0 1-2.69-2.7"/>',
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
    "id-card": '<path d="M16 10h2"/><path d="M16 14h2"/><path d="M6.17 15a3 3 0 0 1 5.66 0"/><circle cx="9" cy="11" r="2"/><rect x="2" y="5" width="20" height="14" rx="2"/>',
    "rotate-ccw": '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>',
    "presentation": '<path d="M2 3h20"/><path d="M21 3v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V3"/><path d="m7 21 5-5 5 5"/>',
    "chevron-left": '<path d="m15 18-6-6 6-6"/>',
    "chevron-right": '<path d="m9 18 6-6-6-6"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/>',
    "moon": '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
    "send": '<path d="M14.536 21.686a.5.5 0 0 0 .937-.024l6.5-19a.496.496 0 0 0-.635-.635l-19 6.5a.5.5 0 0 0-.024.937l7.93 3.18a2 2 0 0 1 1.112 1.11z"/><path d="m21.854 2.147-10.94 10.939"/>'
  };

  function icon(name, size, cls) {
    const s = sv("svg", {
      viewBox: "0 0 24 24", width: size || 20, height: size || 20, fill: "none", stroke: "currentColor",
      "stroke-width": 2, "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true",
      class: "sm-icon" + (cls ? " " + cls : "")
    });
    s.innerHTML = ICONS[name];
    return s;
  }

  /* Her strings carry two kinds of mark-up: **bold** spans and the arrow glyph, which is an icon slot. */
  function rich(str) {
    return String(str).split(/(\*\*[^*]+\*\*|→)/).map(part => {
      if (part === "→") return icon("arrow-right", 16, "sm-inline-icon");
      if (part.startsWith("**")) return h("strong", { text: part.slice(2, -2) });
      return part;
    });
  }

  const smQuery = window.matchMedia("(max-width: 639px)");
  const isSm = () => smQuery.matches;

  /* ------------------------------------------------------------------ motion */

  const SM_MOTION = {
    dur: { instant: 0.10, fast: 0.16, base: 0.22, move: 0.28, max: 0.40, wash: 0.90 },
    ease: { out: "expo.out", inOut: "power2.inOut", in: "power2.in" },
    stagger: 0.03
  };
  const D = SM_MOTION.dur, E = SM_MOTION.ease;
  const root = document.documentElement;
  const params = new URLSearchParams(location.search);

  const fx = {
    live: new Set(),          // tweens tied to an action; any pointer or key press completes them
    arrival: false,           // entrance motion only after a presenter action, never on page load
    reduced: () => root.dataset.motion === "reduced",
    track(t) {
      fx.live.add(t);
      const done = t.eventCallback("onComplete");
      t.eventCallback("onComplete", () => { fx.live.delete(t); if (done) done(); });
      return t;
    },
    finishAll() {
      for (let i = 0; i < 4 && fx.live.size; i++) {
        [...fx.live].forEach(t => { fx.live.delete(t); t.progress(1); });
      }
    },
    fromTo: (el, a, b) => fx.track(gsap.fromTo(el, a, b)),
    to: (el, b) => fx.track(gsap.to(el, b)),
    /* Arrival: opacity + a short rise. Reduced motion: opacity only, 150ms. */
    enter(el, o) {
      o = o || {};
      if (!el) return null;
      if (fx.reduced()) return fx.fromTo(el, { opacity: 0 }, { opacity: 1, duration: 0.15, ease: "none", clearProps: "opacity" });
      return fx.fromTo(el, { opacity: 0, y: o.y == null ? 8 : o.y, scale: o.scale || 1 },
        { opacity: 1, y: 0, scale: 1, duration: o.dur || D.base, delay: o.delay || 0, ease: E.out, clearProps: "opacity,transform" });
    },
    leave(el, done) {
      return fx.to(el, { opacity: 0, duration: fx.reduced() ? 0.15 : D.fast, ease: fx.reduced() ? "none" : E.in, onComplete: done });
    },
    /* sm-count: whole values only; the final text is always the true value. */
    count(el, from, to, fmt) {
      fmt = fmt || String;
      if (el._count) { fx.live.delete(el._count); el._count.kill(); }
      if (from === to || fx.reduced()) { el.textContent = fmt(to); return; }
      const o = { v: from };
      el._count = fx.to(o, {
        v: to, duration: D.max, ease: E.out,
        onUpdate: () => { el.textContent = fmt(Math.round(o.v)); },
        onComplete: () => { el.textContent = fmt(to); el._count = null; }
      });
    },
    /* sm-bars-grow: bars scale from the left; the numbers are in place from the first frame. */
    barsGrow(els) {
      if (!fx.arrival || fx.reduced() || !els.length) return;
      /* delay + duration + stagger stay inside the 400ms ceiling */
      fx.fromTo(els, { scaleX: 0 }, { scaleX: 1, duration: D.base, ease: E.out, stagger: { amount: Math.min(SM_MOTION.stagger * (els.length - 1), 0.12) }, delay: 0.06, clearProps: "transform" });
    }
  };

  function setMotion(reduce) {
    if (reduce || params.get("rm") === "1") root.dataset.motion = "reduced";
    else delete root.dataset.motion;
  }
  /* One matchMedia block switches every tween to its reduced form (all tweens read fx.reduced()). */
  gsap.matchMedia().add({ reduce: "(prefers-reduced-motion: reduce)", any: "all" }, ctx => setMotion(ctx.conditions.reduce));

  document.addEventListener("pointerdown", fx.finishAll, true);
  document.addEventListener("keydown", e => {
    if (!["Shift", "Control", "Alt", "Meta", "Tab"].includes(e.key)) fx.finishAll();
  }, true);

  /* ------------------------------------------------------------------ content */

  const PORTALS = {
    student: {
      name: "Student portal", who: "Signed in as Grace Delgado · Accounting · Junior",
      pages: [["interview", "Activate my profile"], ["recs", "Events for me"], ["readiness", "My readiness"], ["growth", "My growth"]]
    },
    hub: {
      name: "Career Hub portal", who: "CBA Career Hub (CBACH) staff",
      pages: [["overview", "Term overview"], ["records", "Student records"], ["match", "Match students to an event"]]
    },
    partner: {
      name: "Partner portal", who: "Dana Whitfield · Senior Data Lead, Northline Analytics · CPP alumna, 2014",
      pages: [["talk", "My talk"]]
    }
  };

  const DOORS = [
    ["student", "For students", "Student portal", "Activate your profile through a short AI interview, get events picked for you, and see your growth record.", "Enter as Grace Delgado"],
    ["hub", "For CBACH staff", "Career Hub portal", "Student records, matching students to an event, and term reports for the college.", "Enter as Career Hub staff"],
    ["partner", "For industry partners", "Partner portal", "See who came to your talk, what students asked, and how to stay involved.", "Enter as Dana Whitfield"]
  ];

  /* The nine demo stops, in order (DESIGN.md 2.1). */
  const STOPS = [
    [null, "entry"], ["student", "interview"], ["student", "recs"], ["student", "readiness"], ["student", "growth"],
    ["hub", "overview"], ["hub", "records"], ["hub", "match"], ["partner", "talk"]
  ];

  const N1 = "Design for the next phase — made-up data";
  const N2 = "Scripted for this demo. Not a live AI.";
  const FULL_VERSION = "In the full version these connect to the Career Hub's real booking, messaging and resource pages. Shown here as a demo.";
  const BOOK_LABEL = "Book a 30-minute appointment with a CBACH advisor";

  const SCREENS = {
    interview: {
      title: "Activate my profile", status: ["planned", "Planned · scripted for this demo"],
      desc: () => "The app already has Grace's college record. A short AI interview fills in the rest of her profile card, so event suggestions fit her, not just her major."
    },
    recs: {
      title: "Events picked for Grace", status: ["working", "Matching works in class version"],
      desc: () => "Events come to the student, each with a plain reason. " + (state.ivDone ? "These use her profile card." : "Right now the app only knows her major and past events.")
    },
    readiness: {
      title: "Grace's career readiness", status: ["planned", "Planned · draft markers"],
      desc: () => "Points show effort. Readiness shows how many success markers she has reached, and confirmed steps count double so it can't be raised by self-checks alone."
    },
    growth: {
      title: "Grace's career growth record", status: ["planned", "Planned"],
      desc: () => "Each event attended adds to a record the student can see. The record stays with the college after she graduates, so the college can study what helps students."
    },
    overview: {
      title: "Term overview", status: ["partly", "Partly built"],
      desc: () => "What the college can report each term, drawn from the student records. Shown here for the made-up student body of " + students.length + "."
    },
    records: {
      title: "Student records", status: ["working", "Working in class version"],
      desc: () => "Every student is on file from day one with major, year and events attended. The profile card fills in when the student activates through the AI interview."
    },
    match: {
      title: "Match students to an event", status: ["working", "Working in class version"],
      desc: () => "Pick an event and the app ranks all " + students.length + " students. Staff can adjust how much each factor counts, then invite the top 30 personally."
    },
    talk: {
      title: "Your talk: Northline Analytics", status: ["partly", "Partly built"],
      desc: () => "Behind the Business series · Thu Mar 4, 2027 · what an industry partner sees after speaking. Numbers are illustrative."
    }
  };

  /* The scripted interview (DESIGN.md 2.4). Not a live AI. */
  const TECH = "Technology / information systems", ENT = "Entertainment / sports / media";
  const EXPLORING = "Exploring consulting or data roles";
  const IV = [
    {
      ai: () => "Hi Grace! I can see from your college record that you're an Accounting junior, and you came to **Brand Building at a Streaming Studio** and the **Cybersecurity and Cloud Jobs Q&A**. What made you go to the cloud jobs session?",
      opts: () => ["I'm curious about tech jobs", "A friend brought me", "My professor offered extra credit"]
    },
    { ai: () => "Thanks. Which industries would you like to hear more about? Pick as many as you like. I've pre-selected ones that fit what you've told me and the events you went to.", multi: true },
    {
      ai: () => "Got it. What would you like your next step to be after graduation?",
      opts: () => ["Accounting or audit role (CPA path)", "Data, analytics or IT role", "Finance or real estate role", "Graduate school", "Not sure yet"]
    },
    {
      ai: () => state.goal === "Undecided"
        ? "That's very common for juniors. You picked consulting and technology among your interests. Would you like me to suggest events that help you compare consulting and data roles?"
        : "Great, I'll look for events that fit that goal. One last thing: is it OK to suggest events outside the Accounting department?",
      opts: () => state.goal === "Undecided" ? ["Yes, help me compare", "No thanks"] : ["Yes", "Only accounting events"]
    },
    {
      ai: () => "All set. Your profile card is filled in on the right. You can change it any time, and each event you attend will keep it up to date. Ready to see the events I picked for you?",
      opts: () => ["Show my events"]
    }
  ];
  const GUIDED = ["I'm curious about tech jobs", null, "Not sure yet", "Yes, help me compare", "Show my events"];

  const MARKERS = [
    { k: "resume", res: "Resume guide and templates", name: "Resume ready", steps: ["I have a one-page resume for my field", "Attended a resume workshop", "Resume reviewed by the Career Hub"] },
    { k: "interview", res: "Practice interview tool", name: "Interview ready", steps: ["I feel confident answering common interview questions", "Completed a practice interview", "Rated ready by staff or a speaker"] },
    { k: "network", res: "LinkedIn profile checklist", name: "Networking ready", steps: ["My LinkedIn profile is complete", "Attended 2 or more employer events", "Follow-up conversation with a speaker or alum"] },
    { k: "ethics", res: "Workplace ethics scenarios", name: "Professional ethics ready", steps: ["Answered the workplace scenarios check", "Attended a professional ethics session", "Signed off by an instructor or the Career Hub"] },
    { k: "direction", res: "Career exploration guide", name: "Career direction", steps: ["Profile card completed", "Career goal stated", "Met with a career advisor"] },
    { k: "experience", res: "Internship listings on Handshake", name: "Work experience", steps: ["Listed relevant experience", "Internship, job or project recorded", "Confirmed by a supervisor or faculty member"] }
  ];
  const LEVELS = ["I checked myself", "I did it", "Someone confirmed it"];
  const STEP_WEIGHT = [1, 1, 2]; // confirmed steps count double

  const BOT_HELLO = "Hi Grace! I'm the CBACH assistant bot, an AI that answers quick questions. For advice on your plans, you can message or book a CBACH advisor.";
  const BOT_QUESTIONS = ["Where is the resume template?", "How do I get my resume reviewed?", "What counts as an employer event?", "Talk to a person"];
  function botAnswer(q) {
    if (/template|resume guide/i.test(q)) return { text: "The resume guide and templates are in Career Hub digital resources. Pick the accounting or general business template." };
    if (/review/i.test(q)) return { text: "A CBACH advisor can review your resume in a 30-minute appointment. Bring your latest version.", book: true };
    if (/employer event|count/i.test(q)) return { text: "Info sessions, industry panels, career fairs and employer talks all count. You have 2 so far, which meets the networking step." };
    if (/person|human|advisor|talk/i.test(q)) return { text: "Sure. You can message a CBACH advisor or book a 30-minute appointment.", book: true };
    return { text: "I can help with quick questions about events, resources and your readiness card. For this one, a CBACH advisor is the best person to ask.", book: true };
  }

  const GUIDE = {
    entry: ["Opening (Chau)", "Start here. One sentence on the problem, then pick a door.",
      ["Problem: events struggle to fill seats, contacts sit with individual staff, and nobody can see a student's growth.", "Explain the three doors: one app, three kinds of users, each with its own sign-in.", "Click Student portal."],
      "\"Smart Match brings the right events to the right students, and keeps a record of how each student grows.\""],
    interview: ["Student · AI interview (Chau)", "Show that the app already knows the student's record, and the interview fills in the rest.",
      ["Point to the right side: major, year and events come from college records.", "Answer the chat: curious about tech jobs → Done → Not sure yet → Yes, help me compare.", "Watch the profile card fill in as she answers.", "Say clearly: this interview is scripted for today; a live AI version is planned."],
      "\"Most students never fill in a form. A two-minute conversation does it for them.\""],
    recs: ["Student · Events for me (Chau)", "Show events coming to the student, each with a reason.",
      ["Read one 'Why you' line out loud.", "Mention: before the interview, the app only suggested the audit event because she's an accounting major.", "Click Register on the top event to show the check-in code and points."],
      "\"Every suggestion says why. Staff and students can see it isn't a black box.\""],
    readiness: ["Student · My readiness (Janice)", "Points show effort; readiness shows progress toward being job-ready.",
      ["Point to the ring: readiness now versus the gold mark for a junior.", "Tick one self-check (for example, LinkedIn) and show the % move a little.", "Explain why: confirmed steps count double, so self-checks alone can't raise it much.", "Say the markers are a draft and will follow the college's official list.", "Show the four help options: assistant bot (AI) for quick questions, message an advisor, book an advisor, digital resources. Ask the bot How do I get my resume reviewed? and it hands off to a real advisor."],
      "\"Grace can see where she stands for her year and exactly what to do next.\""],
    growth: ["Student · My growth (Janice)", "The record that stays after graduation.",
      ["Walk the timeline from sophomore year to after graduation.", "Point out that her events lean toward media and technology, which her major alone would never show."],
      "\"Over four years this becomes the college's best evidence of what helps students.\""],
    overview: ["Career Hub · Term overview (Janice)", "What the college can report each term.",
      ["These numbers come from the 300 made-up student records in the class file.", "Point to 'students never reached by an event' as the opportunity.", "Readiness charts are illustrative."],
      "\"For the first time, the Career Hub can see who it isn't reaching.\""],
    records: ["Career Hub · Student records (Janice)", "Every student is on file from day one.",
      ["Type 'Delgado' in search to find Grace; her card shows 'AI interview · today'."],
      "\"Students don't sign up from scratch; they activate a record that already exists.\""],
    match: ["Career Hub · Match students to an event (Chau)", "How staff fill an event.",
      ["Northline is selected: Grace is #4 because of her interview answers.", "Move the 'Same major' slider up and show CIS majors take over the list.", "Close: invite the top 30 personally."],
      "\"Students from any major who said they care about the topic get invited, not only the obvious major.\""],
    talk: ["Partner · My talk (Chau)", "Why industry partners would come back.",
      ["Show who was invited, from five majors.", "Show the turnout compared with a mass email.", "Ask the board: 'Would you use this? What would make you speak again?'"],
      "\"Your contact stays with the college, and you see the difference your talk made.\""]
  };

  /* ------------------------------------------------------------------ state */

  const KEY = "smc.a.v1";
  const WEIGHT_KEYS = ["major", "interest", "goal", "past"];

  function freshState() {
    return {
      portal: null,
      page: { student: "interview", hub: "overview", partner: "talk" },
      ivStep: 0, ivLog: [], ivDone: false, picks: [], goal: "", goalSet: false, cardPointsGiven: false,
      registered: [], lastRegistered: null,
      selfChecks: {},
      helpPanel: null,
      bot: [],
      hubEvent: "E11", weights: Object.assign({}, SMC.DEFAULT_WEIGHTS), search: "",
      guideOpen: false, theme: "light"
    };
  }

  function loadState() {
    const s = freshState();
    try {
      const saved = JSON.parse(localStorage.getItem(KEY) || "null");
      if (saved && typeof saved === "object") {
        Object.keys(s).forEach(k => { if (k in saved && typeof saved[k] === typeof s[k]) s[k] = saved[k]; });
        if (saved.portal === null || PORTALS[saved.portal]) s.portal = saved.portal;
        if (typeof saved.lastRegistered === "string") s.lastRegistered = saved.lastRegistered;
        if (typeof saved.helpPanel === "string") s.helpPanel = saved.helpPanel;
      }
    } catch (e) { /* storage blocked or unreadable: start fresh */ }
    return sanitize(s);
  }

  function sanitize(s) {
    const f = freshState();
    Object.keys(PORTALS).forEach(p => { if (!PORTALS[p].pages.some(pg => pg[0] === s.page[p])) s.page[p] = f.page[p]; });
    WEIGHT_KEYS.forEach(k => { const v = Math.round(Number(s.weights[k])); s.weights[k] = v >= 0 && v <= 10 ? v : f.weights[k]; });
    if (!SMC.UPCOMING.some(e => e.id === s.hubEvent)) s.hubEvent = f.hubEvent;
    s.registered = (Array.isArray(s.registered) ? s.registered : []).filter(id => SMC.UPCOMING.some(e => e.id === id));
    s.picks = (Array.isArray(s.picks) ? s.picks : []).filter(t => SMC.TOPICS.includes(t));
    if (!["chat", "msg", "book", "res"].includes(s.helpPanel)) s.helpPanel = null;
    if (!Array.isArray(s.ivLog)) s.ivLog = [];
    if (!Array.isArray(s.bot)) s.bot = [];
    s.theme = s.theme === "dark" ? "dark" : "light";
    return s;
  }

  function save() {
    try { localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) { /* the page still works without storage */ }
  }

  let state, students, grace;

  /* Grace's record follows the interview exactly as in Ann's file: the goal lands at turn 3, the interests at the end. */
  function syncGrace() {
    grace.goal = state.goalSet ? state.goal : "";
    grace.interests = state.ivDone ? state.picks.slice() : [];
    grace.viaAI = state.ivDone;
  }

  /* Fix F3: one points total, derived, the same on every screen. */
  const points = () => 20 + (state.cardPointsGiven ? 20 : 0) + 10 * state.registered.length + 5 * Object.values(state.selfChecks).filter(Boolean).length;

  function graceSteps() {
    const sc = state.selfChecks;
    return {
      resume: [!!sc.resume, false, false], interview: [!!sc.interview, false, false],
      network: [!!sc.network, grace.events.length >= 2, false], ethics: [!!sc.ethics, false, false],
      direction: [state.ivDone, state.ivDone && !!grace.goal, false], experience: [!!sc.experience, false, false]
    };
  }
  function readinessPct(st) {
    let earned = 0;
    Object.values(st).forEach(a => a.forEach((on, i) => { if (on) earned += STEP_WEIGHT[i]; }));
    return Math.round(earned / 24 * 100);
  }

  const currentScreen = () => state.portal ? state.page[state.portal] : "entry";
  const stopIndex = () => STOPS.findIndex(s => s[1] === currentScreen());
  const eventById = id => SMC.UPCOMING.find(e => e.id === id);

  /* --- interview logic (pure state changes; the screen animates around it) --- */

  function ivStart() {
    if (!state.ivLog.length && !state.ivDone) { state.ivStep = 0; state.ivLog = [{ who: "ai", text: IV[0].ai() }]; }
  }

  /* Returns true when the answer finished the interview. */
  function ivAnswer(text) {
    const step = state.ivStep;
    state.ivLog.push({ who: "me", text });
    if (step === 0 && /tech|data|cloud|cyber|curious/i.test(text) && !state.picks.includes(TECH)) state.picks.push(TECH);
    if (step === 2) {
      const key = Object.keys(SMC.GOALTOPIC).find(g => g.toLowerCase() === text.toLowerCase());
      state.goal = key || (/^graduate school$/i.test(text.trim()) ? "Graduate school"            // fix F2
        : /data|analytic|it\b/i.test(text) ? "Data, analytics or IT role"
        : /account|audit|cpa/i.test(text) ? "Accounting or audit role (CPA path)" : "Undecided");
      state.goalSet = true;
    }
    if (step === 3 && state.goal === "Undecided" && /yes|compare/i.test(text)) state.goal = EXPLORING;
    if (step === 4) {
      state.ivDone = true; state.ivStep = 5; state.cardPointsGiven = true;
      syncGrace(); save();
      return true;
    }
    state.ivStep = step + 1;
    if (state.ivStep === 1) [TECH, ENT].forEach(t => { if (!state.picks.includes(t)) state.picks.push(t); });
    state.ivLog.push({ who: "ai", text: IV[state.ivStep].ai() });
    syncGrace(); save();
    return false;
  }

  const picksText = () => state.picks.length ? state.picks.map(SMC.short).join(", ") : "None of these";

  function ivReset() {
    state.ivStep = 0; state.ivLog = []; state.ivDone = false; state.picks = []; state.goal = ""; state.goalSet = false;
    ivStart(); syncGrace(); save();
  }

  function applyGuided() {
    state.ivStep = 0; state.ivLog = []; state.ivDone = false; state.picks = []; state.goal = ""; state.goalSet = false;
    ivStart();
    GUIDED.forEach(a => ivAnswer(a == null ? picksText() : a));
  }

  function applyDeepLinks() {
    const p = params.get("p"), s = params.get("s");
    if (params.get("iv") === "done") applyGuided();
    const reg = params.get("reg");
    if (reg && eventById(reg) && !state.registered.includes(reg)) { state.registered.push(reg); state.lastRegistered = reg; }
    if (["chat", "msg", "book", "res"].includes(params.get("help"))) state.helpPanel = params.get("help");
    const w = (params.get("w") || "").split(",").map(Number);
    if (w.length === 4 && w.every(n => Number.isInteger(n) && n >= 0 && n <= 10)) WEIGHT_KEYS.forEach((k, i) => { state.weights[k] = w[i]; });
    if (eventById(params.get("ev"))) state.hubEvent = params.get("ev");
    if (params.has("q")) state.search = params.get("q");
    if (params.has("guide")) state.guideOpen = params.get("guide") === "1";
    if (params.get("theme") === "dark" || params.get("theme") === "light") state.theme = params.get("theme");
    if (s === "entry") state.portal = null;
    else if (s) {
      const portal = Object.keys(PORTALS).find(k => PORTALS[k].pages.some(pg => pg[0] === s));
      if (portal) { state.portal = portal; state.page[portal] = s; }
    } else if (p && PORTALS[p]) state.portal = p;
  }

  /* ------------------------------------------------------------------ components */

  const STATUS_ICON = { working: "circle-check", partly: "circle-dot", planned: "circle-dashed" };
  const renderStatus = (kind, label) => h("span", { class: "sm-status", "data-kind": kind }, icon(STATUS_ICON[kind], 16), label);
  const renderMarker = () => h("p", { class: "sm-marker" }, icon("info", 16), N1);
  const renderScripted = () => h("p", { class: "sm-scripted" }, icon("info", 16), N2);

  function renderButton(p) {
    const b = h("button", { class: "sm-button", type: "button", "data-variant": p.variant || "primary", "data-size": p.size, id: p.id },
      p.icon ? icon(p.icon, 20) : null, p.label, p.iconEnd ? icon(p.iconEnd, 20) : null);
    for (const k in (p.attrs || {})) b.setAttribute(k, p.attrs[k]);
    if (p.onClick) b.addEventListener("click", e => { if (b.getAttribute("aria-disabled") !== "true") p.onClick(e, b); });
    return b;
  }

  const renderChip = (label, onClick) => h("button", { class: "sm-chip", type: "button", "data-kind": "option", on: { click: onClick } }, label);
  const renderPill = (label, tone) => h("span", { class: "sm-pill", "data-tone": tone }, label);
  const renderLabel = (text, tag) => h(tag || "h2", { class: "sm-label", text });

  /* sm-message: a persistent outcome line, Ann's sentence, next to the control that caused it. */
  const renderMessageSlot = () => h("p", { class: "sm-message", role: "status" });
  function showMessage(slot, text) {
    slot.replaceChildren(icon("circle-check", 20), h("span", { text }));
    fx.enter(slot, { y: 4 });
  }

  function renderStat(value, label, opts) {
    const fig = h("span", { class: "sm-figure", "aria-hidden": "true", text: value });
    const sr = h("span", { class: "sm-vh", text: value + " " + label });
    const el = h("div", { class: "sm-stat" }, fig, h("span", { class: "sm-stat__label", "aria-hidden": "true", text: label }), sr);
    return { el, fig, set(v, fmt) { sr.textContent = (fmt || String)(v) + " " + label; }, opts };
  }

  /* sm-bars: label, bar, value. Scale maximum is the caller's; never rescaled. */
  function renderBars(rows, max, opts) {
    opts = opts || {};
    const fills = [];
    const ul = h("ul", { class: "sm-bars", "data-tone": opts.gold ? "gold" : null }, rows.map(([label, v]) => {
      const fill = h("div", { class: "sm-bars__fill", style: "width:" + Math.round(v / max * 100) + "%" });
      fills.push(fill);
      return h("li", null, h("span", { class: "sm-bars__label", text: label }),
        h("div", { class: "sm-bars__track", "aria-hidden": "true" }, fill),
        h("span", { class: "sm-bars__value sm-mono", text: v + (opts.suffix || "") }));
    }));
    mounted.push(() => fx.barsGrow(fills));
    return ul;
  }

  function renderHead(id) {
    const def = SCREENS[id];
    return h("div", { class: "sm-head" },
      h("h1", { tabindex: "-1", text: def.title }),
      renderStatus(def.status[0], def.status[1]),
      h("p", { class: "sm-head__desc" }, def.desc().split(/(made-up)/).map(t => t === "made-up" ? h("span", { class: "sm-nowrap", text: t }) : t)));
  }

  function renderTurn(t, speaker, onBook) {
    if (t.who === "me") return h("div", { class: "sm-turn", "data-who": "student" }, h("p", null, h("span", { class: "sm-vh", text: "Grace: " }), t.text));
    const n = h("div", { class: "sm-turn", "data-who": "assistant" }, h("span", { class: "sm-label", text: speaker }), h("p", null, rich(t.text)));
    if (t.book) n.append(renderButton({ label: BOOK_LABEL, size: "compact", onClick: onBook }));
    return n;
  }

  /* Keeps the newest turn fully in view. The log always starts at the top of a turn, never mid-line:
     it shows as many earlier turns as fit above the newest one, from `from` (an index) or earlier. */
  function fitLog(log, spacer, from) {
    const turns = [...log.children].filter(n => n !== spacer);
    if (!turns.length) return;
    spacer.style.height = "0px";
    const last = turns[turns.length - 1], bottom = last.offsetTop + last.offsetHeight, room = log.clientHeight - 28;
    let i = turns.length - 1;
    while (i > 0 && bottom - turns[i - 1].offsetTop <= room) i--;
    if (from != null && from < i && bottom - turns[from].offsetTop <= room) i = from;
    const top = i === 0 ? 0 : turns[i].offsetTop - 12;
    spacer.style.height = Math.max(0, top + log.clientHeight - bottom - 28) + "px";
    log.scrollTop = top;
  }

  /* Free-text field + Send. Send is aria-disabled while the field is empty; the reason is N8. */
  function renderAskForm(p) {
    const input = h("input", { class: "sm-field", type: "text", id: p.id, placeholder: p.placeholder, autocomplete: "off", "aria-label": p.label });
    const hint = h("span", { class: "sm-vh", id: p.id + "-hint", text: p.hint });
    const send = renderButton({ label: "Send", iconEnd: "send", attrs: { type: "submit", "aria-disabled": "true", "aria-describedby": p.id + "-hint" } });
    input.addEventListener("input", () => {
      send.setAttribute("aria-disabled", input.value.trim() ? "false" : "true");
      if (input.value.trim()) hint.className = "sm-vh";
    });
    const form = h("form", { class: "sm-form", novalidate: true }, input, send);
    form.addEventListener("submit", e => {
      e.preventDefault();
      const v = input.value.trim();
      if (!v) { hint.className = "sm-hint"; return; }
      p.onSubmit(v);
    });
    return h("div", { class: "sm-group" }, form, hint);
  }

  /* ------------------------------------------------------------------ screens */

  let mounted = [];   // callbacks run once the screen is in the document

  function screenEntry() {
    return h("div", { class: "sm-entry", "data-screen": "entry" },
      h("div", { class: "sm-entry__intro" },
        h("h1", { tabindex: "-1", text: "Smart Match CPP" }),
        h("p", { class: "sm-entry__lede", text: "A student-built app for the CBA Career Hub. Events find the right students, students build a record of their career growth, and industry partners see who they reached." })),
      h("div", { class: "sm-doors" }, DOORS.map(([p, eyebrow, title, body, go]) =>
        h("button", { class: "sm-door", type: "button", "data-door": p, on: { click: () => navigate(p) } },
          h("span", { class: "sm-door__eyebrow", text: eyebrow }),
          h("span", { class: "sm-door__title", "data-flip-id": "portal-" + p, text: title }),
          h("span", { class: "sm-door__body", text: body }),
          h("span", { class: "sm-door__go" }, go, icon("arrow-right", 20))))),
      h("p", { class: "sm-helper", text: "Concept prototype. All students, partners, events and numbers are made up; the 300 student records come from the class exercise file." }));
  }

  /* --- Student · Activate my profile --- */
  function screenInterview() {
    ivStart();
    const SPEAKER = "Smart Match assistant";
    const spacer = h("div", { "aria-hidden": "true" });
    const log = h("div", { class: "sm-transcript__log" }, state.ivLog.map(t => renderTurn(t, SPEAKER)), spacer);
    const live = h("div", { class: "sm-vh", role: "log", "aria-live": "polite" });
    const reply = h("div", { class: "sm-transcript__reply" });

    const interestsDd = h("dd"), goalDd = h("dd");
    let shownPicks = [], shownGoal = null;

    function fillCard(animate) {
      const picks = state.picks.slice();
      if (picks.length) {
        const pills = h("div", { class: "sm-pills" }, picks.map(t => {
          const pill = renderPill(SMC.short(t), "new");
          if (animate && !shownPicks.includes(t)) fx.enter(pill, { y: 0, scale: 0.9 });
          return pill;
        }));
        interestsDd.replaceChildren(pills);
      } else {
        interestsDd.replaceChildren(h("span", { class: "sm-muted", text: "Not yet" }));
        if (animate && shownPicks.length) fx.enter(interestsDd.firstChild, { y: 0 });
      }
      shownPicks = picks;
      const goal = state.goalSet ? (state.goal === EXPLORING ? "Undecided · exploring consulting or data roles" : state.goal) : null;
      if (goal !== shownGoal || !goalDd.firstChild) {
        goalDd.replaceChildren(goal ? h("span", { text: goal }) : h("span", { class: "sm-muted", text: "Not yet" }));
        if (animate) fx.enter(goalDd.firstChild, { y: 0 });
        shownGoal = goal;
      }
    }

    function answer(text) {
      const before = log.children.length - 1;
      const done = ivAnswer(text);
      if (done) {
        navigate("student", "recs");
        toast("Profile card saved. 20 points added.");
        return;
      }
      const fresh = state.ivLog.slice(before).map(t => renderTurn(t, SPEAKER));
      fresh.forEach(n => log.insertBefore(n, spacer));
      fillReply();
      fillCard(true);
      fitLog(log, spacer);
      live.textContent = $("p", fresh[fresh.length - 1]).textContent;
      /* sm-turn: the student's line, then the scripted reply 80ms later, whole. Options work from the first frame. */
      fx.enter(fresh[0], { y: 6, dur: D.fast });
      fx.enter(fresh[1], { y: 6, delay: 0.08 });
      fx.enter(reply, { y: 0, delay: 0.08 });
      const next = $("button, input", reply);
      if (next) next.focus({ preventScroll: true });
    }

    function fillReply() {
      if (state.ivDone) {
        reply.replaceChildren(h("div", { class: "sm-finished" }, h("span", { text: "Interview finished." }),
          renderButton({ label: "Start over", variant: "secondary", icon: "rotate-ccw", onClick: () => { ivReset(); refreshMain(); const b = $(".sm-transcript__reply button"); if (b) b.focus(); } })));
        return;
      }
      const step = IV[state.ivStep];
      if (step.multi) {
        reply.replaceChildren(
          h("div", { class: "sm-chips" }, SMC.TOPICS.map(t => {
            const chip = h("button", { class: "sm-chip", type: "button", "data-kind": "toggle", "aria-pressed": String(state.picks.includes(t)) }, icon("check", 16), SMC.short(t));
            chip.addEventListener("click", () => {
              const i = state.picks.indexOf(t);
              if (i >= 0) state.picks.splice(i, 1); else state.picks.push(t);
              chip.setAttribute("aria-pressed", String(i < 0));
              save(); fillCard(true);
            });
            return chip;
          })),
          renderButton({ label: "Done", onClick: () => answer(picksText()) }));
        return;
      }
      reply.replaceChildren(
        h("div", { class: "sm-chips" }, step.opts().map(o => renderChip(o, () => answer(o)))),
        renderAskForm({ id: "iv-field", label: "Type an answer", placeholder: "Or type your own answer…", hint: "Type an answer first.", onSubmit: answer }));
    }

    fillReply(); fillCard(false);
    mounted.push(() => fitLog(log, spacer));

    const card = h("section", { class: "sm-card sm-profile", "data-tone": "page" },
      h("div", { class: "sm-profile__person" }, h("span", { class: "sm-avatar", "aria-hidden": "true", text: "GD" }),
        h("div", null, h("h2", { text: "Grace Delgado" }), h("p", { class: "sm-helper", text: "Profile card" }))),
      h("div", { class: "sm-group" }, renderLabel("From college records (already on file)", "h3"),
        h("dl", { class: "sm-kv" }, h("dt", { text: "Major" }), h("dd", { text: grace.major }), h("dt", { text: "Year" }), h("dd", { text: grace.year }),
          h("dt", { text: "Events" }), h("dd", null, grace.events.map(e => h("span", { text: SMC.PAST[e][0] }))))),
      h("div", { class: "sm-group" }, renderLabel("From the interview", "h3"),
        h("dl", { class: "sm-kv" }, h("dt", { text: "Interests" }), interestsDd, h("dt", { text: "Next step" }), goalDd)),
      h("p", { class: "sm-helper", text: "Later: students can answer by voice or by typing." }));

    return [h("div", { class: "sm-interview" },
      h("section", { class: "sm-transcript", "data-variant": "interview", "aria-label": SCREENS.interview.title }, renderScripted(), log, reply, live),
      card)];
  }

  /* --- Student · Events for me --- */
  function renderCode(eventId) {
    const q = SMC.qrCells(eventId);
    const svg = sv("svg", { viewBox: "0 0 29 29", role: "img", "aria-label": "Sample check-in code" }, sv("rect", { width: 29, height: 29, "data-fill": "plate" }));
    q.cells.forEach(([x, y]) => svg.append(sv("rect", { x, y, width: 1, height: 1 })));
    q.finders.forEach(([x, y]) => svg.append(sv("rect", { x, y, width: 7, height: 7 }), sv("rect", { x: x + 1, y: y + 1, width: 5, height: 5, "data-fill": "plate" }), sv("rect", { x: x + 2, y: y + 2, width: 3, height: 3 })));
    return svg;
  }

  function renderEventRow(e, onRegister) {
    const registered = state.registered.includes(e.id);
    const btn = renderButton({ label: "Register", onClick: () => onRegister(e, btn) });
    if (registered) confirmButton(btn, false);
    return h("li", { class: "sm-event" },
      h("div", { class: "sm-date", "aria-hidden": "true" }, h("b", { text: e.d }), h("span", { text: e.m })),
      h("div", { class: "sm-event__main" }, h("h3", { text: e.title }),
        h("p", { class: "sm-helper", text: e.host + " · " + e.when + " · 60 seats" }),
        h("p", { class: "sm-why" }, h("b", { text: "Why you:" }), " " + SMC.whyYou(e))),
      h("div", { class: "sm-event__actions" }, btn, h("span", { class: "sm-match-line", text: "match " + e.total + " of 10" })));
  }

  function confirmButton(btn, animate) {
    const ic = icon("check", 20);
    btn.dataset.variant = "confirmed";
    btn.setAttribute("aria-disabled", "true");
    btn.replaceChildren("Registered", ic);
    if (animate) { fx.enter(btn, { y: 0 }); if (!fx.reduced()) fx.fromTo(ic, { scale: 0.4, opacity: 0 }, { scale: 1, opacity: 1, duration: D.fast, ease: E.out, clearProps: "all" }); }
  }

  function screenRecs() {
    const out = [];
    if (!state.ivDone) {
      out.push(h("div", { class: "sm-callout", "data-layout": "row" }, h("span", { text: "Finish the short interview to get better suggestions." }),
        renderButton({ label: "Activate my profile", size: "compact", onClick: () => navigate("student", "interview") })));
    }
    const pointsFig = h("span", { class: "sm-figure", "data-size": "48", text: points() });
    const codeBox = h("div", { class: "sm-checkin__code" });
    const codeName = h("p", { class: "sm-num", style: "font-weight:600" });
    const checkin = h("section", { class: "sm-checkin", hidden: !state.lastRegistered },
      codeBox,
      h("div", { class: "sm-checkin__text" }, renderLabel("Check-in code"), codeName,
        h("p", { class: "sm-helper", text: "Scanned at the door. Attendance goes on her record and points are added. Sample code only." }),
        renderStatus("planned", "Planned")),
      h("div", { class: "sm-checkin__points" }, renderLabel("Career points"), pointsFig, h("p", { class: "sm-helper", text: "Points exist in the early version" })));

    function fillCheckin() {
      const e = eventById(state.lastRegistered);
      if (!e) return;
      codeBox.replaceChildren(renderCode(e.id));
      codeName.textContent = e.title + " · " + e.when;
    }
    function register(e, btn) {
      if (state.registered.includes(e.id)) return;
      const before = points();
      state.registered.push(e.id); state.lastRegistered = e.id; save();
      confirmButton(btn, true);
      toast("Registered. 10 points added.");
      const wasHidden = checkin.hidden;
      checkin.hidden = false; fillCheckin();
      fx.count(pointsFig, before, points());
      if (wasHidden) fx.enter(checkin);
      scrollIntoView(checkin);
    }
    fillCheckin();
    /* Event titles are h3; the list gets its menu label as a hidden h2 so no heading level is skipped. */
    out.push(h("h2", { class: "sm-vh", text: "Events for me" }), h("ul", { class: "sm-events" }, SMC.rankEvents(grace).map(e => renderEventRow(e, register))), checkin);
    return out;
  }

  /* Brings a node into view without moving focus (sm-register). */
  function scrollIntoView(el) {
    const r = el.getBoundingClientRect();
    const over = r.bottom + 88 - window.innerHeight;
    if (over <= 0) return;
    const o = { y: window.scrollY }, to = window.scrollY + Math.min(over, r.top - 16);
    if (fx.reduced()) { window.scrollTo(0, to); return; }
    fx.to(o, { y: to, duration: D.max, ease: E.out, onUpdate: () => window.scrollTo(0, o.y) });
  }

  /* --- Student · My readiness --- */
  function screenReadiness() {
    const target = SMC.TARGET[grace.year];
    const C = 2 * Math.PI * 66;
    let steps = graceSteps(), pct = readinessPct(steps), pts = points();
    const pctFmt = v => v + "%";

    const arc = sv("circle", { class: "sm-ring__arc", cx: 75, cy: 75, r: 66, fill: "none", "stroke-width": 12, "stroke-linecap": "round", "stroke-dasharray": C + " " + C, "stroke-dashoffset": C * (1 - pct / 100) });
    const a = 2 * Math.PI * target / 100;
    const tick = (cls, w, r0, r1) => sv("line", { class: cls, "stroke-width": w, x1: 75 + r0 * Math.cos(a), y1: 75 + r0 * Math.sin(a), x2: 75 + r1 * Math.cos(a), y2: 75 + r1 * Math.sin(a) });
    const ringSvg = sv("svg", { viewBox: "0 0 150 150", role: "img" },
      sv("g", { transform: "rotate(-90 75 75)" },
        sv("circle", { class: "sm-ring__track", cx: 75, cy: 75, r: 66, fill: "none", "stroke-width": 12 }), arc,
        tick("sm-ring__key", 5, 58, 74), tick("sm-ring__tick", 3.4, 59, 73)));
    const ringFig = h("span", { class: "sm-figure", "data-size": "48", text: pctFmt(pct) });
    const ring = h("div", { class: "sm-ring" }, ringSvg, h("div", { class: "sm-ring__center", "aria-hidden": "true" }, ringFig, h("span", { class: "sm-helper", text: "career ready" })));
    const nameRing = () => ringSvg.setAttribute("aria-label", pct + "% career ready. Target for a " + grace.year.toLowerCase() + ": " + target + "%.");
    nameRing();

    const tNow = renderStat(pctFmt(pct), "readiness now");
    const tTarget = renderStat(pctFmt(target), "target for a " + grace.year.toLowerCase() + " (gold mark)");
    const tPoints = renderStat(String(pts), "career points");

    const lead = h("strong");
    const leadText = () => { const gap = target - pct; return gap <= 0 ? "On track for your year." : gap <= 20 ? "A little behind for a junior." : "Behind for a junior, and that's fixable."; };
    lead.textContent = leadText();
    /* Third variant kept for the port; its condition is never met in Ann's code (T9). */
    const next = !state.ivDone ? ["Finish your profile interview", "Adds about 8% and 20 points", "interview"]
      : !steps.resume[1] ? ["Sign up for a resume workshop", "The Career Hub can then review your resume", "recs"]
      : ["Book a practice interview", "Interview ready is your lowest marker", "recs"];
    const callout = h("div", { class: "sm-callout", "data-layout": "row" },
      h("p", null, lead, " Next step: " + next[0] + ". ", h("span", { class: "sm-helper", text: next[1] })),
      renderButton({ label: "Go", size: "compact", onClick: () => navigate("student", next[2]) }));

    /* help */
    const helpMsg = renderMessageSlot();
    const panelHost = h("div", { id: "help-panel", hidden: true });
    const helpButtons = {};
    const helpBtn = (kind, label, variant) => (helpButtons[kind] = renderButton({ label, variant, attrs: { "aria-expanded": "false", "aria-controls": "help-panel" }, onClick: () => setHelp(state.helpPanel === kind ? null : kind, "label") }));
    const help = h("section", { class: "sm-help" },
      h("span", { class: "sm-avatar", "data-tone": "green", "aria-hidden": "true", text: "CB" }),
      h("div", { class: "sm-help__body" },
        h("h2", { text: "Need help with any marker? The CBA Career Hub (CBACH) is here." }),
        h("p", { text: "The assistant bot (AI) answers quick questions any time. CBACH advisors, real people on the Career Hub staff, answer messages and meet with you to review resumes, run practice interviews and help you choose a direction." }),
        h("div", { class: "sm-help__groups" },
          h("div", { class: "sm-help__group" }, renderLabel("Help yourself, any time", "h3"),
            h("div", null, helpBtn("chat", "Chat with the CBACH assistant bot"), helpBtn("res", "Career Hub digital resources"))),
          h("div", { class: "sm-help__group" }, renderLabel("Talk to a person", "h3"),
            h("div", null, helpBtn("msg", "Message a CBACH advisor", "secondary"), helpBtn("book", BOOK_LABEL, "secondary"))))));

    /* markers */
    const dotEls = {};
    const markerCards = MARKERS.map(m => {
      const st = steps[m.k];
      dotEls[m.k] = st.map((on, i) => h("i", { "data-state": on ? "on" : "off", "data-tone": i === 2 ? "gold" : null }));
      const msg = renderMessageSlot();
      const stepEls = m.steps.map((txt, i) => {
        if (i === 0 && m.k !== "direction") {
          const box = h("input", { type: "checkbox", id: "sc-" + m.k, checked: st[0] });
          box.checked = st[0];
          box.addEventListener("change", () => { state.selfChecks[m.k] = box.checked; save(); if (box.checked) toast("Self-check saved. 5 points added."); refresh(); });
          return h("li", null, h("label", { class: "sm-step sm-check", for: "sc-" + m.k }, box, h("span", { text: txt }), h("span", { class: "sm-step__level", text: LEVELS[0] })));
        }
        return h("li", { class: "sm-step" },
          h("span", { class: "sm-step__mark", "data-state": st[i] ? "on" : "off" }, icon("check", 16), h("span", { class: "sm-vh", text: st[i] ? "done" : "not yet" })),
          h("span", { class: st[i] ? null : "sm-muted", text: txt }), h("span", { class: "sm-step__level", text: LEVELS[i] }));
      });
      return h("section", { class: "sm-marker-card" },
        h("div", { class: "sm-marker-card__head" }, h("h3", { text: m.name }), h("div", { class: "sm-dots", "aria-hidden": "true" }, dotEls[m.k])),
        h("ul", { class: "sm-steps" }, stepEls),
        h("div", { class: "sm-marker-card__links" },
          renderButton({ label: m.res, variant: "link", onClick: () => showMessage(msg, "Opens the Career Hub page: " + m.res) }),
          renderButton({ label: "Ask the assistant bot", variant: "link", onClick: () => {
            state.bot.push({ who: "ai", text: "You're looking at **" + m.name + "**. I can point you to resources, or help you book a CBACH advisor." });
            setHelp("chat", "field", true);
          } })),
        msg);
    });
    const markers = h("div", { class: "sm-markers" }, markerCards);
    const closing = h("p", { class: "sm-helper", text: "Draft markers for discussion. If the college has official Career Success Markers, the names here should match them. Readiness is private to the student and her advisor unless she chooses to share it." });

    /* sm-ring-draw + sm-count after a self-check */
    function refresh() {
      const was = pct, wasPts = pts;
      steps = graceSteps(); pct = readinessPct(steps); pts = points();
      MARKERS.forEach(m => steps[m.k].forEach((on, i) => { dotEls[m.k][i].dataset.state = on ? "on" : "off"; }));
      lead.textContent = leadText(); nameRing();
      tNow.set(pct, pctFmt); tPoints.set(pts);
      fx.count(ringFig, was, pct, pctFmt); fx.count(tNow.fig, was, pct, pctFmt); fx.count(tPoints.fig, wasPts, pts);
      const off = C * (1 - pct / 100);
      gsap.killTweensOf(arc);
      if (fx.reduced()) arc.setAttribute("stroke-dashoffset", off);
      else fx.to(arc, { attr: { "stroke-dashoffset": off }, duration: D.max, ease: E.out });
    }

    /* help panels: one open at a time; the content below is FLIP-ed to its new place, never height-animated */
    function panelNode(kind) {
      if (kind === "chat") return panelChat();
      const msg = renderMessageSlot();
      if (kind === "msg") {
        const ta = h("textarea", { class: "sm-field", id: "adv-msg", rows: "3" });
        ta.value = "Hi, could someone review my resume? I'm an accounting junior interested in data and consulting roles.";
        const hint = h("span", { class: "sm-vh", id: "adv-hint", text: "Type a message first." });
        const share = h("input", { type: "checkbox", id: "adv-share" }); share.checked = true;
        const send = renderButton({ label: "Send message", attrs: { "aria-describedby": "adv-hint", "aria-disabled": "false" }, onClick: () => {
          setHelp(null);
          showMessage(helpMsg, "Sent. A CBACH advisor usually replies within one business day.");
          helpButtons.msg.focus();
        } });
        ta.addEventListener("input", () => { const empty = !ta.value.trim(); send.setAttribute("aria-disabled", String(empty)); hint.className = empty ? "sm-hint" : "sm-vh"; });
        return h("section", { class: "sm-panel" }, h("h2", { class: "sm-label", tabindex: "-1", text: "Message a CBACH advisor (a person on the Career Hub staff)" }),
          h("label", { class: "sm-field-label", for: "adv-msg" }, "Your message", ta), hint,
          h("label", { class: "sm-check", for: "adv-share" }, share, h("span", { text: "Share my readiness card with the advisor so they can see where I am" })),
          send, h("p", { class: "sm-helper", text: "Messages go to Career Hub staff, not to the bot. " + FULL_VERSION }));
      }
      if (kind === "book") {
        return h("section", { class: "sm-panel" }, h("h2", { class: "sm-label", tabindex: "-1", text: "Book a 30-minute appointment with a CBACH advisor (a person on the Career Hub staff)" }),
          h("div", { class: "sm-chips" }, ["Mon Oct 12 · 10:00 am", "Tue Oct 13 · 2:30 pm", "Thu Oct 15 · 11:00 am"].map(s =>
            h("button", { class: "sm-chip sm-num", type: "button", "data-kind": "option", on: { click: () => showMessage(msg, "Booked: " + s + " with a CBACH advisor. A reminder will be sent.") } }, s))),
          msg, h("p", { class: "sm-helper", text: FULL_VERSION }));
      }
      return h("section", { class: "sm-panel" }, h("h2", { class: "sm-label", tabindex: "-1", text: "Career Hub digital resources" }),
        h("div", { class: "sm-chips" }, MARKERS.map(m => renderChip(m.res, () => showMessage(msg, "Opens: " + m.res)))),
        msg, h("p", { class: "sm-helper", text: FULL_VERSION }));
    }

    function panelChat() {
      const SPEAKER = "CBACH assistant bot · AI";
      if (!state.bot.length) state.bot.push({ who: "ai", text: BOT_HELLO });
      const openBooking = () => setHelp("book", "label");
      const spacer = h("div", { "aria-hidden": "true" });
      const log = h("div", { class: "sm-transcript__log" }, state.bot.map(t => renderTurn(t, SPEAKER, openBooking)), spacer);
      const live = h("div", { class: "sm-vh", role: "log", "aria-live": "polite" });
      function ask(q) {
        const reply = Object.assign({ who: "ai" }, botAnswer(q));
        state.bot.push({ who: "me", text: q }, reply); save();
        const me = renderTurn({ who: "me", text: q }), ai = renderTurn(reply, SPEAKER, openBooking);
        log.insertBefore(me, spacer); log.insertBefore(ai, spacer);
        fitLog(log, spacer);
        live.textContent = reply.text;
        fx.enter(me, { y: 6, dur: D.fast }); fx.enter(ai, { y: 6, delay: 0.08 });
        const field = $("#bot-field"); if (field) { field.value = ""; field.dispatchEvent(new Event("input")); }
      }
      mounted.push(() => fitLog(log, spacer));
      return h("section", { class: "sm-panel" },
        h("h2", { class: "sm-label", tabindex: "-1", text: "CBACH assistant bot (AI) · for quick questions" }),
        h("div", { class: "sm-transcript", "data-variant": "bot" }, renderScripted(), log,
          h("div", { class: "sm-transcript__reply" },
            h("div", { class: "sm-chips" }, BOT_QUESTIONS.map(q => renderChip(q, () => ask(q)))),
            renderAskForm({ id: "bot-field", label: "Ask the assistant bot", placeholder: "Ask a quick question…", hint: "Type a question first.", onSubmit: ask })), live),
        h("p", { class: "sm-helper", text: "The bot answers quick questions. For advice, it sends you to a CBACH advisor. " + FULL_VERSION }));
    }

    function setHelp(kind, focus, forceRebuild) {
      if (kind === state.helpPanel && !forceRebuild && panelHost.firstChild) return;
      const below = [markers, closing];
      const flip = !fx.reduced() && panelHost.isConnected ? Flip.getState(below) : null;
      state.helpPanel = kind; save();
      helpMsg.replaceChildren();
      Object.keys(helpButtons).forEach(k => { helpButtons[k].setAttribute("aria-expanded", String(k === kind)); if (k === kind) helpButtons[k].dataset.state = "open"; else delete helpButtons[k].dataset.state; });
      mounted = [];
      panelHost.replaceChildren(kind ? panelNode(kind) : "");
      panelHost.hidden = !kind;
      mounted.forEach(fn => fn()); mounted = [];
      if (flip) fx.track(Flip.from(flip, { duration: D.move, ease: E.inOut, overwrite: true }));
      if (kind && panelHost.isConnected) {
        fx.enter(panelHost.firstChild);
        const target = focus === "field" ? $("#bot-field", panelHost) : focus === "label" ? $("h2", panelHost) : null;
        if (target) target.focus();
      }
    }
    if (state.helpPanel) { const k = state.helpPanel; state.helpPanel = null; setHelp(k); }

    mounted.push(() => {
      if (!fx.arrival || fx.reduced()) return;
      fx.fromTo(arc, { attr: { "stroke-dashoffset": C } }, { attr: { "stroke-dashoffset": C * (1 - pct / 100) }, duration: 0.3, ease: E.out, delay: 0.1 });
    });

    return [
      h("div", { class: "sm-rtop" }, ring,
        h("div", { class: "sm-rtop__side" }, h("div", { class: "sm-stats", "data-cols": "3" }, tNow.el, tTarget.el, tPoints.el), callout)),
      help, helpMsg, panelHost, markers, closing];
  }

  /* --- Student · My growth --- */
  function screenGrowth() {
    const reg = state.registered.map(eventById);
    const counts = {};
    grace.events.forEach(e => SMC.PAST[e][2].forEach(t => { counts[SMC.short(t)] = (counts[SMC.short(t)] || 0) + 1; }));
    reg.forEach(e => e.topics.forEach(t => { counts[SMC.short(t)] = (counts[SMC.short(t)] || 0) + 1; }));
    const rows = Object.entries(counts).sort((a, b) => b[1] - a[1]);
    const term = (title, items, future) => h("li", { "data-state": future ? "future" : "past" }, h("h3", { text: title }),
      h("ul", null, items.map(([text, tag, tone, muted]) => h("li", { class: muted ? "sm-muted" : null }, h("span", { text }), tag ? renderPill(tag, tone) : null))));
    const fall = [state.ivDone ? ["Profile card completed through AI interview", "+20 points"] : ["Profile card not yet completed", null, null, true]]
      .concat(reg.map(e => [e.title, "registered", "new"]));
    return [h("div", { class: "sm-grid2" },
      h("section", { class: "sm-block" }, renderLabel("Timeline"),
        h("ol", { class: "sm-timeline" },
          term("Fall 2025 · Sophomore", [[SMC.PAST.E04[0], "attended"]]),
          term("Spring 2026", [[SMC.PAST.E08[0], "attended"]]),
          term("Fall 2026 · Junior", fall),
          term("Summer 2027", [["Internship", "recorded later", "new"]], true),
          term("After graduation", [["First job and employer", "recorded later", "new"]], true))),
      h("section", { class: "sm-block" }, renderLabel("Topics she has explored"),
        renderBars(rows, Math.max(3, ...rows.map(r => r[1]))),
        h("div", { class: "sm-stats", "data-cols": "2" }, renderStat(String(2 + reg.length), "events attended or registered").el, renderStat(String(points()), "career points").el),
        h("p", { class: "sm-helper", text: "An Accounting major whose events lean toward media and technology. Her record shows a path her major alone would never reveal." })))];
  }

  /* --- Career Hub · Term overview --- */
  function screenOverview() {
    const o = SMC.overviewStats(students), r = SMC.hubReadiness(students);   // fix F1: cards shown as counted
    const chart = (label, note, bars) => h("section", { class: "sm-block" }, renderLabel(label), note ? h("p", { class: "sm-helper", text: note }) : null, bars);
    return [
      h("div", { class: "sm-stats" },
        renderStat(String(o.n), "student records loaded").el, renderStat(String(o.attended), "students who attended at least one event").el,
        renderStat(String(o.cards), "students with a profile card").el, renderStat(String(o.neverReached), "students never reached by an event").el),
      h("div", { class: "sm-grid2" },
        chart("Event attendance by major", null, renderBars(o.attendanceByMajor, o.attendanceByMajor[0][1])),
        chart("Events that brought in first-time students", "Share of each event's attendees for whom it was their first career event.", renderBars(o.firstTimers, 100, { gold: true, suffix: "%" })),
        chart("Average readiness by year (illustrative)", null, renderBars(r.map(x => [x[0] + " (" + x[3] + ")", x[1]]), 100, { suffix: "%" })),
        chart("Share on track for their year (illustrative)", "Targets: freshman 20%, sophomore 40%, junior 60%, senior 85%. Shows where the Career Hub should focus, for example seniors who are behind.", renderBars(r.map(x => [x[0], x[2]]), 100, { gold: true, suffix: "%" }))),
      h("section", { class: "sm-card", "data-tone": "page" }, renderLabel("How student data is handled (proposed)"),
        h("ul", { class: "sm-list" }, ["Students activate their own profile; the interview is optional.", "The college owns the records, and they stay after students graduate.", "Reports show group totals. Partners never see individual student records."].map(t => h("li", { text: t }))))];
  }

  /* Grace's name in a list: tint plus an icon and hidden words, never colour alone. */
  const renderWho = s => s.id === SMC.GRACE_ID
    ? h("span", { class: "sm-who" }, icon("id-card", 20), h("span", { class: "sm-vh", text: "Grace Delgado, the student from the demo " }), h("span", { "aria-hidden": "true", text: s.name }))
    : s.name;

  /* sm-table: a real table from md up, stacked rows at sm. cols: [[label, cellFn, className]] */
  function renderRow(cols, item, id, isGrace, sm) {
    const row = sm
      ? h("li", null, cols.map(([label, cell, cls]) => h("div", null, h("span", { class: "sm-stack__k", text: label }), h("span", { class: cls }, cell(item)))))
      : h("tr", null, cols.map(([, cell, cls]) => h("td", { class: cls }, cell(item))));
    row.dataset.flipId = id;
    if (isGrace) row.dataset.grace = "true";
    return row;
  }

  function renderTable(name, caption, cols, sm) {
    const body = sm ? h(name === "match" ? "ol" : "ul", { class: "sm-stack" }) : h("tbody");
    const empty = h("p", { class: "sm-empty", hidden: true });
    const box = sm ? h("div", { class: "sm-block" }, body, empty)
      : h("div", { class: "sm-tablebox" }, h("table", { class: "sm-table", "data-table": name }, h("caption", { class: "sm-vh", text: caption }),
        h("thead", null, h("tr", null, cols.map(c => h("th", { scope: "col", text: c[0] })))), body), empty);
    function fitScroll() {
      if (sm) return;
      if (box.scrollHeight > box.clientHeight + 1) { box.tabIndex = 0; box.setAttribute("role", "region"); box.setAttribute("aria-label", caption); }
      else { box.removeAttribute("tabindex"); box.removeAttribute("role"); box.removeAttribute("aria-label"); }
    }
    return { box, body, empty, fitScroll };
  }

  /* --- Career Hub · Student records --- */
  function screenRecords() {
    const sm = isSm();
    const cardCell = s => s.viaAI ? renderPill("AI interview · today", "new") : (s.interests.length || s.goal) ? renderPill("Completed") : h("span", { class: "sm-muted", text: "Not yet" });
    const cols = [["ID", s => s.id, "sm-mono"], ["Name", renderWho], ["Major", s => s.major], ["Year", s => s.year], ["Events", s => s.events.length, "sm-mono"], ["Profile card", cardCell]];
    const t = renderTable("records", SCREENS.records.title, cols, sm);
    t.empty.textContent = "No records match that search.";
    const count = h("p", { class: "sm-num" });
    const more = h("p", { class: "sm-helper", text: "Showing the first 25. Search to narrow the list." });
    const status = h("div", { class: "sm-vh", role: "status" });
    const input = h("input", { class: "sm-field", type: "search", id: "search", placeholder: "Try Delgado", autocomplete: "off" });
    input.value = state.search;
    let timer;
    function fill(announce) {
      const q = state.search.toLowerCase();
      const hits = students.filter(s => (s.name + " " + s.major + " " + s.id).toLowerCase().includes(q));
      t.body.replaceChildren(...hits.slice(0, 25).map(s => renderRow(cols, s, s.id, s.id === SMC.GRACE_ID, sm)));
      count.textContent = hits.length + " of " + students.length + " records";
      more.hidden = hits.length <= 25;
      t.empty.hidden = hits.length > 0;
      t.fitScroll();
      if (announce) { clearTimeout(timer); timer = setTimeout(() => { status.textContent = count.textContent; }, 400); }
    }
    input.addEventListener("input", () => { state.search = input.value; save(); fill(true); });
    fill(false);
    mounted.push(t.fitScroll);
    return [h("div", { class: "sm-controls" }, h("label", { class: "sm-field-label", for: "search" }, "Search by name, major or ID", input), count), t.box, more, status];
  }

  /* --- Career Hub · Match students to an event --- */
  function screenMatch() {
    const sm = isSm();
    const cols = [["#", () => "", "sm-mono sm-rank"], ["Student", r => renderWho(r.s)], ["Major", r => r.s.major], ["Why on the list", r => r.reason],
      ["What we know", r => r.s.viaAI ? "Profile card (AI interview)" : r.info]];
    const t = renderTable("match", SCREENS.match.title, cols, sm);
    t.empty.textContent = "No student matches with these weights. Raise at least one weight above 0.";
    const graceLine = h("p", { class: "sm-grace-line sm-num" });
    const status = h("div", { class: "sm-vh", role: "status" });
    const inviteMsg = renderMessageSlot();
    const under = h("div", { class: "sm-under" }, h("span", { class: "sm-num", text: "Showing 15 of the top 30." }),
      renderButton({ label: "Send personal invitations to top 30", onClick: () => showMessage(inviteMsg, "In the full version, each student gets a personal invitation and a reminder.") }));
    const cache = new Map();
    let cacheEvent = null, frame = 0, timer;

    /* sm-rerank: existing row nodes are re-ordered (never rebuilt) so Flip can carry them and the slider keeps its drag. */
    function update(animate) {
      const ev = eventById(state.hubEvent);
      if (cacheEvent !== ev.id) { cache.clear(); cacheEvent = ev.id; }
      const ranked = SMC.rankStudents(students, ev, state.weights), top = ranked.slice(0, 15);
      const before = [...t.body.children];
      const flip = animate && !fx.reduced() && before.length ? Flip.getState(before, { simple: true }) : null;
      const rows = top.map((r, i) => {
        let row = cache.get(r.s.id);
        if (!row) { row = renderRow(cols, r, r.s.id, r.s.id === SMC.GRACE_ID, sm); cache.set(r.s.id, row); }
        $(".sm-rank", row).textContent = i + 1;      // numerals change at the start, not mid-flight
        return row;
      });
      /* sm-wash: rows that arrive carry a gold wash that fades after they land (CSS, opacity only). Never blocks. */
      const was = new Set(before);
      rows.forEach(r => { if (animate && !fx.reduced() && before.length && !was.has(r) && !r.dataset.grace) r.dataset.wash = "true"; else delete r.dataset.wash; });
      t.body.replaceChildren(...rows);
      t.empty.hidden = rows.length > 0;
      under.hidden = !rows.length;
      const gi = ranked.findIndex(r => r.s.id === SMC.GRACE_ID);
      graceLine.textContent = gi >= 0 ? "Grace Delgado is #" + (gi + 1) + " on this list" + (grace.viaAI ? " because of her interview answers" : "") + "."
        : grace.viaAI ? "Grace Delgado is not in the top 30 for this event." : "Grace has not done her interview yet, so the app knows little about her.";
      if (!animate) { t.fitScroll(); return; }
      clearTimeout(timer); timer = setTimeout(() => { status.textContent = graceLine.textContent; }, 600);
      if (flip) {
        fx.track(Flip.from(flip, {
          targets: rows, duration: D.move, ease: E.inOut, absolute: false, overwrite: true, simple: true,
          onEnter: els => gsap.fromTo(els, { opacity: 0 }, { opacity: 1, duration: D.base, ease: E.out, overwrite: true, clearProps: "opacity" })
        }));
      } else if (fx.reduced()) {
        gsap.fromTo(t.body, { opacity: 0 }, { opacity: 1, duration: 0.15, ease: "none", overwrite: true, clearProps: "opacity" });
      }
    }
    const schedule = () => { if (!frame) frame = requestAnimationFrame(() => { frame = 0; update(true); }); };

    const picker = h("select", { class: "sm-field sm-event-picker", id: "event" }, SMC.UPCOMING.map(e => h("option", { value: e.id, text: e.title + " · " + e.when })));
    picker.value = state.hubEvent;
    picker.addEventListener("change", () => { state.hubEvent = picker.value; save(); inviteMsg.replaceChildren(); schedule(); });

    const weights = [["major", "Same major"], ["interest", "Said they're interested"], ["goal", "Career goal fits"], ["past", "Went to similar events"]].map(([k, label]) => {
      const val = h("span", { class: "sm-weight__value", "aria-hidden": "true", text: state.weights[k] });
      const input = h("input", { type: "range", min: "0", max: "10", step: "1", id: "w-" + k });
      const paint = () => { input.style.setProperty("--fill", "calc(14px + (100% - 28px) * " + state.weights[k] / 10 + ")"); val.textContent = state.weights[k]; };
      input.value = state.weights[k]; paint();
      input.addEventListener("input", () => { state.weights[k] = Number(input.value); paint(); schedule(); });
      input.addEventListener("change", save);
      return h("div", { class: "sm-weight" }, h("div", { class: "sm-weight__head" }, h("label", { for: "w-" + k, text: label }), val), input);
    });

    update(false);
    mounted.push(t.fitScroll);
    return [h("div", { class: "sm-controls" }, h("label", { class: "sm-field-label", for: "event" }, "Event", picker)),
      h("div", { class: "sm-weights" }, weights), graceLine, t.box, under, inviteMsg, status];
  }

  /* --- Partner · My talk --- */
  function screenTalk() {
    const msg = renderMessageSlot();
    const funnel = [["Invited personally", 30], ["Signed up", 19], ["Attended", 14]];
    const actions = [["Offer another talk", "Offer sent to the Career Hub"], ["Meet interested students", "Students who asked to connect will be notified"], ["Post an internship", "Internship post sent to the Career Hub for review"]];
    const bars = [];
    const funnelEl = h("ul", { class: "sm-funnel" }, funnel.map(([label, v]) => {
      const bar = h("span", { class: "sm-funnel__bar sm-mono", style: "width:" + Math.max(16, v / 30 * 70) + "%", text: v });
      bars.push(bar);
      return h("li", null, bar, h("span", { text: label }));
    }));
    mounted.push(() => fx.barsGrow(bars));
    return [h("div", { class: "sm-grid2" },
      h("section", { class: "sm-block" }, renderLabel("Who was invited"),
        h("p", { class: "sm-helper", text: "Students who said they're interested in technology or data, from every major, not only Computer Information Systems." }),
        renderBars([["Accounting", 8], ["Computer Info Systems", 7], ["Finance, RE & Law", 6], ["IB & Marketing", 5], ["Management & HR", 4]], 8)),
      h("section", { class: "sm-block" }, renderLabel("How your talk filled"), funnelEl,
        h("p", { class: "sm-helper", text: "A mass email to all students for a similar talk brought about 6 people." })),
      h("section", { class: "sm-block" }, renderLabel("What students asked you"),
        h("div", { class: "sm-quotes" },
          h("blockquote", { class: "sm-quote", text: "\"What should an accounting student learn first to move into data work?\"" }),
          h("blockquote", { class: "sm-quote", text: "\"Does Northline hire interns from outside computer science?\"" })),
        h("p", { class: "sm-helper sm-num", text: "Average rating 4.6 of 5 from 14 students." })),
      h("section", { class: "sm-block" }, renderLabel("Stay involved"),
        h("div", { class: "sm-actions" }, actions.map(([label, out], i) => renderButton({ label, variant: i ? "secondary" : "primary", onClick: () => showMessage(msg, out) }))),
        msg,
        h("p", { class: "sm-helper", text: "You see totals and questions, never individual student records. Your contact stays with the college, not with one staff member." })))];
  }

  const BUILD = { interview: screenInterview, recs: screenRecs, readiness: screenReadiness, growth: screenGrowth, overview: screenOverview, records: screenRecords, match: screenMatch, talk: screenTalk };

  function renderScreen(id) {
    if (id === "entry") return screenEntry();
    return h("div", { class: "sm-screen", "data-screen": id }, renderHead(id), BUILD[id]());
  }

  /* ------------------------------------------------------------------ shell */

  const topbar = $("#topbar"), body = $("#body"), main = $("#main"), shell = $("#shell");
  const guideButton = $("#guide-button"), guide = $("#guide"), toastHost = $("#toast");
  add($("#marker-bar"), [icon("info", 16), N1]);   // N1 below 1024px; the top bar carries it above

  function renderTopbar() {
    const p = state.portal;
    const logo = h("span", { class: "sm-logo" }, h("img", { src: SMC.LOGO, alt: "Cal Poly Pomona" }));
    topbar.dataset.variant = p ? "portal" : "entry";
    if (!p) { topbar.replaceChildren(logo, renderMarker()); return; }
    topbar.replaceChildren(logo,
      h("div", { class: "sm-topbar__id" }, h("span", { class: "sm-topbar__name", "data-flip-id": "portal-" + p, text: PORTALS[p].name }), h("span", { class: "sm-topbar__who", text: PORTALS[p].who })),
      renderMarker(),
      renderButton({ label: "Switch portal", variant: "secondary", onClick: () => navigate(null) }));
  }

  function renderNav() {
    const old = $("nav", body);
    if (old) old.remove();
    const p = state.portal;
    body.dataset.portal = p || "none";
    if (!p) return;
    body.prepend(h("nav", { class: "sm-nav", "aria-label": PORTALS[p].name }, h("ul", null, PORTALS[p].pages.map(([id, label]) =>
      h("li", null, h("button", { type: "button", "aria-current": state.page[p] === id ? "page" : null, on: { click: () => navigate(p, id) } }, label))))));
    /* The menu is a scrolling strip below 1024px: keep the current item in view. */
    const list = $("nav ul", body), cur = $('nav [aria-current="page"]', body);
    if (list.scrollWidth > list.clientWidth) list.scrollLeft = cur.parentNode.offsetLeft - 48;
  }

  function mountScreen() {
    mounted = [];
    main.replaceChildren(renderScreen(currentScreen()));
    mounted.forEach(fn => fn());
    mounted = [];
  }
  function refreshMain() { const a = fx.arrival; fx.arrival = false; mountScreen(); fx.arrival = a; }

  function renderApp() {
    root.dataset.screen = currentScreen();
    renderTopbar(); renderNav(); mountScreen(); renderGuide(true);
  }

  const focusTitle = () => { const t = $("h1", main); if (t) t.focus({ preventScroll: true }); };

  /* sm-screen / sm-portal. The new screen is in the document (and its h1 focused) at once; the old one
     leaves as a ghost above it. Door to portal: the door's title travels to the portal name (Flip). */
  function navigate(portal, page) {
    fx.finishAll();
    const from = { portal: state.portal, page: currentScreen() };
    const to = { portal, page: portal ? (page || state.page[portal]) : "entry" };
    if (from.portal === to.portal && from.page === to.page) { focusTitle(); return; }
    clearToast();
    const reduced = fx.reduced();
    const old = main.firstElementChild, rect = old.getBoundingClientRect();
    const portalChange = from.portal !== to.portal;
    let flip = null;
    if (!reduced && portalChange && (!from.portal || !to.portal)) {
      const src = from.portal ? $(".sm-topbar__name", topbar) : $('[data-flip-id="portal-' + to.portal + '"]', main);
      if (src) { flip = Flip.getState(src); if (!from.portal) src.style.visibility = "hidden"; }
    }

    state.portal = to.portal;
    if (to.portal) state.page[to.portal] = to.page;
    save();
    fx.arrival = true;
    window.scrollTo(0, 0);
    renderApp();
    focusTitle();

    const ghost = h("div", { class: "sm-ghost", "aria-hidden": "true", inert: true }, old);
    old.querySelectorAll("[data-flip-id]").forEach(n => n.removeAttribute("data-flip-id"));
    const base = shell.getBoundingClientRect();
    ghost.style.cssText = "top:" + (rect.top - base.top) + "px;left:" + (rect.left - base.left) + "px;width:" + rect.width + "px;height:" + Math.max(0, Math.min(rect.height, window.innerHeight - rect.top)) + "px";
    shell.append(ghost);
    fx.leave(ghost, () => ghost.remove());

    const screen = main.firstElementChild, nav = $("nav", body);
    if (reduced) { fx.enter(screen); return; }
    if (flip) {
      const target = to.portal ? $(".sm-topbar__name", topbar) : $('[data-flip-id="portal-' + from.portal + '"]', main);
      if (target) fx.track(Flip.from(flip, { targets: target, duration: D.move, ease: E.inOut, scale: true, absolute: false }));
    }
    const delay = portalChange ? 0.1 : D.fast;
    fx.enter(screen, { delay });
    if (portalChange && nav) fx.enter(nav, { delay, y: 0 });
  }

  function stopBy(step) {
    const i = stopIndex() + step;
    if (i < 0 || i >= STOPS.length) return;
    navigate(STOPS[i][0], STOPS[i][1]);
  }

  /* --- presenter guide --- */
  let resetTimer = 0, resetArmed = false;

  function renderGuide(swap) {
    const open = state.guideOpen;
    root.dataset.guide = open ? "open" : "closed";
    guideButton.replaceChildren(icon("presentation", 20), open ? "Hide presenter guide" : "Presenter guide");
    guideButton.setAttribute("aria-expanded", String(open));
    guide.dataset.state = open ? "open" : "closed";
    guide.hidden = !open;
    disarmReset();
    if (!open) { guide.replaceChildren(); return; }
    const g = GUIDE[currentScreen()], i = stopIndex();
    const stopBtn = (label, step, ic, end) => renderButton({ label, variant: "secondary", size: "compact", icon: end ? null : ic, iconEnd: end ? ic : null,
      attrs: { "aria-disabled": String(i + step < 0 || i + step >= STOPS.length), "aria-describedby": "guide-stop" }, onClick: () => stopBy(step) });
    const reset = renderButton({ label: "Reset demo", variant: "secondary", size: "compact", icon: "rotate-ccw", id: "reset", onClick: onReset });
    reset.addEventListener("keydown", e => { if (e.repeat) e.preventDefault(); });   // a held key never confirms
    const themeBtn = (name, label, ic) => renderButton({ label, variant: "secondary", size: "compact", icon: ic, attrs: { "aria-pressed": String(state.theme === name) }, onClick: () => { state.theme = name; save(); applyTheme(); renderGuide(); } });
    const content = h("div", { class: "sm-guide__content" },
      h("p", { class: "sm-label", text: "Presenter guide" }),
      h("h2", { text: g[0] }),
      h("div", { class: "sm-guide__stops" }, h("span", { class: "sm-guide__stop", id: "guide-stop", text: "Stop " + (i + 1) + " of 9" }),
        h("div", null, stopBtn("Back", -1, "chevron-left"), stopBtn("Next", 1, "chevron-right", true))),
      h("p", { text: g[1] }),
      h("ol", null, g[2].map(s => h("li", null, rich(s)))),
      h("p", { class: "sm-guide__say" }, h("strong", { text: "Say:" }), " " + g[3]));
    guide.replaceChildren(content, h("div", { class: "sm-guide__foot" }, reset, h("div", { class: "sm-segment" }, themeBtn("light", "Light", "sun"), themeBtn("dark", "Dark", "moon"))));
    if (swap && fx.arrival) gsap.fromTo(content, { opacity: 0 }, { opacity: 1, duration: 0.12, ease: "none", clearProps: "opacity" });
  }

  function toggleGuide(focusButton) {
    fx.finishAll();
    state.guideOpen = !state.guideOpen; save();
    if (state.guideOpen) {
      renderGuide();
      if (fx.reduced()) fx.enter(guide); else fx.fromTo(guide, { opacity: 0, y: 12, scale: 0.98 }, { opacity: 1, y: 0, scale: 1, duration: D.base, ease: E.out, clearProps: "opacity,transform" });
    } else {
      guide.hidden = false;
      root.dataset.guide = "closed";
      guideButton.replaceChildren(icon("presentation", 20), "Presenter guide");
      guideButton.setAttribute("aria-expanded", "false");
      fx.to(guide, { opacity: 0, duration: fx.reduced() ? 0.15 : D.fast, ease: E.in, clearProps: "opacity", onComplete: () => renderGuide() });
    }
    if (focusButton) guideButton.focus();
  }
  guideButton.addEventListener("click", () => toggleGuide(false));

  function disarmReset() {
    clearTimeout(resetTimer); resetArmed = false;
    const b = $("#reset");
    if (b) b.replaceChildren(icon("rotate-ccw", 20), "Reset demo");
  }
  function onReset(e, b) {
    if (!resetArmed) {
      resetArmed = true;
      const bar = h("span", { class: "sm-button__timer", "aria-hidden": "true" });
      b.replaceChildren(icon("rotate-ccw", 20), "Press again to reset", fx.reduced() ? null : bar);
      if (!fx.reduced()) gsap.fromTo(bar, { scaleX: 1 }, { scaleX: 0, duration: 5, ease: "none" });   // sm-confirm
      resetTimer = setTimeout(disarmReset, 5000);
      return;
    }
    const keep = { theme: state.theme, guideOpen: state.guideOpen };
    try { localStorage.removeItem(KEY); } catch (err) { /* nothing to clear */ }
    state = Object.assign(freshState(), keep);
    students = SMC.makeStudents(); grace = students.find(s => s.id === SMC.GRACE_ID);
    syncGrace(); save();
    fx.finishAll();
    fx.arrival = false;
    window.scrollTo(0, 0);
    renderApp(); focusTitle();
  }

  function applyTheme() { root.dataset.theme = state.theme; }

  /* --- toast: points only; 4 seconds; pauses on hover --- */
  let toastTimer = 0;
  function clearToast() { clearTimeout(toastTimer); toastHost.replaceChildren(); toastHost.dataset.state = "closed"; }
  function toast(text) {
    clearTimeout(toastTimer);
    const box = h("span", { class: "sm-toast__box", text });
    const hide = () => fx.to(box, { opacity: 0, y: fx.reduced() ? 0 : 8, duration: fx.reduced() ? 0.15 : D.fast, ease: E.in, onComplete: () => { if (box.isConnected) { box.remove(); toastHost.dataset.state = "closed"; } } });
    const arm = () => { clearTimeout(toastTimer); toastTimer = setTimeout(hide, 4000); };
    box.addEventListener("pointerenter", () => clearTimeout(toastTimer));
    box.addEventListener("pointerleave", arm);
    toastHost.replaceChildren(box);
    toastHost.dataset.state = "open";
    gsap.fromTo(box, { opacity: 0, y: fx.reduced() ? 0 : 8 }, { opacity: 1, y: 0, duration: fx.reduced() ? 0.15 : D.base, ease: E.out });
    arm();
  }

  /* --- keys: PageDown / PageUp move between stops, G toggles the guide, Esc closes it --- */
  document.addEventListener("keydown", e => {
    const t = e.target, tag = t && t.tagName;
    const inText = tag === "TEXTAREA" || (tag === "INPUT" && !["checkbox", "range"].includes(t.type));
    const inSlider = tag === "INPUT" && t.type === "range";
    if (e.key === "PageDown" || e.key === "PageUp") {
      if (inText || inSlider) return;
      e.preventDefault();
      stopBy(e.key === "PageDown" ? 1 : -1);
    } else if ((e.key === "g" || e.key === "G") && !e.ctrlKey && !e.metaKey && !e.altKey) {
      if (inText || e.repeat) return;
      toggleGuide(false);
    } else if (e.key === "Escape") {
      if (resetArmed) disarmReset();
      else if (state.guideOpen) toggleGuide(true);
    }
  });

  $(".sm-skip").addEventListener("click", e => { e.preventDefault(); main.focus(); });

  /* Tables are real tables from 640px up and stacked rows below: rebuild when the breakpoint is crossed. */
  smQuery.addEventListener("change", () => { if (["records", "match"].includes(currentScreen())) refreshMain(); });

  /* ------------------------------------------------------------------ boot */

  if (params.get("reset") === "1") { try { localStorage.removeItem(KEY); } catch (e) { /* nothing to clear */ } }
  state = loadState();
  students = SMC.makeStudents();
  grace = students.find(s => s.id === SMC.GRACE_ID);
  applyDeepLinks();
  sanitize(state);
  syncGrace();
  save();
  applyTheme();
  setMotion(window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  renderApp();
})();
