// R05 · раунд 15 · кадры условных моделей ориентиров отдельно от карты (быстрая проверка вида и бюджета).
// Запуск из корня репозитория:  NODE_PATH=$(npm root -g) node tests/civic/R05/round15/landmarks_preview.mjs [папка]
// Поднимает статический сервер web/ и страницу-стенд (своя, не в сборке): пять моделей на светлой «земле» цвета
// подложки Birge, тот же свет и мягкие тени, что на карте; камера — наклон 52°, поворот −16° (как кнопка «3D»).
// В облаке WebGL идёт через SwiftShader (программная графика) — вид тот же, только медленнее.
import http from "node:http";
import { readFile, mkdir } from "node:fs/promises";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";

const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../..");
const WEB = path.join(ROOT, "web");
const OUT = path.resolve(process.argv[2] || path.join(ROOT, "research/round-15-results/R05/screens/landmarks"));
const { chromium } = require("playwright");

const MIME = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".json": "application/json; charset=utf-8", ".png": "image/png", ".css": "text/css" };
const PAGE = `<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0;height:100%;background:#F4F3EF}canvas{display:block}</style>
<script src="/civic/build3d/build3d-models.js"></script><script src="/civic/build3d/build3d-landmarks.js"></script></head><body>
<script type="module">
import * as THREE from "/vendor/three/three.module.min.js";
const q = new URLSearchParams(location.search);
const Models = CivicBuild3DModels.create(THREE);
const Lib = CivicBuild3DLandmarks.create(THREE, Models);
const data = await (await fetch("/civic/build3d/data/landmarks.json")).json();
const only = q.get("one");
const list = data.landmarks.filter((l) => !only || l.id === only);
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(1);
renderer.setSize(innerWidth, innerHeight);
document.body.appendChild(renderer.domElement);
const scene = new THREE.Scene();
scene.background = new THREE.Color("#F4F3EF");
Models.lights().forEach((l) => scene.add(l));
// Земля — цвет подложки (land #F4F3EF), чуть ниже нуля.
const ground = new THREE.Mesh(new THREE.PlaneGeometry(4000, 4000), new THREE.MeshBasicMaterial({ color: "#F4F3EF" }));
ground.position.z = -0.05;
scene.add(ground);
const SP = 290;
let tris = 0;
list.forEach((spec, i) => {
  const geos = Lib.build(spec);
  tris += Lib.triangles(geos);
  const g = new THREE.Group();
  const mats = { solid: new THREE.MeshLambertMaterial({ vertexColors: true }), glass: new THREE.MeshPhongMaterial({ vertexColors: true, transparent: true, depthWrite: false }),
    glow: new THREE.MeshBasicMaterial({ vertexColors: true }), decal: new THREE.MeshBasicMaterial({ vertexColors: true, transparent: true, depthWrite: false }) };
  for (const k of ["decal", "solid", "glow", "glass"]) if (geos[k]) g.add(Object.assign(new THREE.Mesh(geos[k], mats[k]), { renderOrder: k === "decal" ? 1 : 3 }));
  const th = (spec.rotation_deg || 0) * Math.PI / 180;
  const sun = Models.SUN, wx = -sun[0] / sun[2], wy = -sun[1] / sun[2];
  const sh = Models.shadowMesh(geos, wx * Math.cos(th) - wy * Math.sin(th), wx * Math.sin(th) + wy * Math.cos(th));
  if (sh) g.add(sh);
  g.position.set(only ? 0 : (i - (list.length - 1) / 2) * SP, 0, 0);
  g.rotation.z = -th;
  scene.add(g);
});
const pitch = +(q.get("pitch") || 52), bearing = +(q.get("bearing") || -16);
const dist = +(q.get("dist") || (only ? 360 : 1150));
const cam = new THREE.PerspectiveCamera(+(q.get("fov") || 36), innerWidth / innerHeight, 1, 20000);
cam.up.set(0, 0, 1);
const target = new THREE.Vector3(0, 0, only ? 45 : 50);
// Как камера MapLibre: смотрит по азимуту bearing (по часовой от севера), наклон pitch — от вертикали.
const pr = (pitch * Math.PI) / 180, br = (bearing * Math.PI) / 180;
cam.position.set(target.x - Math.sin(br) * dist * Math.sin(pr), target.y - Math.cos(br) * dist * Math.sin(pr), target.z + dist * Math.cos(pr));
cam.lookAt(target);
renderer.render(scene, cam);
window.__done = { tris, n: list.length };
</script></body></html>`;

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  if (url.pathname === "/__r05/landmarks.html") {
    res.writeHead(200, { "Content-Type": MIME[".html"] });
    return res.end(PAGE);
  }
  const file = path.normalize(path.join(WEB, decodeURIComponent(url.pathname)));
  if (!file.startsWith(WEB)) return res.writeHead(403).end();
  try {
    const data = await readFile(file);
    res.writeHead(200, { "Content-Type": MIME[path.extname(file)] || "application/octet-stream" });
    res.end(data);
  } catch (e) {
    res.writeHead(404).end("not found");
  }
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const BASE = `http://127.0.0.1:${server.address().port}/__r05/landmarks.html`;
await mkdir(OUT, { recursive: true });
const browser = await chromium.launch({ args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"] });
const page = await browser.newPage({ viewport: { width: 1366, height: 768 } });
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
const shots = [["all", ""], ["baiterek", "?one=baiterek"], ["khan-shatyr", "?one=khan-shatyr&dist=520"], ["akorda", "?one=akorda&dist=330"],
  ["nur-alem", "?one=nur-alem&dist=360"], ["palace-peace", "?one=palace-peace&dist=300"]];
for (const [name, query] of shots) {
  await page.goto(BASE + query);
  await page.waitForFunction(() => window.__done, null, { timeout: 60000 });
  const info = await page.evaluate(() => window.__done);
  await page.screenshot({ path: path.join(OUT, `${name}.png`) });
  console.log(name, JSON.stringify(info));
}
console.log(errors.length ? "ОШИБКИ: " + errors.join(" | ") : "ошибок нет");
await browser.close();
server.close();
