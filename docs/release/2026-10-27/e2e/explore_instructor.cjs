// Exploration only: sign in on the instructor page, dump visible structure.
const { chromium } = require("playwright");
const fs = require("fs");
const env = fs.readFileSync("/home/claude/IA-Smart-Match-Revamped/.env", "utf8");
const pass = env.match(/^SMARTMATCH_EXERCISE_INSTRUCTOR_PASSCODE=(.*)$/m)[1].trim();
const base = "http://127.0.0.1:5174";
(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 720 } });
  const page = await ctx.newPage();
  await page.goto(base + "/exercise/instructor");
  await page.waitForTimeout(1500);
  console.log("LABELS:", await page.locator("label").allInnerTexts());
  console.log("BUTTONS:", await page.getByRole("button").allInnerTexts());
  await page.getByLabel("Passcode").fill(pass);
  await page.getByLabel("Passcode").press("Enter");
  await page.waitForTimeout(3000);
  await page.screenshot({ path: "/tmp/claude-0/instr_after_login.png", fullPage: true });
  console.log("TEXT:", (await page.locator("main, body").first().innerText()).slice(0, 2500));
  console.log("BUTTONS2:", await page.getByRole("button").allInnerTexts());
  await browser.close();
})().catch((e) => { console.error("EXPLORE_ERR", e.message); process.exit(1); });
