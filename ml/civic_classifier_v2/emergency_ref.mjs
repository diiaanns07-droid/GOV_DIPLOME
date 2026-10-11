// Срочные случаи по тексту жалобы — эталон на JS для R09 (тот же алгоритм, что ml/civic_classifier_v2/emergency.py).
// Правила — emergency_rules.json. Модуль без зависимостей: можно скопировать в web/civic/feedback/.
//
//   const rules = compileRules(await (await fetch('emergency_rules.json')).json());
//   detect('В подъезде пахнет газом', rules)  // -> [{kind: 'gas', category: 'smell_air', subtopic: 'gas', rule: 'gas_ru', match: 'газом'}]
//
// Телефон: categories_v2.json -> категория -> subtopics[id === subtopic].emergency_phone.
// Нет \b (в JS он только для латиницы) и нет просмотра назад (нет в Safari до 16.4).

function expand(src, defs) {
  let out = src;
  for (const [key, value] of Object.entries(defs)) out = out.split('{' + key + '}').join(value);
  return out;
}

export function normalize(text) {
  return String(text == null ? '' : text).toLowerCase().replace(/ё/g, 'е').replace(/\s+/g, ' ').trim();
}

export function compileRules(json) {
  const defs = json.defs;
  return {
    version: json.version,
    kinds: json.kinds,
    except: json.except.map(e => new RegExp(expand(e.re, defs), 'g')),
    rules: json.rules.map(r => ({
      id: r.id,
      kind: r.kind,
      re: new RegExp(expand(r.re, defs)),
      veto: r.veto ? new RegExp(expand(r.veto, defs)) : null,
    })),
  };
}

export function detect(text, rules) {
  let t = normalize(text);
  for (const ex of rules.except) t = t.replace(ex, ' ');
  const found = {};
  for (const r of rules.rules) {
    if (found[r.kind]) continue;
    const m = r.re.exec(t);
    if (m && !(r.veto && r.veto.test(t))) found[r.kind] = { rule: r.id, match: m[0].trim() };
  }
  const out = [];
  for (const [kind, ks] of Object.entries(rules.kinds)) {
    if (found[kind]) out.push({ kind, category: ks.category, subtopic: ks.subtopic, ...found[kind] });
  }
  return out;
}
