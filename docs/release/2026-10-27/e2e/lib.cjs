// Shared helpers for the local class-exercise E2E run (Agent B). Local only.
const fs = require("fs");
const ENV = fs.readFileSync("/home/claude/IA-Smart-Match-Revamped/.env", "utf8");
const PASS = ENV.match(/^SMARTMATCH_EXERCISE_INSTRUCTOR_PASSCODE=(.*)$/m)[1].trim();
const BASE = "http://127.0.0.1:5174";

async function instructorLogin(browser) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage();
  await page.goto(BASE + "/exercise/instructor");
  await page.getByLabel("Passcode").fill(PASS);
  await page.getByLabel("Passcode").press("Enter");
  await page.getByRole("button", { name: "Show team codes" }).waitFor({ timeout: 20000 });
  return { ctx, page };
}

async function readTeamCodes(page) {
  await page.getByRole("button", { name: "Show team codes" }).click();
  await page.waitForTimeout(1000);
  const txt = await page.locator("body").innerText();
  const codes = {};
  for (const m of txt.matchAll(/Team (\d): (\d{4})/g)) codes[m[1]] = m[2];
  await page.getByRole("button", { name: "Hide team codes" }).click().catch(() => {});
  return codes;
}

// Opens results for every event, asking first each time (two-press). Returns count opened.
async function openAllResults(page, log) {
  const open = page.getByRole("button", { name: "Open results", exact: true });
  await page.getByRole("button", { name: /^(Open|Close) results$/ }).first().waitFor({ timeout: 20000 });
  let opened = 0;
  for (let guard = 0; guard < 20; guard++) {
    const left = await open.count();
    if (left === 0) break;
    await open.first().click();
    await page.getByRole("button", { name: "Open results now" }).click();
    for (let t = 0; t < 40; t++) {
      await page.waitForTimeout(500);
      if ((await open.count()) < left) break;
    }
    opened++;
  }
  log(`opened results for ${opened} event(s)`);
  return opened;
}

// Text of visible body with newlines collapsed, for evidence and number extraction.
async function bodyText(page) {
  return (await page.locator("body").innerText()).replace(/\s+\n/g, "\n");
}

module.exports = { BASE, PASS, instructorLogin, readTeamCodes, openAllResults, bodyText };
