# -*- coding: utf-8 -*-
"""
WP2 manual_calc — выдача артефактов волны 1:
  1) plans/S01.json…S25.json — черновики планов по plan_format.json
     (топ-5 — полные, с помесячными заказами из прогона; остальные — годовые агрегаты);
     адаптивные S16/S25 — дополнительно ветвь STRESS: S16_STRESS_BRANCH.json и т.п.
  2) reference_values.json — «эталонные числа» для сверки с ядром WP1 в волне 2.
  3) questions_output.txt — числовые ответы Q1–Q8 (дублирует run_questions.py).

Запуск: python run_deliverables.py (после run_screening.py).
"""
from __future__ import annotations

import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from mc_data import load_case, make_base, make_stress, YEARS, m_year
from mc_model import run_plan, reserve_required, EPS
from mc_strategies import build_strategies, make_branch

HERE = os.path.dirname(os.path.abspath(__file__))
WP2_DIR = os.path.abspath(os.path.join(HERE, ".."))
PLANS_DIR = os.path.join(WP2_DIR, "plans")

TOP5 = ["S10", "S14", "S18", "S21", "S25"]

TA_LIST = [
    {"id": "TA-01", "value": 365 / 12, "unit": "дней", "rationale_ru": "длительность месяца 365/12 (равномерный спрос, 365 дней в учебном году)", "scope": "календарь"},
    {"id": "TA-02", "value": 24, "unit": "мес", "rationale_ru": "lead time Earth-New в контрольных расчётах консервативно 24 мес", "scope": "канал C"},
    {"id": "TA-03", "value": "поставка в следующем месяце", "unit": "-", "rationale_ru": "Emergency 42 дня (6 недель) в месячной сетке", "scope": "канал E"},
    {"id": "TA-04", "value": "M+L месяцев", "unit": "-", "rationale_ru": "конвенция: заказ в месяце M → поставка в M+L", "scope": "все каналы"},
    {"id": "TA-05", "value": 1, "unit": "мес", "rationale_ru": "ZBO вводится в месяц, следующий за месяцем платежа", "scope": "ZBO"},
    {"id": "TA-06", "value": 0.10, "unit": "доля (реальная)", "rationale_ru": "ставка дисконтирования, t0=2035 (Sommariva et al. 2023, WACC 11.5–13%, округление для консерватизма)", "scope": "финансы"},
    {"id": "TA-07", "value": "конец года", "unit": "-", "rationale_ru": "момент дисконтирования — потоки года приводятся к 31.12", "scope": "финансы"},
    {"id": "TA-08", "value": "среднее (I_start+I_end)/2 по месяцам", "unit": "-", "rationale_ru": "time-weighted средний физический запас для holding cost", "scope": "хранение"},
    {"id": "TA-09", "value": 0.40, "unit": "доля served года", "rationale_ru": "канал E считается базовым при отборе >40% обслуженного спроса года", "scope": "канал E"},
]


def build_plan_json(plan, result, scenario_id: str, detailed: bool) -> dict:
    reservations = []
    for sid, yr_map in sorted(plan.reservations.items()):
        for y in sorted(yr_map):
            if yr_map[y] <= 0:
                continue
            item = {"source_id": sid, "year": y,
                    "reserved_capacity_t_per_year": yr_map[y]}
            first = min(plan.reservations[sid])
            start = plan.start_months.get(sid, 1)
            if y == first and start > 1:
                item["start_month"] = start
            reservations.append(item)

    investments = [{"investment_id": iid, "action": act, "payment_date": dt}
                   for iid, act, dt in plan.investments]

    orders = []
    if detailed:
        for mr in result.months:
            for sid, q in sorted(mr.orders.items()):
                if q > EPS:
                    orders.append({"source_id": sid, "period": mr.period,
                                   "ordered_volume_t": round(q, 3)})
    else:
        annual: dict[tuple[str, int], float] = {}
        for mr in result.months:
            for sid, q in mr.orders.items():
                key = (sid, mr.year)
                annual[key] = annual.get(key, 0.0) + q
        for (sid, y), q in sorted(annual.items()):
            if q > EPS:
                orders.append({"source_id": sid, "period": str(y),
                               "ordered_volume_t": round(q, 2)})

    assumptions = [dict(t) for t in TA_LIST]
    if plan.reserve_target_days != 45.0:
        assumptions.append({
            "id": "TA-10 (кандидат, НЕ утверждён)", "value": plan.reserve_target_days,
            "unit": "дней",
            "rationale_ru": "целевой оперативный запас 60 дней вместо 45 (страховка от внутригодовых шоков); предлагается в REPORT_wave1.md, добавляет только оркестратор",
            "scope": "политика запаса S21"})
    assumptions.append({
        "id": "TD-WP2-01 (TEAM_DECISION)", "value": "demand-chasing + netting коротких каналов",
        "unit": "-",
        "rationale_ru": "политика заказов: непросроченные каналы заказываются в m под поставку m+L (спрос+потери+целевой запас−проекция−забронировано); канал с меньшим lead time, стоящий выше по приоритету, резервирует объём позже (netting); E — реактивный под дефицит следующего месяца",
        "scope": "supply_orders"})
    assumptions.append({
        "id": "TD-WP2-02 (TEAM_DECISION)", "value": plan.buffer_t,
        "unit": "т",
        "rationale_ru": "оперативный буфер сверх 45-дневного резерва (внутригодовая неравномерность, месячная дискретизация)",
        "scope": "inventory_policy"})

    sc = make_stress() if scenario_id == "MANDATORY_STRESS" else make_base()
    inv_policy = {
        "initial_inventory_t": plan.initial_inventory_t,
        "initial_inventory_source": {
            "source_id": plan.initial_inventory_source,
            "order_period": "2034-01",
            "delivery_period": "2035-01",
            "volume_t": plan.initial_inventory_t,
            "paid_in": "2035",
        },
        "reserve_mode": plan.reserve_mode,
        "target_month_end_inventory_t": round(
            reserve_required(load_case(), sc, 2040, plan.reserve_target_days) + plan.buffer_t, 1),
    }
    if plan.reserve_target_days != 45.0:
        inv_policy["target_month_end_inventory_t"] = round(
            reserve_required(load_case(), sc, 2040, plan.reserve_target_days) + plan.buffer_t, 1)

    decisions = {
        "supply_orders": orders,
        "capacity_reservations": reservations,
        "investments": investments,
        "inventory_policy": inv_policy,
    }
    if plan.reserve_mode == "contractual_emergency":
        decisions["emergency_contract"] = {
            "reserved_capacity_t_per_year": 80.0,
            "activation_lead_days": 42,
            "coverage_volume_t": 9.2,
            "notes_ru": ("E-мощность 80 т/год доставляет за 42 дня лишь 80×42/365=9.2 т при спросе "
                         "за 42 дня 11.5 т (2035) … 44.9 т (2040 BASE) / 51.6 т (2040 STRESS) — "
                         "контракт НЕ доказывает эквивалентность 45-дневному резерву "
                         "(нарушения RESERVE_45D показаны численно в constraint_checks)."),
        }

    suffix = ""
    if plan.adaptive:
        suffix = "_STRESS_BRANCH" if scenario_id == "MANDATORY_STRESS" else "_BASE_BRANCH"
    return {
        "plan_id": plan.plan_id + suffix,
        "scenario_id": scenario_id,
        "version": "wave1-draft-1.0",
        "decisions": decisions,
        "assumptions": assumptions,
    }


def main() -> None:
    case = load_case()
    base, stress = make_base(), make_stress()
    os.makedirs(PLANS_DIR, exist_ok=True)
    plans = build_strategies()

    ref_values = []
    for plan in plans:
        sid = plan.plan_id
        detailed = sid in TOP5
        for scn in (base, stress):
            eff = make_branch(plan, scn.scenario_id) if plan.adaptive else plan
            r = run_plan(case, scn, eff)
            detailed_here = detailed  # топ-5 — полные планы в обоих сценариях
            j = build_plan_json(eff, r, scn.scenario_id, detailed_here)
            if scn.scenario_id == "BASE":
                fname = f"{sid}.json"
            elif plan.adaptive:
                fname = f"{sid}_STRESS_BRANCH.json"
            elif detailed:
                fname = f"{sid}_STRESS.json"
            else:
                fname = None
            if fname:
                with open(os.path.join(PLANS_DIR, fname), "w", encoding="utf-8") as f:
                    json.dump(j, f, ensure_ascii=False, indent=2)
            # эталонные числа — топ-5 в обоих сценариях + контроли (S11 потери, S16/S17/S19/S22)
            if sid in TOP5 or (scn.scenario_id == "BASE" and sid in ["S11", "S16", "S17", "S19", "S22"]):
                y2040 = r.years[2040]
                ref_values.append({
                    "plan_id": sid, "scenario_id": scn.scenario_id,
                    "total_pv_mln": round(r.total_pv, 2),
                    "total_cost_mln": round(r.total_cost, 2),
                    "year_2040": {
                        "procurement_mln": round(y2040.procurement, 2),
                        "reservation_mln": round(y2040.reservation, 2),
                        "holding_mln": round(y2040.holding, 2),
                        "fixed_opex_mln": round(y2040.fixed_opex, 2),
                        "total_mln": round(y2040.total, 2),
                        "served_total_t": round(y2040.served_total, 2),
                        "sl_total": round(y2040.sl_total, 4),
                        "i_start_jan_t": round(y2040.i_start_jan, 2),
                    },
                    "capex_cum_2037_mln": round(r.capex_2037, 2),
                    "min_sl_total": round(r.min_sl_total, 4),
                    "min_sl_critical": round(r.min_sl_critical, 4),
                    "total_shortage_t": round(r.total_shortage, 2),
                })
        print(f"  {sid}: планы записаны" + (" (2 ветви)" if plan.adaptive else ""))

    with open(os.path.join(HERE, "reference_values.json"), "w", encoding="utf-8") as f:
        json.dump({"description_ru": "Эталонные числа WP2 волны 1 для сверки с ядром WP1 в волне 2 (независимый ручной расчёт, r=0.10, t0=2035, конвенции TA-01…TA-09)",
                   "values": ref_values}, f, ensure_ascii=False, indent=2)
    print(f"\nreference_values.json записан ({len(ref_values)} записей).")
    print(f"plans/ → {PLANS_DIR}")


if __name__ == "__main__":
    main()
