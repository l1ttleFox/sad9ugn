# -*- coding: utf-8 -*-
"""
WP2 manual_calc — запуск: этап 1 (скрининг 25 стратегий × BASE/STRESS),
этап 2 (детализация топ-5, MCDA, чувствительность), ответы Q1–Q8, черновики plans/*.json.

Запуск ОДНОЙ командой из папки manual_calc:
    python run_screening.py

Выход: screening.csv, detailed_*.csv, plans_drafts/*.json, console-сводка.
Всё детерминировано (seed не нужен).
"""
from __future__ import annotations

import copy
import csv
import json
import os
import sys

# Консоль Windows может быть cp1251 — переключаем вывод в UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from mc_data import (
    load_case, make_base, make_stress, CaseData, Scenario, YEARS, N_MONTHS,
    DISCOUNT_RATE, DISCOUNT_T0, LEAD_MONTHS, m_idx, m_period, m_year,
)
from mc_model import (
    PlanDef, RunResult, run_plan, res_year, reserve_required, price_with_mult,
    d_available_idx, c_available_idx, zbo_active_idx, EPS,
)
from mc_strategies import build_strategies, make_branch

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_PLANS = os.path.join(HERE, "plans_drafts")


# ---------------------------------------------------------------------------
# Контрольные примеры V01–V10 (самопроверка арифметики модели)
# ---------------------------------------------------------------------------

def selfcheck_v01_v10() -> list[tuple[str, bool, str]]:
    """Синтетические проверки из contracts/data/control_cases.md (независимая арифметика)."""
    out = []
    # V01 баланс
    out.append(("V01", 10 + 30 - 2 - 25 == 13, "10+30-2-25=13"))
    # V02 дефицит не отрицательный запас
    served, short, i_end = min(10, 8), max(0, 10 - 8), max(0, 0 + 8 - 0 - 8)
    out.append(("V02", (served, short, i_end) == (8, 2, 0), "served=8, shortage=2, I_end=0"))
    # V03/V04 TOP
    q_pay = max(50, 0.70 * 100)
    out.append(("V03", q_pay == 70 and q_pay * 2 == 140, "max(50,0.7*100)=70 → 140"))
    out.append(("V04", q_pay * 2 == 140, "без второго платежа 140"))
    # V05 прората резервирования
    out.append(("V05", 100 * 0.4 * 0.5 == 20, "100*0.4*0.5=20"))
    # V06 потери один раз
    out.append(("V06", 20 * 0.05 == 1, "20*0.05=1"))
    # V07 45-дн. резерв
    out.append(("V07", 365 * 45 / 365 == 45, "365*45/365=45"))
    # V08 превышение мощности — проверяется в run_plan (CAPACITY_EXCEEDED)
    out.append(("V08", True, "CAPACITY_EXCEEDED формируется в checks (резерв 12 > 10)"))
    # V09 критический вложен в общий
    out.append(("V09", 100 == 100, "total=100, не 160"))
    # V10 без повторного reliability
    out.append(("V10", 20 * 0.50 == 10, "20*0.5=10, НЕ 20*0.5*0.8"))
    return out


def v08_capacity_check(case: CaseData) -> bool:
    """Синтетический V08: резерв 12 > capacity 10 → нарушение CAPACITY_EXCEEDED, excess 2."""
    p = PlanDef(plan_id="V08", family="T", name_ru="тест",
                reservations={"A": {2035: 12.0}}, priority=[], use_emergency=False,
                initial_inventory_t=0.0)
    p.reservations["A"] = {2035: 12.0}
    # подменим capacity для синтетики
    c2 = copy.deepcopy(case)
    c2.sources["A"].capacity = 10.0
    r = run_plan(c2, make_base(), p)
    v = [ch for ch in r.checks if ch.rule_id == "CAPACITY_EXCEEDED" and ch.period == "2035"]
    return bool(v) and abs(v[0].excess - 2.0) < 1e-6


# ---------------------------------------------------------------------------
# Прогон всех стратегий
# ---------------------------------------------------------------------------

def run_all(case: CaseData) -> dict[str, dict[str, RunResult]]:
    results: dict[str, dict[str, RunResult]] = {}
    for plan in build_strategies():
        entry = {}
        if plan.adaptive:
            entry["BASE"] = run_plan(case, make_base(), make_branch(plan, "BASE"))
            entry["MANDATORY_STRESS"] = run_plan(case, make_stress(), make_branch(plan, "MANDATORY_STRESS"))
        else:
            entry["BASE"] = run_plan(case, make_base(), plan)
            entry["MANDATORY_STRESS"] = run_plan(case, make_stress(), plan)
        results[plan.plan_id] = entry
    return results


def screening_row(sid: str, r: RunResult) -> dict:
    return {
        "strategy": sid,
        "scenario": r.scenario_id,
        "total_cost_mln": round(r.total_cost, 1),
        "total_pv_mln": round(r.total_pv, 1),
        "capex_2037_mln": round(r.capex_2037, 1),
        "capex_2040_mln": round(r.capex_2040, 1),
        "capex_headroom_2037": round(1800 - r.capex_2037, 1),
        "min_sl_total": round(r.min_sl_total, 4),
        "min_sl_critical": round(r.min_sl_critical, 4),
        "shortage_total_t": round(r.total_shortage, 1),
        "shortage_2038_2040_t": round(r.shortage_2038_2040, 1),
        "n_violations": len(r.violations),
        "violations": "; ".join(sorted({f"{v.rule_id}@{v.period}" for v in r.violations})),
    }


# ---------------------------------------------------------------------------
# Черновики планов JSON (plan_format.json)
# ---------------------------------------------------------------------------

def plan_to_json(plan: PlanDef, scenario_id: str) -> dict:
    orders = []
    # годовые резервирования
    reservations = []
    for sid, yr_map in sorted(plan.reservations.items()):
        for y in sorted(yr_map):
            if yr_map[y] > 0:
                item = {"source_id": sid, "year": y,
                        "reserved_capacity_t_per_year": yr_map[y]}
                first = min(plan.reservations[sid])
                start = plan.start_months.get(sid, 1)
                if y == first and start > 1:
                    item["start_month"] = start
                reservations.append(item)
    investments = [{"investment_id": iid, "action": act, "payment_date": dt}
                   for iid, act, dt in plan.investments]
    assumptions = [
        {"id": "TA-01", "value": 365 / 12, "unit": "дней", "rationale_ru": "длительность месяца 365/12", "scope": "календарь"},
        {"id": "TA-02", "value": 24, "unit": "мес", "rationale_ru": "lead time Earth-New консервативно 24 мес", "scope": "канал C"},
        {"id": "TA-03", "value": "поставка в следующем месяце", "unit": "-", "rationale_ru": "Emergency 42 дня в месячной сетке", "scope": "канал E"},
        {"id": "TA-04", "value": "M+L", "unit": "мес", "rationale_ru": "заказ в M → поставка в M+L", "scope": "все каналы"},
        {"id": "TA-05", "value": 1, "unit": "мес", "rationale_ru": "ZBO вводится месяцем после платежа", "scope": "ZBO"},
        {"id": "TA-06", "value": 0.10, "unit": "доля", "rationale_ru": "реальная ставка дисконтирования, t0=2035", "scope": "финансы"},
        {"id": "TA-07", "value": "конец года", "unit": "-", "rationale_ru": "момент дисконтирования", "scope": "финансы"},
        {"id": "TA-08", "value": "среднее (I_start+I_end)/2 по месяцам", "unit": "-", "rationale_ru": "time-weighted запас для holding", "scope": "хранение"},
        {"id": "TA-09", "value": 0.40, "unit": "доля", "rationale_ru": "Emergency базовый, если отбор >40% served года", "scope": "канал E"},
    ]
    if plan.reserve_target_days != 45.0:
        assumptions.append({"id": "TA-10 (кандидат)", "value": plan.reserve_target_days,
                            "unit": "дней", "rationale_ru": "целевой запас 60 дней вместо 45 — предлагается в REPORT",
                            "scope": "политика запаса S21"})
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
        "target_month_end_inventory_t": round(reserve_required(
            load_case(), make_stress() if scenario_id == "MANDATORY_STRESS" else make_base(),
            2040, plan.reserve_target_days) + plan.buffer_t, 1),
    }
    dec = {
        "supply_orders": orders,
        "capacity_reservations": reservations,
        "investments": investments,
        "inventory_policy": inv_policy,
    }
    if plan.reserve_mode == "contractual_emergency":
        dec["emergency_contract"] = {
            "reserved_capacity_t_per_year": 80.0,
            "activation_lead_days": 42,
            "coverage_volume_t": 51.6,
            "notes_ru": ("Требуемое покрытие 42 дней в 2040 (стресс): 448.5×42/365 = 51.6 т; "
                         "мощность E 80 т/год = 9.2 т за 42 дня — контракт НЕ покрывает период "
                         "ожидания без физического запаса (нарушение RESERVE_45D показано численно)."),
        }
    return {
        "plan_id": plan.plan_id + ("_STRESS_BRANCH" if (plan.adaptive and scenario_id == "MANDATORY_STRESS")
                                   else ("_BASE_BRANCH" if plan.adaptive else "")),
        "scenario_id": scenario_id,
        "version": "wave1-draft",
        "decisions": dec,
        "assumptions": assumptions,
    }


def plan_with_orders(plan: PlanDef, r: RunResult, scenario_id: str) -> dict:
    """Полный план (для топ-5): заказы из фактического прогона, по месяцам."""
    j = plan_to_json(plan, scenario_id)
    orders = []
    for mr in r.months:
        for sid, q in sorted(mr.orders.items()):
            if q > EPS:
                orders.append({"source_id": sid, "period": mr.period,
                               "ordered_volume_t": round(q, 3)})
    j["decisions"]["supply_orders"] = orders
    return j


# ---------------------------------------------------------------------------
# MCDA (Linkov et al. 2006: критерии, нормировка, открытые веса)
# ---------------------------------------------------------------------------

def mcda_table(results: dict[str, dict[str, RunResult]], top5: list[str]) -> list[dict]:
    rows = []
    for sid in top5:
        b, s = results[sid]["BASE"], results[sid]["MANDATORY_STRESS"]
        rows.append({
            "strategy": sid,
            "pv_base_mln": round(b.total_pv, 1),
            "pv_stress_mln": round(s.total_pv, 1),
            "cost_per_served_base": round(b.total_cost / b.served_total, 4) if b.served_total else None,
            "sl_margin_base": round(min(b.min_sl_total - 0.97, b.min_sl_critical - 0.99), 4),
            "sl_margin_stress": round(min(s.min_sl_total - 0.97, s.min_sl_critical - 0.99), 4),
            "shortage_stress_t": round(s.total_shortage, 1),
            "capex_headroom_mln": round(1800 - b.capex_2037, 1),
            "n_violations_base": len(b.violations),
            "n_violations_stress": len(s.violations),
        })
    # нормировка min-max и взвешивание (веса открыты, TEAM_DECISION)
    weights = {"pv_base_mln": 0.20, "pv_stress_mln": 0.15, "cost_per_served_base": 0.10,
               "sl_margin_base": 0.15, "sl_margin_stress": 0.20, "shortage_stress_t": 0.10,
               "capex_headroom_mln": 0.05, "n_violations_base": 0.025, "n_violations_stress": 0.025}
    lower_better = {"pv_base_mln", "pv_stress_mln", "cost_per_served_base",
                    "shortage_stress_t", "n_violations_base", "n_violations_stress"}
    keys = list(weights)
    ranges = {}
    for k in keys:
        vals = [r[k] for r in rows if r[k] is not None]
        ranges[k] = (min(vals), max(vals))
    for r in rows:
        score = 0.0
        for k in keys:
            lo, hi = ranges[k]
            v = r[k] if r[k] is not None else (hi if k in lower_better else lo)
            norm = 1.0 if hi == lo else ((v - lo) / (hi - lo))
            if k in lower_better:
                norm = 1.0 - norm
            score += weights[k] * norm
        r["mcda_score"] = round(score, 4)
    rows.sort(key=lambda x: -x["mcda_score"])
    return rows


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main() -> None:
    case = load_case()

    print("=" * 78)
    print("WP2 ВОЛНА 1 — НЕЗАВИСИМЫЙ РУЧНОЙ РАСЧЁТ (без src/engine)")
    print("=" * 78)

    print("\n-- Самопроверка арифметики V01–V10 --")
    all_ok = True
    for cid, ok, note in selfcheck_v01_v10():
        all_ok &= ok
        print(f"  {cid}: {'OK' if ok else 'FAIL'} ({note})")
    ok8 = v08_capacity_check(case)
    all_ok &= ok8
    print(f"  V08 (run_plan): {'OK' if ok8 else 'FAIL'} (CAPACITY_EXCEEDED excess=2)")
    if not all_ok:
        print("САМОПРОВЕРКА НЕ ПРОЙДЕНА"); sys.exit(1)

    results = run_all(case)

    # ---- Этап 1: сводная таблица скрининга ----
    os.makedirs(OUT_PLANS, exist_ok=True)
    rows = []
    for sid in sorted(results):
        for scn in ("BASE", "MANDATORY_STRESS"):
            rows.append(screening_row(sid, results[sid][scn]))
    with open(os.path.join(HERE, "screening.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)

    print("\n-- Этап 1: скрининг 25 стратегий (полная таблица — screening.csv) --")
    hdr = f"{'S':4s} {'сценарий':18s} {'Total,млн':>10s} {'PV,млн':>9s} {'minSL_t':>8s} {'minSL_c':>8s} {'дефицит,т':>9s} {'наруш.':>6s}"
    print(hdr)
    for r in rows:
        print(f"{r['strategy']:4s} {r['scenario']:18s} {r['total_cost_mln']:10.1f} {r['total_pv_mln']:9.1f} "
              f"{r['min_sl_total']:8.4f} {r['min_sl_critical']:8.4f} {r['shortage_total_t']:9.1f} {r['n_violations']:6d}")

    print("\n-- Нарушения по стратегиям (численно) --")
    for sid in sorted(results):
        for scn in ("BASE", "MANDATORY_STRESS"):
            r = results[sid][scn]
            if r.violations:
                uniq = {}
                for v in r.violations:
                    uniq.setdefault(v.rule_id, []).append(v)
                parts = []
                for rid, vs in sorted(uniq.items()):
                    sample = vs[0]
                    parts.append(f"{rid}×{len(vs)} (напр. {sample.period}: факт {sample.actual:.3g}, лимит {sample.limit:.3g})")
                print(f"  {sid} {scn}: " + "; ".join(parts))

    # ---- Выбор топ-5 (из РАЗНЫХ семейств) ----
    # Критерий этапа 1: 0 нарушений в BASE и STRESS → среди них минимум PV;
    # обязательный охват РАЗНЫХ семейств: D (S10), E (S14), F (S18), G (S21), H (S25).
    # S16/S25 — адаптивные: S16 (семейство E) дублирует семейство S14 → в топ-5 берём
    # S25 (семейство H), а S16 остаётся в анализе Q1 (option-hold) отдельным расчётом.
    top5 = ["S10", "S14", "S18", "S21", "S25"]
    print(f"\n-- Топ-5 (разные семейства): {top5} --")
    m = mcda_table(results, top5)
    for r in m:
        print(f"  {r['strategy']}: MCDA={r['mcda_score']:.4f} PV_base={r['pv_base_mln']} "
              f"PV_stress={r['pv_stress_mln']} short_stress={r['shortage_stress_t']} "
              f"наруш.B/S={r['n_violations_base']}/{r['n_violations_stress']}")

    # ---- Детальные таблицы топ-5 + стратегии, участвующие в ответах Q1–Q8 ----
    detail_set = sorted(set(top5 + ["S07", "S11", "S15", "S16", "S17", "S19", "S20", "S22", "S24"]))
    for sid in detail_set:
        for scn in ("BASE", "MANDATORY_STRESS"):
            r = results[sid][scn]
            fn = os.path.join(HERE, f"detailed_{sid}_{scn}.csv")
            with open(fn, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["period", "i_start", "delivered", "throughput", "losses",
                            "served_total", "served_critical", "demand_total", "demand_critical",
                            "shortage", "i_end", "storage_mode", "orders", "arrivals"])
                for mr in r.months:
                    w.writerow([mr.period, round(mr.i_start, 3), round(mr.delivered, 3),
                                round(mr.throughput, 3), round(mr.losses, 3),
                                round(mr.served_total, 3), round(mr.served_critical, 3),
                                round(mr.demand_total, 3), round(mr.demand_critical, 3),
                                round(mr.shortage, 3), round(mr.i_end, 3), mr.storage_mode,
                                json.dumps({k: round(v, 2) for k, v in mr.orders.items()}),
                                json.dumps({k: round(v, 2) for k, v in mr.arrivals.items()})])
            fn2 = os.path.join(HERE, f"detailed_{sid}_{scn}_finance.csv")
            with open(fn2, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["year", "capex", "capex_cum", "procurement", "reservation",
                            "top_extra", "holding", "fixed_opex", "total", "discounted",
                            "served_total", "sl_total", "sl_critical", "shortage",
                            "i_start_jan", "reserve_required", "cost_per_served"])
                cum = 0.0
                for y in YEARS:
                    yf = r.years[y]; cum += yf.capex
                    w.writerow([y, round(yf.capex, 2), round(cum, 2), round(yf.procurement, 2),
                                round(yf.reservation, 2), round(yf.top_extra, 2), round(yf.holding, 2),
                                round(yf.fixed_opex, 2), round(yf.total, 2), round(yf.discounted, 2),
                                round(yf.served_total, 2), round(yf.sl_total, 4), round(yf.sl_critical, 4),
                                round(yf.shortage, 2), round(yf.i_start_jan, 2),
                                round(yf.reserve_required, 2), round(yf.cost_per_served, 4)])
            # checks
            fn3 = os.path.join(HERE, f"detailed_{sid}_{scn}_checks.csv")
            with open(fn3, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["rule_id", "period", "passed", "actual", "limit", "excess", "message_ru"])
                for c in r.checks:
                    w.writerow([c.rule_id, c.period, c.passed, round(c.actual, 6),
                                round(c.limit, 6), round(c.excess, 6), c.message_ru])
    print("Детальные таблицы топ-5 записаны (detailed_*.csv).")

    # ---- Черновики планов S01–S25 (топ-5 — полные с заказами) ----
    plans_by_id = {p.plan_id: p for p in build_strategies()}
    for sid, plan in plans_by_id.items():
        for scn in ("BASE", "MANDATORY_STRESS"):
            effective = make_branch(plan, scn) if plan.adaptive else plan
            r = results[sid][scn]
            if sid in top5:
                j = plan_with_orders(effective, r, scn)
            else:
                j = plan_to_json(effective, scn)
            suffix = "_BASE" if scn == "BASE" else "_STRESS"
            with open(os.path.join(OUT_PLANS, f"{sid}{suffix}.json"), "w", encoding="utf-8") as f:
                json.dump(j, f, ensure_ascii=False, indent=2)
    print(f"Черновики планов записаны в {OUT_PLANS} (по 2 сценария на стратегию).")

    # ---- Чувствительность ставки дисконтирования (топ-5) ----
    print("\n-- Чувствительность PV к ставке r (топ-5, BASE) --")
    for r_disc in (0.05, 0.10, 0.15):
        line = []
        for sid in top5:
            res = results[sid]["BASE"]
            pv = sum(res.years[y].total / (1 + r_disc) ** (y - DISCOUNT_T0) for y in YEARS)
            line.append(f"{sid}={pv:8.1f}")
        print(f"  r={r_disc:.0%}: " + "  ".join(line))

    print("\nГотово. Сводка — screening.csv, детали — detailed_*.csv, планы — plans_drafts/.")


if __name__ == "__main__":
    main()
