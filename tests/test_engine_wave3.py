"""Тесты WP1 волна 3: ограничения, сравнение, сохранение, экспорт, риски,
адаптер scenario_parameters (D3.4), полный passed-список проверок (D4.2).

Интеграция: эталонный BASE-план без hard-нарушений; STRESS-декомпозиция
(спрос/цены/ISRU/потолок — по отдельности); invalid_plan_examples
организатора; V08; экспорт → повторная загрузка; идемпотентность save/load.
"""

from __future__ import annotations

import csv
import dataclasses
import json
import os

import pytest

from src.engine import (
    CaseLoadError,
    ConstraintCheck,
    EmergencyContract,
    InitialInventorySource,
    Scenario,
    apply_scenario,
    apply_scenario_parameters,
    check_all,
    check_constraints,
    compare_scenarios,
    evaluate_risks,
    export_results,
    load_case,
    load_plan,
    load_scenario,
    load_saved_plan,
    plan_from_dict,
    run_plan,
    save_plan,
)

from test_engine_wave1 import make_plan, make_synthetic_case  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(REPO_ROOT, "data")
CONFIGS_DIR = os.path.join(REPO_ROOT, "configs")
WP2_DIR = os.path.join(REPO_ROOT, "ai_workstreams", "WP2_strategy_economics")
TEAM_DIR = os.path.join(REPO_ROOT, "ai_workstreams", "WP3_stress_risk", "configs", "team")
EXAMPLES_DIR = os.path.join(REPO_ROOT, "tests", "examples", "invalid_plan_examples")


def _row(costs, year: int):
    for r in costs.financial_breakdown:
        if r.year == year:
            return r
    raise AssertionError(f"Год {year} не найден в financial_breakdown")


def _check(result, rule_id: str, period: str | None = None):
    for c in result.checks:
        if c.rule_id == rule_id and (period is None or c.period == period):
            return c
    raise AssertionError(f"Проверка {rule_id} ({period}) не найдена в checks")


# ---------------------------------------------------------------------------
# Эталонный BASE-план: минимальный выполнимый (B покрывает 2035)
# ---------------------------------------------------------------------------

def make_reference_plan():
    """Минимальный выполнимый план: начальный запас 22 т (подготовительный
    заказ у B, оплата 2035) + ровные месячные заказы B 5.5 т (2035-01…08)
    покрывают синтетический спрос 60 т 2035 года. Lead time B = 4 мес:
    поставки 2035-05…12; начальный запас закрывает 2035-01…04."""
    return plan_from_dict({
        "plan_id": "reference-minimal",
        "scenario_id": "BASE",
        "version": "wave3",
        "decisions": {
            "supply_orders": [
                {"source_id": "B", "period": f"2035-{m:02d}", "ordered_volume_t": 5.5}
                for m in range(1, 9)
            ],
            "capacity_reservations": [
                {"source_id": "B", "year": 2035, "reserved_capacity_t_per_year": 66.0},
            ],
            "investments": [],
            "inventory_policy": {
                "initial_inventory_t": 22.0,
                "initial_inventory_source": {
                    "source_id": "B", "order_period": "2034-09",
                    "delivery_period": "2035-01", "volume_t": 22.0, "paid_in": "2035",
                },
                "reserve_mode": "physical",
            },
        },
        "assumptions": [
            {"id": "TA-REF", "value": 22, "unit": "t",
             "rationale_ru": "начальный запас подготовительного заказа",
             "scope": "2035"},
        ],
    })


def make_reference_case():
    """Синтетический кейс: спрос 60 т только в 2035 (прочее 0), потери 4,5%."""
    return make_synthetic_case(demand_by_year={2035: (60.0, 0.0)}, base_loss_rate=0.045)


def test_reference_plan_base_no_hard_violations():
    """BASE-прогон эталонного плана: все hard-нарушения отсутствуют,
    полный passed-список проверок присутствует (D4.2)."""
    case = make_reference_case()
    plan = make_reference_plan()
    result = run_plan(case, plan, Scenario.base())

    hard_failed = [v for v in result.violations]
    assert hard_failed == [], f"Эталонный план имеет нарушения: {hard_failed}"

    # Полный реестр: и passed, и failed
    assert result.checks, "checks пуст"
    passed_rules = {c.rule_id for c in result.checks if c.passed}
    for rule in ("BASE_TOTAL_SERVICE", "BASE_CRITICAL_SERVICE", "CAPEX_2037",
                 "CAPEX_2040", "RESERVE_45D", "EMERGENCY_BASE_STREAK",
                 "NEGATIVE_INVENTORY", "ISRU_FIRST_YEAR_RELIABILITY"):
        assert rule in passed_rules, f"Проверка {rule} не пройдена/отсутствует"

    # Сервис: спрос 2035 обслужен полностью
    y2035 = next(y for y in result.service.yearly_balance if y.year == 2035)
    assert y2035.served_total_t == pytest.approx(60.0)
    assert y2035.sl_total == pytest.approx(1.0)

    # Финансы: закупка B 2035 = max(44, 0)×8.9 + подготовительные 22×8.9
    r35 = _row(result.costs, 2035)
    assert r35.procurement_mln == pytest.approx((8 * 5.5 + 22.0) * 8.9)
    assert r35.reservation_mln == pytest.approx(66.0 * 0.15)


def test_reference_plan_stress_applies_factors():
    """MANDATORY_STRESS того же плана: множители применились (спрос 2035
    не меняется — шок с 2038; цены A/B ×1.25 в 2038–2039; ISRU 0.55/0.75;
    loss ceiling включён в checks-конфигурацию)."""
    case = load_case(DATA_DIR)
    stress = load_scenario(os.path.join(CONFIGS_DIR, "mandatory_stress.yaml"))
    eff = apply_scenario(case, stress)
    assert eff.effective_demand_total_t[2038] == pytest.approx(250.0 * 1.15)
    assert eff.effective_price_mln_per_t[("A", 2038)] == pytest.approx(6.2 * 1.25)
    assert eff.effective_price_mln_per_t[("A", 2040)] == pytest.approx(6.2)
    assert eff.actual_delivery_share[("D", 2038)] == pytest.approx(0.55)
    assert eff.actual_delivery_share[("D", 2039)] == pytest.approx(0.75)
    assert eff.loss_ceiling.get("enabled") is True

    # Прогон реального плана S10 в стрессе: STRESS_LOSS_LIMIT присутствует
    plan = load_plan(os.path.join(WP2_DIR, "plans", "S10_STRESS.json"))
    result = run_plan(case, plan, stress)
    loss_checks = [c for c in result.checks if c.rule_id == "STRESS_LOSS_LIMIT"]
    assert loss_checks and all(c.period in ("2038", "2039", "2040") for c in loss_checks)


def test_stress_decomposition_four_factors():
    """Декомпозиция стресса (критерий приёмки 2): 4 промежуточных сценария
    по одному фактору — каждый эффект виден отдельно."""
    case = load_case(DATA_DIR)
    plan = load_plan(os.path.join(WP2_DIR, "plans", "S10.json"))
    base = run_plan(case, plan, Scenario.base())
    base_pv = sum(r.discounted_mln for r in base.costs.financial_breakdown)
    base_shortage = sum(y.shortage_t for y in base.service.yearly_balance)

    demand_only = Scenario(
        scenario_id="TEAM_FACTOR_DEMAND",
        demand_multiplier={"2038": 1.15, "2039": 1.15, "2040": 1.15, "default": 1.0},
        critical_demand_multiplier={"2038": 1.15, "2039": 1.15, "2040": 1.15, "default": 1.0},
    )
    price_only = Scenario(
        scenario_id="TEAM_FACTOR_PRICE",
        variable_price_multiplier={
            "Earth-Core": {"2038": 1.25, "2039": 1.25},
            "Earth-Flex": {"2038": 1.25, "2039": 1.25},
        },
    )
    isru_only = Scenario(
        scenario_id="TEAM_FACTOR_ISRU",
        actual_delivery_share={"Lunar-ISRU": {"2038": 0.55, "2039": 0.75}},
    )
    ceiling_only = Scenario(
        # STRESS_LOSS_LIMIT по constraints.csv применяется только в сценарии
        # MANDATORY_STRESS — промежуточный факторный тест сохраняет id,
        # включая ЕДИНСТВЕННЫЙ фактор «потолок потерь».
        scenario_id="MANDATORY_STRESS",
        loss_ceiling={"enabled": True, "from_year": 2038,
                      "max_losses_divided_by_throughput": 0.02},
    )

    r_demand = run_plan(case, plan, demand_only)
    r_price = run_plan(case, plan, price_only)
    r_isru = run_plan(case, plan, isru_only)
    r_ceiling = run_plan(case, plan, ceiling_only)

    # Спрос ×1.15 (S10 заказан под BASE-спрос) → дефицит растёт
    shortage_demand = sum(y.shortage_t for y in r_demand.service.yearly_balance)
    assert shortage_demand > base_shortage

    # Цены ×1.25 для A/B 2038–2039 → PV растёт, физика не меняется
    pv_price = sum(r.discounted_mln for r in r_price.costs.financial_breakdown)
    assert pv_price > base_pv
    assert sum(y.shortage_t for y in r_price.service.yearly_balance) == pytest.approx(base_shortage)

    # ISRU 0.55/0.75 → меньше фактических поставок D → дефицит/запас меняются
    d38_base = base.deliveries.actual_by_source_period.get(("D", "2038-03"), 0.0)
    d38_isru = r_isru.deliveries.actual_by_source_period.get(("D", "2038-03"), 0.0)
    if d38_base:
        assert d38_isru == pytest.approx(d38_base * 0.55)

    # Потолок потерь сам по себе физики не меняет: проверки STRESS_LOSS_LIMIT
    # появляются с 2038; у S10 введён ZBO (потери 1.2% ≤ 2%) — проверки
    # пройдены, PV совпадает с BASE.
    loss_checks = [c for c in r_ceiling.checks if c.rule_id == "STRESS_LOSS_LIMIT"]
    assert {c.period for c in loss_checks} == {"2038", "2039", "2040"}
    assert all(c.passed for c in loss_checks), (
        "ZBO-режим (1.2%) должен укладываться в потолок 2%"
    )
    pv_ceiling = sum(r.discounted_mln for r in r_ceiling.costs.financial_breakdown)
    assert pv_ceiling == pytest.approx(base_pv)


# ---------------------------------------------------------------------------
# constraint_checks: полный список (D4.2), формат нарушений (README §26)
# ---------------------------------------------------------------------------

def test_checks_contain_full_passed_registry():
    """Полный passed-список содержит все проверки выполнимого BASE-плана."""
    case = load_case(DATA_DIR)
    plan = load_plan(os.path.join(WP2_DIR, "plans", "S10.json"))
    result = run_plan(case, plan, Scenario.base())
    rules_passed = {c.rule_id for c in result.checks if c.passed}
    rules_failed = {c.rule_id for c in result.checks if not c.passed}
    # S10 BASE: CAPEX проходит, резерв 45д проходит
    assert "CAPEX_2037" in rules_passed and "CAPEX_2040" in rules_passed
    assert "RESERVE_45D" in rules_passed
    # После согласования мощности по году поставки S10 проходит весь BASE.
    assert not rules_failed
    # violations = только нарушения; каждое попало и в checks
    for v in result.violations:
        assert any(c.rule_id == v.rule_id and c.period == v.period
                   and not c.passed for c in result.checks)
    assert all(not c.passed or c.excess == 0.0 for c in result.checks)


def test_violation_message_format():
    """Формат нарушения (README организатора §26): rule_id, период, факт,
    лимит, excess, русская причина с величиной."""
    case = make_synthetic_case()
    case.supply_sources = [
        dataclasses.replace(s, capacity_t_per_year=10.0)
        if s.source_id == "A" else s
        for s in case.supply_sources
    ]
    plan = make_plan(reservations=[("A", 2035, 12.0)])
    result = run_plan(case, plan, Scenario.base())
    cap = [v for v in result.violations if v.rule_id == "CAPACITY_EXCEEDED"]
    assert cap
    v = cap[0]
    assert v.period == "2035"
    assert v.actual == pytest.approx(12.0)
    assert v.limit == pytest.approx(10.0)
    assert v.excess == pytest.approx(2.0)
    for token in ("A", "2035", "12", "10"):
        assert token in v.message_ru


def test_v08_static_reserved_over_capacity():
    """V08: capacity 10, reserved 12 → CAPACITY_EXCEEDED, excess 2."""
    case = make_synthetic_case()
    case.supply_sources = [
        dataclasses.replace(s, capacity_t_per_year=10.0)
        if s.source_id == "A" else s
        for s in case.supply_sources
    ]
    plan = make_plan(reservations=[("A", 2035, 12.0)])
    result = run_plan(case, plan, Scenario.base())
    c = _check(result, "CAPACITY_EXCEEDED", "2035")
    assert not c.passed
    assert c.excess == pytest.approx(2.0)


def test_check_constraints_returns_only_violations():
    """check_constraints (контракт v1.0) — только нарушения."""
    case = make_synthetic_case()
    case.supply_sources = [
        dataclasses.replace(s, capacity_t_per_year=10.0)
        if s.source_id == "A" else s
        for s in case.supply_sources
    ]
    plan = make_plan(reservations=[("A", 2035, 12.0)])
    result = run_plan(case, plan, Scenario.base())
    viols = check_constraints(case, plan, result.inventory, result.service,
                              result.costs, deliveries=result.deliveries)
    assert viols and all(isinstance(v, type(result.violations[0])) for v in viols)
    assert any(v.rule_id == "CAPACITY_EXCEEDED" for v in viols)


def test_isru_without_capex_and_earth_new_without_exercise():
    """Заказы D без LUNAR_ISRU и C без EARTH_NEW — отдельные rule_id."""
    case = make_synthetic_case()
    plan = make_plan(
        orders=[("C", "2037-06", 10.0), ("D", "2038-06", 10.0)],
        reservations=[("C", 2037, 50.0), ("D", 2038, 50.0)],
    )
    result = run_plan(case, plan, Scenario.base())
    c_rule = _check(result, "EARTH_NEW_WITHOUT_EXERCISE")
    d_rule = _check(result, "ISRU_WITHOUT_CAPEX")
    assert not c_rule.passed and "EARTH_NEW" in c_rule.message_ru
    assert not d_rule.passed and "LUNAR_ISRU" in d_rule.message_ru


def test_isru_deadline_late_funding():
    """Финансирование ISRU после 2037-12 → ISRU_WITHOUT_CAPEX (дедлайн)."""
    case = make_synthetic_case()
    plan = make_plan(
        orders=[("D", "2038-06", 10.0)],
        reservations=[("D", 2038, 50.0)],
        investments=[("LUNAR_ISRU", "fund_capex", "2038-02")],
    )
    result = run_plan(case, plan, Scenario.base())
    d_rule = _check(result, "ISRU_WITHOUT_CAPEX")
    assert not d_rule.passed
    assert "2037-12" in d_rule.message_ru


def test_isru_first_year_reliability_warning():
    """План заявляет надёжность D 2038 = 0.9 > 0.78 → soft-предупреждение."""
    case = make_synthetic_case()
    plan = make_plan()
    from src.engine import Assumption
    plan.assumptions.append(
        Assumption(id="TA-X", value=0.9, unit="share",
                   rationale_ru="надёжность канала D (Lunar-ISRU) 2038 гарантирована",
                   scope="2038")
    )
    result = run_plan(case, plan, Scenario.base())
    warn = _check(result, "ISRU_FIRST_YEAR_RELIABILITY")
    assert not warn.passed
    assert warn.severity == "soft"


def test_emergency_base_streak():
    """TA-09: E базовый (>40% served года) 3 года подряд → нарушение ≤2."""
    case = make_synthetic_case(demand_by_year={
        2036: (60.0, 0.0), 2037: (60.0, 0.0), 2038: (60.0, 0.0),
    })
    # Emergency-снабжение: заказы E по 60 т в год (lead time 1 мес),
    # начальный запас закрывает 2035 и январь каждого года.
    orders = [("E", f"{y}", 60.0) for y in (2036, 2037, 2038)]
    plan = make_plan(
        orders=orders,
        reservations=[("E", y, 80.0) for y in (2036, 2037, 2038)],
        initial_inventory_t=10.0,
    )
    result = run_plan(case, plan, Scenario.base())
    c = _check(result, "EMERGENCY_BASE_STREAK")
    # отбор E ≈ 60 т/год > 40% served (60) — гранично; проверяем что проверка
    # присутствует и streak посчитан (3 при полном покрытии E)
    assert c.limit == pytest.approx(2.0)
    assert c.actual in (2.0, 3.0)
    if c.actual == 3.0:
        assert not c.passed


def test_reserve_45d_contractual_emergency():
    """Контрактный Emergency-резерв: доказательство покрытия 42 дней."""
    case = make_synthetic_case(demand_by_year={2035: (100.0, 0.0)})
    plan = make_plan(
        orders=[("E", "2035", 100.0)],
        reservations=[("E", 2035, 80.0)],
    )
    plan.decisions.inventory_policy.reserve_mode = "contractual_emergency"
    plan.decisions.emergency_contract = EmergencyContract(
        reserved_capacity_t_per_year=80.0, activation_lead_days=42.0,
        coverage_volume_t=12.0,
        notes_ru="покрытие спроса за период ожидания 42 дня",
    )
    result = run_plan(case, plan, Scenario.base())
    c = _check(result, "RESERVE_45D", "2035")
    # спрос за 42 дня = 100×42/365 ≈ 11.5; покрытие 80×42/365 ≈ 9.2 < 11.5 → fail
    assert not c.passed
    # Увеличиваем контрактный резерв — проходит
    plan2 = make_plan(
        orders=[("E", "2035", 100.0)],
        reservations=[("E", 2035, 80.0)],
    )
    plan2.decisions.inventory_policy.reserve_mode = "contractual_emergency"
    plan2.decisions.emergency_contract = EmergencyContract(
        reserved_capacity_t_per_year=120.0, coverage_volume_t=14.0,
    )
    result2 = run_plan(case, plan2, Scenario.base())
    c2 = _check(result2, "RESERVE_45D", "2035")
    assert c2.passed


def test_negative_inventory_protective_check_passes():
    """NEGATIVE_INVENTORY — защитная проверка: в нормальном прогоне passed."""
    case = make_reference_case()
    plan = make_reference_plan()
    result = run_plan(case, plan, Scenario.base())
    c = _check(result, "NEGATIVE_INVENTORY")
    assert c.passed and c.actual >= 0.0


# ---------------------------------------------------------------------------
# invalid_plan_examples организатора (D1.1) + расширяемость Source-X (§28)
# ---------------------------------------------------------------------------

def test_invalid_examples_rejected_with_russian_message():
    """over_capacity/negative_reservation: ключ организатора
    'reserved_capacity_t' не соответствует plan_format.json — load_plan
    отклоняет с русским сообщением (D1.1); malformed_scenario — без
    scenario_id."""
    for name in ("over_capacity.json", "negative_reservation.json"):
        with pytest.raises(CaseLoadError) as e:
            load_plan(os.path.join(EXAMPLES_DIR, name))
        assert name in str(e.value)
        assert "reserved_capacity_t_per_year" in str(e.value)
    with pytest.raises(CaseLoadError) as e:
        load_scenario(os.path.join(EXAMPLES_DIR, "malformed_scenario.json"))
    assert "scenario_id" in str(e.value)


def test_over_capacity_semantics_via_adapted_keys():
    """Семантика примера over_capacity (Source-X: capacity 10, reserved 12 →
    excess 2) воспроизводится в формате plan_format: CAPACITY_EXCEEDED."""
    case = make_synthetic_case()
    case.supply_sources = [
        dataclasses.replace(s, capacity_t_per_year=10.0)
        if s.source_id == "A" else s
        for s in case.supply_sources
    ]
    raw = json.load(open(os.path.join(EXAMPLES_DIR, "over_capacity.json"), encoding="utf-8"))
    res = raw["decisions"]["capacity_reservations"][0]
    plan = plan_from_dict({
        "plan_id": raw["plan_id"] + "-adapted",
        "scenario_id": "BASE",
        "decisions": {
            "supply_orders": [],
            "capacity_reservations": [{
                "source_id": "A",  # Source-X → существующий канал копии набора
                "year": res["year"],
                "reserved_capacity_t_per_year": res["reserved_capacity_t"],
            }],
            "investments": [],
            "inventory_policy": {"initial_inventory_t": 0},
        },
        "assumptions": [],
    })
    result = run_plan(case, plan, Scenario.base())
    c = _check(result, "CAPACITY_EXCEEDED", "2035")
    assert not c.passed and c.excess == pytest.approx(2.0)


def test_extensibility_source_x(tmp_path):
    """Расширяемость (README организатора §28, D1.1): КОПИЯ набора данных с
    синтетическим Source-X — ядро подхватывает шестой канал через данные,
    без переписывания формул."""
    import shutil
    dst = str(tmp_path / "data_x")
    shutil.copytree(DATA_DIR, dst)
    with open(os.path.join(dst, "supply_sources.csv"), "a", encoding="utf-8") as f:
        f.write(
            "Source-X,Synthetic-X,50,5.0,0.20,0.60,3,3,month,"
            '"constant:0.95",2035,TEAM_ASSUMPTION,"extensibility test"\n'
        )
    case_x = load_case(dst)
    sx = case_x.source("Source-X")
    assert sx.capacity_t_per_year == 50.0
    plan = make_plan(
        orders=[("Source-X", "2035-01", 3.0)],
        reservations=[("Source-X", 2035, 40.0)],
    )
    result = run_plan(case_x, plan, Scenario.base())
    # lead time 3 мес → поставка 2035-04 (месячный лимит 40/12 = 3.33 ≥ 3.0);
    # TOP 0.6×40 = 24 > 3 → Q_pay = 24 → платёж 24×5.0
    assert result.deliveries.planned_by_source_period.get(("Source-X", "2035-04")) == pytest.approx(3.0)
    assert not [v for v in result.violations if v.rule_id == "CAPACITY_EXCEEDED"]
    r35 = _row(result.costs, 2035)
    assert r35.procurement_mln == pytest.approx(24.0 * 5.0)
    assert r35.reservation_mln == pytest.approx(40.0 * 0.20)


# ---------------------------------------------------------------------------
# Экспорт: CSV → повторная загрузка, числа совпадают
# ---------------------------------------------------------------------------

def test_export_csv_roundtrip(tmp_path):
    case = make_reference_case()
    plan = make_reference_plan()
    result = run_plan(case, plan, Scenario.base())
    out = str(tmp_path / "export")
    files = export_results(result, out, fmt="csv")
    names = {os.path.basename(f) for f in files}
    assert names == {
        "yearly_balance.csv", "source_schedule.csv", "inventory_trace.csv",
        "financial_breakdown.csv", "constraint_checks.csv", "risk_register.csv",
        "meta.json",
    }

    # 1) financial_breakdown: сверка трёх значений с внутренними числами
    with open(os.path.join(out, "financial_breakdown.csv"), encoding="utf-8") as f:
        fin_rows = list(csv.DictReader(f))
    row2035 = next(r for r in fin_rows if r["year"] == "2035")
    internal = _row(result.costs, 2035)
    assert float(row2035["procurement_mln"]) == pytest.approx(internal.procurement_mln)
    assert float(row2035["reservation_mln"]) == pytest.approx(internal.reservation_mln)
    assert float(row2035["total_mln"]) == pytest.approx(internal.total_mln)
    # колонки — строго по result_format.json
    for col in ("capex_mln", "capex_cumulative_mln", "take_or_pay_extra_mln",
                "holding_mln", "fixed_opex_mln", "discounted_mln",
                "cost_per_served_t_mln"):
        assert col in row2035

    # 2) yearly_balance: i_end 2035-12 совпадает
    with open(os.path.join(out, "yearly_balance.csv"), encoding="utf-8") as f:
        yb_rows = list(csv.DictReader(f))
    y2035 = next(r for r in yb_rows if r["year"] == "2035")
    yb = next(y for y in result.service.yearly_balance if y.year == 2035)
    assert float(y2035["i_end_t"]) == pytest.approx(yb.i_end_t)
    assert float(y2035["sl_total"]) == pytest.approx(yb.sl_total)

    # 3) constraint_checks: passed-список полный, тип — true/false
    with open(os.path.join(out, "constraint_checks.csv"), encoding="utf-8") as f:
        cc_rows = list(csv.DictReader(f))
    assert len(cc_rows) == len(result.checks)
    assert {r["passed"] for r in cc_rows} <= {"true", "false"}

    # 4) meta.json: обязательные поля export.schema.json
    meta = json.load(open(os.path.join(out, "meta.json"), encoding="utf-8"))
    assert meta["scenario_id"] == "BASE"
    assert meta["plan_id"] == "reference-minimal"
    assert meta["assumptions_reference"]
    assert meta["engine_version"]
    assert meta["generated_at"]
    assert isinstance(meta["units"], dict)


def test_export_xlsx(tmp_path):
    case = make_reference_case()
    plan = make_reference_plan()
    result = run_plan(case, plan, Scenario.base())
    out = str(tmp_path / "xlsx")
    files = export_results(result, out, fmt="xlsx")
    assert len(files) == 1 and files[0].endswith("results.xlsx")
    assert os.path.getsize(files[0]) > 0


def test_export_bad_format_raises_russian(tmp_path):
    case = make_reference_case()
    plan = make_reference_plan()
    result = run_plan(case, plan, Scenario.base())
    with pytest.raises(ValueError) as e:
        export_results(result, str(tmp_path / "bad"), fmt="parquet")
    assert "parquet" in str(e.value)


# ---------------------------------------------------------------------------
# persistence: save/load идемпотентны, результат тот же
# ---------------------------------------------------------------------------

def test_save_load_plan_idempotent(tmp_path):
    plan = make_reference_plan()
    plan.decisions.emergency_contract = EmergencyContract(
        reserved_capacity_t_per_year=40.0, activation_lead_days=42.0,
        coverage_volume_t=5.0, notes_ru="договорный резерв E",
    )
    p1 = str(tmp_path / "plan1.json")
    save_plan(plan, p1)
    loaded = load_saved_plan(p1)
    assert loaded == plan  # датаклассы равны
    p2 = str(tmp_path / "plan2.json")
    save_plan(loaded, p2)
    assert open(p1, encoding="utf-8").read() == open(p2, encoding="utf-8").read()


def test_saved_plan_same_result(tmp_path):
    """Сохранённый план повторно открывается и даёт тот же результат."""
    case = make_reference_case()
    plan = make_reference_plan()
    r1 = run_plan(case, plan, Scenario.base())
    p = str(tmp_path / "ref.json")
    save_plan(plan, p)
    r2 = run_plan(case, load_saved_plan(p), Scenario.base())
    for y in range(2035, 2041):
        assert _row(r1.costs, y).total_mln == pytest.approx(_row(r2.costs, y).total_mln)
    assert len(r1.checks) == len(r2.checks)
    assert r1.plan_id == r2.plan_id


# ---------------------------------------------------------------------------
# compare_scenarios
# ---------------------------------------------------------------------------

def test_compare_scenarios_deltas():
    case = load_case(DATA_DIR)
    plan = load_plan(os.path.join(WP2_DIR, "plans", "S10.json"))
    stress = load_scenario(os.path.join(CONFIGS_DIR, "mandatory_stress.yaml"))
    base = run_plan(case, plan, Scenario.base())
    st = run_plan(case, plan, stress)
    comp = compare_scenarios({"BASE": base, "MANDATORY_STRESS": st})
    rows = {r.get("scenario_id"): r for r in comp.rows if r["row_type"] == "scenario"}
    deltas = [r for r in comp.rows if r["row_type"] == "delta"]
    assert "BASE" in rows and "MANDATORY_STRESS" in rows
    assert len(deltas) == 1
    d = deltas[0]
    expected_delta = rows["MANDATORY_STRESS"]["total_mln"] - rows["BASE"]["total_mln"]
    assert d["delta_total_mln"] == pytest.approx(expected_delta)
    # стресс дороже BASE (спрос ×1.15, цены ×1.25)
    assert d["delta_total_mln"] > 0


# ---------------------------------------------------------------------------
# Адаптер scenario_parameters (D3.4)
# ---------------------------------------------------------------------------

def test_adapter_original_value_mismatch_fails():
    """Override с неверным исходным значением → ValueError по-русски."""
    case = load_case(DATA_DIR)
    sc = Scenario(
        scenario_id="TEAM_BAD",
        scenario_parameters={
            "investment_capex_override": {
                "investment_id": "LUNAR_ISRU",
                "original_capex_mln": 1000,  # неверно: в CASE_INPUT 1250
                "new_capex_mln": 1200,
            }
        },
    )
    with pytest.raises(ValueError) as e:
        apply_scenario_parameters(case, sc)
    msg = str(e.value)
    assert "1250" in msg and "1000" in msg and "LUNAR_ISRU" in msg
    # исходный case не мутирован
    assert case.scenario_journal == []


def test_adapter_capex_override_journal_and_effect():
    """TEAM_CAPEX_OVERRUN: CAPEX 1250 → 1437.5, журнал, копия case."""
    case = load_case(DATA_DIR)
    sc = load_scenario(os.path.join(TEAM_DIR, "TEAM_CAPEX_OVERRUN.yaml"))
    plan = load_plan(os.path.join(WP2_DIR, "plans", "S10.json"))
    c2, p2 = apply_scenario_parameters(case, sc, plan)
    assert c2 is not case
    assert c2.scenario_journal and "1437.5" in c2.scenario_journal[0]
    opt = next(o for o in c2.investment_options if o.investment_id == "LUNAR_ISRU")
    assert opt.total_capex_mln == pytest.approx(1437.5)
    # исходный не изменён
    opt0 = next(o for o in case.investment_options if o.investment_id == "LUNAR_ISRU")
    assert opt0.total_capex_mln == pytest.approx(1250.0)
    result = run_plan(c2, p2 or plan, sc)
    assert sum(r.capex_mln for r in result.costs.financial_breakdown) == pytest.approx(1617.5)


def test_adapter_commissioning_override():
    """TEAM_ISRU_DELAY: ввод D 2038 → 2039 + доля 2038 = 0."""
    case = load_case(DATA_DIR)
    sc = load_scenario(os.path.join(TEAM_DIR, "TEAM_ISRU_DELAY.yaml"))
    plan = load_plan(os.path.join(WP2_DIR, "plans", "S10.json"))
    c2, p2 = apply_scenario_parameters(case, sc, plan)
    assert c2.source("D").available_from_year == 2039
    assert c2.actual_delivery_share_override[("D", 2038)] == 0.0
    result = run_plan(c2, p2 or plan, sc)
    # поставок D в 2038 нет
    d38 = [v for (s, p), v in result.deliveries.actual_by_source_period.items()
           if s == "D" and p.startswith("2038")]
    assert all(v == pytest.approx(0.0) for v in d38)


def test_adapter_storage_loss_override():
    """TEAM_ZBO_FAILURE: потери ZBO 2038 = 0.045 вместо 0.012."""
    case = load_case(DATA_DIR)
    sc = load_scenario(os.path.join(TEAM_DIR, "TEAM_ZBO_FAILURE.yaml"))
    plan = load_plan(os.path.join(WP2_DIR, "plans", "S10.json"))
    c2, p2 = apply_scenario_parameters(case, sc, plan)
    base_res = run_plan(case, plan, Scenario.base())
    team_res = run_plan(c2, p2 or plan, sc)
    losses_base = sum(m.losses_t for m in base_res.inventory.monthly_balance
                      if m.period.startswith("2038") and m.storage_mode == "ZBO")
    losses_team = sum(m.losses_t for m in team_res.inventory.monthly_balance
                      if m.period.startswith("2038") and m.storage_mode == "ZBO")
    assert losses_team > losses_base


def test_adapter_inventory_shock_mmod():
    """TEAM_MMOD: потеря 25% запаса в 2038-07 (отдельный механизм, не потери хранения)."""
    case = load_case(DATA_DIR)
    sc = load_scenario(os.path.join(TEAM_DIR, "TEAM_MMOD.yaml"))
    plan = load_plan(os.path.join(WP2_DIR, "plans", "S10.json"))
    c2, p2 = apply_scenario_parameters(case, sc, plan)
    base_res = run_plan(case, plan, Scenario.base())
    team_res = run_plan(c2, p2 or plan, sc)
    jul_base = next(m for m in base_res.inventory.monthly_balance if m.period == "2038-07")
    jul_team = next(m for m in team_res.inventory.monthly_balance if m.period == "2038-07")
    assert jul_team.i_end_t < jul_base.i_end_t
    shock = [v for v in team_res.inventory.violations
             if v.rule_id == "INVENTORY_SHOCK_APPLIED" and v.period == "2038-07"]
    assert shock and shock[0].actual == pytest.approx(0.25 * jul_base.i_start_t, rel=0.02)


def test_adapter_plan_investment_shift():
    """TEAM_EARTH_NEW_EXERCISE_DELAY: платёж exercise сдвинут на 12 мес в копии плана."""
    case = load_case(DATA_DIR)
    sc = load_scenario(os.path.join(TEAM_DIR, "TEAM_EARTH_NEW_EXERCISE_DELAY.yaml"))
    plan = load_plan(os.path.join(WP2_DIR, "plans", "S14.json"))
    c2, p2 = apply_scenario_parameters(case, sc, plan)
    assert p2 is not None and p2 is not plan
    orig = next(i for i in plan.decisions.investments
                if i.investment_id == "EARTH_NEW" and i.action == "exercise_option")
    moved = next(i for i in p2.decisions.investments
                 if i.investment_id == "EARTH_NEW" and i.action == "exercise_option")
    assert moved.payment_date != orig.payment_date
    # исходный план не мутирован
    assert next(i for i in plan.decisions.investments
                if i.investment_id == "EARTH_NEW"
                and i.action == "exercise_option").payment_date == orig.payment_date


def test_adapter_price_override_geo():
    """TEAM_GEO_CHANNEL_A (D8.4): цена меняется только через variable_price_multiplier
    (×1.2 в 2038–2039), скалярный 'event' — метаданные, адаптер их журналирует.
    В остальные годы цена контрольная 6.2."""
    case = load_case(DATA_DIR)
    sc = load_scenario(os.path.join(TEAM_DIR, "TEAM_GEO_CHANNEL_A.yaml"))
    c2, _ = apply_scenario_parameters(case, sc)
    eff = apply_scenario(c2, sc)
    assert eff.effective_price_mln_per_t[("A", 2038)] == pytest.approx(6.2 * 1.2)
    assert eff.effective_price_mln_per_t[("A", 2039)] == pytest.approx(6.2 * 1.2)
    assert eff.effective_price_mln_per_t[("A", 2035)] == pytest.approx(6.2)
    assert any("event" in j for j in c2.scenario_journal)
    assert case.effective_price_mln_per_t[("A", 2035)] == pytest.approx(6.2)


def test_adapter_unknown_override_fails():
    case = load_case(DATA_DIR)
    sc = Scenario(scenario_id="TEAM_UNKNOWN",
                  scenario_parameters={"magic_override": {"x": 1}})
    with pytest.raises(ValueError) as e:
        apply_scenario_parameters(case, sc)
    assert "magic_override" in str(e.value)


def test_all_team_scenarios_runnable():
    """Все 10 TEAM-сценариев WP3 прогоняются через адаптер + run_plan."""
    case = load_case(DATA_DIR)
    plan = load_plan(os.path.join(WP2_DIR, "plans", "S14.json"))
    n = 0
    for name in sorted(os.listdir(TEAM_DIR)):
        sc = load_scenario(os.path.join(TEAM_DIR, name))
        c2, p2 = apply_scenario_parameters(case, sc, plan)
        result = run_plan(c2, p2 or plan, sc)
        assert len(result.costs.financial_breakdown) == 6
        n += 1
    assert n == 10


# ---------------------------------------------------------------------------
# evaluate_risks
# ---------------------------------------------------------------------------

def test_evaluate_risks_collects_consequences():
    case = load_case(DATA_DIR)
    plan = load_plan(os.path.join(WP2_DIR, "plans", "S10.json"))
    base = run_plan(case, plan, Scenario.base())
    scenarios = [
        load_scenario(os.path.join(TEAM_DIR, "TEAM_CAPEX_OVERRUN.yaml")),
        load_scenario(os.path.join(TEAM_DIR, "TEAM_ISRU_DELAY.yaml")),
    ]
    report = evaluate_risks(case, plan, base, scenarios)
    assert len(report.risk_register) == 2
    by_id = {e.risk_id: e for e in report.risk_register}
    capex_entry = by_id["TEAM_CAPEX_OVERRUN"]
    # +187.5 млн CAPEX (дисконтированных меньше)
    assert capex_entry.consequence_mln > 0
    isru_entry = by_id["TEAM_ISRU_DELAY"]
    assert isru_entry.consequence_mln != 0 or isru_entry.consequence_t != 0
    assert "сценарный подход" in isru_entry.probability_basis_ru


def test_evaluate_risks_marks_unexecutable_not_zero():
    """Неприменимый override → запись «НЕ ИСПОЛНЕН», не нули."""
    case = load_case(DATA_DIR)
    plan = load_plan(os.path.join(WP2_DIR, "plans", "S10.json"))
    base = run_plan(case, plan, Scenario.base())
    bad = Scenario(
        scenario_id="TEAM_BROKEN",
        scenario_parameters={
            "investment_capex_override": {
                "investment_id": "ZBO", "original_capex_mln": 1.0,
                "new_capex_mln": 2.0,
            }
        },
    )
    report = evaluate_risks(case, plan, base, [bad])
    entry = report.risk_register[0]
    assert "НЕ ИСПОЛНЕН" in entry.probability_basis_ru
