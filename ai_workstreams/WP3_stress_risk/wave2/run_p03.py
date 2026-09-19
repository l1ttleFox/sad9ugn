"""P03 — TEAM-риски R01–R10: прогон каждого сценария risk_register.yaml
на фиксированном плане S10, затем мера (mitigation) отдельным адаптивным
планом и остаточный риск (prompt_wave2.md п.4, протокол P03).

Контроль: BASE, кроме R01 (TEAM_ISRU_UNDERDELIVERY_COMBINED — явно
комбинированный сценарий, контроль MANDATORY_STRESS).

Меры — копии плана S10 с дополнительными заказами канала B (единственный
канал с headroom резерва и коротким lead time 4 мес; A зарезервирован под
потолок, C/E в плане нет). Адаптивный план сохраняется отдельно
(results/plans_adaptive/S10_MIT_Rxx.json) и НЕ приписывается окружению
(P03 §Общая процедура).

Стоимость меры = PV(адаптивный план под риском) − PV(фиксированный план
под риском); остаточный риск = дельты адаптивного прогона против контроля.

Выход: results/stress/P03_risks.csv, P03_yearly_*.csv, P03_meta.json.
"""

from __future__ import annotations

import json
import os

from wp3lib import (
    PLAN_LABEL,
    RESULTS,
    add_orders,
    base_case,
    base_plan,
    base_scenario,
    clone_plan,
    finance_row,
    mandatory_scenario,
    meta_block,
    min_sl_crit,
    min_sl_total,
    pv_of,
    run_plan,
    run_team,
    shortage_of,
    team_scenario,
    total_cost_of,
    violation_signature,
    write_csv,
    write_json,
    yearly_row,
)

OUT = os.path.join(RESULTS, "stress")
PLANS_OUT = os.path.join(RESULTS, "plans_adaptive")

TEAM_SCENARIOS = {
    "R01": ("TEAM_ISRU_UNDERDELIVERY_COMBINED", "MANDATORY_STRESS"),
    "R02": ("TEAM_ISRU_DELAY", "BASE"),
    "R03": ("TEAM_ZBO_FAILURE", "BASE"),
    "R04": ("TEAM_MMOD", "BASE"),
    "R05": ("TEAM_PRICE_SPIKE_E", "BASE"),
    "R06": ("TEAM_EARTH_NEW_EXERCISE_DELAY", "BASE"),
    "R07": ("TEAM_CAPEX_OVERRUN", "BASE"),
    "R08": ("TEAM_CHANNEL_A_CAPACITY", "BASE"),
    "R09": ("TEAM_MLI_DEGRADATION", "BASE"),
    "R10": ("TEAM_GEO_CHANNEL_A", "BASE"),
}


def b_orders_window(months: list[str], total_t: float) -> list[tuple[str, str, float]]:
    """Равномерные доп. заказы B по списку месяцев ('YYYY-MM')."""
    per = round(total_t / len(months), 4)
    return [("B", m, per) for m in months]


def months_2037_09_to_2038_08() -> list[str]:
    return [f"2037-{m:02d}" for m in range(9, 13)] + [f"2038-{m:02d}" for m in range(1, 9)]


def mitigation_plan(risk_id: str, plan) -> tuple[object, str] | None:
    """Адаптивный план-мера; None если мера не требуется/не применима.

    Возвращает (Plan, описание меры на русском).
    """
    if risk_id == "R01":
        # Недопоставка D 2038: 0.15 × planned_D_2038 ≈ 7.9 т → +8 т у B
        p = clone_plan(plan, "S10_MIT_R01")
        add_orders(p, b_orders_window(months_2037_09_to_2038_08(), 8.0))
        return p, "+8 т заказов B (поставка 2038-01…2038-12, lead 4 мес) под недопоставку D 0.15×52.6≈7.9 т"
    if risk_id == "R02":
        # D недоступен весь 2038: planned_D_2038 ≈ 52.6 т → +53 т у B
        p = clone_plan(plan, "S10_MIT_R02")
        add_orders(p, b_orders_window(months_2037_09_to_2038_08(), 53.0))
        return p, "+53 т заказов B (поставка 2038-01…2038-12) взамен всего объёма D 2038 (52.6 т); CAPEX ISRU сохраняется"
    if risk_id == "R03":
        # ZBO 2038: доп. потери 0.033 × throughput_2038 ≈ 8.3 т → +9 т у B
        p = clone_plan(plan, "S10_MIT_R03")
        add_orders(p, b_orders_window(months_2037_09_to_2038_08(), 9.0))
        return p, "+9 т заказов B (поставка в 2038) под дополнительные потери 0.033×251.7≈8.3 т"
    if risk_id == "R04":
        # MMOD 2038-07: потеря 25% I_start = 0.03 т (запас ядра мал).
        # Дозаказ ПОСЛЕ шока (чтобы шок не вырос): поставка 2038-08…2038-12 →
        # заказы 2038-04…2038-08; +1 т — с большим запасом покрывает потерю
        # и интервал 10–50% (0.01–0.06 т).
        p = clone_plan(plan, "S10_MIT_R04")
        add_orders(p, b_orders_window(
            [f"2038-{m:02d}" for m in range(4, 9)], 1.0))
        return p, "+1 т заказов B с поставкой 2038-08…2038-12 (ПОСЛЕ шока 2038-07 — дозаказ до шока увеличил бы списание 25%); покрывает потерю 0.25×0.11≈0.03 т и весь интервал 10–50%"
    if risk_id == "R08":
        # A 2038: 190→152 → −38 т → +38 т у B
        p = clone_plan(plan, "S10_MIT_R08")
        add_orders(p, b_orders_window(months_2037_09_to_2038_08(), 38.0))
        return p, "+38 т заказов B (поставка 2038-01…2038-12) под срез мощности A 190→152 т/год"
    if risk_id == "R09":
        # MLI BASE 2036–2037: доп. потери 0.015 × throughput ≈ 3.9 т → +4.5 т
        p = clone_plan(plan, "S10_MIT_R09")
        add_orders(p, b_orders_window(
            [f"2036-{m:02d}" for m in range(1, 7)], 4.5))
        return p, "+4.5 т заказов B (поставка 2036-05…2036-10) под доп. потери BASE-хранения 0.015×261≈3.9 т"
    # R05, R06, R10 — мера не требуется (нулевой прямой эффект у S10);
    # R07 — лимит не нарушается, мера не требуется (headroom раскрывается).
    return None


def collect(tag: str, r, ctrl_metrics: dict, ctrl_sig: set) -> dict:
    sig = violation_signature(r)
    return {
        "run": tag,
        "scenario_id": r.scenario_id,
        "total_mln": round(total_cost_of(r), 2),
        "pv_mln": round(pv_of(r), 2),
        "shortage_t": round(shortage_of(r), 3),
        "min_sl_total": round(min_sl_total(r), 4),
        "min_sl_critical": round(min_sl_crit(r), 4),
        "d_total_mln": round(total_cost_of(r) - ctrl_metrics["total"], 2),
        "d_pv_mln": round(pv_of(r) - ctrl_metrics["pv"], 2),
        "d_shortage_t": round(shortage_of(r) - ctrl_metrics["shortage"], 3),
        "d_min_sl_total_pp": round((min_sl_total(r) - ctrl_metrics["min_sl"]) * 100, 3),
        "new_violations": len(sig - ctrl_sig),
        "new_violation_rules": ";".join(sorted({rid for rid, _ in sig - ctrl_sig})),
        "violations_total": len(sig),
    }


def main() -> None:
    case = base_case()
    plan = base_plan()

    r_base = run_plan(case, plan, base_scenario())
    r_mand = run_plan(case, plan, mandatory_scenario())
    ctrl = {
        "BASE": {
            "metrics": {
                "total": total_cost_of(r_base), "pv": pv_of(r_base),
                "shortage": shortage_of(r_base), "min_sl": min_sl_total(r_base),
            },
            "sig": violation_signature(r_base),
            "result": r_base,
        },
        "MANDATORY_STRESS": {
            "metrics": {
                "total": total_cost_of(r_mand), "pv": pv_of(r_mand),
                "shortage": shortage_of(r_mand), "min_sl": min_sl_total(r_mand),
            },
            "sig": violation_signature(r_mand),
            "result": r_mand,
        },
    }

    rows = []
    yearly_rows = [{"run": "BASE", **y} for y in yearly_row(r_base)]
    yearly_rows += [{"run": "MANDATORY_STRESS", **y} for y in yearly_row(r_mand)]
    fin_rows = [{"run": "BASE", **fr} for fr in finance_row(r_base)]
    fin_rows += [{"run": "MANDATORY_STRESS", **fr} for fr in finance_row(r_mand)]

    for risk_id, (sc_name, control) in TEAM_SCENARIOS.items():
        sc = team_scenario(sc_name)
        r_fix, used_plan, journal = run_team(case, plan, sc)
        tag = f"{risk_id}:{sc_name}"
        yearly_rows += [{"run": tag, **y} for y in yearly_row(r_fix)]
        fin_rows += [{"run": tag, **fr} for fr in finance_row(r_fix)]
        row = {"risk_id": risk_id, "scenario": sc_name, "control": control}
        row.update(collect(tag, r_fix, ctrl[control]["metrics"], ctrl[control]["sig"]))
        row["journal"] = " | ".join(journal)

        # --- мера (адаптивный план) ---
        mit = mitigation_plan(risk_id, plan)
        if mit is None:
            if risk_id == "R05":
                row["mitigation"] = ("не требуется: план S10 не использует канал E "
                                     "(нулевой прямой эффект); косвенных нарушений нет")
            elif risk_id == "R06":
                row["mitigation"] = ("не применима: в плане S10 нет инвестиции "
                                     "EARTH_NEW (адаптер зафиксировал no-op в журнале)")
            elif risk_id == "R07":
                row["mitigation"] = ("не требуется: CAPEX cum 2037 = 1617.5 ≤ 1800 "
                                     "(headroom 182.5 млн); лимит не нарушен")
            elif risk_id == "R10":
                row["mitigation"] = ("физическая мера не применима (тарифный шок "
                                     "цены A; поставки и сервис не меняются); "
                                     "управленческая мера — перенос объёмов на "
                                     "B/D в 2038–2039 ограничением headroom B "
                                     "и TOP A=0.70 — вне рамок фиксированного "
                                     "плана S10, оценивается как остаточный "
                                     "финансовый риск")
            else:
                row["mitigation"] = ("не требуется: нулевой прямой эффект "
                                     "(только цена, физика не меняется)")
            row["mitigation_cost_pv_mln"] = 0.0
            row["residual_d_pv_mln"] = row["d_pv_mln"]
            row["residual_d_shortage_t"] = row["d_shortage_t"]
            row["residual_new_violations"] = row["new_violations"]
            row["residual_note"] = "остаток = последствию (мера не применялась)"
        else:
            mit_plan, desc = mit
            os.makedirs(PLANS_OUT, exist_ok=True)
            from engine import save_plan
            save_plan(mit_plan, os.path.join(PLANS_OUT, f"{mit_plan.plan_id}.json"))
            r_mit, _, journal_m = run_team(case, mit_plan, sc)
            tag_m = f"{risk_id}:MIT:{sc_name}"
            yearly_rows += [{"run": tag_m, **y} for y in yearly_row(r_mit)]
            fin_rows += [{"run": tag_m, **fr} for fr in finance_row(r_mit)]
            row["mitigation"] = desc
            row["mitigation_cost_pv_mln"] = round(pv_of(r_mit) - pv_of(r_fix), 2)
            row["residual_d_pv_mln"] = round(
                pv_of(r_mit) - ctrl[control]["metrics"]["pv"], 2)
            row["residual_d_shortage_t"] = round(
                shortage_of(r_mit) - ctrl[control]["metrics"]["shortage"], 3)
            sig_m = violation_signature(r_mit)
            row["residual_new_violations"] = len(sig_m - ctrl[control]["sig"])
            row["residual_note"] = (
                f"minSL={min_sl_total(r_mit):.4f}; план {mit_plan.plan_id} "
                f"сохранён в results/plans_adaptive/")
        rows.append(row)

    cols = ["risk_id", "scenario", "control", "scenario_id", "total_mln", "pv_mln",
            "shortage_t", "min_sl_total", "min_sl_critical",
            "d_total_mln", "d_pv_mln", "d_shortage_t", "d_min_sl_total_pp",
            "new_violations", "new_violation_rules", "violations_total",
            "mitigation", "mitigation_cost_pv_mln",
            "residual_d_pv_mln", "residual_d_shortage_t",
            "residual_new_violations", "residual_note", "journal"]
    write_csv(os.path.join(OUT, "P03_risks.csv"), cols, rows)
    write_csv(os.path.join(OUT, "P03_yearly_balance.csv"),
              ["run"] + list(yearly_row(r_base)[0].keys()), yearly_rows)
    write_csv(os.path.join(OUT, "P03_financial_breakdown.csv"),
              ["run"] + list(finance_row(r_base)[0].keys()), fin_rows)
    write_json(os.path.join(OUT, "P03_meta.json"), meta_block(
        "P03_team_risks", plan.plan_id,
        extra={"protocol": "P03", "plan_note": PLAN_LABEL,
               "controls": {"R01": "MANDATORY_STRESS", "others": "BASE"}}))

    print("P03 результаты (дельты против контроля):")
    for row in rows:
        print(f"  {row['risk_id']} ({row['scenario']}, ctrl={row['control']}): "
              f"ΔPV={row['d_pv_mln']:+.1f} млн, Δshort={row['d_shortage_t']:+.1f} т, "
              f"ΔminSL={row['d_min_sl_total_pp']:+.2f} п.п., "
              f"новых нарушений={row['new_violations']} "
              f"[{row['new_violation_rules']}]")
        print(f"      мера: {row['mitigation'][:110]}")
        print(f"      стоимость меры ΔPV={row['mitigation_cost_pv_mln']:+.1f} млн; "
              f"остаток ΔPV={row['residual_d_pv_mln']:+.1f}, "
              f"Δshort={row['residual_d_shortage_t']:+.1f} т, "
              f"новых нарушений={row['residual_new_violations']}")


if __name__ == "__main__":
    main()
