"""P04 — reverse stress: grid-поиск ломающей комбинации
(множитель спроса × множитель цены A × фактическая доля D).

Сетка (протокол P04): спрос 1.00–1.50 шаг 0.05 (общий и критический
одновременно, D3.1); цена A 1.00–1.50 шаг 0.05; доля D 1.00–0.00 шаг 0.10
(2038–2040). Полный 3D-перебор 11×11×11 = 1331 узел (~2 с на ядре).

Критерий «сломан»: появление НОВОГО нарушения (rule_id, period) сверх
BASE-подписи плана S10 ИЛИ min SL_total ниже BASE. Минимальная комбинация —
по норме max(|Δdemand|/0.05, |Δprice|/0.05, |Δshare|/0.10); показываем все
узлы, равные минимуму. Норма — способ упорядочения сетки, не вероятность.

Серия на MANDATORY_STRESS — отдельная (явное имя): те же оси поверх
параметров mandatory (не подменяя их): множители спроса/цены A применяются
ДОПОЛНИТЕЛЬНО к CASE_INPUT-множителям mandatory (2038+ спрос ×1.15×dm,
цены A/B 2038–39 ×1.25×pm), доля D 2038/2039 = min(0.55/0.75, ds).

Выход: results/stress/P04_grid_base.csv, P04_grid_mandatory.csv,
P04_summary.md.
"""

from __future__ import annotations

import os

from wp3lib import (
    RESULTS,
    base_case,
    base_plan,
    base_scenario,
    mandatory_scenario,
    meta_block,
    min_sl_total,
    run_plan,
    shortage_of,
    violation_signature,
    write_csv,
    write_json,
)
from engine.models import Scenario  # noqa: E402

OUT = os.path.join(RESULTS, "stress")

DEM = [round(1.0 + 0.05 * i, 2) for i in range(11)]  # 1.00..1.50
PRC = [round(1.0 + 0.05 * i, 2) for i in range(11)]  # 1.00..1.50
SHR = [round(1.0 - 0.10 * i, 2) for i in range(11)]  # 1.00..0.00
YEARS = [str(y) for y in range(2035, 2041)]


def norm(dm: float, pm: float, ds: float) -> float:
    return max(abs(dm - 1.0) / 0.05, abs(pm - 1.0) / 0.05, abs(ds - 1.0) / 0.10)


def make_scenario_base(dm: float, pm: float, ds: float) -> Scenario:
    return Scenario(
        scenario_id=f"P04_BASE_d{dm:g}_p{pm:g}_s{ds:g}",
        status="TEAM_ASSUMPTION",
        demand_multiplier={y: dm for y in YEARS},
        critical_demand_multiplier={y: dm for y in YEARS},
        variable_price_multiplier={"Earth-Core": {y: pm for y in YEARS}},
        actual_delivery_share={
            "Lunar-ISRU": {str(y): ds for y in (2038, 2039, 2040)}
        },
    )


def make_scenario_mandatory(dm: float, pm: float, ds: float) -> Scenario:
    """Поверх MANDATORY_STRESS: дополнительные множители × CASE_INPUT.

    Спрос 2038–2040: 1.15×dm (2035–2037: dm — сетка исследует и ранние годы).
    Цена A 2038–2039: 1.25×pm, 2040: pm; B: как mandatory (1.25 2038–39).
    Доля D: min(CASE_INPUT 0.55/0.75/1.0, ds) — дополнительный шок не может
    увеличить поставку выше mandatory-доли (исследуем ухудшение).
    """
    mand_demand = {"2038": 1.15, "2039": 1.15, "2040": 1.15}
    dem_mult = {}
    for y in YEARS:
        dem_mult[y] = round(dm * mand_demand.get(y, 1.0), 6)
    pa = {y: pm for y in YEARS}
    for y in ("2038", "2039"):
        pa[y] = round(pm * 1.25, 6)
    shares = {"2038": 0.55, "2039": 0.75, "2040": 1.0}
    return Scenario(
        scenario_id=f"P04_MAND_d{dm:g}_p{pm:g}_s{ds:g}",
        status="TEAM_ASSUMPTION",
        demand_multiplier=dem_mult,
        critical_demand_multiplier=dict(dem_mult),
        variable_price_multiplier={
            "Earth-Core": pa,
            "Earth-Flex": {"2038": 1.25, "2039": 1.25},
        },
        actual_delivery_share={
            "Lunar-ISRU": {y: min(shares[y], ds) for y in ("2038", "2039", "2040")}
        },
        loss_ceiling={"enabled": True, "from_year": 2038,
                      "max_losses_divided_by_throughput": 0.02},
    )


def scan(series: str, make_sc, base_sig, base_sl) -> list[dict]:
    case = base_case()
    plan = base_plan()
    rows = []
    for dm in DEM:
        for pm in PRC:
            for ds in SHR:
                r = run_plan(case, plan, make_sc(dm, pm, ds))
                sig = violation_signature(r)
                new = sorted(sig - base_sig)
                broken = bool(new) or min_sl_total(r) < base_sl - 1e-9
                rows.append({
                    "series": series,
                    "demand_mult": dm, "priceA_mult": pm, "shareD": ds,
                    "norm": round(norm(dm, pm, ds), 2),
                    "broken": "true" if broken else "false",
                    "new_violations": len(new),
                    "first_new_rules": ";".join(sorted({rid for rid, _ in new}))[:200],
                    "min_sl_total": round(min_sl_total(r), 4),
                    "shortage_t": round(shortage_of(r), 2),
                })
    return rows


def minima(rows: list[dict]) -> list[dict]:
    broken = [r for r in rows if r["broken"] == "true"]
    if not broken:
        return []
    nmin = min(r["norm"] for r in broken)
    return [r for r in broken if r["norm"] == nmin]


def main() -> None:
    case = base_case()
    plan = base_plan()
    r_base = run_plan(case, plan, base_scenario())
    base_sig = violation_signature(r_base)
    base_sl = min_sl_total(r_base)

    r_mand = run_plan(case, plan, mandatory_scenario())
    mand_sig = violation_signature(r_mand)
    mand_sl = min_sl_total(r_mand)

    rows_base = scan("BASE", make_scenario_base, base_sig, base_sl)
    write_csv(os.path.join(OUT, "P04_grid_base.csv"),
              list(rows_base[0].keys()), rows_base)

    rows_mand = scan("MANDATORY_STRESS", make_scenario_mandatory, mand_sig, mand_sl)
    write_csv(os.path.join(OUT, "P04_grid_mandatory.csv"),
              list(rows_mand[0].keys()), rows_mand)

    min_base = minima(rows_base)
    min_mand = minima(rows_mand)

    # первые нарушающие узлы по каждому новому правилу
    def first_by_rule(rows):
        out = {}
        for r in sorted(rows, key=lambda x: (x["norm"], x["demand_mult"],
                                             x["priceA_mult"], -x["shareD"])):
            if r["broken"] == "true":
                for rule in r["first_new_rules"].split(";"):
                    if rule and rule not in out:
                        out[rule] = r
        return out

    summary = {
        "series_BASE": {
            "base_signature": sorted(base_sig)[:60],
            "broken_nodes": sum(1 for r in rows_base if r["broken"] == "true"),
            "total_nodes": len(rows_base),
            "min_norm": min_base[0]["norm"] if min_base else None,
            "min_nodes": min_base,
            "first_by_rule": {k: v for k, v in first_by_rule(rows_base).items()},
        },
        "series_MANDATORY_STRESS": {
            "base_signature": sorted(mand_sig)[:60],
            "broken_nodes": sum(1 for r in rows_mand if r["broken"] == "true"),
            "total_nodes": len(rows_mand),
            "min_norm": min_mand[0]["norm"] if min_mand else None,
            "min_nodes": min_mand,
            "first_by_rule": {k: v for k, v in first_by_rule(rows_mand).items()},
        },
    }
    write_json(os.path.join(OUT, "P04_summary.json"), summary)
    write_json(os.path.join(OUT, "P04_meta.json"), meta_block(
        "P04_reverse_stress_grid", plan.plan_id,
        extra={"protocol": "P04",
               "axes": {"demand": "1.00-1.50 step 0.05 (total+critical)",
                        "priceA": "1.00-1.50 step 0.05",
                        "shareD": "1.00-0.00 step 0.10 (2038-2040)"},
               "norm": "max(|dD|/0.05, |dP|/0.05, |dS|/0.10)",
               "broken_criterion": "новое (rule_id, period) сверх подписи "
                                     "контроля ИЛИ min SL_total ниже контроля"}))

    print(f"BASE серия: сломано {summary['series_BASE']['broken_nodes']}"
          f"/{len(rows_base)}; минимальная норма {summary['series_BASE']['min_norm']}")
    for r in min_base[:12]:
        print(f"  d={r['demand_mult']} p={r['priceA_mult']} s={r['shareD']} "
              f"→ {r['first_new_rules']} (SL={r['min_sl_total']}, "
              f"short={r['shortage_t']} т)")
    print(f"MANDATORY серия: сломано {summary['series_MANDATORY_STRESS']['broken_nodes']}"
          f"/{len(rows_mand)}; минимальная норма "
          f"{summary['series_MANDATORY_STRESS']['min_norm']}")
    for r in min_mand[:12]:
        print(f"  d={r['demand_mult']} p={r['priceA_mult']} s={r['shareD']} "
              f"→ {r['first_new_rules']} (SL={r['min_sl_total']}, "
              f"short={r['shortage_t']} т)")
    print("Первые нарушающие узлы по правилам (BASE):")
    for rule, r in first_by_rule(rows_base).items():
        print(f"  {rule}: d={r['demand_mult']} p={r['priceA_mult']} s={r['shareD']}")
    print("Первые нарушающие узлы по правилам (MANDATORY):")
    for rule, r in first_by_rule(rows_mand).items():
        print(f"  {rule}: d={r['demand_mult']} p={r['priceA_mult']} s={r['shareD']}")


if __name__ == "__main__":
    main()
