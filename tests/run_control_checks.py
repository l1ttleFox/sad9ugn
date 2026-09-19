"""Скрипт-прогон контрольных векторов V01–V10 (validation/control_cases.md).

Запуск:  python tests/run_control_checks.py
Вывод:   таблица «case / expected / actual / OK?» — для защиты и README.

Значения ожиданий читаются из tests/validation/expected_checks.json
(CASE_INPUT организатора). Векторы проверяют арифметику и семантику ядра:
V01 баланс, V02 shortage ≠ отрицательный запас, V03 take-or-pay,
V04 нет второго TOP-платежа, V05 прората резервирования, V06 потери один
раз, V07 резерв 45 дней, V08 CAPACITY_EXCEEDED, V09 вложенность
критического спроса, V10 стресс-доля без повторного reliability.
"""

from __future__ import annotations

import dataclasses
import json
import os
import sys

# Windows-консоль может иметь cp1251 — переключаем вывод в UTF-8.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
if os.path.join(REPO_ROOT, "tests") not in sys.path:
    sys.path.insert(0, os.path.join(REPO_ROOT, "tests"))

from src.engine import (  # noqa: E402
    CapacityReservation,
    InitialInventorySource,
    calculate_deliveries,
    calculate_inventory,
    calculate_service,
    load_case,
    plan_from_dict,
    reserve_required_t,
    validate_plan,
)
from test_engine_wave1 import (  # noqa: E402
    deliveries_from,
    make_plan,
    make_synthetic_case,
)

EXPECTED_PATH = os.path.join(REPO_ROOT, "tests", "validation", "expected_checks.json")


def _expected(case_id: str) -> dict:
    with open(EXPECTED_PATH, "r", encoding="utf-8") as f:
        for c in json.load(f):
            if c["case_id"] == case_id:
                return c["expected"]
    raise SystemExit(f"Вектор {case_id} не найден в expected_checks.json")


def _close(a: float, b: float, eps: float = 1e-6) -> bool:
    return abs(float(a) - float(b)) <= eps


def v01() -> tuple[bool, str]:
    """Материальный баланс: 10 + 30 − 2 − 25 = 13."""
    exp = _expected("V01")
    case = make_synthetic_case(demand_by_year={2035: (300.0, 0.0)},
                               base_loss_rate=2.0 / 30.0)
    plan = make_plan(initial_inventory_t=10.0)
    inv = calculate_inventory(case, plan, deliveries_from({"2035-01": 30.0}))
    row = inv.monthly_balance[0]
    got = row.i_end_t
    return _close(got, exp["closing_inventory_t"]), f"closing={got}"


def v02() -> tuple[bool, str]:
    """Дефицит — отдельная метрика; запас не уходит в минус."""
    exp = _expected("V02")
    case = make_synthetic_case(demand_by_year={2035: (120.0, 0.0)}, base_loss_rate=0.0)
    plan = make_plan()
    inv = calculate_inventory(case, plan, deliveries_from({"2035-01": 8.0}))
    row = inv.monthly_balance[0]
    ok = (_close(row.served_total_t, exp["served_t"])
          and _close(row.shortage_t, exp["shortage_t"])
          and _close(row.i_end_t, exp["closing_inventory_t"])
          and all(m.i_end_t >= 0 for m in inv.monthly_balance))
    return ok, f"served={row.served_total_t}, shortage={row.shortage_t}, closing={row.i_end_t}"


def v03() -> tuple[bool, str]:
    """Take-or-pay: max(50, 0.70×100) = 70 → 70×2 = 140."""
    exp = _expected("V03")
    case = make_synthetic_case()
    case.supply_sources = [
        dataclasses.replace(s, variable_cost_mln_per_t=2.0,
                            reservation_rate_mln_per_t_year_capacity=0.0)
        if s.source_id == "A" else s
        for s in case.supply_sources
    ]
    for d in case.demand:
        case.effective_price_mln_per_t[("A", d.year)] = 2.0
    plan = make_plan(orders=[("A", "2035", 50.0)], reservations=[("A", 2035, 100.0)])
    from src.engine import calculate_costs
    d = calculate_deliveries(case, plan)
    inv = calculate_inventory(case, plan, d)
    costs = calculate_costs(case, plan, d, inv)
    r = costs.financial_breakdown[0]
    q_pay = 70.0  # max(50, 0.7×100)
    ok = _close(r.procurement_mln, exp["variable_payment_mln"])
    return ok, f"payable={q_pay}, payment={r.procurement_mln}"


def v04() -> tuple[bool, str]:
    """TOP не начисляется дважды: платёж остаётся 140."""
    exp = _expected("V04")
    ok, detail = v03()
    case = make_synthetic_case()
    case.supply_sources = [
        dataclasses.replace(s, variable_cost_mln_per_t=2.0,
                            reservation_rate_mln_per_t_year_capacity=0.0)
        if s.source_id == "A" else s
        for s in case.supply_sources
    ]
    for d in case.demand:
        case.effective_price_mln_per_t[("A", d.year)] = 2.0
    plan = make_plan(orders=[("A", "2035", 50.0)], reservations=[("A", 2035, 100.0)])
    from src.engine import calculate_costs
    d = calculate_deliveries(case, plan)
    inv = calculate_inventory(case, plan, d)
    costs = calculate_costs(case, plan, d, inv)
    r = costs.financial_breakdown[0]
    ok = _close(r.procurement_mln, exp["variable_payment_mln"]) and _close(r.total_mln, 140.0)
    return ok, f"payment={r.procurement_mln}, total={r.total_mln} (без второго TOP)"


def v05() -> tuple[bool, str]:
    """Прората резервирования: 100 × 0.4 × 0.5 = 20."""
    exp = _expected("V05")
    case = make_synthetic_case()
    case.supply_sources = [
        dataclasses.replace(s, reservation_rate_mln_per_t_year_capacity=0.4)
        if s.source_id == "B" else s
        for s in case.supply_sources
    ]
    plan = make_plan()
    plan.decisions.capacity_reservations = [
        CapacityReservation(source_id="B", year=2035,
                            reserved_capacity_t_per_year=100.0, start_month=7)
    ]
    from src.engine import calculate_costs
    d = calculate_deliveries(case, plan)
    inv = calculate_inventory(case, plan, d)
    costs = calculate_costs(case, plan, d, inv)
    got = costs.financial_breakdown[0].reservation_mln
    return _close(got, exp["reservation_payment_mln"]), f"reservation={got}"


def v06() -> tuple[bool, str]:
    """Потери = throughput × loss_rate, один раз: 20 × 0.05 = 1."""
    exp = _expected("V06")
    case = make_synthetic_case(base_loss_rate=0.05)
    plan = make_plan()
    inv = calculate_inventory(case, plan, deliveries_from({"2035-03": 20.0}))
    mar = next(m for m in inv.monthly_balance if m.period == "2035-03")
    apr = next(m for m in inv.monthly_balance if m.period == "2035-04")
    ok = _close(mar.losses_t, exp["losses_t"]) and _close(apr.losses_t, 0.0)
    return ok, f"losses(Mar)={mar.losses_t}, losses(Apr)={apr.losses_t}"


def v07() -> tuple[bool, str]:
    """Резерв 45 дней: 365 × 45/365 = 45."""
    exp = _expected("V07")
    got = reserve_required_t(365.0)
    return _close(got, exp["reserve_t"]), f"reserve={got}"


def v08() -> tuple[bool, str]:
    """CAPACITY_EXCEEDED: reserved 12 > capacity 10, excess 2."""
    exp = _expected("V08")
    case = make_synthetic_case()
    case.supply_sources = [
        dataclasses.replace(s, capacity_t_per_year=10.0)
        if s.source_id == "A" else s
        for s in case.supply_sources
    ]
    plan = make_plan(reservations=[("A", 2035, 12.0)])
    violations = validate_plan(plan, case)
    cap = [v for v in violations if v.rule_id == exp["violation"]]
    if not cap:
        return False, f"нарушение {exp['violation']} не найдено"
    ok = _close(cap[0].excess, exp["excess_t"])
    return ok, f"rule={cap[0].rule_id}, excess={cap[0].excess}"


def v09() -> tuple[bool, str]:
    """Критический спрос вложен в общий: total = 100 при critical = 60."""
    exp = _expected("V09")
    case = make_synthetic_case(demand_by_year={2035: (1200.0, 720.0)}, base_loss_rate=0.0)
    plan = make_plan(initial_inventory_t=80.0)
    inv = calculate_inventory(case, plan, deliveries_from({}))
    row = inv.monthly_balance[0]
    ok = (_close(row.demand_total_t, exp["total_demand_t"])
          and _close(row.demand_critical_t, 60.0))
    return ok, f"total={row.demand_total_t}, critical={row.demand_critical_t}"


def v10() -> tuple[bool, str]:
    """Стресс-доля применяется один раз: 20 × 0.5 = 10, без reliability 0.8."""
    exp = _expected("V10")
    case = make_synthetic_case()
    # Синтетический канал B с мощностью 240 т/год, чтобы месячный заказ 20 т
    # не ограничивался долей резерва (лимит = 240/12 = 20).
    case.supply_sources = [
        dataclasses.replace(s, capacity_t_per_year=240.0)
        if s.source_id == "B" else s
        for s in case.supply_sources
    ]
    # «mandatory-like» фактическая доля 0.50 (сценарное поле).
    case.actual_delivery_share[("B", 2035)] = 0.50
    plan = make_plan(
        orders=[("B", "2035-01", 20.0)],
        reservations=[("B", 2035, 240.0)],
    )
    res = calculate_deliveries(case, plan)
    # lead time B — 4 мес: заказ 2035-01 → поставка 2035-05
    planned = res.planned_by_source_period.get(("B", "2035-05"), None)
    got = res.actual_by_source_period.get(("B", "2035-05"), None)
    if got is None:
        return False, "поставка B не найдена"
    ok = _close(planned, 20.0) and _close(got, exp["actual_delivery_t"])
    return ok, f"planned={planned}, actual={got} (не 20×0.5×0.8=8)"


CHECKS = [
    ("V01", "материальный баланс", v01),
    ("V02", "shortage ≠ отрицательный запас", v02),
    ("V03", "take-or-pay минимум", v03),
    ("V04", "нет второго TOP-платежа", v04),
    ("V05", "прората резервирования", v05),
    ("V06", "потери один раз на throughput", v06),
    ("V07", "резерв 45 дней", v07),
    ("V08", "CAPACITY_EXCEEDED", v08),
    ("V09", "критический вложен в общий", v09),
    ("V10", "стресс-доля без reliability", v10),
]


def main() -> int:
    print("=" * 78)
    print("Контрольные векторы V01–V10 (tests/validation/expected_checks.json)")
    print("=" * 78)
    n_ok = 0
    for cid, label, fn in CHECKS:
        try:
            ok, actual = fn()
        except Exception as e:  # noqa: BLE001
            ok, actual = False, f"ОШИБКА: {e}"
        n_ok += int(ok)
        exp = _expected(cid)
        exp_str = json.dumps(exp, ensure_ascii=False)
        print(f"{cid:4s} | {label:34s} | expected: {exp_str:48s} | actual: {actual:52s} | {'OK' if ok else 'FAIL'}")
    print("-" * 78)
    print(f"ИТОГ: {n_ok}/{len(CHECKS)} OK")
    return 0 if n_ok == len(CHECKS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
