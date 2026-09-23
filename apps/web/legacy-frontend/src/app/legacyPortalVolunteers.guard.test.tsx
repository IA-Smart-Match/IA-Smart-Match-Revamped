/**
 * Fail-closed guard: no legacy volunteer-portal read survives under `src/`
 * (B26 T7, plan `docs/plans/b26-tracks/T7-plan.md` §3 tests 8-10).
 *
 * The legacy backend behind that path is not part of this repository. The one
 * allowed occurrence is the label on the Host Home assignments panel, matched
 * by file and exact trimmed line content. The needle is built from parts, and
 * no comment or test title spells it out, so this file never contains the
 * literal it hunts for (the walk also skips this file by path).
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const NEEDLE = ["portals", "volunteers"].join("/");
const API_PORTALS = ["/api", "portals"].join("/");
const HOME_FILE = "app/pages/volunteer/VolunteerHome.tsx";
const HOME_LINE = `endpoints={["/api/${NEEDLE}/{id}/assignments"]}`;

const ALLOWLIST: ReadonlyArray<{ file: string; line: string }> = [
  { file: HOME_FILE, line: HOME_LINE },
];

const SRC_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const GUARD_FILE = "app/legacyPortalVolunteers.guard.test.tsx";

type SourceFile = { file: string; text: string };
type Violation = { file: string; lineNo: number; line: string };

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name);
    return statSync(full).isDirectory() ? walk(full) : [full];
  });
}

function readSources(): SourceFile[] {
  return walk(SRC_DIR)
    .map((full) => path.relative(SRC_DIR, full).split(path.sep).join("/"))
    .filter((file) => file !== GUARD_FILE)
    .map((file) => ({ file, text: readFileSync(path.join(SRC_DIR, file), "utf8") }));
}

function scan(files: ReadonlyArray<SourceFile>): {
  violations: Violation[];
  allowHits: number[];
} {
  const allowHits = ALLOWLIST.map(() => 0);
  const violations: Violation[] = [];
  for (const { file, text } of files) {
    text.split(/\r?\n/).forEach((raw, index) => {
      const line = raw.trim();
      if (!line.includes(NEEDLE)) return;
      const allowed = ALLOWLIST.findIndex((entry) => entry.file === file && entry.line === line);
      if (allowed >= 0) {
        allowHits[allowed] += 1;
      } else {
        violations.push({ file, lineNo: index + 1, line });
      }
    });
  }
  return { violations, allowHits };
}

describe("legacy volunteer-portal guard", () => {
  it("no legacy volunteer-portal string under src/ outside the allowlist", () => {
    const files = readSources();
    const walked = new Set(files.map((f) => f.file));
    expect(files.length).toBeGreaterThan(50);
    expect(walked.has("lib/api.ts")).toBe(true);
    expect(walked.has(HOME_FILE)).toBe(true);

    const { violations, allowHits } = scan(files);
    expect(violations).toEqual([]);
    expect(allowHits).toEqual([1]);
  });

  it("guard self-test", () => {
    const direct = "requestJson(`/api/" + NEEDLE + "/${id}`)";
    expect(scan([{ file: "lib/x.ts", text: direct }]).violations).toHaveLength(1);
    expect(scan([{ file: "lib/x.ts", text: HOME_LINE }]).violations).toHaveLength(1);
    expect(scan([{ file: HOME_FILE, text: `${HOME_LINE} fetch(` }]).violations).toHaveLength(1);
    expect(scan([{ file: HOME_FILE, text: `    ${HOME_LINE}` }]).violations).toHaveLength(0);
  });

  it("VolunteerProfile.tsx contains no /api/portals string and no PortalDatasetUnavailable", () => {
    const text = readFileSync(path.join(SRC_DIR, "app/pages/volunteer/VolunteerProfile.tsx"), "utf8");
    expect(text.includes(API_PORTALS)).toBe(false);
    expect(text.includes("PortalDatasetUnavailable")).toBe(false);
  });
});
