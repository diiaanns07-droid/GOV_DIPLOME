// Помещается ли навигация-капсула эталона между поиском и профилем (ru/kk, 1366/1280/1024) — на макете ui-kit
// prototypes/reference-a.html (сервер статики web/ на 8766). node ref_navfit.cjs
const { chromium } = require('playwright');
const SETS = {
  'ru ref': ['Карта', 'Картина дня', 'Обращения', 'Проекты', 'Ещё'],
  'ru build': ['Карта', 'Картина дня', 'Обращения', 'Проекты и идеи', 'Ещё'],
  'kk build': ['Карта', 'Күн қорытындысы', 'Өтініштер', 'Жобалар мен идеялар', 'Тағы'],
  'kk short': ['Карта', 'Күн қорытындысы', 'Өтініштер', 'Жобалар', 'Тағы'],
  'ru resident': ['Карта', 'Мои обращения', 'Рядом', 'Идеи', 'Ещё'],
  'kk resident': ['Карта', 'Менің өтініштерім', 'Маңайда', 'Идеялар', 'Тағы'],
};
(async () => { const b = await chromium.launch();
  for (const w of [1366, 1280, 1024]) {
    const p = await b.newPage({ viewport: { width: w, height: 768 } });
    await p.goto('http://127.0.0.1:8766/civic/ui-kit/prototypes/reference-a.html?f=home', { waitUntil: 'networkidle' });
    await p.evaluate(() => { const f = document.querySelector('.ra-frame.is-on'); f.style.width = innerWidth + 'px'; });
    for (const [name, labels] of Object.entries(SETS)) {
      const r = await p.evaluate((labels) => {
        const nav = document.querySelector('.ra-frame.is-on .bk-navpill');
        [...nav.children].forEach((a, i) => a.textContent = labels[i]);
        const n = nav.getBoundingClientRect(), s = document.querySelector('.ra-frame.is-on .bk-searchbar').getBoundingClientRect(), m = document.querySelector('.ra-frame.is-on .bk-me').getBoundingClientRect();
        return { nav: Math.round(n.width), gapLeft: Math.round(n.left - s.right), gapRight: Math.round(m.left - n.right) };
      }, labels);
      console.log(w, name.padEnd(12), JSON.stringify(r), r.gapLeft < 12 || r.gapRight < 12 ? '✗ не помещается' : '');
    }
    await p.close();
  }
  await b.close(); })();
