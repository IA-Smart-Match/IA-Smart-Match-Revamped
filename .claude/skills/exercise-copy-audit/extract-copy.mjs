#!/usr/bin/env node
// Student-facing copy extractor for the class exercise. Node stdlib only.
//
//   node extract-copy.mjs [dir]              markdown table of every string: file:line | text
//   node extract-copy.mjs [dir] --banned     only strings hitting a banned term (exit 1 if any)
//   node extract-copy.mjs [dir] --verbatim   check each Ann string in ann-verbatim.md appears (exit 1 if any missing)
//
// dir defaults to apps/web/legacy-frontend/src/app/pages/exercise (run from the repo root).
// ponytail: regex scan, not a TS parser. Misses strings split across JSX expressions
// ("Saved {n} so far") as one sentence; each fragment is listed on its own line instead.
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const dir = args.find((a) => !a.startsWith("--")) ?? "apps/web/legacy-frontend/src/app/pages/exercise";
const mode = args.includes("--banned") ? "banned" : args.includes("--verbatim") ? "verbatim" : "table";

// Instructor screens are not student copy; tests and art are not copy at all.
const SKIP_FILE = /(\.test\.|test_|testkit|Instructor|instructor|Art\.tsx$|resultsArt)/;
const SKIP_LINE = /^\s*(import |export \{|\/\/|\*|\/\*)|className=|data-slot=|data-testid=|aria-hidden|console\./;

// Internal words that must not reach students (rubric R5) and model-talk tells (R9).
export const BANNED = [
  [/\bslots?\b/i, "R5 internal word 'slot'"],
  [/\bworkspace\b/i, "R5 internal word 'workspace'"],
  [/\bfactors?\b/i, "R5 internal word 'factor'"],
  [/\brefresh(ed|ing)?\b/i, "R5 internal word 'refresh'"],
  [/\bStep \d|\bstep (one|two|three)\b/i, "R1 'Step' — use 'Round'"],
];
// Soft tells: listed by --banned for a human look, never fail the run.
export const WARN = [
  [/\bNote that\b|\bsimply\b|\bbasically\b|\bessentially\b|\bPlease note\b/i, "R9 model-talk filler"],
  [/—.*—/, "R9 em-dash chain"],
  [/\b(might|could|perhaps|possibly)\b/i, "R9 hedge (is it a real maybe?)"],
  [/^(This|It|That) /, "R4 starts with 'this/it': is the referent on screen?"],
];

function walk(d) {
  return readdirSync(d).flatMap((name) => {
    const p = join(d, name);
    return statSync(p).isDirectory() ? walk(p) : /\.(tsx|ts)$/.test(name) && !SKIP_FILE.test(p) ? [p] : [];
  });
}

const JSX_TEXT = />([^<>{}]*[A-Za-z]{2,}[^<>{}]*)</g; // text between tags on one line
const LITERAL = /(["'`])((?:(?!\1)[^\\]|\\.)*?[A-Za-z]+ [A-Za-z]+(?:(?!\1)[^\\]|\\.)*?)\1/g; // 2+ words
const JSX_LINE = /^\s*([A-Z][^<>=;]*[a-z.?!:”"}])\s*$/; // a bare text line inside JSX
// `{saved.max_settings}` -> `{max_settings}`: keep the slot visible, drop the code.
const squash = (line) => line.replace(/\{(?:[^{}]|\{[^{}]*\})*\}/g, (m) => `{${(m.match(/[A-Za-z_]+(?=\W*$)|[A-Za-z_]+/g) ?? ["x"]).pop()}}`);

export function extract(file) {
  const rows = [];
  readFileSync(file, "utf8").split("\n").forEach((line, i) => {
    if (SKIP_LINE.test(line)) return;
    const found = new Set();
    const plain = squash(line);
    for (const m of plain.matchAll(JSX_TEXT)) found.add(m[1].trim());
    for (const m of line.matchAll(LITERAL)) found.add(m[2].trim());
    const bare = plain.match(JSX_LINE);
    if (bare && !/[()]|=>|&&|\?\s/.test(bare[1]) && bare[1].split(" ").length > 1) found.add(bare[1].trim());
    for (const text of found) if (text && !/^[a-z-]+(\s[a-z-]+)*$/.test(text)) rows.push({ file, line: i + 1, text });
  });
  return rows;
}

const rows = walk(dir).flatMap(extract);
const verbatim = readFileSync(join(HERE, "ann-verbatim.md"), "utf8")
  .split("\n")
  .map((l) => l.match(/^- "(.+)"\s*$/)?.[1])
  .filter(Boolean);
// Ann's exact words win over the rubric (BRIEF rule 10): never flag them.
const isAnns = (text) => verbatim.some((v) => v.includes(text) || text.includes(v));
const loc = (r) => `${relative(process.cwd(), r.file)}:${r.line}`;
const cell = (s) => s.replace(/\|/g, "\\|");

if (mode === "table") {
  console.log("| file:line | text |\n|---|---|");
  for (const r of rows) console.log(`| ${loc(r)} | ${cell(r.text)} |`);
} else if (mode === "banned") {
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
  console.error(`${hits} banned-term hits (FAIL) in ${rows.length} strings`);
  process.exitCode = hits ? 1 : 0;
} else {
  // Each line of ann-verbatim.md shaped `- "exact text"` must appear somewhere in the sources.
  // Reason lines are built server side, so the domain's exercise package counts as source too.
  const domain = join(dir, "../../../../../../../python/smartmatch_domain/smartmatch_domain/exercise");
  const files = [...walk(dir), ...(statSync(domain, { throwIfNoEntry: false }) ? walk(domain) : [])];
  const source = files.map((f) => readFileSync(f, "utf8")).join("\n").replace(/&apos;|\\'/g, "'");
  const wanted = verbatim;
  const missing = wanted.filter((w) => !source.includes(w));
  for (const w of missing) console.log(`MISSING: "${w}"`);
  console.error(`${wanted.length - missing.length} of ${wanted.length} Ann strings found`);
  process.exitCode = missing.length ? 1 : 0;
}
