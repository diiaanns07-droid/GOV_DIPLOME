const { chromium } = require("playwright");
(async () => {
  const b = await chromium.launch({ args: ["--use-gl=swiftshader"] });
  const p = await (await b.newContext({ viewport: { width: 1440, height: 900 } })).newPage();
  p.on("pageerror", (e) => console.log("ERR", e.message));
  await p.goto("http://127.0.0.1:8501/"); await p.waitForFunction(() => window.SCHOOL_UI && SCHOOL_UI.ready(), null, { timeout: 20000 });
  await p.evaluate(() => localStorage.clear());
  await p.click("#govtech-toggle"); await p.waitForTimeout(800);
  await p.click("#sc-method-pedestrian-v1-strict"); await p.waitForTimeout(2000);
  console.log("saved", await p.evaluate(() => localStorage.getItem("govtech.school-case.v1").slice(0, 400)));
  await p.reload(); await p.waitForFunction(() => window.SCHOOL_UI && SCHOOL_UI.ready(), null, { timeout: 20000 });
  console.log("after reload", await p.evaluate(() => JSON.stringify({ pol: SCHOOL_UI.caseOf("shymkent").parameters.routing_policy_id, msg: SCHOOL_UI.state.msg })));
  await p.click("#govtech-toggle"); await p.waitForTimeout(2500);
  console.log("after toggle", await p.evaluate(() => JSON.stringify({ pol: SCHOOL_UI.caseOf("shymkent").parameters.routing_policy_id, msg: SCHOOL_UI.state.msg, cmp: !!SCHOOL_UI.state.cmp })));
  await b.close();
})();
