// Class-exercise student flow, local only (http://127.0.0.1:5174). Agent B, 2026-10-27.
// Two independent browser contexts (Team 1 and Team 2) run concurrently.
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");
const L = require("./lib.cjs");
const OUT = __dirname;
const SHOTS = path.join(OUT, "screenshots");
const results = { started_utc: new Date().toISOString(), base: L.BASE, teams: {}, steps: [], notes: [] };
const log = (m) => console.log(m);
const shot = async (page, name) => page.screenshot({ path: path.join(SHOTS, name + ".png"), fullPage: true });
const step = (id, detail) => { results.steps.push({ id, ...detail }); log(`STEP ${id} ${JSON.stringify(detail).slice(0, 300)}`); };

// Pull visible numbers from the results text for one event.
function parseNumbers(text) {
  const n = (re) => { const m = text.match(re); return m ? Number(m[1]) : null; };
  return {
    already_coming: n(/Already coming \((\d+)\)/),
    came_because_of_list: n(/Came because of your list \((\d+)\)/),
    still_open: n(/Still open \((\d+)\)/),
    extra_signups_from_list: n(/Your list brought (\d+) extra sign-ups/),
    people_on_list_signed_up: n(/(\d+) people on your list signed up/),
    would_have_signed_up_anyway: n(/(\d+) of them would have signed up from the mass email anyway|(\d+) of them would have signed up/),
  };
}

async function gotoEntry(page, teamNo, code) {
  await page.goto(L.BASE + "/exercise");
  await page.waitForTimeout(1200);
  const skip = page.getByRole("button", { name: "Skip" });
  if (await skip.isVisible().catch(() => false)) { await skip.click(); await page.waitForTimeout(300); }
  await page.locator(`label:has(input[aria-label='Team ${teamNo}'])`).click();
  await page.getByLabel("Team code").fill(code);
  await page.getByRole("button", { name: "Open this team's work" }).click();
  await page.waitForURL(/\/exercise\/events$/, { timeout: 20000 });
  await page.waitForTimeout(1200);
}

async function runRound(page, team, eventKey, settingName, tag) {
  await page.goto(L.BASE + `/exercise/events/${eventKey}`);
  await page.waitForTimeout(1500);
  await shot(page, `t${team}-${tag}-01-event-list`);
  await page.getByLabel("Give this setting a name").fill(settingName);
  await page.getByRole("button", { name: "Save this setting", exact: true }).click();
  await page.waitForTimeout(1200);
  await shot(page, `t${team}-${tag}-02-setting-saved`);
  step(`T${team}-${tag}-save-setting`, { setting: settingName, url: `/exercise/events/${eventKey}` });
  await page.getByRole("link", { name: "Choose one setting and see results" }).click();
  await page.waitForURL(/\/results$/, { timeout: 20000 });
  await page.waitForTimeout(1200);
  await page.locator("label:has(input[name='exercise-final-setting'])").first().click();
  await page.waitForTimeout(400);
  await page.getByRole("button", { name: "Run results for this event" }).click();
  await page.waitForTimeout(600);
  await shot(page, `t${team}-${tag}-03-send-list-armed`);
  const confirm = page.getByRole("button", { name: /^Send ‘/ });
  await confirm.click();
  await page.waitForTimeout(3500);
  await shot(page, `t${team}-${tag}-04-results`);
  const text = await L.bodyText(page);
  const nums = parseNumbers(text);
  step(`T${team}-${tag}-run-results`, { event: eventKey, numbers: nums });
  return { text, nums };
}

async function enterTeam(browser, team, code) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await ctx.newPage();
  await gotoEntry(page, team, code);
  await shot(page, `t${team}-00-events-after-entry`);
  step(`T${team}-enter-team`, { ok: true });
  return { ctx, page };
}

async function teamFlow(team, ctx, page) {
  const T = { team, rounds: {} };
  try {

    // Round 1 (Northline, E11)
    const r1 = await runRound(page, team, "E11", "Balanced", "r1");
    T.rounds.round1 = { event: "E11", numbers: r1.nums };
    results[`evidence_t${team}_r1`] = r1.text.slice(0, 6000);

    // Refresh mid-exercise: state should survive on the results page
    await page.reload();
    await page.waitForTimeout(1500);
    const afterRefresh = await L.bodyText(page);
    step(`T${team}-refresh-after-run`, { kept_results_run: /Results (already )?run/.test(afterRefresh) });
    await shot(page, `t${team}-05-refresh-after-run`);

    // Asking step
    await page.goto(L.BASE + "/exercise/asking");
    await page.waitForTimeout(1500);
    await shot(page, `t${team}-asking-01-page`);
    const choose = page.getByRole("button", { name: /^Choose this way: A small reward\.?$/ });
    await choose.click();
    await page.waitForTimeout(400);
    await page.getByRole("button", { name: /^Confirm: A small reward/ }).click();
    await page.waitForTimeout(1500);
    await shot(page, `t${team}-asking-02-choice-saved`);
    const askBtn = page.getByRole("button", { name: "Ask students now", exact: true });
    await askBtn.click();
    await page.waitForTimeout(400);
    const askConfirm = page.getByRole("button", { name: /^(Confirm|Ask students now\?)/ });
    if (await askConfirm.count()) await askConfirm.first().click();
    await page.waitForTimeout(2500);
    await shot(page, `t${team}-asking-03-asked`);
    step(`T${team}-asking`, { choice: "A small reward" });

    // Round 2 (Harbor, E12)
    const r2 = await runRound(page, team, "E12", "Balanced", "r2");
    T.rounds.round2 = { event: "E12", numbers: r2.nums };
    results[`evidence_t${team}_r2`] = r2.text.slice(0, 6000);

    // Final results overview
    await page.goto(L.BASE + "/exercise/events");
    await page.waitForTimeout(1500);
    await shot(page, `t${team}-06-final-events`);
    T.final_events_text = (await L.bodyText(page)).slice(0, 1500);
    results.teams[team] = T;
  } catch (e) {
    T.error = e.message.split("\n")[0];
    await shot(page, `t${team}-ERROR`).catch(() => {});
    results.teams[team] = T;
    step(`T${team}-ERROR`, { error: T.error });
  } finally {
    await ctx.close();
  }
}

(async () => {
  fs.mkdirSync(SHOTS, { recursive: true });
  const browser = await chromium.launch();
  const ictx = await L.instructorLogin(browser);
  const codes = await L.readTeamCodes(ictx.page);
  await ictx.ctx.close();
  // 1. Team 1 enters first (the instructor event list only renders once a team has entered).
  const t1 = await enterTeam(browser, 1, codes["1"]);
  // 2. Instructor opens results for every event (two presses each).
  const ictx2 = await L.instructorLogin(browser);
  await L.openAllResults(ictx2.page, log);
  await shot(ictx2.page, "instructor-after-open-results");
  step("instructor-open-results", { events: "E11,E12", method: "Open results -> Open results now, per event" });
  await ictx2.ctx.close();
  // 3. Team 2 enters in its own context, then both teams run concurrently.
  const t2 = await enterTeam(browser, 2, codes["2"]);
  await Promise.all([teamFlow(1, t1.ctx, t1.page), teamFlow(2, t2.ctx, t2.page)]);
  results.finished_utc = new Date().toISOString();
  fs.writeFileSync(path.join(OUT, "run_results.json"), JSON.stringify(results, null, 2));
  log("WROTE run_results.json");
  await browser.close();
})().catch((e) => { console.error("RUN_ERR", e.message); fs.writeFileSync(path.join(OUT, "run_results.json"), JSON.stringify({ ...results, fatal: e.message }, null, 2)); process.exit(1); });

