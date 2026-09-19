"""Приёмочные проверки WP4 wave 2 на публичной границе UI ↔ ядро."""

from __future__ import annotations

import csv
from copy import deepcopy
import io
import json
from pathlib import Path
import zipfile

import pytest

from app.services import (
    ROOT,
    available_scenarios,
    contracts_json,
    engine_available,
    export_core_archive,
    get_run_result,
    load_plan_from_catalog,
    load_plan_json,
    run_geo_scenario,
    violation_count,
)


@pytest.fixture(scope="module")
def s10() -> dict:
    return load_plan_from_catalog("wp2::S10.json")


def _totals(result: dict) -> tuple[float, float, float, int]:
    years = result["yearly_balance"]
    return (
        sum(row["delivered_t"] for row in years),
        sum(row["shortage_t"] for row in years),
        sum(row["total_mln"] for row in result["financial_breakdown"]),
        violation_count(result),
    )


def test_engine_and_all_team_scenarios_are_available(s10: dict) -> None:
    assert engine_available()
    scenarios = available_scenarios()
    assert scenarios[:2] == ("BASE", "MANDATORY_STRESS")
    assert len([item for item in scenarios if item.startswith("TEAM_")]) == 10
    for scenario_id in scenarios:
        result = get_run_result(scenario_id, s10)
        assert len(result["yearly_balance"]) == 6
        assert len(result["financial_breakdown"]) == 6


def test_passed_checks_come_from_core(s10: dict) -> None:
    checks = get_run_result("BASE", s10)["constraint_checks"]
    assert any(item["passed"] for item in checks)
    assert any(not item["passed"] for item in checks)
    assert all("message_ru" in item for item in checks)


def test_two_decision_examples_change_real_results(s10: dict) -> None:
    before = _totals(get_run_result("BASE", s10))

    order_and_reserve = deepcopy(s10)
    for row in order_and_reserve["decisions"]["supply_orders"]:
        if row["source_id"] == "A" and row["period"].startswith("2035-"):
            row["ordered_volume_t"] = 0.0
    next(
        row for row in order_and_reserve["decisions"]["capacity_reservations"]
        if row["source_id"] == "A" and row["year"] == 2035
    )["reserved_capacity_t_per_year"] = 80.0
    after_supply = _totals(get_run_result("BASE", order_and_reserve))
    assert after_supply != before
    assert after_supply[:3] != before[:3]
    assert after_supply[3] != before[3]

    no_zbo = deepcopy(s10)
    no_zbo["decisions"]["investments"] = [
        row for row in no_zbo["decisions"]["investments"]
        if row["investment_id"] != "ZBO"
    ]
    after_investment = _totals(get_run_result("BASE", no_zbo))
    assert after_investment != before
    assert after_investment[2] != before[2]


def test_five_ui_values_equal_core_csv(s10: dict) -> None:
    result = get_run_result("BASE", s10)
    payload = export_core_archive("BASE", s10, "csv")
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        yearly = list(csv.DictReader(io.TextIOWrapper(
            archive.open("yearly_balance.csv"), encoding="utf-8-sig"
        )))
        finance = list(csv.DictReader(io.TextIOWrapper(
            archive.open("financial_breakdown.csv"), encoding="utf-8-sig"
        )))
    ui_year = result["yearly_balance"][0]
    ui_finance = result["financial_breakdown"][0]
    assert float(yearly[0]["demand_total_t"]) == pytest.approx(ui_year["demand_total_t"])
    assert float(yearly[0]["delivered_t"]) == pytest.approx(ui_year["delivered_t"])
    assert float(yearly[0]["shortage_t"]) == pytest.approx(ui_year["shortage_t"])
    assert float(yearly[0]["sl_total"]) == pytest.approx(ui_year["sl_total"])
    assert float(finance[0]["total_mln"]) == pytest.approx(ui_finance["total_mln"])


def test_geo_restore_keeps_base_byte_identical(s10: dict) -> None:
    before = json.dumps(
        get_run_result("BASE", s10), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    geo = run_geo_scenario(s10, "Тестовое событие", "A", 1.2, 2038, 2039)
    assert geo["scenario_id"] == "TEAM_GEO"
    after = json.dumps(
        get_run_result("BASE", s10), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    assert after == before


def test_contract_registry_and_invalid_plans_are_readable(s10: dict) -> None:
    registry = json.loads(contracts_json(s10["plan_id"], [{"Канал": "A", "Объём, т": 10.0}]))
    assert registry["plan_id"] == "S10"
    assert registry["contracts"][0]["Канал"] == "A"

    invalid_dir = ROOT / "tests" / "examples" / "invalid_plan_examples"
    for path in sorted(invalid_dir.glob("*.json")):
        with pytest.raises(ValueError) as caught:
            load_plan_json(path.read_bytes())
        assert str(caught.value)
        assert any(token in str(caught.value) for token in ("период", "Параметр", "Резервирование", "Заказ"))
