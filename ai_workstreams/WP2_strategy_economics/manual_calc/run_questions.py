# -*- coding: utf-8 -*-
"""
WP2 manual_calc — числовые ответы Q1–Q8 (prompt_wave1.md «Ключевые вопросы»).
Запуск: python run_questions.py (из папки manual_calc). Детерминированно.
"""
from __future__ import annotations

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from mc_data import load_case, make_base, make_stress, YEARS, DISCOUNT_T0
from mc_model import run_plan, reserve_required, EPS
from mc_strategies import build_strategies, make_branch

case = load_case()
base, stress = make_base(), make_stress()
plans = {p.plan_id: p for p in build_strategies()}


def run(sid: str, scn):
    plan = plans[sid]
    p = make_branch(plan, scn.scenario_id) if plan.adaptive else plan
    return run_plan(case, scn, p)


def pv(r):
    return r.total_pv


def fmt_mln(x):
    return f"{x:,.1f}".replace(",", " ")


print("=" * 78)
print("Q1. Earth-New (360 млн): окупается ли; ранний vs поздний exercise vs option-hold")
print("=" * 78)
r07b, r07s = run("S07", base), run("S07", stress)
r14b, r14s = run("S14", base), run("S14", stress)
r15b, r15s = run("S15", base), run("S15", stress)
r16b, r16s = run("S16", base), run("S16", stress)
r10b, r10s = run("S10", base), run("S10", stress)
print(f"S07 (New early, без D):  PV BASE={fmt_mln(pv(r07b))}, STRESS={fmt_mln(pv(r07s))}, "
      f"дефицит B/S={r07b.total_shortage:.1f}/{r07s.total_shortage:.1f} т, наруш. B/S={len(r07b.violations)}/{len(r07s.violations)}")
print(f"S14 (Full early):        PV BASE={fmt_mln(pv(r14b))}, STRESS={fmt_mln(pv(r14s))}, "
      f"дефицит B/S={r14b.total_shortage:.1f}/{r14s.total_shortage:.1f} т, наруш. B/S={len(r14b.violations)}/{len(r14s.violations)}")
print(f"S15 (Full late):         PV BASE={fmt_mln(pv(r15b))}, STRESS={fmt_mln(pv(r15s))}, "
      f"дефицит B/S={r15b.total_shortage:.1f}/{r15s.total_shortage:.1f} т, наруш. B/S={len(r15b.violations)}/{len(r15s.violations)}")
print(f"S16 (Option-hold):       PV BASE={fmt_mln(pv(r16b))}, STRESS={fmt_mln(pv(r16s))}, "
      f"дефицит B/S={r16b.total_shortage:.1f}/{r16s.total_shortage:.1f} т, наруш. B/S={len(r16b.violations)}/{len(r16s.violations)}")
print(f"S10 (без C, ISRU):       PV BASE={fmt_mln(pv(r10b))}, STRESS={fmt_mln(pv(r10s))}")
print()
d14_10_b = pv(r14b) - pv(r10b)
d14_10_s = pv(r14s) - pv(r10s)
print(f"Цена полного C-пакета (S14−S10): BASE +{fmt_mln(d14_10_b)} млн PV, STRESS +{fmt_mln(d14_10_s)} млн PV")
print(f"S16 против S14: BASE {fmt_mln(pv(r16b) - pv(r14b))} млн, STRESS {fmt_mln(pv(r16s) - pv(r14s))} млн")
print(f"Стоимость гибкости S16: BASE-ветвь {fmt_mln(pv(r16b) - pv(r14b))} млн против S14 (экономия — не платим 270");
print(f"  и не резервируем C 2037–2040); STRESS-ветвь {fmt_mln(pv(r16s) - pv(r14s))} млн против S14 (exercise 2038-01 →")
print(f"  C только с 2040-01, 2039 закрыт A+B+D+запас; резерв C только 2040).")
print(f"  Против рабочей S10: BASE +{fmt_mln(pv(r16b) - pv(r10b))} (=PV опционной премии 90), STRESS +{fmt_mln(pv(r16s) - pv(r10s))}")
print(f"  (exercise+резерв C+TOP 2040 дороже, чем снятие запаса у S10). Ценность опциона = право НЕ платить")
print(f"  270 в BASE (PV 270/1.1³≈203 при решении в 2038); опцион выгоден при P(стресс-ISRU-недобор)×203 > 90,")
print(f"  т.е. при P > 44%. НО: в BASE S16 дороже S10 ровно на 90 — опцион не защищает от главного риска")
print(f"  (провал 2040 при спросе > запаса+420), поэтому его ценность — только страховка от границы 2041.")
print(f"Ранний vs поздний exercise (S14 vs S15): BASE {fmt_mln(pv(r15b) - pv(r14b))} млн (поздний дешевле:")
print(f"  270 млн в 2037 вместо 2035 + меньше лет резерва C), STRESS {fmt_mln(pv(r15s) - pv(r14s))} млн (тоже дешевле).")
print(f"Вывод: Earth-New НЕ окупается в BASE (A+B+D=420≥390; C замещает B по 8.9, но C=7.1+TOP0.5 —")
print(f"  маржа ~1.8 млн/т × ~110 т/год = ~200 млн/год только с 2037; CAPEX 360 + резерв 0.3×130×6лет=234 → PV-убыток).")
print(f"  В STRESS C оправдан как физическая мощность: A+B+D=420 < 448.5 (2040), без C/E — провал 28.5 т.")

print()
print("=" * 78)
print("Q2. ZBO: без ZBO потолок потерь ≤2% в стрессе нарушается с 2038?")
print("=" * 78)
r11b, r11s = run("S11", base), run("S11", stress)
loss_ceil = [c for c in r11s.checks if c.rule_id == "STRESS_LOSS_LIMIT"]
for c in loss_ceil:
    print(f"  S11 STRESS {c.period}: losses/throughput = {c.actual:.4f} (лимит {c.limit:.2f}) → "
          f"{'нарушение, excess=' + format(c.excess, '.4f') if not c.passed else 'OK'}")
r10_loss = [c for c in r10s.checks if c.rule_id == "STRESS_LOSS_LIMIT"]
print(f"  S10 (с ZBO) STRESS: " + ", ".join(f"{c.period}: {c.actual:.4f} {'OK' if c.passed else 'НАРУШЕНИЕ'}" for c in r10_loss))
print(f"  Цена ZBO (S10−S11, PV BASE): {fmt_mln(pv(r10b) - pv(r11b))} млн; нарушение S11 в BASE: "
      f"{[f'{v.rule_id}@{v.period}' for v in r11b.violations]}")
print("  Вывод: БЕЗ ZBO потери 4.5% > 2% во ВСЕ годы 2038–2040 стресса → ZBO обязателен (численно).")

print()
print("=" * 78)
print("Q3. Профиль резервирования A: TOP-сжигание S17 против S18/S19 в 2035–2036")
print("=" * 78)
for sid in ("S17", "S18", "S19"):
    rb = run(sid, base)
    t35, t36 = rb.years[2035].top_extra, rb.years[2036].top_extra
    tot = sum(rb.years[y].top_extra for y in YEARS)
    print(f"  {sid}: TOP-переплата 2035={fmt_mln(t35)}, 2036={fmt_mln(t36)}, "
          f"2035–2036={fmt_mln(t35 + t36)}, всего 2035–2040={fmt_mln(tot)} млн; PV total={fmt_mln(pv(rb))}")
rb17, rb18, rb19 = run("S17", base), run("S18", base), run("S19", base)
print(f"  Цена агрессивного A (2035–2036): S17−S18 = "
      f"{fmt_mln((rb17.years[2035].top_extra + rb17.years[2036].top_extra) - (rb18.years[2035].top_extra + rb18.years[2036].top_extra))} млн TOP-переплаты;")
print(f"  полные расходы 2035–2036: S17={fmt_mln(rb17.years[2035].total + rb17.years[2036].total)}, "
      f"S18={fmt_mln(rb18.years[2035].total + rb18.years[2036].total)}, "
      f"S19={fmt_mln(rb19.years[2035].total + rb19.years[2036].total)} млн")
print(f"  Разница PV(S17−S19) BASE = {fmt_mln(pv(rb17) - pv(rb19))} млн")

print()
print("=" * 78)
print("Q4. Порог выгодности ISRU: D=3.0 против B=8.9 / E=13.8 млн/т")
print("=" * 78)
print("  Переменная экономия на 1 т замещения B→D: 8.9−3.0=5.9 млн/т; E→D: 13.8−3.0=10.8 млн/т.")
print("  Издержки D: CAPEX 1250 млн (2036–2037) + fixed OPEX 70 млн/год 2038–2040 = 1250+210=1460 млн (номинал),")
print(f"  PV (r=10%, платёж 2036-06→2036, OPEX 2038–40): 1250/1.1 + 70×(1/1.1³+1/1.1⁴+1/1.1⁵) = "
      f"{1250 / 1.1 + 70 * (1 / 1.1 ** 3 + 1 / 1.1 ** 4 + 1 / 1.1 ** 5):.1f} млн")
pv_isru = 1250 / 1.1 + 70 * (1 / 1.1 ** 3 + 1 / 1.1 ** 4 + 1 / 1.1 ** 5)
breakeven_t = pv_isru / 5.9
print(f"  Порог окупаемости против B: PV-издержки {pv_isru:.0f} млн / 5.9 млн/т = {breakeven_t:.0f} т суммарного")
print(f"    замещения за 2038–2040, т.е. ~{breakeven_t / 3:.0f} т/год в среднем (при емкости D=120 т/год окупается")
print(f"    при отборе ≥ {breakeven_t / 3:.0f} т/год; фактический отбор D 2038–2040 (S10 BASE):", end=" ")
d_off = {y: sum(mr.arrivals.get("D", 0.0) for mr in r10b.months if mr.year == y) for y in (2038, 2039, 2040)}
print(", ".join(f"{y}={v:.1f} т" for y, v in d_off.items()))
tot_d = sum(d_off.values())
print(f"    итого {tot_d:.1f} т → экономия 5.9×{tot_d:.1f}={5.9 * tot_d:.0f} млн против PV {pv_isru:.0f} млн → "
      f"{'ОКУПАЕТСЯ' if 5.9 * tot_d > pv_isru else 'НЕ окупается'}")
print(f"  Чувствительность к стресс-долям: 2038 факт 0.55×{d_off[2038]:.1f}={0.55 * d_off[2038]:.1f} т, "
      f"2039 0.75×{d_off[2039]:.1f}={0.75 * d_off[2039]:.1f} т → недобор "
      f"{(0.45 * d_off[2038] + 0.25 * d_off[2039]):.1f} т замещается B по 8.9×1.25=11.125 (2038–39):")
extra_cost = 0.45 * d_off[2038] * (8.9 * 1.25 - 3.0) + 0.25 * d_off[2039] * (8.9 * 1.25 - 3.0)
print(f"    дополнительная стоимость стресса для D-стратегии ≈ {extra_cost:.0f} млн (номинал)")

print()
print("=" * 78)
print("Q5. Стоимость робастности: PV(S20/S21) − PV(рабочей S14) против выигрыша в shortage")
print("=" * 78)
r20b, r20s = run("S20", base), run("S20", stress)
r21b, r21s = run("S21", base), run("S21", stress)
r14b2, r14s2 = run("S14", base), run("S14", stress)
print(f"  S20 Robust: PV BASE={fmt_mln(pv(r20b))} (+{fmt_mln(pv(r20b) - pv(r14b2))} к S14), "
      f"STRESS={fmt_mln(pv(r20s))} (+{fmt_mln(pv(r20s) - pv(r14s2))}); shortage стресс: {r20s.total_shortage:.1f} т (у S14: {r14s2.total_shortage:.1f} т)")
print(f"  S21 Deep-60дн: PV BASE={fmt_mln(pv(r21b))} (+{fmt_mln(pv(r21b) - pv(r14b2))}), "
      f"STRESS={fmt_mln(pv(r21s))} (+{fmt_mln(pv(r21s) - pv(r14s2))}); shortage стресс: {r21s.total_shortage:.1f} т")
print("  Вывод: S14/S20/S21 все дают 0 дефицита в стрессе → робастность S20/S21 не даёт выигрыша")
print("  в shortage против S14, но стоит +PV; S21 (+60-дн. запас, кандидат TA-10) — страховка от")
print("  внутригодовых шоков ценой +PV BASE.")

print()
print("=" * 78)
print("Q6. Мощность в стрессе 2040 (448.5 т): какие комбинации проходят физически")
print("=" * 78)
combos = [
    ("A+B", 190 + 110, "S02"),
    ("A+B+E", 190 + 110 + 80, "S03"),
    ("A+B+C", 190 + 110 + 130, "S07"),
    ("A+B+D", 190 + 110 + 120, "S10"),
    ("A+B+C+D", 190 + 110 + 130 + 120, "S14"),
    ("A+B+C+D+E", 190 + 110 + 130 + 120 + 80, "S20"),
    ("B+C+D", 110 + 130 + 120, "S09-вариант"),
]
for name, cap, sid in combos:
    ok2040 = cap >= 448.5
    ok2039 = cap >= 368.0
    # потери: без ZBO 4.5% → эффективная мощность cap×0.955; с ZBO ×0.988
    eff_base_loss = cap * (1 - 0.045)
    eff_zbo = cap * (1 - 0.012)
    print(f"  {name:12s} ({sid:10s}): cap={cap:5.1f} т; 2040 стресс 448.5 → {'ПРОХОДИТ' if ok2040 else 'ПРОВАЛ'}"
          f" (без потерь); с потерями 4.5%: {eff_base_loss:.1f} {'≥' if eff_base_loss >= 448.5 else '<'} 448.5; "
          f"с ZBO 1.2%: {eff_zbo:.1f} {'≥' if eff_zbo >= 448.5 else '<'} 448.5")
print(f"  Стресс-2039: 368 т — A+B=300 не проходит; A+B+C=430 проходит (с ZBO 424.8), A+B+D=420 проходит")
print(f"  Ключевой вывод: БЕЗ D стресс-2040 не проходит НИ ОДНА комбинация без E, а A+B+E=380<448.5 —")
print(f"  тоже провал; только A+B+C+D(+E) ≥ 448.5. Фактический провал S01–S09 в стрессе (дефицит, т):")
for sid in [f"S0{i}" for i in range(1, 10)]:
    rs = run(sid, stress)
    sh3940 = rs.years[2039].shortage + rs.years[2040].shortage
    print(f"    {sid}: shortage 2039–2040 = {sh3940:.1f} т; min SL_total = {rs.min_sl_total:.4f}; всего shortage = {rs.total_shortage:.1f} т")

print()
print("=" * 78)
print("Q7. Контрактный Emergency-резерв (S22) против физического (S21)")
print("=" * 78)
r22b, r22s = run("S22", base), run("S22", stress)
res22 = [c for c in r22b.checks if c.rule_id == "RESERVE_45D"]
print(f"  S22 BASE: PV={fmt_mln(pv(r22b))}; проверки RESERVE_45D (контрактный режим):")
for c in res22:
    print(f"    {c.period}: {'OK' if c.passed else 'НАРУШЕНИЕ'} — {c.message_ru}")
print(f"  S21 BASE (физический 60 дн.): PV={fmt_mln(pv(r21b))}, RESERVE_45D все "
      f"{'OK' if all(c.passed for c in r21b.checks if c.rule_id == 'RESERVE_45D') else 'ЕСТЬ НАРУШЕНИЯ'}")
print(f"  Разница PV (S22−S21): {fmt_mln(pv(r22b) - pv(r21b))} млн")
print("  Вывод: контрактный резерв через E (80 т/год = 9.2 т за 42 дня) НЕ покрывает спрос за период")
print("  ожидания (2035: 11.5 т … 2040: 44.9 т в BASE; 51.6 т в стрессе) — физический запас доказуемее.")

print()
print("=" * 78)
print("Q8. CAPEX headroom < 50 млн")
print("=" * 78)
for sid in sorted(plans):
    rb = run(sid, base)
    hr = 1800 - rb.capex_2037
    if 0 <= hr < 50 or rb.capex_2037 > 1800:
        print(f"  {sid}: CAPEX до 2037-12 = {fmt_mln(rb.capex_2037)} млн, headroom = {fmt_mln(hr)} млн"
              + (" — ПРЕВЫШЕНИЕ ЛИМИТА" if hr < 0 else " — ОПАСНО МАЛ (<50)"))
print("  Риск (реестр WP3): перерасход ISRU >10 млн при headroom 10 млн (S14/S17/S18/S20–S24) ломает")
print("  CAPEX_2037 (hard). S16/S25 (exercise отложен до 2038) держат headroom 280 млн до решения G4.")

print()
print("Готово — все ответы Q1–Q8 числовые.")
