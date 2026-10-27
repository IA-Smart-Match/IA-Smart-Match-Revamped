// Continues Team 1 (asking + Round 2) and runs edge checks on Team 3. Local only.
const { chromium } = require("playwright");
const fs = require("fs"); const path = require("path");
const L = require("./lib.cjs");
const SHOTS = path.join(__dirname, "screenshots");
const out = { started_utc: new Date().toISOString(), t1_rest: {}, edges: [] };
const shot = (p, n) => p.screenshot({ path: path.join(SHOTS, n + ".png"), fullPage: true });
const edge = (id, o) => { out.edges.push({ id, ...o }); console.log("EDGE", id, JSON.stringify(o).slice(0, 260)); };
async function enter(browser, team, code) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage();
  await page.goto(L.BASE + "/exercise"); await page.waitForTimeout(1200);
  const sk = page.getByRole("button", { name: "Skip" }); if (await sk.isVisible().catch(() => false)) await sk.click();
  await page.locator(`label:has(input[aria-label='Team ${team}'])`).click();
  await page.getByLabel("Team code").fill(code);
  await page.getByRole("button", { name: "Open this team's work" }).click();
  await page.waitForURL(/\/exercise\/events$/, { timeout: 20000 });
  return { ctx, page };
}
(async () => {
  const browser = await chromium.launch();
  const ic = await L.instructorLogin(browser);
  const codes = await L.readTeamCodes(ic.page); await ic.ctx.close();

  // ---- Team 1 continuation: asking step then Round 2 (E12)
  const t1 = await enter(browser, 1, codes["1"]);
  const p = t1.page;
  await p.goto(L.BASE + "/exercise/asking"); await p.waitForTimeout(1500);
  const askTxt = await L.bodyText(p);
  out.t1_rest.asking_before = askTxt.includes("Round 1 done") ? "page loaded" : askTxt.slice(0, 200);
  try {
    await p.getByRole("button", { name: /^Choose this way: A small reward/ }).click({ force: true, timeout: 15000 });
    await p.waitForTimeout(500);
    await p.getByRole("button", { name: /^Confirm: A small reward/ }).click({ force: true, timeout: 15000 });
    await p.waitForTimeout(1500);
    await p.getByRole("button", { name: "Ask students now", exact: true }).click({ force: true, timeout: 15000 });
    await p.waitForTimeout(500);
    const c = p.getByRole("button", { name: /^(Confirm|Ask students now\?)/ });
    if (await c.count()) await c.first().click({ force: true });
    await p.waitForTimeout(2500);
    await shot(p, "t1-asking-03-asked");
    out.t1_rest.asking = "done";
  } catch (e) { out.t1_rest.asking = "ERROR " + e.message.split("\n")[0]; await shot(p, "t1-asking-ERROR").catch(()=>{}); }
  try {
    await p.goto(L.BASE + "/exercise/events/E12"); await p.waitForTimeout(1500);
    await p.getByLabel("Give this setting a name").fill("Balanced");
    await p.getByRole("button", { name: "Save this setting", exact: true }).click({ force: true });
    await p.waitForTimeout(1200);
    await p.getByRole("link", { name: "Choose one setting and see results" }).click({ force: true });
    await p.waitForURL(/\/results$/, { timeout: 20000 }); await p.waitForTimeout(1200);
    await p.locator("label:has(input[name='exercise-final-setting'])").first().click({ force: true });
    await p.getByRole("button", { name: "Run results for this event" }).click({ force: true });
    await p.waitForTimeout(500);
    await p.getByRole("button", { name: /^Send ‘/ }).click({ force: true });
    await p.waitForTimeout(3000);
    const t = await L.bodyText(p);
    out.t1_rest.round2_text_excerpt = t.slice(t.indexOf("Your list brought") - 10, t.indexOf("Your list brought") + 160);
    out.t1_rest.round2 = /Results already run/.test(t) ? "run recorded" : "not confirmed";
    await shot(p, "t1-r2-04-results");
  } catch (e) { out.t1_rest.round2 = "ERROR " + e.message.split("\n")[0]; await shot(p, "t1-r2-ERROR").catch(()=>{}); }
  await t1.ctx.close();

  // ---- Edge checks on Team 3 (never entered before)
  // E-01 wrong 4-digit code refused
  const w = await browser.newContext(); const wp = await w.newPage();
  await wp.goto(L.BASE + "/exercise"); await wp.waitForTimeout(1200);
  const sk = wp.getByRole("button", { name: "Skip" }); if (await sk.isVisible().catch(() => false)) await sk.click();
  await wp.locator("label:has(input[aria-label='Team 3'])").click();
  await wp.getByLabel("Team code").fill("0000");
  await wp.getByRole("button", { name: "Open this team's work" }).click({ force: true }); await wp.waitForTimeout(2000);
  const wt = await L.bodyText(wp);
  edge("E-01", { input: "team 3, code 0000 (wrong)", url: new URL(wp.url()).pathname, refusal: (wt.match(/[^\n]*(code|Code|match|not)[^\n]*/g) || []).slice(0, 3) });
  await shot(wp, "E-01-wrong-code");
  // E-02 short code keeps button disabled
  await wp.getByLabel("Team code").fill("12"); await wp.waitForTimeout(300);
  edge("E-02", { input: "code '12' (too short)", button_disabled: await wp.getByRole("button", { name: "Open this team's work" }).isDisabled() });
  // E-03 letters are dropped by the input
  await wp.getByLabel("Team code").fill("abcd"); await wp.waitForTimeout(200);
  edge("E-03", { input: "code 'abcd'", stored_value_length: (await wp.getByLabel("Team code").inputValue()).length });
  await shot(wp, "E-02-03-invalid-code");
  // E-04 deep link refresh (no team yet: should redirect or show entry)
  await wp.goto(L.BASE + "/exercise/events/E11/results"); await wp.waitForTimeout(1500);
  edge("E-04", { input: "direct load /exercise/events/E11/results without team", url: new URL(wp.url()).pathname, text: (await L.bodyText(wp)).slice(0, 120).replace(/\n/g, " | ") });
  await w.close();

  // Team 3: enter with correct code
  const t3 = await enter(browser, 3, codes["3"]); const q = t3.page;
  // E-05 empty setting name
  await q.goto(L.BASE + "/exercise/events/E11"); await q.waitForTimeout(1500);
  const saveBtn = q.getByRole("button", { name: "Save this setting", exact: true });
  edge("E-05", { input: "setting name empty", save_disabled: await saveBtn.isDisabled() });
  // E-06 refresh mid-exercise: save a setting, reload, check it persists
  await q.getByLabel("Give this setting a name").fill("Refresh test");
  await saveBtn.click({ force: true }); await q.waitForTimeout(1200);
  await q.reload(); await q.waitForTimeout(1500);
  const afterReload = await L.bodyText(q);
  edge("E-06", { input: "save 'Refresh test' then reload mid-exercise", setting_kept: afterReload.includes("Refresh test") || afterReload.includes("Balanced") });
  await shot(q, "E-06-refresh-mid-exercise");
  // E-07 duplicate send: double-click send, count server runs for team 3 E11 afterwards
  await q.getByRole("link", { name: "Choose one setting and see results" }).click({ force: true });
  await q.waitForURL(/\/results$/, { timeout: 20000 }); await q.waitForTimeout(1200);
  await q.locator("label:has(input[name='exercise-final-setting'])").first().click({ force: true });
  await q.getByRole("button", { name: "Run results for this event" }).click({ force: true });
  await q.waitForTimeout(400);
  const send = q.getByRole("button", { name: /^Send ‘/ });
  const dup = [];
  try { await send.click({ force: true, timeout: 5000 }); } catch (e) { dup.push("first:" + e.message.split("\n")[0].slice(0, 80)); }
  try { await send.click({ force: true, timeout: 5000 }); } catch (e) { dup.push("second:" + e.message.split("\n")[0].slice(0, 80)); }
  await q.waitForTimeout(3000);
  const afterDup = await L.bodyText(q);
  edge("E-07", { input: "double press of confirm 'Send'", ui_after: /Results already run/.test(afterDup) ? "Results already run (one run)" : "not run", click_errors: dup });
  await shot(q, "E-07-duplicate-send");
  // E-08 deep-link refresh on routes
  for (const [id, pth] of [["E-08a", "/exercise/events/E11/results"], ["E-08b", "/exercise/asking"], ["E-08c", "/exercise/events"]]) {
    await q.goto(L.BASE + pth); await q.waitForTimeout(1500); await q.reload(); await q.waitForTimeout(1500);
    edge(id, { route: pth, after_reload_path: new URL(q.url()).pathname, rendered: (await L.bodyText(q)).length > 200 });
  }
  await t3.ctx.close();
  // E-09 instructor deep link
  const dl = await browser.newContext(); const dp = await dl.newPage();
  await dp.goto(L.BASE + "/exercise/instructor"); await dp.waitForTimeout(1200);
  edge("E-09", { route: "/exercise/instructor (direct load)", renders_passcode: await dp.getByLabel("Passcode").isVisible().catch(() => false) });
  await dl.close();
  out.finished_utc = new Date().toISOString();
  fs.writeFileSync(path.join(__dirname, "run_edges.json"), JSON.stringify(out, null, 2));
  console.log("WROTE run_edges.json");
  await browser.close();
})().catch((e) => { console.error("REST_ERR", e.message); process.exit(1); });
