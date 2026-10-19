# R11 · отчёт к заморозке FINAL-2: ключи словаря без использования (11 октября)

Сделан `tests/civic/R11/tools/unused_keys.py` по головам веток R01 (FINAL-2 28e23e3), R04, R05, R06, R07, R08, R09, R12,
R13 + ui-kit R11. **Ничего не удалено** (правило волны 2: до заморозки R11 ключи не удаляет). Решение на заморозке:

- **Оставить** — экраны ещё не сделаны или закрыты флагом: `ask.*` (R13 «Әкімге сұрақ»), `idea.*` (R06 «Идеялар»),
  `build3d.idea.*` (R05 — эскиз идеи, часть подсказок), `forecast.*` (R13 прототип), `works.*` (лента работ раунда 13
  за `?tools=all`, кабинет R12), `heat.empty_*`, `common.*`, `target.kind.*` (запасные подписи целей), `nearby.subscribe_yard`.
- **Кандидаты на удаление** — роль перешла на другой ключ: `mine.passport.*`, `mine.verify.*`, `mine.state.*`,
  `mine.update*`, `mine.changes.summary` (R09 → `passport.*`, `verify.*`, `status.*`); `staff.fixed.*`, `staff.passport.*`,
  `staff.notified`, `staff.update*` (R09 → `fix.*`, `passport.field.*`, `broadcast.*`); `qr.card.*` (R12 → `report.*`,
  `qr.object_no`); `shell.nav.*`, `shell.layers.title|nearby|ideas` (R01 → `common.nav.*`, `shell.layers.label`);
  `moderation.split*` (R04 → `merge.*`); `complaint.emergency.service.*`, `complaint.emergency.still` (R09 → `emergency.service.*`).
- Перед удалением — повторить отчёт на последних SHA и `missing_keys.py` по сборке (0), затем `i18n_tools check`.

---

# Ключи словаря без использования — 204 из 1258

Ветки: `origin/claude/sharp-dijkstra-0t87gl`, `origin/claude/r14-R05`, `origin/claude/upbeat-knuth-i0rqaa`, `origin/claude/r14-R08`, `origin/claude/modest-shannon-0ki93p`, `origin/claude/tender-brahmagupta-ef5ztl`, `origin/claude/r14-R04`, `origin/claude/round-14-r06`, `origin/claude/r14-R13`, `origin/claude/r14-R12` + ui-kit R11 (HEAD).
Динамические префиксы (ключ дописывается в коде): `build3d.err.`, `build3d.near.`, `cat.`, `common.lang.`, `common.nav.`, `common.role.`, `complaint.example.`, `dates.month_short.`, `district.`, `emergency.service.`, `heat.kind.`, `heat.level.`, `heat.level_word.`, `heat.status.`, `inbox.tab.`, `map.card.precision.`, `mine.passport.next_default.`, `mine.update.`, `nearby.tab.`, `nearby.utility.`, `nearby.why.`, `object.kind.`, `proposal.kind.`, `proposal.status.`, `service.`, `staff.pub.`, `stage.`, `status.`, `subtopic.`, `target.type.`, `works.kind.`, `works.status.`

Перед удалением — проверить глазами: ключ может собираться из частей иначе, чем видит этот поиск.

- **ask** (21): `ask.answer`, `ask.district`, `ask.moderation`, `ask.new`, `ask.privacy`, `ask.rule`, `ask.send`, `ask.staff.answer`, `ask.staff.answered`, `ask.staff.publish`, `ask.staff.queue`, `ask.staff.reject`, `ask.staff.top`, `ask.support`, `ask.supported`, `ask.tab.answered`, `ask.tab.new`, `ask.tab.top`, `ask.text`, `ask.title`, `ask.votes`
- **build3d** (3): `build3d.idea.done`, `build3d.idea.pick_note`, `build3d.idea.pick_title`
- **common** (6): `common.action.next`, `common.action.reset`, `common.appeals`, `common.state.offline`, `common.state.place_error`, `common.tagline`
- **complaint** (8): `complaint.draft.restored`, `complaint.emergency.service.104`, `complaint.emergency.service.112`, `complaint.photo.hint`, `complaint.queue.text`, `complaint.step2.geo_denied`, `complaint.step3.subtopic_label`, `complaint.step4.metoo_caption`
- **forecast** (8): `forecast.check`, `forecast.empty`, `forecast.level.high`, `forecast.level.low`, `forecast.level.medium`, `forecast.prototype`, `forecast.risk`, `forecast.title`
- **heat** (3): `heat.empty_hint`, `heat.empty_title`, `heat.filter.title`
- **idea** (25): `idea.can_improve`, `idea.check.access`, `idea.check.answer.no`, `idea.check.answer.unknown`, `idea.check.answer.yes`, `idea.check.land`, `idea.check.maintenance`, `idea.check.networks`, `idea.check.title`, `idea.description`, `idea.make_project`, `idea.moderation`, `idea.name`, `idea.new`, `idea.reason`, `idea.reject`, `idea.status.project`, `idea.status.rejected`, `idea.status.voting`, `idea.support`, `idea.supported`, `idea.tab.projects`, `idea.tab.review`, `idea.title`, `idea.view3d`
- **mine** (27): `mine.changes.none`, `mine.changes.summary`, `mine.details`, `mine.overdue`, `mine.passport.answered`, `mine.passport.assignee`, `mine.passport.delay`, `mine.passport.fix_eta`, `mine.passport.fix_unknown`, `mine.passport.next_update`, `mine.passport.response`, `mine.passport.temp`, `mine.photos.after`, `mine.state.reopened`, `mine.state.reported`, `mine.state.verified`, `mine.transferred`, `mine.updates.title`, `mine.verify.cant`, `mine.verify.no`, `mine.verify.question`, `mine.verify.reported`, `mine.verify.thanks_cant`, `mine.verify.thanks_no`, `mine.verify.thanks_yes`, `mine.verify.what`, `mine.verify.yes`
- **moderation** (2): `moderation.split`, `moderation.split_done`
- **nearby** (1): `nearby.subscribe_yard`
- **proposal** (1): `proposal.segment_hint`
- **qr** (35): `qr.card.approximate`, `qr.card.by_day`, `qr.card.demo`, `qr.card.demo_note`, `qr.card.eyebrow_qr`, `qr.card.for_days`, `qr.card.loading`, `qr.card.metoo`, `qr.card.metoo_done`, `qr.card.metoo_thanks`, `qr.card.more`, `qr.card.none`, `qr.card.number`, `qr.card.open_map`, `qr.card.report_here`, `qr.card.report_other`, `qr.card.topics`, `qr.error.bad_link`, `qr.error.metoo`, `qr.error.network`, `qr.error.not_found`, `qr.error.open_map`, `qr.error.server`, `qr.kind.bus_stop`, `qr.kind.cell`, `qr.kind.crossing`, `qr.kind.intersection`, `qr.kind.object`, `qr.kind.park`, `qr.kind.pitch`, `qr.kind.playground`, `qr.kind.segment`, `qr.kind.traffic_signal`, `qr.kind.waste`, `qr.kind.yard`
- **shell** (7): `shell.layers.ideas`, `shell.layers.nearby`, `shell.layers.title`, `shell.nav.ideas`, `shell.nav.more`, `shell.nav.nearby`, `shell.nav.projects`
- **staff** (15): `staff.fixed.photo`, `staff.fixed.submit`, `staff.fixed.title`, `staff.notified`, `staff.passport.delay_reason`, `staff.passport.fix_eta`, `staff.passport.next_step`, `staff.passport.next_update`, `staff.passport.save`, `staff.passport.temp_measure`, `staff.passport.title`, `staff.row.unpublished`, `staff.update.send`, `staff.update.title`, `staff.update_overdue`
- **target** (10): `target.fixed_on`, `target.kind.crossing`, `target.kind.intersection`, `target.kind.park`, `target.kind.pitch`, `target.kind.playground`, `target.kind.square`, `target.kind.stop_noname`, `target.kind.traffic_signal`, `target.reject`
- **works** (32): `works.count`, `works.count_shown`, `works.coverage.none_real`, `works.evidence.derived`, `works.evidence.hypothesis`, `works.evidence.observed`, `works.filters`, `works.from`, `works.hide_past`, `works.legend.accuracy`, `works.legend.approx`, `works.legend.cancelled`, `works.legend.cancelled_line`, `works.legend.color_kind`, `works.legend.completed`, `works.legend.completed_line`, `works.legend.demo`, `works.legend.exact`, `works.legend.fill_status`, `works.legend.in_progress`, `works.legend.in_progress_line`, `works.legend.lines_status`, `works.legend.no_coords`, `works.legend.planned`, `works.legend.planned_line`, `works.legend.title`, `works.legend.unknown`, `works.legend.unknown_line`, `works.no_coords_note`, `works.only_visible`, `works.period`, `works.search`
