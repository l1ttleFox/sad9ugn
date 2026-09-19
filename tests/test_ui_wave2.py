"""Приёмочные проверки WP4 wave 2 (финальное обновление) на FINAL-планах WP2."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from copy import deepcopy
from pathlib import Path

import pytest

from app.services import (
    INFORMATIONAL_RULES,
    ROOT,
    available_scenarios,
    comparison_tables,
    contracts_json,
    core_risk_register,
    engine_available,
    export_core_archive,
    final_plan_files,
    get_run_result,
    informational_checks,
    load_contracts_from_catalog,
    load_plan_from_catalog,
    load_plan_json,
    run_geo_scenario,
    save_plan_to_catalog,
    violation_count,
    wp3_published_risk_register,
)


@pytest.fixture(scope="module")
def final_base() -> dict:
    return load_plan_from_catalog("FINAL_BASE.json")


@pytest.fixture(scope="module")
def final_stress() -> dict:
    return load_plan_from_catalog("FINAL_STRESS.json")


def _totals(result: dict) -> tuple[float, float, float, int]:
    years = result["yearly_balance"]
    return (
        round(sum(row["delivered_t"] for row in years), 4),
        round(sum(row["shortage_t"] for row in years), 4),
        round(sum(row["total_mln"] for row in result["financial_breakdown"]), 4),
        violation_count(result),
    )


def test_final_plans_autodiscovered() -> None:
    """Оба FINAL-плана автообнаруживаются в results/plans/ и предлагаются кнопками."""
    finals = {item["plan_id"]: item for item in final_plan_files()}
    assert "FINAL_BASE" in finals and "FINAL_STRESS" in finals
    assert finals["FINAL_BASE"]["scenario_id"] == "BASE"
    assert finals["FINAL_STRESS"]["scenario_id"] == "MANDATORY_STRESS"
    # S10-fallback не показывается, пока FINAL опубликован
    assert all("предварительный" not in item["label"] for item in finals.values())


def test_engine_and_all_team_scenarios_are_available(final_base: dict) -> None:
    assert engine_available()
    scenarios = available_scenarios()
    assert scenarios[:2] == ("BASE", "MANDATORY_STRESS")
    assert len([item for item in scenarios if item.startswith("TEAM_")]) == 10
    for scenario_id in scenarios:
        result = get_run_result(scenario_id, final_base)
        assert len(result["yearly_balance"]) == 6
        assert len(result["financial_breakdown"]) == 6


def test_final_base_zero_hard_violations(final_base: dict) -> None:
    """FINAL_BASE при открытии: 0 hard-нарушений (после D8)."""
    result = get_run_result("BASE", final_base)
    checks = result["constraint_checks"]
    assert all("passed" in item and "message_ru" in item for item in checks)
    assert any(item["passed"] for item in checks)
    assert violation_count(result) == 0
    assert not [item for item in checks if not item["passed"]]
    assert result["plan_id"] == "FINAL_BASE"
    assert result["scenario_id"] == "BASE"


def test_final_stress_zero_hard_violations(final_stress: dict) -> None:
    result = get_run_result("MANDATORY_STRESS", final_stress)
    assert violation_count(result) == 0
    assert result["plan_id"] == "FINAL_STRESS"
    assert result["scenario_id"] == "MANDATORY_STRESS"


def test_informational_check_not_hard_violation(final_base: dict) -> None:
    """INVENTORY_SHOCK_APPLIED — информационная запись, не hard-нарушение (D8.3)."""
    assert "INVENTORY_SHOCK_APPLIED" in INFORMATIONAL_RULES
    result = get_run_result("TEAM_MMOD", final_base)
    info = informational_checks(result)
    assert info, "TEAM_MMOD должен порождать информационную запись шока"
    assert all(item["rule_id"] == "INVENTORY_SHOCK_APPLIED" for item in info)
    assert violation_count(result) == len(
        [c for c in result["constraint_checks"]
         if not c["passed"] and c["rule_id"] not in INFORMATIONAL_RULES])


def test_two_decision_examples_change_real_results(final_base: dict) -> None:
    """Заказ/резерв и инвестиция меняют баланс, расходы и реестр нарушений."""
    before = _totals(get_run_result("BASE", final_base))
    assert before == (1404.173, 0.0, 12411.7137, 0)

    order_and_reserve = deepcopy(final_base)
    for row in order_and_reserve["decisions"]["supply_orders"]:
        if row["source_id"] == "A" and str(row["period"]).startswith("2035"):
            row["ordered_volume_t"] = 0.0
    next(
        row for row in order_and_reserve["decisions"]["capacity_reservations"]
        if row["source_id"] == "A" and row["year"] == 2035
    )["reserved_capacity_t_per_year"] = 80.0
    after_supply = _totals(get_run_result("BASE", order_and_reserve))
    assert after_supply != before
    assert after_supply[1] > 0 and after_supply[3] > 0

    no_zbo = deepcopy(final_base)
    no_zbo["decisions"]["investments"] = [
        row for row in no_zbo["decisions"]["investments"]
        if row["investment_id"] != "ZBO"
    ]
    after_investment = _totals(get_run_result("BASE", no_zbo))
    assert after_investment != before
    assert after_investment[2] != before[2]
    assert after_investment[3] > 0


def test_scenario_switching_and_core_comparison(final_base: dict) -> None:
    """BASE↔MANDATORY_STRESS одного плана; сравнение считает compare_scenarios ядра."""
    base = get_run_result("BASE", final_base)
    stress = get_run_result("MANDATORY_STRESS", final_base)
    assert stress["scenario_id"] == "MANDATORY_STRESS"
    summary, deltas = comparison_tables(final_base, ("BASE", "MANDATORY_STRESS"))
    assert [row["Сценарий"] for row in summary] == ["BASE", "MANDATORY_STRESS"]
    assert summary[0]["Нарушения, шт."] == 0
    assert deltas and deltas[0]["Сценарий (относительно BASE)"] == "MANDATORY_STRESS"
    ui_total_base = round(sum(x["total_mln"] for x in base["financial_breakdown"]), 2)
    assert summary[0]["Расходы, млн у.е."] == pytest.approx(ui_total_base, abs=0.01)


def test_five_ui_values_equal_core_csv(final_base: dict) -> None:
    """Пять чисел FINAL_BASE 2035: UI = CSV экспорта ядра."""
    result = get_run_result("BASE", final_base)
    payload = export_core_archive("BASE", final_base, "csv")
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        meta = json.loads(archive.read("export_meta.json"))
        yearly = list(csv.DictReader(io.TextIOWrapper(
            archive.open("yearly_balance.csv"), encoding="utf-8-sig")))
        finance = list(csv.DictReader(io.TextIOWrapper(
            archive.open("financial_breakdown.csv"), encoding="utf-8-sig")))
    assert meta["scenario_id"] == "BASE" and meta["plan_id"] == "FINAL_BASE"
    assert meta["units"] and meta["assumptions_reference"]
    assert meta["meta"]["engine_version"] != "MOCK"
    ui_year = result["yearly_balance"][0]
    ui_finance = result["financial_breakdown"][0]
    assert float(yearly[0]["demand_total_t"]) == pytest.approx(ui_year["demand_total_t"])
    assert float(yearly[0]["delivered_t"]) == pytest.approx(ui_year["delivered_t"])
    assert float(yearly[0]["sl_total"]) == pytest.approx(ui_year["sl_total"])
    assert float(yearly[0]["shortage_t"]) == pytest.approx(ui_year["shortage_t"])
    assert float(finance[0]["total_mln"]) == pytest.approx(ui_finance["total_mln"])


def test_xlsx_export_same_tables(final_base: dict) -> None:
    payload = export_core_archive("BASE", final_base, "xlsx")
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = set(archive.namelist())
        assert "results.xlsx" in names and "export_meta.json" in names


def test_save_reopen_reproduces_result_with_contracts(final_base: dict, tmp_path: Path) -> None:
    """Сохранение плана + <plan_id>_contracts.json; повторное открытие воспроизводит расчёт."""
    contracts = [{"Контрагент": "Earth-Core", "Канал": "A", "Объём, т": 11.667}]
    filename = save_plan_to_catalog(final_base, "WP4_TEST_TMP", contracts)
    try:
        assert filename == "WP4_TEST_TMP.json"
        saved = ROOT / "results" / "plans" / "WP4_TEST_TMP.json"
        saved_contracts = ROOT / "results" / "plans" / "WP4_TEST_TMP_contracts.json"
        assert saved.exists() and saved_contracts.exists()
        loaded = load_plan_from_catalog("WP4_TEST_TMP.json")
        rows = load_contracts_from_catalog("WP4_TEST_TMP.json")
        assert rows == contracts
        before = get_run_result("BASE", final_base)
        after = get_run_result("BASE", loaded)
        for key in ("monthly_balance", "yearly_balance", "source_schedule",
                    "inventory_trace", "financial_breakdown", "constraint_checks"):
            assert json.dumps(before[key], sort_keys=True) == json.dumps(after[key], sort_keys=True)
        assert after["plan_id"] == "WP4_TEST_TMP"
    finally:
        (ROOT / "results" / "plans" / "WP4_TEST_TMP.json").unlink(missing_ok=True)
        (ROOT / "results" / "plans" / "WP4_TEST_TMP_contracts.json").unlink(missing_ok=True)


def test_geo_restore_keeps_base_byte_identical(final_base: dict) -> None:
    before = json.dumps(
        get_run_result("BASE", final_base), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    geo = run_geo_scenario(final_base, "Тестовое событие", "A", 1.2, 2038, 2039)
    assert geo["scenario_id"] == "TEAM_GEO"
    after = json.dumps(
        get_run_result("BASE", final_base), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    assert after == before


def test_risk_register_from_core_not_static(final_base: dict) -> None:
    """Риски TEAM_* считаются ядром для текущего плана; статические цифры WP3 не подмешиваются."""
    rows = core_risk_register("BASE", final_base)
    assert len(rows) == 10
    assert {row["scenario_id"] for row in rows} == {
        item for item in available_scenarios() if item.startswith("TEAM_")}
    assert any(row["consequence_t"] > 0 for row in rows)
    # опубликованный реестр WP3 доступен отдельным источником, если существует
    assert isinstance(wp3_published_risk_register(), list)


def test_contract_registry_and_invalid_plans_are_readable(final_base: dict) -> None:
    registry = json.loads(contracts_json(final_base["plan_id"], [{"Канал": "A", "Объём, т": 10.0}]))
    assert registry["plan_id"] == "FINAL_BASE"
    assert registry["contracts"][0]["Канал"] == "A"

    invalid_dir = ROOT / "tests" / "examples" / "invalid_plan_examples"
    for path in sorted(invalid_dir.glob("*.json")):
        with pytest.raises(ValueError) as caught:
            load_plan_json(path.read_bytes())
        assert str(caught.value)
        assert any(token in str(caught.value) for token in ("период", "Параметр", "Резервирование", "Заказ"))
