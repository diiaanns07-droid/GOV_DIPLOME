// R05 · раунд 15 · картинки «Было / станет» и «День / Ночь» для карточки проекта (шторка по 3D-превью).
//
//   NODE_PATH="$(npm root -g)" node tests/civic/R05/round15/make_before_after.mjs
//
// Те же процедурные модели, свет, тени и камера, что у превью каталога (tests/civic/R05/build3d/make_previews.mjs:
// наклон 60°, поворот −30°, ортографическая камера, прозрачный фон), и ТА ЖЕ рамка кадра у «было» и «станет» —
// шторка в карточке совпадает пиксель в пиксель.
//   «станет» — сам проект (у сквера, площадок и остановки — прежнее превью <вид>@2x.png, оно не меняется);
//   «было»   — то же место без проекта: пустой участок (утоптанная земля, редкая трава) или край тротуара с табличкой
//              остановки; у освещения — та же улица без фонарей. Это схема «места без проекта», а не снимок места.
// Освещение рисуется вместе с улицей (проезжая часть, тротуары), иначе фонари висят в пустоте; ночью — тёмная сцена,
// конусы света и пятна под фонарями (настоящие источники света three.js в превью).
// Итог (480×320, только @2x — карточка всегда берёт @2x): web/civic/build3d/data/previews/
//   square-before@2x.png, playground-before@2x.png, sports-before@2x.png, stop-before@2x.png,
//   lighting-before@2x.png, lighting-after@2x.png, lighting-night-before@2x.png, lighting-night-after@2x.png.
import http from "node:http";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";

const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../..");
const WEB = path.join(ROOT, "web");
const OUT = path.resolve(process.argv[2] || path.join(WEB, "civic/build3d/data/previews"));
const { chromium } = require("playwright");

const PAGE = `<!doctype html><meta charset="utf-8"><body style="margin:0;background:transparent">
<script src="/civic/build3d/build3d-core.js"></script>
<script src="/civic/build3d/build3d-models.js"></script>
<script type="module">
import * as THREE from "/vendor/three/three.module.min.js";
const M = CivicBuild3DModels.create(THREE);
const K = CivicBuild3DCore.KINDS;
const P = M.palette;
const B = M.Builder;
// «Белый макет» (поправка П1): то же место без проекта — светло-серая земля, пятна бледной травы, тропинка наискосок,
// пара кустиков. Без плиты акцента: она — у нового проекта.
function emptyLot(b, w, d, rand) {
  b.softDisc(w / 2 + 1, d / 2 + 1, 0, 0, 0.01, P.shadow, 0.06);
  b.box(w, d, 0.05, 0, 0, 0, "#e9e8e3");
  const n = Math.round((w * d) / 38);
  for (let i = 0; i < n; i++) {
    const x = (rand() - 0.5) * (w - 3), y = (rand() - 0.5) * (d - 3);
    const s = 1.2 + rand() * 2.8;
    b.add("solid", new THREE.CircleGeometry(s, 9), rand() < 0.5 ? P.lawn : P.lawnDark, new THREE.Matrix4().makeRotationZ(rand() * 6).setPosition(x, y, 0.055), 1, { flat: true });
  }
  // Тропинка наискосок (люди ходят напрямик).
  const len = Math.hypot(w, d) * 0.9, ang = Math.atan2(d, w) * (rand() < 0.5 ? 1 : -1);
  b.box(len, 1.2, 0.02, 0, 0, 0.06, "#f2f1ed", ang);
  // Пара кустиков по краю — место «ничьё», но живое.
  for (let i = 0; i < 3; i++) {
    const x = (rand() < 0.5 ? -1 : 1) * (w / 2 - 1.5 - rand() * 2), y = (rand() - 0.5) * (d - 4);
    b.add("solid", new THREE.IcosahedronGeometry(0.7 + rand() * 0.4, 1), P.hedge, new THREE.Matrix4().makeTranslation(x, y, 0.5), 1, { round: [x, y, 0.5] });
  }
}
// Край тротуара у дороги, только табличка остановки (как в модели stop): «было» до павильона.
function bareStop(b) {
  const W = K.stop.w, D = K.stop.d;
  b.softDisc(W / 2 + 1, D / 2 + 1, 0, 0, 0.01, P.shadow, 0.06);
  b.box(W, D, 0.15, 0, 0, 0, P.stone);
  b.box(W, 0.3, 0.2, 0, -D / 2 + 0.15, 0, P.curb);
  b.cyl(0.05, 0.05, 2.9, 6, 4.9, -1.2, 0.15, P.metal);
  b.box(0.62, 0.05, 0.62, 4.9, -1.2, 2.55, P.sign);
  b.box(0.36, 0.06, 0.2, 4.9, -1.2, 2.75, P.white);
}
// Улица для освещения: тротуар и бордюр со стороны опор (юг), проезжая часть с разметкой, тротуар напротив.
function street(b) {
  const x0 = -9, x1 = 22, cx = (x0 + x1) / 2, L = x1 - x0;
  b.box(L, 3.2, 0.14, cx, -4.4, 0, P.stone);
  b.box(L, 0.25, 0.18, cx, -2.7, 0, P.curb);
  b.box(L, 8.4, 0.04, cx, 1.6, 0, "#d2d3d0"); // проезжая часть — светло-серая, как в макете
  for (let x = x0 + 1; x < x1 - 1; x += 4.5) b.box(2.4, 0.18, 0.012, x + 1.2, 1.6, 0.04, "#fbfbf9");
  b.box(L, 0.25, 0.18, cx, 5.9, 0, P.curb);
  b.box(L, 2.6, 0.14, cx, 7.3, 0, P.stone);
}
const POLES = [0, 13].map((x) => ({ p: [x, 0], dir: [1, 0] }));
function geosOf(kind, variant) {
  if (kind === "lighting") {
    const b = new B();
    street(b);
    const g = variant === "after" ? M.build("lighting", { poles: POLES, offset: 3 }) : null;
    const s = b.finish();
    if (g) for (const k of ["solid", "glow", "decal"]) if (g[k]) s[k] = s[k] ? mergeGeo(s[k], g[k]) : g[k];
    return s;
  }
  if (variant === "after") return M.build(kind, { seed: "preview-" + kind });
  const b = new B();
  if (kind === "stop") bareStop(b);
  else emptyLot(b, K[kind].w, K[kind].d, M.rng("before-" + kind));
  return b.finish();
}
function mergeGeo(a, b) {
  const out = new THREE.BufferGeometry();
  for (const name of ["position", "normal", "color"]) {
    const A = a.attributes[name], Bb = b.attributes[name];
    if (!A || !Bb || A.itemSize !== Bb.itemSize) continue;
    const arr = new Float32Array(A.array.length + Bb.array.length);
    arr.set(A.array, 0); arr.set(Bb.array, A.array.length);
    out.setAttribute(name, new THREE.BufferAttribute(arr, A.itemSize));
  }
  out.computeBoundingBox();
  return out;
}
function frameBox(geos) {
  const box = new THREE.Box3();
  for (const k of ["solid", "glow", "glass"]) if (geos[k]) { geos[k].computeBoundingBox(); box.union(geos[k].boundingBox); }
  return box;
}
// Ночь (П1): тёмно-серые объёмы (слабый нейтральный свет неба, без синевы) и тёплые конусы света: у каждой опоры —
// прожектор three.js (пятно на асфальте), светлый плафон и прозрачный конус (аддитивный, гаснет к земле).
function nightLights(scene, withLamps) {
  const hemi = new THREE.HemisphereLight(0x5b6066, 0x16181b, 0.9);
  hemi.position.set(0, 0, 1);
  scene.add(hemi);
  const moon = new THREE.DirectionalLight(0xc9ccd0, 0.22);
  moon.position.set(0.6, 0.9, 1.4);
  scene.add(moon);
  if (!withLamps) return;
  for (const pole of POLES) {
    const hx = pole.p[0], hy = 1.95 - 3 + 0; // голова фонаря: опора в 3 м к югу, кронштейн 1,95 м к улице
    const head = new THREE.Vector3(hx, -3 + 1.95, 8.6);
    const spot = new THREE.SpotLight(0xffd59a, 230, 20, Math.PI / 6, 0.55, 1.6); // пятно ≈ конусу (r ≈ 5 м)
    spot.position.copy(head);
    spot.target.position.set(hx, -3 + 2.6, 0);
    scene.add(spot, spot.target);
    // Конус света: открытый, вершина у плафона, основание r 4,6 м у земли; прозрачность в вершинах 0,28 → 0.
    const h = 8.4, r = 4.6, seg = 40;
    const cone = new THREE.ConeGeometry(r, h, seg, 1, true);
    cone.rotateX(Math.PI / 2); // вершина вверх, к плафону
    cone.translate(0, 0, h / 2);
    const pa = cone.attributes.position, col = [];
    for (let i = 0; i < pa.count; i++) { const z = pa.getZ(i); const a = 0.22 * Math.pow(Math.max(0, Math.min(1, z / h)), 1.4); col.push(1, 0.86, 0.6, a); }
    cone.setAttribute("color", new THREE.Float32BufferAttribute(col, 4));
    const mat = new THREE.MeshBasicMaterial({ vertexColors: true, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide });
    const mesh = new THREE.Mesh(cone, mat);
    mesh.position.set(hx, head.y + 0.3, 0.05);
    mesh.renderOrder = 6;
    scene.add(mesh);
    // Тёплое пятно на асфальте (поверх освещения прожектором — мягче край).
    const disc = new THREE.Mesh(new THREE.CircleGeometry(5.2, 40), new THREE.MeshBasicMaterial({ color: 0xffc06a, transparent: true, opacity: 0.1, depthWrite: false, blending: THREE.AdditiveBlending }));
    disc.position.set(hx, head.y + 0.6, 0.06);
    disc.renderOrder = 5;
    scene.add(disc);
  }
}
window.render = (kind, variant, night, W, H) => {
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
  renderer.setPixelRatio(1);
  renderer.setSize(W, H);
  renderer.setClearColor(0x000000, 0);
  const scene = new THREE.Scene();
  if (night) nightLights(scene, variant === "after");
  else M.lights().forEach((l) => scene.add(l));
  const geos = geosOf(kind, variant);
  // Рамка кадра — всегда по «станет» днём: «было» и «ночь» совпадают с ним пиксель в пиксель.
  const frame = geosOf(kind, "after");
  const box = frameBox(frame);
  const mats = {
    solid: new THREE.MeshLambertMaterial({ vertexColors: true }),
    glass: new THREE.MeshLambertMaterial({ vertexColors: true, transparent: true, depthWrite: false, side: THREE.DoubleSide }), // без блика (П1)
    glow: new THREE.MeshBasicMaterial({ vertexColors: true, color: night ? 0xffffff : 0xffffff }),
    decal: new THREE.MeshBasicMaterial({ vertexColors: true, transparent: true, depthWrite: false }),
  };
  if (night) mats.decal.opacity = 0.35;
  const order = { decal: 1, solid: 3, glow: 3, glass: 4 };
  for (const k of ["decal", "solid", "glow", "glass"]) {
    if (!geos[k]) continue;
    const mesh = new THREE.Mesh(geos[k], mats[k]);
    mesh.renderOrder = order[k];
    scene.add(mesh);
  }
  if (!night) {
    const wx = -M.SUN[0] / M.SUN[2], wy = -M.SUN[1] / M.SUN[2];
    const shadow = M.shadowMesh(geos, wx, wy);
    if (shadow) scene.add(shadow);
    const fsh = M.shadowMesh(frame, wx, wy);
    if (fsh) { fsh.geometry.computeBoundingBox(); box.union(fsh.geometry.boundingBox.clone().expandByScalar(-1.6)); }
  }
  const b = (-30 * Math.PI) / 180, p = (60 * Math.PI) / 180;
  const fwd = new THREE.Vector3(Math.sin(b) * Math.sin(p), Math.cos(b) * Math.sin(p), -Math.cos(p));
  const target = box.getCenter(new THREE.Vector3());
  const cam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 2000);
  cam.up.set(0, 0, 1);
  cam.position.copy(target).addScaledVector(fwd, -500);
  cam.lookAt(target);
  cam.updateMatrixWorld();
  const inv = cam.matrixWorldInverse;
  let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
  for (const x of [box.min.x, box.max.x]) for (const y of [box.min.y, box.max.y]) for (const z of [box.min.z, box.max.z]) {
    const v = new THREE.Vector3(x, y, z).applyMatrix4(inv);
    x0 = Math.min(x0, v.x); x1 = Math.max(x1, v.x); y0 = Math.min(y0, v.y); y1 = Math.max(y1, v.y);
  }
  const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
  let hw = ((x1 - x0) / 2) * 1.06, hh = ((y1 - y0) / 2) * 1.06;
  if (hw / hh > W / H) hh = (hw * H) / W; else hw = (hh * W) / H;
  Object.assign(cam, { left: cx - hw, right: cx + hw, top: cy + hh, bottom: cy - hh });
  cam.updateProjectionMatrix();
  renderer.render(scene, cam);
  const url = renderer.domElement.toDataURL("image/png");
  renderer.dispose();
  return url;
};
window.previewReady = true;
</script>`;

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  if (url.pathname === "/__ba.html") {
    res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
    return res.end(PAGE);
  }
  const file = path.normalize(path.join(WEB, decodeURIComponent(url.pathname)));
  if (!file.startsWith(WEB)) return res.writeHead(403).end();
  try {
    const data = await readFile(file);
    res.writeHead(200, { "Content-Type": file.endsWith(".js") ? "text/javascript; charset=utf-8" : "application/octet-stream" });
    res.end(data);
  } catch (e) {
    res.writeHead(404).end();
  }
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const browser = await chromium.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
const page = await browser.newPage();
page.on("pageerror", (e) => console.log("pageerror", e.message));
await page.goto(`http://127.0.0.1:${server.address().port}/__ba.html`);
await page.waitForFunction(() => window.previewReady === true, null, { timeout: 30000 });
await mkdir(OUT, { recursive: true });
const jobs = [
  ["square", "before", false, "square-before@2x.png"],
  ["playground", "before", false, "playground-before@2x.png"],
  ["sports", "before", false, "sports-before@2x.png"],
  ["stop", "before", false, "stop-before@2x.png"],
  ["lighting", "before", false, "lighting-before@2x.png"],
  ["lighting", "after", false, "lighting-after@2x.png"],
  ["lighting", "before", true, "lighting-night-before@2x.png"],
  ["lighting", "after", true, "lighting-night-after@2x.png"],
];
for (const [kind, variant, night, name] of jobs) {
  const url = await page.evaluate(([k, v, n]) => window.render(k, v, n, 480, 320), [kind, variant, night]);
  await writeFile(path.join(OUT, name), Buffer.from(url.split(",")[1], "base64"));
  console.log("записано:", path.relative(ROOT, path.join(OUT, name)));
}
await browser.close();
server.close();
