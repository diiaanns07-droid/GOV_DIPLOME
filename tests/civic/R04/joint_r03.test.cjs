/* Joint test: R04 editor (this tree) + R03 public map module of the PINNED delivery (d5ee758, read with `git show`, not
 * checked out) on one MapLibre map, against the contract mock. Shows what happens when the editor draws over a public
 * object: with R03 as delivered (observation, recorded, not asserted — R03 is not R04's code) and with the 2-line patch
 * R04 proposes (asserted). The patch is fixtures/r03_editor_tool_patch.json (= research/round-13-results/R04/r03_editor_tool.patch).
 * Run:  node --test tests/civic/R04/joint_r03.test.cjs        Evidence: R04_EVIDENCE=1 -> research/round-13-results/R04/evidence/joint_r03.json
 * Without Playwright or the pinned R03 commit the suite is skipped (NOT_RUN).
 */
"use strict";
const { describe, it, before, after } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { execFileSync } = require("child_process");
const { startStand } = require("./stand.cjs");
const { loadPlaywright, makeKit, fk, sleep } = require("./e2e_helpers.cjs");

const PW = loadPlaywright();
const REPO = path.resolve(__dirname, "../../..");
const PATCH = JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures/r03_editor_tool_patch.json"), "utf8"));
function r03Dirs() {
  try {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), "r04-joint-r03-"));
    const out = {};
    for (const v of ["pinned", "patched"]) {
      const dir = path.join(root, v);
      fs.mkdirSync(dir);
      for (const f of ["civic-map-core.js", "civic-map.js"]) {
        let src = execFileSync("git", ["-C", REPO, "show", PATCH.base + ":web/civic/map/" + f], { stdio: ["ignore", "pipe", "ignore"] }).toString("utf8");
        if (v === "patched" && f === "civic-map.js") for (const r of PATCH.replacements) { assert.equal(src.split(r.find).length, 2, "patch anchor"); src = src.replace(r.find, r.replace); }
        fs.writeFileSync(path.join(dir, f), src);
      }
      out[v] = dir;
    }
    return out;
  } catch (e) { return null; }
}
const DIRS = PW ? r03Dirs() : null;
const skip = !PW ? "playwright not installed" : !DIRS ? "R03 commit " + PATCH.base + " not available locally (NOT_RUN)" : false;

describe("R04 editor + R03 public map on one map (joint, pinned R03)", { skip }, () => {
  let stand, browser, K;
  const pages = [], evidence = { r03_sha: PATCH.base, runs: {} };
  before(async () => {
    stand = await startStand({ staticDirs: [{ prefix: "/r03-pinned/", dir: DIRS.pinned }, { prefix: "/r03-patched/", dir: DIRS.patched }] });
    browser = await PW.chromium.launch({ args: ["--enable-unsafe-swiftshader"] });
    K = makeKit({ stand, browser, pages, shotsDir: path.join(REPO, "research/round-13-results/R04/screenshots") });
  });
  after(async () => {
    if (process.env.R04_EVIDENCE === "1") {
      const dir = path.join(REPO, "research/round-13-results/R04/evidence");
      fs.mkdirSync(dir, { recursive: true });
      fs.writeFileSync(path.join(dir, "joint_r03.json"), JSON.stringify(evidence, null, 1) + "\n");
    }
    if (browser) await browser.close();
    if (stand) await stand.close();
  });

  async function run(variant) {
    K.H().reset();
    const pub = await K.seedPublished({ title: "Публичный объект под курсором", geometry: { type: "Point", coordinates: [71.43, 51.13] } });
    const p = await K.newPage();
    await p.goto(stand.url + "/harness/joint.html?r03=" + variant);
    await p.waitForFunction(() => window.__mapState === "loaded" || String(window.__mapState || "").startsWith("error"), null, { timeout: 20000 });
    assert.equal(await p.evaluate(() => window.__mapState), "loaded");
    // R03 rendered the public object (its own layers) — wait until a click target exists at the object's pixel
    const at = async () => p.evaluate(() => { const q = window.__map.project([71.43, 51.13]), r = window.__map.getCanvas().getBoundingClientRect(); return { x: r.left + q.x, y: r.top + q.y }; });
    await p.waitForFunction(() => window.__map.queryRenderedFeatures(window.__map.project([71.43, 51.13])).some((f) => !String(f.layer.id).startsWith("civic-r04-")), null, { timeout: 20000 });
    await p.waitForSelector(fk("login-user"));
    await K.loginToList(p);
    await K.fillDraft(p, { title: "Отметка поверх публичного объекта" });
    // 1) hover over the public object while the line tool is active: whose cursor wins?
    await p.click(fk("tool-line"));
    const pt = await at();
    await p.mouse.move(pt.x + 2, pt.y + 2);
    await sleep(250);
    const cursor = await p.evaluate(() => window.__map.getCanvas().style.cursor);
    await p.keyboard.press("Escape");
    // 2) place the editor's point exactly on the public object
    const before = await p.evaluate(() => window.__r03selects.length);
    await p.click(fk("tool-point"));
    await p.mouse.click(pt.x, pt.y);
    await p.waitForSelector(fk("geometry_confirmed"));
    await sleep(300);
    const selects = (await p.evaluate(() => window.__r03selects)).slice(before);
    const events = await p.evaluate(() => window.__toolEvents);
    const r = { r03_selected_while_drawing: selects.length > 0, r03_selects: selects, cursor_while_drawing: cursor,
      tool_events_balanced: events.filter((e) => e.active).length === events.filter((e) => !e.active).length, editor_point_set: true, public_id: pub.id };
    evidence.runs[variant] = r;
    await p.context().close();
    return r;
  }

  it("R03 as delivered (d5ee758): observation only — does drawing over a public object also select it?", async (t) => {
    const r = await run("pinned");
    t.diagnostic("pinned R03: selected while drawing = " + r.r03_selected_while_drawing + ", cursor while drawing = '" + r.cursor_while_drawing + "'");
    assert.equal(r.tool_events_balanced, true, "the editor's start/end events stay balanced either way");
  });

  it("R03 + the proposed patch: a drawing click places only the editor's mark, the crosshair stays", async () => {
    const r = await run("patched");
    assert.equal(r.r03_selected_while_drawing, false, "R03 must not open the public card under an editor click: " + JSON.stringify(r.r03_selects));
    assert.equal(r.cursor_while_drawing, "crosshair");
    assert.equal(r.tool_events_balanced, true);
  });
});
