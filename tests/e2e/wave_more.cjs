// R10 · раунд 14 · проверки остальных пунктов POLISH_WAVE.md (волна 1) и POLISH_WAVE_2.md (волна 2) + обязательные мелочи.
// Подключается из wave_checks.cjs: require("./wave_more.cjs")(H) → список пунктов {id, title, owner, run, probe, done}.
// H — помощники wave_checks (add, st, W, part, exact, openPage, goto, header, …): здесь своих помощников браузера нет.
//
// Поля API — по коду сборки (R09 ui/civic_feedback/v2, R12 engine/civic_geo, R08 ui/civic_akim, R07 ui/civic_heat):
// envelope R09 {ok, data}, остальные v2 — голый JSON (A.data понимает оба). Пункт без кода роли — ЖДЁТ (probe).
"use strict";
const fs = require("fs"), path = require("path");

module.exports = function waveMore(H) {
  const { add, st, W, part, exact, openPage, goto, header, modeRe, mineRe, shotOf, staffLogin, devId, complaintById, STOPS, ROOT, L } = H;
  const NURA = "71.38,51.10,71.44,51.14";
  const say = (lang, ru, kk) => (lang === "kk" ? kk : ru);
  const langsOf = (variants) => [...new Set(variants.map(([, l]) => l))];
  const dayRe = (lang) => exact(W(lang, ["common.nav.day", "shell.section.day", "akim.title"], say(lang, "Картина дня", "Күн қорытындысы")));
  const inboxRe = (lang) => exact(W(lang, ["common.nav.complaints", "shell.nav.inbox", "inbox.title"], say(lang, "Обращения", "Өтініштер")));

  // ---------------------------------------------------------------------------- данные сборки
  const objects = (() => { try { return JSON.parse(fs.readFileSync(path.join(ROOT, "data/civic/astana/geo/objects.json"), "utf8")).items; } catch { return []; } })();
  const near = (kind) => objects.filter((o) => o.kind === kind && o.point[0] > 71.395 && o.point[0] < 71.42 && o.point[1] > 51.12 && o.point[1] < 51.132);
  const INTER = near("intersection").find((o) => (o.graph_nodes || 0) >= 3) || near("intersection")[0] || null;
  const SIGNAL = near("traffic_signal")[0] || null;
  const holidays = (() => { try { const y = JSON.parse(fs.readFileSync(path.join(ROOT, "ui/civic_feedback/v2/holidays_kz.json"), "utf8")).years;
    return new Set(Object.values(y).flatMap((v) => (v.holidays || []).map((h) => h.date))); } catch { return null; } })();

  async function categories(A) {
    const r = await A.call("GET", "/api/civic/v2/categories");
    const d = A.data(r) || {};
    return (d.categories || d.items || []);
  }
  async function file(A, { stop, device, text, category = "lighting", subtopic, target, lang = "ru" }) {
    const body = { text, lang, category, category_source: "resident", point: (target && target.point) || stop.point, device_id: device, demo: true,
      target: target ? { kind: "object", id: target.id, label_ru: target.label_ru, label_kk: target.label_kk } : { kind: "object", id: stop.id, label_ru: `Остановка «${stop.name}»` },
      ...(subtopic !== undefined ? { subtopic } : {}) };
    const r = await H.postRetry(A, "/api/civic/v2/complaints", body, device);
    const rec = (A.data(r) || {}).complaint || A.data(r) || null;
    return { http: r.status, rec: rec && rec.id ? rec : null, error: r.body && (r.body.error || r.body.message) };
  }
  const mine = async (A, device) => { const r = await A.call("GET", "/api/civic/v2/complaints/mine", null, false, device); return ((A.data(r) || {}).items) || []; };
  const changes = async (A, device) => { const r = await A.call("GET", "/api/civic/v2/complaints/changes", null, false, device); return A.data(r) || {}; };
  const summary = async (A) => A.data(await A.call("GET", "/api/civic/v2/akim/summary?days=30")) || {};

  // ---------------------------------------------------------------------------- W1-1 светофор, перекрёсток, переход (R12)
  async function checkStreetTargets(ctx) {
    const { browser, base, variants } = ctx;
    const A = L.api(base);
    if (!INTER) { add("W1-1", "данные", "перекрёсток R12 у Нуры в geo/objects.json", "FAIL", "нет ни одного kind=intersection в рамке"); return; }
    const STREET = ["intersection", "traffic_signal", "crossing"];
    for (const [cat, first] of [["roads", ["intersection", "traffic_signal", "crossing"]], ["sidewalks", ["crossing", "intersection", "traffic_signal"]], ["noise_safety", ["crossing", "intersection", "traffic_signal"]]]) {
      const r = await A.call("GET", `/api/civic/v2/targets?lon=${INTER.point[0]}&lat=${INTER.point[1]}&category=${cat}`);
      const c = ((A.data(r) || {}).candidates || []).map((x) => x.target || {});
      add("W1-1", "API", `«${cat}» у перекрёстка: первым в «Это здесь?» — светофор/перекрёсток/переход`, st(r.status === 200 && !!c[0] && first.includes(c[0].object_kind)),
        { http: r.status, first: c[0] ? { kind: c[0].object_kind, ru: c[0].label_ru } : null, kinds: c.map((x) => x.object_kind || x.kind).slice(0, 5) });
    }
    const r0 = await A.call("GET", `/api/civic/v2/targets?lon=${INTER.point[0]}&lat=${INTER.point[1]}&category=roads`);
    const inter = ((A.data(r0) || {}).candidates || []).map((x) => x.target || {}).find((t) => t.object_kind === "intersection");
    add("W1-1", "API", "подпись перекрёстка «Перекрёсток ул. A и ул. B» (ru) и своя kk", st(!!inter && /^Перекр[её]сток\s.+\sи\s.+/.test(inter.label_ru || "") && !!inter.label_kk && inter.label_kk !== inter.label_ru),
      { ru: inter && inter.label_ru, kk: inter && inter.label_kk, osm: INTER.id, streets: INTER.streets_ru });
    if (SIGNAL) {
      const r1 = await A.call("GET", `/api/civic/v2/targets?lon=${SIGNAL.point[0]}&lat=${SIGNAL.point[1]}&category=roads&subtopic=traffic_light_timing`);
      const c1 = ((A.data(r1) || {}).candidates || []).map((x) => x.target || {});
      add("W1-1", "API", "«Светофор долго красный» у светофора: светофор — первый кандидат", st(!!c1[0] && c1[0].object_kind === "traffic_signal"),
        { first: c1[0] ? { kind: c1[0].object_kind, ru: c1[0].label_ru } : null, osm: SIGNAL.id });
    }
    // Мастер жалобы (R09): нажатие у перекрёстка → в «Это здесь?» есть точка улицы (мастер спрашивает место ДО категории —
    // порядок «улицы первыми» по категории тут не действует, но точка улицы должна предлагаться).
    const plain = await A.call("GET", `/api/civic/v2/targets?lon=${INTER.point[0]}&lat=${INTER.point[1]}`);
    const offered = ((A.data(plain) || {}).candidates || []).map((x) => x.target || {}).filter((t) => STREET.includes(t.object_kind));
    for (const [size, lang] of variants) {
      const tag = `${size[0]}-${lang}`;
      const P = await openPage(browser, size, lang);
      try {
        await goto(P.page, base, lang);
        await header(P.page, lang, modeRe(lang, "resident"), 1200);
        const start = W(lang, "complaint.start.button", say(lang, "Сообщить о проблеме", "Мәселе туралы хабарлау"));
        if (!(await L.clickText(P.page, part(start), { wait: 1500 }))) { add("W1-1", tag, "мастер жалобы открыт", "FAIL", "нет кнопки «" + start + "»"); continue; }
        const pt = await L.showPoint(P.page, INTER.point, 17);
        if (pt) { const at = pt.onCanvas || !pt.near ? pt : pt.near; await L.tap(P.page, at.x, at.y); }
        await L.sleep(3000);
        const dlg = (await L.firstVisible(P.page.getByRole("dialog"))) || P.page;
        const txt = await dlg.innerText().catch(() => "");
        const label = offered.map((t) => t[lang === "kk" ? "label_kk" : "label_ru"]).find((l) => l && txt.includes(l));
        add("W1-1", tag, "мастер: нажатие у перекрёстка → в «Это здесь?» есть перекрёсток/светофор/переход", st(!!label),
          { label: label || null, api_offers: offered.map((t) => t.object_kind) }, await shotOf(P.page, `${tag}-W1-1-wizard`));
      } finally { await P.ctx.close(); }
    }
  }

  // ---------------------------------------------------------------------------- W1-2 уточнения (R09)
  async function checkSubtopic(ctx) {
    const { browser, base, variants, staff } = ctx;
    const A = L.api(base);
    const cats = await categories(A);
    const light = cats.find((c) => c.id === "lighting");
    const sub = light && (light.subtopics || []).find((s) => !s.emergency_phone);
    if (!sub) { add("W1-2", "API", "уточнения категории «Освещение» в /categories", "FAIL", { categories: cats.length }); return; }
    const D = devId("s");
    const ok = await file(A, { stop: STOPS[1], device: D, text: "Фонарь у остановки не горит третий день", subtopic: sub.id });
    const bad = await file(A, { stop: STOPS[1], device: devId("s"), text: "Фонарь у остановки не горит", subtopic: "no_such_subtopic" });
    add("W1-2", "API", "уточнение сохраняется в записи (subtopic), чужое уточнение — отказ 422", st(!!ok.rec && ok.rec.subtopic === sub.id && bad.http === 422),
      { saved: ok.rec && ok.rec.subtopic, http: ok.http, bad: bad.http });
    if (!ok.rec) return;
    const login = staff && staff.user ? await A.login(staff.user, staff.pass) : { ok: false };
    const inbox = login.ok ? await A.call("GET", "/api/civic/v2/complaints/inbox", null, true) : null;
    const seen = inbox ? JSON.stringify(A.data(inbox) || {}).includes(`"subtopic":"${sub.id}"`) || JSON.stringify(A.data(inbox) || {}).includes(sub.id) : false;
    add("W1-2", "API", "акимат: уточнение видно в «Обращениях» (/complaints/inbox)", st(seen), { login: login.ok, http: inbox && inbox.status });
    for (const lang of langsOf(variants)) {
      const tag = `1366-${lang}`;
      const K = await openPage(browser, [1366, 768], lang, { "birge.mode": "akimat" });
      try {
        await goto(K.page, base, lang);
        if (!(await staffLogin(K.page, lang, staff))) { add("W1-2", tag, "вход сотрудника", "FAIL"); continue; }
        const opened = await header(K.page, lang, inboxRe(lang), 2500);
        const label = sub[lang] || W(lang, "subtopic." + sub.id) || sub.ru;
        const shown = opened ? await L.visibleText(K.page, part(label)) : false;
        add("W1-2", tag, `акимат «Обращения»: уточнение «${label}» видно в списке`, st(opened && shown), { opened, label }, await shotOf(K.page, `${tag}-W1-2-inbox`));
      } finally { await K.ctx.close(); }
    }
  }

  // ---------------------------------------------------------------------------- W1-5 фото (R09 + R15)
  // Маленький JPEG рисует сам Chromium (canvas), сегмент APP1 «Exif» с «GPS» вставляется вручную сразу после SOI.
  async function makeJpeg(browser, w = 640, h = 480) {
    const ctx = await browser.newContext(); const page = await ctx.newPage();
    const b64 = await page.evaluate(([w, h]) => { const c = document.createElement("canvas"); c.width = w; c.height = h; const g = c.getContext("2d");
      g.fillStyle = "#3a6"; g.fillRect(0, 0, w, h); g.fillStyle = "#fff"; g.fillText("R10 photo", 20, 40); return c.toDataURL("image/jpeg", 0.8).split(",")[1]; }, [w, h]);
    await ctx.close();
    const jpg = Buffer.from(b64, "base64");
    const payload = Buffer.concat([Buffer.from("Exif\0\0MM\0*\0\0\0\x08", "binary"), Buffer.from("GPSLatitude=51.1281;GPSLongitude=71.4304;R10-SECRET-GPS", "ascii")]);
    const seg = Buffer.concat([Buffer.from([0xFF, 0xE1, (payload.length + 2) >> 8, (payload.length + 2) & 255]), payload]);
    return Buffer.concat([jpg.subarray(0, 2), seg, jpg.subarray(2)]);
  }
  async function upload(A, id, bytes, kind, device, staffFlag = false) {
    const s = await A.call("POST", `/api/civic/v2/complaints/${id}/photos`, { kind, size: bytes.length }, staffFlag, device);
    const sd = A.data(s) || {};
    if (![200, 201].includes(s.status) || !sd.upload_id) return { http: s.status, error: s.body && s.body.error, stage: "start" };
    const step = sd.chunk_bytes || 36000;
    let last = null;
    for (let off = 0; off < bytes.length; off += step) {
      last = await A.call("POST", `/api/civic/v2/complaints/${id}/photos/${sd.upload_id}`, { offset: off, data: bytes.subarray(off, off + step).toString("base64") }, staffFlag, device);
      if (![200, 201].includes(last.status)) return { http: last.status, error: last.body && last.body.error, stage: "chunk" };
    }
    const d = A.data(last) || {};
    return { http: last.status, photo: d.photo || null };
  }
  async function checkPhotos(ctx) {
    const { browser, base } = ctx;
    const A = L.api(base);
    const D = devId("p");
    const c = await file(A, { stop: STOPS[2], device: D, text: "Сломана скамейка на остановке, фото прилагаю", category: "transport" });
    if (!c.rec) { add("W1-5", "API", "жалоба для фото", "FAIL", c); return; }
    const jpg = await makeJpeg(browser);
    const up = await upload(A, c.rec.id, jpg, "resident", D);
    const got = up.photo ? await A.call("GET", `/api/civic/v2/complaints/${c.rec.id}/photos/${up.photo.id}`, null, false, D) : null;
    const url = got && ((A.data(got) || {}).photo || {}).data_url;
    const stored = url ? Buffer.from(url.split(",")[1] || "", "base64") : null;
    const gpsLeft = stored ? stored.includes(Buffer.from("R10-SECRET-GPS")) || stored.includes(Buffer.from("Exif\0\0")) : null;
    add("W1-5", "API", "фото с телефона прикрепляется; EXIF и GPS удалены (в сохранённом файле их нет)", st(!!stored && stored.length > 1000 && gpsLeft === false && jpg.includes(Buffer.from("R10-SECRET-GPS"))),
      { upload: up.http, error: up.error, stored_bytes: stored && stored.length, exif_gps_left: gpsLeft });
    const more = [];
    for (let i = 0; i < 3; i++) more.push((await upload(A, c.rec.id, jpg, "resident", D)).http);
    add("W1-5", "API", "не больше 3 фото: четвёртое — отказ", st(more.slice(0, 2).every((h) => [200, 201].includes(h)) && more[2] >= 400), { http: more });
    const gif = Buffer.concat([Buffer.from("GIF89a"), Buffer.alloc(2000, 1)]);
    const D2 = devId("p");
    const c2 = await file(A, { stop: STOPS[2], device: D2, text: "Сломана урна у остановки", category: "transport" });
    const g = c2.rec ? await upload(A, c2.rec.id, gif, "resident", D2) : { http: null };
    const big = c2.rec ? await A.call("POST", `/api/civic/v2/complaints/${c2.rec.id}/photos`, { kind: "resident", size: 1_600_000 }, false, D2) : { status: null };
    add("W1-5", "API", "только jpeg/png/webp и не больше 1,5 МБ: GIF и файл 1,6 МБ — отказ", st(g.http >= 400 && big.status >= 400), { gif: g.http, big: big.status });
    const pub = await A.call("GET", `/api/civic/v2/complaints/${c.rec.id}?view=public`);
    const other = up.photo ? await A.call("GET", `/api/civic/v2/complaints/${c.rec.id}/photos/${up.photo.id}`, null, false, devId("x")) : { status: null };
    const heat = await A.call("GET", `/api/civic/v2/heat?bbox=${NURA}&days=30&zoom=16`);
    const leak = /data:image|\/photos\/p-/.test(JSON.stringify(A.data(pub) || {})) || /data:image|\/photos\/p-/.test(JSON.stringify(A.data(heat) || {}));
    add("W1-5", "API", "фото видит только акимат (и автор): в публичной карточке и на карте их нет, чужое устройство — отказ", st(!leak && [403, 404].includes(other.status)),
      { public_has_photo: leak, other_device: other.status });
  }

  // ---------------------------------------------------------------------------- W1-6 рабочие дни, W1-7 «Передано» (R09 + R08)
  async function checkDeadlines(ctx) {
    const { base, staff } = ctx;
    const A = L.api(base);
    const cats = await categories(A);
    const light = cats.find((c) => c.id === "lighting") || {};
    const D = devId("d");
    const c = await file(A, { stop: STOPS[0], device: D, text: "Не горит фонарь над переходом", subtopic: "lamp_off" });
    if (!c.rec) { add("W1-6", "API", "жалоба для срока", "FAIL", c); return; }
    const rec = await complaintById(A, c.rec.id);
    const created = new Date(rec.created_at), due = new Date(rec.due_at);
    // Счёт в днях Астаны (UTC+5): дни после подачи до срока включительно, рабочие = пн–пт и не праздник РК.
    const local = (d) => new Date(d.getTime() + 5 * 3600e3).toISOString().slice(0, 10);
    const isWork = (s) => { const wd = new Date(s + "T00:00:00Z").getUTCDay(); return wd !== 0 && wd !== 6 && !(holidays && holidays.has(s)); };
    let n = 0;
    for (let t = new Date(local(created) + "T00:00:00Z").getTime() + 864e5; t <= new Date(local(due) + "T00:00:00Z").getTime(); t += 864e5) if (isWork(new Date(t).toISOString().slice(0, 10))) n++;
    add("W1-6", "API", "срок ответа = N рабочих дней РК с праздниками 2026 (выходные не съедают срок)",
      st(!!rec.due_at && holidays !== null && Number.isInteger(light.response_days) && n === light.response_days && isWork(local(due))),
      { created: rec.created_at, due_at: rec.due_at, working_days: n, response_days: light.response_days, holidays: holidays && holidays.size });
    const login = staff && staff.user ? await A.login(staff.user, staff.pass) : { ok: false };
    const sv = login.ok ? A.data(await A.call("GET", `/api/civic/v2/complaints/${c.rec.id}`, null, true)) || {} : {};
    const sr = sv.complaint || sv;
    const dl = sr.deadline || (sr.staff_view && sr.staff_view.deadline) || null;
    add("W1-6", "API", "акимату: «Осталось N рабочих дней» (deadline.working_days_left)", st(!!dl && Number.isInteger(dl.working_days_left) && dl.state === "ok"), { deadline: dl });
    // W1-7: «Передано: Служба освещения» — служба из таблицы R08 («категория/уточнение → служба»), без названий организаций.
    const m = (await mine(A, D)).find((x) => x.id === c.rec.id) || {};
    const assignee = m.passport && m.passport.assignee;
    const route = A.data(await A.call("GET", "/api/civic/v2/akim/routing?category=lighting&subtopic=lamp_off")) || {};
    const svc = route.service || (route.items && route.items[0] && route.items[0].service) || route;
    const svcRu = (svc && (svc.ru || svc.name_ru)) || null;
    add("W1-7", "API", "«Передано: …» — служба из таблицы R08 по категории и уточнению, общее название", st(!!assignee && (!svcRu || assignee === svcRu) && /служб|оператор|теплосет|водоканал|полиц/i.test(assignee)),
      { assignee, routing: svcRu, source: m.passport && m.passport.assignee_source });
  }

  // ---------------------------------------------------------------------------- W1-8 мат и оскорбления (R04)
  // Текст — из теста самого R04 (tests/civic/R04/round14/test_r04_profanity.py), маска «первая буква + звёздочки».
  const RUDE = "Опять эта блядская яма у остановки!!! Заебали, когда починят?";
  async function checkProfanity(ctx) {
    const { browser, base, staff, variants } = ctx;
    const A = L.api(base);
    const D = devId("m");
    const c = await file(A, { stop: STOPS[1], device: D, text: RUDE, category: "roads" });
    if (!c.rec) { add("W1-8", "API", "жалоба с грубыми словами", "FAIL", c); return; }
    const pub = JSON.stringify(A.data(await A.call("GET", `/api/civic/v2/complaints/${c.rec.id}?view=public`)) || {});
    const heat = JSON.stringify(A.data(await A.call("GET", `/api/civic/v2/heat?bbox=${NURA}&days=30&zoom=16`)) || {});
    const sim = JSON.stringify(A.data(await A.call("POST", "/api/civic/v2/similar", { text: RUDE, point: STOPS[1].point, days: 30 })) || {});
    // Чужим жителям текст настоящих жалоб не показывается вовсе (публичная карточка без текста, на карте — только примеры);
    // текст виден автору в «Моих обращениях» — он тоже не сотрудник, шлюз маскирует и там.
    const own = JSON.stringify(await mine(A, D));
    const raw = /блядск|Заебал/i, masked = /б\*{5,}|З\*{5,}/;
    add("W1-8", "API", "не сотрудникам (карточка, карта, похожие, «Мои обращения»): грубых слов нет, в тексте — звёздочки",
      st(!raw.test(pub) && !raw.test(heat) && !raw.test(sim) && !raw.test(own) && masked.test(own)),
      { raw_in: { public: raw.test(pub), heat: raw.test(heat), similar: raw.test(sim), mine: raw.test(own) }, masked_in_mine: masked.test(own) });
    const login = staff && staff.user ? await A.login(staff.user, staff.pass) : { ok: false };
    const sv = login.ok ? A.data(await A.call("GET", `/api/civic/v2/complaints/${c.rec.id}`, null, true)) || {} : {};
    const sr = sv.complaint || sv;
    const mod = sr.moderation || (sr.staff_view && sr.staff_view.moderation) || null;
    add("W1-8", "API", "акимат видит оригинал и пометку «содержит грубые слова» (moderation.rude)", st(raw.test(JSON.stringify(sr)) && !!mod && mod.rude === true), { login: login.ok, moderation: mod });
    for (const lang of langsOf(variants)) {
      const tag = `1366-${lang}`;
      const K = await openPage(browser, [1366, 768], lang, { "birge.mode": "akimat" });
      try {
        await goto(K.page, base, lang);
        if (!(await staffLogin(K.page, lang, staff))) { add("W1-8", tag, "вход сотрудника", "FAIL"); continue; }
        const rudeRe = part(W(lang, "moderation.rude", say(lang, "Содержит грубые слова", "Дөрекі сөздер бар")));
        const card = await H.openCard(K.page, STOPS[1]);
        const inCard = card ? await L.visibleText(K.page, rudeRe) : false;
        add("W1-8", tag, "карточка места (R07) у акимата: пометка «содержит грубые слова» у текста жителя", st(!!card && inCard), { card: !!card, mark: inCard }, await shotOf(K.page, `${tag}-W1-8-card`));
        await K.page.keyboard.press("Escape").catch(() => null);
        const opened = await header(K.page, lang, inboxRe(lang), 2500);
        const inInbox = opened ? await L.visibleText(K.page, rudeRe) : false;
        add("W1-8", tag, "«Обращения» (R09): пометка «содержит грубые слова» у такого обращения", st(opened && inInbox), { opened, mark: inInbox }, await shotOf(K.page, `${tag}-W1-8-inbox`));
      } finally { await K.ctx.close(); }
    }
  }

  // ---------------------------------------------------------------------------- W1-9 разъединить дубли (R04 + R09 + R07)
  async function checkUnmerge(ctx) {
    const { browser, base, staff, variants } = ctx;
    const A = L.api(base);
    const stop = STOPS[2];
    const a = await file(A, { stop, device: devId("u"), text: "Нет крыши у павильона остановки", category: "transport" });
    const b = await file(A, { stop, device: devId("u"), text: "Нет урны у остановки, мусор на земле", category: "transport" });
    const login = staff && staff.user ? await A.login(staff.user, staff.pass) : { ok: false };
    if (!a.rec || !b.rec || !login.ok) { add("W1-9", "API", "подготовка: две жалобы и вход сотрудника", "FAIL", { a: a.http, b: b.http, login: login.ok }); return; }
    // Запись — напрямую (с сессией сотрудника): в списке по рамке дубли не показываются.
    const recOf = async (id) => { const d = A.data(await A.call("GET", `/api/civic/v2/complaints/${id}`, null, true)) || {}; return d.complaint || (d.id ? d : null); };
    const people = async (id) => { const r = await recOf(id); return r ? (r.reporters ?? 1 + (r.metoo || 0)) : null; };
    const p0 = await people(a.rec.id);
    const m = await A.call("POST", `/api/civic/v2/complaints/${b.rec.id}/duplicate`, { of: a.rec.id }, true);
    const p1 = await people(a.rec.id);
    add("W1-9", "API", "сотрудник отмечает дубль: люди дубля переходят к исходной", st([200, 201].includes(m.status) && p1 === p0 + 1), { http: m.status, before: p0, after: p1 });
    // UI до разделения: карточка места R07 у акимата — блок «Объединено с этим» → «Это разные проблемы».
    for (const lang of langsOf(variants).slice(0, 1)) {
      const tag = `1366-${lang}`;
      const K = await openPage(browser, [1366, 768], lang, { "birge.mode": "akimat" });
      try {
        await goto(K.page, base, lang);
        if (!(await staffLogin(K.page, lang, staff))) { add("W1-9", tag, "вход сотрудника", "FAIL"); continue; }
        const card = await H.openCard(K.page, stop);
        await L.sleep(1500);
        const title = W(lang, "merge.title", say(lang, "Объединено с этим", "Осымен біріктірілген"));
        const block = card ? await L.firstVisible(K.page.locator("details, section").filter({ hasText: part(title) })) : null;
        if (block) { await block.locator("summary").click().catch(() => null); await L.sleep(800); }
        const sep = block ? await L.clickText(block, exact(W(lang, "merge.separate", say(lang, "Это разные проблемы", "Бұл әртүрлі мәселелер"))), { wait: 2500 }) : false;
        const after = await recOf(b.rec.id);
        add("W1-9", tag, "карточка места (R07): «Объединено с этим» → «Это разные проблемы» разделяет одним действием", st(!!block && sep && after && !after.duplicate_of),
          { card: !!card, block: !!block, clicked: sep, duplicate_of: after && after.duplicate_of }, await shotOf(K.page, `${tag}-W1-9-card`));
      } finally { await K.ctx.close(); }
    }
    const still = await recOf(b.rec.id);
    if (still && still.duplicate_of) {
      const u = await A.call("POST", `/api/civic/v2/complaints/${b.rec.id}/unduplicate`, {}, true);
      const p2 = await people(a.rec.id), rb = await recOf(b.rec.id);
      add("W1-9", "API", "«Это разные проблемы» (POST unduplicate): дубль снова отдельный, число людей у исходной пересчитано", st([200, 201].includes(u.status) && rb && !rb.duplicate_of && p2 === p0),
        { http: u.status, people: [p0, p1, p2], duplicate_of: rb && rb.duplicate_of });
    }
  }

  // ---------------------------------------------------------------------------- W1-10 черновик и плохая сеть (R09)
  async function wizardText(page, lang, point) { return H.wizardToText(page, lang, point); }
  async function checkDraftOffline(ctx) {
    const { browser, base, variants } = ctx;
    const A = L.api(base);
    for (const [size, lang] of variants) {
      const tag = `${size[0]}-${lang}`;
      const P = await openPage(browser, size, lang);
      try {
        await goto(P.page, base, lang);
        let wz = await wizardText(P.page, lang, STOPS[0].point);
        if (!wz.ok) { add("W1-10", tag, "мастер жалобы до шага текста", "FAIL", wz.why); continue; }
        const text = say(lang, "Черновик R10: на остановке нет света ", "R10 жобасы: аялдамада жарық жоқ ") + Date.now().toString(36);
        await wz.box.fill(text); await L.sleep(1800);
        await P.page.reload(); await L.sleep(3500);
        wz = await wizardText(P.page, lang, STOPS[0].point);
        const restored = wz.ok ? (await wz.box.inputValue().catch(() => "")) === text : false;
        add("W1-10", tag, "черновик: текст жалобы сохраняется на устройстве и возвращается после перезагрузки", st(restored), { reopened: wz.ok }, await shotOf(P.page, `${tag}-W1-10-draft`));
        if (!wz.ok) continue;
        if (!restored) await wz.box.fill(text);
        await L.sleep(2500);
        // До «Отправить» (как W1-3): «Далее» → «У меня другое» (если есть похожие) → экран проверки.
        const catName = W(lang, "cat.lighting");
        const sendRe = exact(W(lang, ["complaint.step3.send", "complaint.send"], say(lang, "Отправить", "Жіберу")));
        const nextRe = exact(W(lang, "complaint.wizard.next", say(lang, "Далее", "Әрі қарай")));
        const otherRe = exact(W(lang, "complaint.step4.different", say(lang, "У меня другое", "Менде басқа мәселе")));
        let send = null;
        for (let i = 0; i < 6 && !send; i++) {
          const dlg = (await L.firstVisible(P.page.getByRole("dialog"))) || P.page;
          const ob = await L.firstVisible(dlg.getByRole("button", { name: otherRe }));
          if (ob) { await ob.click().catch(() => null); await L.sleep(1200); continue; }
          send = await L.firstVisible(dlg.getByRole("button", { name: sendRe }));
          if (send && (await send.isEnabled().catch(() => false))) break;
          send = null;
          const nb = await L.firstVisible(dlg.getByRole("button", { name: nextRe }));
          if (!nb) break;
          if (!(await nb.isEnabled().catch(() => false)) && catName) await L.clickText(dlg, part(catName), { wait: 900 });
          await nb.click({ timeout: 3000 }).catch(() => null); await L.sleep(1500);
        }
        if (!send) { add("W1-10", tag, "плохая сеть: дойти до «Отправить»", "FAIL", "кнопки «Отправить» нет"); continue; }
        await P.ctx.setOffline(true);
        await send.click().catch(() => null); await L.sleep(2500);
        const offlineMsg = await L.visibleText(P.page, new RegExp([W(lang, "complaint.queue.offline"), W(lang, "complaint.queue.title")].filter(Boolean).map((x) => L.textRe(x).source).join("|") || "$^", "i"));
        const queued = await P.page.evaluate(() => { try { return JSON.parse(localStorage.getItem("birge.complaint.outbox") || "[]").length; } catch { return -1; } });
        add("W1-10", tag, "нет сети при отправке: понятное сообщение и жалоба в очереди на устройстве", st(offlineMsg && queued >= 1), { offlineMsg, queued }, await shotOf(P.page, `${tag}-W1-10-offline`));
        await P.ctx.setOffline(false);
        let left = queued;
        for (const t0 = Date.now(); Date.now() - t0 < 40000 && left > 0; await L.sleep(1000)) left = await P.page.evaluate(() => { try { return JSON.parse(localStorage.getItem("birge.complaint.outbox") || "[]").length; } catch { return -1; } });
        const dev = await P.page.evaluate(() => localStorage.getItem("birge.device"));
        const mineNow = dev ? await mine(A, dev) : [];
        const arrived = mineNow.some((x) => (x.text || "").includes(text.slice(-8)));
        add("W1-10", tag, "сеть вернулась: автоповтор отправил жалобу из очереди (она в «Моих обращениях»)", st(queued >= 1 && left === 0 && arrived), { left, arrived, mine: mineNow.length });
      } finally { await P.ctx.close(); }
    }
  }

  // ---------------------------------------------------------------------------- W1-11 сезонный порядок (R09 + R11)
  async function firstCategory(browser, base, size, lang, when) {
    const P = await openPage(browser, size, lang);
    try {
      if (when) await P.page.clock.setFixedTime(new Date(when));
      await goto(P.page, base, lang);
      const wz = await H.wizardToText(P.page, lang, STOPS[0].point);
      if (!wz.ok) return { why: wz.why };
      let grid = await L.firstVisible(P.page.locator(".bk-catgrid"));
      if (!grid) { const ch = await L.firstVisible(P.page.locator(".bc-change")); if (ch) { await ch.click().catch(() => null); await L.sleep(800); } grid = await L.firstVisible(P.page.locator(".bk-catgrid")); }
      const ids = grid ? await grid.locator("button[data-category]").evaluateAll((els) => els.map((e) => e.dataset.category)) : [];
      return { ids, shot: await shotOf(P.page, `${size[0]}-${lang}-W1-11-${when ? "winter" : "now"}`) };
    } finally { await P.ctx.close(); }
  }
  async function checkSeason(ctx) {
    const { browser, base, variants } = ctx;
    for (const [size, lang] of variants.filter(([s]) => s[0] >= 761)) {
      const tag = `${size[0]}-${lang}`;
      const autumn = await firstCategory(browser, base, size, lang, "2026-10-12T12:00:00+05:00");
      const winter = await firstCategory(browser, base, size, lang, "2026-12-15T12:00:00+05:00");
      add("W1-11", tag, "сетка категорий: в октябре первыми «Дороги», в декабре — «Снег и гололёд»",
        st(!!autumn.ids && !!winter.ids && autumn.ids[0] === "roads" && winter.ids[0] === "snow_ice"),
        { october: (autumn.ids || []).slice(0, 3), december: (winter.ids || []).slice(0, 3), why: autumn.why || winter.why }, winter.shot);
    }
  }

  // ---------------------------------------------------------------------------- W1-12 новые цели на карте и в «Картине дня» (R07, R08)
  async function checkNewTargetsMap(ctx) {
    const { browser, base, variants } = ctx;
    const A = L.api(base);
    if (!SIGNAL) { add("W1-12", "данные", "светофор R12 у Нуры", "FAIL", "нет kind=traffic_signal в рамке"); return; }
    const r = await A.call("GET", `/api/civic/v2/targets?lon=${SIGNAL.point[0]}&lat=${SIGNAL.point[1]}&category=roads&subtopic=traffic_light_timing`);
    const tg = ((A.data(r) || {}).candidates || []).map((x) => x.target || {}).find((t) => t.object_kind === "traffic_signal");
    if (!tg) { add("W1-12", "API", "светофор среди кандидатов R12", "FAIL", { http: r.status }); return; }
    for (let i = 0; i < 3; i++) await file(A, { target: { ...tg, point: SIGNAL.point }, device: devId("t"), text: `Светофор долго горит красный, пешеходы ждут (${i})`, category: "roads", subtopic: "traffic_light_timing" });
    const h = await A.call("GET", `/api/civic/v2/heat?bbox=${NURA}&days=30&zoom=16`);
    const it = ((A.data(h) || {}).items || []).find((x) => x.target && x.target.id === tg.id);
    const kind = it && (it.target.subtype || it.target.object_kind);
    add("W1-12", "API", "тепловая карта: у цели-светофора свой вид (subtype traffic_signal), а не просто «объект»", st(!!it && kind === "traffic_signal"),
      { found: !!it, subtype: kind || null, label: it && it.target.label_ru });
    for (const lang of langsOf(variants)) {
      const tag = `1366-${lang}`;
      const K = await openPage(browser, [1366, 768], lang, { "birge.mode": "akimat" });
      try {
        await goto(K.page, base, lang);
        const p = await L.showPoint(K.page, SIGNAL.point, 18);
        if (p) await L.tap(K.page, p.x, p.y);
        await L.sleep(2500);
        const card = await L.firstVisible(K.page.locator(".r07-card"));
        const kindWord = W(lang, ["heat.kind.traffic_signal", "target.kind.traffic_signal"], say(lang, "Светофор", "Бағдаршам"));
        const eyebrow = card ? await card.locator(".r07-eyebrow").innerText().catch(() => "") : "";
        add("W1-12", tag, `карточка цели на карте: вид «${kindWord}» и подпись светофора`, st(!!card && part(kindWord).test(eyebrow)),
          { card: !!card, eyebrow: eyebrow.trim().slice(0, 60) }, await shotOf(K.page, `${tag}-W1-12-signal`));
        await K.page.keyboard.press("Escape").catch(() => null);
        const day = await header(K.page, lang, dayRe(lang), 2500);
        const s = await summary(A);
        const withSub = ((s.hot || {}).items || []).filter((x) => x.subtopic);
        const label = withSub[0] && withSub[0].subtopic[lang];
        const shown = label ? await L.visibleText(K.page, part(label)) : false;
        add("W1-12", tag, "«Картина дня»: у горячего места — уточнение («… — светофор, N жалоб»)", st(day && withSub.length > 0 && shown),
          { day, hot_with_subtopic: withSub.length, label }, await shotOf(K.page, `${tag}-W1-12-day`));
      } finally { await K.ctx.close(); }
    }
  }

  // ---------------------------------------------------------------------------- W2-3 один ответ всем, W2-10 «Что изменилось» (R09)
  async function checkBroadcast(ctx) {
    const { browser, base, staff, variants } = ctx;
    const A = L.api(base);
    const D1 = devId("b"), D2 = devId("b"), D3 = devId("b");
    const c = await file(A, { stop: STOPS[3], device: D1, text: "Темно на остановке, фонари не горят", subtopic: "lamp_off" });
    const login = staff && staff.user ? await A.login(staff.user, staff.pass) : { ok: false };
    if (!c.rec || !login.ok) { add("W2-3", "API", "подготовка: жалоба и вход сотрудника", "FAIL", { http: c.http, login: login.ok }); return; }
    for (const d of [D2, D3]) await A.call("POST", `/api/civic/v2/complaints/${c.rec.id}/metoo`, { device_id: d }, false, d);
    await A.call("POST", `/api/civic/v2/complaints/${c.rec.id}/status`, { status: "in_progress" }, true);
    const note = "R10: заменили лампу, вечером проверим";
    // R09: «Что изменилось» — новое с прошлого визита (первый визит только запоминает момент): житель уже заходил до обновления.
    const seenBefore = new Date(Date.now() - 60000).toISOString();
    const u = await A.call("POST", `/api/civic/v2/complaints/${c.rec.id}/update`, { text: note }, true);
    const ud = A.data(u) || {};
    const seen = {};
    for (const [n, d] of [["автор", D1], ["«Я тоже» 1", D2], ["«Я тоже» 2", D3]]) {
      const ch = await changes(A, d);
      seen[n] = (ch.items || []).some((x) => x.complaint_id === c.rec.id && (x.text || "").includes("заменили лампу"));
    }
    add("W2-3", "API", "одно обновление сотрудника → его видят автор и все «Я тоже» (в «Что изменилось»)", st([200, 201].includes(u.status) && Object.values(seen).every(Boolean) && (ud.notified ?? 3) >= 3),
      { http: u.status, notified: ud.notified, seen });
    const ch1 = await changes(A, D1);
    const ev = (ch1.items || []).find((x) => x.complaint_id === c.rec.id && x.id);
    add("W2-10", "API", "«Что изменилось»: события по своим обращениям с id (status, note, …) и итог", st(!!ev && !!ch1.summary), { kinds: (ch1.items || []).filter((x) => x.complaint_id === c.rec.id).map((x) => x.kind), summary: ch1.summary });
    for (const [size, lang] of variants) {
      const tag = `${size[0]}-${lang}`;
      const P = await openPage(browser, size, lang, { "birge.mode": "resident", "birge.device": D2, "birge.complaint.changes_seen": seenBefore });
      try {
        await goto(P.page, base, lang);
        const opened = await header(P.page, lang, mineRe(lang), 2000);
        const box = await L.firstVisible(P.page.locator(".bc-changes"));
        const text = box ? await L.visibleText(box, /заменили лампу/i) : false;
        add("W2-10", tag, "житель («Я тоже»): «Мои обращения» → «Что изменилось» с обновлением сотрудника", st(opened && !!box && text), { opened, box: !!box, text }, await shotOf(P.page, `${tag}-W2-10-changes`));
        if (ev) {
          const P2 = await openPage(browser, size, lang, { "birge.mode": "resident", "birge.device": D1, "birge.complaint.changes_seen": seenBefore });
          try {
            await goto(P2.page, new URL(`#mine/event=${encodeURIComponent(ev.id)}`, base).href, lang);
            await L.sleep(1500);
            // Подсвечена строка изменения или раскрыта карточка этого обращения с этим изменением в истории.
            const focus = await L.firstVisible(P2.page.locator(".bc-changes__item--focus"));
            const card = await L.firstVisible(P2.page.locator("[class*=focus], [class*=highlight]").filter({ hasText: /заменили лампу/i }));
            add("W2-10", tag, "уведомление открывает конкретное изменение (#mine/event=…), а не главную", st(!!focus || !!card), { event: ev.id, row: !!focus, card: !!card },
              await shotOf(P2.page, `${tag}-W2-10-event`));
          } finally { await P2.ctx.close(); }
        }
      } finally { await P.ctx.close(); }
    }
  }

  // ---------------------------------------------------------------------------- W2-5 «Нужно решение акима», W2-8 «Пульс» (R08 + R13)
  async function checkDayBlocks(ctx) {
    const { browser, base, variants } = ctx;
    const A = L.api(base);
    const s = await summary(A);
    const dec = s.decisions || {}, items = dec.items || [];
    const full = items.filter((d) => d.problem_ru && d.blocker_ru && (d.options || []).length === 2 && d.decision_ru && d.problem_kk && d.decision_kk);
    add("W2-5", "API", "«Нужно решение акима»: 1–3 решения, у каждого — проблема, что блокирует, 2 варианта, нужное решение (ru и kk)",
      st(dec.available === true && items.length >= 1 && items.length <= 3 && full.length === items.length), { available: dec.available, n: items.length, complete: full.length, source: dec.source, demo: dec.demo });
    const pulse = s.pulse || {}, pi = pulse.items || [];
    add("W2-8", "API", "«Пульс района»: 1–5 тревог с причиной (рост к обычному уровню) и местом на карте",
      // Тревога по всему городу (spike_city) — без одной цели: место на карте = список районов (districts).
      st(pulse.available === true && pi.length >= 1 && pi.length <= 5 && pi.every((p) => p.kind && (p.ratio || p.value) && (p.target || p.district || (p.districts && p.districts.length)))),
      { available: pulse.available, n: pi.length, kinds: pi.map((p) => p.kind), method: pulse.method });
    for (const [size, lang] of variants) {
      const tag = `${size[0]}-${lang}`;
      const K = await openPage(browser, size, lang, { "birge.mode": "akimat" });
      try {
        await goto(K.page, base, lang);
        const day = await header(K.page, lang, dayRe(lang), 2500);
        await L.sleep(1200);
        const dTitle = W(lang, "akim.decision.title"), pTitle = W(lang, "akim.pulse.title");
        const decBox = dTitle ? await L.firstVisible(K.page.locator(".akim-decisions, section").filter({ hasText: part(dTitle) })) : null;
        if (decBox) await decBox.scrollIntoViewIfNeeded().catch(() => null);
        const decN = decBox ? await decBox.locator("[class*=akim-decision__], li, article").count().catch(() => 0) : 0;
        const demoMark = decBox && dec.demo ? await L.visibleText(decBox, /пример|үлгі/i) : !dec.demo;
        add("W2-5", tag, `«Картина дня»: блок «${dTitle}» виден; демо помечено «пример»`, st(day && !!decBox && decN > 0 && demoMark), { day, block: !!decBox, demoMark }, await shotOf(K.page, `${tag}-W2-5-decisions`));
        const pBox = pTitle ? await L.firstVisible(K.page.locator("section, div").filter({ has: K.page.locator(".akim-pulse__item") }).filter({ hasText: part(pTitle) })) : null;
        if (pBox) await pBox.scrollIntoViewIfNeeded().catch(() => null);
        const rows = pBox ? await pBox.locator(".akim-pulse__item").count() : 0;
        const link = pBox ? await L.firstVisible(pBox.locator(".akim-pulse__map")) : null;
        let toMap = false;
        if (link) { await link.click().catch(() => null); await L.sleep(2500); toMap = !!(await L.firstVisible(K.page.locator(".r07-card, .maplibregl-canvas"))) && !(await L.visibleText(K.page, part(pTitle))); }
        add("W2-8", tag, `«Картина дня»: «${pTitle}» — 1–5 тревог, у тревоги ссылка «на карте» открывает карту`, st(day && rows >= 1 && rows <= 5 && !!link && toMap), { rows, link: !!link, toMap }, await shotOf(K.page, `${tag}-W2-8-pulse`));
      } finally { await K.ctx.close(); }
    }
  }

  // ---------------------------------------------------------------------------- W2-9 «Вопрос акиму» (R13)
  async function checkAsk(ctx) {
    const { browser, base, variants } = ctx;
    for (const [size, lang] of variants) {
      const tag = `${size[0]}-${lang}`;
      const P = await openPage(browser, size, lang, { "birge.mode": "resident" });
      try {
        await goto(P.page, new URL("#ask", base).href, lang);
        await L.sleep(1500);
        const txt = await P.page.evaluate(() => document.body.innerText);
        const answers = (txt.match(new RegExp(L.textRe(W(lang, "ask.answer", say(lang, "Ответ акима", "Әкімнің жауабы"))).source, "gi")) || []).length;
        const demo = /пример|үлгі/i.test(txt);
        add("W2-9", tag, "«Вопрос акиму»: вопросы жителей с голосами, «Ответ акима» хотя бы у 2, демо помечено", st(answers >= 2 && demo), { answers, demo }, await shotOf(P.page, `${tag}-W2-9-ask`));
      } finally { await P.ctx.close(); }
    }
  }

  // ---------------------------------------------------------------------------- обязательные мелочи POLISH_WAVE_2
  async function checkSmall(ctx) {
    const { browser, base, variants } = ctx;
    for (const [size, lang] of variants) {
      const tag = `${size[0]}-${lang}`;
      const P = await openPage(browser, size, lang, { "birge.mode": "akimat" });
      try {
        await goto(P.page, base, lang);
        // M-1 «Нет свежих данных» (R07): районы без жалоб и осмотров за период — серые, в легенде пункт «нет свежих данных».
        // Видно только на уровне районов и только если такой район есть: в демо все районы с жалобами — тогда NOT_RUN.
        const A0 = L.api(base);
        const dist = ((A0.data(await A0.call("GET", "/api/civic/v2/heat?days=7&zoom=10")) || {}).items) || [];
        const noData = dist.filter((x) => x.state === "no_data");
        if (!noData.length) add("M-1", tag, "тепловая карта: серый «Нет свежих данных» у районов без жалоб", "NOT_RUN",
          { why: "в данных демо нет района без жалоб за 7 дней — серому нечего показать", districts: dist.length, states: [...new Set(dist.map((x) => x.state))] });
        else {
          await L.showPoint(P.page, [71.43, 51.13], 10);
          await L.sleep(2000);
          const help = await L.firstVisible(P.page.getByRole("button", { name: /^\?$|Что значат цвета|Түстер нені білдіреді/i }));
          if (help) { await help.click().catch(() => null); await L.sleep(800); }
          const nodata = await L.visibleText(P.page, part(W(lang, "heat.legend.nodata", say(lang, "Нет свежих данных", "Жаңа дерек жоқ"))));
          add("M-1", tag, "тепловая карта: серый «Нет свежих данных» у районов без жалоб — в легенде", st(nodata), { help: !!help, no_data: noData.length }, await shotOf(P.page, `${tag}-M-1-legend`));
          await P.page.keyboard.press("Escape").catch(() => null);
        }
        // M-4 список рядом с картой (R07): «Горячие места» — кнопки, карточка без точного нажатия на значок.
        const items = P.page.locator(".r07-hot .r07-item");
        let n = await items.count().catch(() => 0);
        if (!n && P.mobile) { const t = await L.firstVisible(P.page.locator(".r07-sheet__handle, [class*=sheet] [class*=handle], .bk-sheet__handle")); if (t) { await t.click().catch(() => null); await L.sleep(800); n = await items.count().catch(() => 0); } }
        const first = n ? await L.firstVisible(items) : null;
        if (first) { await first.click().catch(() => null); await P.page.locator(".r07-card").first().waitFor({ state: "visible", timeout: 6000 }).catch(() => null); }
        const card = first ? await L.firstVisible(P.page.locator(".r07-card")) : null;
        add("M-4", tag, "рядом с картой — список мест («Горячие места»); нажатие по строке открывает карточку", st(n >= 3 && !!first && !!card), { items: n, card: !!card }, await shotOf(P.page, `${tag}-M-4-list`));
      } finally { await P.ctx.close(); }
      // M-5 лёгкая карточка раньше 3D (R05): 3D-библиотека не нужна, пока житель не открыл 3D.
      const R = await openPage(browser, size, lang, { "birge.mode": "resident" });
      try {
        const three = [];
        R.page.on("request", (q) => { if (/three(\.module|\.min)?(\.js)?|\/vendor\/three\//i.test(q.url())) three.push(q.url().split("/").slice(-2).join("/")); });
        await goto(R.page, base, lang);
        // POLISH_WAVE_2 правило 5 («новые слои грузятся только когда включены») и мелочь «лёгкая карточка раньше 3D; 3D — по кнопке».
        add("M-5", tag, "лёгкая карточка раньше 3D (правило 5): на главной без слоя «Проекты» и 3D библиотека 3D не загружается", st(three.length === 0), { three: three.slice(0, 3) });
      } finally { await R.ctx.close(); }
    }
  }

  // ---------------------------------------------------------------------------- пункты
  const has = (dirs, re) => H.grepBuild(dirs, re).length > 0;
  const R09 = ["web/civic/feedback", "ui/civic_feedback"];
  return [
    { id: "W1-1", title: "Светофор, перекрёсток, переход как цели", owner: "R12 (+R09 мастер)", run: checkStreetTargets, probe: () => objects.some((o) => o.kind === "intersection"),
      done: "Жалоба «светофор долго красный» привязывается к светофору; перекрёсток — «Перекрёсток ул. A и ул. B»" },
    { id: "W1-2", title: "Уточнения в мастере жалобы", owner: "R09", run: checkSubtopic, probe: () => has(R09, /subtopic/), done: "за 1 нажатие уточнение; видно акимату в карточке и списке" },
    { id: "W1-5", title: "Фото к жалобе (EXIF/GPS, лимиты, только акимат)", owner: "R09 (+R15)", run: checkPhotos, probe: () => has(R09, /photos/), done: "фото с телефона, метаданные удалены" },
    { id: "W1-6", title: "Сроки в рабочих днях РК + W1-7 «Передано»", owner: "R09 (+R08)", run: checkDeadlines, also: ["W1-7"], probe: () => has(R09, /working_days|add_working_days/), done: "выходные не съедают срок; «Передано: Служба освещения»" },
    { id: "W1-8", title: "Мат и оскорбления", owner: "R04 (+R07, R09 вывод)", run: checkProfanity, probe: () => has(["ui/civic_ml_api"], /def mask/), done: "в публичных местах нет мата, текст для акимата не теряется" },
    { id: "W1-9", title: "Разъединить дубли", owner: "R04 + R09 (+R07 кнопка)", run: checkUnmerge, probe: () => has(R09, /unduplicate|unmark_duplicate/), done: "неверное «Я тоже» исправляется одним действием" },
    { id: "W1-10", title: "Черновик и плохая сеть", owner: "R09", run: checkDraftOffline, probe: () => has(R09, /complaint\.(draft|outbox)/), done: "жалоба не теряется при обрыве связи" },
    { id: "W1-11", title: "Сезонный порядок категорий", owner: "R09 + R11", run: checkSeason, probe: () => has(["web/civic/feedback", "web/civic/ui-kit"], /season/i), done: "зимой «Снег и гололёд» первым" },
    { id: "W1-12", title: "Новые цели на карте и уточнения в «Картине дня»", owner: "R07, R08", run: checkNewTargetsMap, probe: () => objects.some((o) => o.kind === "traffic_signal"), done: "свои значки и подписи; «Перекрёсток … — светофор, 9 жалоб»" },
    { id: "W2-3", title: "Один ответ всем «Я тоже» + W2-10 «Что изменилось»", owner: "R09", run: checkBroadcast, also: ["W2-10"], probe: () => has(R09, /complaints\/changes|\/update/), done: "одно действие оператора → обновление у всех; житель видит смысл участия" },
    { id: "W2-5", title: "«Нужно решение акима» + W2-8 «Пульс района»", owner: "R08 (+R13)", run: checkDayBlocks, also: ["W2-8"], probe: () => has(["ui/civic_akim", "web/civic/akim"], /decision|pulse/), done: "1–3 решения; 1–5 тревог с причиной и ссылкой на карту" },
    { id: "W2-9", title: "«Вопрос акиму»", owner: "R13", run: checkAsk, probe: (s, r) => !!(r.globals.BirgeAsk || r.globals.BirgeQuestions), done: "вопросы, голоса и «Ответ акима»" },
    { id: "M", title: "Обязательные мелочи: серый «нет данных», список у карты, лёгкая карточка до 3D", owner: "R07, R05", run: checkSmall, also: ["M-1", "M-4", "M-5"], probe: () => true,
      done: "POLISH_WAVE_2 «обязательные мелочи» (номер и экран проверки — в LF-2, уведомление → W2-10, язык → W2-6)" },
  ];
};
