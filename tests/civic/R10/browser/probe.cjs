// R10 UI-agnostic browser probe (Playwright, CommonJS). Real screenshots of a running build.
//   NODE_PATH=/opt/node22/lib/node_modules node tests/civic/R10/browser/probe.cjs \
//     --url http://127.0.0.1:PORT/ --out research/round-11-results/R10/shots/<label> --label <label>
// Checks that do not depend on R01's selectors: one map canvas (U01), light background (U01),
// attribution present and not covered (U06), basemap requests and failures (U06 NOT_RUN when
// blocked), no /staff/ calls from the public page (U09), no session/role in JS-visible storage
// or cookies (S06/S07), XSS sentinel never fired (S10/U10), console/page errors.
'use strict';
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

function arg(name, fallback) {
  const i = process.argv.indexOf('--' + name);
  return i > 0 ? process.argv[i + 1] : fallback;
}

const URL_ = arg('url');
const OUT = arg('out');
const LABEL = arg('label', 'probe');
const WAIT_MS = Number(arg('wait', '6000'));
const EXE = process.env.R10_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const VIEWPORTS = [{ name: 'desktop', width: 1440, height: 900 }, { name: 'mobile', width: 390, height: 844 }];

async function probe(browser, vp) {
  const context = await browser.newContext({ viewport: { width: vp.width, height: vp.height },
    deviceScaleFactor: 1, isMobile: vp.name === 'mobile', hasTouch: vp.name === 'mobile' });
  const page = await context.newPage();
  const requests = [];
  const failures = [];
  const consoleErrors = [];
  const dialogs = [];
  page.on('request', (r) => requests.push({ url: r.url(), method: r.method(), type: r.resourceType() }));
  page.on('requestfailed', (r) => failures.push({ url: r.url(), error: (r.failure() || {}).errorText }));
  page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 300)); });
  page.on('pageerror', (e) => consoleErrors.push('pageerror: ' + String(e).slice(0, 300)));
  page.on('dialog', async (d) => { dialogs.push(d.message()); await d.dismiss(); });
  const t0 = Date.now();
  let navError = null;
  try {
    await page.goto(URL_, { waitUntil: 'domcontentloaded', timeout: 30000 });
  } catch (e) { navError = String(e).slice(0, 300); }
  await page.waitForTimeout(WAIT_MS);
  const loadMs = Date.now() - t0;
  const facts = await page.evaluate(() => {
    const canvases = [...document.querySelectorAll('canvas')];
    const mapCanvases = [...document.querySelectorAll('canvas.maplibregl-canvas')];
    // Attribution: MapLibre control with text, or any visible element naming OSM/OpenFreeMap.
    const visibleUncovered = (el) => {
      const r = el.getBoundingClientRect();
      if (!(r.width > 0 && r.height > 0 && r.right <= innerWidth + 1 && r.bottom <= innerHeight + 1 && r.left >= -1 && r.top >= -1)) return { inViewport: false, notCovered: false, rect: [r.left, r.top, r.width, r.height] };
      const top = document.elementFromPoint(Math.min(Math.max(r.left + r.width / 2, 0), innerWidth - 1), Math.min(Math.max(r.top + r.height / 2, 0), innerHeight - 1));
      return { inViewport: true, notCovered: !!top && (el === top || el.contains(top) || top.contains(el)), rect: [r.left, r.top, r.width, r.height] };
    };
    const candidates = [];
    const ctrl = document.querySelector('.maplibregl-ctrl-attrib');
    if (ctrl && ctrl.innerText.trim()) candidates.push(ctrl);
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
    while (walker.nextNode()) {
      const el = walker.currentNode;
      if (el.children.length === 0 && /(©|OpenStreetMap|OSM contributors|OpenMapTiles)/i.test(el.textContent || '') && !/недоступн|unavailable/i.test(el.textContent || '')) candidates.push(el);
    }
    const attributionCandidates = candidates.slice(0, 5).map((el) => ({ text: (el.innerText || el.textContent).trim().slice(0, 160), ...visibleUncovered(el) }));
    const attribution = attributionCandidates.find((a) => a.inViewport && a.notCovered) || attributionCandidates[0] || null;
    const bg = getComputedStyle(document.body).backgroundColor;
    const store = (s) => { const o = {}; try { for (let i = 0; i < s.length; i++) { const k = s.key(i); o[k] = String(s.getItem(k)).slice(0, 200); } } catch (e) { o.__error = String(e); } return o; };
    return { title: document.title, canvasCount: canvases.length, mapCanvasCount: mapCanvases.length,
      attribution, attributionCandidates, bodyBackground: bg, jsCookies: (() => { try { return document.cookie; } catch (e) { return ''; } })(),
      localStorage: store(localStorage), sessionStorage: store(sessionStorage),
      xssSentinel: typeof window.__r10xss !== 'undefined' ? window.__r10xss : null,
      lang: document.documentElement.lang, textSample: document.body.innerText.slice(0, 600) };
  });
  fs.mkdirSync(OUT, { recursive: true });
  const shot = path.join(OUT, `${LABEL}-${vp.name}-${vp.width}x${vp.height}.png`);
  await page.screenshot({ path: shot, fullPage: false });
  await context.close();
  const sensitive = /(csrf|token|password|passwd|secret|bearer)/i;
  const staffCalls = requests.filter((r) => /\/api\/civic\/v1\/staff\//.test(r.url));
  const basemap = requests.filter((r) => /openfreemap|openstreetmap|tile|\.pbf|glyphs|sprite/i.test(r.url));
  const lum = (() => { const m = facts.bodyBackground.match(/\d+(\.\d+)?/g); if (!m) return null;
    const [r, g, b] = m.slice(0, 3).map(Number); return +(0.2126 * r + 0.7152 * g + 0.0722 * b).toFixed(1) / 255; })();
  return {
    viewport: vp, url: URL_, navError, loadMs, screenshot: shot, facts,
    checks: {
      U01_single_map_canvas: facts.mapCanvasCount === 1 ? 'PASS' : (facts.mapCanvasCount === 0 ? 'FAIL(no maplibre canvas)' : `FAIL(${facts.mapCanvasCount} map canvases)`),
      U01_light_background: lum === null ? 'NOT_RUN(transparent body bg)' : (lum >= 0.7 ? 'PASS' : `FAIL(luminance ${lum.toFixed(2)})`),
      U06_attribution_visible: !facts.attribution ? 'FAIL(no OSM/OpenFreeMap attribution text found)' : (facts.attribution.inViewport && facts.attribution.notCovered ? 'PASS' : 'FAIL(covered or off-screen)'),
      U06_basemap: basemap.length === 0 ? 'NOT_RUN(no basemap requests)' : (failures.some((f) => basemap.some((b) => b.url === f.url)) ? 'NOT_RUN(basemap blocked by network; check fallback in screenshot)' : 'PASS(requests succeeded)'),
      U09_no_staff_calls_public: staffCalls.length === 0 ? 'PASS' : `FAIL(${staffCalls.length} staff calls)`,
      S06_no_session_in_js_storage: [facts.jsCookies, JSON.stringify(facts.localStorage), JSON.stringify(facts.sessionStorage)].some((s) => sensitive.test(s)) ? 'REVIEW(auth-like key/value in JS-visible storage)' : 'PASS',
      S10_xss_not_executed: (facts.xssSentinel === null && dialogs.length === 0) ? 'PASS' : `FAIL(sentinel=${facts.xssSentinel}, dialogs=${dialogs.length})`,
      console_errors: consoleErrors.length === 0 ? 'PASS' : `REVIEW(${consoleErrors.length})`,
    },
    staffCalls, basemapRequests: basemap.length, failures: failures.slice(0, 40), consoleErrors: consoleErrors.slice(0, 40), dialogs,
    apiRequests: requests.filter((r) => /\/api\//.test(r.url)).map((r) => r.method + ' ' + r.url.replace(/^https?:\/\/[^/]+/, '')),
  };
}

(async () => {
  if (!URL_ || !OUT) { console.error('usage: --url URL --out DIR [--label L] [--wait ms]'); process.exit(2); }
  const browser = await chromium.launch({ executablePath: EXE, headless: true });
  const results = [];
  try {
    for (const vp of VIEWPORTS) results.push(await probe(browser, vp));
  } finally { await browser.close(); }
  const report = { label: LABEL, url: URL_, at: new Date().toISOString(), chromium: EXE, results };
  fs.writeFileSync(path.join(OUT, `${LABEL}-probe.json`), JSON.stringify(report, null, 1));
  for (const r of results) console.log(r.viewport.name, JSON.stringify(r.checks));
})().catch((e) => { console.error(e); process.exit(1); });
