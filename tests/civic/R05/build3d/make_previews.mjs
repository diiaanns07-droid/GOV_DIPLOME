// R05 · дизайн-марафон: картинки-превью пяти объектов для каталога «Что построить?» (стеклянная шторка с карточками).
//
//   NODE_PATH="$(npm root -g)" node tests/civic/R05/build3d/make_previews.mjs
//
// Рендерит те же процедурные модели (build3d-models.js), тем же светом и той же мягкой тенью, что и на карте, под тем
// же углом, что демо (наклон 60°, поворот −30°), на прозрачном фоне. Без пунктира границы (это пометка проекта на
// карте, не сам объект). Освещение — две опоры в 13 м.
// Итог: web/civic/build3d/data/previews/<вид>.png (240×160) и <вид>@2x.png (480×320) — каталог показывает их без
// загрузки three.js (лёгкий вид). Пересобирать после изменения моделей; вид детерминирован (seed "preview-<вид>").
import http from "node:http";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";

const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../..");
const WEB = path.join(ROOT, "web");
const OUT = path.join(WEB, "civic/build3d/data/previews");
const { chromium } = (() => {
  for (const id of ["playwright", "/opt/node22/lib/node_modules/playwright"]) {
    try {
      return require(id);
    } catch (e) {
      /* следующий */
    }
  }
  throw new Error("нужен playwright");
})();

const PAGE = `<!doctype html><meta charset="utf-8"><body style="margin:0;background:transparent">
<script src="/civic/build3d/build3d-core.js"></script>
<script src="/civic/build3d/build3d-models.js"></script>
<script type="module">
import * as THREE from "/vendor/three/three.module.min.js";
const M = CivicBuild3DModels.create(THREE);
const K = CivicBuild3DCore.KINDS;
window.render = (kind, W, H) => {
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
  renderer.setPixelRatio(1);
  renderer.setSize(W, H);
  renderer.setClearColor(0x000000, 0);
  const scene = new THREE.Scene();
  M.lights().forEach((l) => scene.add(l));
  const geos = kind === "lighting"
    ? M.build("lighting", { poles: [0, 13].map((x) => ({ p: [x, 0], dir: [1, 0] })), offset: 3 })
    : M.build(kind, { seed: "preview-" + kind });
  const mats = {
    solid: new THREE.MeshLambertMaterial({ vertexColors: true }),
    glass: new THREE.MeshLambertMaterial({ vertexColors: true, transparent: true, depthWrite: false, side: THREE.DoubleSide }),
    glow: new THREE.MeshBasicMaterial({ vertexColors: true }),
    decal: new THREE.MeshBasicMaterial({ vertexColors: true, transparent: true, depthWrite: false }),
  };
  const order = { decal: 1, solid: 3, glow: 3, glass: 4 };
  const box = new THREE.Box3();
  for (const k of ["decal", "solid", "glow", "glass"]) {
    if (!geos[k]) continue;
    const mesh = new THREE.Mesh(geos[k], mats[k]);
    mesh.renderOrder = order[k];
    scene.add(mesh);
    if (k !== "decal") box.union(geos[k].boundingBox);
  }
  const wx = -M.SUN[0] / M.SUN[2], wy = -M.SUN[1] / M.SUN[2];
  const shadow = M.shadowMesh(geos, wx, wy, document);
  if (shadow) {
    scene.add(shadow);
    shadow.geometry.computeBoundingBox();
    box.union(shadow.geometry.boundingBox.clone().expandByScalar(-1.6)); // край размытия почти прозрачный
  }
  // Камера как у карты: смотрит на азимут −30°, наклон 60° от надира, ортографическая — без перспективных искажений.
  const b = (-30 * Math.PI) / 180, p = (60 * Math.PI) / 180;
  const fwd = new THREE.Vector3(Math.sin(b) * Math.sin(p), Math.cos(b) * Math.sin(p), -Math.cos(p));
  const target = box.getCenter(new THREE.Vector3());
  const cam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 2000);
  cam.up.set(0, 0, 1);
  cam.position.copy(target).addScaledVector(fwd, -500);
  cam.lookAt(target);
  cam.updateMatrixWorld();
  // Вписать: углы рамки объекта в осях камеры, поля 6 %.
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
  if (url.pathname === "/__preview.html") {
    res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
    return res.end(PAGE);
  }
  const file = path.normalize(path.join(WEB, decodeURIComponent(url.pathname)));
  if (!file.startsWith(WEB)) {
    res.writeHead(403);
    return res.end();
  }
  try {
    const data = await readFile(file);
    res.writeHead(200, { "Content-Type": file.endsWith(".js") ? "text/javascript; charset=utf-8" : "application/octet-stream" });
    res.end(data);
  } catch (e) {
    res.writeHead(404);
    res.end();
  }
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const browser = await chromium.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
const page = await browser.newPage();
page.on("pageerror", (e) => console.log("pageerror", e.message));
await page.goto(`http://127.0.0.1:${server.address().port}/__preview.html`);
await page.waitForFunction(() => window.previewReady === true, null, { timeout: 30000 });
await mkdir(OUT, { recursive: true });
const made = [];
for (const kind of ["square", "playground", "sports", "stop", "lighting"]) {
  for (const [suffix, W, H] of [["", 240, 160], ["@2x", 480, 320]]) {
    const url = await page.evaluate(([k, w, h]) => window.render(k, w, h), [kind, W, H]);
    const name = `${kind}${suffix}.png`;
    await writeFile(path.join(OUT, name), Buffer.from(url.split(",")[1], "base64"));
    made.push(name);
  }
}
await browser.close();
server.close();
console.log(`превью: ${made.length} → ${path.relative(ROOT, OUT)}`);
