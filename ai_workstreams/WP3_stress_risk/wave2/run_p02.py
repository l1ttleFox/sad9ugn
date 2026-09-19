"""P02 — чувствительность FINAL-плана (один план FINAL_BASE, BASE-контроль).

Оси (протокол P02 + prompt_wave2.md п.2 + REFRESH_WP3_AFTER_FINAL.md п.3):
  1. low/high demand (data/demand.csv; критический спрос — постоянная
     внутригодовая доля, решение D3.1: множитель критического = множитель
     общего);
  2. переменная цена A/B ×0.8 / ×1.2 (испытательный ±20%, TEAM_ASSUMPTION);
  3. фактическая доля D 0.40/0.55/0.75 (2038–2039; испытательные точки,
     0.55/0.75 — CASE_INPUT только внутри mandatory);
  4. ставка PV 0.05/0.15 (пост-обработка financial_breakdown: физика от
     ставки не зависит, TA-06; ядро не меняется);
  5. lead time C 18/24 мес — в FINAL-плане канал C НЕ используется
     (стратегия S10: A/B/D, нет EARTH_NEW) → эффект нулевой, фиксируется
     честно; ось не применяется.

Tornado: Δtotal, ΔPV(r=0.10), Δshortage, Δmin SL_total, Δнарушений (новые
относительно BASE-подписи). Reverse-пороги: бинарный поиск (шаг 0.01)
первого значения оси, где появляется НОВОЕ нарушение или падает сервис.

ВАЖНО (REFRESH п.3): порог определяется относительно ЧИСТОГО, выполнимого
FINAL BASE. FINAL BASE имеет 0 hard-нарушений (проверяется явно; если бы
имел — это блокер и эскалация WP2, а не база для reverse stress).

Выход: results/stress/P02_*.csv
"""

from __future__ import annotations

import os
import sys

from wp3lib import (
    RESULTS,
    base_case,
    base_plan,
    base_scenario,
    demand_scenario,
    finance_row,
    isru_share_scenario,
    meta_block,
    min_sl_crit,
    min_sl_total,
    price_mult_scenario,
    pv_of,
    run_plan,
    shortage_of,
    total_cost_of,
    violation_signature,
    write_csv,
    write_json,
    yearly_row,
)

OUT = os.path.join(RESULTS, "stress")
YEARS = list(range(2035, 2041))

# demand.csv: base_total, low_total, high_total
LOW_MULT = {y: 0.8 for y in YEARS}  # 80/100 … 312/390 = 0.8 все годы
HIGH_MULT = {2035: 1.1, 2036: 1.1, 2037: 1.1, 2038: 1.25, 2039: 1.25, 2040: 1.25}


def metrics(r, base_sig) -> dict:
    return {
        "total_mln": round(total_cost_of(r), 2),
        "pv_mln": round(pv_of(r), 2),
        "pv_r05_mln": round(pv_of(r, rate=0.05), 2),
        "pv_r15_mln": round(pv_of(r, rate=0.15), 2),
        "shortage_t": round(shortage_of(r), 3),
        "min_sl_total": round(min_sl_total(r), 4),
        "min_sl_critical": round(min_sl_crit(r), 4),
        "new_violations": len(violation_signature(r) - base_sig),
    }


def main() -> None:
    case = base_case()
    plan = base_plan()
    r_base = run_plan(case, plan, base_scenario())
    base_sig = violation_signature(r_base)
    m_base = metrics(r_base, base_sig)

    # БЛОКЕР-ПРОВЕРКА: FINAL BASE обязан быть чистым (0 hard-нарушений).
    if base_sig:
        print(
            "БЛОКЕР: FINAL BASE имеет hard-нарушения "
            f"({sorted(base_sig)}). Reverse-пороги не имеют базы — "
            "эскалация WP2 (REFRESH_WP3_AFTER_FINAL.md п.3).",
            file=sys.stderr,
        )
        raise SystemExit(2)

    runs: dict[str, tuple[object, dict]] = {}

    # 1. low/high demand
    for label, mult in (("demand_low_x0.8", LOW_MULT), ("demand_high", HIGH_MULT)):
        r = run_plan(case, plan, demand_scenario(f"TEAM_P02_{label.upper()}", mult))
        runs[label] = (r, m_base)

    # 2. цены A/B ±20% (все годы)
    for tag, p in (("priceAB_x0.8", 0.8), ("priceAB_x1.2", 1.2)):
        sc = price_mult_scenario(
            f"TEAM_P02_{tag.upper()}", "Earth-Core", {y: p for y in YEARS}
        )
        sc.variable_price_multiplier["Earth-Flex"] = {str(y): p for y in YEARS}
        r = run_plan(case, plan, sc)
        runs[tag] = (r, m_base)

    # 3. доля D (2038–2039)
    for tag, s in (("shareD_0.40", 0.40), ("shareD_0.55", 0.55), ("shareD_0.75", 0.75)):
        r = run_plan(case, plan, isru_share_scenario(
            f"TEAM_P02_{tag.upper()}", {2038: s, 2039: s}))
        runs[tag] = (r, m_base)

    # 4. ставка — пост-обработка (отдельные прогоны не нужны)
    # 5. lead time C — не применим к FINAL (нет канала C в плане)

    # --- tornado-таблица ---
    tornado = []
    axes = {
        "demand_low_x0.8": ("спрос low", "×0.80 всех лет (demand.csv)"),
        "demand_high": ("спрос high", "×1.10 (2035–37), ×1.25 (2038–40) (demand.csv)"),
        "priceAB_x0.8": ("цена A/B", "×0.80 (испытательный −20%, TEAM_ASSUMPTION)"),
        "priceAB_x1.2": ("цена A/B", "×1.20 (испытательный +20%, TEAM_ASSUMPTION)"),
        "shareD_0.40": ("доля D 2038–39", "0.40 (испытательная)"),
        "shareD_0.55": ("доля D 2038–39", "0.55 (CASE_INPUT только в mandatory)"),
        "shareD_0.75": ("доля D 2038–39", "0.75 (CASE_INPUT только в mandatory)"),
    }
    for tag, (r, _) in runs.items():
        m = metrics(r, base_sig)
        name, src = axes[tag]
        tornado.append({
            "factor": name, "variant": tag, "source": src,
            "total_mln": m["total_mln"],
            "d_total_mln": round(m["total_mln"] - m_base["total_mln"], 2),
            "pv_mln": m["pv_mln"],
            "d_pv_mln": round(m["pv_mln"] - m_base["pv_mln"], 2),
            "d_shortage_t": round(m["shortage_t"] - m_base["shortage_t"], 3),
            "min_sl_total": m["min_sl_total"],
            "d_min_sl_total_pp": round((m["min_sl_total"] - m_base["min_sl_total"]) * 100, 3),
            "d_new_violations_vs_base": m["new_violations"],
        })
    tornado.sort(key=lambda row: -abs(row["d_pv_mln"]))
    write_csv(os.path.join(OUT, "P02_tornado.csv"), list(tornado[0].keys()), tornado)

    # ставка дисконтирования (пост-обработка BASE-прогона)
    rate_rows = [
        {"rate": r_, "pv_mln": round(pv_of(r_base, rate=r_), 2),
         "note": "физика не зависит от ставки; PV пересчитан из total_mln "
                 "года (TA-06/07: конец года, t0=2035)"}
        for r_ in (0.05, 0.10, 0.15)
    ]
    write_csv(os.path.join(OUT, "P02_discount_rate.csv"),
              list(rate_rows[0].keys()), rate_rows)

    # lead time C — не применим к FINAL-плану (нет канала C)
    write_csv(os.path.join(OUT, "P02_lead_time_C.csv"),
              ["factor", "variants", "effect", "reason"],
              [{"factor": "lead time C", "variants": "18/24 мес",
                "effect": "0 (нет влияния)",
                "reason": "FINAL-план (стратегия S10) не использует канал C "
                          "(нет инвестиции EARTH_NEW, заказов и резервов C) — "
                          "чувствительность не применима к данному плану; "
                          "ось 18/24 мес не рассчитывается"}])

    # --- reverse-пороги (бинарный поиск, шаг 0.01) ---
    thresholds = []
    base_min_sl_raw = min_sl_total(r_base)

    def first_break(make_sc, lo, hi, tol=0.01):
        """Первое значение x в [lo, hi] (рост), где появляется новое нарушение
        или min SL_total падает ниже BASE-значения; None если нет."""
        def broken(x):
            r = run_plan(case, plan, make_sc(x))
            sig = violation_signature(r)
            new = sig - base_sig
            sl_worse = min_sl_total(r) < base_min_sl_raw - 1e-9
            return (bool(new) or sl_worse), r
        is_broken, _ = broken(hi)
        if not is_broken:
            return None, None
        a, b = lo, hi
        while b - a > tol:
            mid = (a + b) / 2
            if broken(mid)[0]:
                b = mid
            else:
                a = mid
        return b, broken(b)[1]

    # ось: множитель спроса (все годы, общий+критический)
    x, r_x = first_break(
        lambda m: demand_scenario("TEAM_P02_THRESH_DEMAND", {y: m for y in YEARS}),
        1.0, 3.0)
    if x is not None:
        nv = sorted(violation_signature(r_x) - base_sig)
        thresholds.append({
            "axis": "множитель спроса (все годы)", "threshold": round(x, 2),
            "first_broken": "; ".join(f"{rid}@{per}" for rid, per in nv[:6]),
            "min_sl_total": round(min_sl_total(r_x), 4),
        })

    # ось: цена A (все годы) — ожидается отсутствие физической границы
    x_p, r_p = first_break(
        lambda m: price_mult_scenario("TEAM_P02_THRESH_PRICE_A", "Earth-Core",
                                      {y: m for y in YEARS}),
        1.0, 3.0)
    thresholds.append({
        "axis": "множитель цены A (все годы)",
        "threshold": round(x_p, 2) if x_p is not None else "нет границы до ×3.00",
        "first_broken": ("; ".join(f"{rid}@{per}" for rid, per in
                                   sorted(violation_signature(r_p) - base_sig)[:6])
                         if x_p is not None else
                         "физические лимиты от цены не зависят — границы нет "
                         "(P02 §Результат); OPEX-бюджет кейсом не задан, цена "
                         "влияет только на PV"),
        "min_sl_total": round(min_sl_total(r_p), 4) if r_p is not None else "",
    })

    # ось: доля D 2038–2039 (снижение) — ищем сверху вниз
    def first_break_down(make_sc, hi=1.0, lo=0.0, tol=0.01):
        def broken(x):
            r = run_plan(case, plan, make_sc(x))
            sig = violation_signature(r)
            return (bool(sig - base_sig)
                    or min_sl_total(r) < base_min_sl_raw - 1e-9), r
        is_broken, _ = broken(lo)
        if not is_broken:
            return None, None
        a, b = lo, hi
        while b - a > tol:
            mid = (a + b) / 2
            if broken(mid)[0]:
                a = mid
            else:
                b = mid
        return a, broken(a)[1]

    x_s, r_s = first_break_down(
        lambda s: isru_share_scenario("TEAM_P02_THRESH_SHARED",
                                      {2038: s, 2039: s}))
    if x_s is not None:
        nv = sorted(violation_signature(r_s) - base_sig)
        thresholds.append({
            "axis": "фактическая доля D 2038–2039 (снижение)",
            "threshold": round(x_s, 2),
            "first_broken": "; ".join(f"{rid}@{per}" for rid, per in nv[:6]),
            "min_sl_total": round(min_sl_total(r_s), 4),
        })

    write_csv(os.path.join(OUT, "P02_reverse_thresholds.csv"),
              ["axis", "threshold", "first_broken", "min_sl_total"], thresholds)

    # --- годовые таблицы всех осей ---
    yearly_rows = [{"run": "BASE", **y} for y in yearly_row(r_base)]
    for tag, (r, _) in runs.items():
        for y in yearly_row(r):
            yearly_rows.append({"run": tag, **y})
    write_csv(os.path.join(OUT, "P02_yearly_balance.csv"),
              list(yearly_rows[0].keys()), yearly_rows)

    fin_rows = []
    all_runs = [("BASE", r_base)] + [(t, rr) for t, (rr, _) in runs.items()]
    for tag, r in all_runs:
        for fr in finance_row(r):
            fin_rows.append({"run": tag, **fr})
    write_csv(os.path.join(OUT, "P02_financial_breakdown.csv"),
              list(fin_rows[0].keys()), fin_rows)

    write_json(os.path.join(OUT, "P02_meta.json"), meta_block(
        "P02_sensitivity", plan.plan_id,
        extra={"protocol": "P02", "base_signature_size": len(base_sig),
               "base_clean": len(base_sig) == 0,
               "thresholds": thresholds,
               "note": "порог = первое значение оси, где появляется НОВОЕ "
                       "нарушение (rule_id, period) сверх BASE-подписи или "
                       "min SL_total хуже BASE; FINAL BASE чист (0 hard-нарушений, "
                       "SL=1.0/1.0) —reverse-пороги измеряют запас прочности "
                       "выполнимого финального плана (D8 устранил ложные "
                       "CAPACITY_EXCEEDED старой конвенции лимита отбора)"}))

    print("P02 tornado:")
    for row in tornado:
        print(f"  {row['variant']}: ΔPV={row['d_pv_mln']:+.1f} млн, "
              f"Δshort={row['d_shortage_t']:+.1f} т, "
              f"ΔminSL={row['d_min_sl_total_pp']:+.2f} п.п., "
              f"новых нарушений={row['d_new_violations_vs_base']}")
    print("Пороги:")
    for t in thresholds:
        print(f"  {t['axis']}: {t['threshold']} → {t['first_broken']}")
    print("Ставки: " + ", ".join(f"r={x['rate']}: PV={x['pv_mln']}" for x in rate_rows))


if __name__ == "__main__":
    main()
