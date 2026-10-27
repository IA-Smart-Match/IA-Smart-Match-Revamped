const { chromium } = require("playwright");
const L = require("./lib.cjs");
(async () => {
  const browser = await chromium.launch();
  const { ctx, page } = await L.instructorLogin(browser);
  const codes = await L.readTeamCodes(page);
  console.log("CODES_TEAMS", Object.keys(codes).join(","));
  await L.openAllResults(page, (m) => console.log(m));
  await page.waitForTimeout(1500);
  console.log("AFTER_OPEN_BTNS", JSON.stringify(await page.getByRole("button", { name: /^(Open|Close) results$/ }).allInnerTexts()));
  await ctx.close(); await browser.close();
})().catch((e) => { console.error("EXPLORE_ERR", e.message); process.exit(1); });
