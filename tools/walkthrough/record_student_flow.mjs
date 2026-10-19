// Records a plain student walkthrough (no captions) as a .webm.
// Usage: see README.md. Config comes from the environment only.
import { chromium } from "playwright";

const base = process.env.WALKTHROUGH_BASE_URL;
if (!base) throw new Error("Set WALKTHROUGH_BASE_URL (e.g. http://localhost:5273).");
const outDir = process.env.WALKTHROUGH_OUT_DIR ?? "walkthrough-video";
const team = process.env.WALKTHROUGH_TEAM ?? "1";
const pause = Number(process.env.WALKTHROUGH_PAUSE_MS ?? 4000);
// Optional: opens instructor results in a separate, unrecorded context.
const passcode = process.env.EXERCISE_INSTRUCTOR_PASSCODE;

const browser = await chromium.launch({ slowMo: 400 });
try {
  if (passcode) {
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await page.goto(new URL("/exercise/instructor", base).href);
    await page.locator('input[type="password"]').fill(passcode);
    await page.keyboard.press("Enter");
    await page.waitForTimeout(1500);
    await ctx.close();
  }
  const ctx = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    recordVideo: { dir: outDir, size: { width: 1280, height: 720 } },
  });
  const page = await ctx.newPage();
  const beat = () => page.waitForTimeout(pause);
  await page.goto(new URL("/exercise", base).href);
  await beat();
  await page.getByLabel(`Team ${team}`).check({ force: true });
  await beat();
  await page.getByRole("button", { name: "Open this team's work" }).click();
  await page.waitForURL(/\/exercise\/events$/);
  await beat();
  await page.locator('a[href^="/exercise/events/"]').first().click();
  await page.waitForURL(/\/exercise\/events\/[^/]+$/);
  await beat();
  for (let i = 0; i < 4; i += 1) {
    await page.mouse.wheel(0, 500);
    await beat();
  }
  await page.getByRole("link", { name: "Go to results for this event" }).click();
  await page.waitForURL(/\/results$/);
  await beat();
  await ctx.close(); // flushes the .webm
  console.log(`Video saved under ${outDir}/`);
} finally {
  await browser.close();
}
