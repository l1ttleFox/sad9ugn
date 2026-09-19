"""P01 — обязательный стресс на FINAL-планах: BASE vs MANDATORY_STRESS
+ декомпозиция на 4 изолированных фактора (prompt_wave2.md п.1,
REFRESH_WP3_AFTER_FINAL.md п.2).

Схема прогонов (решение WP2: стратегия S10, два операционных плана):
  BASE              — FINAL_BASE  + configs/base.yaml;
  MANDATORY_STRESS  — FINAL_STRESS + configs/mandatory_stress.yaml
                      (TD-01 demand-chasing пересчитан WP2 под стресс-профиль);
  MANDATORY_ON_FIXED_BASE (справочно) — FINAL_BASE + mandatory_stress.yaml:
                      цена отсутствия адаптации заказов (STRESS_PROTOCOL §84:
                      адаптация показывается явно, отдельным планом);
  F1–F4             — изолированные факторы на НЕИЗМЕННОМ FINAL_BASE
                      (декомпозиция «какие эффекты вызваны чем»).

Факторы (по configs/mandatory_stress.yaml, CASE_INPUT — не меняется):
  F1 спрос ×1.15 (2038–2040, общий и критический);
  F2 переменные цены A/B ×1.25 (2038–2039);
  F3 фактическая поставка D 0.55/0.75/1.0 (2038/2039/2040);
  F4 потолок losses/throughput ≤ 0.02 с 2038.

Проверка: 55%/75% — фактические доли, НЕ умножены на reliability
(критерий приёмки 1): actual/planned для D по годам 2038/2039/2040 ==
0.55/0.75/1.00 в прогоне MANDATORY_STRESS (FINAL_STRESS).

Выход: results/stress/P01_*.csv/json.
"""

from __future__ import annotations

import os

from wp3lib import (
    RESULTS,
    base_case,
    base_plan,
    base_scenario,
    finance_row,
    meta_block,
    mandatory_scenario,
    min_sl_crit,
    min_sl_total,
    pv_of,
    run_plan,
    shortage_of,
    stress_plan,
    total_cost_of,
    violation_signature,
    write_csv,
    write_json,
    yearly_row,
)
from engine.models import Scenario  # noqa: E402

OUT = os.path.join(RESULTS, "stress")

YEARS = range(2035, 2041)
ONE = {str(y): 1.0 for y in YEARS}


def factor_scenarios() -> dict[str, Scenario]:
    f1 = Scenario(
        scenario_id="TEAM_FACTOR_DEMAND_x115",
        status="TEAM_ASSUMPTION",
        demand_multiplier={**ONE, "2038": 1.15, "2039": 1.15, "2040": 1.15},
        critical_demand_multiplier={**ONE, "2038": 1.15, "2039": 1.15, "2040": 1.15},
    )
    f2 = Scenario(
        scenario_id="TEAM_FACTOR_PRICE_AB_x125",
        status="TEAM_ASSUMPTION",
        variable_price_multiplier={
            "Earth-Core": {"2038": 1.25, "2039": 1.25},
            "Earth-Flex": {"2038": 1.25, "2039": 1.25},
        },
    )
    f3 = Scenario(
        scenario_id="TEAM_FACTOR_ISRU_55_75",
        status="TEAM_ASSUMPTION",
        actual_delivery_share={"Lunar-ISRU": {"2038": 0.55, "2039": 0.75, "2040": 1.0}},
    )
    # F4: STRESS_LOSS_LIMIT по constraints.csv срабатывает только при
    # scenario_id=MANDATORY_STRESS — единственный фактор «потолок»
    # включается сценарием с этим id и пустыми множителями (все 1.0).
    f4 = Scenario(
        scenario_id="MANDATORY_STRESS",
        status="CASE_INPUT",
        loss_ceiling={"enabled": True, "from_year": 2038,
                      "max_losses_divided_by_throughput": 0.02},
    )
    return {
        "F1_demand_x1.15": f1,
        "F2_price_AB_x1.25": f2,
        "F3_isru_55_75": f3,
        "F4_loss_ceiling_2pct": f4,
    }


def summary_row(name: str, r) -> dict:
    loss_checks = [c for c in r.checks if c.rule_id == "STRESS_LOSS_LIMIT"]
    return {
        "scenario": name,
        "scenario_id": r.scenario_id,
        "plan_id": r.plan_id,
        "total_mln": round(total_cost_of(r), 2),
        "pv_mln": round(pv_of(r), 2),
        "shortage_t": round(shortage_of(r), 2),
        "min_sl_total": round(min_sl_total(r), 4),
        "min_sl_critical": round(min_sl_crit(r), 4),
        "violations": len(violation_signature(r)),
        "loss_ceiling_checks": len(loss_checks),
        "loss_ceiling_failed": sum(1 for c in loss_checks if not c.passed),
    }


def main() -> None:
    case = base_case()
    plan_base = base_plan()        # FINAL_BASE
    plan_stress = stress_plan()    # FINAL_STRESS

    r_base = run_plan(case, plan_base, base_scenario())
    r_stress = run_plan(case, plan_stress, mandatory_scenario())
    # справочно: mandatory на НЕадаптированном плане (цена адаптации TD-01)
    r_mand_fixed = run_plan(case, plan_base, mandatory_scenario())

    runs = {
        "BASE": r_base,
        "MANDATORY_STRESS": r_stress,
        "MANDATORY_ON_FIXED_BASE": r_mand_fixed,
    }
    for name, sc in factor_scenarios().items():
        runs[name] = run_plan(case, plan_base, sc)

    # --- годовая таблица BASE vs STRESS vs факторы ---
    yearly_rows = []
    for name, r in runs.items():
        for y in yearly_row(r):
            yearly_rows.append({"run": name, **y})
    write_csv(
        os.path.join(OUT, "P01_yearly_balance.csv"),
        ["run"] + list(yearly_row(r_base)[0].keys()),
        yearly_rows,
    )
    fin_rows = []
    for name, r in runs.items():
        for fr in finance_row(r):
            fin_rows.append({"run": name, **fr})
    write_csv(
        os.path.join(OUT, "P01_financial_breakdown.csv"),
        ["run"] + list(finance_row(r_base)[0].keys()),
        fin_rows,
    )

    # --- сводка ---
    summary = [summary_row(name, r) for name, r in runs.items()]
    write_csv(
        os.path.join(OUT, "P01_summary.csv"),
        list(summary[0].keys()),
        summary,
    )

    # --- нарушения (полный список, каждый прогон) ---
    viol_rows = []
    for name, r in runs.items():
        for v in r.violations:
            viol_rows.append(
                {
                    "run": name, "rule_id": v.rule_id, "period": v.period,
                    "actual": v.actual, "limit": v.limit, "excess": v.excess,
                    "message_ru": v.message_ru,
                }
            )
    write_csv(
        os.path.join(OUT, "P01_violations.csv"),
        ["run", "rule_id", "period", "actual", "limit", "excess", "message_ru"],
        viol_rows,
    )

    # --- КРИТЕРИЙ 1: ISRU 55/75 не умножены на reliability ---
    # Доказательство — в прогоне MANDATORY_STRESS (FINAL_STRESS):
    # actual/planned D за год == share из yaml без reliability.
    rel_checks = []
    for year, share in ((2038, 0.55), (2039, 0.75), (2040, 1.0)):
        planned = sum(
            v for (s, p), v in r_stress.deliveries.planned_by_source_period.items()
            if s == "D" and p.startswith(str(year))
        )
        actual = sum(
            v for (s, p), v in r_stress.deliveries.actual_by_source_period.items()
            if s == "D" and p.startswith(str(year))
        )
        ratio = actual / planned if planned else None
        # reliability D по supply_sources.csv: 2038:0.78; 2039:0.90; 2040:0.93
        rel = {2038: 0.78, 2039: 0.90, 2040: 0.93}[year]
        rel_checks.append(
            {
                "year": year,
                "planned_t": round(planned, 4),
                "actual_t": round(actual, 4),
                "ratio_actual_planned": round(ratio, 6) if ratio is not None else "",
                "expected_share": share,
                "share_times_reliability": round(share * rel, 6),
                "verdict": (
                    "OK: ratio == share (без reliability)"
                    if ratio is not None and abs(ratio - share) < 1e-9
                    else "ОШИБКА"
                ),
            }
        )
    write_csv(
        os.path.join(OUT, "P01_isru_no_reliability_check.csv"),
        list(rel_checks[0].keys()),
        rel_checks,
    )
    ok_all = all(c["verdict"].startswith("OK") for c in rel_checks)

    write_json(
        os.path.join(OUT, "P01_meta.json"),
        meta_block(
            "BASE+MANDATORY_STRESS+4_factors",
            f"{plan_base.plan_id}+{plan_stress.plan_id}",
            extra={
                "protocol": "P01",
                "plans": {
                    "BASE": plan_base.plan_id,
                    "MANDATORY_STRESS": plan_stress.plan_id,
                    "factors_F1_F4": plan_base.plan_id,
                    "MANDATORY_ON_FIXED_BASE": plan_base.plan_id,
                },
                "factors": {
                    "F1": "demand x1.15 (2038-2040, total+critical)",
                    "F2": "variable price A/B x1.25 (2038-2039)",
                    "F3": "actual delivery share D 0.55/0.75/1.0 (2038/2039/2040)",
                    "F4": "loss ceiling 0.02 from 2038",
                },
                "isru_no_reliability_ok": ok_all,
                "note": "промежуточные факторные сценарии — TEAM_ASSUMPTION "
                        "(исследовательская декомпозиция CASE_INPUT-стресса на "
                        "неизменном FINAL_BASE); F4 сохраняет id MANDATORY_STRESS, "
                        "т.к. STRESS_LOSS_LIMIT по constraints.csv применяется "
                        "только к этому сценарию; MANDATORY_ON_FIXED_BASE — "
                        "справочный прогон mandatory на неадаптированном плане "
                        "(цена отсутствия адаптации TD-01)",
            },
        ),
    )

    # --- консольная таблица ---
    print("P01 summary:")
    hdr = ["scenario", "plan_id", "total_mln", "pv_mln", "shortage_t",
           "min_sl_total", "min_sl_critical", "violations", "loss_ceiling_failed"]
    print(" | ".join(hdr))
    for s in summary:
        print(" | ".join(str(s[h]) for h in hdr))
    print("ISRU без reliability:", "OK" if ok_all else "ОШИБКА")
    for c in rel_checks:
        print(f"  {c['year']}: actual/planned={c['ratio_actual_planned']} "
              f"(ожидалось {c['expected_share']}; share×reliability было бы "
              f"{c['share_times_reliability']}) — {c['verdict']}")


if __name__ == "__main__":
    main()
