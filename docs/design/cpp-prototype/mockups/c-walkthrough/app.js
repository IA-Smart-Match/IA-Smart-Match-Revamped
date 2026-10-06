/* Smart Match CPP · Direction C: Walkthrough (static mockup; see NOTES.md).
   Structure: tokens → copy → state → motion → components (render*) → screens (screen*) → shell → boot.
   One state object, one save(), go() for a stop change, update() for a change inside a screen. */
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

/* ---------- copy (DESIGN.md section 2, verbatim) ---------- */
const N1 = "Design for the next phase — made-up data";
const N2 = "Scripted for this demo. Not a live AI.";
const STOPS = ["entry", "interview", "recs", "readiness", "growth", "overview", "records", "match", "talk"];
const PORTALS = {
  student: { name: "Student portal", who: "Signed in as Grace Delgado · Accounting · Junior",
    items: [["interview", "Activate my profile"], ["recs", "Events for me"], ["readiness", "My readiness"], ["growth", "My growth"]] },
  hub: { name: "Career Hub portal", who: "CBA Career Hub (CBACH) staff",
    items: [["overview", "Term overview"], ["records", "Student records"], ["match", "Match students to an event"]] },
  partner: { name: "Partner portal", who: "Dana Whitfield · Senior Data Lead, Northline Analytics · CPP alumna, 2014",
    items: [["talk", "My talk"]] }
};
const SCREEN = {
  entry: { portal: null, title: "Smart Match CPP" },
  interview: { portal: "student", title: "Activate my profile", status: ["planned", "Planned · scripted for this demo"],
    desc: "The app already has Grace's college record. A short AI interview fills in the rest of her profile card, so event suggestions fit her, not just her major." },
  recs: { portal: "student", title: "Events picked for Grace", status: ["working", "Matching works in class version"],
    desc: "Events come to the student, each with a plain reason." },
  readiness: { portal: "student", title: "Grace's career readiness", status: ["planned", "Planned · draft markers"],
    desc: "Points show effort. Readiness shows how many success markers she has reached, and confirmed steps count double so it can't be raised by self-checks alone." },
  growth: { portal: "student", title: "Grace's career growth record", status: ["planned", "Planned"],
    desc: "Each event attended adds to a record the student can see. The record stays with the college after she graduates, so the college can study what helps students." },
  overview: { portal: "hub", title: "Term overview", status: ["partly", "Partly built"],
    desc: "What the college can report each term, drawn from the student records. Shown here for the made-up student body of 300." },
  records: { portal: "hub", title: "Student records", status: ["working", "Working in class version"],
    desc: "Every student is on file from day one with major, year and events attended. The profile card fills in when the student activates through the AI interview." },
  match: { portal: "hub", title: "Match students to an event", status: ["working", "Working in class version"],
    desc: "Pick an event and the app ranks all 300 students. Staff can adjust how much each factor counts, then invite the top 30 personally." },
  talk: { portal: "partner", title: "Your talk: Northline Analytics", status: ["partly", "Partly built"],
    desc: "Behind the Business series · Thu Mar 4, 2027 · what an industry partner sees after speaking. Numbers are illustrative." }
};
const DOORS = [
  ["student", "For students", "Student portal", "Activate your profile through a short AI interview, get events picked for you, and see your growth record.", "Enter as Grace Delgado"],
  ["hub", "For CBACH staff", "Career Hub portal", "Student records, matching students to an event, and term reports for the college.", "Enter as Career Hub staff"],
  ["partner", "For industry partners", "Partner portal", "See who came to your talk, what students asked, and how to stay involved.", "Enter as Dana Whitfield"]
];
const TECH = "Technology / information systems", ENT = "Entertainment / sports / media";
const EXPLORING = "Exploring consulting or data roles";
/* Scripted turns. A nested array is a bold span. */
const IV = {
  t1: { say: ["Hi Grace! I can see from your college record that you're an Accounting junior, and you came to ", ["Brand Building at a Streaming Studio"], " and the ", ["Cybersecurity and Cloud Jobs Q&A"], ". What made you go to the cloud jobs session?"],
    opts: ["I'm curious about tech jobs", "A friend brought me", "My professor offered extra credit"] },
  t2: { say: ["Thanks. Which industries would you like to hear more about? Pick as many as you like. I've pre-selected ones that fit what you've told me and the events you went to."], toggles: true },
  t3: { say: ["Got it. What would you like your next step to be after graduation?"],
    opts: ["Accounting or audit role (CPA path)", "Data, analytics or IT role", "Finance or real estate role", "Graduate school", "Not sure yet"] },
  t4a: { say: ["That's very common for juniors. You picked consulting and technology among your interests. Would you like me to suggest events that help you compare consulting and data roles?"],
    opts: ["Yes, help me compare", "No thanks"] },
  t4b: { say: ["Great, I'll look for events that fit that goal. One last thing: is it OK to suggest events outside the Accounting department?"],
    opts: ["Yes", "Only accounting events"] },
  t5: { say: ["All set. Your profile card is filled in on the right. You can change it any time, and each event you attend will keep it up to date. Ready to see the events I picked for you?"],
    opts: ["Show my events"] }
};
const GUIDED = ["I'm curious about tech jobs", "Technology, Entertainment", "Not sure yet", "Yes, help me compare", "Show my events"];
const BOT_FIRST = ["Hi Grace! I'm the CBACH assistant bot, an AI that answers quick questions. For advice on your plans, you can message or book a CBACH advisor."];
const BOT_Q = ["Where is the resume template?", "How do I get my resume reviewed?", "What counts as an employer event?", "Talk to a person"];
const BOT_A = [
  ["The resume guide and templates are in Career Hub digital resources. Pick the accounting or general business template.", false],
  ["A CBACH advisor can review your resume in a 30-minute appointment. Bring your latest version.", true],
  ["Info sessions, industry panels, career fairs and employer talks all count. You have 2 so far, which meets the networking step.", false],
  ["Sure. You can message a CBACH advisor or book a 30-minute appointment.", true],
  ["I can help with quick questions about events, resources and your readiness card. For this one, a CBACH advisor is the best person to ask.", true]
];
const BOOK = "Book a 30-minute appointment with a CBACH advisor";
const FULL = "In the full version these connect to the Career Hub's real booking, messaging and resource pages. Shown here as a demo.";
const HELP = {
  chat: { label: "Chat with the CBACH assistant bot", variant: "primary", title: "CBACH assistant bot (AI) · for quick questions" },
  res: { label: "Career Hub digital resources", variant: "primary", title: "Career Hub digital resources" },
  msg: { label: "Message a CBACH advisor", variant: "secondary", title: "Message a CBACH advisor (a person on the Career Hub staff)" },
  book: { label: BOOK, variant: "secondary", title: BOOK + " (a person on the Career Hub staff)" }
};
const SLOTS = ["Mon Oct 12 · 10:00 am", "Tue Oct 13 · 2:30 pm", "Thu Oct 15 · 11:00 am"];
const LEVELS = ["I checked myself", "I did it", "Someone confirmed it"];
const MARKERS = [
  { k: "resume", name: "Resume ready", steps: ["I have a one-page resume for my field", "Attended a resume workshop", "Resume reviewed by the Career Hub"], res: "Resume guide and templates" },
  { k: "interview", name: "Interview ready", steps: ["I feel confident answering common interview questions", "Completed a practice interview", "Rated ready by staff or a speaker"], res: "Practice interview tool" },
  { k: "network", name: "Networking ready", steps: ["My LinkedIn profile is complete", "Attended 2 or more employer events", "Follow-up conversation with a speaker or alum"], res: "LinkedIn profile checklist" },
  { k: "ethics", name: "Professional ethics ready", steps: ["Answered the workplace scenarios check", "Attended a professional ethics session", "Signed off by an instructor or the Career Hub"], res: "Workplace ethics scenarios" },
  { k: "direction", name: "Career direction", steps: ["Profile card completed", "Career goal stated", "Met with a career advisor"], res: "Career exploration guide" },
  { k: "experience", name: "Work experience", steps: ["Listed relevant experience", "Internship, job or project recorded", "Confirmed by a supervisor or faculty member"], res: "Internship listings on Handshake" }
];
/* Third next-step variant is unreachable in her code (T9); the strings are kept for the port. */
const NEXT_STEPS = {
  before: ["Finish your profile interview", "Adds about 8% and 20 points", "interview"],
  after: ["Sign up for a resume workshop", "The Career Hub can then review your resume", "recs"],
  unused: ["Book a practice interview", "Interview ready is your lowest marker", "readiness"]
};
const WEIGHTS = [["major", "Same major"], ["interest", "Said they're interested"], ["goal", "Career goal fits"], ["past", "Went to similar events"]];
const TALK = {
  invited: [["Accounting", 8], ["Computer Info Systems", 7], ["Finance, RE & Law", 6], ["IB & Marketing", 5], ["Management & HR", 4]],
  funnel: [["Invited personally", 30], ["Signed up", 19], ["Attended", 14]],
  quotes: ["“What should an accounting student learn first to move into data work?”", "“Does Northline hire interns from outside computer science?”"],
  acts: [["Offer another talk", "Offer sent to the Career Hub", "primary"], ["Meet interested students", "Students who asked to connect will be notified", "secondary"], ["Post an internship", "Internship post sent to the Career Hub for review", "secondary"]]
};
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

/* ---------- icons: Lucide (ISC), inlined ---------- */
const ICONS = {
  "arrow-right": [["path", "M5 12h14"], ["path", "m12 5 7 7-7 7"]],
  "check": [["path", "M20 6 9 17l-5-5"]],
  "circle-check": [["circle", 10], ["path", "m9 12 2 2 4-4"]],
  "circle-dot": [["circle", 10], ["circle", 1]],
  "circle-dashed": [["path", "M10.1 2.182a10 10 0 0 1 3.8 0"], ["path", "M13.9 21.818a10 10 0 0 1-3.8 0"], ["path", "M17.609 3.721a10 10 0 0 1 2.69 2.7"], ["path", "M2.182 13.9a10 10 0 0 1 0-3.8"], ["path", "M20.279 17.609a10 10 0 0 1-2.7 2.69"], ["path", "M21.818 10.1a10 10 0 0 1 0 3.8"], ["path", "M3.721 6.391a10 10 0 0 1 2.7-2.69"], ["path", "M6.391 20.279a10 10 0 0 1-2.69-2.7"]],
  "info": [["circle", 10], ["path", "M12 16v-4"], ["path", "M12 8h.01"]],
  "send": [["path", "M14.536 21.686a.5.5 0 0 0 .937-.024l6.5-19a.496.496 0 0 0-.635-.635l-19 6.5a.5.5 0 0 0-.024.937l7.93 3.18a2 2 0 0 1 1.112 1.11z"], ["path", "m21.854 2.147-10.94 10.939"]],
  "id-card": [["path", "M16 10h2"], ["path", "M16 14h2"], ["path", "M6.17 15a3 3 0 0 1 5.66 0"], ["path", "M9 13a2 2 0 1 0 0-4 2 2 0 0 0 0 4z"], ["path", "M4 5h16a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2z"]],
  "qr-code": [["path", "M4 3h3a1 1 0 0 1 1 1v3a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z"], ["path", "M17 3h3a1 1 0 0 1 1 1v3a1 1 0 0 1-1 1h-3a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z"], ["path", "M4 16h3a1 1 0 0 1 1 1v3a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-3a1 1 0 0 1 1-1z"], ["path", "M21 16h-3a2 2 0 0 0-2 2v3"], ["path", "M21 21v.01"], ["path", "M12 7v3a2 2 0 0 1-2 2H7"], ["path", "M3 12h.01"], ["path", "M12 3h.01"], ["path", "M12 16v.01"], ["path", "M16 12h1"], ["path", "M21 12v.01"], ["path", "M12 21v-1"]],
  "rotate-ccw": [["path", "M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"], ["path", "M3 3v5h5"]],
  "presentation": [["path", "M2 3h20"], ["path", "M21 3v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V3"], ["path", "m7 21 5-5 5 5"]],
  "chevron-left": [["path", "m15 18-6-6 6-6"]],
  "chevron-right": [["path", "m9 18 6-6-6-6"]],
  "search": [["path", "m21 21-4.34-4.34"], ["path", "M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16z"]]
};
const SVG = "http://www.w3.org/2000/svg";
function svg(tag, attrs) {
  const el = document.createElementNS(SVG, tag);
  for (const k in attrs) el.setAttribute(k, attrs[k]);
  return el;
}
function icon(name, size, label) {
  const el = svg("svg", { class: "sm-icon", viewBox: "0 0 24 24", width: size || 20, height: size || 20, fill: "none", stroke: "currentColor", "stroke-width": 2, "stroke-linecap": "round", "stroke-linejoin": "round" });
  if (label) { el.setAttribute("role", "img"); el.setAttribute("aria-label", label); } else el.setAttribute("aria-hidden", "true");
  ICONS[name].forEach(([tag, v]) => el.append(tag === "circle" ? svg("circle", { cx: 12, cy: 12, r: v }) : svg("path", { d: v })));
  return el;
}

/* ---------- DOM helper: createElement + textContent only, never innerHTML ---------- */
function add(el, kids) {
  for (const k of kids.flat(Infinity)) if (k != null && k !== false) el.append(k.nodeType ? k : document.createTextNode(String(k)));
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
const rich = parts => parts.map(p => Array.isArray(p) ? h("b", { text: p[0] }) : p);
const plain = parts => parts.map(p => Array.isArray(p) ? p[0] : p).join("");
const $ = (sel, root) => (root || document).querySelector(sel);
const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));

/* ---------- state (DESIGN.md 3.7) ---------- */
const KEY = "smc.c.v1";
const fresh = () => ({
  portal: null, page: { student: "interview", hub: "overview", partner: "talk" },
  ivStep: 0, ivLog: [{ ai: "t1" }], ivDone: false, picks: [], goal: "", cardPointsGiven: false,
  registered: [], lastRegistered: null, selfChecks: {}, helpPanel: null, bot: [],
  hubEvent: "E11", weights: { ...SMC.DEFAULT_WEIGHTS }, search: "", guideOpen: false, theme: "light"
});
let state = fresh();
let students = SMC.makeStudents();
/* Not saved: outcome messages, the armed reset, what was last shown (for count-ups). */
const ui = { msgs: {}, armed: null, shown: {}, doorsDone: false, advText: "Hi, could someone review my resume? I'm an accounting junior interested in data and consulting roles.", advShare: true };

function load() {
  try {
    const raw = window.localStorage.getItem(KEY);
    if (raw) { const s = JSON.parse(raw); if (s && typeof s === "object" && Array.isArray(s.ivLog)) state = { ...fresh(), ...s, page: { ...fresh().page, ...s.page }, weights: { ...SMC.DEFAULT_WEIGHTS, ...s.weights } }; }
  } catch (e) { /* storage blocked: run from memory */ }
}
function save() {
  syncGrace();
  try { window.localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) { /* ignore */ }
}
function clearSaved() { try { window.localStorage.removeItem(KEY); } catch (e) { /* ignore */ } }
const grace = () => students.find(s => s.id === SMC.GRACE_ID);
/* Her behaviour: the goal lands on the record at turn 3, interests and "via AI" only when the interview finishes. */
function syncGrace() {
  const g = grace();
  g.interests = state.ivDone ? state.picks.slice() : [];
  g.goal = state.goal;
  g.viaAI = state.ivDone;
}
const cur = () => state.portal ? state.page[state.portal] : "entry";
const stopNo = () => STOPS.indexOf(cur()) + 1;
/* Fix F3: one derived points total everywhere. */
const points = () => 20 + (state.cardPointsGiven ? 20 : 0) + 10 * state.registered.length + 5 * MARKERS.filter(m => state.selfChecks[m.k]).length;
function markerSteps() {
  const sc = state.selfChecks, out = {};
  MARKERS.forEach(m => { out[m.k] = [!!sc[m.k], false, false]; });
  out.network[1] = true;
  out.direction = [state.ivDone, state.ivDone && !!state.goal, false];
  return out;
}
function readinessPct() {
  let e = 0;
  Object.values(markerSteps()).forEach(st => st.forEach((on, i) => { if (on) e += [1, 1, 2][i]; }));
  return Math.round(e / 24 * 100);
}
const goalShown = g => g === EXPLORING ? "Undecided · exploring consulting or data roles" : g;
const turnKey = () => { for (let i = state.ivLog.length - 1; i >= 0; i--) if (state.ivLog[i].ai) return state.ivLog[i].ai; return "t1"; };
const addPick = t => { if (!state.picks.includes(t)) state.picks.push(t); };

/* The scripted interview, exactly as DESIGN.md 2.4 (with fix F2). Mutates state; returns true when it finishes. */
function ivApply(answer) {
  const key = turnKey();
  state.ivLog.push({ me: answer });
  if (key === "t1") {
    if (/tech|data|cloud|cyber|curious/i.test(answer)) addPick(TECH);
    addPick(TECH); addPick(ENT);
    state.ivLog.push({ ai: "t2" });
  } else if (key === "t2") {
    state.ivLog.push({ ai: "t3" });
  } else if (key === "t3") {
    const a = answer.toLowerCase();
    state.goal = Object.keys(SMC.GOALTOPIC).find(g => g.toLowerCase() === a)
      || (a === "graduate school" ? "Graduate school"
        : /data|analytic|it\b/i.test(answer) ? "Data, analytics or IT role"
          : /account|audit|cpa/i.test(answer) ? "Accounting or audit role (CPA path)" : "Undecided");
    state.ivLog.push({ ai: state.goal === "Undecided" ? "t4a" : "t4b" });
  } else if (key === "t4a" || key === "t4b") {
    if (key === "t4a" && /yes|compare/i.test(answer)) state.goal = EXPLORING;
    state.ivLog.push({ ai: "t5" });
  } else {
    state.ivDone = true; state.cardPointsGiven = true; state.ivStep = 5;
    return true;
  }
  state.ivStep += 1;
  return false;
}
function ivReset() {
  state.ivStep = 0; state.ivLog = [{ ai: "t1" }]; state.ivDone = false; state.picks = []; state.goal = "";
}
function botRule(q) {
  const s = q.toLowerCase();
  if (s.includes("template") || s.includes("resume guide")) return 0;
  if (s.includes("review")) return 1;
  if (s.includes("employer event") || s.includes("count")) return 2;
  if (/person|human|advisor|talk/.test(s)) return 3;
  return 4;
}

/* ---------- motion (DESIGN.md 8) ---------- */
const params = new URLSearchParams(window.location.search);
const M = {
  reduced: false, forced: params.get("rm") === "1" || document.documentElement.dataset.motion === "reduced",
  live: new Set(),
  track(t) { if (t) { M.live.add(t); t.then(() => M.live.delete(t)); } return t; },
  /* Any click or key completes what is still moving, then acts (8.1 rule 2). */
  finish() { const all = Array.from(M.live); M.live.clear(); all.forEach(t => t.progress(1)); },
  enter(targets, o) {
    o = o || {};
    if (!targets || targets.length === 0) return null;
    if (M.reduced) return M.track(gsap.fromTo(targets, { opacity: 0 }, { opacity: 1, duration: 0.15, ease: "none", clearProps: "opacity" }));
    return M.track(gsap.fromTo(targets, { opacity: 0, x: o.x || 0, y: o.y || 0, scale: o.scale || 1 },
      { opacity: 1, x: 0, y: 0, scale: 1, duration: o.dur || D.base, ease: o.ease || E.out, delay: o.delay || 0, stagger: o.stagger || 0, clearProps: "opacity,transform" }));
  },
  count(el, from, to, fmt) {
    if (el._tw) el._tw.kill();
    if (M.reduced || from === to) { el.textContent = fmt(to); return; }
    const o = { v: from };
    el._tw = gsap.to(o, { v: to, duration: D.max, ease: E.out, onUpdate() { el.textContent = fmt(Math.round(o.v)); }, onComplete() { el.textContent = fmt(to); } });
  }
};
if (M.forced) document.documentElement.dataset.motion = "reduced";
gsap.matchMedia().add({ reduce: "(prefers-reduced-motion: reduce)", full: "(prefers-reduced-motion: no-preference)" }, ctx => { M.reduced = M.forced || ctx.conditions.reduce; });
M.reduced = M.forced || window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/* Figures that change because of the presenter's action count once; on arrival they show the final value. */
function applyCounts(root, arriving) {
  $$("[data-count]", root).forEach(el => {
    const key = el.dataset.count, to = Number(el.dataset.to), sfx = el.dataset.sfx || "", prev = ui.shown[key];
    ui.shown[key] = to;
    if (!arriving && prev != null && prev !== to) M.count(el, prev, to, v => v + sfx);
  });
  const arc = $(".sm-ring__arc", root);
  if (arc) {
    const C = 414.69, to = Number(arc.dataset.pct), prev = arriving ? 0 : ui.shownRing;
    ui.shownRing = to;
    if (!M.reduced && prev != null && prev !== to) gsap.fromTo(arc, { strokeDashoffset: C * (1 - prev / 100) }, { strokeDashoffset: C * (1 - to / 100), duration: D.max, ease: E.out, overwrite: true });
  }
}
/* A chosen chip travels to its place on the profile card (14.5 moment 3): first, last, invert, play. */
function travel(fromRect, toEl) {
  if (!toEl) return;
  if (M.reduced || !fromRect) { M.enter(toEl, { scale: 0.9 }); return; }
  const to = toEl.getBoundingClientRect();
  const ghost = toEl.cloneNode(true);
  ghost.classList.add("c-ghost"); ghost.setAttribute("aria-hidden", "true");
  ghost.style.left = to.left + "px"; ghost.style.top = to.top + "px"; ghost.style.width = to.width + "px";
  document.body.append(ghost);
  gsap.set(toEl, { opacity: 0 });
  M.track(gsap.fromTo(ghost, { x: fromRect.left - to.left, y: fromRect.top - to.top },
    { x: 0, y: 0, duration: D.move, ease: E.inOut, onComplete() { ghost.remove(); gsap.set(toEl, { clearProps: "opacity" }); } }));
}
function scrollToView(el, clear) {
  const r = el.getBoundingClientRect(), top = 80, bottom = window.innerHeight - (clear || 88);
  if (r.top >= top && r.bottom <= bottom) return;
  const y = window.scrollY + (r.bottom > bottom ? Math.min(r.top - top, r.bottom - bottom) : r.top - top);
  if (M.reduced) { window.scrollTo(0, y); return; }
  const o = { y: window.scrollY };
  M.track(gsap.to(o, { y, duration: D.max, ease: E.out, onUpdate() { window.scrollTo(0, o.y); } }));
}

/* ---------- toast and live regions ---------- */
const els = {};
let toastTimer = 0, saveTimer = 0;
function toast(text) {
  const el = els.toast;
  window.clearTimeout(toastTimer); gsap.killTweensOf(el);
  el.textContent = text; el.hidden = false;
  if (M.reduced) gsap.fromTo(el, { opacity: 0 }, { opacity: 1, duration: 0.15 }); else gsap.fromTo(el, { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: D.base, ease: E.out });
  toastTimer = window.setTimeout(hideToast, 4000);
}
function hideToast() {
  const el = els.toast;
  gsap.to(el, { opacity: 0, y: M.reduced ? 0 : 8, duration: D.fast, ease: E.in, onComplete() { el.hidden = true; el.textContent = ""; } });
}
let sayTimer = 0;
function announce(text, wait) {
  window.clearTimeout(sayTimer);
  sayTimer = window.setTimeout(() => { els.status.textContent = text; }, wait || 0);
}

/* ---------- components: props in, DOM node out ---------- */
function renderButton(p) {
  const { label, variant = "primary", icon: ic, iconAfter, onclick, ...attrs } = p;
  const el = h("button", { class: "sm-button", type: "button", "data-variant": variant, ...attrs }, ic && icon(ic), label != null && h("span", { text: label }), iconAfter && icon(iconAfter));
  /* aria-disabled, never the disabled attribute: the control stays focusable and ignores activation. */
  if (onclick) el.addEventListener("click", e => { if (el.getAttribute("aria-disabled") !== "true") onclick(e); });
  return el;
}
const STATUS_ICON = { working: "circle-check", partly: "circle-dot", planned: "circle-dashed" };
const renderStatus = (kind, text) => h("span", { class: "sm-status", "data-kind": kind }, icon(STATUS_ICON[kind], 20), text);
const renderMarker = () => h("p", { class: "sm-marker" }, icon("info", 20), N1);
const renderScripted = () => h("p", { class: "sm-scripted" }, icon("info", 20), N2);
function renderChip(p) {
  const { label, kind = "option", pressed, ...attrs } = p;
  const on = kind === "toggle" && pressed;
  return h("button", { class: "sm-chip", type: "button", "data-kind": kind, "aria-pressed": kind === "toggle" ? String(!!pressed) : null, ...attrs }, on && icon("check", 20), label);
}
const renderPill = (text, tone, attrs) => h("span", { class: "sm-pill", "data-tone": tone, ...attrs }, text);
/* Persistent outcome line, directly under the control that caused it (7.11). */
const renderMessage = key => ui.msgs[key] ? h("div", { class: "sm-message", role: "status" }, icon("circle-check", 20), h("span", { text: ui.msgs[key] })) : null;
function setMsg(key, text) { ui.msgs[key] = text; update(); }
function renderStat(p) {
  return h("p", { class: "sm-stat", "data-wide": p.wide },
    h("span", { class: "sm-stat__figure", "data-count": p.count, "data-to": p.count ? p.value : null, "data-sfx": p.sfx, text: p.value + (p.sfx || "") }), " ",
    h("span", { class: "sm-stat__label", text: p.label }));
}
function renderHead(id, desc) {
  const s = SCREEN[id];
  return h("div", { class: "c-head" }, h("h1", { tabindex: "-1", text: s.title }), renderStatus(s.status[0], s.status[1]), h("p", { class: "c-head__desc", text: desc || s.desc }));
}
function renderBars(p) {
  return h("ul", { class: "sm-bars", "data-tone": p.tone, style: p.labelW ? "--c-bars-label:" + p.labelW + "px" : null }, p.rows.map(([k, v]) =>
    h("li", { class: "sm-bars__row" }, h("span", { text: k }),
      h("div", { class: "sm-bars__track" }, h("div", { class: "sm-bars__fill", style: "width:" + Math.round(v / p.max * 100) + "%" })),
      h("span", { class: "sm-bars__value", text: v + (p.sfx || "") }))));
}
function renderFunnel(rows) {
  return h("ul", { class: "sm-funnel" }, rows.map(([k, v]) =>
    h("li", { class: "sm-funnel__row" }, h("span", { class: "sm-funnel__bar", style: "width:" + Math.max(16, Math.round(70 * v / 30)) + "%", text: v }), h("span", { text: k }))));
}
function renderRing(pct, target) {
  const C = 414.69, a = (target / 100 * 360 - 90) * Math.PI / 180;
  const pt = r => [80 + r * Math.cos(a), 80 + r * Math.sin(a)];
  const line = (cls, w, r1, r2) => { const p1 = pt(r1), p2 = pt(r2); return svg("line", { class: cls, x1: p1[0], y1: p1[1], x2: p2[0], y2: p2[1], "stroke-width": w }); };
  const el = svg("svg", { viewBox: "0 0 160 160", role: "img", "aria-label": pct + "% career ready. Target for a junior: " + target + "%.", fill: "none" });
  el.append(svg("circle", { class: "sm-ring__track", cx: 80, cy: 80, r: 66, "stroke-width": 14 }),
    svg("circle", { class: "sm-ring__arc", cx: 80, cy: 80, r: 66, "stroke-width": 14, "stroke-linecap": "round", "stroke-dasharray": C, "stroke-dashoffset": C * (1 - pct / 100), transform: "rotate(-90 80 80)", "data-pct": pct }),
    line("sm-ring__key", 6, 56, 76), line("sm-ring__tick", 4, 57, 75));
  return h("div", { class: "sm-ring" }, el,
    h("div", { class: "sm-ring__mid", "aria-hidden": "true" }, h("span", { class: "sm-ring__pct", "data-count": "pct", "data-to": pct, "data-sfx": "%", text: pct + "%" }), h("span", { class: "sm-ring__cap", text: "career ready" })));
}
/* A real table at md and up; stacked rows (ol for a ranked list, ul otherwise) at 390. */
function renderTable(o) {
  const stacked = mq.sm.matches;
  let body, table;
  if (stacked) body = table = h(o.ordered ? "ol" : "ul", { class: "sm-table", "aria-label": o.caption });
  else {
    body = h("tbody");
    table = h("table", { class: "sm-table", "data-fixed": o.fixed }, h("caption", { text: o.caption }), h("thead", null, h("tr", null, o.cols.map(c => h("th", { scope: "col", text: c })))), body);
  }
  const row = (cells, ro) => {
    const el = stacked
      ? h("li", null, cells.map((c, i) => h("div", { class: "sm-table__pair" }, h("span", { class: "sm-table__k", text: o.cols[i] }), h("span", { "data-col": i }, c))))
      : h("tr", null, cells.map((c, i) => h("td", { "data-col": i }, c)));
    if (ro && ro.id) el.dataset.flipId = ro.id;
    if (ro && ro.grace) el.dataset.grace = "";
    return el;
  };
  const empty = text => stacked ? h("li", { class: "sm-table__empty", text }) : h("tr", null, h("td", { colspan: o.cols.length, class: "sm-table__empty", text }));
  return { box: h("div", { class: "sm-table-box" }, table), body, row, empty };
}
const nameCell = s => s.id === SMC.GRACE_ID
  ? h("span", { class: "sm-table__name" }, icon("id-card", 20), h("span", { class: "sm-vh", text: "Grace Delgado, the student from the demo" }), s.name)
  : h("span", { class: "sm-table__name", text: s.name });
function renderTurn(p) {
  return h("div", { class: "sm-turn", "data-who": p.who },
    p.who === "ai" ? h("span", { class: "sm-turn__who", text: p.speaker }) : h("span", { class: "sm-vh", text: "Grace:" }),
    h("span", null, p.who === "ai" ? rich(p.parts) : p.text), p.extra);
}
/* Free-text row: a labelled field and Send. Send is aria-disabled while the field is empty; N8 says why. */
function renderSend(p) {
  const id = "f-" + p.fid, rid = "why-" + p.fid;
  const input = h("input", { class: "sm-field__input", id, type: "text", placeholder: p.placeholder, autocomplete: "off", "data-fid": p.fid });
  const why = h("p", { class: "c-reason", id: rid, "data-state": "closed", text: p.reason });
  const btn = renderButton({ label: "Send", icon: "send", "aria-disabled": "true", "aria-describedby": rid, "data-fid": p.fid + "-send" });
  const send = () => { const v = input.value.trim(); if (v) p.onSend(v, input); else why.dataset.state = "open"; };
  input.addEventListener("input", () => {
    const empty = !input.value.trim();
    btn.setAttribute("aria-disabled", String(empty));
    if (empty) btn.setAttribute("aria-describedby", rid); else { btn.removeAttribute("aria-describedby"); why.dataset.state = "closed"; }
  });
  input.addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); send(); } });
  btn.addEventListener("click", send);
  return h("div", { class: "c-stack" }, h("div", { class: "c-sendrow" }, h("label", { class: "sm-vh", for: id, text: p.label }), input, btn), why);
}
/* Scroll the log so the newest turn is whole and the view starts at the top of a turn, never mid-line. */
function fitLog(log) {
  const turns = $$(".sm-turn", log), pad = $(".c-logpad", log), last = turns[turns.length - 1];
  if (!last) return;
  pad.style.height = "0px";
  const view = log.clientHeight, edge = 8, bottom = last.offsetTop + last.offsetHeight;
  let k = turns.length - 1;
  while (k > 0 && bottom - turns[k - 1].offsetTop <= view - edge) k--;
  const top = Math.max(0, turns[k].offsetTop - edge);
  pad.style.height = Math.max(0, top + view - log.scrollHeight) + "px";
  log.scrollTop = top;
}
function renderProfileCard() {
  const g = grace(), goal = goalShown(state.goal);
  const kv = (k, dd) => [h("dt", { text: k }), dd];
  return h("div", { class: "sm-card c-profile" },
    h("div", { class: "c-profile__head" }, h("span", { class: "sm-avatar", "aria-hidden": "true", text: "GD" }),
      h("h2", { class: "c-profile__name" }, g.name, " ", h("span", { class: "c-label", text: "Profile card" }))),
    h("div", { class: "c-profile__group" }, h("p", { class: "c-label", text: "From college records (already on file)" }),
      h("dl", { class: "c-kv" }, kv("Major", h("dd", { text: g.major })), kv("Year", h("dd", { text: g.year })),
        kv("Events", h("dd", null, g.events.map(e => h("span", { text: SMC.PAST[e][0] })))))),
    h("div", { class: "c-profile__group" }, h("p", { class: "c-label", text: "From the interview" }),
      h("dl", { class: "c-kv" },
        kv("Interests", state.picks.length ? h("dd", null, state.picks.map(t => renderPill(SMC.short(t), "new", { "data-topic": t }))) : h("dd", { "data-empty": true, text: "Not yet" })),
        kv("Next step", goal ? h("dd", null, h("span", { "data-goal": true, text: goal })) : h("dd", { "data-empty": true, text: "Not yet" })))),
    h("p", { class: "c-note", text: "Later: students can answer by voice or by typing." }));
}
function renderEventRow(p) {
  const e = p.ev;
  return h("article", { class: "sm-card sm-event", "data-feature": p.feature },
    h("div", { class: "sm-event__date" }, h("b", { text: e.d }), h("span", { text: e.m })),
    h("div", null, h("h3", { text: e.title }), h("p", { class: "sm-event__meta", text: e.host + " · " + e.when + " · 60 seats" })),
    h("p", { class: "sm-event__why" }, h("b", { text: "Why you:" }), " ", SMC.whyYou(e)),
    h("div", { class: "sm-event__foot" },
      p.registered
        ? renderButton({ label: "Registered", variant: "confirmed", iconAfter: "check", "aria-disabled": "true", "aria-describedby": "checkin-what", "data-fid": "reg-" + e.id })
        : renderButton({ label: "Register", "data-fid": "reg-" + e.id, onclick: p.onRegister }),
      h("span", { class: "sm-event__match", text: "match " + e.total + " of 10" })));
}
function renderCheckin(e) {
  const q = SMC.qrCells(e.id);
  const code = svg("svg", { class: "sm-checkin__code", viewBox: "0 0 " + q.size + " " + q.size, role: "img", "aria-label": "Sample check-in code", "shape-rendering": "crispEdges" });
  const rect = (x, y, s, fill) => code.append(svg("rect", { x, y, width: s, height: s, style: "fill:var(" + fill + ")" }));
  rect(0, 0, q.size, "--sm-plate");
  q.cells.forEach(([x, y]) => rect(x, y, 1, "--sm-code-dark"));
  q.finders.forEach(([x, y]) => { rect(x, y, 7, "--sm-code-dark"); rect(x + 1, y + 1, 5, "--sm-plate"); rect(x + 2, y + 2, 3, "--sm-code-dark"); });
  return h("div", { class: "sm-card sm-checkin" }, code,
    h("div", { class: "c-stack" }, h("h2", null, icon("qr-code", 20), "Check-in code"),
      h("p", { class: "sm-checkin__what", id: "checkin-what", text: e.title + " · " + e.when }),
      h("p", { text: "Scanned at the door. Attendance goes on her record and points are added. Sample code only." }),
      renderStatus("planned", "Planned")),
    h("div", { class: "sm-checkin__points" }, h("p", { class: "c-label", text: "Career points" }),
      h("p", { class: "sm-stat__figure", "data-count": "points", "data-to": points(), text: points() }),
      h("p", { class: "c-note", text: "Points exist in the early version" })));
}
function renderMarkerCard(m, st) {
  const mark = (on) => [h("span", { class: "sm-step__mark", "data-state": on ? "on" : "off" }, on && icon("check", 16)), h("span", { class: "sm-vh", text: on ? "done" : "not yet" })];
  const words = i => h("span", null, m.steps[i], h("span", { class: "sm-step__level", text: LEVELS[i] }));
  const self = m.k !== "direction";
  return h("div", { class: "sm-card sm-marker-card" },
    h("div", { class: "sm-marker-card__head" }, h("h3", { text: m.name }),
      h("span", { class: "sm-dots", "aria-hidden": "true" }, st.map(on => h("i", { "data-state": on ? "on" : "off" })))),
    h("div", { class: "sm-marker-card__steps" },
      self ? h("label", { class: "sm-step" }, (() => { const c = h("input", { type: "checkbox", "data-fid": "sc-" + m.k, onchange: e => selfCheck(m.k, e.currentTarget.checked) }); c.checked = st[0]; return c; })(), words(0))
        : h("div", { class: "sm-step" }, h("span", null, mark(st[0])), words(0)),
      [1, 2].map(i => h("div", { class: "sm-step" }, h("span", null, mark(st[i])), words(i)))),
    h("div", { class: "sm-marker-card__links" },
      renderButton({ label: m.res, variant: "link", "data-fid": "res-" + m.k, onclick: () => setMsg("mk-" + m.k, "Opens the Career Hub page: " + m.res) }),
      renderButton({ label: "Ask the assistant bot", variant: "link", "data-fid": "ask-" + m.k, onclick: () => { state.bot.push({ marker: m.name }); openHelp("chat", "#f-bot", true); } })),
    renderMessage("mk-" + m.k));
}
function renderHelpPanel(kind) {
  const foot = text => h("p", { class: "c-note", text });
  let body;
  if (kind === "chat") {
    const turns = [{ parts: BOT_FIRST }].concat(state.bot.map(t => t.me ? { me: t.me } : t.marker
      ? { parts: ["You're looking at ", [t.marker], ". I can point you to resources, or help you book a CBACH advisor."] }
      : { parts: [BOT_A[t.rule][0]], book: BOT_A[t.rule][1] }));
    body = [h("div", { class: "sm-transcript sm-bot" }, renderScripted(),
      h("div", { class: "sm-transcript__log" }, turns.map((t, i) => t.me ? renderTurn({ who: "me", text: t.me }) : renderTurn({ who: "ai", speaker: "CBACH assistant bot · AI", parts: t.parts,
        extra: t.book && h("div", null, renderButton({ label: BOOK, variant: "inline", "data-fid": "bot-book-" + i, onclick: () => openHelp("book", null, true) })) })), h("div", { class: "c-logpad" })),
      h("div", { class: "sm-transcript__reply" }, h("div", { class: "sm-chips" }, BOT_Q.map((q, i) => renderChip({ label: q, "data-fid": "bq" + i, onclick: () => askBot(q) }))),
        renderSend({ fid: "bot", label: "Ask the assistant bot", placeholder: "Ask a quick question…", reason: "Type a question first.", onSend: askBot }))),
    foot("The bot answers quick questions. For advice, it sends you to a CBACH advisor. " + FULL)];
  } else if (kind === "msg") {
    const ta = h("textarea", { class: "sm-field__input", id: "f-adv", rows: 3, "data-fid": "adv", oninput: e => { ui.advText = e.currentTarget.value; const empty = !ui.advText.trim(); btn.setAttribute("aria-disabled", String(empty)); if (!empty) why.dataset.state = "closed"; } });
    ta.value = ui.advText;
    const share = h("input", { type: "checkbox", "data-fid": "adv-share", onchange: e => { ui.advShare = e.currentTarget.checked; } });
    share.checked = ui.advShare;
    const why = h("p", { class: "c-reason", id: "why-adv", "data-state": "closed", text: "Type a message first." });
    const btn = renderButton({ label: "Send message", "aria-disabled": String(!ui.advText.trim()), "aria-describedby": "why-adv", "data-fid": "adv-send" });
    btn.addEventListener("click", () => {
      if (!ui.advText.trim()) { why.dataset.state = "open"; return; }
      ui.msgs.help = "Sent. A CBACH advisor usually replies within one business day."; state.helpPanel = null;
      update({ focus: "[data-fid='help-msg']" });
    });
    body = [h("div", { class: "sm-field" }, h("label", { class: "sm-field__label", for: "f-adv", text: "Your message" }), ta),
      h("label", { class: "sm-check" }, share, h("span", { text: "Share my readiness card with the advisor so they can see where I am" })),
      h("div", { class: "c-stack" }, h("div", null, btn), why),
      foot("Messages go to Career Hub staff, not to the bot. " + FULL)];
  } else if (kind === "book") {
    body = [h("div", { class: "sm-chips" }, SLOTS.map((s, i) => renderChip({ label: s, "data-fid": "slot" + i, onclick: () => setMsg("book", "Booked: " + s + " with a CBACH advisor. A reminder will be sent.") }))), renderMessage("book"), foot(FULL)];
  } else {
    body = [h("div", { class: "sm-chips" }, MARKERS.map((m, i) => renderChip({ label: m.res, "data-fid": "resc" + i, onclick: () => setMsg("res", "Opens: " + m.res) }))), renderMessage("res"), foot(FULL)];
  }
  return h("div", { class: "sm-card c-panel", id: "help-panel" }, h("h2", { tabindex: "-1", text: HELP[kind].title }), body);
}

/* ---------- actions inside the student screens ---------- */
function answer(text, fromEl) {
  const key = turnKey();
  const from = key === "t2" ? state.picks.map(t => { const c = $$(".sm-chip[data-topic]").find(x => x.dataset.topic === t); return [t, c && c.getBoundingClientRect()]; })
    : key === "t3" && fromEl ? [["goal", fromEl.getBoundingClientRect()]] : [];
  if (ivApply(text)) {
    save();
    go("recs");
    toast("Profile card saved. 20 points added.");
    return;
  }
  const node = update({ focus: ".sm-transcript__reply button, .sm-transcript__reply input" });
  const turns = $$(".sm-turn", node), ai = turns[turns.length - 1];
  /* The student turn, then the assistant's whole reply with its options 80ms later. Nothing streams. */
  M.enter([turns[turns.length - 2]], { y: 6, dur: D.fast });
  M.enter([ai, $(".sm-transcript__reply", node)], { y: 6, delay: 0.08 });
  from.forEach(([t, rect]) => travel(rect, t === "goal" ? $("[data-goal]", node) : $$(".sm-pill[data-topic]", node).find(x => x.dataset.topic === t)));
  els.ivLive.textContent = plain(IV[turnKey()].say);
}
function togglePick(t) {
  const i = state.picks.indexOf(t);
  if (i >= 0) state.picks.splice(i, 1); else state.picks.push(t);
  const node = update();
  if (i < 0) M.enter([$$(".sm-pill[data-topic]", node).find(x => x.dataset.topic === t)], { scale: 0.9 });
}
function register(id) {
  if (state.registered.includes(id)) return;
  state.registered.push(id); state.lastRegistered = id;
  toast("Registered. 10 points added.");
  const node = update(), card = $(".sm-checkin", node);
  M.enter([$("[data-fid='reg-" + id + "'] .sm-icon", node)], { scale: 0.9, dur: D.fast });
  M.enter([card], { y: 8 });
  scrollToView(card, 176); /* stays clear of the toast */
}
function selfCheck(k, on) {
  state.selfChecks[k] = on;
  if (on) toast("Self-check saved. 5 points added.");
  update();
}
function openHelp(kind, focusSel, force) {
  const closing = !force && state.helpPanel === kind;
  state.helpPanel = closing ? null : kind;
  delete ui.msgs.book; delete ui.msgs.res; delete ui.msgs.help;
  const below = $(".c-markers"), before = below && below.getBoundingClientRect().top;
  const node = update(), panel = $("#help-panel", node);
  if (!panel) return;
  const target = (focusSel && $(focusSel, panel)) || $("h2", panel);
  target.focus({ preventScroll: true });
  M.enter([panel], { y: 8 });
  /* What sits below jumps to its new place and is brought there with a transform, not by animating height. */
  const now = $(".c-markers", node);
  if (now && before != null && !M.reduced) M.track(gsap.from(now, { y: before - now.getBoundingClientRect().top, duration: D.base, ease: E.out, clearProps: "transform" }));
  const log = $(".sm-transcript__log", panel);
  if (log) fitLog(log);
  scrollToView(panel);
}
function askBot(q) {
  state.bot.push({ me: q }, { rule: botRule(q) });
  const node = update({ focus: "#f-bot" });
  const turns = $$("#help-panel .sm-turn", node);
  M.enter([turns[turns.length - 2]], { y: 6, dur: D.fast });
  M.enter([turns[turns.length - 1]], { y: 6, delay: 0.08 });
  els.botLive.textContent = BOT_A[botRule(q)][0];
  scrollToView($("#help-panel", node));
}

/* ---------- screens: student ---------- */
function screenEntry() {
  return h("section", { class: "c-entry", "data-surface": "stage" },
    h("span", { class: "c-plate" }, h("img", { src: SMC.LOGO, alt: "Cal Poly Pomona" })),
    h("h1", { tabindex: "-1", text: "Smart Match CPP" }),
    h("p", { class: "c-entry__lede", text: "A student-built app for the CBA Career Hub. Events find the right students, students build a record of their career growth, and industry partners see who they reached." }),
    h("div", { class: "c-entry__doors" }, DOORS.map(([portal, eyebrow, title, body, action]) =>
      h("button", { class: "sm-door", type: "button", "data-fid": "door-" + portal, onclick: () => go(state.page[portal]) },
        h("span", { class: "sm-door__eyebrow", text: eyebrow }), h("span", { class: "sm-door__title", text: title }),
        h("span", { class: "sm-door__body", text: body }), h("span", { class: "sm-door__action" }, action, icon("arrow-right", 24))))),
    h("p", { class: "c-entry__demo", text: "Concept prototype. All students, partners, events and numbers are made up; the 300 student records come from the class exercise file." }));
}
function screenInterview() {
  const turn = IV[turnKey()];
  const log = h("div", { class: "sm-transcript__log" },
    state.ivLog.map(t => t.ai ? renderTurn({ who: "ai", speaker: "Smart Match assistant", parts: IV[t.ai].say }) : renderTurn({ who: "me", text: t.me })),
    h("div", { class: "c-logpad" }));
  let reply;
  if (state.ivDone) {
    reply = h("div", { class: "c-row" }, h("p", { text: "Interview finished." }),
      renderButton({ label: "Start over", variant: "secondary", icon: "rotate-ccw", "data-fid": "iv-over", onclick: () => { ivReset(); update({ focus: ".sm-transcript__reply button" }); } }));
  } else if (turn.toggles) {
    reply = [h("div", { class: "sm-chips" }, SMC.TOPICS.map((t, i) => renderChip({ label: SMC.short(t), kind: "toggle", pressed: state.picks.includes(t), "data-topic": t, "data-fid": "tg" + i, onclick: () => togglePick(t) }))),
      h("div", null, renderButton({ label: "Done", "data-fid": "iv-done", onclick: () => answer(state.picks.length ? state.picks.map(SMC.short).join(", ") : "None of these") }))];
  } else {
    reply = [h("div", { class: "sm-chips" }, turn.opts.map((o, i) => renderChip({ label: o, "data-fid": "op" + i, onclick: e => answer(o, e.currentTarget) }))),
      renderSend({ fid: "iv", label: "Type an answer", placeholder: "Or type your own answer…", reason: "Type an answer first.", onSend: answer })];
  }
  const node = h("section", null, renderHead("interview"),
    h("div", { class: "c-interview" },
      h("div", { class: "sm-transcript" }, renderScripted(), log, h("div", { class: "sm-transcript__reply" }, reply)),
      renderProfileCard()));
  node._mounted = () => fitLog(log);
  return node;
}
function screenRecs() {
  const ranked = SMC.rankEvents(grace()), done = state.ivDone;
  const last = state.lastRegistered && SMC.UPCOMING.find(e => e.id === state.lastRegistered);
  return h("section", { "data-after": done },
    renderHead("recs", SCREEN.recs.desc + " " + (done ? "These use her profile card." : "Right now the app only knows her major and past events.")),
    !done && h("div", { class: "sm-card c-callout", "data-tone": "gold" }, h("p", { text: "Finish the short interview to get better suggestions." }),
      renderButton({ label: "Activate my profile", "data-fid": "recs-go", onclick: () => go("interview") })),
    h("h2", { class: "sm-vh", text: "Events for me" }),
    h("div", { class: "c-events" }, ranked.map((e, i) => renderEventRow({ ev: e, feature: i === 0, registered: state.registered.includes(e.id), onRegister: () => register(e.id) }))),
    last && renderCheckin(last));
}
function screenReadiness() {
  const pct = readinessPct(), target = SMC.TARGET.Junior, gap = target - pct;
  const lead = gap <= 0 ? "On track for your year." : gap <= 20 ? "A little behind for a junior." : "Behind for a junior, and that's fixable.";
  const [step, note, dest] = state.ivDone ? NEXT_STEPS.after : NEXT_STEPS.before;
  const steps = markerSteps(), open = state.helpPanel;
  const helpButton = k => renderButton({ label: HELP[k].label, variant: HELP[k].variant, "aria-expanded": String(open === k), "aria-controls": "help-panel", "data-fid": "help-" + k, onclick: () => openHelp(k) });
  const node = h("section", null, renderHead("readiness"),
    h("div", { class: "c-ready" }, renderRing(pct, target),
      h("div", { class: "c-ready__side" },
        h("div", { class: "c-tiles" }, renderStat({ value: pct, sfx: "%", count: "pct2", label: "readiness now" }), renderStat({ value: target, sfx: "%", label: "target for a junior (gold mark)" }), renderStat({ value: points(), count: "points", label: "career points" })),
        h("div", { class: "sm-card c-callout", "data-tone": "gold" }, h("p", null, h("b", { text: lead }), " Next step: " + step + ". " + note),
          renderButton({ label: "Go", variant: "inline", "data-fid": "ready-go", onclick: () => go(dest) })))),
    h("div", { class: "sm-card sm-help" },
      h("div", { class: "sm-help__head" }, h("span", { class: "sm-avatar", "data-tone": "green", "aria-hidden": "true", text: "CB" }), h("h2", { text: "Need help with any marker? The CBA Career Hub (CBACH) is here." })),
      h("p", { text: "The assistant bot (AI) answers quick questions any time. CBACH advisors, real people on the Career Hub staff, answer messages and meet with you to review resumes, run practice interviews and help you choose a direction." }),
      h("div", { class: "sm-help__groups" },
        h("div", { class: "sm-help__group" }, h("p", { class: "c-label", text: "Help yourself, any time" }), helpButton("chat"), helpButton("res")),
        h("div", { class: "sm-help__group" }, h("p", { class: "c-label", text: "Talk to a person" }), helpButton("msg"), helpButton("book")))),
    open ? renderHelpPanel(open) : renderMessage("help"),
    h("div", { class: "c-markers" }, MARKERS.map(m => renderMarkerCard(m, steps[m.k]))),
    h("p", { class: "c-closing", text: "Draft markers for discussion. If the college has official Career Success Markers, the names here should match them. Readiness is private to the student and her advisor unless she chooses to share it." }));
  node._mounted = () => { const log = $(".sm-bot .sm-transcript__log", node); if (log) fitLog(log); };
  return node;
}
function screenGrowth() {
  const reg = SMC.UPCOMING.filter(e => state.registered.includes(e.id)), t = {};
  const bump = x => { const k = SMC.short(x); t[k] = (t[k] || 0) + 1; };
  grace().events.forEach(e => SMC.PAST[e][2].forEach(bump));
  reg.forEach(e => e.topics.forEach(bump));
  const rows = Object.entries(t).sort((a, b) => b[1] - a[1]);
  const terms = [
    ["Fall 2025 · Sophomore", [["Brand Building at a Streaming Studio", "attended"]]],
    ["Spring 2026", [["Cybersecurity and Cloud Jobs Q&A", "attended"]]],
    ["Fall 2026 · Junior", [state.ivDone ? ["Profile card completed through AI interview", "+20 points", "new"] : ["Profile card not yet completed"]].concat(reg.map(e => [e.title, "registered", "new"]))],
    ["Summer 2027", [["Internship", "recorded later", "quiet"]], true],
    ["After graduation", [["First job and employer", "recorded later", "quiet"]], true]
  ];
  return h("section", null, renderHead("growth"),
    h("div", { class: "c-grid2" },
      h("div", { class: "sm-card c-block" }, h("h2", { text: "Timeline" }),
        h("ol", { class: "sm-timeline" }, terms.map(([when, lines, future]) =>
          h("li", { class: "sm-timeline__term", "data-state": future ? "future" : "past" }, h("span", { class: "sm-timeline__dot", "aria-hidden": "true" }),
            h("div", null, h("p", { class: "sm-timeline__when", text: when }),
              lines.map(([text, tag, tone]) => h("p", { class: "sm-timeline__line", "data-empty": !tag }, h("span", { text }), tag && renderPill(tag, tone))))))) ),
      h("div", { class: "c-stack" },
        h("div", { class: "sm-card c-block", "data-anim": "bars" }, h("h2", { text: "Topics she has explored" }),
          renderBars({ rows, max: Math.max(3, ...rows.map(r => r[1])), labelW: 160 })),
        h("div", { class: "sm-card c-tiles", "data-cols": "2" },
          renderStat({ value: 2 + state.registered.length, label: "events attended or registered" }), renderStat({ value: points(), count: "points", label: "career points" })))),
    h("p", { class: "c-closing", text: "An Accounting major whose events lean toward media and technology. Her record shows a path her major alone would never reveal." }));
}

/* ---------- screens: Career Hub and partner ---------- */
function screenOverview() {
  const o = SMC.overviewStats(students), r = SMC.hubReadiness(students);
  const chart = (label, note, bars) => h("div", { class: "sm-card c-chart", "data-anim": "bars" }, h("h2", { text: label }), note && h("p", { class: "c-note", text: note }), bars);
  return h("section", null, renderHead("overview"),
    h("div", { class: "c-tiles", "data-cols": "4" },
      renderStat({ value: o.n, label: "student records loaded" }),
      renderStat({ value: o.attended, label: "students who attended at least one event" }),
      renderStat({ value: o.cards, count: "cards", label: "students with a profile card" }),
      h("div", { class: "sm-card" }, renderStat({ value: o.neverReached, label: "students never reached by an event", wide: true }))),
    h("div", { class: "c-grid2" },
      chart("Event attendance by major", null, renderBars({ rows: o.attendanceByMajor, max: Math.max(...o.attendanceByMajor.map(x => x[1])), labelW: 180 })),
      chart("Events that brought in first-time students", "Share of each event's attendees for whom it was their first career event.", renderBars({ rows: o.firstTimers, max: 100, sfx: "%", tone: "gold", labelW: 300 }))),
    h("div", { class: "c-grid2" },
      chart("Average readiness by year (illustrative)", null, renderBars({ rows: r.map(([y, avg, , n]) => [y + " (" + n + ")", avg]), max: 100, sfx: "%", labelW: 180 })),
      chart("Share on track for their year (illustrative)", "Targets: freshman 20%, sophomore 40%, junior 60%, senior 85%. Shows where the Career Hub should focus, for example seniors who are behind.", renderBars({ rows: r.map(([y, , on]) => [y, on]), max: 100, sfx: "%", tone: "gold", labelW: 180 }))),
    h("div", { class: "sm-card c-block", "data-tone": "sunk" }, h("h2", { text: "How student data is handled (proposed)" }),
      h("ul", { class: "c-list" },
        h("li", { text: "Students activate their own profile; the interview is optional." }),
        h("li", { text: "The college owns the records, and they stay after students graduate." }),
        h("li", { text: "Reports show group totals. Partners never see individual student records." }))));
}
function screenRecords() {
  const T = renderTable({ caption: "Student records", cols: ["ID", "Name", "Major", "Year", "Events", "Profile card"] });
  const count = h("p", { class: "c-count" }), more = h("p", { class: "c-note", text: "Showing the first 25. Search to narrow the list." });
  const input = h("input", { class: "sm-field__input", id: "f-search", type: "text", placeholder: "Try Delgado", autocomplete: "off", "data-fid": "search" });
  input.value = state.search;
  const cardCell = s => s.viaAI ? renderPill("AI interview · today", "new") : (s.interests.length || s.goal) ? renderPill("Completed") : h("span", { class: "c-muted", text: "Not yet" });
  const fill = () => {
    const q = state.search.toLowerCase();
    const hits = students.filter(s => (s.name + " " + s.major + " " + s.id).toLowerCase().includes(q));
    count.textContent = hits.length + " of 300 records";
    T.body.replaceChildren(...(hits.length
      ? hits.slice(0, 25).map(s => T.row([s.id, nameCell(s), s.major, s.year, s.events.length, cardCell(s)], { grace: s.id === SMC.GRACE_ID }))
      : [T.empty("No records match that search.")]));
    more.hidden = hits.length <= 25;
    return hits.length;
  };
  /* Live on each keystroke; the field is outside the re-rendered region, so focus and caret stay. */
  input.addEventListener("input", () => { state.search = input.value; save(); announce(fill() + " of 300 records", 400); });
  fill();
  const node = h("section", null, renderHead("records"),
    h("div", { class: "c-records-top" }, h("div", { class: "sm-field" }, h("label", { class: "sm-field__label", for: "f-search", text: "Search by name, major or ID" }), input), count),
    T.box, more);
  node._refresh = fill;
  return node;
}
function renderWeight(p) {
  const id = "w-" + p.k, val = h("span", { class: "sm-weight__value", text: p.value });
  const input = h("input", { type: "range", min: 0, max: 10, step: 1, id, "data-fid": id });
  input.value = p.value;
  const fill = () => input.style.setProperty("--c-fill", "calc(12px + " + input.value / 10 + " * (100% - 24px))");
  fill();
  input.addEventListener("input", () => { val.textContent = input.value; fill(); p.onInput(Number(input.value)); });
  /* Page keys move the weight by 2 and never change stop while a slider has focus (7.8). */
  input.addEventListener("keydown", e => {
    if (e.key !== "PageUp" && e.key !== "PageDown") return;
    e.preventDefault();
    input.value = Number(input.value) + (e.key === "PageUp" ? 2 : -2);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  return h("div", { class: "sm-weight" }, h("div", { class: "sm-weight__top" }, h("label", { for: id, text: p.label }), val), input);
}
function screenMatch() {
  const cols = ["#", "Student", "Major", "Why on the list", "What we know"];
  const T = renderTable({ caption: "Match students to an event", cols, ordered: true, fixed: true });
  const pool = new Map(), slot = h("div");
  const rank = h("span", { class: "c-grace__rank", "aria-hidden": "true", "data-state": "closed" }), line = h("p", { class: "c-grace__line" });
  let lastRank = null, raf = 0, first = true;
  const pick = id => { state.hubEvent = id; delete ui.msgs.invite; refresh(true); };
  const option = e => e.title + " · " + e.when;
  /* Event picker (7.9): a native select; at 390 a radio group, so no option is ever cut short. */
  let picker;
  if (mq.sm.matches) {
    picker = h("fieldset", { class: "sm-event-picker" }, h("legend", { text: "Event" }), SMC.UPCOMING.map(e => {
      const r = h("input", { type: "radio", name: "event", value: e.id, "data-fid": "ev-" + e.id, onchange: () => pick(e.id) });
      r.checked = e.id === state.hubEvent;
      return h("label", { class: "sm-radio" }, r, h("span", { text: option(e) }));
    }));
  } else {
    const select = h("select", { class: "sm-select", id: "f-event", "data-fid": "event", onchange: e => pick(e.currentTarget.value) }, SMC.UPCOMING.map(e => h("option", { value: e.id, text: option(e) })));
    select.value = state.hubEvent;
    picker = h("div", { class: "sm-event-picker" }, h("label", { for: "f-event", text: "Event" }), select);
  }
  /* Render at most once per frame while a weight is dragged. */
  const schedule = () => { if (!raf) raf = window.requestAnimationFrame(() => { raf = 0; refresh(true); }); };
  const weights = WEIGHTS.map(([k, label]) => renderWeight({ k, label, value: state.weights[k], onInput: v => { state.weights[k] = v; schedule(); } }));
  function wash(rows) {
    $$(".c-wash", T.box).forEach(w => { gsap.killTweensOf(w); w.remove(); });
    rows.filter(el => !("grace" in el.dataset)).forEach(el => {
      const w = h("div", { class: "c-wash", style: "top:" + el.offsetTop + "px;height:" + el.offsetHeight + "px" });
      T.box.append(w);
      gsap.fromTo(w, { opacity: 1 }, { opacity: 0, duration: D.wash, ease: E.out, onComplete() { w.remove(); } });
    });
  }
  const put = (cell, v) => { v = String(v); if (cell.textContent !== v) cell.textContent = v; };
  function refresh(animate) {
    /* Storage is written after the drag settles, not on every frame. */
    window.clearTimeout(saveTimer); saveTimer = window.setTimeout(save, 250);
    const ev = SMC.UPCOMING.find(e => e.id === state.hubEvent), g = grace();
    const ranked = SMC.rankStudents(students, ev, state.weights);
    const gi = ranked.findIndex(r => r.s.id === SMC.GRACE_ID);
    const text = gi >= 0 ? "Grace Delgado is #" + (gi + 1) + " on this list" + (g.viaAI ? " because of her interview answers" : "") + "."
      : g.viaAI ? "Grace Delgado is not in the top 30 for this event." : "Grace has not done her interview yet, so the app knows little about her.";
    line.textContent = text;
    /* Moment 5: her rank as a large numeral that counts as the weights move; it leaves when she leaves the top 30. */
    rank.dataset.state = gi >= 0 ? "open" : "closed";
    if (gi >= 0) {
      M.count(rank, animate && lastRank != null ? lastRank : gi + 1, gi + 1, v => "#" + v);
      if (animate && lastRank == null) gsap.fromTo(rank, { opacity: 0 }, { opacity: 1, duration: D.base, ease: E.out, clearProps: "opacity" });
    }
    lastRank = gi >= 0 ? gi + 1 : null;
    /* Re-rank: rank numerals change at the start; rows travel with Flip; a new change re-targets from where they are. */
    const old = Array.from(T.body.children).filter(el => el.dataset.flipId), top = ranked.slice(0, 15);
    const same = old.length === top.length && top.length > 0 && top.every((r, i) => old[i].dataset.flipId === r.s.id);
    const fs = !same && animate && !M.reduced && old.length ? Flip.getState(old, { simple: true }) : null;
    const rows = top.map((r, i) => {
      const info = r.s.viaAI ? "Profile card (AI interview)" : r.info;
      let el = pool.get(r.s.id);
      if (!el) {
        el = T.row([i + 1, nameCell(r.s), r.s.major, r.reason, info], { id: r.s.id, grace: r.s.id === SMC.GRACE_ID });
        el._cells = $$("[data-col]", el); pool.set(r.s.id, el);
        return el;
      }
      if (!el.isConnected) { gsap.killTweensOf(el); gsap.set(el, { clearProps: "all" }); }
      put(el._cells[0], i + 1); put(el._cells[3], r.reason); put(el._cells[4], info);
      return el;
    });
    if (!same) T.body.replaceChildren(...(rows.length ? rows : [T.empty("No student matches with these weights. Raise at least one weight above 0.")]));
    if (fs && rows.length) {
      Flip.from(fs, { targets: rows, duration: D.move, ease: E.inOut, absolute: false, overwrite: true, simple: true,
        onEnter: entered => { gsap.fromTo(entered, { opacity: 0 }, { opacity: 1, duration: D.base, ease: E.out, overwrite: true }); wash(entered); } });
    } else if (!same && animate && M.reduced) gsap.fromTo(T.body, { opacity: 0 }, { opacity: 1, duration: 0.15, ease: "none", overwrite: true });
    slot.replaceChildren(...[renderMessage("invite")].filter(Boolean));
    if (animate && !first) announce(text, 600);
    first = false;
  }
  refresh(false);
  const node = h("section", { "data-dense": true }, renderHead("match"),
    h("div", { class: "c-match-band" },
      picker,
      h("div", { class: "c-grace" }, rank, line),
      h("div", { class: "c-weights" }, weights)),
    T.box,
    h("div", { class: "c-under" }, h("span", { text: "Showing 15 of the top 30." }),
      renderButton({ label: "Send personal invitations to top 30", "data-fid": "invite", onclick: () => setMsg("invite", "In the full version, each student gets a personal invitation and a reminder.") })),
    slot);
  node._refresh = () => refresh(false);
  return node;
}
function screenTalk() {
  return h("section", null, renderHead("talk"),
    h("div", { class: "c-grid2" },
      h("div", { class: "sm-card c-block", "data-anim": "bars" }, h("h2", { text: "Who was invited" }),
        h("p", { class: "c-note", text: "Students who said they're interested in technology or data, from every major, not only Computer Information Systems." }),
        renderBars({ rows: TALK.invited, max: 8, labelW: 220 })),
      h("div", { class: "sm-card c-block" }, h("h2", { text: "How your talk filled" }), renderFunnel(TALK.funnel),
        h("p", { class: "c-bignote", text: "A mass email to all students for a similar talk brought about 6 people." }))),
    h("div", { class: "sm-card c-block" }, h("h2", { text: "What students asked you" }),
      TALK.quotes.map(q => h("blockquote", { class: "c-quote", text: q })),
      h("p", { class: "c-note", text: "Average rating 4.6 of 5 from 14 students." })),
    h("div", { class: "sm-card c-block" }, h("h2", { text: "Stay involved" }),
      h("div", { class: "c-row" }, TALK.acts.map(([label, msg, variant], i) => renderButton({ label, variant, "data-fid": "act" + i, onclick: () => setMsg("talk", msg) }))),
      renderMessage("talk"),
      h("p", { class: "c-note", text: "You see totals and questions, never individual student records. Your contact stays with the college, not with one staff member." })));
}
const SCREENS = { entry: screenEntry, interview: screenInterview, recs: screenRecs, readiness: screenReadiness, growth: screenGrowth, overview: screenOverview, records: screenRecords, match: screenMatch, talk: screenTalk };

/* ---------- shell: top bar, stop rail, guide ---------- */
const mq = { sm: window.matchMedia("(max-width: 639px)"), compact: window.matchMedia("(max-width: 1199px)") };
const stopCount = id => h("span", { class: "c-stopcount", id }, "Stop ", h("b", { text: stopNo() }), " of ", h("b", { text: STOPS.length }));
function renderNav() {
  const p = PORTALS[state.portal], here = cur();
  return h("nav", { class: "sm-nav", "aria-label": p.name }, h("ul", null, p.items.map(([id, label]) =>
    h("li", null, h("button", { class: "sm-nav__item", type: "button", "aria-current": id === here ? "page" : null, onclick: () => go(id) }, label, id === here && els.navBar)))));
}
function renderChrome() {
  const p = state.portal, n = stopNo(), compact = mq.compact.matches;
  els.shell.dataset.screen = cur();
  els.bar.replaceChildren();
  add(els.bar, [
    h("a", { class: "sm-skip", href: "#main", text: "Skip to main content", onclick: e => { e.preventDefault(); els.main.focus(); } }),
    h("div", { class: "c-bar" },
      p && h("div", { class: "c-bar__brand" }, h("span", { class: "c-plate" }, h("img", { src: SMC.LOGO, alt: "Cal Poly Pomona" })),
        h("div", { class: "c-bar__who" }, h("span", { class: "c-bar__portal", text: PORTALS[p].name }), h("span", { class: "c-bar__id", text: PORTALS[p].who }))),
      renderMarker(),
      p && renderButton({ label: "Switch portal", variant: "secondary", onclick: () => go("entry") })),
    p && compact && h("div", { class: "c-strip" }, renderNav())]);
  els.rail.replaceChildren(...[
    n > 1 && renderButton({ label: "Back", variant: "stage", icon: "chevron-left", onclick: () => step(-1) }),
    h("div", { class: "c-rail__fill" }, p && !compact && renderNav()),
    h("div", { class: "c-rail__where" }, h("span", { class: "c-rail__who", text: (/\((\w+)\)$/.exec(GUIDE[cur()][0]) || [])[1] }), stopCount("rail-stop")),
    renderButton({ label: "Next", variant: "stage", iconAfter: "chevron-right", "aria-disabled": n === STOPS.length ? "true" : null, "aria-describedby": n === STOPS.length ? "rail-stop" : null, onclick: () => step(1) }),
    h("span", { class: "c-rail__dock" })
  ].filter(Boolean));
  els.guideBtn.setAttribute("aria-expanded", String(state.guideOpen));
  els.guideBtn.replaceChildren(icon("presentation", 20), h("span", { text: state.guideOpen ? "Hide presenter guide" : "Presenter guide" }));
  els.shell.dataset.guide = state.guideOpen ? "open" : "closed";
  els.guide.dataset.state = state.guideOpen ? "open" : "closed";
  if (state.guideOpen) renderGuide();
}
function renderGuide() {
  const [title, intent, steps, say] = GUIDE[cur()], n = stopNo(), armed = !!ui.armed;
  const reset = renderButton({ label: armed ? "Press again to reset" : "Reset demo", variant: "secondary", icon: "rotate-ccw", "data-armed": armed ? "true" : null, "data-fid": "reset", onclick: pressReset });
  /* A held key never confirms: repeats of Enter are swallowed. */
  reset.addEventListener("keydown", e => { if (e.repeat) e.preventDefault(); });
  if (armed && !M.reduced) {
    const bar = h("span", { class: "sm-confirm", "aria-hidden": "true" });
    reset.append(bar);
    gsap.fromTo(bar, { scaleX: ui.armLeft() }, { scaleX: 0, duration: 5 * ui.armLeft(), ease: "none" });
  }
  const content = h("div", { class: "c-stack" },
    h("p", { class: "sm-guide__eyebrow", text: "Presenter guide" }), h("h2", { text: title }), h("p", { text: intent }),
    h("ol", null, steps.map(s => h("li", { text: s }))),
    h("p", { class: "sm-guide__say" }, h("b", { text: "Say:" }), " ", say));
  els.guide.replaceChildren(content,
    h("div", { class: "sm-guide__stops" }, stopCount("guide-stop"),
      renderButton({ label: "Back", variant: "secondary", icon: "chevron-left", "aria-disabled": n === 1 ? "true" : null, "aria-describedby": n === 1 ? "guide-stop" : null, "data-fid": "g-back", onclick: () => step(-1) }),
      renderButton({ label: "Next", iconAfter: "chevron-right", "aria-disabled": n === STOPS.length ? "true" : null, "aria-describedby": n === STOPS.length ? "guide-stop" : null, "data-fid": "g-next", onclick: () => step(1) })),
    h("div", null, reset));
  return content;
}
function disarm() {
  if (!ui.armed) return;
  window.clearTimeout(ui.armed); ui.armed = null;
  if (state.guideOpen) refreshGuide();
}
function refreshGuide() {
  const act = document.activeElement, fid = els.guide.contains(act) && act.dataset.fid;
  renderGuide();
  if (fid) { const t = $$("[data-fid]", els.guide).find(x => x.dataset.fid === fid); if (t) t.focus({ preventScroll: true }); }
}
/* Reset demo (N5): inline confirm, 5 seconds, second press clears everything and returns to the entry. */
function pressReset() {
  if (!ui.armed) {
    const t0 = Date.now();
    ui.armLeft = () => Math.max(0, 1 - (Date.now() - t0) / 5000);
    ui.armed = window.setTimeout(disarm, 5000);
    refreshGuide();
    return;
  }
  window.clearTimeout(ui.armed); ui.armed = null;
  clearSaved();
  state = fresh(); students = SMC.makeStudents();
  ui.msgs = {}; ui.shown = {}; ui.shownRing = null;
  go("entry", { force: true });
}
function setGuide(open) {
  disarm();
  state.guideOpen = open; save();
  renderChrome();
  const g = els.guide;
  if (open) {
    if (M.reduced) gsap.fromTo(g, { opacity: 0 }, { opacity: 1, duration: 0.15, overwrite: true, clearProps: "opacity" });
    else gsap.fromTo(g, { opacity: 0, y: 12, scale: 0.98 }, { opacity: 1, y: 0, scale: 1, duration: D.base, ease: E.out, overwrite: true, clearProps: "opacity,transform" });
  } else {
    g.dataset.state = "open";
    gsap.to(g, { opacity: 0, duration: D.fast, ease: E.in, overwrite: true, onComplete() { g.dataset.state = "closed"; gsap.set(g, { clearProps: "all" }); } });
  }
  const s = $(".c-screen:not([data-leaving])", els.stage);
  if (s && s._mounted) s._mounted();
}

/* ---------- navigation ---------- */
function mount() {
  const id = cur(), node = SCREENS[id]();
  node.classList.add("c-screen"); node.dataset.screen = id;
  return node;
}
/* After a screen is in the page: fit its transcript, and make a table box focusable when it scrolls (7.7). */
function mounted(node) {
  if (node._mounted) node._mounted();
  $$(".sm-table-box", node).forEach(box => {
    if (box.scrollWidth <= box.clientWidth + 1) return;
    box.tabIndex = 0; box.setAttribute("role", "group"); box.setAttribute("aria-label", SCREEN[node.dataset.screen].title);
  });
}
function arrive(node, boot) {
  if (M.reduced) return;
  const id = node.dataset.screen;
  /* Moment 2: the doors arrive, once per page load. */
  if (id === "entry" && !ui.doorsDone) M.enter($$(".sm-door", node), { y: 16, stagger: SM_MOTION.stagger, delay: boot ? 0 : 0.1 });
  if (id === "entry") ui.doorsDone = true;
  /* Moment 4: the three reasons enter one after another once the interview has given the app something to say. */
  if (id === "recs" && state.ivDone) M.enter($$(".sm-event__why", node), { y: 8, stagger: SM_MOTION.stagger, delay: 0.1 });
  $$("[data-anim='bars'] .sm-bars", node).forEach(group =>
    M.track(gsap.from($$(".sm-bars__fill", group).slice(0, 8), { scaleX: 0, duration: D.base, ease: E.out, stagger: SM_MOTION.stagger, clearProps: "transform" })));
}
/* A stop change (14.5 moment 1). Focus moves to the new h1 at once; the travel never delays the presenter. */
function go(id, o) {
  M.finish();
  if (!els.toast.hidden) { window.clearTimeout(toastTimer); gsap.killTweensOf(els.toast); els.toast.hidden = true; }
  const from = STOPS.indexOf(cur()), old = $(".c-screen:not([data-leaving])", els.stage);
  if (id === cur() && old && !(o && o.force)) { $("h1", old).focus({ preventScroll: true }); return; }
  const p = SCREEN[id].portal;
  state.portal = p; if (p) state.page[p] = id;
  const to = STOPS.indexOf(id), dir = to >= from ? 1 : -1;
  ui.msgs = {}; disarm(); save();
  const bar = els.navBar, fs = bar.isConnected && !M.reduced ? Flip.getState(bar) : null;
  const rect = old && old.getBoundingClientRect();
  renderChrome();
  const next = mount();
  if (old && !M.reduced && !(o && o.boot)) {
    old.dataset.leaving = ""; old.setAttribute("aria-hidden", "true"); old.inert = true;
    old.style.top = rect.top + "px"; old.style.left = rect.left + "px"; old.style.width = rect.width + "px";
    M.track(gsap.to(old, { opacity: 0, x: -24 * dir, duration: D.fast, ease: E.in, onComplete() { old.remove(); } }));
    M.track(gsap.fromTo(next, { opacity: 0, x: 24 * dir }, { opacity: 1, x: 0, duration: D.move, ease: E.out, delay: 0.1, clearProps: "opacity,transform" }));
  } else {
    if (old) old.remove();
    if (!(o && o.boot)) M.enter([next]);
  }
  els.stage.append(next);
  window.scrollTo(0, 0);
  mounted(next);
  if (!(o && o.boot)) $("h1", next).focus({ preventScroll: true });
  if (fs && bar.isConnected) Flip.from(fs, { duration: D.move, ease: E.inOut, overwrite: true });
  arrive(next, o && o.boot);
  applyCounts(next, true);
  if (els.guide.dataset.state === "open" && !(o && o.boot)) gsap.fromTo(els.guide.firstElementChild, { opacity: 0 }, { opacity: 1, duration: 0.12, ease: "none" });
}
/* A change inside a screen: re-render the affected region in place, keep focus, count what changed. */
function update(o) {
  save();
  const old = $(".c-screen:not([data-leaving])", els.stage);
  if (old._refresh && !(o && o.full)) { old._refresh(); applyCounts(old, false); return old; }
  const act = document.activeElement, had = old.contains(act), fid = had && act.dataset.fid;
  const next = mount();
  old.replaceWith(next);
  mounted(next);
  if (had) {
    const t = (fid && $$("[data-fid]", next).find(x => x.dataset.fid === fid)) || (o && o.focus && $(o.focus, next));
    if (t) t.focus({ preventScroll: true });
  }
  applyCounts(next, false);
  return next;
}
function step(d) {
  const n = STOPS.indexOf(cur()) + d;
  if (n >= 0 && n < STOPS.length) go(STOPS[n]);
}

/* ---------- keys ---------- */
function onKey(e) {
  const t = e.target, tag = t.tagName;
  const typing = tag === "TEXTAREA" || t.isContentEditable || (tag === "INPUT" && !/^(checkbox|radio|range|button)$/.test(t.type));
  const adjusting = tag === "SELECT" || (tag === "INPUT" && t.type === "range");
  if (e.key === "Escape") {
    if (ui.armed) disarm();
    else if (state.guideOpen) { setGuide(false); els.guideBtn.focus(); }
    return;
  }
  if (typing || e.ctrlKey || e.metaKey || e.altKey) return;
  if ((e.key === "PageDown" || e.key === "PageUp") && !adjusting) {
    e.preventDefault();
    if (!e.repeat) step(e.key === "PageDown" ? 1 : -1);
  } else if ((e.key === "g" || e.key === "G") && tag !== "SELECT" && !e.repeat) setGuide(!state.guideOpen);
}

/* ---------- deep links (DESIGN.md 3.7) and boot ---------- */
function applyLinks() {
  const s = params.get("s"), p = params.get("p");
  if (s && SCREEN[s]) { state.portal = SCREEN[s].portal; if (state.portal) state.page[state.portal] = s; }
  else if (p && PORTALS[p]) state.portal = p;
  if (params.get("iv") === "done" && !state.ivDone) { ivReset(); GUIDED.forEach(ivApply); }
  (params.get("reg") || "").split(",").forEach(id => {
    if (SMC.UPCOMING.some(e => e.id === id) && !state.registered.includes(id)) { state.registered.push(id); state.lastRegistered = id; }
  });
  if (HELP[params.get("help")]) state.helpPanel = params.get("help");
  const w = (params.get("w") || "").split(",").map(Number);
  if (w.length === 4 && w.every(v => Number.isInteger(v) && v >= 0 && v <= 10)) WEIGHTS.forEach(([k], i) => { state.weights[k] = w[i]; });
  if (SMC.UPCOMING.some(e => e.id === params.get("ev"))) state.hubEvent = params.get("ev");
  if (params.has("q")) state.search = params.get("q");
  if (params.get("guide") === "1") state.guideOpen = true;
  /* theme=dark is accepted and ignored: this direction ships light only (DESIGN.md 14.3). */
  state.theme = "light";
}
function boot() {
  ["shell", "bar", "rail", "main", "stage", "guide", "toast"].forEach(id => { els[id] = document.getElementById(id); });
  els.guideBtn = document.getElementById("guide-button");
  els.status = document.getElementById("live-status");
  els.navBar = h("span", { class: "sm-nav__bar", "aria-hidden": "true" });
  /* One hidden log per transcript: it receives only the newest assistant turn, once (7.10). */
  els.ivLive = h("div", { class: "sm-vh", role: "log", "aria-live": "polite" });
  els.botLive = h("div", { class: "sm-vh", role: "log", "aria-live": "polite" });
  els.shell.append(els.ivLive, els.botLive);
  if (params.get("reset") === "1") clearSaved(); else load();
  if (!SCREEN[cur()]) state = fresh();
  applyLinks();
  save();
  go(cur(), { force: true, boot: true });
  els.guideBtn.addEventListener("click", () => setGuide(!state.guideOpen));
  els.toast.addEventListener("mouseenter", () => window.clearTimeout(toastTimer));
  els.toast.addEventListener("mouseleave", () => { toastTimer = window.setTimeout(hideToast, 4000); });
  document.addEventListener("pointerdown", M.finish, true);
  document.addEventListener("keydown", e => { if (!e.repeat) M.finish(); }, true);
  document.addEventListener("keydown", onKey);
  const relayout = () => { renderChrome(); update({ full: true }); };
  mq.sm.addEventListener("change", relayout);
  mq.compact.addEventListener("change", relayout);
  window.addEventListener("resize", () => { const s = $(".c-screen:not([data-leaving])", els.stage); if (s && s._mounted) s._mounted(); });
}
boot();
})();
