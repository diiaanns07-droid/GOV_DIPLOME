// Макет эталона по-казахски (prototypes/reference-a.html?lang=kk): кадры <OUT>/kk-<f>.png, обрезанные строки, русские остатки,
// промежутки капсулы меню. node ref_kk_check.cjs <OUT> (сервер статики web/ на 8766)
const { chromium } = require('playwright');
(async () => { const b = await chromium.launch();
  for (const f of ['home','obj','proj','phone']) {
    const vp = f === 'phone' ? { width: 375, height: 812 } : { width: 1366, height: 768 };
    const p = await b.newPage({ viewport: vp });
    const errs = []; p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
    await p.goto('http://127.0.0.1:8766/civic/ui-kit/prototypes/reference-a.html?lang=kk&f=' + f, { waitUntil: 'networkidle' });
    await p.evaluate(() => document.fonts.ready); await p.waitForTimeout(300);
    await p.locator('.ra-frame.is-on').screenshot({ path: `${process.argv[2]}/kk-${f}.png` });
    const r = await p.evaluate(() => {
      const fr = document.querySelector('.ra-frame.is-on'); const out = { cut: [], ru: [] };
      fr.querySelectorAll('*').forEach(e => {
        if (e.closest('svg')) return;
        const cs = getComputedStyle(e);
        if ((cs.overflow === 'hidden' || cs.textOverflow === 'ellipsis' || cs.webkitLineClamp !== 'none') && e.scrollWidth > e.clientWidth + 1 && !e.matches('.ra-frame,.bk-objcard,.bk-psheet,.bk-pd,.bk-plist,.bk-thumb,.bk-pd__im')) out.cut.push((e.className || e.tagName) + ': ' + e.textContent.trim().slice(0, 40));
        const own = [...e.childNodes].filter(n => n.nodeType === 3).map(n => n.nodeValue).join('').trim();
        if (/[а-яё]{3,}/i.test(own) && !/[әғқңөұүһі]/i.test(own) && !/^(Карта|Профиль|ТК)/.test(own)) out.ru.push(own.slice(0, 40));
      });
      const s = fr.querySelector('.bk-searchbar'), n = fr.querySelector('.bk-navpill'), m = fr.querySelector('.bk-me');
      if (s && n && m) { const a = s.getBoundingClientRect(), c = n.getBoundingClientRect(), d = m.getBoundingClientRect(); out.nav = [Math.round(c.width), Math.round(c.left - a.right), Math.round(d.left - c.right)]; }
      return out; });
    console.log(f, JSON.stringify(r), errs.length ? 'errors ' + errs.join(';') : '');
    await p.close(); }
  await b.close(); })();
