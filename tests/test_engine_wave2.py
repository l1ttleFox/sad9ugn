"""Тесты финансового блока WP1 волна 2 (finance.calculate_costs).

Контрольные векторы V03/V04/V05 — tests/validation/expected_checks.json;
ручной пример A-канала (критерий приёмки 3 prompt_wave2.md): резерв 190,
заказ 150, TOP 70% → Q_pay = max(150, 133) = 150 → платёж 150×6.2 = 930,
резервирование 190×0.45 = 85.5; CAPEX EARTH_NEW 90+270=360 (без третьего
платежа); дисконтирование PV = CF/(1.10)^(t−2035); OPEX-прората ZBO/ISRU;
цена STRESS ×1.25 только A/B и только 2038–2039.
"""

from __future__ import annotations

import dataclasses
import json
import os

import pytest

from src.engine import (
    CapacityReservation,
    InitialInventorySource,
    InventoryPolicy,
    Investment,
    Plan,
    PlanDecisions,
    Scenario,
    SupplyOrder,
    apply_scenario,
    calculate_costs,
    calculate_deliveries,
    calculate_inventory,
    load_case,
    load_scenario,
    run_plan,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(REPO_ROOT, "data")
CONFIGS_DIR = os.path.join(REPO_ROOT, "configs")
EXPECTED_CHECKS_PATH = os.path.join(REPO_ROOT, "tests", "validation", "expected_checks.json")


def _expected(case_id: str) -> dict:
    with open(EXPECTED_CHECKS_PATH, "r", encoding="utf-8") as f:
        checks = json.load(f)
    for c in checks:
        if c["case_id"] == case_id:
            return c["expected"]
    raise AssertionError(f"Контрольный вектор {case_id} не найден в expected_checks.json")


# Синтетический кейс волны 1 (значения CASE_INPUT) — импорт из wave1-тестов
# (pytest добавляет tests/ в sys.path при сборе).
from test_engine_wave1 import make_synthetic_case, make_plan  # noqa: E402


def run_costs(case, plan):
    """Полный контур: deliveries → inventory → costs (как в run_plan)."""
    deliveries = calculate_deliveries(case, plan)
    inventory = calculate_inventory(case, plan, deliveries)
    return calculate_costs(case, plan, deliveries, inventory), deliveries, inventory


def row(costs, year: int):
    for r in costs.financial_breakdown:
        if r.year == year:
            return r
    raise AssertionError(f"Год {year} не найден в financial_breakdown")


# ---------------------------------------------------------------------------
# V03 — минимум take-or-pay: max(50, 0.70×100) = 70; 70×2 = 140
# ---------------------------------------------------------------------------

def test_v03_take_or_pay_minimum():
    expected = _expected("V03")
    case = make_synthetic_case()
    # цена A = 2 млн/т, тариф резервирования 0 (изолируем переменный платёж)
    case.supply_sources = [
        dataclasses.replace(s, variable_cost_mln_per_t=2.0,
                            reservation_rate_mln_per_t_year_capacity=0.0)
        if s.source_id == "A" else s
        for s in case.supply_sources
    ]
    for d in case.demand:
        case.effective_price_mln_per_t[("A", d.year)] = 2.0
    plan = make_plan(
        orders=[("A", "2035", 50.0)],
        reservations=[("A", 2035, 100.0)],
    )
    costs, _, _ = run_costs(case, plan)
    r = row(costs, 2035)
    # Q_pay = max(50, 0.70×100) = 70 → 70×2 = 140
    assert r.procurement_mln == pytest.approx(expected["variable_payment_mln"])
    assert r.reservation_mln == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# V04 — take-or-pay НЕ начисляется дважды (платёж остаётся 140)
# ---------------------------------------------------------------------------

def test_v04_no_double_take_or_pay():
    expected = _expected("V04")
    case = make_synthetic_case()
    case.supply_sources = [
        dataclasses.replace(s, variable_cost_mln_per_t=2.0,
                            reservation_rate_mln_per_t_year_capacity=0.0)
        if s.source_id == "A" else s
        for s in case.supply_sources
    ]
    for d in case.demand:
        case.effective_price_mln_per_t[("A", d.year)] = 2.0
    plan = make_plan(
        orders=[("A", "2035", 50.0)],
        reservations=[("A", 2035, 100.0)],
    )
    costs, _, _ = run_costs(case, plan)
    r = row(costs, 2035)
    # переменный платёж ровно 140, никакого второго TOP-платежа
    assert r.procurement_mln == pytest.approx(expected["variable_payment_mln"])
    # total не содержит 140 дважды (прочие компоненты нулевые: нет CAPEX/OPEX/запаса)
    assert r.total_mln == pytest.approx(140.0)
    # справочная метрика переплаты: 2 × (70 − 50) = 40 — НЕ отдельный платёж
    assert r.take_or_pay_extra_mln == pytest.approx(40.0)


# ---------------------------------------------------------------------------
# V05 — прората резервирования: 100 × 0.4 × 0.5 = 20
# ---------------------------------------------------------------------------

def test_v05_reservation_prorata():
    expected = _expected("V05")
    case = make_synthetic_case()
    case.supply_sources = [
        dataclasses.replace(s, reservation_rate_mln_per_t_year_capacity=0.4)
        if s.source_id == "B" else s
        for s in case.supply_sources
    ]
    # start_month=7 → доля года (13−7)/12 = 0.5
    plan = make_plan(reservations=[("B", 2035, 100.0)])
    plan.decisions.capacity_reservations = [
        CapacityReservation(source_id="B", year=2035,
                            reserved_capacity_t_per_year=100.0, start_month=7)
    ]
    costs, _, _ = run_costs(case, plan)
    r = row(costs, 2035)
    assert r.reservation_mln == pytest.approx(expected["reservation_payment_mln"])


def test_reservation_full_year():
    """Полный год: 100 × 0.4 × 1.0 = 40 (start_month=1)."""
    case = make_synthetic_case()
    case.supply_sources = [
        dataclasses.replace(s, reservation_rate_mln_per_t_year_capacity=0.4)
        if s.source_id == "B" else s
        for s in case.supply_sources
    ]
    plan = make_plan(reservations=[("B", 2035, 100.0)])
    costs, _, _ = run_costs(case, plan)
    assert row(costs, 2035).reservation_mln == pytest.approx(40.0)


# ---------------------------------------------------------------------------
# Критерий приёмки 3 — ручной пример годового платежа канала A
# ---------------------------------------------------------------------------

def test_manual_example_channel_a():
    """Резерв A 190 т/год, заказ 150 т, TOP 70%:
    Q_pay = max(150, 0.7×190=133) = 150 → платёж 150×6.2 = 930;
    резервирование 190×0.45 = 85.5. Итого переменные + резерв = 1015.5."""
    case = make_synthetic_case()
    plan = make_plan(
        orders=[("A", "2035", 150.0)],
        reservations=[("A", 2035, 190.0)],
    )
    costs, _, _ = run_costs(case, plan)
    r = row(costs, 2035)
    assert r.procurement_mln == pytest.approx(150.0 * 6.2)  # 930
    assert r.reservation_mln == pytest.approx(190.0 * 0.45)  # 85.5
    assert r.procurement_mln + r.reservation_mln == pytest.approx(1015.5)
    # TOP не связал: заказ (150) выше минимума (133) → переплата 0
    assert r.take_or_pay_extra_mln == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# TOP — годовой минимум, месячный шаг не создаёт месячных минимумов
# ---------------------------------------------------------------------------

def test_top_period_is_calendar_year():
    """Заказ 10 т одним месяцем при резерве A 190 т/год:
    Q_pay = max(10, 133) = 133 → 133×6.2 = 824.6 (годовой контроль, не помесячно)."""
    case = make_synthetic_case()
    plan = make_plan(
        orders=[("A", "2035-03", 10.0)],
        reservations=[("A", 2035, 190.0)],
    )
    costs, _, _ = run_costs(case, plan)
    r = row(costs, 2035)
    assert r.procurement_mln == pytest.approx(133.0 * 6.2)
    assert r.take_or_pay_extra_mln == pytest.approx((133.0 - 10.0) * 6.2)


def test_top_c_only_after_commissioning():
    """TOP C = 0.50 только с года ввода (exercise + 24 мес, TA-02).

    exercise 2035-06 → C доступен с 2037-06: в 2036 резерв C есть, но
    TOP-минимум не начисляется (канал не введён); в 2037 — начисляется.
    """
    case = make_synthetic_case()
    plan = make_plan(
        reservations=[("C", 2036, 100.0), ("C", 2037, 100.0)],
        investments=[("EARTH_NEW", "exercise_option", "2035-06")],
    )
    costs, _, _ = run_costs(case, plan)
    r36 = row(costs, 2036)
    r37 = row(costs, 2037)
    # 2036: только резервный платёж 100×0.30, TOP-минимума нет
    assert r36.reservation_mln == pytest.approx(30.0)
    assert r36.procurement_mln == pytest.approx(0.0)
    assert r36.take_or_pay_extra_mln == pytest.approx(0.0)
    # 2037: год ввода — TOP 0.5×100 = 50 т → 50×7.1 = 355
    assert r37.procurement_mln == pytest.approx(50.0 * 7.1)
    assert r37.take_or_pay_extra_mln == pytest.approx(50.0 * 7.1)


# ---------------------------------------------------------------------------
# CAPEX: EARTH_NEW 90 + 270 = 360, третьего платежа нет (§12)
# ---------------------------------------------------------------------------

def test_capex_earth_new_profile():
    case = make_synthetic_case()
    plan = make_plan(
        investments=[
            ("EARTH_NEW", "buy_option", "2035-03"),
            ("EARTH_NEW", "exercise_option", "2036-06"),
        ],
    )
    costs, _, _ = run_costs(case, plan)
    assert row(costs, 2035).capex_mln == pytest.approx(90.0)
    assert row(costs, 2036).capex_mln == pytest.approx(270.0)
    # суммарно 360, никакого третьего платежа
    total_capex = sum(r.capex_mln for r in costs.financial_breakdown)
    assert total_capex == pytest.approx(360.0)
    # накопленный итог для лимитов
    assert row(costs, 2036).capex_cumulative_mln == pytest.approx(360.0)
    assert row(costs, 2040).capex_cumulative_mln == pytest.approx(360.0)


def test_capex_lunar_isru_and_zbo():
    case = make_synthetic_case()
    plan = make_plan(
        investments=[
            ("LUNAR_ISRU", "fund_capex", "2037-06"),
            ("ZBO", "fund_capex", "2036-05"),
        ],
    )
    costs, _, _ = run_costs(case, plan)
    assert row(costs, 2037).capex_mln == pytest.approx(1250.0)
    assert row(costs, 2036).capex_mln == pytest.approx(180.0)
    assert row(costs, 2037).capex_cumulative_mln == pytest.approx(1430.0)


# ---------------------------------------------------------------------------
# Фиксированный OPEX: прората ZBO, ISRU с 2038
# ---------------------------------------------------------------------------

def test_fixed_opex_zbo_prorata_midyear():
    """Платёж ZBO 2036-05 → ввод 2036-06 (TA-05): OPEX 2036 = 12×7/12 = 7.0,
    с 2037 — полные 12/год."""
    case = make_synthetic_case()
    plan = make_plan(investments=[("ZBO", "fund_capex", "2036-05")])
    costs, _, _ = run_costs(case, plan)
    assert row(costs, 2035).fixed_opex_mln == pytest.approx(0.0)
    assert row(costs, 2036).fixed_opex_mln == pytest.approx(12.0 * 7.0 / 12.0)
    assert row(costs, 2037).fixed_opex_mln == pytest.approx(12.0)
    assert row(costs, 2040).fixed_opex_mln == pytest.approx(12.0)


def test_fixed_opex_zbo_january_payment():
    """Платёж ZBO 2036-01 → ввод 2036-02: OPEX 2036 = 12×11/12 = 11, с 2037 — 12."""
    case = make_synthetic_case()
    plan = make_plan(investments=[("ZBO", "fund_capex", "2036-01")])
    costs, _, _ = run_costs(case, plan)
    assert row(costs, 2035).fixed_opex_mln == pytest.approx(0.0)
    assert row(costs, 2036).fixed_opex_mln == pytest.approx(11.0)
    assert row(costs, 2037).fixed_opex_mln == pytest.approx(12.0)


def test_zbo_payment_before_2036_no_opex():
    """Платёж ZBO 2035-12 игнорируется для ввода (опция с 2036, TA-05):
    OPEX не начисляется, но сам платёж попадает в CAPEX года платежа."""
    case = make_synthetic_case()
    plan = make_plan(investments=[("ZBO", "fund_capex", "2035-12")])
    costs, _, _ = run_costs(case, plan)
    assert row(costs, 2035).capex_mln == pytest.approx(180.0)
    assert all(r.fixed_opex_mln == pytest.approx(0.0) for r in costs.financial_breakdown)


def test_fixed_opex_isru_from_2038():
    """LUNAR_ISRU профинансирован до 2038 → OPEX +70/год в 2038–2040."""
    case = make_synthetic_case()
    plan = make_plan(investments=[("LUNAR_ISRU", "fund_capex", "2037-06")])
    costs, _, _ = run_costs(case, plan)
    assert row(costs, 2037).fixed_opex_mln == pytest.approx(0.0)
    for y in (2038, 2039, 2040):
        assert row(costs, y).fixed_opex_mln == pytest.approx(70.0)


def test_fixed_opex_isru_not_funded():
    """Без финансирования LUNAR_ISRU OPEX +70/год НЕ начисляется."""
    case = make_synthetic_case()
    plan = make_plan()
    costs, _, _ = run_costs(case, plan)
    assert all(r.fixed_opex_mln == pytest.approx(0.0) for r in costs.financial_breakdown)


# ---------------------------------------------------------------------------
# Хранение: 0.72 × time-weighted средний запас (TA-08)
# ---------------------------------------------------------------------------

def test_holding_cost_constant_inventory():
    """Постоянный запас 12 т весь горизонт: holding = 0.72×12 = 8.64/год."""
    case = make_synthetic_case()
    plan = make_plan(initial_inventory_t=12.0)
    costs, _, _ = run_costs(case, plan)
    for y in range(2035, 2041):
        assert row(costs, y).holding_mln == pytest.approx(0.72 * 12.0)


def test_holding_cost_average_of_monthly_means():
    """Среднее (I_start+I_end)/2 по месяцам: начальный запас 24 т, спрос 24 т/год
    (2 т/мес) → запас линейно падает 24→0; месячные средние 23, 21, …, 1,
    Σ/12 = 12 → holding 2035 = 0.72×12 = 8.64."""
    case = make_synthetic_case(demand_by_year={2035: (24.0, 0.0)})
    plan = make_plan(initial_inventory_t=24.0)
    costs, _, inventory = run_costs(case, plan)
    months = [mb for mb in inventory.monthly_balance if mb.period.startswith("2035")]
    mean = sum((m.i_start_t + m.i_end_t) / 2.0 for m in months) / 12.0
    assert mean == pytest.approx(12.0)
    assert row(costs, 2035).holding_mln == pytest.approx(0.72 * 12.0)
    # с 2036 запас нулевой — хранение 0
    assert row(costs, 2036).holding_mln == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Дисконтирование: PV = CF / (1.10)^(t − 2035), конец года (TA-06/TA-07)
# ---------------------------------------------------------------------------

def test_discounting_manual_example():
    """CAPEX 180 в 2036 и 1250 в 2037: PV2035 = CF2035;
    PV2036 = 180/1.1 = 163.636…; PV2037 = 1250/1.21 = 1033.058…"""
    case = make_synthetic_case()
    plan = make_plan(
        investments=[
            ("ZBO", "fund_capex", "2035-06"),   # 180 в 2035 (ввод ZBO 2035-07 игнорируется: не ранее 2036)
            ("LUNAR_ISRU", "fund_capex", "2037-06"),  # 1250 в 2037
        ],
    )
    # ZBO платёж 2035-06 попадает в CAPEX 2035 (дата платежа), но опция
    # доступна с 2036 — OPEX не начисляется до ввода (zbo_start_index=None).
    costs, _, _ = run_costs(case, plan)
    r35 = row(costs, 2035)
    r37 = row(costs, 2037)
    # 2035: CF = 180 (CAPEX); дисконт (1.1)^0 = 1
    assert r35.total_mln == pytest.approx(180.0)
    assert r35.discounted_mln == pytest.approx(180.0)
    # 2036: потоков нет
    assert row(costs, 2036).total_mln == pytest.approx(0.0)
    # 2037: CF = 1250 → PV = 1250 / 1.1^2
    assert r37.total_mln == pytest.approx(1250.0)
    assert r37.discounted_mln == pytest.approx(1250.0 / 1.21)


def test_discount_factor_by_year():
    """Проверка множителя по годам: ZBO 2038-01 → CAPEX 180 + OPEX 12×11/12 = 11
    (ввод 2038-02); CF2038 = 191 → PV = 191/1.1³."""
    case = make_synthetic_case()
    plan = make_plan(investments=[("ZBO", "fund_capex", "2038-01")])
    costs, _, _ = run_costs(case, plan)
    r = row(costs, 2038)
    assert r.capex_mln == pytest.approx(180.0)
    assert r.fixed_opex_mln == pytest.approx(11.0)
    assert r.total_mln == pytest.approx(191.0)
    assert r.discounted_mln == pytest.approx(191.0 / 1.1**3)


# ---------------------------------------------------------------------------
# STRESS: цена ×1.25 только A/B и только 2038–2039
# ---------------------------------------------------------------------------

def test_stress_price_multiplier_only_ab_2038_2039():
    case = load_case(DATA_DIR)
    stress = load_scenario(os.path.join(CONFIGS_DIR, "mandatory_stress.yaml"))
    eff = apply_scenario(case, stress)
    plan = make_plan(
        orders=[
            ("A", "2038", 100.0), ("B", "2038", 50.0),
            ("A", "2039", 100.0), ("B", "2039", 50.0),
            ("A", "2040", 100.0), ("B", "2040", 50.0),
        ],
        reservations=[
            ("A", 2038, 120.0), ("B", 2038, 60.0),
            ("A", 2039, 120.0), ("B", 2039, 60.0),
            ("A", 2040, 120.0), ("B", 2040, 60.0),
        ],
        plan_id="stress-price-check",
    )
    deliveries = calculate_deliveries(eff, plan)
    inventory = calculate_inventory(eff, plan, deliveries)
    costs = calculate_costs(eff, plan, deliveries, inventory)

    # 2038–2039: A по 6.2×1.25 = 7.75, B по 8.9×1.25 = 11.125.
    # TOP A: 0.7×120 = 84 < 100 → Q_pay = 100. TOP B = 0.
    p38 = 100 * 6.2 * 1.25 + 50 * 8.9 * 1.25
    assert row(costs, 2038).procurement_mln == pytest.approx(p38)
    assert row(costs, 2039).procurement_mln == pytest.approx(p38)
    # 2040: множитель снят — те же объёмы по базовым ценам
    p40 = 100 * 6.2 + 50 * 8.9
    assert row(costs, 2040).procurement_mln == pytest.approx(p40)
    # 2035–2037 заказов нет; TOP A не начисляется (резервов нет)
    assert row(costs, 2035).procurement_mln == pytest.approx(0.0)


def test_stress_does_not_change_reservation_rates():
    """Тарифы резервирования и CAPEX шоком +25% НЕ меняются (notes сценария)."""
    case = load_case(DATA_DIR)
    stress = load_scenario(os.path.join(CONFIGS_DIR, "mandatory_stress.yaml"))
    eff = apply_scenario(case, stress)
    plan = make_plan(
        reservations=[("A", 2038, 190.0)],
        investments=[("ZBO", "fund_capex", "2038-01")],
    )
    deliveries = calculate_deliveries(eff, plan)
    inventory = calculate_inventory(eff, plan, deliveries)
    costs = calculate_costs(eff, plan, deliveries, inventory)
    r = row(costs, 2038)
    assert r.reservation_mln == pytest.approx(190.0 * 0.45)
    assert r.capex_mln == pytest.approx(180.0)
    # TOP A в стрессе: 0.7×190 = 133 → 133 × 6.2 × 1.25 = 1030.75
    assert r.procurement_mln == pytest.approx(133.0 * 6.2 * 1.25)


# ---------------------------------------------------------------------------
# Подготовительный период: начальный запас оплачивается в 2035 (units §3)
# ---------------------------------------------------------------------------

def test_initial_inventory_paid_in_2035():
    """Начальный запас 65 т заказом 2034 у A: переменный платёж 65×6.2 = 403
    включается в 2035 год (вместе с TOP max для A)."""
    case = make_synthetic_case()
    plan = make_plan(
        initial_inventory_t=65.0,
        initial_source=InitialInventorySource(
            source_id="A", order_period="2034-01", delivery_period="2035-01",
            volume_t=65.0, paid_in="2035",
        ),
    )
    costs, _, _ = run_costs(case, plan)
    r = row(costs, 2035)
    # заказов/резервов 2035 нет → Q_pay = 65 (подготовительный объём)
    assert r.procurement_mln == pytest.approx(65.0 * 6.2)
    # в прочие годы платёж не повторяется
    for y in range(2036, 2041):
        assert row(costs, y).procurement_mln == pytest.approx(0.0)


def test_initial_inventory_counts_into_top_max():
    """Подготовительный объём входит в Q_order года для TOP max():
    резерв A 100 (минимум 70), подготовительный заказ 65, годовой заказ 0
    → Q_pay = max(65, 70) = 70 → 70×6.2 = 434 (один раз)."""
    case = make_synthetic_case()
    plan = make_plan(
        reservations=[("A", 2035, 100.0)],
        initial_inventory_t=65.0,
        initial_source=InitialInventorySource(
            source_id="A", order_period="2034-01", delivery_period="2035-01",
            volume_t=65.0, paid_in="2035",
        ),
    )
    costs, _, _ = run_costs(case, plan)
    r = row(costs, 2035)
    assert r.procurement_mln == pytest.approx(70.0 * 6.2)
    assert r.take_or_pay_extra_mln == pytest.approx((70.0 - 65.0) * 6.2)


# ---------------------------------------------------------------------------
# cost_per_served_t_mln
# ---------------------------------------------------------------------------

def test_cost_per_served_and_none_on_zero():
    case = make_synthetic_case(demand_by_year={2035: (24.0, 0.0)})
    plan = make_plan(initial_inventory_t=24.0)
    costs, _, _ = run_costs(case, plan)
    r35 = row(costs, 2035)
    assert r35.cost_per_served_t_mln == pytest.approx(r35.total_mln / 24.0)
    # 2036: спрос 0, served 0 → None (не делить на ноль)
    assert row(costs, 2036).cost_per_served_t_mln is None


# ---------------------------------------------------------------------------
# TotalCost = Procurement + Reservation + Holding + FixedOPEX + CAPEX (§8)
# ---------------------------------------------------------------------------

def test_total_cost_decomposition():
    case = make_synthetic_case(demand_by_year={2036: (12.0, 0.0)})
    plan = make_plan(
        orders=[("A", "2035", 150.0)],
        reservations=[("A", 2035, 190.0)],
        investments=[("ZBO", "fund_capex", "2036-05")],
        initial_inventory_t=10.0,
    )
    costs, _, _ = run_costs(case, plan)
    for r in costs.financial_breakdown:
        assert r.total_mln == pytest.approx(
            r.capex_mln + r.procurement_mln + r.reservation_mln
            + r.holding_mln + r.fixed_opex_mln
        )


# ---------------------------------------------------------------------------
# Интеграция: run_plan возвращает costs; ошибки входа — на русском
# ---------------------------------------------------------------------------

def test_run_plan_includes_costs():
    case = load_case(DATA_DIR)
    plan = make_plan(
        orders=[("B", "2035", 120.0)],
        reservations=[("B", 2035, 120.0)],
        plan_id="integration-wave2",
    )
    result = run_plan(case, plan, Scenario.base())
    assert len(result.costs.financial_breakdown) == 6
    r = row(result.costs, 2035)
    # B: TOP 0 → procurement = 120×8.9 = 1068; reservation = 120×0.15 = 18
    assert r.procurement_mln == pytest.approx(120.0 * 8.9)
    assert r.reservation_mln == pytest.approx(120.0 * 0.15)
    assert r.discounted_mln == pytest.approx(r.total_mln)


def test_capex_payment_date_out_of_horizon_raises_russian():
    """Платёж вне горизонта → исключение с русским сообщением и параметром."""
    case = make_synthetic_case()
    plan = make_plan()
    plan.decisions.investments = [Investment("ZBO", "fund_capex", "2041-06")]
    with pytest.raises(ValueError) as e:
        run_costs(case, plan)
    assert "2041-06" in str(e.value)


def test_capex_malformed_payment_date_raises_russian():
    case = make_synthetic_case()
    plan = make_plan()
    plan.decisions.investments = [Investment("ZBO", "fund_capex", "2036")]
    with pytest.raises(ValueError) as e:
        run_costs(case, plan)
    assert "2036" in str(e.value)
