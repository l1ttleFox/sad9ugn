"""P05 — геополитический бонус: TEAM_GEO_CHANNEL_A как работающий модуль.

Цикл модуля (prompt_wave2.md п.5, протокол P05):
  1. event: коэффициент 1.20 к агрегированной переменной цене канала A
     (6.2 → 7.44 млн/т) в 2038–2039 — применяется ОДИН раз через
     variable_price_multiplier (price-override в scenario_parameters
     дублирует событие и игнорируется — см. wp3lib: предотвращение
     двойного начёта, баг конфигов зафиксирован в REPORT_wave2);
  2. пересчёт того же плана S10 → Δ расходов/PV/SL/нарушений;
  3. экспорт параметров события (results/geopolitics/geo_event.json):
     event_id, канал, исходная цена, коэффициент, новые цены по годам,
     период, версия данных, input diff;
  4. восстановление контрольных цен: повторный прогон BASE после события
     = исходные числа (побайтово) + цена A снова 6.2 + sha256 исходных
     файлов data/supply_sources.csv и configs/*.yaml не изменился;
  5. стороны эффекта: заказчик (ΔPV), провайдер A (Δ выручки канала A).

Combined: TEAM_GEO_A_MANDATORY_COMBINED — явно объявленный отдельный
сценарий (P05 §Сочетание): спрос/D/потолок как в mandatory; цена A
2038–2039 = 6.2 × 1.25 × 1.20 = 9.30 (ровно один раз каждый шок),
B = 8.9 × 1.25. Правило «эффект не начисляется дважды» проверяется
арифметикой множителей и отсутствием двойного применения в журнале.

Выход: results/geopolitics/*.csv/json.
"""

from __future__ import annotations

import hashlib
import os

from wp3lib import (
    RESULTS,
    REPO,
    base_case,
    base_plan,
    base_scenario,
    finance_row,
    mandatory_scenario,
    meta_block,
    min_sl_total,
    pv_of,
    run_plan,
    shortage_of,
    team_scenario,
    total_cost_of,
    violation_signature,
    write_csv,
    write_json,
    yearly_row,
)
from engine.models import Scenario  # noqa: E402

OUT = os.path.join(RESULTS, "geopolitics")

FILES_TO_HASH = [
    os.path.join(REPO, "data", "supply_sources.csv"),
    os.path.join(REPO, "configs", "base.yaml"),
    os.path.join(REPO, "configs", "mandatory_stress.yaml"),
]


def file_hashes() -> dict[str, str]:
    return {
        os.path.relpath(p, REPO): hashlib.sha256(open(p, "rb").read()).hexdigest()
        for p in FILES_TO_HASH
    }


def channel_payments(r, plan, source_id: str) -> dict[int, float]:
    """Переменные платежи канала по годам: price_eff × max(Q_order, TOP×reserved).

    Q_order — заказы, фактически принятые к исполнению (без LEAD_TIME/
    CAPACITY-срезки — повтор формулы finance.py для одной стороны эффекта).
    """
    from engine.deliveries import month_index, channel_available_from, lead_time_months

    reserved: dict[tuple[str, int], float] = {}
    for res in plan.decisions.capacity_reservations:
        key = (res.source_id, res.year)
        reserved[key] = max(reserved.get(key, 0.0), res.reserved_capacity_t_per_year)

    ordered: dict[int, float] = {}
    avail = channel_available_from(plan, r.case, source_id)
    rsv_by = r.deliveries.reserved_by_source_year
    for o in plan.decisions.supply_orders:
        if o.source_id != source_id or o.ordered_volume_t <= 0:
            continue
        y, m = int(o.period[:4]), int(o.period[5:7])
        idx = month_index(y, m)
        if avail is None or idx < avail:
            continue
        monthly_limit = rsv_by.get((source_id, y), 0.0) / 12.0
        if monthly_limit > 0 and (source_id, y) in r.case.capacity_override:
            monthly_limit = r.case.capacity_override[(source_id, y)] / 12.0
        vol = min(o.ordered_volume_t, monthly_limit) if monthly_limit > 0 else 0.0
        ordered[y] = ordered.get(y, 0.0) + vol

    src = r.case.source(source_id)
    out: dict[int, float] = {}
    for y in range(2035, 2041):
        q_order = ordered.get(y, 0.0)
        top = src.take_or_pay_share * reserved.get((source_id, y), 0.0)
        q_pay = max(q_order, top)
        price = r.case.effective_price_mln_per_t.get((source_id, y), 0.0)
        out[y] = price * q_pay
    return out


def main() -> None:
    hashes_before = file_hashes()
    case = base_case()
    plan = base_plan()

    # --- 1. контроль BASE (до события) ---
    r_before = run_plan(case, plan, base_scenario())
    price_a_before = case.source("A").variable_cost_mln_per_t

    # --- 2. гео-событие ---
    sc_geo = team_scenario("TEAM_GEO_CHANNEL_A")
    # однократное применение: только variable_price_multiplier (2038–2039 ×1.2)
    r_geo = run_plan(case, plan, Scenario(
        scenario_id=sc_geo.scenario_id,
        status=sc_geo.status,
        label_ru=sc_geo.label_ru,
        variable_price_multiplier=sc_geo.variable_price_multiplier,
        notes=list(sc_geo.notes),
    ))
    price_a_eff = {y: r_geo.case.effective_price_mln_per_t[("A", y)]
                   for y in range(2035, 2041)}

    # --- 3. восстановление контрольных цен ---
    r_restored = run_plan(base_case(), base_plan(), base_scenario())
    price_a_restored = base_case().source("A").variable_cost_mln_per_t
    hashes_after = file_hashes()

    same_yearly = (yearly_row(r_before) == yearly_row(r_restored))
    same_fin = (finance_row(r_before) == finance_row(r_restored))
    restoration_ok = (
        same_yearly and same_fin
        and abs(price_a_restored - price_a_before) < 1e-12
        and hashes_before == hashes_after
    )

    # --- 4. стороны эффекта ---
    pay_before = channel_payments(r_before, plan, "A")
    pay_geo = channel_payments(r_geo, plan, "A")
    parties = []
    for y in range(2035, 2041):
        parties.append({
            "year": y,
            "price_A_before": round(r_before.case.effective_price_mln_per_t[("A", y)], 4),
            "price_A_geo": round(price_a_eff[y], 4),
            "payments_A_before_mln": round(pay_before[y], 2),
            "payments_A_geo_mln": round(pay_geo[y], 2),
            "delta_provider_A_mln": round(pay_geo[y] - pay_before[y], 2),
        })
    write_csv(os.path.join(OUT, "P05_parties.csv"), list(parties[0].keys()), parties)

    delta_provider = round(sum(p["delta_provider_A_mln"] for p in parties), 2)
    delta_pv = round(pv_of(r_geo) - pv_of(r_before), 2)

    # --- 5. combined (явно объявленный, отдельный сценарий) ---
    sc_m = mandatory_scenario()
    combined = Scenario(
        scenario_id="TEAM_GEO_A_MANDATORY_COMBINED",
        status="TEAM_ASSUMPTION",
        demand_multiplier=dict(sc_m.demand_multiplier),
        critical_demand_multiplier=dict(sc_m.critical_demand_multiplier),
        variable_price_multiplier={
            "Earth-Core": {"2038": 1.25 * 1.20, "2039": 1.25 * 1.20},
            "Earth-Flex": {"2038": 1.25, "2039": 1.25},
        },
        actual_delivery_share=dict(sc_m.actual_delivery_share),
        loss_ceiling=dict(sc_m.loss_ceiling),
        notes=[
            "COMBINED: mandatory ×1.25 и geo ×1.20 применены к цене A 2038-2039 "
            "РОВНО ПО ОДНОМУ РАЗУ (6.2×1.25×1.20=9.30); B только ×1.25; "
            "спрос/D/потолок — из MANDATORY_STRESS (CASE_INPUT, без изменений)",
        ],
    )
    r_mand = run_plan(case, plan, sc_m)
    r_comb = run_plan(case, plan, combined)

    # правило «не начисляется дважды»: цена A 2038 = 9.30, не 11.16
    price_ok = abs(r_comb.case.effective_price_mln_per_t[("A", 2038)] - 6.2 * 1.5) < 1e-9

    # --- выгрузки ---
    all_runs = [("BASE", r_before), ("TEAM_GEO_CHANNEL_A", r_geo),
                ("MANDATORY_STRESS", r_mand),
                ("TEAM_GEO_A_MANDATORY_COMBINED", r_comb)]
    yearly_rows = []
    for tag, r in all_runs:
        yearly_rows += [{"run": tag, **y} for y in yearly_row(r)]
    write_csv(os.path.join(OUT, "P05_yearly_balance.csv"),
              ["run"] + list(yearly_row(r_before)[0].keys()), yearly_rows)
    fin_rows = []
    for tag, r in all_runs:
        fin_rows += [{"run": tag, **fr} for fr in finance_row(r)]
    write_csv(os.path.join(OUT, "P05_financial_breakdown.csv"),
              ["run"] + list(finance_row(r_before)[0].keys()), fin_rows)

    summary = {
        "base": {"total_mln": round(total_cost_of(r_before), 2),
                 "pv_mln": round(pv_of(r_before), 2),
                 "shortage_t": round(shortage_of(r_before), 3),
                 "min_sl_total": round(min_sl_total(r_before), 4),
                 "violations": len(violation_signature(r_before))},
        "geo": {"total_mln": round(total_cost_of(r_geo), 2),
                "pv_mln": round(pv_of(r_geo), 2),
                "shortage_t": round(shortage_of(r_geo), 3),
                "min_sl_total": round(min_sl_total(r_geo), 4),
                "violations": len(violation_signature(r_geo)),
                "new_violations_vs_base": len(
                    violation_signature(r_geo) - violation_signature(r_before))},
        "mandatory": {"total_mln": round(total_cost_of(r_mand), 2),
                      "pv_mln": round(pv_of(r_mand), 2),
                      "shortage_t": round(shortage_of(r_mand), 3),
                      "min_sl_total": round(min_sl_total(r_mand), 4)},
        "combined": {"total_mln": round(total_cost_of(r_comb), 2),
                     "pv_mln": round(pv_of(r_comb), 2),
                     "shortage_t": round(shortage_of(r_comb), 3),
                     "min_sl_total": round(min_sl_total(r_comb), 4),
                     "price_A_2038": round(
                         r_comb.case.effective_price_mln_per_t[("A", 2038)], 4),
                     "no_double_count_ok": price_ok},
        "delta_geo_vs_base": {
            "d_total_mln": round(total_cost_of(r_geo) - total_cost_of(r_before), 2),
            "d_pv_mln": delta_pv,
            "d_shortage_t": 0.0,
            "d_sl": 0.0,
            "delta_provider_A_revenue_mln": delta_provider,
        },
        "restoration": {
            "yearly_identical": same_yearly,
            "finance_identical": same_fin,
            "price_A_restored": price_a_restored,
            "file_hashes_identical": hashes_before == hashes_after,
            "ok": restoration_ok,
        },
    }
    write_json(os.path.join(OUT, "P05_summary.json"), summary)

    # --- экспорт параметров события ---
    write_json(os.path.join(OUT, "geo_event.json"), {
        "event_id": "geo_channel_a_tariff",
        "module": "TEAM_GEO_CHANNEL_A (P05, бонус)",
        "channel": {"source_id": "A", "name": "Earth-Core"},
        "price_type": "variable (агрегированная переменная цена канала)",
        "original_price_mln_per_t": 6.2,
        "multiplier": 1.2,
        "new_price_mln_per_t": {"2038": 7.44, "2039": 7.44},
        "period": "2038-01..2039-12",
        "application": ("variable_price_multiplier сценария — ровно один раз; "
                        "price-override в scenario_parameters YAML дублирует "
                        "событие и НЕ применяется (предотвращение двойного "
                        "начёта; баг конфига — REPORT_wave2 §Баги)"),
        "reservation_rate_changed": False,
        "capex_changed": False,
        "other_channels_changed": False,
        "case_input_version_sha256": hashes_before,
        "input_diff": {
            "effective_price_mln_per_t": {
                f"A/{y}": {"before": round(
                    r_before.case.effective_price_mln_per_t[("A", y)], 4),
                    "after": round(price_a_eff[y], 4)}
                for y in range(2035, 2041)
            }
        },
        "plan_id": plan.plan_id,
        "plan_note": "S10, до FINAL",
        "status": "TEAM_ASSUMPTION (условный бонусный сценарий, не прогноз)",
    })

    write_json(os.path.join(OUT, "P05_meta.json"), meta_block(
        "P05_geopolitics", plan.plan_id,
        extra={"protocol": "P05", "restoration_ok": restoration_ok,
               "no_double_count_ok": price_ok,
               "file_hashes_before": hashes_before,
               "file_hashes_after": hashes_after}))

    print("P05 гео-модуль:")
    print(f"  BASE: total={summary['base']['total_mln']}, PV={summary['base']['pv_mln']}")
    print(f"  GEO : total={summary['geo']['total_mln']}, PV={summary['geo']['pv_mln']} "
          f"(ΔPV={delta_pv:+.1f} млн, Δпоставщика A={delta_provider:+.1f} млн, "
          f"SL/shortage не меняются, новых нарушений="
          f"{summary['geo']['new_violations_vs_base']})")
    print(f"  MAND: total={summary['mandatory']['total_mln']}, "
          f"PV={summary['mandatory']['pv_mln']}")
    print(f"  COMB: total={summary['combined']['total_mln']}, "
          f"PV={summary['combined']['pv_mln']}, цена A 2038="
          f"{summary['combined']['price_A_2038']} (9.30 — без двойного начёта: "
          f"{price_ok})")
    print(f"  Восстановление цен: {'OK' if restoration_ok else 'ОШИБКА'} "
          f"(A={price_a_restored}, файлы не изменились="
          f"{hashes_before == hashes_after})")


if __name__ == "__main__":
    main()
