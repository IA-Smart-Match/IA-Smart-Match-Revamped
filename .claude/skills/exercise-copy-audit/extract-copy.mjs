#!/usr/bin/env node
// Student-facing copy extractor for the class exercise. Node stdlib only.
//
//   node extract-copy.mjs [dir]              markdown table of every string: file:line | text
//   node extract-copy.mjs [dir] --banned     strings hitting a banned term (FAIL, exit 1) or a soft tell (warn);
//                                            also scans the exercise API routers' sentences (warn only:
//                                            some are instructor-only, read them)
//   node extract-copy.mjs [dir] --verbatim   every Ann string in ann-verbatim.md appears (exit 1 if any missing)
//
// dir defaults to apps/web/legacy-frontend/src/app/pages/exercise (run from the repo root).
// ponytail: regex scan, not a TS parser. Bare JSX text over several lines is joined into one row;
// a sentence split around an element (<strong>) still shows as fragments. Read the page too.
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const dir = args.find((a) => !a.startsWith("--")) ?? "apps/web/legacy-frontend/src/app/pages/exercise";
const mode = args.includes("--banned") ? "banned" : args.includes("--verbatim") ? "verbatim" : "table";
const ROOT = join(dir, "../../../../../../.."); // repo root, from the default dir
const DOMAIN = join(ROOT, "python/smartmatch_domain/smartmatch_domain/exercise");
const ROUTERS = join(ROOT, "services/api/smartmatch_api/routers");

// Instructor screens are not student copy; tests and art are not copy at all.
const SKIP_FILE = /(\.test\.|test_|testkit|Instructor|instructor|Art\.tsx$|resultsArt)/;
const SKIP_LINE =
  /^\s*(import |export \{|\/\/|\*|\/\*|#|type |interface |readonly )|className=|data-slot=|data-testid=|aria-hidden|console\.|logger\./;
// Tailwind class lists, ids, keys and type unions are not sentences.
const NOT_COPY = /^[a-z0-9:_\-/[\]. ]+$|\b(flex|gap-|px-|py-|text-ce|md:|lg:|rounded-|border-)|^[a-z_"]+( \| [a-z_"]+)+$/;

// Internal words that must not reach students (rubric R5, R1) and model-talk tells (R9).
export const BANNED = [
  [/\bslots?\b/i, "R5 internal word 'slot'"],
  [/\bworkspace\b/i, "R5 internal word 'workspace'"],
  [/\bfactors?\b/i, "R5 internal word 'factor'"],
  [/\brefresh(ed|ing)?\b/i, "R5 internal word 'refresh'"],
  [/\bdata file\b|\bdataset\b/i, "R5 internal word 'data file' (instructor page only)"],
  [/\bStep \d|\bstep (one|two|three)\b/i, "R1 'Step': use 'Round 1 / Round 2'"],
  [/\bround (one|two)\b/i, "R1 spelled-out round: use 'Round 1 / Round 2'"],
  [/\bSession \d\b/, "R1 'Session' is the class meeting, not a round"],
];
// Soft tells: listed by --banned for a human look, never fail the run.
export const WARN = [
  [/\bNote that\b|\bsimply\b|\bbasically\b|\bessentially\b|\bPlease note\b/i, "R9 model-talk filler"],
  [/—.*—/, "R9 em-dash chain"],
  [/\b(might|could|perhaps|possibly)\b/i, "R9 hedge (is it a real maybe?)"],
  [/^(This|It|That|These|Them) /, "R4 starts with 'this/it': is the noun on screen?"],
  [/\b(ranked|invitations|profiles?|invitees)\b/i, "R1 glossary: check the word (list, CBACH emails, students)"],
];

function walk(d, ext = /\.(tsx|ts)$/, skip = true) {
  if (!statSync(d, { throwIfNoEntry: false })) return [];
  return readdirSync(d).flatMap((name) => {
    const p = join(d, name);
    return statSync(p).isDirectory() ? walk(p, ext, skip) : ext.test(name) && !(skip && SKIP_FILE.test(p)) ? [p] : [];
  });
}

const JSX_TEXT = />([^<>{}]*[A-Za-z]{2,}[^<>{}]*)</g; // text between tags on one line
const LITERAL = /(["'`])((?:(?!\1)[^\\]|\\.)*?[A-Za-z]+ [A-Za-z]+(?:(?!\1)[^\\]|\\.)*?)\1/g; // 2+ words
const LABEL = /\b(label|title|text|heading|message|summary|hint|placeholder)\s*[:=]\s*["'`]([^"'`]*[A-Za-z]{3,}[^"'`]*)["'`]/g; // 1-word labels too
const JSX_LINE = /^\s*([A-Za-z“"][^<>=;]*[a-z.?!:”"}])\s*$/; // a bare text line inside JSX
// `{saved.max_settings}` -> `{max_settings}`: keep the placeholder visible, drop the code.
const squash = (line) =>
  line.replace(/\{(?:[^{}]|\{[^{}]*\})*\}/g, (m) => `{${(m.match(/[A-Za-z_]+/g) ?? ["x"]).pop()}}`);
const isBare = (text) =>
  !/[()]|=>|&&|\?\s|^(return|const|let|if|else|case|default)\b/.test(text) && text.split(" ").length > 1;

export function extract(file) {
  const rows = [];
  let open = null; // the bare-text row the previous line belonged to
  readFileSync(file, "utf8").split("\n").forEach((line, i) => {
    if (SKIP_LINE.test(line)) {
      open = null;
      return;
    }
    const plain = squash(line);
    const bare = plain.match(JSX_LINE);
    if (bare && isBare(bare[1])) {
      // JSX text wrapped over several lines is one sentence: join it.
      if (open && open.end === i) {
        open.text += ` ${bare[1].trim()}`;
        open.end = i + 1;
        return;
      }
      open = { file, line: i + 1, end: i + 1, text: bare[1].trim() };
      rows.push(open);
      return;
    }
    open = null;
    const found = new Set();
    for (const m of plain.matchAll(JSX_TEXT)) found.add(m[1].trim());
    for (const m of plain.matchAll(LITERAL)) found.add(m[2].trim());
    for (const m of plain.matchAll(LABEL)) found.add(m[2].trim());
    for (const text of found) if (text) rows.push({ file, line: i + 1, text });
  });
  return rows.filter((r) => !NOT_COPY.test(r.text));
}

const verbatim = readFileSync(join(HERE, "ann-verbatim.md"), "utf8")
  .split("\n")
  .map((l) => l.match(/^- "(.+)"\s*$/)?.[1])
  .filter(Boolean);
// Ann's exact words win over the rubric (owner rule): never flag them.
const isAnns = (text) => verbatim.some((v) => v.includes(text) || text.includes(v));
const loc = (r) => `${relative(process.cwd(), r.file)}:${r.line}`;
const cell = (s) => s.replace(/\|/g, "\\|");

if (mode === "table") {
  const rows = walk(dir).flatMap(extract);
  console.log("| file:line | text |\n|---|---|");
  for (const r of rows) console.log(`| ${loc(r)} | ${cell(r.text)} |`);
} else if (mode === "banned") {
  const rows = walk(dir).flatMap(extract);
  // Server sentences students can see are refusal details; docstrings are not copy.
  const server = walk(ROUTERS, /^exercise_.*\.py$/)
    .flatMap(extract)
    .filter((r) => /detail|message=|_REFUSAL|_SENTENCE|_MESSAGE/.test(readFileSync(r.file, "utf8").split("\n")[r.line - 1]));
  let hits = 0;
  console.log("| file:line | text | rule | level |\n|---|---|---|---|");
  for (const r of rows) {
    if (isAnns(r.text)) continue;
    for (const [re, why] of BANNED)
      if (re.test(r.text)) {
        hits++;
        console.log(`| ${loc(r)} | ${cell(r.text)} | ${why} | FAIL |`);
      }
    for (const [re, why] of WARN) if (re.test(r.text)) console.log(`| ${loc(r)} | ${cell(r.text)} | ${why} | warn |`);
  }
  for (const r of server)
    for (const [re, why] of BANNED)
      if (re.test(r.text)) console.log(`| ${loc(r)} | ${cell(r.text)} | ${why} (server: student-facing?) | warn |`);
  console.error(`${hits} banned-term hits (FAIL) in ${rows.length} strings; server sentences listed as warn`);
  process.exitCode = hits ? 1 : 0;
} else {
  // Reason lines are built server side, so the domain's exercise package counts as source too.
  // A test that asserts the exact rendered text proves a string built from template pieces.
  const tests = walk(join(ROOT, "apps/web/legacy-frontend/src/app/pages/exercise"), /\.test\.tsx$/, false);
  const files = [...walk(dir), ...walk(DOMAIN, /\.py$/), ...tests];
  const source = files.map((f) => readFileSync(f, "utf8")).join("\n").replace(/&apos;|\\'/g, "'").replace(/\s+/g, " "); // JSX wraps lines
  const missing = verbatim.filter((w) => !source.includes(w.replace(/\s+/g, " ")));
  for (const w of missing) console.log(`MISSING: "${w}"`);
  console.error(`${verbatim.length - missing.length} of ${verbatim.length} Ann strings found`);
  process.exitCode = missing.length ? 1 : 0;
}
