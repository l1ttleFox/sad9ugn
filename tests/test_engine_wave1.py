"""Тесты расчётного ядра WP1 волна 1.

Контрольные векторы V01, V02, V06, V07, V08, V09, V10-аналог —
значения из tests/validation/expected_checks.json (CASE_INPUT организатора).
Дополнительно: lead times (A — 12 мес, Emergency — 6 недель), смена режима
хранения среди года (TA-05), загрузка реальных data/ и configs/, apply_scenario.
"""

from __future__ import annotations

import dataclasses
import json
import os

import pytest

from src.engine import (
    CaseData,
    CaseLoadError,
    ConstraintRow,
    DeliveriesResult,
    DemandRow,
    InvestmentOption,
    Plan,
    PlanDecisions,
    CapacityReservation,
    InitialInventorySource,
    InventoryPolicy,
    Investment,
    Scenario,
    StorageOption,
    SupplyOrder,
    SupplySource,
    apply_scenario,
    calculate_deliveries,
    calculate_inventory,
    calculate_service,
    load_case,
    load_plan,
    load_scenario,
    plan_from_dict,
    reserve_required_t,
    run_plan,
    validate_case,
    validate_plan,
)
from src.engine.inventory import zbo_start_index
from src.engine.deliveries import lead_time_months

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(REPO_ROOT, "data")
CONFIGS_DIR = os.path.join(REPO_ROOT, "configs")
EXPECTED_CHECKS_PATH = os.path.join(REPO_ROOT, "tests", "validation", "expected_checks.json")

HORIZON_YEARS = list(range(2035, 2041))


def _expected(case_id: str) -> dict:
    """Ожидаемые значения контрольного вектора из expected_checks.json."""
    with open(EXPECTED_CHECKS_PATH, "r", encoding="utf-8") as f:
        checks = json.load(f)
    for c in checks:
        if c["case_id"] == case_id:
            return c["expected"]
    raise AssertionError(f"Контрольный вектор {case_id} не найден в expected_checks.json")


# ---------------------------------------------------------------------------
# Синтетические данные
# ---------------------------------------------------------------------------

def make_synthetic_case(
    demand_by_year: dict[int, tuple[float, float]] | None = None,
    base_loss_rate: float = 0.0,
    base_capacity: float = 70.0,
) -> CaseData:
    """Синтетический CaseData (структура — как CASE_INPUT, значения тестовые).

    demand_by_year: {год: (total_t, critical_t)}; по умолчанию спрос нулевой.
    """
    demand_by_year = demand_by_year or {}
    demand = []
    for y in HORIZON_YEARS:
        total, crit = demand_by_year.get(y, (0.0, 0.0))
        demand.append(
            DemandRow(year=y, base_total_t=total, base_critical_t=crit,
                      low_total_t=total, high_total_t=total)
        )
    sources = [
        SupplySource("A", "Earth-Core", 190, 6.2, 0.45, 0.70, 12, 12, "month",
                     "constant:0.96", 2035),
        SupplySource("B", "Earth-Flex", 110, 8.9, 0.15, 0.00, 4, 4, "month",
                     "constant:0.985", 2035),
        SupplySource("C", "Earth-New", 130, 7.1, 0.30, 0.50, 18, 24, "month",
                     "first_operating_year:0.88;later:0.94", None),
        SupplySource("D", "Lunar-ISRU", 120, 3.0, 0.00, 0.00, 1, 2, "month",
                     "2038:0.78;2039:0.90;2040:0.93", 2038),
        SupplySource("E", "Emergency", 80, 13.8, 0.35, 0.00, 6, 6, "week",
                     "constant:0.995", 2035),
    ]
    storage = [
        StorageOption("BASE", "Base storage", base_capacity, base_loss_rate, 0.72, 0, 0, 2035),
        StorageOption("ZBO", "ZBO modernization", 120, 0.012, 0.72, 180, 12, 2036),
    ]
    investments = [
        InvestmentOption("EARTH_NEW", "Earth-New option", 90, 270, 360,
                         "18-24 months after exercise/preparation decision", 0),
        InvestmentOption("LUNAR_ISRU", "Lunar-ISRU pilot", 0, 1250, 1250,
                         "must be financed before 2038; available from 2038", 70),
        InvestmentOption("ZBO", "ZBO modernization", 0, 180, 180,
                         "option available from 2036", 12),
    ]
    case = CaseData(
        demand=demand,
        supply_sources=sources,
        storage_options=storage,
        investment_options=investments,
        constraints=[],
    )
    for d in case.demand:
        case.effective_demand_total_t[d.year] = d.base_total_t
        case.effective_demand_critical_t[d.year] = d.base_critical_t
    for s in case.supply_sources:
        for d in case.demand:
            case.effective_price_mln_per_t[(s.source_id, d.year)] = s.variable_cost_mln_per_t
            case.actual_delivery_share[(s.source_id, d.year)] = 1.0
    case.loss_ceiling = {"enabled": False}
    return case


def make_plan(
    orders: list[tuple[str, str, float]] | None = None,
    reservations: list[tuple[str, int, float]] | None = None,
    investments: list[tuple[str, str, str]] | None = None,
    initial_inventory_t: float = 0.0,
    initial_source: InitialInventorySource | None = None,
    plan_id: str = "test-plan",
) -> Plan:
    """Построение тестового плана."""
    return Plan(
        plan_id=plan_id,
        scenario_id="BASE",
        decisions=PlanDecisions(
            supply_orders=[SupplyOrder(*o) for o in (orders or [])],
            capacity_reservations=[CapacityReservation(*r) for r in (reservations or [])],
            investments=[Investment(*i) for i in (investments or [])],
            inventory_policy=InventoryPolicy(
                initial_inventory_t=initial_inventory_t,
                initial_inventory_source=initial_source,
            ),
        ),
    )


def deliveries_from(delivered: dict[str, float]) -> DeliveriesResult:
    """DeliveriesResult с заданным фактом поставок по месяцам."""
    d = DeliveriesResult()
    d.delivered_by_period = dict(delivered)
    d.planned_by_period = dict(delivered)
    return d


def month_row(inventory_result, period: str):
    """Строка monthly_balance за период."""
    for mb in inventory_result.monthly_balance:
        if mb.period == period:
            return mb
    raise AssertionError(f"Период {period} не найден в monthly_balance")


# ---------------------------------------------------------------------------
# Контрольные векторы (expected_checks.json)
# ---------------------------------------------------------------------------

def test_v01_material_balance():
    """V01: 10 + 30 − 2 − 25 = 13."""
    expected = _expected("V01")
    # месячный спрос 25 → годовой 300; потери 2 т при поступлении 30 т → rate 2/30
    case = make_synthetic_case(
        demand_by_year={2035: (300.0, 0.0)}, base_loss_rate=2.0 / 30.0
    )
    plan = make_plan(initial_inventory_t=10.0)
    inv = calculate_inventory(case, plan, deliveries_from({"2035-01": 30.0}))
    row = month_row(inv, "2035-01")
    assert row.i_start_t == pytest.approx(10.0)
    assert row.delivered_t == pytest.approx(30.0)
    assert row.losses_t == pytest.approx(2.0)
    assert row.served_total_t == pytest.approx(25.0)
    assert row.i_end_t == pytest.approx(expected["closing_inventory_t"])
    # Тождество баланса выполняется для каждого месяца.
    for mb in inv.monthly_balance:
        assert mb.i_end_t == pytest.approx(
            mb.i_start_t + mb.delivered_t - mb.losses_t - mb.served_total_t, abs=1e-9
        ) or mb.i_end_t == 0.0


def test_v02_shortage_not_negative_inventory():
    """V02: дефицит — отдельная метрика; запас не уходит в минус."""
    expected = _expected("V02")
    case = make_synthetic_case(demand_by_year={2035: (120.0, 0.0)}, base_loss_rate=0.0)
    plan = make_plan(initial_inventory_t=0.0)
    inv = calculate_inventory(case, plan, deliveries_from({"2035-01": 8.0}))
    row = month_row(inv, "2035-01")
    assert row.served_total_t == pytest.approx(expected["served_t"])
    assert row.shortage_t == pytest.approx(expected["shortage_t"])
    assert row.i_end_t == pytest.approx(expected["closing_inventory_t"])
    assert row.i_end_t >= 0.0
    # Ни в одном месяце запас не отрицателен.
    assert all(mb.i_end_t >= 0.0 for mb in inv.monthly_balance)


def test_v06_losses_once_on_throughput():
    """V06: потери = throughput × loss_rate, один раз (20 × 0.05 = 1)."""
    expected = _expected("V06")
    case = make_synthetic_case(demand_by_year={}, base_loss_rate=0.05)
    plan = make_plan()
    inv = calculate_inventory(case, plan, deliveries_from({"2035-03": 20.0}))
    row = month_row(inv, "2035-03")
    assert row.throughput_t == pytest.approx(20.0)
    assert row.losses_t == pytest.approx(expected["losses_t"])
    # Потери не начисляются повторно на остаток: в следующих месяцах без
    # поступлений losses = 0 (double counting запрещён, CALCULATION_RULES §3).
    assert month_row(inv, "2035-04").losses_t == pytest.approx(0.0)
    assert month_row(inv, "2035-03").i_end_t == pytest.approx(19.0)


def test_v07_reserve_45_days():
    """V07: 365 × 45 / 365 = 45."""
    expected = _expected("V07")
    assert reserve_required_t(365.0) == pytest.approx(expected["reserve_t"])
    case = make_synthetic_case(demand_by_year={2035: (365.0, 100.0)})
    plan = make_plan(initial_inventory_t=50.0)
    inv = calculate_inventory(case, plan, deliveries_from({}))
    service = calculate_service(case, inv)
    y2035 = next(y for y in service.yearly_balance if y.year == 2035)
    assert y2035.reserve_required_t == pytest.approx(expected["reserve_t"])
    assert y2035.reserve_actual_start_t == pytest.approx(50.0)
    assert y2035.reserve_ok is True


def test_v08_capacity_exceeded():
    """V08: reserved 12 > capacity 10 → CAPACITY_EXCEEDED, excess 2."""
    expected = _expected("V08")
    case = make_synthetic_case()
    case.supply_sources = [
        dataclasses.replace(s, capacity_t_per_year=10.0) if s.source_id == "A" else s
        for s in case.supply_sources
    ]
    plan = make_plan(reservations=[("A", 2035, 12.0)])
    violations = validate_plan(plan, case)
    cap = [v for v in violations if v.rule_id == expected["violation"]]
    assert cap, f"Ожидалось нарушение {expected['violation']}, получено: {violations}"
    assert cap[0].excess == pytest.approx(expected["excess_t"])
    assert cap[0].period == "2035"
    assert "A" in cap[0].message_ru and "2035" in cap[0].message_ru


def test_v08_monthly_oftake_capacity_exceeded():
    """V08 (расчётная часть): заказ в месяце > reserved/12 → CAPACITY_EXCEEDED."""
    case = make_synthetic_case()
    # резерв B 120 т/год → месячный лимит 10 т; заказ 12 т в 2035-01
    plan = make_plan(
        orders=[("B", "2035-01", 12.0)],
        reservations=[("B", 2035, 120.0)],
    )
    res = calculate_deliveries(case, plan)
    cap = [v for v in res.violations if v.rule_id == "CAPACITY_EXCEEDED"]
    assert cap
    assert cap[0].period == "2035-01"
    assert cap[0].excess == pytest.approx(2.0)
    # Поставка ограничена зарезервированной мощностью: 10 т в 2035-05.
    assert res.planned_by_source_period.get(("B", "2035-05")) == pytest.approx(10.0)


def test_v09_critical_nested_in_total():
    """V09: critical=60 вложен в total=100 (не 160)."""
    expected = _expected("V09")
    case = make_synthetic_case(demand_by_year={2035: (1200.0, 720.0)}, base_loss_rate=0.0)
    plan = make_plan(initial_inventory_t=80.0)
    inv = calculate_inventory(case, plan, deliveries_from({}))
    row = month_row(inv, "2035-01")
    # месячный общий спрос 100, критический 60 — вложен, не суммируется
    assert row.demand_total_t == pytest.approx(expected["total_demand_t"])
    assert row.demand_critical_t == pytest.approx(60.0)
    # аллокация при дефиците: сначала критический (available = 80)
    assert row.served_critical_t == pytest.approx(60.0)
    assert row.served_total_t == pytest.approx(80.0)
    assert row.shortage_t == pytest.approx(20.0)


def test_v10_analog_isru_share_without_reliability():
    """V10-аналог на данных кейса: ISRU share 0.55 применяется ОДИН раз,
    reliability (0.78 в 2038) НЕ умножается повторно."""
    case = make_synthetic_case()
    case.actual_delivery_share[("D", 2038)] = 0.55
    # D доступен с 2038-01 при финансировании LUNAR_ISRU до 2038-01
    plan = make_plan(
        orders=[("D", "2038-01", 10.0)],
        reservations=[("D", 2038, 120.0)],
        investments=[("LUNAR_ISRU", "fund_capex", "2037-06")],
    )
    res = calculate_deliveries(case, plan)
    # lead time D — 2 месяца (политика): заказ 2038-01 → поставка 2038-03
    assert res.planned_by_source_period.get(("D", "2038-03")) == pytest.approx(10.0)
    # факт = 10 × 0.55 = 5.5; НЕ 10 × 0.55 × 0.78 = 4.29 (reliability отдельно)
    assert res.actual_by_source_period[("D", "2038-03")] == pytest.approx(10.0 * 0.55)
    assert res.delivered_by_period.get("2038-03") == pytest.approx(5.5)


# ---------------------------------------------------------------------------
# Lead times и доступность каналов
# ---------------------------------------------------------------------------

def test_lead_time_a_12_months():
    """Канал A: заказ 2035-01 → поставка 2036-01 (12 месяцев, TA-04)."""
    case = make_synthetic_case()
    plan = make_plan(
        orders=[("A", "2035-01", 10.0)],
        reservations=[("A", 2035, 190.0)],
    )
    res = calculate_deliveries(case, plan)
    assert res.planned_by_source_period.get(("A", "2036-01")) == pytest.approx(10.0)
    assert "2035-01" not in [
        p for (s, p) in res.planned_by_source_period if s == "A"
    ]
    months, desc = lead_time_months(case, "A")
    assert months == 12
    assert desc == "12 month"


def test_lead_time_emergency_6_weeks_next_month():
    """Emergency: 6 недель → поставка в следующем месяце (TA-03)."""
    case = make_synthetic_case()
    plan = make_plan(
        orders=[("E", "2035-01", 5.0)],
        reservations=[("E", 2035, 80.0)],
    )
    res = calculate_deliveries(case, plan)
    months, desc = lead_time_months(case, "E")
    assert months == 1
    assert "42" in desc and "TA-03" in desc
    assert res.planned_by_source_period.get(("E", "2035-02")) == pytest.approx(5.0)


def test_lead_time_c_policy_24_months():
    """Earth-New: диапазон 18–24, политика 24 месяца (TA-02), раскрыт в schedule."""
    case = make_synthetic_case()
    months, desc = lead_time_months(case, "C")
    assert months == 24
    assert desc == "18-24 month (policy: 24)"
    plan = make_plan(
        orders=[("C", "2037-06", 10.0)],
        reservations=[("C", 2037, 130.0)],
        investments=[("EARTH_NEW", "exercise_option", "2035-06")],
    )
    res = calculate_deliveries(case, plan)
    # C доступен с 2037-06 (24 мес после exercise 2035-06); поставка 2039-06
    assert res.planned_by_source_period.get(("C", "2039-06")) == pytest.approx(10.0)
    assert not [v for v in res.violations if v.rule_id == "LEAD_TIME_VIOLATION"]
    # Строка source_schedule раскрывает конвенцию lead time
    row = next(
        r for r in res.source_schedule
        if r.source_id == "C" and r.period == "2039-06" and r.planned_delivery_t > 0
    )
    assert row.lead_time_applied == "18-24 month (policy: 24)"


def test_channel_c_unavailable_before_exercise_plus_24():
    """C недоступен ранее 24 мес после exercise → LEAD_TIME_VIOLATION."""
    case = make_synthetic_case()
    plan = make_plan(
        orders=[("C", "2037-05", 10.0)],
        reservations=[("C", 2037, 130.0)],
        investments=[("EARTH_NEW", "exercise_option", "2035-06")],
    )
    res = calculate_deliveries(case, plan)
    lead = [v for v in res.violations if v.rule_id == "LEAD_TIME_VIOLATION"]
    assert lead and lead[0].period == "2037-05"
    assert "недоступен" in lead[0].message_ru


def test_channel_d_requires_isru_financed_before_2038():
    """D: без финансирования LUNAR_ISRU до 2038-01 канал недоступен."""
    case = make_synthetic_case()
    # Без инвестиции
    plan = make_plan(
        orders=[("D", "2038-01", 10.0)],
        reservations=[("D", 2038, 120.0)],
    )
    res = calculate_deliveries(case, plan)
    assert any(v.rule_id == "LEAD_TIME_VIOLATION" for v in res.violations)
    # Финансирование позднее дедлайна 2037-12
    plan_late = make_plan(
        orders=[("D", "2038-01", 10.0)],
        reservations=[("D", 2038, 120.0)],
        investments=[("LUNAR_ISRU", "fund_capex", "2038-02")],
    )
    res_late = calculate_deliveries(case, plan_late)
    assert any(v.rule_id == "LEAD_TIME_VIOLATION" for v in res_late.violations)
    # validate_plan также ловит заказ D без инвестиции
    static = validate_plan(plan, case)
    assert any(v.rule_id == "INVESTMENT_REQUIRED" for v in static)


# ---------------------------------------------------------------------------
# Режимы хранения и смена режима (TA-05)
# ---------------------------------------------------------------------------

def test_zbo_switch_midyear():
    """Смена режима среди года: платёж ZBO 2036-05 → ZBO с 2036-06 (TA-05).

    Поступления месяцев ≤ 2036-05 теряют 4,5%, начиная с 2036-06 — 1,2%.
    """
    case = make_synthetic_case(base_loss_rate=0.045)
    plan = make_plan(investments=[("ZBO", "fund_capex", "2036-05")])
    assert zbo_start_index(plan) is not None

    inv = calculate_inventory(
        case, plan,
        deliveries_from({"2036-05": 10.0, "2036-06": 10.0}),
    )
    may = month_row(inv, "2036-05")
    jun = month_row(inv, "2036-06")
    assert may.storage_mode == "BASE"
    assert may.storage_capacity_t == pytest.approx(70.0)
    assert may.losses_t == pytest.approx(10.0 * 0.045)
    assert jun.storage_mode == "ZBO"
    assert jun.storage_capacity_t == pytest.approx(120.0)
    assert jun.losses_t == pytest.approx(10.0 * 0.012)


def test_zbo_not_earlier_than_2036():
    """Платёж ZBO до 2036-01 игнорируется (опция доступна с 2036)."""
    plan = make_plan(investments=[("ZBO", "fund_capex", "2035-06")])
    assert zbo_start_index(plan) is None


def test_storage_overflow_violation():
    """Переполнение ёмкости → STORAGE_OVERFLOW с периодом и excess."""
    case = make_synthetic_case(base_capacity=70.0)
    plan = make_plan()
    inv = calculate_inventory(case, plan, deliveries_from({"2035-02": 200.0}))
    over = [v for v in inv.violations if v.rule_id == "STORAGE_OVERFLOW"]
    assert over
    assert over[0].period == "2035-02"
    assert over[0].excess == pytest.approx(130.0)
    assert "ёмкость" in over[0].message_ru


# ---------------------------------------------------------------------------
# Загрузка реальных данных и сценариев
# ---------------------------------------------------------------------------

def test_load_real_case():
    """Загрузка реальных data/*.csv проходит без ошибок."""
    case = load_case(DATA_DIR)
    assert len(case.demand) == 6
    assert len(case.supply_sources) == 5
    assert case.source("E").lead_time_unit == "week"
    assert case.storage("BASE").capacity_t == 70.0
    violations = validate_case(case)
    assert violations == [], f"Реальные данные не прошли валидацию: {violations}"


def test_load_real_scenarios_and_apply():
    """configs/base.yaml и mandatory_stress.yaml загружаются и применяются."""
    base = load_scenario(os.path.join(CONFIGS_DIR, "base.yaml"))
    assert base.scenario_id == "BASE"
    stress = load_scenario(os.path.join(CONFIGS_DIR, "mandatory_stress.yaml"))
    assert stress.scenario_id == "MANDATORY_STRESS"

    case = load_case(DATA_DIR)

    # BASE: все множители 1.0 — данные не меняются
    base_case = apply_scenario(case, base)
    assert base_case.effective_demand_total_t[2038] == pytest.approx(250.0)
    assert base_case.effective_price_mln_per_t[("A", 2038)] == pytest.approx(6.2)
    assert base_case.actual_delivery_share[("D", 2038)] == pytest.approx(1.0)

    # MANDATORY_STRESS: спрос ×1.15 с 2038, цены Earth-Core/Flex ×1.25
    # в 2038–2039, ISRU share 0.55 (2038) / 0.75 (2039), loss ceiling включён.
    stress_case = apply_scenario(case, stress)
    assert stress_case.effective_demand_total_t[2038] == pytest.approx(250.0 * 1.15)
    assert stress_case.effective_demand_critical_t[2038] == pytest.approx(170.0 * 1.15)
    assert stress_case.effective_demand_total_t[2035] == pytest.approx(100.0)
    assert stress_case.effective_price_mln_per_t[("A", 2038)] == pytest.approx(6.2 * 1.25)
    assert stress_case.effective_price_mln_per_t[("B", 2039)] == pytest.approx(8.9 * 1.25)
    assert stress_case.effective_price_mln_per_t[("A", 2040)] == pytest.approx(6.2)
    # Цены каналов, не названных в сценарии, не меняются (Earth-New 7.1)
    assert stress_case.effective_price_mln_per_t[("C", 2038)] == pytest.approx(7.1)
    assert stress_case.actual_delivery_share[("D", 2038)] == pytest.approx(0.55)
    assert stress_case.actual_delivery_share[("D", 2039)] == pytest.approx(0.75)
    assert stress_case.actual_delivery_share[("D", 2040)] == pytest.approx(1.0)
    assert stress_case.actual_delivery_share[("A", 2038)] == pytest.approx(1.0)
    assert stress_case.loss_ceiling["enabled"] is True
    # Исходный case НЕ мутируется
    assert case.effective_demand_total_t[2038] == pytest.approx(250.0)
    assert case.scenario_id == "BASE"


def test_load_case_missing_file(tmp_path):
    """Ошибка загрузки называет файл по-русски."""
    with pytest.raises(CaseLoadError) as e:
        load_case(str(tmp_path))
    assert "не найден" in str(e.value)


def test_load_plan_examples():
    """Загрузка примера плана организатора."""
    plan = load_plan(os.path.join(REPO_ROOT, "tests", "examples", "empty_plan.json"))
    assert plan.plan_id == "example-empty-plan"
    assert plan.decisions.supply_orders == []


def test_load_invalid_plan_examples():
    """Некорректные планы → CaseLoadError с русским сообщением и параметром."""
    examples_dir = os.path.join(REPO_ROOT, "tests", "examples", "invalid_plan_examples")
    # over_capacity.json / negative_reservation.json: параметр
    # 'reserved_capacity_t_per_year' отсутствует (ключ организаторского примера
    # 'reserved_capacity_t' не соответствует plan_format.json)
    for name in ("over_capacity.json", "negative_reservation.json"):
        with pytest.raises(CaseLoadError) as e:
            load_plan(os.path.join(examples_dir, name))
        msg = str(e.value)
        assert name in msg
        assert "reserved_capacity_t_per_year" in msg


def test_load_malformed_scenario():
    """Сценарий без scenario_id → CaseLoadError (JSON парсится как YAML)."""
    path = os.path.join(
        REPO_ROOT, "tests", "examples", "invalid_plan_examples", "malformed_scenario.json"
    )
    with pytest.raises(CaseLoadError) as e:
        load_scenario(path)
    assert "scenario_id" in str(e.value)


# ---------------------------------------------------------------------------
# validate_case / validate_plan
# ---------------------------------------------------------------------------

def test_validate_case_critical_gt_total():
    """critical > total → нарушение целостности данных."""
    case = make_synthetic_case(demand_by_year={2035: (50.0, 60.0)})
    violations = validate_case(case)
    assert any(v.rule_id == "DATA_CRITICAL_GT_TOTAL" and v.period == "2035" for v in violations)


def test_validate_plan_static_checks():
    """Статика плана: неизвестный investment_id, период вне горизонта."""
    case = load_case(DATA_DIR)
    plan = plan_from_dict(
        {
            "plan_id": "bad-plan",
            "scenario_id": "BASE",
            "decisions": {
                "supply_orders": [{"source_id": "B", "period": "2041-01", "ordered_volume_t": 5}],
                "capacity_reservations": [],
                "investments": [
                    {"investment_id": "MARS_BASE", "action": "fund_capex", "payment_date": "2036-01"}
                ],
                "inventory_policy": {"initial_inventory_t": 0},
            },
            "assumptions": [],
        }
    )
    violations = validate_plan(plan, case)
    rules = {v.rule_id for v in violations}
    assert "PERIOD_OUT_OF_HORIZON" in rules
    assert "UNKNOWN_INVESTMENT" in rules
    # Сообщения — на русском, с параметрами
    for v in violations:
        assert v.message_ru


def test_validate_plan_initial_inventory_mismatch():
    """Начальный запас не должен учитываться дважды (units §3)."""
    case = load_case(DATA_DIR)
    plan = make_plan(
        initial_inventory_t=10.0,
        initial_source=InitialInventorySource(
            source_id="A", order_period="2034-09", delivery_period="2035-01",
            volume_t=8.0, paid_in="2035",
        ),
    )
    violations = validate_plan(plan, case)
    assert any(v.rule_id == "INITIAL_INVENTORY_MISMATCH" for v in violations)


# ---------------------------------------------------------------------------
# Интеграция: синтетический план (только канал B, ровные заказы)
# ---------------------------------------------------------------------------

def test_b_only_plan_manual_balance():
    """Ручная сверка: канал B, резерв 120 т/год, ровный годовой заказ 120 т.

    Месячный лимит отбора = 120/12 = 10 т; заказ 120 т/год распределяется
    равномерно (10 т/мес). Lead time B = 4 мес: поставки начинаются с 2035-05.
    Спрос 2035 = 60 т/год → 5 т/мес. Потери BASE 4,5% от поступлений.

    Ручной расчёт (см. также REPORT_wave1.md):
      2035-01…04: поставок нет, I=0 → served=0, shortage=5 т/мес;
      2035-05: I_start=0, delivered=10, losses=10×0.045=0.45, served=5,
               I_end=0+10−0.45−5=4.55;
      2035-06: I_start=4.55, delivered=10, losses=0.45, served=5,
               I_end=4.55+10−0.45−5=9.10;
      2035-07: I_end=9.10+10−0.45−5=13.65.
    """
    case = load_case(DATA_DIR)
    # Синтетический ровный спрос для сверки (60 т/год в 2035, прочее 0).
    # Меняем исходные base_*_t (а не effective_*), чтобы apply_scenario
    # внутри run_plan вычислил действующий спрос именно из них.
    case.demand = [
        dataclasses.replace(
            d,
            base_total_t=(60.0 if d.year == 2035 else 0.0),
            base_critical_t=0.0,
            low_total_t=0.0,
            high_total_t=0.0,
        )
        for d in case.demand
    ]

    plan = make_plan(
        orders=[("B", "2035", 120.0)],
        reservations=[("B", 2035, 120.0)],
        plan_id="b-only-manual",
    )
    result = run_plan(case, plan, Scenario.base())
    inv = result.inventory

    assert not [v for v in result.violations if v.rule_id == "CAPACITY_EXCEEDED"]

    m05 = month_row(inv, "2035-05")
    assert m05.i_start_t == pytest.approx(0.0)
    assert m05.delivered_t == pytest.approx(10.0)
    assert m05.losses_t == pytest.approx(0.45)
    assert m05.served_total_t == pytest.approx(5.0)
    assert m05.i_end_t == pytest.approx(4.55)

    m06 = month_row(inv, "2035-06")
    assert m06.i_start_t == pytest.approx(4.55)
    assert m06.i_end_t == pytest.approx(9.10)

    m07 = month_row(inv, "2035-07")
    assert m07.i_end_t == pytest.approx(13.65)

    # До начала поставок — дефицит, но запас не отрицательный
    m01 = month_row(inv, "2035-01")
    assert m01.shortage_t == pytest.approx(5.0)
    assert m01.i_end_t == pytest.approx(0.0)

    # Сервис: SL 2035 = served/demand (8 месяцев по 5 т из 60 т)
    service = result.service
    y2035 = next(y for y in service.yearly_balance if y.year == 2035)
    assert y2035.delivered_t == pytest.approx(80.0)  # 8 поставок по 10 т
    assert y2035.served_total_t == pytest.approx(40.0)  # 8 месяцев × 5 т
    assert y2035.sl_total == pytest.approx(40.0 / 60.0)
    # Резерв 45 дней: R = 60×45/365 ≈ 7.397; на 01.01 запас 0 → reserve_ok False
    assert y2035.reserve_required_t == pytest.approx(60.0 * 45.0 / 365.0)
    assert y2035.reserve_ok is False
