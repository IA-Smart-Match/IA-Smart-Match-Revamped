// Records a plain student walkthrough (no captions) as a .webm: Northline,
// save a setting, send the list, ask once, Harbor, before/after.
// Usage: see README.md. Config comes from the environment only.
import { chromium } from "playwright";

const base = process.env.WALKTHROUGH_BASE_URL;
if (!base) throw new Error("Set WALKTHROUGH_BASE_URL (e.g. http://localhost:5273).");
const outDir = process.env.WALKTHROUGH_OUT_DIR ?? "walkthrough-video";
const team = process.env.WALKTHROUGH_TEAM ?? "1";
const pause = Number(process.env.WALKTHROUGH_PAUSE_MS ?? 7000);
// The recording runs at least this long (default 3.5 min); a 3-5 min target.
const minMs = Number(process.env.WALKTHROUGH_MIN_MS ?? 210000);
const passcode = process.env.EXERCISE_INSTRUCTOR_PASSCODE;

const url = (p) => new URL(p, base).href;
const browser = await chromium.launch({ slowMo: 400 });
try {
  if (passcode) {
    // Unrecorded: sign in on the instructor page and open results for every event.
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await page.goto(url("/exercise/instructor"));
    await page.getByLabel("Passcode").fill(passcode);
    await page.getByLabel("Passcode").press("Enter");
    const open = page.getByRole("button", { name: "Open results", exact: true });
    await open.first().waitFor({ timeout: 15000 });
    while ((await open.count()) > 0) {
      await open.first().click();
      await page.getByRole("button", { name: "Open results now" }).click();
      await page.getByRole("button", { name: "Close results", exact: true }).first().waitFor();
    }
    await ctx.close();
  }

  const ctx = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    recordVideo: { dir: outDir, size: { width: 1280, height: 720 } },
  });
  const page = await ctx.newPage();
  const started = Date.now();
  const beat = (n = 1) => page.waitForTimeout(pause * n);
  const scroll = async (times) => {
    for (let i = 0; i < times; i += 1) {
      await page.mouse.wheel(0, 450);
      await beat();
    }
  };
  // Two-press buttons: first press arms, second press confirms.
  const pressTwice = async (name) => {
    const btn = page.getByRole("button", { name });
    await btn.click();
    await beat(0.5);
    await page.getByRole("button", { name: /^(Confirm|Send this list|Ask them now\?)/ }).click();
  };
  const openEvent = async (index) => {
    await page.goto(url("/exercise/events"));
    await beat();
    await page.locator('a[href^="/exercise/events/"]').nth(index).click();
    await page.waitForURL(/\/exercise\/events\/[^/]+$/);
    await beat();
  };
  const runResults = async () => {
    await page.getByRole("link", { name: "Go to results for this event" }).click();
    await page.waitForURL(/\/results$/);
    await beat();
    await page.getByRole("radio").first().check({ force: true }); // final setting
    await beat();
    await pressTwice(/Run results for this event/);
    await beat(2);
    await scroll(3);
  };

  // 1. Pick team, read Northline.
  await page.goto(url("/exercise"));
  await beat();
  await page.getByLabel(`Team ${team}`).check({ force: true });
  await beat();
  await page.getByRole("button", { name: "Open this team's work" }).click();
  await page.waitForURL(/\/exercise\/events$/);
  await beat();
  await openEvent(0);
  await scroll(4);
  // 2. Save a setting (when the page offers one), then send the list.
  const save = page.getByRole("button", { name: /^Save/ }).first();
  if (await save.isVisible().catch(() => false)) {
    await save.click();
    await beat();
  }
  await runResults();
  // 3. Ask for more (round two).
  await page.goto(url("/exercise/asking"));
  await beat();
  await pressTwice(/^Choose this way/);
  await beat();
  const ask = page.getByRole("button", { name: /^Ask them now/ });
  if (await ask.isVisible().catch(() => false)) {
    await pressTwice(/^Ask them now/);
    await beat(2);
  }
  // 4. Harbor: build the list, send it, compare before and after.
  await openEvent(1);
  await scroll(4);
  await runResults();
  // 5. Pad to the target length.
  const left = minMs - (Date.now() - started);
  if (left > 0) await page.waitForTimeout(left);
  const seconds = Math.round((Date.now() - started) / 1000);
  await ctx.close(); // flushes the .webm
  console.log(`Video saved under ${outDir}/ (about ${seconds}s)`);
} finally {
  await browser.close();
}
