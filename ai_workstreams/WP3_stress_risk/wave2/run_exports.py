"""Выгрузки ключевых прогонов через ЯДРОВОЙ export_results (критерий
приёмки 5: «все выгрузки совпадают с числами ядра» — используется тот же
экспортёр, что и UI/WP4). FINAL: BASE — FINAL_BASE, MANDATORY_STRESS —
FINAL_STRESS; TEAM-риски — на FINAL_BASE (R01 COMBINED — на FINAL_STRESS);
меры MIT_R* — адаптивные планы results/plans_adaptive/FINAL_MIT_R*.json.

Каталоги: results/stress/exports/<SCENARIO>/ — yearly_balance.csv,
financial_breakdown.csv, constraint_checks.csv, source_schedule.csv,
inventory_trace.csv, risk_register.csv, meta.json.
"""

from __future__ import annotations

import os

from wp3lib import (
    RESULTS,
    base_case,
    base_plan,
    base_scenario,
    mandatory_scenario,
    team_scenario,
    run_team,
    stress_plan,
)
from engine import export_results, load_saved_plan, run_plan  # noqa: E402
from engine.models import Scenario  # noqa: E402

OUT = os.path.join(RESULTS, "stress", "exports")

# адаптивные планы-меры: (риск, сценарий, план контроля)
MIT_SCENARIOS = {
    "R01": "TEAM_ISRU_UNDERDELIVERY_COMBINED",
    "R02": "TEAM_ISRU_DELAY",
    "R04": "TEAM_MMOD",
    "R08": "TEAM_CHANNEL_A_CAPACITY",
}


def main() -> None:
    case = base_case()
    plan = base_plan()        # FINAL_BASE
    plan_s = stress_plan()    # FINAL_STRESS

    runs = [
        ("BASE", run_plan(case, plan, base_scenario())),
        ("MANDATORY_STRESS", run_plan(case, plan_s, mandatory_scenario())),
    ]
    for name in ("TEAM_ISRU_UNDERDELIVERY_COMBINED", "TEAM_ISRU_DELAY",
                 "TEAM_ZBO_FAILURE", "TEAM_MMOD", "TEAM_PRICE_SPIKE_E",
                 "TEAM_EARTH_NEW_EXERCISE_DELAY", "TEAM_CAPEX_OVERRUN",
                 "TEAM_CHANNEL_A_CAPACITY", "TEAM_MLI_DEGRADATION",
                 "TEAM_GEO_CHANNEL_A"):
        sc = team_scenario(name)
        p = plan_s if name == "TEAM_ISRU_UNDERDELIVERY_COMBINED" else plan
        r, _, _ = run_team(case, p, sc)
        runs.append((name, r))

    # P01 факторные сценарии (на неизменном FINAL_BASE)
    from run_p01 import factor_scenarios
    for tag, sc in factor_scenarios().items():
        runs.append((tag, run_plan(case, plan, sc)))

    # P05 combined (явно объявленный; FINAL_STRESS)
    sc_m = mandatory_scenario()
    combined = Scenario(
        scenario_id="TEAM_GEO_A_MANDATORY_COMBINED",
        status="TEAM_ASSUMPTION",
        demand_multiplier=dict(sc_m.demand_multiplier),
        critical_demand_multiplier=dict(sc_m.critical_demand_multiplier),
        variable_price_multiplier={
            "Earth-Core": {"2038": 1.5, "2039": 1.5},
            "Earth-Flex": {"2038": 1.25, "2039": 1.25},
        },
        actual_delivery_share=dict(sc_m.actual_delivery_share),
        loss_ceiling=dict(sc_m.loss_ceiling),
        notes=["COMBINED (явно объявленный): mandatory ×1.25 и geo ×1.20 "
               "по одному разу (цена A 2038–39 = 9.30); план FINAL_STRESS"],
    )
    runs.append(("TEAM_GEO_A_MANDATORY_COMBINED", run_plan(case, plan_s, combined)))

    for name, r in runs:
        path = os.path.join(OUT, name)
        export_results(r, path, fmt="csv")
        print(f"  {name}: {path}")

    # адаптивные планы-меры — экспорт их прогонов под рисковым сценарием
    plans_dir = os.path.join(RESULTS, "plans_adaptive")
    for risk, sc_name in MIT_SCENARIOS.items():
        fpath = os.path.join(plans_dir, f"FINAL_MIT_{risk}.json")
        if not os.path.exists(fpath):
            continue
        p = load_saved_plan(fpath)
        sc = team_scenario(sc_name)
        r, _, _ = run_team(case, p, sc)
        path = os.path.join(OUT, f"MIT_{risk}")
        export_results(r, path, fmt="csv")
        print(f"  MIT_{risk}: {path}")


if __name__ == "__main__":
    main()
