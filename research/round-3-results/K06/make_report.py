"""Build report.html from out/headways.json (output of headway_calc.py). Static, self-contained, stdlib only.
Usage: python3 make_report.py out/headways.json report.html"""
import html, json, sys

src, dst = sys.argv[1], sys.argv[2]
res = json.load(open(src, encoding="utf-8"))
meta, c = res["meta"], res["counters"]

def f1(x): return f"{x:.1f}".replace(".", ",")
def f2(x): return f"{x:.2f}".replace(".", ",")

DT = {"weekday": "Будни", "weekend": "Выходные", "all": "Все дни"}
rows = {k: [] for k in DT}
SCALE = max(max(s["time_weighted_wait_min"], s["ptal_wait_min"]) for s in res["summary"]) * 1.02
for s in res["summary"]:
    base = s["pooled_H_min"] / 2
    total = base + s["excess_between_days_min"] + s["excess_within_day_min"]
    scale = SCALE  # minutes for full bar width (largest value on the page)
    seg = lambda v, cls: f'<span class="seg {cls}" style="width:{max(v, 0) / scale * 100:.1f}%"></span>'
    bar = (f'<div class="bar" title="H/2 {f1(base)} + между днями {f1(s["excess_between_days_min"])} + внутри дня '
           f'{f1(s["excess_within_day_min"])} мин">' + seg(base, "b0") + seg(s["excess_between_days_min"], "b1") +
           seg(s["excess_within_day_min"], "b2") +
           f'<span class="ptal" style="left:{min(s["ptal_wait_min"] / scale, 1) * 100:.1f}%"></span></div>')
    rows[s["day_type"]].append(
        f'<tr><td>{s["route"]}</td><td>{s["direction"]}</td><td>{s["window"]}</td><td>{s["days"]}</td>'
        f'<td>{f1(s["pooled_H_min"])}</td><td>{f2(s["pooled_cv"])}</td><td>{f2(s["median_daily_cv"])}</td>'
        f'<td>{f1(s["ptal_wait_min"])}</td><td>{f1(s["pooled_formula_wait_min"])}</td>'
        f'<td>{f1(s["daily_median_wait_min"])}</td><td>{f1(s["day_equal_mean_wait_min"])}</td>'
        f'<td class="rec">{f1(s["time_weighted_wait_min"])}</td><td>{f1(s["excess_between_days_min"])}</td>'
        f'<td>{f1(s["excess_within_day_min"])}</td><td class="barcell">{bar}</td></tr>')

def stats(dt):
    S = [s for s in res["summary"] if s["day_type"] == dt]
    within = sorted(s["excess_within_day_min"] for s in S)
    between = sorted(s["excess_between_days_min"] for s in S)
    gap_med = sorted(s["time_weighted_wait_min"] - s["daily_median_wait_min"] for s in S)
    over = sum(s["time_weighted_wait_min"] > s["ptal_wait_min"] for s in S)
    md = lambda v: (v[len(v) // 2 - 1] + v[len(v) // 2]) / 2
    return {"n": len(S), "w": (within[0], md(within), within[-1]), "b": (between[0], md(between), between[-1]),
            "g": (gap_med[0], md(gap_med), gap_med[-1]), "over": over}
wk = stats("weekday")

dur = "".join(
    f'<tr><td>{d["route"]}</td><td>{d["direction"]}</td><td>{d["window"]}</td><td>{d["n"]}</td>'
    f'<td>{f1(d["p50_min"])}</td><td>{f1(d["p90_min"])}</td></tr>'
    for d in res["durations_include_layover"] if d["day_type"] == "weekday")
excl = ", ".join(f'{x["route"]}/{x["direction"]} {x["date"]} ({x["departures"]})' for x in res["excluded_days"])

tabs = "".join(f'<button role="tab" data-t="{k}" aria-selected="{str(k == "weekday").lower()}">{v}</button>'
               for k, v in DT.items())
tables = "".join(
    f'<tbody data-t="{k}"{"" if k == "weekday" else " hidden"}>{"".join(v)}</tbody>' for k, v in rows.items())

page = f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Интервалы автобусов Астаны</title>
<style>
:root{{--bg:#fbfbf9;--fg:#1d1f22;--muted:#5d636b;--line:#dcdcd6;--card:#fff;--warn:#fff4dc;--warnline:#e2b33c;
--b0:#8a94a3;--b1:#d08a2e;--b2:#c2413b;--ptal:#1f5fbf;--rec:#eef4ff}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--bg:#16181b;--fg:#e8e9eb;--muted:#a0a6ae;
--line:#33373d;--card:#1e2125;--warn:#3a3020;--warnline:#b8862a;--b0:#6f7887;--b1:#d99a45;--b2:#e0625b;--ptal:#6ea0ef;--rec:#1d2738}}}}
:root[data-theme="dark"]{{--bg:#16181b;--fg:#e8e9eb;--muted:#a0a6ae;--line:#33373d;--card:#1e2125;--warn:#3a3020;
--warnline:#b8862a;--b0:#6f7887;--b1:#d99a45;--b2:#e0625b;--ptal:#6ea0ef;--rec:#1d2738}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}}
main{{max-width:1180px;margin:0 auto;padding:24px 16px 48px}}h1{{font-size:1.5rem;margin:0 0 4px}}
h2{{font-size:1.15rem;margin:32px 0 8px}}p,li,dd{{max-width:75ch;overflow-wrap:anywhere}}.muted{{color:var(--muted)}}
.banner{{background:var(--warn);border:1px solid var(--warnline);border-radius:8px;padding:12px 16px;margin:16px 0}}
.banner dl{{display:grid;grid-template-columns:max-content 1fr;gap:4px 14px;margin:0}}.banner dt{{font-weight:600}}
.banner dd{{margin:0}}.scroll{{overflow-x:auto;border:1px solid var(--line);border-radius:8px;background:var(--card)}}
table{{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums;font-size:13px}}
th,td{{padding:6px 8px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}}
th{{position:sticky;top:0;background:var(--card);font-weight:600;vertical-align:bottom;white-space:normal}}
td:nth-child(-n+3),th:nth-child(-n+3){{text-align:left}}.rec{{background:var(--rec);font-weight:600}}
.tabs{{display:flex;gap:6px;margin:8px 0}}.tabs button{{font:inherit;padding:5px 12px;border:1px solid var(--line);
border-radius:6px;background:var(--card);color:var(--fg);cursor:pointer}}.tabs button[aria-selected="true"]{{border-color:var(--ptal);
box-shadow:inset 0 -2px 0 var(--ptal)}}.barcell{{min-width:150px;width:150px}}.bar{{position:relative;display:flex;height:12px;
background:transparent;border-radius:2px}}.seg{{display:block;height:100%}}.b0{{background:var(--b0)}}.b1{{background:var(--b1)}}
.b2{{background:var(--b2)}}.ptal{{position:absolute;top:-3px;width:2px;height:18px;background:var(--ptal)}}
.legend{{display:flex;flex-wrap:wrap;gap:14px;font-size:13px;color:var(--muted);margin:6px 0}}
.legend i{{display:inline-block;width:12px;height:12px;margin-right:5px;vertical-align:-1px}}
code,pre{{font-family:ui-monospace,monospace;font-size:13px}}pre{{background:var(--card);border:1px solid var(--line);
border-radius:8px;padding:12px;overflow-x:auto}}
</style></head><body><main>
<h1>Интервалы и ожидание автобусов Астаны — сравнение методов</h1>
<p class="muted">K06, раунд 3. Исторический расчёт для исследования и диплома. Не прогноз и не данные Шымкента.</p>
<div class="banner" role="note"><dl>
<dt>Город</dt><dd>Астана. Числа этой страницы нельзя приписывать Шымкенту или другим городам.</dd>
<dt>Охват</dt><dd>Только 3 маршрута: {", ".join(meta["routes"])} (оператор CTS). Это не вся сеть Астаны.</dd>
<dt>Период</dt><dd>Исторический: {meta["first_date"]} — {meta["last_date"]}, {meta["service_dates"]} дат, {meta["trips"]} рейсов.
Состояние сети в 2026 году здесь не отражено.</dd>
<dt>Источник</dt><dd>Mansurova et al., Zenodo 15769359 (doi:10.5281/zenodo.15769359), прочитано через зеркало
Mrithula742/Bussure @ 0356bb5. Лицензия CC BY 4.0 указана только в README зеркала, на Zenodo не проверена.</dd>
<dt>Неполнота</dt><dd>Время начала рейса восстановлено авторами набора по GPS. Интервалы измерены на старте рейса,
не на каждой остановке (stop_times недоступен). Пассажиропотока нет.</dd></dl></div>

<h2>Главное</h2>
<ul>
<li><b>Разница между днями даёт мало, основная нерегулярность — внутри дня.</b> В будни вклад различий между днями
{f1(wk["b"][0])}–{f1(wk["b"][2])} мин (медиана {f1(wk["b"][1])}), вклад нерегулярности внутри дня
{f1(wk["w"][0])}–{f1(wk["w"][2])} мин (медиана {f1(wk["w"][1])}).</li>
<li><b>Объединение дней завышает CV, но почти не искажает ожидание.</b> Формула H/2·(1+CV²) на объединённой выборке
алгебраически равна Σh²/(2Σh), то есть среднему по времени из дневных ожиданий. Небольшая разница с рекомендованным
методом возникает только из-за отнесения интервалов к окну по началу, а не по времени прихода пассажира.</li>
<li><b>Медиана дневных ожиданий занижает ожидание пассажира</b> на {f1(wk["g"][0])}–{f1(wk["g"][2])} мин
(медиана {f1(wk["g"][1])}), потому что игнорирует, что плохих дней и длинных интервалов пассажир «застаёт» больше.</li>
<li>Рекомендованное ожидание выше PTAL (H/2 + 2 мин) в {wk["over"]} из {wk["n"]} комбинаций маршрут/направление/окно в будни.</li>
</ul>

<h2>Методы</h2>
<ul>
<li><b>PTAL</b>: H/2 + 2 мин, H — средний интервал. Константа надёжности, не наблюдение.</li>
<li><b>Объединение формулой</b> (как в AST-A06): все интервалы всех дат в одну выборку, H/2·(1+CV²).</li>
<li><b>Медиана дневных</b>: медиана по датам H<sub>d</sub>/2·(1+CV<sub>d</sub>²). Описывает «типичный день»,
<b>не равна ожиданию пассажира</b>.</li>
<li><b>Среднее дней</b>: каждая дата с весом 1, ожидание по времени прихода внутри окна.</li>
<li><b>Взвешенное по времени</b> (рекомендовано): ∫ожидание dt / покрытое время по всем датам — ожидание пассажира,
пришедшего в случайный момент наблюдённого обслуживания в окне.</li>
<li><b>Разложение</b>: рекомендованное − H/2 = между днями (дневной средний интервал отличается от общего) + внутри дня
(нерегулярность в пределах дня).</li>
</ul>
<p><b>Допущения формулы ожидания.</b> Пассажир приходит равномерно случайно, не зная расписания и не пользуясь табло
или приложением; садится в первый автобус (вместимость не ограничена); интервал на старте рейса переносится на остановку.
С расписанием и онлайн-табло реальное ожидание меньше, поэтому это оценка сверху, а не прогноз.</p>

<h2>Сравнение по маршрутам, направлениям и окнам</h2>
<div class="tabs" role="tablist">{tabs}</div>
<div class="legend"><span><i style="background:var(--b0)"></i>H/2 (регулярное движение)</span>
<span><i style="background:var(--b1)"></i>между днями</span><span><i style="background:var(--b2)"></i>внутри дня</span>
<span><i style="background:var(--ptal);width:2px"></i>PTAL H/2+2</span><span>шкала: 0–{f1(SCALE)} мин</span></div>
<div class="scroll"><table>
<thead><tr><th>Марш­рут</th><th>Напр.</th><th>Окно</th><th>Дат</th><th>H, мин</th><th>CV объед.</th>
<th>CV медиана дней</th><th>PTAL</th><th>Объед. формулой</th><th>Медиана дневных</th><th>Среднее дней</th>
<th>Взвеш. по времени</th><th>Между днями</th><th>Внутри дня</th><th>Разложение ожидания</th></tr></thead>
{tables}</table></div>
<p class="muted">Ожидание в минутах. Окно — полуинтервал [начало, конец) в часах дня обслуживания.
Направление — direction_id набора (1/2).</p>

<h2>Проверочный пример (двое суток, вычислен вручную)</h2>
<div class="scroll"><table><thead><tr><th>Дата</th><th>Отправления</th><th>Интервалы</th><th>H</th><th>CV</th>
<th>Ожидание</th><th>Покрыто</th></tr></thead><tbody>
<tr><td>Пн</td><td>06:00, 06:10, 06:10 (дубль), 06:10:30 (&lt;60 с), 06:20, 06:30</td><td>10, 10, 10</td><td>10</td><td>0</td><td>5</td><td>30</td></tr>
<tr><td>Вт</td><td>06:00, 06:30, 07:00</td><td>30, 30</td><td>30</td><td>0</td><td>15</td><td>60</td></tr>
</tbody></table></div>
<p>Объединение: H = 18, CV² = 96/324 = 0,296 → 9·1,296 = <b>11,67</b> = Σh²/(2Σh) = 2100/180. Взвешенное по времени:
(30·5 + 60·15)/90 = <b>11,67</b>. Среднее дней (5+15)/2 = 10, медиана дневных = 10, PTAL 11. Между днями 2,67, внутри дня 0:
вся «нерегулярность» объединённой выборки (CV 0,54) здесь создана различием дней. Тесты: <code>test_headway_calc.py</code>.</p>

<h2>Длительность рейса (включая отстой на конечной)</h2>
<p>Это время от начала до конца восстановленного рейса. Обычно оно включает отстой на конечной и посадку, потому что
76,7% следующих рейсов той же машины начинаются не позже 60 с после окончания предыдущего (K06, next-round).
<b>Не является мерой пробок и не прогнозирует скорость движения.</b> Будни.</p>
<div class="scroll"><table><thead><tr><th>Маршрут</th><th>Напр.</th><th>Окно старта</th><th>Рейсов</th>
<th>p50, мин</th><th>p90, мин</th></tr></thead><tbody>{dur}</tbody></table></div>

<h2>Очистка входа</h2>
<ul>
<li>Точные дубли (маршрут, направление, дата, старт до секунды): {c.get("exact_duplicates", 0)}, оставлено по одному.</li>
<li>Почти-дубли (&lt; 60 с после предыдущего оставленного отправления): {c.get("near_duplicates", 0)}, позднее отправление удалено.
В AST-A06 удалялся сам интервал, поэтому числа отличаются.</li>
<li>Нулевые и отрицательные интервалы после сортировки и удаления дублей невозможны.</li>
<li>Разрывы &gt; 3 ч: {c.get("service_breaks", 0)}, время внутри разрыва не считается ожиданием.</li>
<li>Полночь: времена ≥ 24:00:00 остаются в своей дате обслуживания; в этом наборе их нет (рейсы 06–22 ч).
Интервалы между датами не связываются; приход до первого и после последнего отправления дня не учитывается.</li>
<li>Неполные даты (&lt; 0,5 медианы отправлений маршрута/направления) исключены: {len(res["excluded_days"])} —
<span class="muted">{html.escape(excl)}</span>.</li>
</ul>

<h2>Поправки к прежним выводам</h2>
<ul>
<li><b>AST-A06 (F011, F018):</b> CV 0,56–1,08 — это CV объединённой выборки; как мера регулярности одного дня он
завышен (медиана дневного CV ниже). Сама оценка ожидания объединением близка к рекомендованной.
Избыток над H/2 следует подписывать как нерегулярность внутри дня плюс небольшой вклад различий между днями.</li>
<li><b>AST-A06, таблица 7.2:</b> «в салоне + трафик» → «длительность рейса, включая отстой; не пробка».</li>
<li><b>K06 next-round (K06-F009):</b> отменяется. Сочетание среднего H из объединения с медианой дневного CV
(«избыток 1,4–7,8 мин») — несогласованная смесь, которая занижает ожидание. Корректные значения — столбцы
«Взвеш. по времени» и разложение выше.</li>
</ul>

<h2>Воспроизведение (из корня репозитория)</h2>
<pre>GIT_LFS_SKIP_SMUDGE=1 git clone --filter=blob:none --sparse https://github.com/Mrithula742/Bussure ../bussure
git -C ../bussure sparse-checkout set datasets/astana
git -C ../bussure checkout 0356bb5b37ef0992ec0df3a4f09be35e3147b094
cd research/round-3-results/K06
python3 -m unittest -v test_headway_calc
python3 headway_calc.py --gtfs ../../../../bussure/datasets/astana/gtfs_data --out out
python3 make_report.py out/headways.json report.html</pre>
<p class="muted">Только стандартная библиотека Python 3. Хэши входов:
research/next-round/K06/source_snapshot/SHA256SUMS_gtfs_data.txt.</p>
</main>
<script>
document.querySelectorAll('.tabs button').forEach(b=>b.addEventListener('click',()=>{{
document.querySelectorAll('.tabs button').forEach(x=>x.setAttribute('aria-selected',x===b));
document.querySelectorAll('tbody[data-t]').forEach(t=>t.hidden=t.dataset.t!==b.dataset.t);}}));
</script></body></html>"""
open(dst, "w", encoding="utf-8").write(page)
print("wrote", dst, len(page), "bytes")
