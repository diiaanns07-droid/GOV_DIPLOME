// Геометрия эталона (http://127.0.0.1:8790/REFERENCE.html, вариант A) против макета ui-kit (http://127.0.0.1:8766/civic/ui-kit/prototypes/reference-a.html):
// для пар «элемент эталона → класс ui-kit» печатает [left, top, width, height] и разницу; ✗ — больше 1 px. node ref_geom.cjs
// Сравнение геометрии: эталон (REFERENCE.html, вариант A) против макета ui-kit (reference-a.html)
const { chromium } = require('playwright');
const MAP = {
  home: [['.search','.bk-searchbar'],['.chips','.bk-chip[aria-pressed=true]'],['.chips .chip.on','.bk-chip[aria-pressed=true]'],['.chips .chip:nth-child(2)','.bk-chip:nth-child(2)'],['.nav','.bk-navpill'],['.nav a.on','.bk-navpill [aria-current]'],['.me','.bk-me'],['.ava','.bk-ava'],
    ['.sum','.bk-sum'],['.sum .h','.bk-sum__hd'],['.kpi','.bk-kpi'],['.hot','.bk-hot'],['.hot:nth-of-type(4)','.bk-hot:nth-of-type(4)'],['.sum .more','.bk-sum .bk-more'],['.ctl','.bk-mapctl'],['.ctl .solo','.bk-mapctl > .bk-mapbtn'],['.ctl .cap','.bk-mapctl__group'],['.legend','.bk-legend'],['.pin .c','.bk-pin__c'],['.pin .n','.bk-pin__n']],
  obj: [['.card','.bk-objcard'],['.card .hd','.bk-objcard__hd'],['.card h2','.bk-objcard__title'],['.card .sub','.bk-objcard__sub'],['.card .x','.bk-objcard .bk-x'],['.big','.bk-big'],['.big b','.bk-big b'],['.st','.bk-stline'],['.acts','.bk-acts'],['.btn.p','.bk-btn--primary'],['.btn.s','.bk-acts .bk-btn:not(.bk-btn--primary)'],['.tabs','.bk-tabs'],['.tabs a.on','.bk-tabs [aria-selected=true]'],['.rows','.bk-rows'],['.row','.bk-row'],['.row .ic','.bk-row__ic'],['.quote','.bk-quote'],['.card .more','.bk-objcard .bk-more'],['.pin.sel .c','.bk-pin.is-sel .bk-pin__c']],
  proj: [['.sheet','.bk-psheet'],['.sheet .hd','.bk-psheet__hd'],['.seg','.bk-psheet .bk-seg'],['.seg span','.bk-psheet .bk-seg button'],['.plist','.bk-plist'],['.pc','.bk-pc'],['.thumb','.bk-thumb'],['.pc .t p','.bk-pc__title'],['.pc .t small','.bk-pc__sub'],['.pill','.bk-pill'],['.vote','.bk-vote'],['.pd','.bk-pd'],['.pd .im','.bk-pd__im'],['.pd h3','.bk-pd__title'],['.pd .facts','.bk-facts'],['.pd .facts div','.bk-facts > div'],['.pd .quote','.bk-pd .bk-quote'],['.pd .acts','.bk-pd .bk-acts'],['.pd .btn.p','.bk-pd .bk-btn--primary'],['.pd .in > p:last-child','.bk-pd__note'],['.tag','.bk-tag-proj']],
  phone: [['.p-search','.bk-psearch'],['.p-sheet','.bk-phsheet'],['.handle','.bk-handle'],['.p-sheet .hot','.bk-phsheet .bk-hot'],['.p-sheet .hot:last-of-type','.bk-phsheet .bk-hot:last-of-type'],['.fab','.bk-fab'],['.fab i','.bk-fab__ic']],
};
(async () => {
  const b = await chromium.launch();
  const rect = async (p, root, sel) => p.evaluate(([root, sel]) => { const r0 = document.querySelector(root).getBoundingClientRect(); const e = document.querySelector(root + ' ' + sel); if (!e) return null; const r = e.getBoundingClientRect(); const cs = getComputedStyle(e); return [Math.round(r.left - r0.left), Math.round(r.top - r0.top), Math.round(r.width), Math.round(r.height), cs.fontSize, cs.fontWeight, cs.color]; }, [root, sel]);
  for (const f of Object.keys(MAP)) {
    const vp = f === 'phone' ? { width: 375, height: 812 } : { width: 1366, height: 768 };
    const r = await b.newPage({ viewport: { width: 1500, height: 1000 } });
    await r.goto('http://127.0.0.1:8790/REFERENCE.html', { waitUntil: 'networkidle' });
    await r.click(`.switch button[data-f=${f}]`);
    await r.evaluate(() => document.querySelectorAll('.frame').forEach(x => x.style.transform = 'none'));
    const q = await b.newPage({ viewport: vp });
    await q.goto('http://127.0.0.1:8766/civic/ui-kit/prototypes/reference-a.html?f=' + f, { waitUntil: 'networkidle' });
    await q.evaluate(() => document.fonts.ready); await q.waitForTimeout(300);
    const rroot = f === 'phone' ? '#stagePhone .frame.on' : '#stage .frame.on';
    console.log('== ' + f);
    for (const [a, c] of MAP[f]) {
      const x = await rect(r, rroot, a), y = await rect(q, '.ra-frame.is-on', c);
      const d = x && y ? [0,1,2,3].map(i => y[i] - x[i]) : null;
      const bad = d && d.some(v => Math.abs(v) > 1);
      console.log((bad ? '✗ ' : '  ') + a.padEnd(26) + JSON.stringify(x && x.slice(0,4)) + ' → ' + JSON.stringify(y && y.slice(0,4)) + (d ? ' Δ' + JSON.stringify(d) : '') + (x && y && (x[4] !== y[4] || x[5] !== y[5]) ? `  font ${x[4]}/${x[5]} vs ${y[4]}/${y[5]}` : ''));
    }
    await r.close(); await q.close();
  }
  await b.close();
})();
