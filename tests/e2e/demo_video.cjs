// R10 · раунд 15 · демо-ролик Birge: автоматическая запись сценария v2 (IDEA §3) в Playwright, 1366×768, ҚАЗ и РУС.
//
//   NODE_PATH="$(npm root -g)" node tests/e2e/demo_video.cjs --root <папка сборки> --out <папка>
//        [--langs kk,ru] [--parts 0,1,2] [--world] [--basemap simplified|real] [--glass keep|off|auto]
//        [--subtitles <json>] [--pace 0.5] [--fast] [--no-mp4] [--skip project|none] [--cursor-steps 10]
//
// Что получается в <out> (на каждый язык):
//   birge-demo-<lang>.webm — запись Playwright (как есть);  birge-demo-<lang>.mp4 — H.264 для заявки (если есть ffmpeg);
//   birge-demo-<lang>.vtt / .srt — субтитры с временем (те же, что «вшиты» в кадр);  кадры <lang>-<шаг>.jpg;
//   MANIFEST.json — сборка, длительность, сцены с временем, что пропущено и почему.
// Субтитры, пометка «Пример / упрощённая подложка» и курсор рисуются слоем поверх страницы (pointer-events: none) —
// нажатиям не мешают и уже есть в видео. Текст — tests/e2e/fixtures/video_subtitles.json (черновик R10; окончательный —
// docs/gton/VIDEO_SCRIPT.md R14, казахский проверяет R11), --subtitles <файл> — свой текст.
// Облако: подложка OpenFreeMap не грузится — карта с упрощённым фоном, в кадре это подписано (--basemap simplified).
// Ноутбук с интернетом (LOCAL-16): --basemap real — пометка про подложку не ставится.
// Сценарий: сцена 0 — «ИИ-разбор пачки обращений» R04 (поправка П3; есть экран — снимается первой, субтитры intake /
// intake_result R14); часть 1 — шаги 1–7 DEMO_SCRIPT R01 (FINAL-4); часть 2 — сцены 7–9 «Бірге» (IDEA §3), если их модули есть в
// сборке; нет модуля — сцена не записывается, причина в MANIFEST (в ролике — одна строка «появятся в FINAL-5»).
// Каждый язык — свой сервер с чистой временной базой (сценарий меняет данные: «Я тоже», проект, статусы).
"use strict";
const { chromium } = require("playwright");
const { execFileSync } = require("child_process");
const fs = require("fs"), path = require("path"), os = require("os");
const L = require("./r10_lib.cjs");
const { sleep, T, esc, textRe, firstVisible } = L;

const args = L.parseArgs(process.argv.slice(2));
const ROOT = path.resolve(args.root || path.join(__dirname, "../.."));
const OUT = path.resolve(args.out || path.join(os.tmpdir(), "r10-video"));
const LANGS = String(args.langs || "kk,ru").split(",");
const PARTS = String(args.parts || "0,1,2").split(",").map(Number);
const [W, H] = String(args.size || "1366x768").split("x").map(Number);
const FAST = !!args.fast;                       // паузы ×0,35 — пробный прогон, не для показа
const STEPS = Math.max(4, Math.min(30, Number(args["cursor-steps"] || 10)));  // шаги движения курсора к кнопке
let stepsNow = STEPS;
// Сцены, которые не снимаем (--skip project,…). С 15 окт шаг 5 (проект в 3D) снимается по умолчанию: R05 сдал «белый
// макет» (AMENDMENTS П1, правило 3), а с курсором 10 / 6 шагов ролик с частью 2 — 4:49 ҚАЗ / 4:44 РУС (ветка R01 B0.9).
const SKIP = new Set(String(args.skip === undefined ? "none" : args.skip).split(",").filter((x) => x && x !== "none" && x !== "true"));
const BASEMAP = args.basemap === "real" ? "real" : "simplified";
const GLASS = args.glass === "auto" ? null : String(args.glass || "keep");
const SUBS = JSON.parse(fs.readFileSync(path.resolve(args.subtitles || path.join(__dirname, "fixtures/video_subtitles.json")), "utf8"));
const STOP = { id: "osm-node-4109037549", name: "Хан Шатыр", name_kk: "Хан Шатыр", point: [71.406553, 51.131155] };
const PLACE = [71.4148, 51.1131];               // место сквера (как demo_flow.cjs)
const SHOT_Q = 72;

// pause — паузы для зрителя (в --fast короче); ожидания ответа интерфейса — wait (всегда полные, иначе шаги не проходят).
// --pace — множитель пауз для зрителя (0,7 по умолчанию: часть 1 ≈ 3 мин, весь ролик ≤ 5 мин); --fast — 0,35.
// Темп пауз: 0,6 — ролик ≤ 5 мин (VISUAL_BRIEF №12) с частью 2; субтитр всё равно держится не меньше времени чтения.
const PACE = FAST ? 0.35 : Math.max(0.3, Math.min(2, Number(args.pace || 0.5)));
const pause = (ms) => sleep(Math.round(ms * PACE));
// Время чтения субтитра идёт вместе с действиями сцены (их субтитр и описывает): say() ждёт только паузу сцены, а следующий
// субтитр (или quiet) не заменит текущий, пока тот не провисел len / READ_CPS с. Раньше say() ждал чтения целиком минус 2 с
// и только потом шли нажатия — ролик ҚАЗ был 4:49–4:55 из 5:00, а вычитка R11 удлинила казахский текст на ~80 знаков.
const READ_CPS = 17;   // знаков в секунду: удобная скорость чтения субтитров (норма 15–17); 17 — запас под 5 мин для ҚАЗ
const wait = (ms) => sleep(ms);
const log = (...xs) => console.log(new Date().toISOString().slice(11, 19), ...xs);
const dbg = (...xs) => { if (process.env.R10V_DEBUG) log("  ·", ...xs); };

// ------------------------------------------------------------------------------------------------ слой поверх страницы
// Субтитры внизу по центру, пометка о данных справа внизу, заголовок части сверху, курсор и «круг» нажатия.
// Всё — pointer-events: none и z-index максимальный: интерфейс под слоем работает как обычно.
function overlayScript() {
  const css = `
  /* Субтитры: правее строки легенды (слева внизу) и выше подписи © OpenStreetMap (ODbL — её не закрываем). */
  #r10v-sub{position:fixed;left:400px;right:96px;bottom:58px;display:flex;justify-content:center;opacity:0;
    transition:opacity .22s ease-out;pointer-events:none;z-index:2147483646}
  /* Текст слоя — через content: attr(data-t): поиск элементов по тексту (getByText) его не видит и не путает с интерфейсом. */
  #r10v-sub span{display:inline-block;max-width:100%;padding:9px 16px;border-radius:12px;background:rgba(14,18,16,.84);
    color:#fff;font:500 19px/1.38 Inter,"Segoe UI",Arial,sans-serif;text-align:center;letter-spacing:.005em;
    box-shadow:0 6px 24px rgba(0,0,0,.22)}
  #r10v-sub span::after,#r10v-badge::after,#r10v-title::after{content:attr(data-t)}
  #r10v-sub.on{opacity:1}
  /* Низ занят интерфейсом (шторка каталога, лист, форма) — субтитр наверху, под капсулой разделов. */
  #r10v-sub.top{top:84px;bottom:auto;left:530px;right:20px}
  #r10v-sub.raise{bottom:150px}
  @media (max-width:900px){#r10v-sub{left:12px;right:12px;bottom:96px}}
  /* Пометка о данных: справа сверху, под «ҚАЗ · РУС» и аватаром. */
  #r10v-badge{position:fixed;right:20px;top:74px;max-width:430px;padding:5px 10px;border-radius:8px;
    background:rgba(255,255,255,.9);color:#3b4541;font:500 12.5px/1.35 Inter,"Segoe UI",Arial,sans-serif;text-align:right;
    box-shadow:0 1px 6px rgba(0,0,0,.12);pointer-events:none;z-index:2147483646}
  #r10v-badge.low{top:auto;bottom:60px}
  #r10v-badge.off{display:none}
  #r10v-title{position:fixed;left:50%;top:78px;transform:translateX(-50%);padding:6px 14px;border-radius:999px;
    background:rgba(14,18,16,.78);color:#fff;font:600 15px/1.3 Inter,"Segoe UI",Arial,sans-serif;opacity:0;
    transition:opacity .25s ease-out;pointer-events:none;z-index:2147483646}
  #r10v-title.on{opacity:1}
  #r10v-cur{position:fixed;left:0;top:0;width:18px;height:18px;margin:-9px 0 0 -9px;border-radius:50%;
    background:rgba(20,24,22,.55);border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.35);pointer-events:none;
    z-index:2147483647;transition:transform .08s ease-out}
  #r10v-cur.down{transform:scale(.75)}
  .r10v-ring{position:fixed;width:44px;height:44px;margin:-22px 0 0 -22px;border-radius:50%;border:3px solid rgba(232,93,4,.85);
    pointer-events:none;z-index:2147483647;animation:r10vring .5s ease-out forwards}
  @keyframes r10vring{from{transform:scale(.4);opacity:1}to{transform:scale(1.25);opacity:0}}`;
  const mount = () => {
    if (document.getElementById("r10v-sub") || !document.body) return;
    const st = document.createElement("style"); st.textContent = css; document.head.appendChild(st);
    for (const id of ["r10v-sub", "r10v-badge", "r10v-title", "r10v-cur"]) {
      const d = document.createElement("div"); d.id = id; d.setAttribute("aria-hidden", "true"); document.body.appendChild(d);
    }
    const cur = document.getElementById("r10v-cur");
    const pos = window.__r10vPos || { x: innerWidth / 2, y: innerHeight / 2 };
    cur.style.left = pos.x + "px"; cur.style.top = pos.y + "px";
    document.addEventListener("mousemove", (e) => { cur.style.left = e.clientX + "px"; cur.style.top = e.clientY + "px";
      window.__r10vPos = { x: e.clientX, y: e.clientY }; }, true);
    document.addEventListener("mousedown", (e) => { cur.classList.add("down");
      const r = document.createElement("div"); r.className = "r10v-ring"; r.style.left = e.clientX + "px"; r.style.top = e.clientY + "px";
      document.body.appendChild(r); setTimeout(() => r.remove(), 600); }, true);
    document.addEventListener("mouseup", () => cur.classList.remove("down"), true);
    const s = window.__r10vState || {};
    if (s.badge) window.__r10v.badge(s.badge);
    if (s.sub) window.__r10v.sub(s.sub);
    // Место субтитров: внизу, если там карта; если низ занят панелью интерфейса, а верх свободен — наверху.
    const mine = (n) => n.closest && n.closest("#r10v-sub,#r10v-badge,#r10v-title,#r10v-cur,.r10v-ring");
    const mapLike = (n) => !n || n === document.body || n === document.documentElement
      || (n.closest && n.closest(".maplibregl-canvas-container, .maplibregl-marker, .maplibregl-ctrl-attrib, .b3d-labels"));
    const busy = (x0, y0, x1, y1) => {
      for (let x = x0; x <= x1; x += 60) for (let y = y0; y <= y1; y += 22) {
        const hit = document.elementsFromPoint(x, y).find((n) => !mine(n));
        if (!mapLike(hit)) return true;
      }
      return false;
    };
    setInterval(() => {
      const sub = document.getElementById("r10v-sub"), badge = document.getElementById("r10v-badge");
      if (!sub || !badge || innerWidth < 900) return;
      const W = innerWidth, H = innerHeight;
      // Низ занят (сообщение «Голос учтён», панель) — наверх; занят и верх (баннер кризиса) — чуть выше нижних сообщений.
      const low = busy(400, H - 132, W - 96, H - 62), high = busy(540, 128, W - 20, 160);
      const top = low && !high;
      sub.classList.toggle("top", top);
      sub.classList.toggle("raise", low && high && !busy(400, H - 212, W - 96, H - 152));  // выше — только если там свободно
      // Пометка «Демо-запись…»: на стороне, противоположной субтитру (субтитр внизу — пометка справа под шапкой,
      // наверху — справа внизу), и только если там нет интерфейса (баннер кризиса, кнопки панели); иначе прячем.
      const bh = badge.offsetHeight || 40, y = top ? H - 60 - bh : 74;
      const free = !busy(W - 440, y + 2, W - 24, y + bh - 2);
      badge.classList.toggle("low", top);
      badge.classList.toggle("off", !free);
    }, 250);
  };
  window.__r10v = {
    sub(text) { (window.__r10vState = window.__r10vState || {}).sub = text; const el = document.getElementById("r10v-sub");
      if (!el) return; if (!text) { el.classList.remove("on"); return; }
      const span = document.createElement("span"); span.dataset.t = text; el.replaceChildren(span); el.classList.add("on"); },
    badge(text) { (window.__r10vState = window.__r10vState || {}).badge = text; const el = document.getElementById("r10v-badge");
      if (el) el.dataset.t = text || ""; if (el) el.style.display = text ? "" : "none"; },
    title(text) { const el = document.getElementById("r10v-title"); if (!el) return;
      if (!text) { el.classList.remove("on"); return; } el.dataset.t = text; el.classList.add("on"); },
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount); else mount();
}

// ------------------------------------------------------------------------------------------------ запись одного языка
async function recordLang(browser, lang) {
  const srv = await L.startServer(ROOT, { demo: true, staff: true, world: !!args.world });
  const dict = L.loadDict(ROOT, lang);
  const sub = (key) => (SUBS[key] && (SUBS[key][lang] || SUBS[key].ru)) || "";
  const tmpVideo = fs.mkdtempSync(path.join(os.tmpdir(), "r10-video-"));
  const ctx = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 1,
    locale: lang === "kk" ? "kk-KZ" : "ru-RU", recordVideo: { dir: tmpVideo, size: { width: W, height: H } } });
  await L.glassMode(ctx, GLASS);
  // Язык интерфейса — до первой загрузки (как выбор человека, сохранённый в браузере), чтобы ролик не начинался с РУС.
  await ctx.addInitScript((lg) => { try { if (!sessionStorage.getItem("r10v-lang")) { localStorage.setItem("birge.lang", lg);
    localStorage.setItem("civic.lang", lg); sessionStorage.setItem("r10v-lang", "1"); } } catch (e) { /* без хранилища */ } }, lang);
  await ctx.addInitScript(overlayScript);
  // Вход сотрудника — до записи, через API (cookie сессии в контексте): вход не функция для показа, а 10 с ролика.
  let preLogin = false;
  if (srv.staff && srv.staff.user) {
    const r = await ctx.request.post(srv.base + "api/civic/v1/session/login", { data: { username: srv.staff.user, password: srv.staff.pass },
      headers: { Origin: srv.base.replace(/\/$/, "") } }).catch(() => null);
    preLogin = !!(r && r.ok());
  }
  const page = await ctx.newPage();
  const t0 = Date.now();
  const cues = [], scenes = [], skipped = [], shots = [];
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message.slice(0, 200)));
  let open = null, trim = 0, readUntil = 0;
  const at = () => (Date.now() - t0) / 1000;
  // Субтитр на экране не меньше времени чтения (1 с на READ_CPS знаков, кроме --fast): дочитать перед заменой.
  const readOut = async () => { const w = readUntil - Date.now(); if (w > 0) await sleep(w); };
  const say = async (key, hold = 4200, vars = {}) => {
    let text = sub(key);
    for (const [k, v] of Object.entries(vars)) text = text.replace("{" + k + "}", v);
    await readOut();
    if (open) { open.end = at(); cues.push(open); }
    open = text ? { start: at(), end: null, text, key } : null;
    await page.evaluate((x) => window.__r10v && window.__r10v.sub(x), text).catch(() => null);
    readUntil = Date.now() + (FAST || !text ? 0 : Math.round(text.length / READ_CPS * 1000));
    await sleep(Math.round(hold * PACE));
  };
  const quiet = async () => { await readOut(); if (open) { open.end = at(); cues.push(open); open = null; }
    await page.evaluate(() => window.__r10v && window.__r10v.sub("")).catch(() => null); };
  const title = async (text, ms = 2600) => { await page.evaluate((x) => window.__r10v && window.__r10v.title(x), text).catch(() => null);
    await pause(ms); await page.evaluate(() => window.__r10v && window.__r10v.title("")).catch(() => null); };
  // Новая сцена — с чистого кадра: прошлый субтитр дочитывается и уходит до перехода (иначе подпись табло висела бы над
  // «Календарём работ»). Внутри сцены чтение идёт вместе с действиями.
  const scene = async (id) => { await quiet(); const s = { id, start: at(), end: null, ok: true, notes: [] }; scenes.push(s); return s; };
  const done = (s, ok = true, note) => { s.end = at(); s.ok = s.ok && ok; if (note) s.notes.push(note); log(lang, s.id, ok ? "ok" : "НЕ ВЫШЛО", note || ""); };
  const shot = async (name) => { const f = path.join(OUT, `${lang}-${name}.jpg`);
    await page.screenshot({ path: f, type: "jpeg", quality: SHOT_Q }).catch(() => null); shots.push(path.basename(f)); };

  // Плавный курсор: к центру элемента за ~0,5 с, затем нажатие.
  // Шаги курсора: каждый шаг ждёт кадра страницы; на 3D-карте в облаке (программный WebGL) кадр ~0,4 с, и 18 шагов
  // съедали секунды на каждое нажатие (шаг 5 — 64 с). 10 шагов — движение ещё видно; в 3D-сцене — 6.
  const moveTo = async (x, y, steps = stepsNow) => { await page.mouse.move(x, y, { steps: FAST ? 4 : steps }); };
  const press = async (loc, after = 900) => {
    if (!loc) return false;
    await loc.scrollIntoViewIfNeeded({ timeout: 2000 }).catch(() => null);
    const b = await loc.boundingBox().catch(() => null);
    if (!b) return false;
    await moveTo(b.x + b.width / 2, b.y + b.height / 2);
    await pause(180);
    await page.mouse.click(b.x + b.width / 2, b.y + b.height / 2);
    await sleep(after);
    return true;
  };
  const button = async (re, scope = page, role = "button") => firstVisible(scope.getByRole(role, { name: re }));
  const pressText = async (re, wait, scope, role) => press(await button(re, scope, role), wait);
  const word = (key, ru, kk) => T(dict, key, lang === "kk" ? kk : ru);
  const exact = (s) => new RegExp("^" + esc(s) + "$", "i");
  // Кнопки шапки и меню аватара — как demo_flow (L.headerClick), но с видимым движением курсора к аватару.
  const header = async (re, wait = 1200) => {
    const own = await firstVisible(page.getByRole("button", { name: re }).and(page.locator(":not(.birge-avatar)")));
    if (own) return press(own, wait);
    const avatar = await firstVisible(page.locator(".birge-avatar"));
    if (avatar) { await press(avatar, 500); }
    const menu = await firstVisible(page.locator("#birge-account"));
    if (menu) for (const role of ["menuitemradio", "menuitem", "button", "link"]) {
      const it = await firstVisible(menu.getByRole(role, { name: re }));
      if (it) return press(it, wait);
    }
    await page.keyboard.press("Escape").catch(() => null);
    return false;
  };
  const setMode = (mode) => header(exact(mode === "resident" ? word("common.role.resident", "Житель", "Тұрғын") : word("common.role.akimat", "Акимат", "Әкімдік")), 1400);
  // Карта: плавный перелёт к точке (кинематографично), затем точка на свободной части холста (как demo_flow showPoint).
  const flyTo = async (p, zoom, ms = 2200) => page.evaluate(async ([pp, z, d]) => {
    // eslint-disable-next-line no-undef
    const m = typeof map !== "undefined" && map && map.flyTo ? map : null;
    if (!m) return false;
    m.flyTo({ center: pp, zoom: z, pitch: 0, bearing: 0, duration: d, essential: true });
    await new Promise((ok) => setTimeout(ok, d + 300));
    return true;
  }, [p, zoom, FAST ? 600 : ms]).catch(() => false);

  try {
    await page.goto(srv.base + (BASEMAP === "real" ? "" : ""));
    await page.waitForFunction(() => document.readyState === "complete" && document.body.innerText.length > 50, null, { timeout: 40000 }).catch(() => null);
    await wait(2500);
    // Язык: если интерфейс открылся не на нужном языке — переключатель в шапке.
    const langNow = await page.evaluate(() => document.documentElement.lang).catch(() => "");
    if (langNow !== lang) { const b = await button(lang === "kk" ? /^(·\s*)?ҚАЗ$/ : /^(·\s*)?РУС$/); if (b) { await press(b, 1200); } }
    await page.evaluate((x) => window.__r10v && window.__r10v.badge(x), sub(BASEMAP === "real" ? "badge_real" : "badge")).catch(() => null);
    trim = Math.max(0, at() - 0.4);  // начало ролика — готовая карта, без белой страницы загрузки

    if (PARTS.includes(0)) await part0();
    if (PARTS.includes(1)) await part1();
    if (PARTS.includes(2)) await part2();
    await say("final", 6500);
    await quiet();  // дочитать последний субтитр целиком
    await pause(1200);
  } catch (e) {
    errors.push("сценарий: " + String(e.message || e).slice(0, 300));
    log(lang, "ошибка сценария", e.message);
  }
  const video = page.video();
  await ctx.close();
  const raw = video ? await video.path().catch(() => null) : null;
  await srv.stop();
  const base = path.join(OUT, `birge-demo-${lang}`);
  let webm = null, mp4 = null;
  if (raw && fs.existsSync(raw)) { webm = base + ".webm"; fs.copyFileSync(raw, webm); }
  fs.rmSync(tmpVideo, { recursive: true, force: true });
  if (open) { open.end = at(); cues.push(open); }
  if (webm && !args["no-mp4"]) mp4 = toMp4(webm, base + ".mp4", trim);
  // Субтитры — по времени .mp4 (он начинается с готовой карты); нет .mp4 — по времени .webm.
  const shift = mp4 ? trim : 0;
  const timed = cues.map((c) => ({ ...c, start: Math.max(0, c.start - shift), end: Math.max(0, c.end - shift) }));
  fs.writeFileSync(base + ".vtt", toVtt(timed));
  fs.writeFileSync(base + ".srt", toSrt(timed));
  const duration = mp4 ? probeDuration(mp4) : webm ? probeDuration(webm) : null;
  return { lang, webm: webm && path.basename(webm), mp4: mp4 && path.basename(mp4), vtt: path.basename(base + ".vtt"),
    srt: path.basename(base + ".srt"), duration_s: duration ?? Math.round(at()), trim_s: Math.round(shift * 10) / 10, pace: PACE,
    bytes: webm ? fs.statSync(webm).size : 0,
    mp4_bytes: mp4 ? fs.statSync(mp4).size : 0, scenes, skipped, cues: cues.length, shots, page_errors: errors.slice(0, 8),
    seeds: srv.seeds };

  // ---------------------------------------------------------------------------------------------- сцена 0 (П3)
  // «Ночью пришли сотни обращений» → «Пример: обращения за ночь» → «Разобрать» → итог (числа считает код) → «Создать
  // задачи». Вход сотрудника — до записи (preLogin). Экрана R04 нет — сцена не снимается, причина в MANIFEST.
  async function part0() {
    const has = await page.evaluate(() => !!window.BirgeIntake).catch(() => false);
    if (!has || !preLogin) { skipped.push({ scene: "intake", why: !has ? "экрана R04 «Разбор обращений» нет в сборке (П3)" : "вход сотрудника не удался" }); return; }
    const s = await scene("intake");
    const title0 = T(dict, "shell.palette.scene0", lang === "kk" ? "0-көрініс · ЖИ-талдау" : "Сцена 0 · ИИ-разбор");
    await page.evaluate((x) => window.__r10v && window.__r10v.title(x), title0).catch(() => null);
    await setMode("akimat");
    // Как ведущий: Ctrl+K «Сцена 0» (R01); нет команды — адрес #intake.
    let via = "hash";
    await page.keyboard.press("Control+k").catch(() => null);
    await pause(500);
    const input = await firstVisible(page.locator(".birge-palette__input"));
    if (input) {
      await input.type(title0.split("·")[0].trim(), { delay: FAST ? 0 : 45 }).catch(() => null);
      await pause(600);
      const offered = await page.evaluate((tt) => [...document.querySelectorAll(".birge-palette__item")].some((li) => (li.textContent || "").includes(tt)), title0).catch(() => false);
      if (offered) { await page.keyboard.press("Enter").catch(() => null); via = "ctrl+k"; } else await page.keyboard.press("Escape").catch(() => null);
    }
    if (via === "hash") await page.evaluate(() => { location.hash = "#intake"; }).catch(() => null);
    await pause(1600);
    await page.evaluate(() => window.__r10v && window.__r10v.title("")).catch(() => null);
    const SEL = "#birge-screen:not([hidden])";
    const scope = page.locator(SEL);
    await say("intake", 900);
    const sampled = await pressText(/пример|үлгі|мысал/i, 1400, scope);
    const ran = await pressText(lang === "kk" ? /^\s*(талда|талдау)/i : /^\s*разобрать/i, 600, scope);
    // Итог разбора — строка с числами; ждём до 12 с (живой счётчик).
    let line = null;
    for (let i = 0; i < 48 && ran && !line; i++) {
      line = await page.evaluate((sel) => { const r = document.querySelector(sel); if (!r) return null;
        for (const e of r.querySelectorAll("*")) { const txt = (e.innerText || "").trim(); if (txt.length < 160 && /→/.test(txt) && (txt.match(/\d+/g) || []).length >= 4) return txt; }
        return null; }, SEL).catch(() => null);
      if (!line) await sleep(250);
    }
    // Счётчик итога R04 доигрывает ~0,7 с (числа растут до summary) — кадр и субтитр после него, по настоящему времени.
    await sleep(1500);
    await pause(600);
    await shot("0-intake");
    await say("intake_result", 2400);
    const why = await button(/почему так|неге|неліктен|себебі/i, scope);
    if (why) { await press(why, 2200); }
    const created = await pressText(lang === "kk" ? /құру|жасау/i : /создать задачи|создать/i, 2600, scope);
    await shot("0-created");
    done(s, sampled && ran && !!line, !sampled ? "нет кнопки «Пример»" : !ran ? "нет кнопки «Разобрать»" : !line ? "итог разбора не появился" : null);
    s.notes.push(`вход: ${via}; итог: ${line ? line.replace(/\s+/g, " ").slice(0, 100) : "—"}; создано: ${created}`);
  }

  // ---------------------------------------------------------------------------------------------- часть 1 (FINAL-4)
  async function part1() {
    // Заголовок части и вступление — сразу, вид «Акимат» включается под них (без пустых секунд в начале).
    let s = await scene("intro");
    await page.evaluate((x) => window.__r10v && window.__r10v.title(x), sub("part1")).catch(() => null);
    await say("intro", 2400);
    await page.evaluate(() => window.__r10v && window.__r10v.title("")).catch(() => null);
    await setMode("akimat");
    await pause(3600);
    await shot("0-intro");
    done(s);

    // Шаги 1–2: житель, жалоба на остановку, категория, «Я тоже».
    s = await scene("complaint");
    await setMode("resident");
    await say("s1", 1800);
    const startLabel = word("complaint.start.button", "Сообщить о проблеме", "Мәселе туралы хабарлау");
    const started = await pressText(textRe(startLabel), 1600);
    const formRe = textRe(word("complaint.step2.title", "Где проблема?", "Мәселе қай жерде?"));
    const form = started ? await firstVisible(page.getByRole("dialog").filter({ hasText: formRe })) : null;
    let picked = false;
    if (form) {
      const pt = await L.showPoint(page, STOP.point, 17);
      if (pt) { await moveTo(pt.x, pt.y); await pause(250); await page.mouse.click(pt.x, pt.y); await wait(2600); }
      const nameRe = new RegExp([STOP.name, STOP.name_kk].map(esc).join("|"), "i");
      const choice = await button(nameRe, form);
      if (!choice && pt && pt.near) { await page.mouse.click(pt.near.x, pt.near.y); await wait(2400); }
      picked = await press(await button(nameRe, form), 1500);
    }
    await shot("1-place");
    if (picked) {
      await say("s2", 600);
      const dlg = (await firstVisible(page.getByRole("dialog"))) || page;
      const box = await firstVisible(dlg.getByRole("textbox"));
      if (box) { await press(box, 300); await page.keyboard.type("Аялдамада жарық жоқ, вечером на остановке темно", { delay: FAST ? 5 : 30 }); }
      await wait(3600);
      await shot("2-category");
      const sendRe = textRe(word("complaint.step3.send", "Отправить", "Жіберу"));
      const nextRe = exact(word("complaint.wizard.next", "Далее", "Әрі қарай"));
      let sent = await pressText(sendRe, 2600, dlg);
      if (!sent) sent = await pressText(nextRe, 2600, dlg);
      const metooRe = exact(word("complaint.step4.metoo", "Я тоже", "Мен де"));
      const metoo = await button(metooRe);
      if (metoo) { await say("s2b", 1200); await press(metoo, 2600); }
      else await pressText(sendRe, 2600, (await firstVisible(page.getByRole("dialog"))) || page);
      await shot("2-sent");
      await pause(1500);
      // Закрыть окно подтверждения (Esc), вернуться на карту.
      await page.keyboard.press("Escape").catch(() => null);
      await pause(800);
      done(s, true);
    } else done(s, false, "форма жалобы или остановка не найдены");

    // Шаг 3: тепловая карта у акимата, «Горячие места».
    s = await scene("heat");
    await setMode("akimat");
    await say("s3", 600);
    await flyTo(STOP.point, 14.6, 2600);
    await pause(2600);
    await shot("3-heat");
    const allHot = exact(word("akim.today.all_hot", "Все горячие места", "Барлық шағымы көп орындар"));
    let hotOpen = await pressText(allHot, 1400, page, "link");
    if (!hotOpen) hotOpen = await pressText(allHot, 1400);
    if (hotOpen) {
      await say("s3b", 900);
      const hotRe = new RegExp("^" + esc(word("heat.hot_title", "Горячие места", "Шағымы көп орындар")), "i");
      const items = page.locator("section").filter({ has: page.getByRole("heading", { name: hotRe }) }).getByRole("listitem").getByRole("button");
      if (await items.count().catch(() => 0)) { await press(items.first(), 2800); await shot("3-hot"); await pause(1800); }
      await page.keyboard.press("Escape").catch(() => null); await pause(700);
      await page.keyboard.press("Escape").catch(() => null); await pause(700);
    }
    done(s, hotOpen, hotOpen ? null : "ссылки «Все горячие места» нет");

    // Шаг 4: «Картина дня».
    s = await scene("day");
    const dayRe = exact(word("common.nav.day", "Картина дня", "Күн қорытындысы"));
    const day = await header(dayRe, 2600);
    if (day) {
      await say("s4", 2400);
      await shot("4-day");
      await page.mouse.move(W / 2, H / 2);
      for (let i = 0; i < 3; i++) { await page.mouse.wheel(0, 300); await pause(900); }
      await pause(900);
      for (let i = 0; i < 3; i++) { await page.mouse.wheel(0, -300); await pause(200); }
      const mapRe = exact(word("common.nav.map", "Карта", "Карта"));
      if (!(await header(mapRe, 1500))) await page.evaluate(() => window.BirgeShell && window.BirgeShell.setSection("map")).catch(() => null);
    }
    done(s, day, day ? null : "раздела «Картина дня» нет");

    // Шаг 5: вход сотрудника → «Что построить?» → «Сквер» → место → «Поставить» → 3D; житель «За».
    let login = preLogin;
    const doProject = !SKIP.has("project");
    if (!doProject) skipped.push({ scene: "project", owner: "R05",
      why: "шаг 5 (проект в 3D) не снимался: --skip project" });
    if (doProject) s = await scene("project");
    if (doProject && !login && srv.staff && srv.staff.user) {
      if (await header(textRe(lang === "kk" ? "Қызметкерлерге" : "Для сотрудников"), 1600)) {
        const user = await firstVisible(page.locator("input[autocomplete=username], input[name=username]"));
        const pass = await firstVisible(page.locator("input[type=password]"));
        if (user && pass) {
          // Вход без посимвольного набора: пароль не «печатается» в кадре, сцена короче.
          await press(user, 150); await user.fill(srv.staff.user).catch(() => null);
          await press(pass, 150); await pass.fill(srv.staff.pass).catch(() => null);
          await page.keyboard.press("Enter"); await wait(2400);
          login = !!(await button(/^(Выйти|Шығу)$/i));
          dbg("5: вход сотрудника", login);
          if (!(await pressText(/^(Закрыть кабинет|Кабинетті жабу)$/i, 900))) await page.keyboard.press("Escape").catch(() => null);
          await pause(600);
        }
      }
    }
    let placed = false;
    if (doProject) stepsNow = Math.min(6, STEPS);  // 3D-сцена: кадры дорогие — короче движения курсора
    if (doProject && login) {
      await say("s5", 600);
      const catalogTitle = word("proposal.catalog.title", "Что построить?", "Не салайық?");
      const catalogShown = !!(await firstVisible(page.getByText(textRe(catalogTitle))));
      dbg("5: каталог виден до слоя", catalogShown);
      if (!catalogShown) {
        const layersRe = exact(word("shell.layers.label", "Слой на карте", "Картадағы қабат"));
        const lb = await button(layersRe);
        dbg("5: кнопка слоёв", !!lb);
        if (lb) { await press(lb, 700);
          const radio = await firstVisible(page.getByRole("radio", { name: new RegExp("^" + esc(word("shell.layers.projects", "Проекты", "Жобалар")), "i") }));
          dbg("5: пункт «Проекты»", !!radio);
          if (radio) { await moveTo(...(await center(radio))); await radio.evaluate((e) => e.click()).catch(() => null); await wait(1600); } }
        dbg("5: каталог после слоя", !!(await firstVisible(page.getByText(textRe(catalogTitle)))));
      }
      const kindName = word("proposal.kind.square", "Сквер", "Гүлзар");
      const aria = word("build3d.catalog.place", "{kind}: поставить на карту", "{kind}: картаға орнату").replace("{kind}", kindName);
      const kindRe = new RegExp("^(" + esc(kindName) + "|" + esc(aria) + ")$", "i");
      if (!(await button(kindRe))) dbg("5: развернуть каталог", await pressText(exact(catalogTitle), 1000));
      await flyTo(PLACE, 17, 1800);
      dbg("5: вид «Сквер»", await pressText(kindRe, 1200));
      const pt = await L.showPoint(page, PLACE, 17);
      dbg("5: точка на карте", !!pt);
      if (pt) { const x = pt.onCanvas ? pt.x : pt.near ? pt.near.x : pt.x, y = pt.onCanvas ? pt.y : pt.near ? pt.near.y : pt.y;
        await moveTo(x, y); await pause(300); await page.mouse.click(x, y); await wait(1400); }
      dbg("5: место выбрано");
      placed = await pressText(exact(word("proposal.place", "Поставить", "Орнату")), 3800);
      dbg("5: «Поставить»", placed);
      await shot("5-placed");
      const view3d = new RegExp("^(3D|" + esc(word("common.map.view3d", "Объёмный вид", "Көлемді көрініс")) + ")$", "i");
      if (await pressText(view3d, 2400)) { await shot("5-3d"); await pressText(view3d, 800); }
      dbg("5: 3D показан и выключен");
      // Житель голосует «За» по табличке проекта.
      await setMode("resident");
      dbg("5: режим «Житель»");
      await say("s5b", 600);
      const p2 = await L.showPoint(page, PLACE, 17);
      dbg("5: точка проекта у жителя", !!p2);
      const projRe = new RegExp("^" + esc(kindName) + ":.*2027", "i");
      // Табличка проекта ближе всего к месту — одним проходом в странице: цикл getByRole(name).nth(i) на большой странице
      // пересчитывает имена всех кнопок на каждом шаге (в пробе шага 5 — десятки секунд).
      const spot = p2 ? await page.evaluate(([src, px, py]) => {
        const rx = new RegExp(src, "i");
        let bestPt = null, bestDist = Infinity;
        for (const el of document.querySelectorAll("button, [role=button]")) {
          const name = (el.getAttribute("aria-label") || el.textContent || "").trim().replace(/\s+/g, " ");
          if (!rx.test(name)) continue;
          const b = el.getBoundingClientRect();
          if (b.width < 2 || b.height < 2 || b.bottom < 0 || b.top > innerHeight) continue;
          const d = Math.hypot(b.x + b.width / 2 - px, b.y + b.height / 2 - py);
          if (d < bestDist) { bestPt = { x: b.x + b.width / 2, y: b.y + b.height / 2 }; bestDist = d; }
        }
        return bestPt;
      }, [projRe.source, p2.x, p2.y]).catch(() => null) : null;
      let best = null;
      if (!spot) {  // запасной путь — по роли и имени, как раньше (медленно, но находит табличку без aria-label)
        const labels = page.getByRole("button", { name: projRe });
        let bestD = Infinity;
        for (let i = 0; i < Math.min(await labels.count().catch(() => 0), 30); i++) {
          const it = labels.nth(i); if (!(await it.isVisible().catch(() => false))) continue;
          const b = await it.boundingBox().catch(() => null); if (!b || !p2) continue;
          const d = Math.hypot(b.x + b.width / 2 - p2.x, b.y + b.height / 2 - p2.y); if (d < bestD) { best = it; bestD = d; }
        }
      }
      dbg("5: табличка проекта найдена", spot ? "в странице" : !!best);
      if (spot) { await moveTo(spot.x, spot.y); await pause(180); await page.mouse.click(spot.x, spot.y); await sleep(1600); }
      if (spot || best) { if (best) await press(best, 1600);
        await pressText(new RegExp("^" + esc(word("proposal.vote_up", "За", "Жақтаймын")) + "(\\s|:|\\d|$)", "i"), 2200);
        await shot("5-vote"); await page.keyboard.press("Escape").catch(() => null); await pause(600); }
    }
    stepsNow = STEPS;
    if (doProject) done(s, login && placed, !login ? "вход сотрудника не удался" : placed ? null : "проект не поставлен");

    // Шаги 6–7: служба → «Взять в работу» → «Отметить исправленным» → сообщение жителям; житель «Да, исправлено».
    s = await scene("fixed");
    let verified = false;
    if (login) {
      await setMode("akimat");
      await say("s6", 600);
      const st = await L.showPoint(page, STOP.point, 17);
      if (st) { await moveTo(st.x, st.y); await pause(250); await page.mouse.click(st.x, st.y); await wait(2400); }
      await pressText(textRe(word("target.take", "Взять в работу", "Жұмысқа алу")), 2000);
      const fix = await pressText(textRe(word("target.mark_fixed", "Отметить исправленным", "Түзетілді деп белгілеу")), 2400);
      const fixForm = fix ? await firstVisible(page.locator(".r07-fixform")) : null;
      if (fixForm) {
        const what = await firstVisible(fixForm.locator("input[name=what_done], textarea[name=what_done], textarea, input[type=text]"));
        if (what) { await press(what, 200); await page.keyboard.type(lang === "kk" ? "Шам ауыстырылды" : "Заменили лампу", { delay: FAST ? 5 : 45 }); }
        const send = (await firstVisible(fixForm.locator("button[type=submit]")))
          || (await button(textRe(word("fix.send", "Сообщить жителям", "Тұрғындарға хабарлау")), fixForm));
        if (send) await press(send, 2800);
      }
      await shot("6-fixed");
      await page.keyboard.press("Escape").catch(() => null); await pause(700);
      await setMode("resident");
      await say("s7", 600);
      const mineLabel = word("common.nav.mine", "Мои обращения", "Менің өтініштерім");
      if (await header(textRe(mineLabel), 1900)) {
        const box = (await firstVisible(page.getByRole("dialog").filter({ hasText: textRe(mineLabel) }))) || page;
        const yes = await button(exact(word("verify.yes", "Да, исправлено", "Иә, түзетілді")), box);
        if (yes) { await press(yes, 2600);
          verified = !!(await firstVisible(page.getByText(new RegExp(esc(word("status.verified", "Проверено жителями", "Тұрғындар тексерді")), "i")))); }
        await shot("7-verified");
        await say("s7b", 4200);
        await page.keyboard.press("Escape").catch(() => null); await pause(600);
      }
    }
    done(s, verified, verified ? null : "проверка жителем не показана");
    await setMode("akimat");
  }

  // ---------------------------------------------------------------------------------------------- часть 2 (сцены 7–9)
  // Экраны раунда 15 ищутся по оболочке (BirgeShell: разделы вида и «Ещё»), модули — по /api/civic/v2/modules.
  async function part2() {
    // Сцены — по scenes демо-мира R02 (двор, инициатива, кризис) и адресам IA_ROUND15 R11 / INTEGRATION R17:
    // #yard/<двор>, #together/<инициатива>, #agencies/board, #agencies/calendar, #agencies/crisis=<id>; «Хроника» —
    // BirgeReplay.open (R07). Нет модуля на странице или в API — сцена не записывается, причина — в MANIFEST.
    const W15 = loadWorldScenes();
    const has = await page.evaluate(() => ({ together: !!window.BirgeTogether, agencies: !!window.BirgeAgencies,
      works: !!window.BirgeWorksCalendar, replay: !!(window.BirgeReplay && window.BirgeReplay.open) })).catch(() => ({}));
    const mods = await fetch(srv.base + "api/civic/v2/modules").then((r) => r.json()).then((j) => j.modules || {}).catch(() => ({}));
    const ready = (re) => Object.entries(mods).some(([k, v]) => re.test(k) && v.status === "ready");
    // Сцена 8, житель: жалоба сцены на 2 службы. Состояние готовит API (как в DEMO_SCRIPT делает сотрудник): совместное
    // исполнение «Водоканал + Дорожная служба», часть «Водоканал — сделано»; житель этой вкладки — «Я тоже» → в «Моих
    // обращениях» строка служб (R09 joint.resident). Нет маршрута R09 раунда 15 — сцена пропускается с причиной.
    let joint = false;
    if (W15.complaint8 && srv.staff && srv.staff.user) {
      const A = L.api(srv.base);
      if ((await A.login(srv.staff.user, srv.staff.pass)).ok) {
        const c8 = `/api/civic/v2/complaints/${W15.complaint8}`;
        const r1 = await A.call("POST", `${c8}/services`, { services: [{ service: "water", role: "lead" }, { service: "road", role: "partner" }] }, true);
        const r2 = r1.status === 200 ? await A.call("POST", `${c8}/part`, { service: "water", status: "done",
          note: lang === "kk" ? "Құбыр ауыстырылды" : "Трубу заменили" }, true) : r1;
        const dev = r2.status === 200 ? await page.evaluate(() => { try { let d = localStorage.getItem("birge.device");
          if (!d || !/^[A-Za-z0-9_-]{16,80}$/.test(d)) { d = "d-r10video-" + Date.now().toString(36); localStorage.setItem("birge.device", d); }
          return d; } catch (e) { return null; } }).catch(() => null) : null;
        const r3 = dev ? await A.call("POST", `${c8}/metoo`, { device_id: dev }, false, dev) : { status: 0 };
        joint = [200, 201, 409].includes(r3.status);
      }
    }
    const plan = [
      { id: "scene7-yard", ok: has.together && ready(/together/) && W15.yard, owner: "R16", why: "«Мой двор» (BirgeTogether R16)" },
      { id: "scene8-joint", ok: joint, owner: "R09", why: "паспорт жителя «2 службы» (R09 совместное исполнение)" },
      { id: "scene8-board", ok: has.agencies && ready(/agenc/), owner: "R17", why: "«Штаб ведомств» (BirgeAgencies R17)" },
      { id: "scene8-works", ok: has.works && ready(/works.(calendar|conflicts)|conflict/), owner: "R12", why: "«Календарь работ» (BirgeWorksCalendar R12)" },
      { id: "scene9-crisis", ok: has.agencies && ready(/incident/) && W15.incident, owner: "R17", why: "кризисный штаб (BirgeAgencies R17)" },
      { id: "scene9-replay", ok: has.replay && ready(/replay/), owner: "R07", why: "«Хроника города» (BirgeReplay R07)" },
    ];
    for (const p of plan.filter((x) => !x.ok)) skipped.push({ scene: p.id, owner: p.owner, why: `нет в сборке: ${p.why}` });
    const go = async (hash, after = 2400) => { await page.evaluate((hh) => { location.hash = hh; }, hash).catch(() => null); await wait(after); };
    const toMap = async () => { await page.evaluate(() => window.BirgeShell && window.BirgeShell.setSection("map")).catch(() => null); await wait(900); };
    await quiet();  // заставка «Часть 2» — без субтитра части 1
    await page.evaluate((x) => window.__r10v && window.__r10v.title(x), sub("part2")).catch(() => null);
    await pause(1800);
    await page.evaluate(() => window.__r10v && window.__r10v.title("")).catch(() => null);
    if (!plan.some((x) => x.ok)) { await say("skipped", 4200); return; }
    // --- сцена 7: «Мой двор» → «Я приду»
    if (plan[0].ok) {
      const s = await scene("scene7-yard");
      await setMode("resident");
      await go(`#yard/${W15.yard}`);
      await say("yard", 4200);
      await shot("7-yard");
      if (W15.initiative) {
        await go(`#together/${W15.initiative}`);
        await say("yard_join", 900);
        const joinRe = new RegExp("^(" + [word("together.join", "Я приду", "Мен барамын"), "Я приду", "Мен барамын"].map(esc).join("|") + ")", "i");
        await pressText(joinRe, 2200);
        await shot("7-join");
        await pause(2400);
      }
      done(s);
      await toMap();
    }
    // --- сцена 8, житель: «Мои обращения» → «2 службы: Водоканал — сделано · Дорожная служба — в работе»
    if (plan[1].ok) {
      const s = await scene("scene8-joint");
      await setMode("resident");
      await go("#mine", 2600);
      await say("agencies", 5200);
      const seen = await page.evaluate(() => [...document.querySelectorAll(".bc-joint-line")].some((e) => e.getClientRects().length)).catch(() => false);
      await shot("8-joint");
      done(s, seen, seen ? null : "строки служб нет на карточке");
      await toMap();
    }
    // --- сцена 8: «Штаб ведомств» (табло) и «Календарь работ»
    if (plan[2].ok || plan[3].ok) await setMode("akimat");
    if (plan[2].ok) {
      const s = await scene("scene8-board");
      await go("#agencies/board");
      await say("board", 5200);
      await page.mouse.move(W / 2, H / 2); await page.mouse.wheel(0, 260); await pause(1200);
      await shot("8-board");
      done(s);
    }
    if (plan[3].ok) {
      const s = await scene("scene8-works");
      await go("#agencies/calendar");
      // Вкладка «Календарь работ» у R17 (191f81e7+); без неё — свой раздел R12.
      if (!(await page.evaluate(() => !!document.querySelector("#birge-screen:not([hidden]) .wcal")).catch(() => false))) await go("#works-calendar");
      await say("works", 5200);
      await shot("8-works");
      done(s);
    }
    // --- сцена 9: кризисный штаб и «Хроника города»
    if (plan[4].ok) {
      const s = await scene("scene9-crisis");
      await setMode("akimat");
      // Адрес штаба: #agencies/crisis/<id> (R17 191f81e7+; внутри уже открытых «Ведомств» прежний вид crisis=<id>
      // вкладку не переключает), прежний #agencies/crisis=<id>, публичная карточка #crisis/<id>. В кадр — только когда
      // на экране название этого кризиса.
      const title = W15.incTitle && (lang === "kk" ? W15.incTitle.kk : W15.incTitle.ru);
      const shown = async () => !title || page.evaluate((tt) => (document.querySelector("#birge-screen:not([hidden])") || document.body).innerText.includes(tt), title).catch(() => false);
      let opened = false;
      const tries = [`#agencies/crisis/${W15.incident}`, `#agencies/crisis=${W15.incident}`, `#crisis/${W15.incident}`];
      for (let i = 0; i < tries.length && !opened; i++) {
        if (i) await toMap();   // повтор — с карты: экран смонтируется заново и прочтёт адрес
        await go(tries[i], 2800);
        opened = await shown();
      }
      await say("crisis", 5200);
      await shot("9-crisis");
      done(s, opened, opened ? null : "штаб кризиса не открылся по адресам R17");
      await toMap();
    }
    if (plan[5].ok) {
      const s = await scene("scene9-replay");
      await page.evaluate(() => { const m = typeof map !== "undefined" ? map : null; if (m) m.flyTo({ center: [71.40, 51.13], zoom: 11.6, duration: 1200 }); }).catch(() => null);
      await wait(1500);
      await say("replay", 600);
      const ended = await page.evaluate(async () => {
        // Лёгкий вход R07 (replay-attach.js): open() возвращает Promise ручки; полная хроника — ручку сразу.
        const rp = await Promise.resolve(window.BirgeReplay.open({ map: typeof map !== "undefined" ? map : null, heat: window.CivicShell && window.CivicShell.heat, days: 7, autoplay: true }));
        for (let i = 0; i < 150; i++) { await new Promise((ok) => setTimeout(ok, 200)); const st = rp.state && rp.state(); if (st && (st.ended || st.status === "error")) return !!st.ended; }
        return false;
      }).catch(() => false);
      await shot("9-replay");
      await pause(1800);
      await page.evaluate(() => { try { window.BirgeReplay.active && window.BirgeReplay.active.close(); } catch (e) { /* закрыто */ } }).catch(() => null);
      done(s, ended, ended ? null : "хроника не доиграла до конца");
    }
  }

  function loadWorldScenes() {
    try {
      const w = JSON.parse(fs.readFileSync(path.join(ROOT, "data/civic/astana/demo-world/world_v1.json"), "utf8"));
      const sc = w.scenes || {};
      const inc = (w.incidents || []).find((x) => x.id === (sc.scene9 || {}).incident);
      return { yard: (sc.scene7 || {}).yard, initiative: (sc.scene7 || {}).initiative, complaint8: (sc.scene8 || {}).complaint,
        incident: (sc.scene9 || {}).incident, incTitle: inc ? { ru: inc.title_ru, kk: inc.title_kk } : null };
    } catch (e) { return {}; }
  }

  async function center(loc) { const b = await loc.boundingBox().catch(() => null); return b ? [b.x + b.width / 2, b.y + b.height / 2] : [W / 2, H / 2]; }
}

// ------------------------------------------------------------------------------------------------ субтитры и видео
const stamp = (s, sep) => { const ms = Math.max(0, Math.round(s * 1000)); const h = Math.floor(ms / 3600000), m = Math.floor(ms / 60000) % 60,
  sec = Math.floor(ms / 1000) % 60, r = ms % 1000; return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}${sep}${String(r).padStart(3, "0")}`; };
const toVtt = (cues) => "WEBVTT\n\n" + cues.map((c, i) => `${i + 1}\n${stamp(c.start, ".")} --> ${stamp(c.end, ".")}\n${c.text}\n`).join("\n");
const toSrt = (cues) => cues.map((c, i) => `${i + 1}\n${stamp(c.start, ",")} --> ${stamp(c.end, ",")}\n${c.text}\n`).join("\n");

function ffmpegBin() {
  for (const bin of [process.env.FFMPEG, "ffmpeg"]) { if (!bin) continue;
    try { execFileSync(bin, ["-hide_banner", "-version"], { stdio: "ignore" }); return bin; } catch { /* нет */ } }
  return null;
}
function toMp4(webm, mp4, trim = 0) {
  const bin = ffmpegBin();
  if (!bin) return null;
  try {
    execFileSync(bin, ["-y", "-hide_banner", "-loglevel", "error", "-ss", trim.toFixed(2), "-i", webm, "-c:v", "libx264", "-preset", "medium", "-crf", "26",
      "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", mp4], { stdio: "ignore", timeout: 900000 });
    return fs.existsSync(mp4) ? mp4 : null;
  } catch { return null; }
}
function probeDuration(file) {
  const bin = ffmpegBin();
  if (!bin) return null;
  try { execFileSync(bin, ["-hide_banner", "-i", file], { stdio: "pipe" }); } catch (e) {
    const m = String(e.stderr || "").match(/Duration: (\d+):(\d+):(\d+\.\d+)/);
    if (m) return Math.round(Number(m[1]) * 3600 + Number(m[2]) * 60 + Number(m[3]));
  }
  return null;
}

// ------------------------------------------------------------------------------------------------ запуск
(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ args: ["--disable-dev-shm-usage"] });
  const runs = [];
  for (const lang of LANGS) { log("запись", lang); runs.push(await recordLang(browser, lang)); }
  await browser.close();
  const manifest = {
    what: "Демо-ролик Birge, сценарий v2 (IDEA §3): часть 1 — шаги 1–7 DEMO_SCRIPT R01, часть 2 — сцены 7–9 «Бірге»",
    build: { root: ROOT, sha: L.buildSha(ROOT) }, size: `${W}x${H}`, parts: PARTS, fast: FAST, glass: GLASS || "auto",
    basemap: BASEMAP === "real" ? "настоящая подложка (интернет)" : "упрощённая подложка — облако без интернета (подписано в кадре)",
    world: !!args.world, subtitles: args.subtitles || "tests/e2e/fixtures/video_subtitles.json (черновик R10)",
    machine: L.machine(), when: new Date().toISOString(), runs,
  };
  fs.writeFileSync(path.join(OUT, "MANIFEST.json"), JSON.stringify(manifest, null, 1));
  for (const r of runs) log(r.lang, `${r.duration_s} с`, r.mp4 || r.webm, "сцены:", r.scenes.map((s) => `${s.id}${s.ok ? "" : "✗"}`).join(" "),
    r.skipped.length ? "пропущено: " + r.skipped.map((x) => x.scene).join(", ") : "");
  const bad = runs.some((r) => !r.webm || r.scenes.some((s) => !s.ok));
  process.exit(bad ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
