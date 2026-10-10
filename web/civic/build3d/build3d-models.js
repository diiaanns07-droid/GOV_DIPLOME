/*
 * Birge · 3D-превью (R05, раунд 14) — процедурные low-poly модели пяти объектов.
 *
 * Никаких внешних 3D-файлов: всё собирается из простых фигур three.js (коробки, цилиндры,
 * икосаэдры) в ЕДИНОМ стиле — светлая палитра Birge, плоские грани, мягкие цвета.
 *
 * Оси модели: x — восток (ширина), y — север (глубина), z — вверх; метры; центр пятна в (0, 0).
 * Модель повёрнута на rotation_deg по часовой стрелке (как азимут) уже в сцене, не здесь.
 *
 * Каждая модель = несколько слитых геометрий по виду материала (чтобы было мало вызовов отрисовки):
 *   solid — непрозрачные части с цветом в вершинах (одна геометрия на объект);
 *   glass — прозрачные части (стекло остановки, сетка ворот и забора);
 *   glow  — светящиеся плафоны фонарей;
 *   decal — мягкие пятна на земле (тень под объектом, круги света), прозрачность в вершинах;
 *   outline — пунктир границы проекта (всегда виден — объект предложен, а не существует).
 *
 * Подключение: window.CivicBuild3DModels.create(THREE) → { build(kind, opts), ... }.
 * В Node: require(...).create(THREE) — для тестов размеров и освобождения памяти.
 */
(function (root, factory) {
  "use strict";
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.CivicBuild3DModels = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // Палитра 3D (светлая, спокойная; согласована с токенами ui-kit: бренд #176b4a, акцент #d7f57c).
  var P = {
    paving: "#e4e0d4",
    pavingDark: "#d3d0c4",
    curb: "#cfd3cb",
    lawn: "#b9d693",
    lawnDark: "#a9cb82",
    soil: "#8f7258",
    trunk: "#8a6a50",
    leaf: ["#7db56a", "#6aa95e", "#8cbf74", "#5f9f5a"],
    conifer: ["#4f8a5e", "#5b9567"],
    wood: "#c9a07a",
    metal: "#5b6a64",
    metalDark: "#3b4a45",
    white: "#f6f7f2",
    water: "#8fcfe0",
    stone: "#dfe3dc",
    rubber: "#f0d2b4",
    sand: "#ecd9a8",
    teal: "#4f8a8b",
    coral: "#e07a5f",
    yellow: "#f2b33d",
    turf: "#5fa36a",
    turf2: "#69ac73",
    line: "#f7f8f4",
    fence: "#2f5e4e",
    brand: "#176b4a",
    brandLight: "#2f7d5b",
    tactile: "#e9c46a",
    glass: "#cfe8ee",
    net: "#f4f6f2",
    glow: "#fff1c1",
    lightPool: "#ffe7a1",
    shadow: "#152c26",
    flowers: ["#e9a3b4", "#f5c451", "#ffffff", "#c9a7e0"],
  };

  // Детерминированный генератор случайных чисел (одинаковый вид объекта после перезагрузки).
  function rng(seedStr) {
    var h = 2166136261;
    var s = String(seedStr || "birge");
    for (var i = 0; i < s.length; i++) {
      h ^= s.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return function () {
      h += 0x6d2b79f5;
      var t = h;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function create(THREE) {
    if (!THREE || !THREE.BufferGeometry) throw new Error("CivicBuild3DModels: нужен three.js");
    var tmpColor = new THREE.Color();

    // ── Сборщик частей ──
    // Каждая часть: геометрия three.js (Y-вверх или Z-вверх — приводим к Z-вверх), цвет, матрица.
    function Builder() {
      this.solid = [];
      this.glass = [];
      this.glow = [];
      this.decal = [];
      this.outline = [];
    }

    // Добавить геометрию g (уже в осях Z-вверх) с цветом и преобразованием.
    Builder.prototype.add = function (bucket, g, color, matrix, alpha) {
      var geo = g.index ? g.toNonIndexed() : g;
      if (geo !== g) g.dispose();
      if (matrix) geo.applyMatrix4(matrix);
      this[bucket].push({ geo: geo, color: color, alpha: alpha == null ? 1 : alpha });
      return this;
    };

    // Коробка w×d×h, низ на высоте z, центр (x, y), поворот rotZ (радианы, против часовой).
    Builder.prototype.box = function (w, d, h, x, y, z, color, rotZ, bucket, alpha) {
      var g = new THREE.BoxGeometry(w, d, h);
      var m = new THREE.Matrix4().makeRotationZ(rotZ || 0).setPosition(x || 0, y || 0, (z || 0) + h / 2);
      return this.add(bucket || "solid", g, color, m, alpha);
    };

    // Цилиндр вдоль Z: радиусы снизу/сверху, высота, число граней; низ на высоте z.
    Builder.prototype.cyl = function (rBottom, rTop, h, seg, x, y, z, color, bucket, alpha) {
      var g = new THREE.CylinderGeometry(rTop, rBottom, h, seg || 8, 1);
      g.rotateX(Math.PI / 2); // three.js строит цилиндр вдоль Y — кладём его вдоль Z
      var m = new THREE.Matrix4().makeTranslation(x || 0, y || 0, (z || 0) + h / 2);
      return this.add(bucket || "solid", g, color, m, alpha);
    };

    // Отрезок-«трубка» между двумя точками 3D (перекладины, ножки качелей, канаты).
    Builder.prototype.rod = function (a, b, r, seg, color, bucket) {
      var va = new THREE.Vector3(a[0], a[1], a[2]);
      var vb = new THREE.Vector3(b[0], b[1], b[2]);
      var len = va.distanceTo(vb);
      if (len < 1e-6) return this;
      var g = new THREE.CylinderGeometry(r, r, len, seg || 6, 1);
      var dir = vb.clone().sub(va).normalize();
      var q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir);
      var m = new THREE.Matrix4().compose(va.clone().add(vb).multiplyScalar(0.5), q, new THREE.Vector3(1, 1, 1));
      return this.add(bucket || "solid", g, color, m);
    };

    // Наклонная плита (горка): от точки a (низ) к точке b, ширина w, толщина t.
    Builder.prototype.ramp = function (a, b, w, t, color) {
      var va = new THREE.Vector3(a[0], a[1], a[2]);
      var vb = new THREE.Vector3(b[0], b[1], b[2]);
      var len = va.distanceTo(vb);
      var g = new THREE.BoxGeometry(w, len, t);
      var dir = vb.clone().sub(va).normalize();
      var q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir);
      var m = new THREE.Matrix4().compose(va.clone().add(vb).multiplyScalar(0.5), q, new THREE.Vector3(1, 1, 1));
      return this.add("solid", g, color, m);
    };

    // Мягкое пятно на земле: эллипс rx×ry, прозрачность от центра (alpha) к краю (0).
    Builder.prototype.softDisc = function (rx, ry, x, y, z, color, alpha, bucket) {
      var seg = 28;
      var pos = [];
      var col = [];
      tmpColor.set(color);
      for (var i = 0; i < seg; i++) {
        var a0 = (i / seg) * Math.PI * 2,
          a1 = ((i + 1) / seg) * Math.PI * 2;
        pos.push(x, y, z, x + Math.cos(a0) * rx, y + Math.sin(a0) * ry, z, x + Math.cos(a1) * rx, y + Math.sin(a1) * ry, z);
        col.push(tmpColor.r, tmpColor.g, tmpColor.b, alpha, tmpColor.r, tmpColor.g, tmpColor.b, 0, tmpColor.r, tmpColor.g, tmpColor.b, 0);
      }
      var g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
      g.setAttribute("normal", new THREE.Float32BufferAttribute(new Array(pos.length).fill(0).map(function (v, k) {
        return k % 3 === 2 ? 1 : 0;
      }), 3));
      g.setAttribute("color", new THREE.Float32BufferAttribute(col, 4));
      this[bucket || "decal"].push({ geo: g, color: null, alpha: 1, ownColors: true });
      return this;
    };

    // Пунктир вокруг прямоугольника w×d (граница проекта). Штрих 1.6 м, промежуток 1.0 м.
    Builder.prototype.dashedRect = function (w, d, z) {
      var dash = 1.6,
        gap = 1.0,
        thick = 0.28;
      var hw = w / 2,
        hd = d / 2;
      var sides = [
        [-hw, -hd, hw, -hd],
        [hw, -hd, hw, hd],
        [hw, hd, -hw, hd],
        [-hw, hd, -hw, -hd],
      ];
      var self = this;
      sides.forEach(function (s) {
        var len = Math.hypot(s[2] - s[0], s[3] - s[1]);
        var dx = (s[2] - s[0]) / len,
          dy = (s[3] - s[1]) / len;
        var n = Math.max(1, Math.floor((len + gap) / (dash + gap)));
        var used = n * dash + (n - 1) * gap;
        var start = (len - used) / 2;
        for (var i = 0; i < n; i++) {
          var c = start + i * (dash + gap) + dash / 2;
          self.box(dash, thick, 0.04, s[0] + dx * c, s[1] + dy * c, z || 0.02, P.brand, Math.atan2(dy, dx), "outline");
        }
      });
      return this;
    };

    // Пунктир вдоль ломаной (участок улицы для освещения).
    Builder.prototype.dashedLine = function (pts, z) {
      var dash = 2.2,
        gap = 1.4,
        thick = 0.35;
      for (var i = 0; i < pts.length - 1; i++) {
        var a = pts[i],
          b = pts[i + 1];
        var len = Math.hypot(b[0] - a[0], b[1] - a[1]);
        if (len < 0.01) continue;
        var dx = (b[0] - a[0]) / len,
          dy = (b[1] - a[1]) / len;
        for (var s = 0; s < len; s += dash + gap) {
          var l = Math.min(dash, len - s);
          var c = s + l / 2;
          this.box(l, thick, 0.04, a[0] + dx * c, a[1] + dy * c, z || 0.03, P.brand, Math.atan2(dy, dx), "outline");
        }
      }
      return this;
    };

    // ── Мелкие объекты (общие для всех моделей) ──

    // Дерево: лиственное (неровный икосаэдр) или ель (два конуса). s — масштаб 0.8–1.25.
    Builder.prototype.tree = function (x, y, s, rand, conifer) {
      s = s || 1;
      this.cyl(0.2 * s, 0.15 * s, 1.7 * s, 6, x, y, 0, P.trunk);
      if (conifer) {
        var c = P.conifer[Math.floor(rand() * P.conifer.length)];
        var g1 = new THREE.ConeGeometry(1.7 * s, 3.0 * s, 7);
        g1.rotateX(Math.PI / 2);
        this.add("solid", g1, c, new THREE.Matrix4().makeTranslation(x, y, 1.2 * s + 1.5 * s));
        var g2 = new THREE.ConeGeometry(1.2 * s, 2.4 * s, 7);
        g2.rotateX(Math.PI / 2);
        this.add("solid", g2, c, new THREE.Matrix4().makeTranslation(x, y, 2.9 * s + 1.2 * s));
        return this;
      }
      var g = new THREE.IcosahedronGeometry(1.9 * s, 1);
      // Чуть «мнём» вершины — крона выглядит живой, но остаётся аккуратной.
      var p = g.attributes.position;
      var seen = {};
      for (var i = 0; i < p.count; i++) {
        var key = p.getX(i).toFixed(3) + "," + p.getY(i).toFixed(3) + "," + p.getZ(i).toFixed(3);
        if (!seen[key]) seen[key] = 0.9 + rand() * 0.2;
        var k = seen[key];
        p.setXYZ(i, p.getX(i) * k, p.getY(i) * k, p.getZ(i) * k * 1.1);
      }
      var leaf = P.leaf[Math.floor(rand() * P.leaf.length)];
      this.add("solid", g, leaf, new THREE.Matrix4().makeTranslation(x, y, 2.9 * s));
      return this;
    };

    // Скамейка 1.8 м: сиденье и спинка из дерева, ножки металлические. rot — радианы.
    Builder.prototype.bench = function (x, y, rot) {
      var m = new THREE.Matrix4().makeRotationZ(rot || 0).setPosition(x, y, 0);
      var b = new Builder();
      b.box(1.8, 0.45, 0.07, 0, 0, 0.42, P.wood);
      b.box(1.8, 0.07, 0.38, 0, 0.2, 0.55, P.wood);
      b.box(0.07, 0.42, 0.42, -0.75, 0, 0, P.metalDark);
      b.box(0.07, 0.42, 0.42, 0.75, 0, 0, P.metalDark);
      b.box(0.07, 0.07, 0.95, -0.75, 0.22, 0, P.metalDark);
      b.box(0.07, 0.07, 0.95, 0.75, 0.22, 0, P.metalDark);
      return this.merge(b, m);
    };

    // Урна.
    Builder.prototype.bin = function (x, y) {
      this.cyl(0.25, 0.28, 0.8, 8, x, y, 0, P.metal);
      this.cyl(0.3, 0.3, 0.06, 8, x, y, 0.8, P.metalDark);
      return this;
    };

    // Парковый фонарь 3.6 м.
    Builder.prototype.parkLamp = function (x, y) {
      this.cyl(0.08, 0.06, 3.4, 6, x, y, 0, P.metalDark);
      this.cyl(0.22, 0.16, 0.35, 6, x, y, 3.3, P.metalDark);
      this.cyl(0.18, 0.18, 0.18, 6, x, y, 3.2, P.glow, "glow");
      return this;
    };

    // Вложить части другого сборщика с матрицей m.
    Builder.prototype.merge = function (other, m) {
      var self = this;
      ["solid", "glass", "glow", "decal", "outline"].forEach(function (bucket) {
        other[bucket].forEach(function (part) {
          if (m) part.geo.applyMatrix4(m);
          self[bucket].push(part);
        });
      });
      return this;
    };

    // Слить части одного вида в одну геометрию: позиции, нормали (плоские грани), цвета.
    function mergeBucket(parts, withAlpha) {
      if (!parts.length) return null;
      var total = 0;
      parts.forEach(function (p) {
        total += p.geo.attributes.position.count;
      });
      var pos = new Float32Array(total * 3);
      var nor = new Float32Array(total * 3);
      var col = new Float32Array(total * (withAlpha ? 4 : 3));
      var off = 0;
      parts.forEach(function (part) {
        var g = part.geo;
        if (!part.ownColors) g.computeVertexNormals(); // не индексированная геометрия → нормали граней
        var pa = g.attributes.position,
          na = g.attributes.normal,
          ca = g.attributes.color;
        if (!part.ownColors) tmpColor.set(part.color);
        for (var i = 0; i < pa.count; i++) {
          pos[(off + i) * 3] = pa.getX(i);
          pos[(off + i) * 3 + 1] = pa.getY(i);
          pos[(off + i) * 3 + 2] = pa.getZ(i);
          nor[(off + i) * 3] = na ? na.getX(i) : 0;
          nor[(off + i) * 3 + 1] = na ? na.getY(i) : 0;
          nor[(off + i) * 3 + 2] = na ? na.getZ(i) : 1;
          var stride = withAlpha ? 4 : 3;
          if (part.ownColors) {
            col[(off + i) * stride] = ca.getX(i);
            col[(off + i) * stride + 1] = ca.getY(i);
            col[(off + i) * stride + 2] = ca.getZ(i);
            if (withAlpha) col[(off + i) * stride + 3] = ca.itemSize === 4 ? ca.getW(i) : 1;
          } else {
            col[(off + i) * stride] = tmpColor.r;
            col[(off + i) * stride + 1] = tmpColor.g;
            col[(off + i) * stride + 2] = tmpColor.b;
            if (withAlpha) col[(off + i) * stride + 3] = part.alpha;
          }
        }
        off += pa.count;
        g.dispose();
      });
      var out = new THREE.BufferGeometry();
      out.setAttribute("position", new THREE.BufferAttribute(pos, 3));
      out.setAttribute("normal", new THREE.BufferAttribute(nor, 3));
      out.setAttribute("color", new THREE.BufferAttribute(col, withAlpha ? 4 : 3));
      out.computeBoundingBox();
      out.computeBoundingSphere();
      return out;
    }

    Builder.prototype.finish = function () {
      return {
        solid: mergeBucket(this.solid, false),
        glass: mergeBucket(this.glass, true),
        glow: mergeBucket(this.glow, false),
        decal: mergeBucket(this.decal, true),
        outline: mergeBucket(this.outline, false),
      };
    };

    // ───────────── Модели ─────────────

    // Сквер 40×30: мощение, четыре газона, крестом дорожки, фонтан в центре, деревья, скамейки, фонари.
    function square(b, rand) {
      var W = 40,
        D = 30;
      b.softDisc(W / 2 + 2, D / 2 + 2, 0, 0, 0.01, P.shadow, 0.1);
      b.box(W, D, 0.1, 0, 0, 0, P.paving);
      var path = 3.2;
      var qw = (W - path) / 2 - 1.2,
        qd = (D - path) / 2 - 1.2;
      var quads = [
        [-1, -1],
        [1, -1],
        [1, 1],
        [-1, 1],
      ];
      quads.forEach(function (q, i) {
        var cx = q[0] * (path / 2 + qw / 2 + 0.2),
          cy = q[1] * (path / 2 + qd / 2 + 0.2);
        b.box(qw, qd, 0.08, cx, cy, 0.1, i % 2 ? P.lawn : P.lawnDark);
        b.box(qw + 0.3, 0.15, 0.22, cx, cy - (qd / 2 + 0.07) * 1, 0.05, P.curb);
        b.box(qw + 0.3, 0.15, 0.22, cx, cy + (qd / 2 + 0.07), 0.05, P.curb);
      });
      // Площадка в центре и фонтан.
      b.cyl(6.2, 6.2, 0.06, 28, 0, 0, 0.1, P.pavingDark);
      b.cyl(2.8, 2.8, 0.5, 20, 0, 0, 0.1, P.stone);
      b.cyl(2.45, 2.45, 0.06, 20, 0, 0, 0.5, P.water);
      b.cyl(0.5, 0.35, 1.0, 10, 0, 0, 0.5, P.stone);
      b.cyl(0.9, 0.9, 0.12, 12, 0, 0, 1.45, P.stone);
      // Цветники у входов на площадку.
      [
        [0, 10.5],
        [0, -10.5],
      ].forEach(function (c) {
        b.box(5, 1.6, 0.35, c[0] + 0, c[1], 0.1, P.soil);
        for (var k = 0; k < 9; k++) {
          var f = new THREE.IcosahedronGeometry(0.28, 0);
          b.add("solid", f, P.flowers[k % P.flowers.length], new THREE.Matrix4().makeTranslation(c[0] - 2 + k * 0.5, c[1] + (k % 2 ? 0.35 : -0.35), 0.55));
        }
      });
      // Деревья на газонах: по 3–4 на четверть, лиственные и ели, без попадания на дорожки.
      quads.forEach(function (q) {
        var n = 3 + (rand() > 0.5 ? 1 : 0);
        for (var k = 0; k < n; k++) {
          var tx = q[0] * (path / 2 + 2.6 + rand() * (qw - 5.2));
          var ty = q[1] * (path / 2 + 2.6 + rand() * (qd - 5.2));
          b.tree(tx, ty, 0.85 + rand() * 0.35, rand, rand() < 0.3);
        }
      });
      // Скамейки вдоль дорожек у площадки, лицом к дорожке.
      [
        [7.5, 2.6, Math.PI],
        [11.5, 2.6, Math.PI],
        [-7.5, -2.6, 0],
        [-11.5, -2.6, 0],
        [2.6, 8.5, -Math.PI / 2],
        [-2.6, -8.5, Math.PI / 2],
      ].forEach(function (s) {
        b.bench(s[0], s[1], s[2]);
      });
      [
        [5.2, 5.2],
        [-5.2, 5.2],
        [5.2, -5.2],
        [-5.2, -5.2],
      ].forEach(function (c) {
        b.parkLamp(c[0], c[1]);
      });
      b.bin(7.5, -2.4);
      b.bin(-7.5, 2.4);
    }

    // Детская площадка 24×18: мягкое покрытие, башня с горкой, качели, песочница, балансир, скамейки.
    function playground(b, rand) {
      var W = 24,
        D = 18;
      b.softDisc(W / 2 + 1.5, D / 2 + 1.5, 0, 0, 0.01, P.shadow, 0.1);
      b.box(W, D, 0.12, 0, 0, 0, P.rubber);
      // Бортик.
      b.box(W, 0.3, 0.25, 0, -D / 2 + 0.15, 0, P.curb);
      b.box(W, 0.3, 0.25, 0, D / 2 - 0.15, 0, P.curb);
      b.box(0.3, D, 0.25, -W / 2 + 0.15, 0, 0, P.curb);
      b.box(0.3, D, 0.25, W / 2 - 0.15, 0, 0, P.curb);
      // Башня: 4 стойки, площадка на 1.2 м, перила, крыша-пирамида.
      var tx = -6,
        ty = 2.5;
      [
        [-1, -1],
        [1, -1],
        [1, 1],
        [-1, 1],
      ].forEach(function (c) {
        b.box(0.14, 0.14, 2.7, tx + c[0] * 0.95, ty + c[1] * 0.95, 0.12, P.teal);
      });
      b.box(2.1, 2.1, 0.14, tx, ty, 1.2, P.white);
      b.box(2.1, 0.08, 0.6, tx, ty + 1.0, 1.34, P.teal);
      b.box(0.08, 2.1, 0.6, tx - 1.0, ty, 1.34, P.teal);
      var roof = new THREE.ConeGeometry(1.75, 1.1, 4);
      roof.rotateX(Math.PI / 2);
      roof.rotateZ(Math.PI / 4);
      b.add("solid", roof, P.coral, new THREE.Matrix4().makeTranslation(tx, ty, 2.82 + 0.55));
      // Горка вниз к югу, лестница на север.
      b.ramp([tx, ty - 1.0, 1.3], [tx, ty - 4.6, 0.3], 0.7, 0.08, P.yellow);
      b.ramp([tx - 0.38, ty - 1.0, 1.55], [tx - 0.38, ty - 4.6, 0.55], 0.06, 0.1, P.yellow);
      b.ramp([tx + 0.38, ty - 1.0, 1.55], [tx + 0.38, ty - 4.6, 0.55], 0.06, 0.1, P.yellow);
      b.box(0.8, 0.5, 0.3, tx, ty - 4.85, 0.12, P.yellow);
      for (var s = 0; s < 4; s++) b.box(0.8, 0.12, 0.06, tx + 1.6, ty + 0.2 - s * 0.05, 0.3 * (s + 1), P.white);
      b.rod([tx + 1.2, ty - 0.2, 0.12], [tx + 1.2, ty - 0.2, 1.3], 0.05, 6, P.teal);
      b.rod([tx + 2.0, ty - 0.2, 0.12], [tx + 2.0, ty - 0.2, 0.2], 0.05, 6, P.teal);
      b.ramp([tx + 1.6, ty - 0.2 + 0.0, 0.12], [tx + 1.0, ty - 0.2, 1.2], 0.8, 0.04, P.white);
      // Качели: А-образные стойки, перекладина 3.2 м, два сиденья на тросах.
      var sx = 5.5,
        sy = 3.5,
        top = 2.4;
      [-1.7, 1.7].forEach(function (dx) {
        b.rod([sx + dx, sy - 0.9, 0.12], [sx + dx, sy, top], 0.06, 6, P.metal);
        b.rod([sx + dx, sy + 0.9, 0.12], [sx + dx, sy, top], 0.06, 6, P.metal);
      });
      b.rod([sx - 1.75, sy, top], [sx + 1.75, sy, top], 0.07, 6, P.metal);
      [-0.75, 0.75].forEach(function (dx) {
        b.rod([sx + dx - 0.2, sy, top], [sx + dx - 0.2, sy, 0.55], 0.015, 4, P.metalDark);
        b.rod([sx + dx + 0.2, sy, top], [sx + dx + 0.2, sy, 0.55], 0.015, 4, P.metalDark);
        b.box(0.5, 0.22, 0.05, sx + dx, sy, 0.5, P.coral);
      });
      // Песочница 3×3 с деревянным бортом.
      var px = 5.5,
        py = -4.2;
      b.box(3, 0.22, 0.32, px, py - 1.39, 0.12, P.wood);
      b.box(3, 0.22, 0.32, px, py + 1.39, 0.12, P.wood);
      b.box(0.22, 2.56, 0.32, px - 1.39, py, 0.12, P.wood);
      b.box(0.22, 2.56, 0.32, px + 1.39, py, 0.12, P.wood);
      b.box(2.56, 2.56, 0.18, px, py, 0.12, P.sand);
      // Балансир.
      b.box(0.3, 0.3, 0.45, -1, -5, 0.12, P.metalDark);
      var plank = new THREE.Matrix4().makeRotationY(0.16).setPosition(-1, -5, 0.62);
      b.add("solid", new THREE.BoxGeometry(3.2, 0.28, 0.08), P.yellow, plank);
      // Скамейки у края для родителей и пара деревьев.
      b.bench(-1, 7.9, Math.PI);
      b.bench(3, 7.9, Math.PI);
      b.tree(-10.2, 7, 0.75, rand, false);
      b.tree(10.4, -7, 0.75, rand, true);
      b.bin(-3, 7.9);
    }

    // Спортплощадка 32×20: искусственная трава полосами, разметка, ворота с сеткой, забор.
    function sports(b) {
      var W = 32,
        D = 20,
        FW = 28,
        FD = 16;
      b.softDisc(W / 2 + 1.5, D / 2 + 1.5, 0, 0, 0.01, P.shadow, 0.1);
      b.box(W, D, 0.1, 0, 0, 0, P.stone);
      var stripes = 10;
      for (var i = 0; i < stripes; i++) {
        var sw = FW / stripes;
        b.box(sw, FD, 0.06, -FW / 2 + sw * (i + 0.5), 0, 0.1, i % 2 ? P.turf : P.turf2);
      }
      var lz = 0.16,
        lt = 0.12,
        lh = 0.015;
      // Внешняя линия, средняя линия, центральный круг, штрафные.
      b.box(FW - 0.6, lt, lh, 0, -FD / 2 + 0.3, lz, P.line);
      b.box(FW - 0.6, lt, lh, 0, FD / 2 - 0.3, lz, P.line);
      b.box(lt, FD - 0.6, lh, -FW / 2 + 0.3, 0, lz, P.line);
      b.box(lt, FD - 0.6, lh, FW / 2 - 0.3, 0, lz, P.line);
      b.box(lt, FD - 0.6, lh, 0, 0, lz, P.line);
      for (var k = 0; k < 32; k++) {
        var a = (k / 32) * Math.PI * 2;
        b.box(0.62, lt, lh, Math.cos(a) * 3, Math.sin(a) * 3, lz, P.line, a + Math.PI / 2);
      }
      b.cyl(0.15, 0.15, lh, 8, 0, 0, lz, P.line);
      [-1, 1].forEach(function (side) {
        var gx = side * (FW / 2 - 0.3);
        b.box(4, lt, lh, gx - side * 2, -3, lz, P.line);
        b.box(4, lt, lh, gx - side * 2, 3, lz, P.line);
        b.box(lt, 6, lh, gx - side * 4, 0, lz, P.line);
        b.cyl(0.13, 0.13, lh, 8, gx - side * 6, 0, lz, P.line);
        // Ворота 3×2 м: стойки, перекладина, задняя рама, сетка.
        var back = gx + side * 1.0;
        b.rod([gx, -1.5, 0.16], [gx, -1.5, 2.0], 0.06, 8, P.white);
        b.rod([gx, 1.5, 0.16], [gx, 1.5, 2.0], 0.06, 8, P.white);
        b.rod([gx, -1.5, 2.0], [gx, 1.5, 2.0], 0.06, 8, P.white);
        b.rod([gx, -1.5, 2.0], [back, -1.5, 0.16], 0.03, 6, P.white);
        b.rod([gx, 1.5, 2.0], [back, 1.5, 0.16], 0.03, 6, P.white);
        b.rod([back, -1.5, 0.16], [back, 1.5, 0.16], 0.03, 6, P.white);
        var net = new THREE.PlaneGeometry(3, Math.hypot(1.0, 1.84));
        var tilt = new THREE.Matrix4()
          .makeRotationY(side * (Math.PI / 2 - Math.atan2(1.84, 1.0)))
          .premultiply(new THREE.Matrix4().makeTranslation(gx + side * 0.5, 0, 1.08));
        net.rotateX(Math.PI / 2);
        net.rotateZ(Math.PI / 2);
        b.add("glass", net, P.net, tilt, 0.55);
        // Высокий забор за воротами (3 м) с сеткой.
        var fx = side * (W / 2 - 0.1);
        for (var y = -D / 2; y <= D / 2 + 1e-6; y += D / 4) b.cyl(0.05, 0.05, 3, 6, fx, y, 0, P.fence);
        b.box(0.06, D, 0.06, fx, 0, 2.95, P.fence);
        b.box(0.04, D, 2.8, fx, 0, 0.1, P.net, 0, "glass", 0.22);
      });
      // Невысокий забор вдоль длинных сторон (1.1 м) — поле хорошо видно сверху.
      [-1, 1].forEach(function (side) {
        var fy = side * (D / 2 - 0.1);
        for (var x = -W / 2; x <= W / 2 + 1e-6; x += 4) b.cyl(0.05, 0.05, 1.1, 6, x, fy, 0, P.fence);
        b.box(W, 0.06, 0.06, 0, fy, 1.05, P.fence);
        b.box(W, 0.04, 0.9, 0, fy, 0.12, P.net, 0, "glass", 0.22);
      });
      b.bench(-6, -D / 2 + 1.1, 0);
      b.bench(6, -D / 2 + 1.1, 0);
    }

    // Остановка 12×4.5: платформа с бордюром и тактильной полосой, павильон со стеклом,
    // скамья, табличка, урна. Улица — с юга (−y): павильон открыт к дороге.
    function stop(b) {
      var W = 12,
        D = 4.5;
      b.softDisc(W / 2 + 1, D / 2 + 1, 0, 0, 0.01, P.shadow, 0.1);
      b.box(W, D, 0.15, 0, 0, 0, P.stone);
      b.box(W, 0.3, 0.2, 0, -D / 2 + 0.15, 0, P.curb);
      b.box(W - 1, 0.4, 0.02, 0, -D / 2 + 0.75, 0.15, P.tactile);
      var py = 0.85,
        pw = 6,
        pd = 1.7;
      [
        [-pw / 2, -pd / 2],
        [pw / 2, -pd / 2],
        [pw / 2, pd / 2],
        [-pw / 2, pd / 2],
      ].forEach(function (c) {
        b.box(0.1, 0.1, 2.5, c[0], py + c[1], 0.15, P.metalDark);
      });
      // Крыша: светлая плита с зелёным торцом.
      b.box(pw + 0.6, pd + 0.7, 0.12, 0, py - 0.1, 2.65, P.white);
      b.box(pw + 0.62, pd + 0.72, 0.1, 0, py - 0.1, 2.55, P.brandLight);
      // Стекло: задняя стенка и боковины.
      b.box(pw - 0.1, 0.04, 2.15, 0, py + pd / 2, 0.3, P.glass, 0, "glass", 0.45);
      b.box(0.04, pd - 0.1, 2.15, -pw / 2, py, 0.3, P.glass, 0, "glass", 0.45);
      b.box(0.04, pd - 0.1, 2.15, pw / 2, py, 0.3, P.glass, 0, "glass", 0.45);
      b.box(pw, 0.06, 0.06, 0, py + pd / 2, 2.4, P.metalDark);
      b.box(pw, 0.06, 0.06, 0, py + pd / 2, 0.25, P.metalDark);
      // Скамья вдоль задней стенки.
      b.box(3.4, 0.42, 0.07, -0.6, py + 0.45, 0.47, P.wood);
      b.box(0.08, 0.3, 0.32, -2.1, py + 0.45, 0.15, P.metalDark);
      b.box(0.08, 0.3, 0.32, 0.9, py + 0.45, 0.15, P.metalDark);
      // Информационный щит у правой боковины.
      b.box(1.0, 0.06, 1.5, 2.1, py + pd / 2 - 0.05, 0.6, P.white);
      b.box(1.0, 0.07, 0.25, 2.1, py + pd / 2 - 0.05, 1.85, P.brand);
      // Табличка остановки на столбе у бордюра.
      b.cyl(0.05, 0.05, 2.9, 6, 4.9, -1.2, 0.15, P.metal);
      b.box(0.62, 0.05, 0.62, 4.9, -1.2, 2.55, P.brand);
      b.box(0.36, 0.06, 0.2, 4.9, -1.2, 2.75, P.white);
      b.bin(-4.6, 0.9);
    }

    // Освещение: опоры через ~30 м вдоль участка. pts — точки опор в метрах относительно якоря:
    // [{p:[x,y], dir:[dx,dy]}]; line — сама ось участка (для пунктира). offset — от оси вбок, м.
    function lighting(b, opts) {
      var poles = opts.poles || [];
      var offset = opts.offset == null ? 5 : opts.offset;
      var H = 8;
      poles.forEach(function (pole) {
        var dx = pole.dir[0],
          dy = pole.dir[1];
        var nx = dy,
          ny = -dx; // правая нормаль к направлению участка
        var x = pole.p[0] + nx * offset,
          y = pole.p[1] + ny * offset;
        var ax = -nx,
          ay = -ny; // кронштейн смотрит на улицу
        b.box(0.45, 0.45, 0.35, x, y, 0, P.curb);
        b.cyl(0.13, 0.08, H, 8, x, y, 0.35, P.metal);
        b.rod([x, y, H + 0.2], [x + ax * 1.7, y + ay * 1.7, H + 0.45], 0.05, 6, P.metal);
        var head = new THREE.BoxGeometry(0.75, 0.32, 0.14);
        var rot = Math.atan2(ay, ax);
        b.add("solid", head, P.metalDark, new THREE.Matrix4().makeRotationZ(rot).setPosition(x + ax * 1.9, y + ay * 1.9, H + 0.4));
        var lens = new THREE.BoxGeometry(0.6, 0.24, 0.05);
        b.add("glow", lens, P.glow, new THREE.Matrix4().makeRotationZ(rot).setPosition(x + ax * 1.9, y + ay * 1.9, H + 0.3));
        b.softDisc(6, 6, x + ax * 1.9, y + ay * 1.9, 0.02, P.lightPool, 0.38);
      });
      if (opts.line && opts.line.length > 1) b.dashedLine(opts.line, 0.03);
    }

    var BUILDERS = { square: square, playground: playground, sports: sports, stop: stop };

    // Построить геометрии объекта. opts: {seed, w, d} для прямоугольных; {poles, line, offset} — освещение.
    // Возврат: {solid, glass, glow, decal, outline} (BufferGeometry или null), height — высота верха.
    function build(kind, opts) {
      opts = opts || {};
      var b = new Builder();
      var rand = rng(opts.seed || kind);
      if (kind === "lighting") lighting(b, opts);
      else if (BUILDERS[kind]) {
        BUILDERS[kind](b, rand);
        if (opts.w && opts.d) b.dashedRect(opts.w + 1.6, opts.d + 1.6, 0.02);
      } else throw new Error("неизвестный вид объекта: " + kind);
      var geos = b.finish();
      var box = new THREE.Box3();
      ["solid", "glass", "glow"].forEach(function (k) {
        if (geos[k]) box.union(geos[k].boundingBox);
      });
      geos.height = box.isEmpty() ? 1 : box.max.z;
      geos.bounds = box;
      return geos;
    }

    return { build: build, palette: P, rng: rng };
  }

  return { create: create };
});
