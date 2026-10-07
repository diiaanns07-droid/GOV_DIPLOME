// R10 skeptic re-checks for the R01 walkthrough (Playwright, CommonJS). Independent of walkthrough.cjs:
// fresh objects created through the API, then the disputed UI states are re-created and measured.
// Run through the launcher (server + editors via pty):
//   python3 -I tests/civic/R10/browser/run_walkthrough.py --script skeptic_r01.cjs --code-root <checkout> \
//       --out <json> --shots <dir> --label <label>
// Checks:
//   K-U04-reach@WxH   conflict panel "Перенести мои правки…" reachable by pointer at 4 viewports;
//                     then a mouse-only recovery (collapse the diff <details>, Playwright scroll) is tried.
//   K-A07-receipt     what the resident actually sees after submitting feedback (receipt + channels).
//   K-X*              extra observations: feedback-button contrast, footer overflow / panel h-scroll,
//                     training-mode header overflow, assistant on a draft id, 4xx URLs behind console errors.
// Passwords, cookies and CSRF tokens are never written to the report.
'use strict';
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const BASE = process.env.R10_BASE_URL;
const OUT = process.env.R10_OUT_JSON;
const SHOTS = process.env.R10_SHOTS;
const EXE = process.env.R10_CHROMIUM || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const ED = { user: process.env.R10_EDITOR_USER, pw: process.env.R10_EDITOR_PASSWORD };
const REPO = path.resolve(__dirname, '../../../..');
const API = '/api/civic/v1';

// SKEPTIC_PARTS=u04,a07,x2,x3,x4 (default: all) — lets a single re-check be repeated quickly
const PARTS = new Set(String(process.env.SKEPTIC_PARTS || 'u04,a07,x2,x3,x4').split(','));
const R = { started_utc: new Date().toISOString(), base_url: BASE, chromium: null, checks: [], notes: [] };
const save = () => { if (OUT) fs.writeFileSync(OUT, JSON.stringify(R, null, 1)); };
function rec(id, vp, status, evidence, shot) {
  R.checks.push({ id, viewport: vp, status, evidence, screenshot: shot || null });
  console.log(`[${status}] ${id} @${vp} :: ${JSON.stringify(evidence).slice(0, 600)}`);
  save();
}
async function shot(page, name) {
  const vp = page.viewportSize();
  const file = path.join(SHOTS, `${name}_${vp.width}x${vp.height}.png`);
  await page.screenshot({ path: file });
  return path.relative(REPO, file);
}
async function call(page, method, p, body) {
  return page.evaluate(async ({ method, p, body }) => {
    const h = { Accept: 'application/json' };
    if (method !== 'GET') {
      const s = await (await fetch('/api/civic/v1/session', { headers: h, cache: 'no-store' })).json();
      if (s && s.data && s.data.csrf_token) h['X-CSRF-Token'] = s.data.csrf_token;
      h['Content-Type'] = 'application/json';
    }
    const r = await fetch('/api/civic/v1' + p, { method, headers: h, cache: 'no-store', body: body == null ? undefined : JSON.stringify(body) });
    let j = null; try { j = await r.json(); } catch (e) { j = null; }
    return { status: r.status, json: j };
  }, { method, p, body: body == null ? null : body });
}
async function apiLogin(page) {
  await page.goto(BASE + '/favicon.svg');
  const r = await page.evaluate(async (c) => {
    const x = await fetch('/api/civic/v1/session/login', { method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' }, body: JSON.stringify(c) });
    return x.status;
  }, { username: ED.user, password: ED.pw });
  if (r !== 200) throw new Error('login ' + r);
}
function objBody(title, end) {
  return { title, description: 'R10 skeptic', kind: 'roadworks', status: 'planned',
    geometry: { type: 'Point', coordinates: [71.43042, 51.12825] }, geometry_precision: 'approximate',
    schedule: { planned_start: '2026-10-14', original_planned_end: end, current_planned_end: end, actual_end: null },
    budget: { amount_kzt: null, basis: 'unknown', source_id: null }, responsible: { organization: null, public_contact: null },
    evidence_type: 'synthetic', source_refs: [], evidence_notes: '' };
}
async function createPublished(page, title) {
  const c = await call(page, 'POST', '/staff/objects', objBody(title, '2026-10-20'));
  if (c.status !== 201 && c.status !== 200) throw new Error('create ' + c.status + ' ' + JSON.stringify(c.json).slice(0, 300));
  const it = c.json.data.item;
  const p = await call(page, 'POST', '/staff/objects/' + it.id + '/publish', { expected_revision: it.revision, reason: 'R10 skeptic: публикация' });
  if (p.status !== 200) throw new Error('publish ' + p.status);
  return { id: it.id, revision: p.json.data.item.revision };
}
async function waitMap(page) {
  await page.waitForFunction(() => (typeof mapReady !== 'undefined' && mapReady === true) || !!document.querySelector('#map-fallback:not(.hidden)'), null, { timeout: 40000 }).catch(() => null);
}
async function openHome(page, hash) {
  if (page.url() !== 'about:blank') await page.goto('about:blank');
  await page.goto(BASE + '/' + (hash || ''), { waitUntil: 'domcontentloaded' });
  await waitMap(page);
  await page.waitForFunction(() => { const c = document.querySelector('#civic-map-root .civic-r03-count'); return !!c && /объект/.test(c.textContent); }, null, { timeout: 45000 }).catch(() => null);
}
async function waitCard(page, title) {
  await page.waitForFunction((t) => { const c = document.querySelector('#civic-map-root .civic-r03-card'); if (!c || c.hidden) return false;
    const h = c.querySelector('.civic-r03-card-title'); return !!h && !c.querySelector('.civic-r03-loading') && (!t || h.textContent === t); }, title || null, { timeout: 30000 });
}
const strip = (s) => String(s || '').replace(/\s+/g, ' ').trim();

// geometry probe of the conflict state
const probeConflict = (page) => page.evaluate(() => {
  const q = (s) => document.querySelector('#civic-editor ' + s);
  const b = q('[data-fk="rebase"]'), body = q('.civic-r04-body'), act = q('.civic-r04-actions'), panel = q('[aria-label="Конфликт версий"]'), sv = q('[data-fk="save"]');
  const rect = (e) => { if (!e) return null; const r = e.getBoundingClientRect(); return [r.left, r.top, r.width, r.height].map(Math.round); };
  const hit = (e) => { if (!e) return 'absent'; const r = e.getBoundingClientRect(); const t = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    return !t ? 'nothing' : (t === e || e.contains(t)) ? 'itself' : t.closest('.civic-r04-actions') ? 'action bar' : t.tagName.toLowerCase() + '.' + String(t.className).slice(0, 40); };
  const out = { focused: document.activeElement === b, body: rect(body), bodyScroll: body ? [body.scrollTop, body.scrollHeight, body.clientHeight] : null,
    actions: rect(act), actionsScroll: act ? [act.scrollTop, act.scrollHeight, act.clientHeight] : null, actionsCss: act ? getComputedStyle(act).position + '/' + getComputedStyle(act).maxHeight : null,
    diffOpen: !!(act && act.querySelector('details.civic-r04-diff[open]')), panel: rect(panel) };
  if (b) { b.scrollIntoView({ block: 'center' }); out.btnCentred = { rect: rect(b), hit: hit(b) }; body.scrollTop = 0; out.btnBodyTop = { rect: rect(b), hit: hit(b) }; }
  if (panel) out.panelHitAtTop = hit(panel.querySelector('p'));
  out.save = { rect: rect(sv), hit: hit(sv) };
  out.noticeText = (q('.civic-r04-msg-error') || {}).innerText || '';
  return out;
});

async function conflictAt(browser, vp) {
  const ctx = await browser.newContext({ viewport: vp, deviceScaleFactor: 1, isMobile: vp.width < 500, hasTouch: vp.width < 500, locale: 'ru-RU' });
  const page = await ctx.newPage();
  const vpn = `${vp.width}x${vp.height}`;
  try {
    await apiLogin(page);
    const title = 'R10 skeptic конфликт ' + vpn;
    const o = await createPublished(page, title);
    await openHome(page);
    const e = (s) => page.locator('#civic-editor ' + s);
    await page.locator('#civic-staff-button').click();
    await e('[data-fk="filter-published"]').waitFor({ timeout: 15000 });
    await e('[data-fk="filter-published"]').click();
    await e(`[data-fk="row-${o.id}"]`).click();
    await e('[data-fk="current_planned_end"]').waitFor({ timeout: 15000 });
    await e('[data-fk="current_planned_end"]').fill('2026-10-27');
    await e('[data-fk="reason"]').waitFor({ timeout: 10000 });
    await e('[data-fk="reason"]').fill('R10 skeptic: перенос срока');
    const bump = await call(page, 'POST', '/staff/objects/' + o.id + '/update', { expected_revision: o.revision, changes: { description: 'R10 skeptic: вторая вкладка' }, reason: 'R10 skeptic: вторая вкладка' });
    await e('[data-fk="save"]').click();
    await e('[aria-label="Конфликт версий"]').waitFor({ state: 'attached', timeout: 15000 });
    await page.waitForTimeout(400);
    const g0 = await probeConflict(page);
    let trial0 = true; try { await e('[data-fk="rebase"]').click({ trial: true, timeout: 4000 }); } catch (x) { trial0 = false; }
    const s0 = await shot(page, 'k09_conflict_state');
    // mouse-only recovery: collapse the "Изменения" <details> in the action bar with a real click, then try again
    let collapsed = false, trial1 = null, g1 = null, clicked = false, after = null, s1 = null;
    const summary = e('.civic-r04-actions details.civic-r04-diff > summary');
    if (await summary.count()) {
      let sumOk = true; try { await summary.click({ timeout: 4000 }); } catch (x) { sumOk = false; }
      collapsed = sumOk && !(await page.evaluate(() => !!document.querySelector('#civic-editor .civic-r04-actions details.civic-r04-diff[open]')));
      await page.waitForTimeout(300);
      g1 = await probeConflict(page);
      trial1 = true; try { await e('[data-fk="rebase"]').click({ trial: true, timeout: 4000 }); } catch (x) { trial1 = false; }
      s1 = await shot(page, 'k09b_conflict_diff_collapsed');
      if (trial1) {
        await e('[data-fk="rebase"]').click();
        clicked = true;
        await page.waitForTimeout(500);
        after = strip(await page.evaluate(() => [...document.querySelectorAll('#civic-editor .civic-r04-msg')].map((m) => m.innerText).join(' | ')));
      }
    }
    rec('K-U04-reach', vpn, trial0 ? 'PASS' : 'FAIL', {
      bump_status: bump.status, pointer_trial_click_initial: trial0, ui_moved_focus_to_rebase: g0.focused,
      body_rect: g0.body, body_scroll_top_height_client: g0.bodyScroll, action_bar_rect: g0.actions, action_bar_css: g0.actionsCss,
      action_bar_scroll_top_height_client: g0.actionsScroll, diff_open: g0.diffOpen, conflict_panel_rect: g0.panel,
      rebase_btn_after_scrollIntoView: g0.btnCentred, rebase_btn_with_body_at_top: g0.btnBodyTop, conflict_panel_first_line_hit: g0.panelHitAtTop,
      save_button: g0.save, notice: strip(g0.noticeText).slice(0, 200),
      recovery_collapse_diff: { summary_clicked_and_collapsed: collapsed, pointer_trial_click_after: trial1, geometry_after: g1 && { action_bar_rect: g1.actions, rebase_btn: g1.btnCentred, rebase_btn_body_top: g1.btnBodyTop },
        clicked_rebase: clicked, notice_after_click: after },
    }, [s0, s1].filter(Boolean));
  } catch (x) {
    rec('K-U04-reach', vpn, 'ERROR', { error: String(x && x.message || x).split('\n')[0].slice(0, 300) });
  } finally { await ctx.close(); }
}

async function main() {
  fs.mkdirSync(SHOTS, { recursive: true });
  const browser = await chromium.launch({ executablePath: EXE, headless: true });
  R.chromium = browser.version();
  const D = { width: 1440, height: 900 };

  // ---------- U04-reach at several viewports
  if (PARTS.has('u04')) for (const vp of [D, { width: 1366, height: 768 }, { width: 1920, height: 1080 }, { width: 390, height: 844 }]) await conflictAt(browser, vp);

  // ---------- setup for the resident checks: one published object (editor context)
  const edCtx = await browser.newContext({ viewport: D, deviceScaleFactor: 1, locale: 'ru-RU' });
  const ep = await edCtx.newPage();
  await apiLogin(ep);
  const TITLE = 'R10 skeptic обращение';
  const o = await createPublished(ep, TITLE);
  // a draft that residents must not learn anything about
  const DRAFT_TITLE = 'R10 СКРЫТЫЙ черновик Жаркент';
  const dr = await call(ep, 'POST', '/staff/objects', objBody(DRAFT_TITLE, '2026-11-30'));
  const draftId = dr.json && dr.json.data ? dr.json.data.item.id : null;

  // ---------- A07: what the resident sees after submitting (+ X1 button contrast, X5 4xx URLs)
  if (PARTS.has('a07')) {
    const ctx = await browser.newContext({ viewport: D, deviceScaleFactor: 1, locale: 'ru-RU' });
    const p = await ctx.newPage();
    const bad = [];
    p.on('response', (r) => { if (r.status() >= 400) bad.push(r.status() + ' ' + r.request().method() + ' ' + r.url().replace(BASE, '')); });
    p.on('requestfailed', (r) => { if (!/openfreemap/.test(r.url())) bad.push('failed ' + r.url().replace(BASE, '') + ' ' + ((r.failure() || {}).errorText || '')); });
    try {
      await openHome(p, '#object=' + encodeURIComponent(o.id));
      await waitCard(p, TITLE);
      const fbBtn = p.locator('#civic-map-root [data-r03-action="feedback"]');
      // X1: contrast of the "Задать вопрос" button (screenshot 15 looked dark-on-dark): idle / hover / form open
      const styleOf = () => p.evaluate(() => { const b = document.querySelector('#civic-map-root [data-r03-action="feedback"]'); if (!b) return null; const cs = getComputedStyle(b);
        return { color: cs.color, background: cs.backgroundColor, focused: document.activeElement === b, hover: b.matches(':hover') }; });
      await p.mouse.move(1000, 600); await p.waitForTimeout(250);
      await fbBtn.scrollIntoViewIfNeeded(); await p.mouse.move(1000, 600); await p.waitForTimeout(250);
      const idle = await styleOf();
      const ishot = path.join(SHOTS, 'kx1_feedback_button_idle_1440x900.png');
      { const bb = await fbBtn.boundingBox(); await p.screenshot({ path: ishot, clip: { x: Math.max(0, bb.x - 30), y: Math.max(0, bb.y - 60), width: bb.width + 60, height: bb.height + 90 } }); }
      await fbBtn.hover(); await p.waitForTimeout(250);
      const hover = await styleOf();
      let colorRules = [];
      try {
        const cdp = await p.context().newCDPSession(p);
        await cdp.send('DOM.enable'); await cdp.send('CSS.enable');
        const { root } = await cdp.send('DOM.getDocument');
        const { nodeId } = await cdp.send('DOM.querySelector', { nodeId: root.nodeId, selector: '#civic-map-root [data-r03-action="feedback"]' });
        await cdp.send('CSS.forcePseudoState', { nodeId, forcedPseudoClasses: ['hover'] });
        const m = await cdp.send('CSS.getMatchedStylesForNode', { nodeId });
        colorRules = (m.matchedCSSRules || []).filter((x) => x.rule.style.cssProperties.some((pr) => pr.name === 'color' || pr.name === 'background' || pr.name === 'background-color'))
          .map((x) => ({ selector: x.rule.selectorList.text, origin: x.rule.origin, props: x.rule.style.cssProperties.filter((pr) => ['color', 'background', 'background-color'].includes(pr.name) && pr.value).map((pr) => pr.name + ':' + pr.value) }));
        await cdp.send('CSS.forcePseudoState', { nodeId, forcedPseudoClasses: [] });
        await cdp.detach();
      } catch (x) { colorRules = ['cdp error: ' + String(x && x.message || x).slice(0, 120)]; }
      const hshot = path.join(SHOTS, 'kx1_feedback_button_hover_1440x900.png');
      { const bb = await fbBtn.boundingBox(); await p.screenshot({ path: hshot, clip: { x: Math.max(0, bb.x - 10), y: Math.max(0, bb.y - 10), width: bb.width + 20, height: bb.height + 20 } }); }
      await fbBtn.click();
      const box = (s) => p.locator('#civic-feedback-box ' + s);
      await box('textarea').waitFor({ timeout: 10000 });
      await p.mouse.move(1000, 600); await p.waitForTimeout(250);
      const open = await styleOf();
      const same = (st) => !!st && st.color === st.background;
      rec('K-X1-feedback-button', '1440x900', same(idle) || same(open) ? 'FAIL' : 'PASS', { idle, hover, form_open_mouse_away: open, text_colour_equals_background: { idle: same(idle), form_open: same(open) }, matched_rules_with_hover_forced: colorRules }, [path.relative(REPO, ishot), path.relative(REPO, hshot)]);
      const before = await p.evaluate(() => (document.querySelector('#civic-feedback-box .civic-r06-official') || {}).innerText || '');
      await box('select').first().selectOption('sidewalks');
      await box('textarea').fill('R10 skeptic: на тротуаре нет обхода ограждения у остановки');
      await box('input[type="radio"][value="true"]').check();
      const [resp] = await Promise.all([
        p.waitForResponse((r) => r.request().method() === 'POST' && r.url().endsWith(API + '/feedback'), { timeout: 20000 }),
        box('button[type="submit"]').click(),
      ]);
      await box('.civic-r06-receipt').waitFor({ timeout: 10000 });
      await p.waitForTimeout(400);
      const seen = await p.evaluate(() => {
        const boxEl = document.getElementById('civic-feedback-box');
        // the scroll container that clips the panel content
        let sc = boxEl.parentElement; while (sc && sc !== document.body) { const o = getComputedStyle(sc).overflowY; if ((o === 'auto' || o === 'scroll') && sc.scrollHeight > sc.clientHeight) break; sc = sc.parentElement; }
        const vr = sc && sc !== document.body ? sc.getBoundingClientRect() : { top: 0, bottom: innerHeight, left: 0, right: innerWidth };
        const visible = (el) => { const r = el.getBoundingClientRect(); return r.height > 0 && r.bottom > Math.max(vr.top, 0) && r.top < Math.min(vr.bottom, innerHeight); };
        const els = [...boxEl.querySelectorAll('p, div, li, h3, h4')].filter((el) => /iKOMEK|eOtinish/.test(el.textContent) && ![...el.children].some((c) => /iKOMEK|eOtinish/.test(c.textContent)));
        const receipt = boxEl.querySelector('.civic-r06-receipt');
        const notice = receipt && receipt.querySelector('.civic-r06-official');
        return {
          box_text_mentions: { iKOMEK: /iKOMEK/.test(boxEl.innerText), eOtinish: /eOtinish/.test(boxEl.innerText) },
          receipt_mentions: { iKOMEK: /iKOMEK/.test(receipt.innerText), eOtinish: /eOtinish/.test(receipt.innerText) },
          mention_elements: els.map((el) => ({ cls: el.className, text: el.textContent.trim().slice(0, 160), visible_now: visible(el), inside_receipt: receipt.contains(el) })),
          receipt_notice: notice ? { text: notice.innerText.trim(), visible_now: visible(notice) } : null,
          form_still_present: !!boxEl.querySelector('form textarea'),
        };
      });
      const s = await shot(p, 'k14_receipt_view');
      // scroll the panel to the top of the feedback box to see what else the resident sees
      await p.evaluate(() => document.getElementById('civic-feedback-box').scrollIntoView({ block: 'start' }));
      await p.waitForTimeout(300);
      const s2 = await shot(p, 'k14b_receipt_box_top');
      rec('K-A07-receipt', '1440x900', resp.status() < 300 && seen.receipt_notice && /не выполняется/.test(seen.receipt_notice.text) ? 'PASS' : 'FAIL',
        { post_status: resp.status(), form_notice_before_submit: strip(before), ...seen }, [s, s2]);
    } catch (x) { rec('K-A07-receipt', '1440x900', 'ERROR', { error: String(x && x.message || x).split('\n')[0].slice(0, 300) }); }
    // X5: 4xx/failed requests on a resident page (load + card + feedback)
    rec('K-X5-resident-4xx', '1440x900', 'INFO', { responses_4xx_or_failed: bad });
    await ctx.close();
  }

  // ---------- X2: logged-in editor footer overflow, panel horizontal scroll after "Сообщения жителей"
  if (PARTS.has('x2')) try {
    await openHome(ep, '#object=' + encodeURIComponent(o.id));
    await waitCard(ep, TITLE);
    // the shell learns about the session only when the staff drawer is opened (no /session call on public load)
    await ep.locator('#civic-staff-button').click();
    await ep.locator('#civic-editor [data-fk="new"]').waitFor({ timeout: 15000 });
    await ep.locator('#civic-moderation-button').waitFor({ timeout: 15000 });
    const m0 = await ep.evaluate(() => { const f = document.querySelector('.civic-foot'); const b = document.getElementById('civic-moderation-button').getBoundingClientRect(); const pn = document.getElementById('civic-panel').getBoundingClientRect();
      return { foot_scroll_client: [f.scrollWidth, f.clientWidth], btn_right: Math.round(b.right), panel_right: Math.round(pn.right) }; });
    await ep.locator('#civic-moderation-button').click();
    await ep.waitForTimeout(800);
    const m1 = await ep.evaluate(() => { const out = []; document.querySelectorAll('#civic-panel, #civic-panel *').forEach((el) => { if (el.scrollLeft > 0) out.push({ el: el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + '.' + String(el.className).slice(0, 40), scrollLeft: el.scrollLeft }); });
      const t = document.querySelector('#civic-map-root .civic-r03-card-title'); const r = t ? t.getBoundingClientRect() : null; const pn = document.getElementById('civic-panel').getBoundingClientRect();
      return { h_scrolled: out, card_title_left: r ? Math.round(r.left) : null, panel_left: Math.round(pn.left) }; });
    const s = await shot(ep, 'kx2_moderation_open_panel');
    rec('K-X2-editor-footer', '1440x900', m1.h_scrolled.length ? 'FAIL' : 'PASS', { before_click: m0, after_click: m1 }, s);
  } catch (x) { rec('K-X2-editor-footer', '1440x900', 'ERROR', { error: String(x && x.message || x).split('\n')[0].slice(0, 300) }); }

  // ---------- X3: training-mode header overflow at 1440x900
  if (PARTS.has('x3')) {
    const ctx = await browser.newContext({ viewport: D, deviceScaleFactor: 1, locale: 'ru-RU' });
    const p = await ctx.newPage();
    try {
      await openHome(p);
      await p.locator('#civic-modes [data-mode="training"]').click();
      await p.waitForFunction(() => !document.body.classList.contains('civic-mode'));
      await p.waitForTimeout(1200);
      const h = await p.evaluate(() => { const top = document.querySelector('.topbar').getBoundingClientRect(); const c = document.querySelector('.top-center'); const cr = c.getBoundingClientRect();
        const kids = [...c.querySelectorAll('b, span')].map((k) => { const r = k.getBoundingClientRect(); return { text: k.textContent.trim().slice(0, 40), top: Math.round(r.top), bottom: Math.round(r.bottom) }; });
        return { topbar: [Math.round(top.top), Math.round(top.bottom)], top_center: [Math.round(cr.top), Math.round(cr.bottom), Math.round(cr.width)], center_scroll_client_h: [c.scrollHeight, c.clientHeight], overflow: getComputedStyle(c).overflow, kids,
          outside: kids.filter((k) => k.top < top.top - 1 || k.bottom > top.bottom + 1).length }; });
      const f = path.join(SHOTS, 'kx3_training_header_1440x900.png');
      await p.screenshot({ path: f, clip: { x: 0, y: 0, width: 1440, height: 130 } });
      rec('K-X3-training-header', '1440x900', h.outside ? 'FAIL' : 'PASS', h, path.relative(REPO, f));
    } catch (x) { rec('K-X3-training-header', '1440x900', 'ERROR', { error: String(x && x.message || x).split('\n')[0].slice(0, 300) }); }
    await ctx.close();
  }

  // ---------- X4: assistant asked about a DRAFT id (A02 privacy) vs a non-existent id
  if (PARTS.has('x4')) {
    const ctx = await browser.newContext({ viewport: D, deviceScaleFactor: 1, locale: 'ru-RU' });
    const p = await ctx.newPage();
    try {
      await p.goto(BASE + '/favicon.svg');
      const q = 'Когда закончат работы и как называется объект?';
      const a1 = await call(p, 'POST', '/assistant', { question: q, object_id: draftId, scenario_id: null });
      const a2 = await call(p, 'POST', '/assistant', { question: q, object_id: 'ast-0000000000', scenario_id: null });
      const leak = (r) => { const t = JSON.stringify(r.json || {}); return { title: t.includes('СКРЫТЫЙ') || t.includes('Жаркент'), date: /2026-11-30|30\.11\.2026|30 ноября/.test(t) }; };
      const norm = (r) => JSON.stringify(r.json || {}).replace(draftId, '<id>').replace('ast-0000000000', '<id>');
      // through the UI: deep link to the draft, click the first assistant chip
      await openHome(p, '#object=' + encodeURIComponent(draftId));
      await p.waitForTimeout(800);
      let uiAnswer = null;
      const chip = p.locator('button', { hasText: 'Когда закончат работы?' }).first();
      if (await chip.count()) { await chip.click(); await p.waitForTimeout(2500); uiAnswer = strip(await p.evaluate(() => ['.civic-r09-status', '.civic-r09-answer'].map((s) => (document.querySelector(s) || {}).innerText || '').join(' | '))); }
      const pageLeak = await p.evaluate(() => /СКРЫТЫЙ|Жаркент|30 ноября|30\.11\.2026/.test(document.body.innerText));
      const s = await shot(p, 'kx4_assistant_on_draft');
      const ok = !leak(a1).title && !leak(a1).date && !pageLeak;
      rec('K-X4-assistant-draft', '1440x900', ok ? 'PASS' : 'FAIL', { draft_response: { status: a1.status, leak: leak(a1), body: JSON.stringify(a1.json).slice(0, 400) },
        nonexistent_response: { status: a2.status, body: JSON.stringify(a2.json).slice(0, 400) }, same_shape_as_nonexistent: norm(a1) === norm(a2), ui_answer: uiAnswer && uiAnswer.slice(0, 300), page_mentions_draft: pageLeak }, s);
    } catch (x) { rec('K-X4-assistant-draft', '1440x900', 'ERROR', { error: String(x && x.message || x).split('\n')[0].slice(0, 300) }); }
    await ctx.close();
  }

  await edCtx.close();
  await browser.close();
}

main().then(() => { R.finished_utc = new Date().toISOString(); save(); process.exit(0); })
  .catch((e) => { R.finished_utc = new Date().toISOString(); R.notes.push('aborted: ' + String(e && e.stack || e).slice(0, 600)); save(); console.error(e); process.exit(1); });
