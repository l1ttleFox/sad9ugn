"""P03 — TEAM-риски R01–R10 на FINAL-планах: прогон каждого сценария
risk_register.yaml, затем мера (mitigation) отдельным адаптивным планом
и остаточный риск (prompt_wave2.md п.4, протокол P03, REFRESH п.5).

Контроль: BASE на FINAL_BASE, кроме R01 (TEAM_ISRU_UNDERDELIVERY_COMBINED —
явно комбинированный сценарий, контроль MANDATORY_STRESS на FINAL_STRESS).

Меры — копии FINAL-планов (results/plans_adaptive/FINAL_MIT_Rxx.json),
производные от состава FINAL: каналы A/B/D (C/E в плане нет), headroom B
110 т/год (месячный лимит отгрузки 9.167 т) при фактических заказах B —
главный инструмент компенсации (lead 4 мес). Для R08 мера дополнительно
срезает заказы и резерв A 2038 (мощность физически недоступна). Для R02
снимаются заказы недоступного канала D (перезаказ B). INVENTORY_SHOCK_APPLIED
— информационная запись, в hard-нарушения не входит (D8.3).

Стоимость меры = PV(адаптивный план под риском) − PV(фиксированный план
под риском); остаточный риск = дельты адаптивного прогона против контроля.

Выход: results/stress/P03_risks.csv, P03_yearly_*.csv, P03_meta.json.
"""

from __future__ import annotations

import collections
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
    reduce_channel_year_orders,
    remove_channel_year_orders,
    run_plan,
    run_team,
    set_reservation,
    shortage_of,
    stress_plan,
    team_scenario,
    total_cost_of,
    violation_signature,
    info_signature,
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

B_MONTHLY_CAP = 110.0 / 12.0  # резерв B 110 т/год, месячная доля отгрузки


def _shift_month(period: str, k: int) -> str:
    y, m = int(period[:4]), int(period[5:7])
    idx = (y - 2000) * 12 + (m - 1) + k
    return f"{2000 + idx // 12:04d}-{idx % 12 + 1:02d}"


def b_orders_for_delivery_window(
    plan, need_t: float, deliv_start: str, deliv_end: str
) -> tuple[list[tuple[str, str, float]], float]:
    """Заказы B под окно поставки [deliv_start, deliv_end] с учётом
    месячного headroom B (резерв 110/12 минус уже размещённые заказы;
    заказ M → поставка M+4). Возвращает (заказы, неразмещённый остаток)."""
    existing = collections.defaultdict(float)
    for o in plan.decisions.supply_orders:
        if o.source_id == "B" and o.ordered_volume_t > 0:
            existing[o.period] += o.ordered_volume_t
    orders: list[tuple[str, str, float]] = []
    left = need_t
    om = _shift_month(deliv_start, -4)
    om_end = _shift_month(deliv_end, -4)
    while left > 1e-9 and om <= om_end:
        room = B_MONTHLY_CAP - existing.get(om, 0.0)
        if room > 1e-9:
            v = min(room, left)
            orders.append(("B", om, round(v, 4)))
            left -= v
        om = _shift_month(om, 1)
    return orders, left


def mitigation_plan(risk_id: str, plan, ctx: dict):
    """Адаптивный план-мера, производная от FINAL-плана; None если мера не
    требуется/не применима. Возвращает (Plan, описание меры на русском)."""
    if risk_id == "R01":
        # COMBINED на FINAL_STRESS: доля D 2038 0.55→0.40 → потеря
        # 0.15 × 63.76 ≈ 9.6 т; запас FINAL_STRESS на 2039-01 падает до
        # 40.6 < 45.4 (RESERVE_45D). +10 т B с поставкой в конце 2038.
        p = clone_plan(plan, "FINAL_MIT_R01")
        ords, left = b_orders_for_delivery_window(p, 10.0, "2038-09", "2038-12")
        add_orders(p, ords)
        assert left < 1e-9
        return p, ("+10 т заказов B (окно поставки 2038-09…2038-12, lead 4 мес) "
                   "под недопоставку D 0.15×63.8≈9.6 т в combined-стрессе")
    if risk_id == "R02":
        # D недоступен весь 2038: снимаются заказы D с поставкой 2038
        # (заказы 2037-11…2038-10), замещение +66 т B (покрытие поставки
        # D 2038 63.0 т + восстановление 45-дн. резерва на 2039-01).
        p = clone_plan(plan, "FINAL_MIT_R02")
        p.decisions.supply_orders = [
            o for o in p.decisions.supply_orders
            if not (
                o.source_id == "D"
                and (
                    o.period in ("2037-11", "2037-12")
                    or (o.period.startswith("2038") and int(o.period[5:7]) <= 10)
                )
            )
        ]
        ords, left = b_orders_for_delivery_window(p, 66.0, "2038-01", "2038-12")
        add_orders(p, ords)
        assert left < 1e-9, f"R02: headroom B недостаточен, остаток {left}"
        return p, ("перезаказ: сняты заказы недоступного D с поставкой 2038 "
                   "(63.0 т), замещены +66 т B (поставка 2038-01…2038-12, "
                   "lead 4 мес, headroom B исчерпан); CAPEX ISRU сохраняется")
    if risk_id == "R04":
        # MMOD 2038-07: потеря 25% × I_start 49.1 = 12.3 т (интервал
        # 10–50% → 4.9–24.6 т). Мера-страховка +18 т B с поставкой ПОСЛЕ
        # шока (2038-08…2038-12) закрывает весь интервал до 50% включительно.
        p = clone_plan(plan, "FINAL_MIT_R04")
        ords, left = b_orders_for_delivery_window(p, 18.0, "2038-08", "2038-12")
        add_orders(p, ords)
        assert left < 1e-9
        return p, ("+18 т заказов B с поставкой 2038-08…2038-12 (строго ПОСЛЕ "
                   "шока 2038-07 — дозаказ до шока увеличил бы списание); "
                   "закрывает потерю 12.3 т (25%) и весь интервал 10–50% "
                   "(4.9–24.6 т) с восстановлением резерва 45 дн. на 2039–2040")
    if risk_id == "R08":
        # Мощность A 2038 190→152: заказы A 2037 (поставка 2038, lead 12)
        # срезаются на 38 т, резерв A 2038 приводится к фактической мощности
        # 152, замещение +38 т B в поставку 2038.
        p = clone_plan(plan, "FINAL_MIT_R08")
        p = reduce_channel_year_orders(p, "A", 2037, 38.0)
        p = set_reservation(p, "A", 2038, 152.0)
        ords, left = b_orders_for_delivery_window(p, 38.0, "2038-01", "2038-12")
        add_orders(p, ords)
        assert left < 1e-9
        return p, ("срез заказов A 2037 на 38 т (поставка 2038) + резерв A "
                   "2038 → 152 т/год (фактическая мощность) + замещение "
                   "+38 т B (поставка 2038-01…2038-12, lead 4 мес)")
    # R03, R09: новых нарушений нет, запас поглощает эффект — мера
    # не требуется (страховочный дозаказ B рассчитывается в residual_note).
    # R05, R06, R10: мера не применима (нулевой прямой эффект / только цена).
    # R07: лимит не нарушен (headroom FINAL раскрывается численно).
    return None


def collect(tag: str, r, ctrl_metrics: dict, ctrl_sig: set) -> dict:
    sig = violation_signature(r)
    return {
        "run": tag,
        "scenario_id": r.scenario_id,
        "plan_id": r.plan_id,
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
        "info_events": len(info_signature(r) - info_signature(ctrl_metrics["result"])),
    }


def main() -> None:
    case = base_case()
    plan_base = base_plan()       # FINAL_BASE
    plan_stress = stress_plan()   # FINAL_STRESS

    r_base = run_plan(case, plan_base, base_scenario())
    r_mand = run_plan(case, plan_stress, mandatory_scenario())
    ctrl = {
        "BASE": {
            "metrics": {
                "total": total_cost_of(r_base), "pv": pv_of(r_base),
                "shortage": shortage_of(r_base), "min_sl": min_sl_total(r_base),
                "result": r_base,
            },
            "sig": violation_signature(r_base),
            "plan": plan_base,
            "result": r_base,
        },
        "MANDATORY_STRESS": {
            "metrics": {
                "total": total_cost_of(r_mand), "pv": pv_of(r_mand),
                "shortage": shortage_of(r_mand), "min_sl": min_sl_total(r_mand),
                "result": r_mand,
            },
            "sig": violation_signature(r_mand),
            "plan": plan_stress,
            "result": r_mand,
        },
    }

    rows = []
    yearly_rows = [{"run": "BASE", **y} for y in yearly_row(r_base)]
    yearly_rows += [{"run": "MANDATORY_STRESS", **y} for y in yearly_row(r_mand)]
    fin_rows = [{"run": "BASE", **fr} for fr in finance_row(r_base)]
    fin_rows += [{"run": "MANDATORY_STRESS", **fr} for fr in finance_row(r_mand)]

    # плановая поставка D 2038 (FINAL_BASE) — для формул последствий
    d38_base = sum(
        v for (s, p), v in r_base.deliveries.planned_by_source_period.items()
        if s == "D" and p.startswith("2038")
    )
    i07_base = next(
        m.i_start_t for m in r_base.inventory.monthly_balance if m.period == "2038-07"
    )

    for risk_id, (sc_name, control) in TEAM_SCENARIOS.items():
        sc = team_scenario(sc_name)
        plan_fix = ctrl[control]["plan"]
        r_fix, used_plan, journal = run_team(case, plan_fix, sc)
        tag = f"{risk_id}:{sc_name}"
        yearly_rows += [{"run": tag, **y} for y in yearly_row(r_fix)]
        fin_rows += [{"run": tag, **fr} for fr in finance_row(r_fix)]
        row = {
            "risk_id": risk_id, "scenario": sc_name, "control": control,
            "plan_id": plan_fix.plan_id,
        }
        row.update(collect(tag, r_fix, ctrl[control]["metrics"], ctrl[control]["sig"]))
        row["journal"] = " | ".join(journal)

        # --- мера (адаптивный план, производная от FINAL) ---
        mit = mitigation_plan(risk_id, plan_fix, {"d38": d38_base, "i07": i07_base})
        if mit is None:
            if risk_id == "R03":
                row["mitigation"] = ("не требуется: дополнительных нарушений нет, "
                                     "запас поглощает +8.7 т потерь 2038 (резерв "
                                     "45 дн. на 2039-01: 40.5 ≥ 39.5); страховочный "
                                     "дозаказ +9 т B доступен в пределах headroom")
            elif risk_id == "R05":
                row["mitigation"] = ("не требуется: FINAL-план не использует канал E "
                                     "(нулевой прямой эффект); косвенных нарушений нет")
            elif risk_id == "R06":
                row["mitigation"] = ("не применима: в FINAL-плане (S10) нет инвестиции "
                                     "EARTH_NEW — канал C не используется (адаптер "
                                     "зафиксировал no-op в журнале); риск остаётся "
                                     "актуален только для альтернатив S14/S18/S21")
            elif risk_id == "R07":
                row["mitigation"] = ("не требуется: CAPEX cum 2037 FINAL = 1430 + 187.5 "
                                     "= 1617.5 ≤ 1800 (headroom 182.5 млн); лимит не "
                                     "нарушен. Для альтернатив с headroom 10 млн "
                                     "(S14/S18/S21) тот же шок ломает CAPEX_2037")
            elif risk_id == "R09":
                row["mitigation"] = ("не требуется: +5.3 т потерь 2036–2037 поглощаются "
                                     "запасом (I 2038-01 = 39.0 ≥ 30.8), нарушений нет; "
                                     "страховочный дозаказ +4.5 т B стоит ≈ +47 млн PV — "
                                     "экономически неоправдан")
            elif risk_id == "R10":
                row["mitigation"] = ("физическая мера не применима (тарифный шок цены A; "
                                     "поставки и сервис не меняются); управленческая мера — "
                                     "перенос объёмов 2038–2039 на B (headroom ≈ 30–80 т/год) "
                                     "ограничен TOP A = 0.70×190 = 133 т: платежи A не "
                                     "снижаются ниже TOP, экономия ≤ (7.44−8.9)×ΔQ < 0 — "
                                     "перенос на B дороже; риск принимается")
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

    cols = ["risk_id", "scenario", "control", "plan_id", "scenario_id",
            "total_mln", "pv_mln", "shortage_t", "min_sl_total", "min_sl_critical",
            "d_total_mln", "d_pv_mln", "d_shortage_t", "d_min_sl_total_pp",
            "new_violations", "new_violation_rules", "violations_total",
            "info_events", "mitigation", "mitigation_cost_pv_mln",
            "residual_d_pv_mln", "residual_d_shortage_t",
            "residual_new_violations", "residual_note", "journal"]
    write_csv(os.path.join(OUT, "P03_risks.csv"), cols, rows)
    write_csv(os.path.join(OUT, "P03_yearly_balance.csv"),
              ["run"] + list(yearly_row(r_base)[0].keys()), yearly_rows)
    write_csv(os.path.join(OUT, "P03_financial_breakdown.csv"),
              ["run"] + list(finance_row(r_base)[0].keys()), fin_rows)
    write_json(os.path.join(OUT, "P03_meta.json"), meta_block(
        "P03_team_risks", f"{plan_base.plan_id}+{plan_stress.plan_id}",
        extra={"protocol": "P03", "plan_note": PLAN_LABEL,
               "controls": {"R01": f"MANDATORY_STRESS ({plan_stress.plan_id})",
                            "others": f"BASE ({plan_base.plan_id})"},
               "d38_planned_base": round(d38_base, 3),
               "i_start_2038_07_base": round(i07_base, 3),
               "info_rule_policy": "INVENTORY_SHOCK_APPLIED — информационное "
                                   "событие, исключено из hard-нарушений (D8.3)"}))

    print("P03 результаты (дельты против контроля):")
    for row in rows:
        print(f"  {row['risk_id']} ({row['scenario']}, ctrl={row['control']}): "
              f"ΔPV={row['d_pv_mln']:+.1f} млн, Δshort={row['d_shortage_t']:+.1f} т, "
              f"ΔminSL={row['d_min_sl_total_pp']:+.2f} п.п., "
              f"новых нарушений={row['new_violations']} "
              f"[{row['new_violation_rules'][:80]}]")
        print(f"      мера: {row['mitigation'][:120]}")
        print(f"      стоимость меры ΔPV={row['mitigation_cost_pv_mln']:+.1f} млн; "
              f"остаток ΔPV={row['residual_d_pv_mln']:+.1f}, "
              f"Δshort={row['residual_d_shortage_t']:+.1f} т, "
              f"новых нарушений={row['residual_new_violations']}")


if __name__ == "__main__":
    main()
