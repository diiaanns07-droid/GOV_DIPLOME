/*
 * Birge · 3D-Астана (R05, раунд 15) — условные low-poly модели ориентиров города.
 *
 * Байтерек, Хан Шатыр, Ақорда, «Нұр Әлем», Дворец мира и согласия — из простых фигур three.js тем же сборщиком,
 * что и объекты 3D-превью (build3d-models.js): плоские мягкие цвета, затенение у земли, мягкая тень, постройка «по
 * частям». Это УСЛОВНЫЕ модели: форма упрощена, размеры примерные (data/civic/astana/landmarks/README.md) — не точные
 * копии зданий; так и написано в «?» легенды карты.
 *
 * Оси: x — восток, y — север, z — вверх, метры; (0, 0) — точка ориентира из landmarks.json. Поворот rotation_deg
 * (по часовой, как азимут) ставит модуль 3D в сцене, как у проектов: «главный фасад» модели смотрит на +x — вдоль оси
 * бульвара Нұржол (Хан Шатыр — Байтерек — Ақорда — пирамида).
 *
 * Бюджет: все пять вместе — меньше 50 000 треугольников (tests/civic/R05/round15/test_landmarks.mjs).
 * Подключение: build3d.js грузит этот файл сам и только когда нужен (наклонённая карта с 13-го масштаба, ориентир
 * в кадре): CivicBuild3DLandmarks.create(THREE, Models) → { build(spec), triangles(geos), MODELS }.
 * В Node: require(...).create(THREE, Models) — для тестов размеров и бюджета.
 */
(function (root, factory) {
  "use strict";
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.CivicBuild3DLandmarks = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  // Цвета ориентиров — светлые и тёплые, в тон подложке Birge (здания #ECE9E2…#D2CDC4, ориентиры #E6DCC8, вода #C3DFEC):
  // модели читаются как «главные здания города», но не спорят со значками жалоб (насыщенный цвет — только у золота,
  // купола и стекла, маленькими пятнами). Зелёного нет: на карте зелёный значит «исправлено».
  var C = {
    white: "#f6f5f1",
    whiteShade: "#e9e8e2",
    stone: "#e4dfd3",
    stoneLight: "#eeeae1",
    stoneDark: "#d3ccbc",
    gold: "#e2b64a",
    goldDeep: "#c99a33",
    tent: "#efe7d4",
    tentRib: "#c9bb9c",
    tentBase: "#ddd6c6",
    mast: "#b9bdb8",
    wall: "#f3f1eb",
    window: "#c8d2d6",
    roof: "#e3e4df",
    dome: "#3f7fbe",
    domeLight: "#5d97cf",
    glass: "#a9c8d8",
    glassTop: "#c3dce8",
    glassDark: "#8fb2c6",
    frame: "#7f97a3",
    pyramid: "#e6dfcf",
    pyramidBand: "#d4cab4",
    apexGold: "#e9c862",
    apexBlue: "#7fb4d8",
    shadow: "#152c26",
  };

  function create(THREE, Models) {
    if (!THREE || !Models || !Models.Builder) throw new Error("CivicBuild3DLandmarks: нужны three.js и CivicBuild3DModels.create(THREE)");
    var Builder = Models.Builder;
    var TAU = Math.PI * 2;

    function translate(x, y, z) {
      return new THREE.Matrix4().makeTranslation(x, y, z);
    }

    // Гладкая поверхность по сетке параметров (u — по кругу, v — снизу вверх): fn(u, v) → [x, y, z].
    // Нормали — по соседним узлам (центральные разности): шатёр и купол без «граней». Треугольники — против часовой
    // снаружи (лицевая сторона), если fn обходит u против часовой стрелки, а v идёт вверх.
    function gridGeo(nu, nv, fn, closedU) {
      var cols = nu + 1;
      var P = [];
      var i, j;
      for (j = 0; j <= nv; j++) for (i = 0; i <= nu; i++) P.push(fn(i / nu, j / nv));
      function at(ii, jj) {
        if (closedU) ii = ((ii % nu) + nu) % nu;
        else ii = Math.max(0, Math.min(nu, ii));
        jj = Math.max(0, Math.min(nv, jj));
        return P[jj * cols + ii];
      }
      var N = [];
      for (j = 0; j <= nv; j++) {
        for (i = 0; i <= nu; i++) {
          var a = at(i + 1, j),
            b = at(i - 1, j),
            c = at(i, j + 1),
            d = at(i, j - 1);
          var du = [a[0] - b[0], a[1] - b[1], a[2] - b[2]],
            dv = [c[0] - d[0], c[1] - d[1], c[2] - d[2]];
          var n = [du[1] * dv[2] - du[2] * dv[1], du[2] * dv[0] - du[0] * dv[2], du[0] * dv[1] - du[1] * dv[0]];
          var l = Math.hypot(n[0], n[1], n[2]) || 1;
          N.push([n[0] / l, n[1] / l, n[2] / l]);
        }
      }
      var pos = [],
        nor = [];
      function push(k) {
        pos.push(P[k][0], P[k][1], P[k][2]);
        nor.push(N[k][0], N[k][1], N[k][2]);
      }
      for (j = 0; j < nv; j++) {
        for (i = 0; i < nu; i++) {
          var k00 = j * cols + i,
            k10 = j * cols + i + 1,
            k11 = (j + 1) * cols + i + 1,
            k01 = (j + 1) * cols + i;
          push(k00);
          push(k10);
          push(k11);
          push(k00);
          push(k11);
          push(k01);
        }
      }
      var g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
      g.setAttribute("normal", new THREE.Float32BufferAttribute(nor, 3));
      return g;
    }

    // Эллиптический «пояс» (стенка без крыши и дна): полуоси rx, ry, высота h, низ на z.
    function ellipseWall(rx, ry, h, z, seg) {
      return gridGeo(
        seg,
        1,
        function (u, v) {
          var a = u * TAU;
          return [rx * Math.cos(a), ry * Math.sin(a), z + v * h];
        },
        true
      );
    }
    // Плоский эллипс (крыша пояса, площадка) на высоте z.
    function ellipseCap(rx, ry, z, seg) {
      var pos = [],
        nor = [];
      for (var i = 0; i < seg; i++) {
        var a0 = (i / seg) * TAU,
          a1 = ((i + 1) / seg) * TAU;
        pos.push(0, 0, z, rx * Math.cos(a0), ry * Math.sin(a0), z, rx * Math.cos(a1), ry * Math.sin(a1), z);
        nor.push(0, 0, 1, 0, 0, 1, 0, 0, 1);
      }
      var g = new THREE.BufferGeometry();
      g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
      g.setAttribute("normal", new THREE.Float32BufferAttribute(nor, 3));
      return g;
    }

    // ───────────── Байтерек ─────────────
    // Белый «ствол» из перекрещенных стоек (решётка), раскрывается вверху «кроной» и держит золотой шар Ø 22 м;
    // внизу — круглое основание с павильоном входа. Высота верха шара ≈ 105 м (условно).
    function baiterek(b) {
      var RS = 11,
        ZS = 94.5; // шар: радиус и центр (верх ≈ 105,5 м)
      b.softDisc(34, 34, 0, 0, 0.02, C.shadow, 0.07);
      b.group(function () {
        b.cyl(18, 18, 0.7, 48, 0, 0, 0, C.stone);
        b.cyl(15, 15, 0.5, 48, 0, 0, 0.7, C.stoneLight);
        // Павильон входа: низкий белый барабан, чуть сужается кверху.
        b.cyl(9.5, 8.6, 5.2, 32, 0, 0, 1.2, C.white);
        b.cyl(8.9, 8.9, 0.5, 32, 0, 0, 6.4, C.whiteShade);
      });
      // Ядро ствола — сплошная белая колонна (силуэт читается с 13-го масштаба, где стойки тоньше точки).
      b.group(function () {
        b.cyl(3.6, 2.9, 73, 16, 0, 0, 6.9, C.white);
      });
      // Решётка: два семейства по 12 стоек, закрученных навстречу (ромбы, как у настоящего ствола), профиль [z, r]:
      // ствол шириной с половину шара, внизу «корни», вверху раскрывается «чашей» и обнимает шар у экватора.
      var prof = [
        [1.2, 9.6],
        [5, 7.8],
        [11, 5.8],
        [24, 5.0],
        [46, 4.7],
        [64, 5.0],
        [73, 6.6],
        [80, 9.6],
        [85.5, 12.4],
        [90.5, 14.0],
        [95.5, 14.4],
        [99.5, 13.4],
      ];
      var N = 12,
        twist = 0.6,
        top = prof[prof.length - 1][0];
      [1, -1].forEach(function (fam) {
        for (var k = 0; k < N; k++) {
          b.group(function () {
            var a0 = (k / N) * TAU + (fam < 0 ? Math.PI / N : 0);
            var pts = prof.map(function (p) {
              var a = a0 + fam * twist * (p[0] / top);
              return [p[1] * Math.cos(a), p[1] * Math.sin(a), p[0]];
            });
            for (var i = 0; i < pts.length - 1; i++) b.rod(pts[i], pts[i + 1], i < 2 ? 0.95 : 0.75, 5, C.white);
          });
        }
      });
      // Кольцо «чаши» под шаром — светлая обвязка, на которую опираются стойки.
      b.group(function () {
        b.cyl(9.8, 9.8, 1.1, 32, 0, 0, 79.6, C.whiteShade);
      });
      // Шар: гладкое золото, низ чуть темнее (собственная тень).
      b.group(function () {
        b.add("solid", new THREE.IcosahedronGeometry(RS, 4), C.gold, translate(0, 0, ZS), 1, {
          round: [0, 0, ZS],
          grad: [ZS - RS, ZS + RS * 0.4, 0.78],
          flat: true,
        });
      });
    }

    // ───────────── Хан Шатыр ─────────────
    // Прозрачный шатёр на эллиптическом основании (условно 200 × 172 м), вершина смещена назад (на запад) и
    // переходит в мачту ≈ 150 м. Мембрана — тёплая светлая, тросы — тонкие полосы темнее.
    function khanShatyr(b, spec) {
      var size = (spec && spec.size_m) || {};
      var A = size.base_a || 100,
        B = size.base_b || 86;
      var H = 128, // вершина мембраны
        Z0 = 4, // мембрана начинается над поясом основания
        AX = -24,
        AY = 4; // смещение вершины (шатёр несимметричный, вершина ближе к западному краю)
      var W = function (t) {
        return Math.pow(1 - t, 1.16); // слегка вогнутые склоны: у земли положе, к вершине круче
      };
      var tent = function (u, v) {
        var a = u * TAU,
          w = W(v);
        return [AX + (A * Math.cos(a) - AX) * w, AY + (B * Math.sin(a) - AY) * w, Z0 + (H - Z0) * v];
      };
      b.softDisc(A + 26, B + 26, 0, 0, 0.02, C.shadow, 0.06);
      // Пояс основания: светлая стенка и плоская крыша кольца.
      b.group(function () {
        b.add("solid", ellipseWall(A + 2.5, B + 2.5, Z0 + 0.4, 0, 72), C.tentBase, null, 1, { keepNormals: true });
        b.add("solid", ellipseCap(A + 2.5, B + 2.5, Z0 + 0.4, 72), C.tentBase);
      });
      // Мембрана: 72 × 14 ячеек, гладкие нормали.
      b.group(function () {
        b.add("solid", gridGeo(72, 14, tent, true), C.tent, null, 1, { keepNormals: true, grad: [Z0, H * 0.6, 0.9] });
      });
      // Тросы: 18 полос от пояса к вершине, чуть над мембраной (0,35 м наружу), и три горизонтальных кольца.
      b.group(function () {
        var ribs = 18,
          seg = 12;
        for (var r = 0; r < ribs; r++) {
          var u0 = r / ribs;
          var du = 0.0035; // ширина полосы в долях окружности (~2 м у земли)
          var strip = gridGeo(
            1,
            seg,
            function (u, v) {
              var p = tent(u0 + (u - 0.5) * du * (1 - v * 0.85), v * 0.97);
              var n = [p[0] - AX * (1 - W(v)), p[1] - AY * (1 - W(v))];
              var l = Math.hypot(n[0], n[1]) || 1;
              return [p[0] + (n[0] / l) * 0.35, p[1] + (n[1] / l) * 0.35, p[2] + 0.1];
            },
            false
          );
          b.add("solid", strip, C.tentRib, null, 1, { keepNormals: true });
        }
        [0.22, 0.45, 0.68].forEach(function (v) {
          var ring = gridGeo(
            96,
            1,
            function (u, vv) {
              var p = tent(u, v + (vv - 0.5) * 0.012);
              var n = [p[0] - AX * (1 - W(v)), p[1] - AY * (1 - W(v))];
              var l = Math.hypot(n[0], n[1]) || 1;
              return [p[0] + (n[0] / l) * 0.3, p[1] + (n[1] / l) * 0.3, p[2]];
            },
            true
          );
          b.add("solid", ring, C.tentRib, null, 1, { keepNormals: true });
        });
      });
      // Венец на вершине и мачта до ≈ 150 м.
      b.group(function () {
        b.cyl(5.2, 3.6, 4.5, 20, AX, AY, H - 2.5, C.mast);
        b.cyl(1.25, 0.25, 150 - H - 2, 10, AX, AY, H + 2, C.mast);
      });
    }

    // ───────────── Ақорда ─────────────
    // Белое здание (центральная часть и два крыла), колоннада главного фасада на восток (к площади и Есилю), барабан
    // и голубой купол с золотым кольцом, шпиль до ≈ 80 м. Ряды окон — тонкие полосы на стенах.
    function akorda(b, spec) {
      var size = (spec && spec.size_m) || {};
      var L = size.length || 116,
        D = size.depth || 46;
      var cw = D,
        cl = 60,
        ch = 30; // центр: глубина по x, длина по y, высота
      var wl = (L - cl) / 2,
        ww = D - 8,
        wh = 24; // крылья
      b.softDisc(D / 2 + 22, L / 2 + 18, 0, 0, 0.02, C.shadow, 0.07);
      // Стилобат — светлая плита под всем зданием.
      b.group(function () {
        b.box(D + 18, L + 8, 1.2, 4, 0, 0, C.stone);
      });
      b.group(function () {
        b.box(cw, cl, ch, 0, 0, 1.2, C.wall);
        b.box(cw + 1.2, cl + 1.2, 1.4, 0, 0, 1.2 + ch, C.whiteShade); // карниз
      });
      [-1, 1].forEach(function (side) {
        b.group(function () {
          var y = side * (cl / 2 + wl / 2);
          b.box(ww, wl, wh, -2, y, 1.2, C.wall);
          b.box(ww + 1, wl + 0.6, 1.2, -2, y, 1.2 + wh, C.whiteShade);
          // Окна крыльев: три ряда полос на восточном и западном фасадах.
          [7, 13, 19].forEach(function (z) {
            b.box(0.25, wl - 6, 2.2, -2 + ww / 2 + 0.12, y, 1.2 + z, C.window);
            b.box(0.25, wl - 6, 2.2, -2 - ww / 2 - 0.12, y, 1.2 + z, C.window);
          });
        });
      });
      // Окна центральной части (по бокам от колоннады) и запада.
      b.group(function () {
        [8, 15, 22].forEach(function (z) {
          b.box(0.25, cl - 8, 2.4, -cw / 2 - 0.12, 0, 1.2 + z, C.window);
          b.box(0.25, 10, 2.4, cw / 2 + 0.12, 25, 1.2 + z, C.window);
          b.box(0.25, 10, 2.4, cw / 2 + 0.12, -25, 1.2 + z, C.window);
        });
      });
      // Колоннада главного фасада: 8 колонн, антаблемент сверху.
      b.group(function () {
        var x = cw / 2 + 5;
        for (var k = 0; k < 8; k++) {
          var y = -17.5 + k * 5;
          b.cyl(1.05, 0.9, 22, 12, x, y, 1.2, C.white);
        }
        b.box(8, 42, 3.4, cw / 2 + 4, 0, 23.2, C.wall);
        b.box(8.6, 43, 0.9, cw / 2 + 4, 0, 26.6, C.whiteShade);
      });
      // Барабан, купол, золотое кольцо, фонарь и шпиль.
      var zc = 1.2 + ch + 1.4;
      b.group(function () {
        b.cyl(13.2, 13.2, 9.5, 36, 0, 0, zc, C.wall);
        // Окна барабана — тёмный пояс по кругу.
        b.cyl(13.35, 13.35, 3, 36, 0, 0, zc + 3.2, C.window);
        b.cyl(14, 14, 1.1, 36, 0, 0, zc + 9.5, C.gold);
      });
      var zd = zc + 10.6,
        rd = 13.0,
        hd = 19;
      b.group(function () {
        var dome = gridGeo(
          36,
          9,
          function (u, v) {
            var a = u * TAU,
              ph = v * (Math.PI / 2) * 0.96;
            return [rd * Math.cos(ph) * Math.cos(a), rd * Math.cos(ph) * Math.sin(a), zd + hd * Math.sin(ph)];
          },
          true
        );
        b.add("solid", dome, C.dome, null, 1, { keepNormals: true, grad: [zd, zd + hd, 0.82] });
        b.cyl(2.6, 2.2, 4.2, 16, 0, 0, zd + hd - 1.2, C.gold);
        b.cyl(1.0, 0.18, 80 - (zd + hd + 3), 10, 0, 0, zd + hd + 3, C.gold);
      });
    }

    // ───────────── «Нұр Әлем» (шар ЭКСПО) ─────────────
    // Стеклянный шар Ø 80 м на низком основании, верх ≈ 100 м. Грани икосаэдра — как стеклянные панели: чуть разные
    // по тону (светлее к верху), тонкие рёбра каркаса — тремя кольцами.
    function nurAlem(b, spec, rand) {
      var R = 40,
        ZC = 59;
      b.softDisc(R + 20, R + 20, 0, 0, 0.02, C.shadow, 0.07);
      b.group(function () {
        b.cyl(31, 31, 1.0, 48, 0, 0, 0, C.stone);
        b.cyl(21, 24, 20, 36, 0, 0, 1.0, C.glassDark); // стеклянное основание под шаром (вход)
      });
      b.group(function () {
        var g = new THREE.IcosahedronGeometry(R, 4);
        g.translate(0, 0, ZC);
        // Тон панели — по высоте её центра (светлее к верху) и чуть случайно (детерминированно): живое стекло.
        var pa = g.attributes.position;
        var cols = [];
        var lo = new THREE.Color(C.glassDark),
          hi = new THREE.Color(C.glassTop),
          tmp = new THREE.Color();
        for (var i = 0; i < pa.count; i += 3) {
          var zc = (pa.getZ(i) + pa.getZ(i + 1) + pa.getZ(i + 2)) / 3;
          var k = Math.max(0, Math.min(1, (zc - (ZC - R)) / (2 * R)));
          tmp.copy(lo).lerp(hi, 0.25 + 0.75 * k);
          var j = 0.94 + rand() * 0.1;
          for (var q = 0; q < 3; q++) cols.push(tmp.r * j, tmp.g * j, tmp.b * j);
        }
        g.computeVertexNormals();
        g.setAttribute("color", new THREE.Float32BufferAttribute(cols, 3));
        b.solid.push({ geo: g, color: null, alpha: 1, ownColors: true, grp: b._grp });
        // Каркас: три кольца (экватор и две широты) — тонкие тёмные пояса.
        [-0.45, 0, 0.45].forEach(function (s) {
          var z = ZC + R * s,
            r = Math.sqrt(R * R - (R * s) * (R * s)) + 0.25;
          b.add("solid", ellipseWall(r, r, 0.7, z - 0.35, 64), C.frame, null, 1, { keepNormals: true, flat: true });
        });
      });
    }

    // ───────────── Дворец мира и согласия (пирамида) ─────────────
    // Квадратная пирамида 62 × 62 × 62 м на низком основании: светлый камень с поясами, верх — витраж (золото и голубой).
    function pyramid(b, spec) {
      var size = (spec && spec.size_m) || {};
      var S = (size.base || 62) / 2,
        H = spec && spec.height_m ? spec.height_m : 62;
      var ZB = 1.6; // основание
      var cut = 0.74; // доля высоты до витража
      function frustum(z0, z1, h0, h1, color, look) {
        // Четыре грани усечённой пирамиды (полуширины h0 → h1); плоские грани.
        var pos = [];
        var c0 = [
          [-h0, -h0],
          [h0, -h0],
          [h0, h0],
          [-h0, h0],
        ];
        var c1 = [
          [-h1, -h1],
          [h1, -h1],
          [h1, h1],
          [-h1, h1],
        ];
        for (var i = 0; i < 4; i++) {
          var j = (i + 1) % 4;
          pos.push(c0[i][0], c0[i][1], z0, c0[j][0], c0[j][1], z0, c1[j][0], c1[j][1], z1);
          if (h1 > 1e-6) pos.push(c0[i][0], c0[i][1], z0, c1[j][0], c1[j][1], z1, c1[i][0], c1[i][1], z1);
        }
        var g = new THREE.BufferGeometry();
        g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
        b.add("solid", g, color, null, 1, look);
      }
      b.softDisc(S + 20, S + 20, 0, 0, 0.02, C.shadow, 0.08);
      b.group(function () {
        b.box(2 * S + 12, 2 * S + 12, ZB, 0, 0, 0, C.stone);
      });
      var zc = ZB + H * cut,
        hc = S * (1 - cut);
      b.group(function () {
        frustum(ZB, zc, S, hc, C.pyramid, { grad: [ZB, zc, 0.88] });
        // Каменные пояса — чуть выступают (0,3 м), темнее.
        [0.2, 0.4, 0.6].forEach(function (f) {
          var z = ZB + H * f,
            h = S * (1 - f) + 0.3;
          frustum(z - 0.6, z + 0.6, h + 0.02, h - 0.02, C.pyramidBand, { flat: true });
        });
      });
      // Витраж: золотой, самая верхушка — голубая.
      b.group(function () {
        var zt = ZB + H * 0.9,
          ht = S * 0.1;
        frustum(zc, zt, hc, ht, C.apexGold, { flat: true });
        frustum(zt, ZB + H, ht, 0, C.apexBlue, { flat: true });
      });
    }

    var MODELS = { baiterek: baiterek, khan_shatyr: khanShatyr, akorda: akorda, nur_alem: nurAlem, pyramid: pyramid };

    // Построить геометрии ориентира по записи landmarks.json ({id, model, size_m, height_m}).
    // Возврат — как у Models.build: {solid, glass, glow, decal, outline, height, bounds}.
    function build(spec) {
      var fn = MODELS[spec && spec.model];
      if (!fn) throw new Error("неизвестная модель ориентира: " + (spec && spec.model));
      var b = new Builder();
      fn(b, spec, Models.rng("landmark-" + spec.id));
      var geos = b.finish();
      var box = new THREE.Box3();
      ["solid", "glass", "glow"].forEach(function (k) {
        if (geos[k]) box.union(geos[k].boundingBox);
      });
      geos.height = box.isEmpty() ? 1 : box.max.z;
      geos.bounds = box;
      return geos;
    }

    // Число треугольников (бюджет ≤ 50 000 на все ориентиры вместе).
    function triangles(geos) {
      var n = 0;
      ["solid", "glass", "glow", "decal", "outline"].forEach(function (k) {
        if (geos && geos[k]) n += geos[k].attributes.position.count / 3;
      });
      return n;
    }

    return { build: build, triangles: triangles, MODELS: Object.keys(MODELS), palette: C };
  }

  return { create: create, version: "r15-1" };
});
