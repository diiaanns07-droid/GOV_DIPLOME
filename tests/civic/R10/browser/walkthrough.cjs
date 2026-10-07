// R10 independent browser walkthrough of the civic platform (Playwright, CommonJS).
// Not R01's script: selectors come from reading the UI source (web/civic/**), checks are R10's own.
// Run through the launcher (it starts the server, creates editors via pty, serves restarts):
//   python3 -I tests/civic/R10/browser/run_walkthrough.py --code-root <checkout> --out <json> --shots <dir>
// Environment (set by the launcher): R10_BASE_URL R10_OUT_JSON R10_SHOTS R10_CODE_SHA R10_EDITOR_USER
//   R10_EDITOR_PASSWORD R10_EDITOR2_USER R10_EDITOR2_PASSWORD R10_CTL=1 (restart control on stdin/stdout).
// Passwords and session/CSRF values are never written to the report or printed.
// Skeptic revision (round 11): A07-receipt-channels (not a CONTRACT/BRIEF requirement) -> A07-receipt-visible + note;
// U04-reach also tries the mouse-only way out (collapse the diff); URL-based console classification; new graded checks
// U02-cta-contrast, U03-editor-footer, U01-modes-header. Targeted re-checks at other viewports: skeptic_r01.cjs.
'use strict';
const fs = require('fs');
const path = require('path');
const readline = require('readline');
const { chromium, request: pwRequest } = require('playwright');

const BASE = process.env.R10_BASE_URL;
const OUT = process.env.R10_OUT_JSON;
const SHOTS = process.env.R10_SHOTS;
const EXE = process.env.R10_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const ED = { user: process.env.R10_EDITOR_USER, pw: process.env.R10_EDITOR_PASSWORD };
const ED2 = { user: process.env.R10_EDITOR2_USER, pw: process.env.R10_EDITOR2_PASSWORD };
const CTL = process.env.R10_CTL === '1';
const REPO = path.resolve(__dirname, '../../../..');
const API = '/api/civic/v1';
const D = { width: 1440, height: 900 };
const M = { width: 390, height: 844 };
const vpn = (vp) => (typeof vp === 'string' ? vp : `${vp.width}x${vp.height}`);

const TITLE_XSS = 'R10 <img src=x onerror="window.__r10xss=1"> ремонт';
const TITLE = 'R10 ремонт тротуара «проверка» & синтетика';
const FB_TEXT = 'R10: тротуар перекрыт без обхода <img src=x onerror="window.__r10xss=2"> проверка формы';
const FB_XSS = '<img src=x onerror="window.__r10xss=2">';
const REPLY = 'Ответ R10: передано подрядчику <img src=x onerror="window.__r10xss=3"> спасибо';
const REPLY_XSS = '<img src=x onerror="window.__r10xss=3">';
const MOD_REASON = 'R10: проверено, персональных данных нет';
const REASON_PUB1 = 'Первая публикация: синтетическая запись R10';
const REASON_SHIFT = 'Перенос срока: подрядчик запросил неделю (R10)';
const REASON_PUB2 = 'Публикация переноса срока (R10)';
const BUMP_DESC = 'R10: описание изменено во второй вкладке (проверка конфликта)';
const BUMP_REASON = 'R10 вторая вкладка: уточнение описания';
const REASON_T = 'Перенос срока: замер времени R10';

// ------------------------------------------------------------------ report
const R = {
  code_sha: process.env.R10_CODE_SHA || null, label: process.env.R10_LABEL || null,
  started_utc: new Date().toISOString(), finished_utc: null, base_url: BASE,
  chromium: { executablePath: EXE, version: null, headless: true },
  viewports: [D, M], steps: [], timing: {}, network_staff_calls_public: [], console_errors: [],
  dialogs: [], notes: [], not_run: [], state: {},
};
function save() { if (OUT) fs.writeFileSync(OUT, JSON.stringify(R, null, 1)); }
function step(id, name, vp, status, evidence, screenshot) {
  const s = { id, name, viewport: vp ? vpn(vp) : 'n/a', status, evidence: String(evidence), screenshot: screenshot || null };
  R.steps.push(s);
  if (status === 'NOT_RUN') R.not_run.push({ id: id + (vp ? '@' + vpn(vp) : ''), reason: String(evidence) });
  console.log(`[${status}] ${id} @${s.viewport} ${name} :: ${String(evidence).slice(0, 400)}`);
  save();
  return s;
}
const note = (t) => { R.notes.push(t); console.log('NOTE ' + t); save(); };

// ------------------------------------------------------------------ restart control
let ctlWaiter = null;
const rl = CTL ? readline.createInterface({ input: process.stdin }) : null;
if (rl) rl.on('line', (l) => { if (ctlWaiter) { const w = ctlWaiter; ctlWaiter = null; w(l); } });
function ctl(cmd, timeoutMs = 150000) {
  return new Promise((resolve, reject) => {
    const t = setTimeout(() => { ctlWaiter = null; reject(new Error('control timeout')); }, timeoutMs);
    ctlWaiter = (l) => { clearTimeout(t); resolve(l); };
    process.stdout.write('R10CTL:' + cmd + '\n');
  });
}

// ------------------------------------------------------------------ browser helpers
const PAGES = [];
let DELIBERATE = 0;  // >0 while the script itself calls the API from a page (not the UI)
function instrument(page, label, role) {
  const rec = { label, role, api: [], staff: [], consoleErrors: [], dialogs: [], bad: [] };
  page.on('request', (r) => {
    const u = r.url();
    if (!u.includes(API)) return;
    const e = { t: new Date().toISOString(), m: r.method(), p: u.replace(BASE, ''), deliberate: DELIBERATE > 0 };
    rec.api.push(e);
    if (u.includes(API + '/staff')) rec.staff.push(e);
  });
  page.on('console', (m) => { if (m.type() === 'error') { const loc = (m.location() || {}).url || ''; rec.consoleErrors.push(m.text().slice(0, 300) + (loc ? ' @ ' + loc.replace(BASE, '').slice(0, 160) : '')); } });
  page.on('response', (r) => { if (r.status() >= 400) rec.bad.push(r.status() + ' ' + r.request().method() + ' ' + r.url().replace(BASE, '').slice(0, 160) + (DELIBERATE > 0 ? ' (script)' : '')); });
  page.on('pageerror', (e) => rec.consoleErrors.push('pageerror: ' + String(e).slice(0, 300)));
  page.on('dialog', async (d) => { rec.dialogs.push(d.type() + ': ' + d.message().slice(0, 200)); try { await d.dismiss(); } catch (e) { /* closed */ } });
  PAGES.push(rec);
  return rec;
}
let ACTIONS = 0;  // UI actions: clicks + fills + key presses + checks + selects
async function click(loc, o) { ACTIONS++; await loc.click(o); }
async function fill(loc, v) { ACTIONS++; await loc.fill(v); }
async function check(loc) { ACTIONS++; await loc.check(); }
async function select(loc, v) { ACTIONS++; await loc.selectOption(v); }
async function key(page, k) { ACTIONS++; await page.keyboard.press(k); }

async function shot(page, nn, name) {
  const vp = page.viewportSize();
  const file = path.join(SHOTS, `${nn}_${name}_${vp.width}x${vp.height}.png`);
  await page.screenshot({ path: file, fullPage: false });
  return path.relative(REPO, file);
}
async function waitMap(page, timeout = 40000) {
  try {
    await page.waitForFunction(() => (typeof mapReady !== 'undefined' && mapReady === true)
      || !!document.querySelector('#map-fallback:not(.hidden)'), null, { timeout });
    return true;
  } catch (e) { return false; }
}
async function waitList(page, timeout = 45000) {
  await page.waitForFunction(() => {
    const c = document.querySelector('#civic-map-root .civic-r03-count');
    return !!c && /объект/.test(c.textContent) && !document.querySelector('#civic-map-root .civic-r03-list-view .civic-r03-loading');
  }, null, { timeout });
}
async function openHome(page) {
  // via about:blank so a URL that differs only by #fragment still triggers a full load
  if (page.url() !== 'about:blank') await page.goto('about:blank');
  await page.goto(BASE + '/', { waitUntil: 'domcontentloaded' });
  const ok = await waitMap(page);
  await waitList(page);
  return ok;
}
async function openObject(page, id, title) {
  if (page.url() !== 'about:blank') await page.goto('about:blank');
  await page.goto(BASE + '/#object=' + encodeURIComponent(id), { waitUntil: 'domcontentloaded' });
  await waitMap(page);
  await waitCard(page, title);
}
async function waitCard(page, title, timeout = 30000) {
  await page.waitForFunction((t) => {
    const card = document.querySelector('#civic-map-root .civic-r03-card');
    if (!card || card.hidden) return false;
    const h = card.querySelector('.civic-r03-card-title');
    if (!h || card.querySelector('.civic-r03-loading')) return false;
    return t ? h.textContent === t : true;
  }, title || null, { timeout });
}
async function cardFacts(page) {
  return page.evaluate(() => {
    const card = document.querySelector('#civic-map-root .civic-r03-card');
    if (!card || card.hidden) return null;
    const dl = {};
    card.querySelectorAll('dt').forEach((dt) => { const dd = dt.nextElementSibling; dl[dt.textContent.trim()] = dd ? dd.innerText.trim() : null; });
    const vis = (el) => { if (!el) return false; const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
    const banner = card.querySelector('.civic-r03-banner');
    return {
      title: card.querySelector('.civic-r03-card-title') ? card.querySelector('.civic-r03-card-title').textContent : null,
      text: card.innerText, dl,
      banners: [...card.querySelectorAll('.civic-r03-banner')].map((b) => b.innerText.trim()),
      bannerVisible: vis(banner),
      shift: card.querySelector('.civic-r03-shift') ? card.querySelector('.civic-r03-shift').innerText.trim() : null,
      history: [...card.querySelectorAll('.civic-r03-history li')].map((li) => li.innerText.trim()),
      sources: (() => { const h4 = [...card.querySelectorAll('h4')].find((x) => x.textContent === 'Источники'); return h4 ? h4.parentElement.innerText.trim() : null; })(),
      hash: location.hash,
    };
  });
}
async function mapHasObject(page, id) {
  return page.evaluate((oid) => {
    try {
      const src = map.getSource('civic-r03-objects');
      if (!src) return { source: false };
      const data = src.serialize().data;
      const feats = (data && data.features) || [];
      return { source: true, features: feats.length, has: feats.some((f) => f.properties && f.properties.cid === oid) };
    } catch (e) { return { error: String(e) }; }
  }, id);
}
async function pageFetch(page, method, p, body, withCsrf) {
  DELIBERATE++;
  try {
    return await page.evaluate(async ({ method, p, body, withCsrf }) => {
      const headers = { Accept: 'application/json' };
      if (withCsrf) {
        const s = await (await fetch('/api/civic/v1/session', { headers, credentials: 'same-origin', cache: 'no-store' })).json();
        if (s && s.data && s.data.csrf_token) headers['X-CSRF-Token'] = s.data.csrf_token;
      }
      if (body !== null && body !== undefined) headers['Content-Type'] = 'application/json';
      const r = await fetch('/api/civic/v1' + p, { method, headers, credentials: 'same-origin', cache: 'no-store',
        body: body === null || body === undefined ? undefined : JSON.stringify(body) });
      let j = null;
      try { j = await r.json(); } catch (e) { j = null; }
      return { status: r.status, json: j };
    }, { method, p, body: body === undefined ? null : body, withCsrf: !!withCsrf });
  } finally { DELIBERATE--; }
}
const strip = (s) => String(s || '').replace(/\s+/g, ' ').trim();
// WCAG contrast ratio of two rgb()/rgba() colours (alpha ignored)
function contrast(c1, c2) {
  const L = (c) => { const m = String(c).match(/[\d.]+/g); if (!m) return null; const [r, g, b] = m.slice(0, 3).map((v) => { v = Number(v) / 255; return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
  const a = L(c1), b = L(c2); if (a === null || b === null) return null;
  return +((Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)).toFixed(2);
}
function lumOf(color) {
  if (!color) return null;
  let r, g, b, a = 1;
  const hex = /^#([0-9a-f]{6})$/i.exec(color.trim());
  if (hex) { const n = parseInt(hex[1], 16); r = n >> 16; g = (n >> 8) & 255; b = n & 255; }
  else { const m = color.match(/[\d.]+/g); if (!m || m.length < 3) return null; [r, g, b] = m.slice(0, 3).map(Number); if (m.length > 3) a = Number(m[3]); }
  if (a === 0) return null;
  return +((0.2126 * r + 0.7152 * g + 0.0722 * b) / 255).toFixed(3);
}

// ------------------------------------------------------------------ scenario
async function main() {
  if (!BASE || !OUT || !SHOTS) throw new Error('R10_BASE_URL, R10_OUT_JSON, R10_SHOTS are required');
  fs.mkdirSync(SHOTS, { recursive: true });
  const browser = await chromium.launch({ executablePath: EXE, headless: true });
  R.chromium.version = browser.version();
  const newCtx = (vp, extra) => browser.newContext(Object.assign({ viewport: vp, deviceScaleFactor: 1,
    isMobile: vp.width < 500, hasTouch: vp.width < 500, locale: 'ru-RU' }, extra || {}));
  const S = {};  // scenario state
  R.state = S;
  const guard = async (id, name, vp, fn) => {
    try { await fn(); } catch (e) {
      const msg = String(e && e.message ? e.message : e).split('\n')[0].slice(0, 400);
      step(id, name, vp, 'FAIL', 'step aborted: ' + msg + ' (see rerun note for reproducibility)');
    }
  };

  // ============ U01 / U09: public page at both sizes
  const resD = await newCtx(D); const rD = await resD.newPage(); const recRD = instrument(rD, 'resident-desktop', 'resident');
  const resM = await newCtx(M); const rM = await resM.newPage(); const recRM = instrument(rM, 'resident-mobile', 'resident');
  for (const [page, vp, rec] of [[rD, D, recRD], [rM, M, recRM]]) {
    await guard('U01', 'city mode default, one map canvas, light background', vp, async () => {
      const mapOk = await openHome(page);
      await page.waitForTimeout(1500);
      const f = await page.evaluate(() => ({
        bodyClass: document.body.className,
        modes: [...document.querySelectorAll('#civic-modes [data-mode]')].map((b) => ({ mode: b.dataset.mode, label: b.textContent.trim(), pressed: b.getAttribute('aria-pressed'), title: b.title })),
        mapCanvases: document.querySelectorAll('canvas.maplibregl-canvas').length, canvases: document.querySelectorAll('canvas').length,
        bgs: ['html', 'body'].map((s) => getComputedStyle(document.querySelector(s)).backgroundColor),
        mapBg: (() => { try { const l = map.getStyle().layers.find((x) => x.type === 'background'); return l && l.paint ? l.paint['background-color'] : null; } catch (e) { return null; } })(),
        rootVisible: !document.getElementById('civic-root').hidden, h1: (document.querySelector('#civic-panel h1') || {}).textContent,
        sidebarVisible: !!(document.querySelector('.sidebar') && document.querySelector('.sidebar').offsetParent),
        title: document.title,
      }));
      const civic = f.modes.find((m) => m.mode === 'civic');
      const bgL = f.bgs.map(lumOf).find((x) => x !== null);
      const mapL = lumOf(typeof f.mapBg === 'string' ? f.mapBg : null);
      const light = (bgL === undefined || bgL === null || bgL >= 0.7) && (mapL === null || mapL >= 0.7);
      const ok = civic && civic.pressed === 'true' && /civic-mode/.test(f.bodyClass) && f.rootVisible && f.mapCanvases === 1 && light && !f.sidebarVisible;
      const sh = await shot(page, '01', 'home');
      step('U01', 'city mode default, one map canvas, light background', vp, ok ? 'PASS' : 'FAIL',
        `mode civic pressed=${civic && civic.pressed}; body="${f.bodyClass}"; civic panel h1="${f.h1}"; maplibre canvases=${f.mapCanvases} (all canvases ${f.canvases}); bg html/body=${f.bgs.join(' / ')} lum=${bgL}; map background ${f.mapBg} lum=${mapL}; training sidebar visible=${f.sidebarVisible}; mapReady=${mapOk}; modes=${f.modes.map((m) => m.label + '[' + m.title + ']').join(', ')}`, sh);
    });
    step('U09', 'no /staff/* requests from the public page before login', vp,
      rec.staff.length === 0 ? 'PASS' : 'FAIL',
      `api requests during load: ${rec.api.map((e) => e.m + ' ' + e.p).join(', ') || 'none'}; staff requests: ${rec.staff.length}`);
  }

  // ============ U01b: training / school modes are reachable, separate and labelled (desktop)
  await guard('U01-modes', 'training model / school modes reachable, separate, labelled', D, async () => {
    const mc = await newCtx(D); const p = await mc.newPage(); instrument(p, 'modes-desktop', 'resident');
    await openHome(p);
    const read = () => p.evaluate(() => ({
      bodyClass: document.body.className, civicVisible: !document.getElementById('civic-root').hidden,
      pressed: [...document.querySelectorAll('#civic-modes [data-mode]')].filter((b) => b.getAttribute('aria-pressed') === 'true').map((b) => b.textContent.trim()),
      brand: (document.querySelector('.brand-title') || {}).textContent, metricNote: (document.getElementById('map-metric-note') || {}).textContent,
      sidebar: !!(document.querySelector('.sidebar') && document.querySelector('.sidebar').offsetParent),
      govtech: !!(window.GOVTECH && window.GOVTECH.active), canvases: document.querySelectorAll('canvas.maplibregl-canvas').length,
      visibleText: document.body.innerText.slice(0, 300).replace(/\s+/g, ' '),
    }));
    await click(p.locator('#civic-modes [data-mode="training"]'));
    await p.waitForFunction(() => !document.body.classList.contains('civic-mode'));
    await p.waitForTimeout(800);
    const tr = await read();
    const shT = await shot(p, '02', 'training_mode');
    // header text must stay inside the header bar (round-11 skeptic addition: 02_training_mode showed clipped text)
    const hdr = await p.evaluate(() => { const top = document.querySelector('.topbar').getBoundingClientRect(); const c = document.querySelector('.top-center');
      const kids = [...c.children].map((k) => { const r = k.getBoundingClientRect(); return { text: k.textContent.replace(/\s+/g, ' ').trim().slice(0, 50), top: Math.round(r.top), bottom: Math.round(r.bottom) }; });
      return { bar: [Math.round(top.top), Math.round(top.bottom)], width: Math.round(c.getBoundingClientRect().width), kids, outside: kids.filter((k) => k.top < top.top - 1 || k.bottom > top.bottom + 1) }; });
    step('U01-modes-header', 'training-mode header text stays inside the header bar at 1440x900', D, hdr.outside.length ? 'FAIL' : 'PASS',
      `header bar y=${hdr.bar}; .top-center width ${hdr.width}px; children: ${hdr.kids.map((k) => `"${k.text}" y=${k.top}..${k.bottom}`).join('; ')}; outside the bar: ${hdr.outside.length} (text above the page top is cut off)`, shT);
    await click(p.locator('#civic-modes [data-mode="school"]'));
    await p.waitForTimeout(1500);
    const sc = await read();
    const shS = await shot(p, '03', 'school_mode');
    await click(p.locator('#civic-modes [data-mode="civic"]'));
    await p.waitForFunction(() => document.body.classList.contains('civic-mode') && !document.getElementById('civic-root').hidden);
    const back = await read();
    const ok = !tr.civicVisible && tr.sidebar && tr.pressed.join() === 'Учебная модель' && tr.canvases === 1
      && !sc.civicVisible && sc.pressed.join() === 'Школы' && sc.canvases === 1 && back.civicVisible && back.canvases === 1;
    step('U01-modes', 'training model / school modes reachable, separate, labelled', D, ok ? 'PASS' : 'FAIL',
      `training: civic panel hidden=${!tr.civicVisible}, simulator sidebar shown=${tr.sidebar}, pressed="${tr.pressed}", brand="${strip(tr.brand)}", note="${strip(tr.metricNote)}"; school: civic hidden=${!sc.civicVisible}, GOVTECH active=${sc.govtech}, pressed="${sc.pressed}"; back to city: civic panel visible=${back.civicVisible}; one maplibre canvas in every mode=${[tr, sc, back].every((x) => x.canvases === 1)}`, [shT, shS]);
    await mc.close();
  });

  // ============ E1: editor logs in through the form and creates a draft through the form
  const edD = await newCtx(D); const eD = await edD.newPage(); const recED = instrument(eD, 'editor-desktop', 'editor');
  const ed = (sel) => eD.locator('#civic-editor ' + sel);
  let createBody = null;
  eD.on('request', (r) => {
    if (r.method() !== 'POST') return;
    if (r.url().endsWith(API + '/staff/objects')) { try { createBody = JSON.parse(r.postData()); } catch (e) { createBody = null; } }
    if (/\/staff\/objects\/[^/]+\/update$/.test(r.url())) { try { const b = JSON.parse(r.postData()); S.updateChangeKeys = Object.keys(b.changes || {}).join('+'); S.updateBodies = (S.updateBodies || []).concat([{ changes: b.changes, reason: b.reason, expected_revision: b.expected_revision }]); } catch (e) { /* ignore */ } }
  });
  await guard('E1-login', 'editor opens staff UI and logs in via the form', D, async () => {
    await openHome(eD);
    await click(eD.locator('#civic-staff-button'));
    await ed('input[name="username"]').waitFor({ timeout: 15000 });
    const staffBefore = recED.staff.filter((e) => !e.deliberate).length;
    const sh = await shot(eD, '04', 'staff_login');
    step('U09-staff-ui', 'opening the staff UI makes no /staff/* call before login', D, staffBefore === 0 ? 'PASS' : 'FAIL',
      `API calls so far: ${recED.api.map((e) => e.m + ' ' + e.p).join(', ')}`, sh);
    await fill(ed('input[name="username"]'), ED.user);
    await fill(ed('input[name="password"]'), ED.pw);
    const [resp] = await Promise.all([
      eD.waitForResponse((r) => r.url().endsWith(API + '/session/login'), { timeout: 20000 }),
      click(ed('button[type="submit"]')),
    ]);
    await ed('[data-fk="new"]').waitFor({ timeout: 15000 });
    const who = strip(await ed('.civic-r04-who').innerText().catch(() => ''));
    const pwLeft = await ed('input[type="password"]').count();
    step('E1-login', 'editor opens staff UI and logs in via the form', D, resp.status() === 200 ? 'PASS' : 'FAIL',
      `button "Для сотрудников" -> drawer "Кабинет сотрудника" -> login form; POST /session/login ${resp.status()}; header: "${who}"; password inputs left in DOM=${pwLeft}`);
  });

  await guard('E1-form', 'create draft through the form (XSS title attempt, then plain title)', D, async () => {
    await click(ed('[data-fk="new"]'));
    await ed('[data-fk="title"]').waitFor({ timeout: 10000 });
    const ta = await eD.evaluate(() => [...document.querySelectorAll('#civic-editor textarea')].map((t) => {
      const lab = t.id ? document.querySelector('label[for="' + CSS.escape(t.id) + '"]') : null;
      const help = (t.getAttribute('aria-describedby') || '').split(' ').map((i) => document.getElementById(i)).filter(Boolean).map((x) => x.textContent).join(' ');
      return { key: t.getAttribute('data-fk'), label: lab ? lab.textContent : null, placeholder: t.placeholder, help: help.slice(0, 160) };
    }));
    const jsonTa = ta.filter((t) => /json|\{|\[/i.test([t.label, t.placeholder, t.help].join(' ')));
    step('E1-nojson', 'draft form has no raw-JSON textarea', D, jsonTa.length === 0 ? 'PASS' : 'FAIL',
      `textareas in the new-object form: ${ta.map((t) => `${t.key} ("${t.label}")`).join('; ')}; expecting JSON: ${jsonTa.length}`);
    // XSS title attempt
    const postsBefore = recED.api.filter((e) => e.m === 'POST' && e.p === API + '/staff/objects').length;
    await fill(ed('[data-fk="title"]'), TITLE_XSS);
    await select(ed('select[data-fk="kind"]'), 'roadworks');
    await select(ed('select[data-fk="status"]'), 'planned');
    await fill(ed('[data-fk="planned_start"]'), '2026-10-14');
    await fill(ed('[data-fk="original_planned_end"]'), '2026-10-20');
    await fill(ed('[data-fk="current_planned_end"]'), '2026-10-20');
    await fill(ed('[data-fk="geometry"]'), '51.12825');
    await fill(ed('[data-fk="geo-lon"]'), '71.43042');
    await click(ed('[data-fk="geo-apply"]'));
    await check(ed('[data-fk="geometry_confirmed"]'));
    await check(ed('input[type="radio"][value="synthetic"]'));
    await click(ed('[data-fk="save"]'));
    await eD.waitForTimeout(1500);
    const postsAfter = recED.api.filter((e) => e.m === 'POST' && e.p === API + '/staff/objects').length;
    const titleErr = strip(await eD.evaluate(() => { const i = document.querySelector('#civic-editor [data-fk="title"]'); const e = i && document.getElementById(i.id + '-err'); return e ? e.textContent : ''; }));
    const kept = await ed('[data-fk="title"]').inputValue();
    const sh = await shot(eD, '05', 'xss_title_rejected');
    step('E1-xss-title', 'title with XSS payload via the form', D,
      postsAfter === postsBefore && /HTML/.test(titleErr) && kept === TITLE_XSS ? 'PASS' : 'FAIL',
      `form refused before sending (POST /staff/objects sent: ${postsAfter - postsBefore}); field error: "${titleErr}"; typed title kept in the field: ${kept === TITLE_XSS}. Consequence: an HTML-bearing title cannot be stored, so S10 for the title is covered by rejection, not by rendering`, sh);
    // plain title -> draft
    await fill(ed('[data-fk="title"]'), TITLE);
    const [resp] = await Promise.all([
      eD.waitForResponse((r) => r.request().method() === 'POST' && r.url().endsWith(API + '/staff/objects'), { timeout: 20000 }),
      click(ed('[data-fk="save"]')),
    ]);
    const j = await resp.json().catch(() => null);
    S.id = j && j.data && j.data.item ? j.data.item.id : null;
    S.revAfterCreate = j && j.data && j.data.item ? j.data.item.revision : null;
    await ed('.civic-r04-msg').first().waitFor({ timeout: 10000 });
    const msg = strip(await ed('.civic-r04-msg').first().innerText());
    const meta = strip(await ed('.civic-r04-meta').first().innerText().catch(() => ''));
    const sh2 = await shot(eD, '06', 'draft_created');
    const fieldsSent = createBody ? Object.keys(createBody).join(',') : 'n/a';
    step('E1', 'draft created through the form (roadworks, 2026-10-14..2026-10-20, synthetic)', D,
      resp.status() < 300 && S.id && createBody && createBody.kind === 'roadworks' && createBody.evidence_type === 'synthetic' ? 'PASS' : 'FAIL',
      `POST /staff/objects ${resp.status()} id=${S.id} rev=${S.revAfterCreate}; body keys sent by the form: ${fieldsSent}; kind=${createBody && createBody.kind}, schedule=${createBody && JSON.stringify(createBody.schedule)}, evidence=${createBody && createBody.evidence_type}; notice: "${msg}"; meta: "${meta}"`, sh2);
  });

  // second editor "tab": same session cookie, used for direct API calls (server-side checks, conflict)
  const ctx2 = await browser.newContext({ storageState: await edD.storageState(), viewport: D });
  const p2 = await ctx2.newPage(); instrument(p2, 'editor-tab2-api', 'editor');
  await p2.goto(BASE + '/favicon.svg');
  await guard('S10-server-title', 'server also rejects an HTML title (direct API, editor session)', 'api', async () => {
    if (!createBody) { step('S10-server-title', 'server also rejects an HTML title', 'api', 'NOT_RUN', 'no captured form body'); return; }
    const body = JSON.parse(JSON.stringify(createBody)); body.title = TITLE_XSS;
    const r = await pageFetch(p2, 'POST', '/staff/objects', body, true);
    const err = r.json && r.json.error ? `${r.json.error.code}: ${JSON.stringify(r.json.error.fields || {})}` : '';
    S.serverAcceptedXssTitle = r.status < 300 ? (r.json.data.item.id) : null;
    step('S10-server-title', 'server also rejects an HTML title (direct API, editor session)', 'api', r.status === 422 || r.status === 400 ? 'PASS' : 'FAIL',
      `POST /staff/objects with the form body but title=${JSON.stringify(TITLE_XSS)} -> ${r.status} ${err.slice(0, 200)}`);
  });

  // mobile staff UI (second editor) — screenshots and layout
  await guard('E-mobile', 'staff UI at 390x844', M, async () => {
    const edM = await newCtx(M); const eM = await edM.newPage(); instrument(eM, 'editor-mobile', 'editor');
    await openHome(eM);
    await click(eM.locator('#civic-staff-button'));
    await eM.locator('#civic-editor input[name="username"]').waitFor({ timeout: 15000 });
    const shL = await shot(eM, '04', 'staff_login');
    await fill(eM.locator('#civic-editor input[name="username"]'), ED2.user);
    await fill(eM.locator('#civic-editor input[name="password"]'), ED2.pw);
    await click(eM.locator('#civic-editor button[type="submit"]'));
    await eM.locator('#civic-editor [data-fk="new"]').waitFor({ timeout: 15000 });
    await click(eM.locator('#civic-editor [data-fk="filter-all"]'));
    await eM.waitForTimeout(500);
    const f = await eM.evaluate(() => {
      const d = document.getElementById('civic-editor').getBoundingClientRect();
      return { sw: document.documentElement.scrollWidth, iw: innerWidth, drawer: [d.left, d.top, d.width, d.height].map(Math.round),
        rows: document.querySelectorAll('#civic-editor .civic-r04-row').length, desktopOnly: /только на компьютере|desktop only|для компьютера/i.test(document.getElementById('civic-editor').innerText) };
    });
    const shList = await shot(eM, '04b', 'staff_list');
    step('E-mobile', 'staff UI usable at 390x844 (login + list)', M, f.sw <= f.iw + 1 && f.rows >= 1 ? 'PASS' : 'FAIL',
      `drawer rect [l,t,w,h]=${f.drawer}; scrollWidth=${f.sw} innerWidth=${f.iw}; rows listed=${f.rows}; UI declares desktop-only=${f.desktopOnly}; editor flow itself was run at 1440x900`, [shL, shList]);
    await edM.close();
  });

  // ============ A02: draft not visible to residents (list, map, deep link, API)
  for (const vp of [D, M]) {
    await guard('A02', 'draft invisible to a fresh resident (list/map/deep link)', vp, async () => {
      if (!S.id) throw new Error('no draft id');
      const c = await newCtx(vp); const p = await c.newPage(); const rec = instrument(p, 'resident-fresh-a02-' + vpn(vp), 'resident');
      await openHome(p);
      const inList = await p.evaluate((t) => document.querySelector('#civic-map-root .civic-r03-list') ? document.querySelector('#civic-map-root .civic-r03-list').innerText.includes(t) : false, TITLE);
      const byId = await p.locator(`#civic-map-root [data-id="${S.id}"]`).count();
      const mp = await mapHasObject(p, S.id);
      const p3 = await c.newPage(); const rec3 = instrument(p3, 'resident-fresh-a02-deeplink-' + vpn(vp), 'resident');
      await p3.goto(BASE + '/#object=' + encodeURIComponent(S.id), { waitUntil: 'domcontentloaded' });
      await waitMap(p3);
      await waitCard(p3, null, 30000);
      const cf = await cardFacts(p3);
      const api = await pageFetch(p3, 'GET', '/objects/' + encodeURIComponent(S.id));
      const sh = await shot(p3, '07', 'draft_deeplink_notfound');
      const ok = !inList && byId === 0 && mp.has === false && cf && cf.title === 'Объект не найден' && !cf.text.includes(TITLE) && api.status === 404;
      step('A02', 'draft invisible to a fresh resident (list/map/deep link)', vp, ok ? 'PASS' : 'FAIL',
        `list contains title=${inList}, list item by id=${byId}, map source features=${mp.features} has id=${mp.has}; deep link ${'/#object=' + S.id} -> card "${cf && cf.title}" (${strip(cf && cf.text).slice(0, 120)}), contains draft title=${cf ? cf.text.includes(TITLE) : 'n/a'}; GET ${API}/objects/{id} -> ${api.status}; staff calls=${rec.staff.length + rec3.staff.length}`, sh);
      await c.close();
    });
  }

  // ============ E2: publish via UI; resident sees it; U02 card content
  await guard('E2', 'publish via the editor UI', D, async () => {
    await click(ed('[data-fk="publish"]'));
    await ed('[data-fk="reason"]').waitFor({ timeout: 10000 });
    await fill(ed('[data-fk="reason"]'), REASON_PUB1);
    const [resp] = await Promise.all([
      eD.waitForResponse((r) => r.request().method() === 'POST' && /\/staff\/objects\/[^/]+\/publish$/.test(r.url()), { timeout: 20000 }),
      click(ed('[data-fk="confirm"]')),
    ]);
    await eD.waitForFunction(() => [...document.querySelectorAll('#civic-editor .civic-r04-msg')].some((m) => /Опубликовано/.test(m.textContent)), null, { timeout: 15000 });
    const msg = strip(await eD.evaluate(() => [...document.querySelectorAll('#civic-editor .civic-r04-msg')].map((m) => m.innerText).join(' | ')));
    step('E2', 'publish via the editor UI (button "Опубликовать…" + reason + confirm)', D, resp.status() === 200 ? 'PASS' : 'FAIL',
      `POST .../publish ${resp.status()}; notice: "${msg}"`);
  });
  for (const [page, vp, rec] of [[rD, D, recRD], [rM, M, recRM]]) {
    await guard('E2-resident', 'resident sees the published object in list and map', vp, async () => {
      await openHome(page);
      const item = page.locator(`#civic-map-root [data-r03-action="select"][data-id="${S.id}"]`);
      const n = await item.count();
      const itemText = n ? strip(await item.innerText()) : '';
      const mp = await mapHasObject(page, S.id);
      step('E2-resident', 'resident (reload) sees the published object in list and map', vp, n === 1 && mp.has === true && itemText.includes(TITLE) ? 'PASS' : 'FAIL',
        `list item by id=${n} text="${itemText}"; map source has feature cid=${S.id}: ${mp.has} (features=${mp.features})`);
      await click(item);
      await waitCard(page, TITLE);
      const cf = await cardFacts(page);
      const sh = await shot(page, '08', 'published_card');
      const dl = cf.dl;
      const budget = dl['Стоимость'] || '';
      const checks = {
        deadline: dl['Текущий срок'] === '20 октября 2026',
        responsible: /нет данных|не указан/i.test(dl['Организация'] || ''),
        source: cf.banners.some((b) => /Демо|синтетическ/i.test(b)) && cf.bannerVisible,
        budget: !/(^|\s)0\s*₸/.test(budget) && /нет данных|неизвестно/i.test(budget),
      };
      step('U02', 'card: current deadline, responsible, source/demo label, unknown budget not 0', vp, Object.values(checks).every(Boolean) ? 'PASS' : 'FAIL',
        `Текущий срок="${dl['Текущий срок']}", Начало="${dl['Начало по плану']}", Организация="${dl['Организация']}", Стоимость="${strip(budget)}", banner on card="${cf.banners.join(' | ')}" (visible=${cf.bannerVisible}), Источники="${strip(cf.sources).slice(0, 90)}", checks=${JSON.stringify(checks)}`, sh);
      if (vp === M) {
        const f = await page.evaluate(() => {
          const p = document.getElementById('civic-panel').getBoundingClientRect();
          const card = document.querySelector('#civic-map-root .civic-r03-card');
          const c = card.getBoundingClientRect();
          return { sw: document.documentElement.scrollWidth, iw: innerWidth, ih: innerHeight, sheet: document.getElementById('civic-panel').dataset.sheet,
            panel: [p.left, p.top, p.width, p.height, p.bottom].map(Math.round), cardTop: Math.round(c.top), cardInPanel: c.top >= p.top - 1 };
        });
        const ok = f.sw <= f.iw + 1 && f.panel[0] === 0 && Math.abs(f.panel[4] - f.ih) <= 1 && f.panel[2] === f.iw && f.panel[1] > f.ih * 0.3 && f.cardInPanel;
        step('U03', 'mobile: card opens in a bottom sheet, no horizontal scroll', M, ok ? 'PASS' : 'FAIL',
          `panel [left,top,width,height,bottom]=${f.panel} of viewport ${f.iw}x${f.ih}; data-sheet=${f.sheet}; card inside sheet (top ${f.cardTop}); scrollWidth=${f.sw} <= innerWidth+1=${f.iw + 1}`, sh);
      }
      // (after U03: scrolling the CTA into view moves the card inside the sheet) the card's call to action must be legible, not only present in the DOM (round-11 skeptic addition)
      {
        const cta = page.locator('#civic-map-root [data-r03-action="feedback"]');
        await cta.scrollIntoViewIfNeeded();
        if (vp === D) await page.mouse.move(1000, 600);
        await page.waitForTimeout(250);
        const st = await page.evaluate(() => { const b = document.querySelector('#civic-map-root [data-r03-action="feedback"]'); const cs = getComputedStyle(b); const svg = b.querySelector('svg');
          return { label: b.textContent.trim(), color: cs.color, background: cs.backgroundColor, hover: b.matches(':hover'), icon: svg ? getComputedStyle(svg).stroke : null }; });
        const bb = await cta.boundingBox();
        const file = path.join(SHOTS, `08b_card_cta_${vpn(vp)}.png`);
        await page.screenshot({ path: file, clip: { x: Math.max(0, bb.x - 12), y: Math.max(0, bb.y - 40), width: Math.min(bb.width + 24, vp.width), height: bb.height + 60 } });
        const ratio = contrast(st.color, st.background);
        step('U02-cta-contrast', 'card button "Задать вопрос по объекту" is legible (WCAG 1.4.3 >= 4.5:1)', vp, ratio !== null && ratio >= 4.5 ? 'PASS' : 'FAIL',
          `label="${st.label}"; computed color=${st.color} on background=${st.background} -> contrast ${ratio}:1 (hover=${st.hover}); icon stroke=${st.icon}; cause: ".civic-r03-root button { color: inherit }" (0,1,1) overrides ".civic-r03-btn-primary { color: #fff }" (0,1,0) in web/civic/map/civic-map.css`, path.relative(REPO, file));
      }
    });
  }

  // ============ E3 + U04: date change with reason; provoke a conflict from a second tab
  await guard('E3', 'editor changes current_planned_end to 2026-10-27 with a reason (+ conflict)', D, async () => {
    await ed('[data-fk="current_planned_end"]').waitFor({ timeout: 10000 });
    const tE0 = Date.now();
    await fill(ed('[data-fk="current_planned_end"]'), '2026-10-27');
    await ed('[data-fk="reason"]').waitFor({ timeout: 10000 });
    S.updateHint = strip(await eD.evaluate(() => { const r = document.querySelector('#civic-editor .civic-r04-reason'); return r ? r.querySelector('.civic-r04-help').textContent + ' / label: ' + r.querySelector('label').textContent : ''; }));
    await fill(ed('[data-fk="reason"]'), REASON_SHIFT);
    // second tab bumps the revision through the API with the same editor session
    const cur = await pageFetch(p2, 'GET', '/staff/objects/' + encodeURIComponent(S.id));
    const rev0 = cur.json && cur.json.data ? cur.json.data.item.revision : null;
    const bump = await pageFetch(p2, 'POST', '/staff/objects/' + encodeURIComponent(S.id) + '/update',
      { expected_revision: rev0, changes: { description: BUMP_DESC }, reason: BUMP_REASON }, true);
    const rev1 = bump.json && bump.json.data && bump.json.data.item ? bump.json.data.item.revision : null;
    await click(ed('[data-fk="save"]'));
    let conflictText = '';
    try {
      await ed('[aria-label="Конфликт версий"]').waitFor({ timeout: 15000 });
      conflictText = strip(await ed('[aria-label="Конфликт версий"]').innerText());
    } catch (e) { conflictText = ''; }
    const dateKept = await ed('[data-fk="current_planned_end"]').inputValue();
    const reasonKept = await ed('[data-fk="reason"]').inputValue().catch(() => '(reason field gone)');
    const notice = strip(await ed('.civic-r04-msg-error').first().innerText().catch(() => ''));
    const shC = await shot(eD, '09', 'conflict');
    step('U04', 'stale form save -> conflict message, typed values kept', D,
      bump.status === 200 && conflictText && dateKept === '2026-10-27' && reasonKept === REASON_SHIFT ? 'PASS' : 'FAIL',
      `tab2 API update rev ${rev0}->${rev1} (status ${bump.status}); stale save -> conflict box: "${conflictText.slice(0, 260)}"; notice: "${notice.slice(0, 120)}"; date field still "${dateKept}", reason still "${reasonKept}"`, shC);
    // can a pointer user reach the conflict panel's "move my edits" button? (actionability + elementFromPoint)
    let rebased = false, rebaseHow = 'n/a';
    if (await ed('[data-fk="rebase"]').count()) {
      const geo = await eD.evaluate(() => {
        const b = document.querySelector('#civic-editor [data-fk="rebase"]');
        const body = document.querySelector('#civic-editor .civic-r04-body');
        const act = document.querySelector('#civic-editor .civic-r04-actions');
        const probe = () => { const r = b.getBoundingClientRect(); const t = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
          return { rect: [r.left, r.top, r.width, r.height].map(Math.round), top: !t ? 'none' : (t === b || b.contains(t)) ? 'the button itself' : t.closest('.civic-r04-actions') ? 'sticky action bar .civic-r04-actions' : t.tagName.toLowerCase() + '.' + t.className }; };
        const focused = document.activeElement === b;
        b.scrollIntoView({ block: 'center' });
        const centred = probe();
        body.scrollTop = 0;
        const atTop = probe();
        const br = body.getBoundingClientRect(), ar = act.getBoundingClientRect();
        return { focused, centred, atTop, body: { top: Math.round(br.top), height: Math.round(br.height) }, actions: { top: Math.round(ar.top), height: Math.round(ar.height), css: getComputedStyle(act).position + ', max-height ' + getComputedStyle(act).maxHeight } };
      });
      let pointerOk = true;
      try { await ed('[data-fk="rebase"]').click({ trial: true, timeout: 5000 }); } catch (e) { pointerOk = false; }
      const shR = await shot(eD, '09b', 'conflict_panel_reach');
      // mouse-only way out: collapse the "Изменения: … было / станет" <details> in the action bar, then try again
      let collapsed = false, pointerAfterCollapse = null, barAfter = null;
      if (!pointerOk) {
        const sum = ed('.civic-r04-actions details.civic-r04-diff > summary');
        if (await sum.count()) {
          try { await click(sum, { timeout: 4000 }); collapsed = !(await eD.evaluate(() => !!document.querySelector('#civic-editor .civic-r04-actions details.civic-r04-diff[open]'))); } catch (e) { collapsed = false; }
          await eD.waitForTimeout(300);
          barAfter = await eD.evaluate(() => { const a = document.querySelector('#civic-editor .civic-r04-actions').getBoundingClientRect(); const b = document.querySelector('#civic-editor .civic-r04-body').getBoundingClientRect(); return `action bar height ${Math.round(a.height)}px vs body ${Math.round(b.height)}px`; });
          pointerAfterCollapse = true;
          try { await ed('[data-fk="rebase"]').click({ trial: true, timeout: 5000 }); } catch (e) { pointerAfterCollapse = false; }
        }
      }
      step('U04-reach', 'conflict panel action ("Перенести мои правки…") reachable by pointer', D, pointerOk ? 'PASS' : 'FAIL',
        `Playwright actionability (trial click) ok=${pointerOk}; button focused by the UI=${geo.focused}; after scrollIntoView top element at its centre: ${geo.centred.top} (rect ${geo.centred.rect}); with the drawer body scrolled to top: ${geo.atTop.top}; drawer body top=${geo.body.top} height=${geo.body.height}px vs action bar top=${geo.actions.top} height=${geo.actions.height}px (${geo.actions.css}) — the whole conflict panel (what changed on the server) is under the bar; notice text says versions are compared "ниже" (below) while the panel is above; mouse-only workaround: collapse the diff <details> (clicked=${collapsed}${barAfter ? ', ' + barAfter : ''}) -> pointer reach after collapse=${pointerAfterCollapse} (a ~40px strip above the bar; not discoverable); keyboard: focus is already on the button, Enter works. Other sizes: see skeptic_rechecks K-U04-reach (1366x768 and 390x844: no pointer/touch path even after collapsing)`, shR);
      if (pointerOk) { await click(ed('[data-fk="rebase"]')); rebaseHow = 'mouse click'; }
      else if (pointerAfterCollapse) { await click(ed('[data-fk="rebase"]')); rebaseHow = 'mouse click after collapsing the diff (direct click was blocked)'; }
      else { await ed('[data-fk="rebase"]').focus(); await key(eD, 'Enter'); rebaseHow = 'keyboard (focus + Enter): pointer click impossible'; }
      rebased = true;
    }
    const reasonAfterRebase = await ed('[data-fk="reason"]').inputValue().catch(() => '');
    if (!reasonAfterRebase) await fill(ed('[data-fk="reason"]'), REASON_SHIFT);
    const [resp] = await Promise.all([
      eD.waitForResponse((r) => r.request().method() === 'POST' && /\/staff\/objects\/[^/]+\/update$/.test(r.url()), { timeout: 20000 }),
      click(ed('[data-fk="save"]')),
    ]);
    const uj = await resp.json().catch(() => null);
    const pend = uj && uj.data && uj.data.item && uj.data.item.staff ? uj.data.item.staff.has_unpublished_changes : null;
    await eD.waitForTimeout(800);
    let pub = null;
    const pubBtn = ed('[data-fk="publish"]');
    if (await pubBtn.count() && await pubBtn.isEnabled()) {
      await click(pubBtn);
      await ed('[data-fk="reason"]').waitFor({ timeout: 10000 });
      await fill(ed('[data-fk="reason"]'), REASON_PUB2);
      const [pr] = await Promise.all([
        eD.waitForResponse((r) => r.request().method() === 'POST' && /\/publish$/.test(r.url()), { timeout: 20000 }),
        click(ed('[data-fk="confirm"]')),
      ]);
      pub = pr.status();
      await eD.waitForFunction(() => /опубликован/i.test((document.querySelector('#civic-editor .civic-r04-msg') || {}).textContent || ''), null, { timeout: 15000 }).catch(() => null);
    }
    const msg = strip(await ed('.civic-r04-msg').first().innerText().catch(() => ''));
    S.e3ms = Date.now() - tE0;
    const sh = await shot(eD, '10', 'shift_published_editor');
    step('E3', 'current_planned_end -> 2026-10-27 with reason via the form (re-publish if required)', D,
      resp.status() === 200 && (pend === false || pub === 200) ? 'PASS' : 'FAIL',
      `rebase offered and used=${rebased} via ${rebaseHow}; update body changes keys=${S.updateChangeKeys}; reason kept after rebase=${reasonAfterRebase === REASON_SHIFT}; POST .../update ${resp.status()} (has_unpublished_changes=${pend}); re-publish required=${pend === true}, POST .../publish ${pub}; notice: "${msg}"`, sh);
  });

  if ((S.updateBodies || []).some((b) => b.changes && Object.prototype.hasOwnProperty.call(b.changes, 'internal_notes') && !b.changes.internal_notes))
    note('E3 observation: the editor diff lists "Внутренняя заметка: пусто → пусто" as a change and the update request carries changes.internal_notes=' + JSON.stringify((S.updateBodies.find((b) => b.changes && 'internal_notes' in b.changes) || {}).changes.internal_notes) + ' although the field was not touched (changes keys: ' + S.updateBodies.map((b) => Object.keys(b.changes || {}).join('+')).join(', ') + ')');

  // ============ A04 / U05: resident sees the shift and history; F5; server restart
  const shiftCheck = (cf) => {
    const hist = cf.history.join(' || ');
    return {
      current: cf.dl['Текущий срок'] === '27 октября 2026', original: cf.dl['Первоначальный срок'] === '20 октября 2026',
      shift: /перенес[её]н/i.test(cf.shift || '') && /7 дн/.test(cf.shift || ''),
      reason: [REASON_SHIFT, REASON_PUB2].some((r) => hist.includes(r) || (cf.shift || '').includes(r)),
      hist,
    };
  };
  for (const [page, vp] of [[rD, D], [rM, M]]) {
    await guard('A04', 'resident card: new date, original date, history with reason', vp, async () => {
      await openObject(page, S.id, TITLE);
      const cf = await cardFacts(page);
      const c = shiftCheck(cf);
      const sh = await shot(page, '11', 'card_shift_history');
      step('A04', 'resident card: new date + original date + history entry with reason', vp, c.current && c.original && c.shift && c.reason ? 'PASS' : 'FAIL',
        `Текущий срок="${cf.dl['Текущий срок']}", Первоначальный срок="${cf.dl['Первоначальный срок']}", shift note="${strip(cf.shift)}", history="${strip(c.hist).slice(0, 400)}"`, sh);
    });
  }
  {
    const cf = await cardFacts(rD).catch(() => null);
    if (cf) {
      const hist = cf.history.join(' || ') + ' ' + (cf.shift || '');
      if (!hist.includes(REASON_SHIFT) && hist.includes(REASON_PUB2))
        note(`A04 observation: the public history/shift note shows the re-publish reason «${REASON_PUB2}», not the reason typed together with the date change «${REASON_SHIFT}»; while typing it the editor was told: "${S.updateHint}". With the pending-publication model the update reason stays editor-only, so the hint over-promises.`);
    }
  }
  await guard('U05-F5', 'F5 keeps the selected object and data', D, async () => {
    const before = await cardFacts(rD);
    await rD.reload({ waitUntil: 'domcontentloaded' });
    await waitMap(rD);
    await waitCard(rD, TITLE);
    const after = await cardFacts(rD);
    const c = shiftCheck(after);
    step('U05-F5', 'F5 keeps the selected object (permalink #object=) and data', D, after.hash === before.hash && c.current && c.reason ? 'PASS' : 'FAIL',
      `hash before="${before.hash}" after="${after.hash}"; card title after reload="${after.title}"; Текущий срок="${after.dl['Текущий срок']}"`);
  });
  await guard('U05-restart', 'server restart (same DB): data still there', D, async () => {
    if (!CTL) { step('U05-restart', 'server restart (same DB): data still there', D, 'NOT_RUN', 'no restart control channel (run via run_walkthrough.py)'); return; }
    const t0 = Date.now();
    const r = await ctl('RESTART');
    if (!/^R10CTL:OK/.test(r)) throw new Error('restart failed: ' + r);
    await rD.reload({ waitUntil: 'domcontentloaded' });
    await waitMap(rD);
    await waitCard(rD, TITLE);
    const cf = await cardFacts(rD);
    const c = shiftCheck(cf);
    const sh = await shot(rD, '12', 'after_restart');
    const sess = await pageFetch(eD, 'GET', '/session');
    S.editorSessionAfterRestart = !!(sess.json && sess.json.data && sess.json.data.authenticated);
    step('U05-restart', 'server process restarted (same DB) -> reload: data still there', D, c.current && c.original && c.reason ? 'PASS' : 'FAIL',
      `launcher: ${r.replace('R10CTL:', '')}; ${Date.now() - t0} ms to reload; after restart card="${cf.title}", Текущий срок="${cf.dl['Текущий срок']}", Первоначальный="${cf.dl['Первоначальный срок']}", reason in history=${c.reason}; editor session still valid after restart=${S.editorSessionAfterRestart}`, sh);
  });

  // ============ U08 + A07: resident feedback (network failure first)
  const fb = (sel) => rD.locator('#civic-feedback-box ' + sel);
  await guard('U08', 'feedback POST network failure -> error shown, text kept', D, async () => {
    await waitCard(rD, TITLE);
    await click(rD.locator('#civic-map-root [data-r03-action="feedback"]'));
    await fb('textarea').waitFor({ timeout: 10000 });
    S.formNotice = strip(await fb('.civic-r06-official').first().innerText().catch(() => ''));
    await select(fb('select'), 'sidewalks');
    await fill(fb('textarea'), FB_TEXT);
    await check(fb('input[type="radio"][value="true"]'));
    const handler = (route) => (route.request().method() === 'POST' ? route.abort('failed') : route.continue());
    await rD.route('**/api/civic/v1/feedback', handler);
    await click(fb('button[type="submit"]'));
    await rD.waitForFunction(() => { const s = document.querySelector('#civic-feedback-box .civic-r06-status'); return s && /civic-r06-status-error/.test(s.className); }, null, { timeout: 15000 });
    const status = strip(await fb('.civic-r06-status').first().innerText());
    const kept = await fb('textarea').inputValue();
    const sh = await shot(rD, '13', 'feedback_network_error');
    await rD.unroute('**/api/civic/v1/feedback', handler);
    step('U08', 'feedback POST aborted (page.route) -> error shown, typed text kept', D, status && kept === FB_TEXT ? 'PASS' : 'FAIL',
      `status line: "${status}"; textarea still holds the typed text=${kept === FB_TEXT}`, sh);
  });
  await guard('A07', 'resident submits feedback with consent; receipt not an official registration', D, async () => {
    const [resp] = await Promise.all([
      rD.waitForResponse((r) => r.request().method() === 'POST' && r.url().endsWith(API + '/feedback'), { timeout: 20000 }),
      click(fb('button[type="submit"]')),
    ]);
    await fb('.civic-r06-receipt').waitFor({ timeout: 10000 });
    const receipt = strip(await fb('.civic-r06-receipt').innerText());
    S.receiptShown = /Номер квитанции/.test(receipt);
    const sh = await shot(rD, '14', 'feedback_receipt');
    const notOfficial = /регистрац\S*( обращения)? не выполняется/i.test(receipt);
    const channels = /iKOMEK/i.test(receipt) && /eOtinish/i.test(receipt);
    step('A07', 'feedback via the card form with consent; receipt says it is not an official registration', D,
      resp.status() < 300 && notOfficial ? 'PASS' : 'FAIL', `POST /feedback ${resp.status()}; receipt: "${receipt.replace(/[0-9A-Za-z_-]{16,}/g, '<id>').slice(0, 900)}"`, sh);
    // Graded against USER_TEST_SCRIPT T4 ("понятен receipt и что это не официальное обращение"): the receipt number and the
    // not-official notice must be on screen, not only in the DOM. Naming iKOMEK/eOtinish in the receipt is NOT required by
    // CONTRACT/BRIEF/ACCEPTANCE (official channel = later stage) -> recorded as a note, not graded (round-11 skeptic fix).
    const vis = await rD.evaluate(() => {
      const box = document.getElementById('civic-feedback-box');
      let sc = box.parentElement; while (sc && sc !== document.body) { const o = getComputedStyle(sc).overflowY; if ((o === 'auto' || o === 'scroll') && sc.scrollHeight > sc.clientHeight) break; sc = sc.parentElement; }
      const vr = sc && sc !== document.body ? sc.getBoundingClientRect() : { top: 0, bottom: innerHeight };
      const inView = (el) => { if (!el) return false; const r = el.getBoundingClientRect(); return r.height > 0 && r.top >= Math.max(vr.top, 0) - 1 && r.bottom <= Math.min(vr.bottom, innerHeight) + 1; };
      const rc = box.querySelector('.civic-r06-receipt');
      return { id: inView(rc && rc.querySelector('.civic-r06-receipt-id')), notice: inView(rc && rc.querySelector('.civic-r06-official')), noticeText: ((rc && rc.querySelector('.civic-r06-official')) || {}).innerText || '' };
    });
    step('A07-receipt-visible', 'receipt number and "not an official registration" notice are on screen (T4)', D, vis.id && vis.notice && /не выполняется/.test(vis.noticeText) ? 'PASS' : 'FAIL',
      `receipt id in view=${vis.id}; notice in view=${vis.notice}: "${strip(vis.noticeText)}"`, sh);
    if (!channels) note(`A07 wording observation (not graded; not a CONTRACT/BRIEF requirement): the receipt notice from the server replaces the form notice, so after submitting the resident is told the message is not official but not where to go; the form notice before submitting did name the channels: "${S.formNotice}". Suggestion only.`);
  });
  await guard('A07-mobile-form', 'feedback form at 390x844', M, async () => {
    await openObject(rM, S.id, TITLE);
    await click(rM.locator('#civic-map-root [data-r03-action="feedback"]'));
    await rM.locator('#civic-feedback-box textarea').waitFor({ timeout: 10000 });
    const f = await rM.evaluate(() => ({ sw: document.documentElement.scrollWidth, iw: innerWidth, sheet: document.getElementById('civic-panel').dataset.sheet,
      notice: (document.querySelector('#civic-feedback-box .civic-r06-official') || {}).textContent }));
    const sh = await shot(rM, '14', 'feedback_form');
    step('A07-mobile-form', 'feedback form usable at 390x844 (sheet full, no horizontal scroll)', M, f.sw <= f.iw + 1 && /iKOMEK/.test(f.notice || '') ? 'PASS' : 'FAIL',
      `sheet=${f.sheet}; scrollWidth=${f.sw}/${f.iw}; notice="${strip(f.notice)}" (form not submitted from mobile)`, sh);
    await key(rM, 'Escape');
  });
  await guard('A07-pending', 'message not public while pending (fresh resident)', D, async () => {
    const c = await newCtx(D); const p = await c.newPage(); instrument(p, 'resident-fresh-pending', 'resident');
    await openObject(p, S.id, TITLE);
    await click(p.locator('#civic-map-root [data-r03-action="feedback"]'));
    await p.waitForFunction(() => { const s = document.querySelector('#civic-feedback-box .civic-r06-public'); return s && s.querySelector('ul, .civic-r06-muted'); }, null, { timeout: 15000 });
    const pub = strip(await p.locator('#civic-feedback-box .civic-r06-public').innerText());
    const api = await pageFetch(p, 'GET', '/objects/' + encodeURIComponent(S.id) + '/feedback');
    const apiHas = JSON.stringify(api.json || {}).includes('тротуар перекрыт');
    const sh = await shot(p, '15', 'pending_not_public');
    step('A07-pending', 'pending message not public (fresh resident: card list + public API)', D, !pub.includes('тротуар перекрыт') && !apiHas && api.status === 200 ? 'PASS' : 'FAIL',
      `public block: "${pub.slice(0, 200)}"; GET /objects/{id}/feedback ${api.status}, items=${api.json && api.json.data ? (api.json.data.items || []).length : 'n/a'}, contains text=${apiHas}`, sh);
    await c.close();
  });

  // ============ A08: editor approves with a public reply through the moderation UI
  await guard('A08', 'editor approves with a public reply via the moderation UI', D, async () => {
    if (await eD.locator('#civic-moderation-button').isHidden()) {
      note('moderation button hidden for the editor at A08 (session state after restart?) — logging in again via the staff UI');
      await click(eD.locator('#civic-staff-button'));
      await ed('input[name="username"]').waitFor({ timeout: 15000 });
      await fill(ed('input[name="username"]'), ED.user); await fill(ed('input[name="password"]'), ED.pw);
      await click(ed('button[type="submit"]'));
      await ed('[data-fk="new"]').waitFor({ timeout: 15000 });
    }
    const foot = await eD.evaluate(() => { const b = document.getElementById('civic-moderation-button').getBoundingClientRect(); const pnl = document.getElementById('civic-panel').getBoundingClientRect(); const f = document.querySelector('.civic-foot');
      return { btnRight: Math.round(b.right), panelRight: Math.round(pnl.right), footScroll: f.scrollWidth, footClient: f.clientWidth }; });
    if (foot.btnRight > foot.panelRight + 1 || foot.footScroll > foot.footClient + 1)
      note(`A08 observation (1440x900): for a signed-in editor the panel footer overflows — "Сообщения жителей" button right edge ${foot.btnRight}px vs panel right ${foot.panelRight}px (footer scrollWidth ${foot.footScroll} > clientWidth ${foot.footClient}); the label is clipped (see 09_conflict / 16 screenshots).`);
    await click(eD.locator('#civic-moderation-button'));
    // layout after the click: does the overflowing footer drag the resident panel sideways? (round-11 skeptic addition)
    await eD.waitForTimeout(500);
    const shift = await eD.evaluate(() => { const pn = document.getElementById('civic-panel'); const t = document.querySelector('#civic-map-root .civic-r03-card-title, #civic-map-root .civic-r03-count');
      const pr = pn.getBoundingClientRect(), tr = t ? t.getBoundingClientRect() : null; return { scrollLeft: pn.scrollLeft, panelLeft: Math.round(pr.left), contentLeft: tr ? Math.round(tr.left) : null }; });
    const shP = await shot(eD, '16a', 'panel_after_moderation_click');
    step('U03-editor-footer', 'desktop 1440x900, signed-in editor: panel footer fits; clicking "Сообщения жителей" does not shift the panel', D,
      foot.btnRight <= foot.panelRight + 1 && shift.scrollLeft === 0 ? 'PASS' : 'FAIL',
      `footer scrollWidth ${foot.footScroll} vs clientWidth ${foot.footClient}; "Сообщения жителей" right edge ${foot.btnRight}px vs panel right ${foot.panelRight}px; after the click #civic-panel.scrollLeft=${shift.scrollLeft}, card content left=${shift.contentLeft}px vs panel left=${shift.panelLeft}px (content clipped on the left)`, shP);
    const item = eD.locator('#civic-moderation .civic-r06-queue-item', { hasText: 'тротуар перекрыт' });
    await item.first().waitFor({ timeout: 15000 });
    await click(item.first());
    const form = eD.locator('#civic-moderation .civic-r06-decision');
    await form.waitFor({ timeout: 15000 });
    const privateText = strip(await eD.locator('#civic-moderation .civic-r06-private').innerText().catch(() => ''));
    await fill(form.locator('textarea[placeholder^="Причина решения"]'), MOD_REASON);
    await fill(form.locator('textarea[placeholder^="Необязательно"]'), REPLY);
    const approveChecked = await form.locator('input[type="radio"][value="approve"]').isChecked();
    const [resp] = await Promise.all([
      eD.waitForResponse((r) => r.request().method() === 'POST' && /\/staff\/feedback\/[^/]+\/moderate$/.test(r.url()), { timeout: 20000 }),
      click(form.locator('button[type="submit"]')),
    ]);
    const mj = await resp.json().catch(() => null);
    await eD.waitForTimeout(1200);
    const head = strip(await eD.locator('#civic-moderation .civic-r06-detail h4').first().innerText().catch(() => ''));
    const sh = await shot(eD, '16', 'moderation_approve');
    step('A08', 'editor approves with a public reply via the moderation UI', D, resp.status() === 200 && approveChecked ? 'PASS' : 'FAIL',
      `button "Сообщения жителей" -> queue -> message (moderator sees literal text: ${privateText.includes(FB_XSS)}) -> approve (default checked=${approveChecked}) + reason + public reply -> POST .../moderate ${resp.status()} ${mj && mj.error ? mj.error.code + ' ' + JSON.stringify(mj.error.fields) : ''}; detail header now "${head}"`, sh);
  });
  for (const [page, vp] of [[rD, D], [rM, M]]) {
    await guard('A08-resident', 'resident sees the approved message and the reply', vp, async () => {
      await openObject(page, S.id, TITLE);
      await click(page.locator('#civic-map-root [data-r03-action="feedback"]'));
      await page.locator('#civic-feedback-box .civic-r06-public-item').first().waitFor({ timeout: 15000 });
      const it = page.locator('#civic-feedback-box .civic-r06-public-item').first();
      await it.scrollIntoViewIfNeeded();
      const txt = await it.locator('.civic-r06-text').innerText();
      const reply = strip(await it.locator('.civic-r06-reply').innerText().catch(() => ''));
      const sh = await shot(page, '17', 'reply_visible');
      step('A08-resident', 'resident sees the approved message and the moderator reply', vp, txt.includes('тротуар перекрыт') && reply.includes('передано подрядчику') ? 'PASS' : 'FAIL',
        `public message text="${strip(txt)}"; reply="${reply}"`, sh);
    });
  }

  // ============ S10 / U10: no script execution; payloads shown as literal text
  for (const [page, vp, rec] of [[rD, D, recRD], [rM, M, recRM]]) {
    await guard('S10', 'XSS payloads not executed, shown as literal text', vp, async () => {
      const f = await page.evaluate(({ a, b }) => ({
        sentinel: typeof window.__r10xss === 'undefined' ? 'undefined' : String(window.__r10xss),
        imgX: document.querySelectorAll('img[src="x"]').length,
        fbLiteral: document.body.innerText.includes(a), replyLiteral: document.body.innerText.includes(b),
      }), { a: FB_XSS, b: REPLY_XSS });
      const dialogs = PAGES.filter((p) => p.role === 'resident').reduce((n, p) => n + p.dialogs.length, 0);
      step('S10', 'resident: window.__r10xss undefined, no dialog, payloads visible as literal text', vp,
        f.sentinel === 'undefined' && f.imgX === 0 && dialogs === 0 && f.fbLiteral && f.replyLiteral ? 'PASS' : 'FAIL',
        `__r10xss=${f.sentinel}; injected <img src=x> elements=${f.imgX}; dialogs in resident pages=${dialogs}; feedback payload literal in page text=${f.fbLiteral}; reply payload literal=${f.replyLiteral}; title payload: rejected at input (form + server), so not rendered anywhere${S.serverAcceptedXssTitle ? ' — BUT server accepted it via API: ' + S.serverAcceptedXssTitle : ''}`);
    });
  }

  // ============ U06: attribution with a stubbed basemap style; real basemap NOT_RUN; fallback notice
  for (const [page, vp] of [[rD, D], [rM, M]]) {
    const f = await page.evaluate(() => ({ status: (document.getElementById('map-status') || {}).innerText, hidden: document.getElementById('map-status').classList.contains('hidden'),
      offline: document.body.classList.contains('offline-basemap'), attrib: (document.querySelector('.maplibregl-ctrl-attrib') || {}).className || null,
      attribText: (document.querySelector('.maplibregl-ctrl-attrib') || {}).innerText || '' }));
    step('U06-fallback', 'basemap blocked -> offline fallback notice is honest', vp,
      f.offline && !f.hidden && /OpenFreeMap недоступна/.test(f.status || '') && /без улиц/.test(f.status || '') ? 'PASS' : 'FAIL',
      `#map-status="${strip(f.status)}" visible=${!f.hidden}; body.offline-basemap=${f.offline}; attribution control in fallback: class="${f.attrib}", text="${strip(f.attribText)}" (no OSM-derived layer is drawn in fallback)`);
  }
  step('U06-basemap', 'OpenFreeMap basemap and 3D buildings', 'n/a', 'NOT_RUN',
    'tiles.openfreemap.org blocked by the sandbox proxy (CONNECT 403 -> net::ERR_TUNNEL_CONNECTION_FAILED for /styles/liberty and /planet); real basemap, streets and 3D not observable here');
  for (const vp of [D, M]) {
    await guard('U06-attribution', 'attribution visible and not covered (stubbed basemap style)', vp, async () => {
      const c = await newCtx(vp); const p = await c.newPage(); instrument(p, 'resident-stubstyle-' + vpn(vp), 'resident');
      const STYLE = { version: 8, sources: { openmaptiles: { type: 'geojson', data: { type: 'FeatureCollection', features: [] },
        attribution: '<a href="https://openfreemap.org" target="_blank">OpenFreeMap</a> <a href="https://www.openmaptiles.org/" target="_blank">&copy; OpenMapTiles</a> Data from <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a>' } },
        layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#f2efe9' } }, { id: 'stub-line', type: 'line', source: 'openmaptiles', paint: { 'line-color': '#999' } }] };
      await p.route('https://tiles.openfreemap.org/**', (route) => (/\/styles\/liberty/.test(route.request().url())
        ? route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(STYLE) }) : route.abort('failed')));
      await openHome(p);
      await p.waitForFunction(() => { const a = document.querySelector('.maplibregl-ctrl-attrib'); return a && /OpenStreetMap/.test(a.innerText); }, null, { timeout: 15000 });
      const measure = () => p.evaluate(() => {
        const a = document.querySelector('.maplibregl-ctrl-attrib');
        const inner = a.querySelector('.maplibregl-ctrl-attrib-inner') || a;
        const r = inner.getBoundingClientRect();
        const pts = [[r.left + 4, r.top + r.height / 2], [r.left + r.width / 2, r.top + r.height / 2], [r.right - 4, r.top + r.height / 2]];
        const cov = pts.map(([x, y]) => { const t = document.elementFromPoint(Math.min(Math.max(x, 0), innerWidth - 1), Math.min(Math.max(y, 0), innerHeight - 1)); return !!t && (a.contains(t)); });
        return { text: a.innerText.trim(), rect: [r.left, r.top, r.width, r.height].map(Math.round), inViewport: r.width > 0 && r.left >= 0 && r.right <= innerWidth + 1 && r.bottom <= innerHeight + 1 && r.top >= 0, uncovered: cov, cls: a.className };
      });
      const m0 = await measure();
      const sh = await shot(p, '19', 'attribution_stubstyle');
      // with a card open (mobile: sheet) the control must still be free
      const first = p.locator('#civic-map-root [data-r03-action="select"]').first();
      let m1 = null;
      if (await first.count()) { await click(first); await waitCard(p, null); await p.waitForTimeout(600); m1 = await measure(); }
      const sh2 = await shot(p, '19b', 'attribution_card_open');
      const ok = [m0, m1].filter(Boolean).every((m) => m.inViewport && m.uncovered.every(Boolean) && /OpenStreetMap/.test(m.text) && /OpenFreeMap/.test(m.text));
      step('U06-attribution', 'attribution visible and not covered (basemap style STUBBED locally: real host blocked)', vp, ok ? 'PASS' : 'FAIL',
        `stub style with the liberty attribution string served via page.route; list view: rect=${m0.rect} inViewport=${m0.inViewport} uncovered(l,c,r)=${m0.uncovered} text="${strip(m0.text)}"; card open: ${m1 ? `rect=${m1.rect} inViewport=${m1.inViewport} uncovered=${m1.uncovered}` : 'n/a'}`, [sh, sh2]);
      await c.close();
    });
  }

  // ============ U07: keyboard
  await guard('U07', 'keyboard: Tab reaches list, card controls, feedback form; Escape', D, async () => {
    const c = await newCtx(D); const p = await c.newPage(); instrument(p, 'resident-keyboard', 'resident');
    await openHome(p);
    const desc = () => p.evaluate(() => { const a = document.activeElement; if (!a || a === document.body) return 'body';
      return a.tagName.toLowerCase() + (a.id ? '#' + a.id : '') + (a.getAttribute('data-r03-action') ? '[' + a.getAttribute('data-r03-action') + ']' : '') + (a.getAttribute('data-mode') ? '[mode=' + a.getAttribute('data-mode') + ']' : '') + ':' + (a.getAttribute('aria-label') || a.textContent || a.placeholder || '').trim().slice(0, 30); });
    const where = (sel) => p.evaluate((s) => !!document.activeElement && !!document.activeElement.closest(s), sel);
    const seq = [];
    let reachedList = false;
    for (let i = 0; i < 70 && !reachedList; i++) {
      await key(p, 'Tab'); const d = await desc(); seq.push(d);
      reachedList = await p.evaluate((id) => !!document.activeElement && document.activeElement.matches('[data-r03-action="select"]'), S.id);
    }
    const listTabs = seq.length;
    // move to our object in the list with Tab if needed, then open it with Enter
    for (let i = 0; i < 10; i++) {
      if (await p.evaluate((id) => document.activeElement && document.activeElement.getAttribute('data-id') === id, S.id)) break;
      await key(p, 'Tab');
    }
    await key(p, 'Enter');
    await waitCard(p, null);
    const afterEnter = await desc();
    const cardSeq = [];
    let reachedFb = false;
    for (let i = 0; i < 40 && !reachedFb; i++) {
      await key(p, 'Tab'); cardSeq.push(await desc());
      reachedFb = await where('[data-r03-action="feedback"]');
    }
    let reachedForm = false; const formSeq = [];
    if (reachedFb) {
      await key(p, 'Enter');
      await p.locator('#civic-feedback-box textarea').waitFor({ timeout: 10000 });
      for (let i = 0; i < 40 && !reachedForm; i++) {
        await key(p, 'Tab'); formSeq.push(await desc());
        reachedForm = await p.evaluate(() => !!document.activeElement && document.activeElement.matches('#civic-feedback-box textarea'));
      }
    }
    const sh = await shot(p, '20', 'keyboard_feedback_form');
    // Escape behaviour
    await key(p, 'Escape');
    const esc1 = await p.evaluate(() => ({ feedbackOpen: !document.getElementById('civic-feedback-box').hidden,
      cardOpen: !document.querySelector('#civic-map-root .civic-r03-card').hidden, focus: document.activeElement === document.body ? 'body' : document.activeElement.tagName }));
    await key(p, 'Escape');
    const esc2 = await p.evaluate(() => ({ cardOpen: !document.querySelector('#civic-map-root .civic-r03-card').hidden, focus: document.activeElement === document.body ? 'body' : document.activeElement.tagName }));
    let esc3 = null;
    if (esc2.cardOpen) {
      await p.locator('#civic-map-root .civic-r03-card-title').focus();
      await key(p, 'Escape');
      esc3 = await p.evaluate(() => ({ cardOpen: !document.querySelector('#civic-map-root .civic-r03-card').hidden, focus: document.activeElement === document.body ? 'body' : (document.activeElement.getAttribute('data-id') ? 'list item' : document.activeElement.tagName) }));
    }
    // staff drawer: Escape closes it
    await click(p.locator('#civic-staff-button'));
    await p.locator('#civic-editor input[name="username"]').waitFor({ timeout: 10000 });
    await key(p, 'Escape');
    const drawer = await p.evaluate(() => ({ hidden: document.getElementById('civic-editor').hidden, focus: document.activeElement && document.activeElement.id }));
    const ok = reachedList && reachedFb && reachedForm && !esc1.feedbackOpen && (esc2.cardOpen === false || (esc3 && esc3.cardOpen === false)) && drawer.hidden;
    step('U07', 'keyboard: Tab reaches list, card controls, feedback form; Escape closes', D, ok ? 'PASS' : 'FAIL',
      `list item reached after ${listTabs} Tabs (path: ${seq.slice(0, 14).join(' > ')}${seq.length > 14 ? ' > …' : ''}); Enter opened card, focus="${afterEnter}"; card controls: ${cardSeq.join(' > ')}; feedback form textarea reached=${reachedForm} via ${formSeq.slice(0, 6).join(' > ')}; Escape#1: feedback closed=${!esc1.feedbackOpen}, card still open=${esc1.cardOpen}, focus=${esc1.focus}; Escape#2 (focus ${esc1.focus}): card open=${esc2.cardOpen}; Escape with focus in card: ${esc3 ? 'card open=' + esc3.cardOpen + ', focus->' + esc3.focus : 'n/a'}; staff drawer + Escape: hidden=${drawer.hidden}, focus->#${drawer.focus}`, sh);
    if (!esc1.feedbackOpen && esc1.focus === 'body') note('U07 observation: after Escape closes the feedback form, keyboard focus falls back to <body> (not returned to the "Задать вопрос" button); a second Escape then does not reach the card.');
    await c.close();
  });

  // ============ S06 / S07: cookie flags, storage, role spoof
  await guard('S06', 'session cookie HttpOnly; no session/role/CSRF in JS storage', D, async () => {
    const cookies = (await edD.cookies()).filter((c) => /127\.0\.0\.1|localhost/.test(c.domain));
    const sessionCookies = cookies.filter((c) => c.value && c.value.length >= 20);
    const vals = sessionCookies.map((c) => c.value);
    const f = await eD.evaluate(async (cvals) => {
      const s = await (await fetch('/api/civic/v1/session', { headers: { Accept: 'application/json' }, cache: 'no-store' })).json();
      const csrf = s && s.data ? s.data.csrf_token : null;
      const dump = (st) => { const o = []; for (let i = 0; i < st.length; i++) { const k = st.key(i); o.push([k, String(st.getItem(k))]); } return o; };
      const ls = dump(localStorage), ss = dump(sessionStorage);
      const all = ls.concat(ss);
      return { authenticated: !!(s.data && s.data.authenticated), docCookie: document.cookie, docCookieHasSession: cvals.some((v) => document.cookie.includes(v)),
        storageKeys: all.map(([k]) => k), csrfInStorage: !!csrf && all.some(([k, v]) => v.includes(csrf) || k.includes(csrf)),
        cookieInStorage: all.some(([k, v]) => cvals.some((c) => v.includes(c))),
        storageSummary: all.map(([k, v]) => k + '=' + v.slice(0, 90)),
        suspiciousKeys: all.filter(([k, v]) => /csrf|token|role|auth|passw/i.test(k) || /"role"\s*:|authenticated|csrf|"token"|passw|editor/i.test(v)).map(([k, v]) => k + '=' + v.slice(0, 60)) };
    }, vals);
    const ok = sessionCookies.length >= 1 && sessionCookies.every((c) => c.httpOnly) && !f.docCookieHasSession && !f.csrfInStorage && !f.cookieInStorage && f.suspiciousKeys.length === 0;
    step('S06', 'after login: session cookie HttpOnly; storages hold no session/role/CSRF', D, ok ? 'PASS' : 'FAIL',
      `cookies: ${cookies.map((c) => `${c.name} (len ${c.value.length}, httpOnly=${c.httpOnly}, sameSite=${c.sameSite}, path=${c.path}, secure=${c.secure})`).join('; ')}; document.cookie="${f.docCookie.replace(/=[^;]{12,}/g, '=<value>')}" contains session=${f.docCookieHasSession}; storage keys=[${f.storageKeys.join(', ')}] (content: ${JSON.stringify(f.storageSummary)}); CSRF token in storage=${f.csrfInStorage}; session value in storage=${f.cookieInStorage}; auth-like keys=${JSON.stringify(f.suspiciousKeys)}; session authenticated=${f.authenticated}`);
  });
  await guard('S07', 'localStorage role=editor in a resident context grants nothing', D, async () => {
    const c = await newCtx(D);
    await c.addInitScript(() => {
      try {
        localStorage.setItem('role', 'editor'); localStorage.setItem('civic.role', 'editor'); localStorage.setItem('isEditor', 'true');
        localStorage.setItem('user', JSON.stringify({ name: 'r10', role: 'editor' }));
        localStorage.setItem('civic.session.v1', JSON.stringify({ authenticated: true, user: { name: 'r10', role: 'editor' } }));
        sessionStorage.setItem('role', 'editor'); sessionStorage.setItem('csrf_token', 'r10-fake');
      } catch (e) { /* ignore */ }
    });
    const p = await c.newPage(); const rec = instrument(p, 'resident-role-spoof', 'resident-spoof');
    await openHome(p);
    const modHidden = await p.locator('#civic-moderation-button').isHidden();
    await click(p.locator('#civic-staff-button'));
    await p.locator('#civic-editor input[name="username"]').waitFor({ timeout: 15000 });
    const staffRows = await p.locator('#civic-editor [data-fk="new"], #civic-editor .civic-r04-row').count();
    const uiStaffCalls = rec.staff.filter((e) => !e.deliberate).map((e) => e.m + ' ' + e.p);
    const r1 = await pageFetch(p, 'GET', '/staff/objects');
    const r2 = await pageFetch(p, 'GET', '/staff/feedback?moderation=pending');
    const sh = await shot(p, '21', 'role_spoof_login_required');
    step('S07', 'localStorage/sessionStorage role=editor in a resident context grants no staff UI/data', D,
      modHidden && staffRows === 0 && r1.status === 401 && r2.status === 401 ? 'PASS' : 'FAIL',
      `moderation button hidden=${modHidden}; "Для сотрудников" shows the login form, staff list/new buttons=${staffRows}; UI staff calls=${JSON.stringify(uiStaffCalls)}; direct GET /staff/objects -> ${r1.status}, GET /staff/feedback -> ${r2.status}`, sh);
    await c.close();
  });

  // ============ STRETCH timing (automated-run, not a user study)
  await guard('T-editor', 'timing: editor publishes a date change with reason', D, async () => {
    const t = await edD.newPage(); instrument(t, 'editor-timing', 'editor');
    await openHome(t);
    const e = (s) => t.locator('#civic-editor ' + s);
    const a0 = ACTIONS; const t0 = Date.now();
    await click(t.locator('#civic-staff-button'));
    await e('[data-fk="filter-published"]').waitFor({ timeout: 15000 });
    await click(e('[data-fk="filter-published"]'));
    await click(e(`[data-fk="row-${S.id}"]`));
    await e('[data-fk="current_planned_end"]').waitFor({ timeout: 15000 });
    await fill(e('[data-fk="current_planned_end"]'), '2026-10-29');
    await fill(e('[data-fk="reason"]'), REASON_T);
    await Promise.all([t.waitForResponse((r) => /\/update$/.test(r.url()), { timeout: 20000 }), click(e('[data-fk="save"]'))]);
    await t.waitForTimeout(500);
    let republished = false;
    if (await e('[data-fk="publish"]').count() && await e('[data-fk="publish"]').isEnabled()) {
      await click(e('[data-fk="publish"]'));
      await fill(e('[data-fk="reason"]'), REASON_T);
      await Promise.all([t.waitForResponse((r) => /\/publish$/.test(r.url()), { timeout: 20000 }), click(e('[data-fk="confirm"]'))]);
      republished = true;
    }
    const ms = Date.now() - t0;
    R.timing.editor_publish_date_change = { label: 'automated-run, not a user study', from: 'click "Для сотрудников" (already logged in)', to: 'server confirmed the public change',
      wall_ms: ms, ui_actions: ACTIONS - a0, republish_step: republished, new_current_planned_end: '2026-10-29' };
    step('T-editor', 'STRETCH timing: editor publishes a date change with reason (automated-run, not a user study)', D, 'PASS',
      `${ms} ms, ${ACTIONS - a0} UI actions (clicks+fills+keys), re-publish step=${republished}`);
    await t.close();
  });
  await guard('T-resident', 'timing: resident finds deadline + reason', D, async () => {
    const c = await newCtx(D); const p = await c.newPage(); instrument(p, 'resident-timing', 'resident');
    const a0 = ACTIONS; const t0 = Date.now();
    await openHome(p);
    await click(p.locator('#civic-map-root [data-r03-action="select"]', { hasText: TITLE }).first());
    await p.waitForFunction((r) => { const c = document.querySelector('#civic-map-root .civic-r03-card'); return c && !c.hidden && [...c.querySelectorAll('.civic-r03-history li, .civic-r03-shift')].some((x) => x.innerText.includes(r)); }, REASON_T, { timeout: 30000 });
    const ms = Date.now() - t0;
    const cf = await cardFacts(p);
    R.timing.resident_find_deadline_reason = { label: 'automated-run, not a user study', from: 'page.goto("/")', to: 'history entry with the reason visible',
      wall_ms: ms, ui_actions: ACTIONS - a0, shown_deadline: cf.dl['Текущий срок'], shift_note: strip(cf.shift) };
    step('T-resident', 'STRETCH timing: resident finds deadline + reason (automated-run, not a user study)', D, 'PASS',
      `${ms} ms incl. page load, ${ACTIONS - a0} UI actions; deadline="${cf.dl['Текущий срок']}", shift="${strip(cf.shift)}"`);
    await c.close();
  });

  // ============ Logout via UI; replay staff API -> 401
  await guard('LOGOUT', 'logout via UI; replayed staff call -> 401', D, async () => {
    if (await eD.locator('#civic-editor').isHidden()) await click(eD.locator('#civic-staff-button'));
    await ed('[data-fk="logout"]').waitFor({ timeout: 15000 });
    const before = (await edD.cookies()).filter((c) => c.value && c.value.length >= 20);
    const [resp] = await Promise.all([
      eD.waitForResponse((r) => r.url().endsWith(API + '/session/logout'), { timeout: 20000 }),
      click(ed('[data-fk="logout"]')),
    ]);
    await ed('input[name="username"]').waitFor({ timeout: 10000 });
    await eD.waitForTimeout(500);
    const modHidden = await eD.locator('#civic-moderation-button').isHidden();
    const after = (await edD.cookies()).filter((c) => c.value && c.value.length >= 20);
    const ctxReplay = await pageFetch(eD, 'GET', '/staff/objects');
    const ctxReplayPost = await pageFetch(eD, 'POST', '/staff/objects/' + encodeURIComponent(S.id) + '/update', { expected_revision: 1, changes: { description: 'R10 replay' }, reason: 'R10 replay after logout' }, true);
    let oldCookie = null;
    if (before.length) {
      const rq = await pwRequest.newContext({ baseURL: BASE, extraHTTPHeaders: { Cookie: before.map((c) => c.name + '=' + c.value).join('; ') } });
      const r = await rq.get(API + '/staff/objects');
      oldCookie = r.status();
      await rq.dispose();
    }
    const sh = await shot(eD, '22', 'after_logout');
    step('LOGOUT', 'logout via UI closes staff UI; replayed staff calls -> 401', D,
      resp.status() === 200 && modHidden && ctxReplay.status === 401 && [401, 403].includes(ctxReplayPost.status) && (oldCookie === null || oldCookie === 401) ? 'PASS' : 'FAIL',
      `POST /session/logout ${resp.status()}; staff drawer back to login form; moderation button hidden=${modHidden}; session cookies before/after=${before.length}/${after.length}; replay from the same context GET /staff/objects -> ${ctxReplay.status}, POST update -> ${ctxReplayPost.status}; replay with the pre-logout cookie value (new request context) -> ${oldCookie}`, sh);
  });

  // ============ wrap-up: public staff calls, console errors
  const residentPages = PAGES.filter((p) => p.role === 'resident');
  R.network_staff_calls_public = residentPages.flatMap((p) => p.staff.filter((e) => !e.deliberate).map((e) => ({ page: p.label, call: e.m + ' ' + e.p })));
  R.network_staff_calls_public_note = 'resident contexts never logged in; deliberate script fetches (401 checks) are excluded';
  // classified by the resource URL (console location) first, then by text; anything else is 'unexpected'
  const classify = (t, page) => (/ERR_TUNNEL_CONNECTION_FAILED|openfreemap/i.test(t) && !/stubstyle/.test(page) ? 'basemap-blocked (expected)'
    : /net::ERR_FAILED @ https:\/\/tiles\.openfreemap\.org/.test(t) && /stubstyle/.test(page) ? 'stub-style tile request aborted by the script (expected)'
    : /status of 404 .*@ \/favicon\.ico/.test(t) ? 'favicon.ico 404 (browser default request; benign)'
    : /status of 401 .*@ \/api\/civic\/v1\/staff\//.test(t) && /role-spoof|editor-desktop/.test(page) ? 'expected 401 from a deliberate staff call (S07/LOGOUT)'
    : /status of 404 .*@ \/api\/civic\/v1\/objects\//.test(t) && /a02-deeplink/.test(page) ? 'expected 404 for the draft deep link (A02)'
    : /status of 409 .*@ \/api\/civic\/v1\/staff\/objects\/[^/]+\/update/.test(t) ? 'expected 409 from the U04 conflict'
    : /status of 422 .*@ \/api\/civic\/v1\/staff\/objects$/.test(t) ? 'expected 422 from the server-side HTML-title check'
    : /net::ERR_FAILED @ \/api\/civic\/v1\/feedback$/.test(t) ? 'U08 deliberate abort (expected)' : 'unexpected');
  R.console_errors = PAGES.flatMap((p) => p.consoleErrors.map((t) => ({ page: p.label, kind: classify(t, p.label), text: t })));
  R.http_errors = PAGES.filter((p) => p.bad.length).map((p) => ({ page: p.label, responses: p.bad }));
  R.dialogs = PAGES.flatMap((p) => p.dialogs.map((d) => ({ page: p.label, dialog: d })));
  const unexpected = R.console_errors.filter((e) => e.kind === 'unexpected');
  step('CONSOLE', 'console/page errors (all pages)', 'n/a', unexpected.length ? 'FAIL' : 'PASS',
    `total=${R.console_errors.length}; unexpected=${unexpected.length}${unexpected.length ? ': ' + unexpected.slice(0, 5).map((e) => e.page + ': ' + e.text.slice(0, 120)).join(' | ') : ''}`);
  step('U09-final', 'no /staff/* calls from any resident page during the whole run', 'n/a', R.network_staff_calls_public.length === 0 ? 'PASS' : 'FAIL',
    `${R.network_staff_calls_public.length} staff calls from ${residentPages.length} resident pages`);

  await browser.close();
}

main().then(() => {
  R.finished_utc = new Date().toISOString();
  R.summary = R.steps.reduce((a, s) => { a[s.status] = (a[s.status] || 0) + 1; return a; }, {});
  save();
  console.log('SUMMARY ' + JSON.stringify(R.summary));
  if (rl) rl.close();
  process.exit(0);
}).catch((e) => {
  R.finished_utc = new Date().toISOString();
  R.notes.push('walkthrough aborted: ' + String(e && e.stack ? e.stack : e).slice(0, 800));
  save();
  console.error(e);
  if (rl) rl.close();
  process.exit(1);
});
