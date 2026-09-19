"""Тесты приёмки WP3 волны 2 (prompt_wave2.md §Критерии приёмки).

Все проверки — на ядре (run_plan), план S10 (до FINAL), CASE_INPUT не
меняется. Запуск: python -m pytest tests/test_wp3_wave2.py -q
"""

from __future__ import annotations

import csv
import os
import sys

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO, "src"))
sys.path.insert(0, os.path.join(REPO, "ai_workstreams", "WP3_stress_risk", "wave2"))

from engine import (  # noqa: E402
    apply_scenario_parameters,
    load_case,
    load_plan,
    load_scenario,
    run_plan,
)
from engine.models import Scenario  # noqa: E402
import wp3lib  # noqa: E402

DATA = os.path.join(REPO, "data")
PLANS = os.path.join(REPO, "ai_workstreams", "WP2_strategy_economics", "plans")
TEAM = os.path.join(REPO, "ai_workstreams", "WP3_stress_risk", "configs", "team")
RESULTS = os.path.join(REPO, "results")


@pytest.fixture(scope="module")
def case_plan():
    return load_case(DATA), load_plan(os.path.join(PLANS, "S10.json"))


# ---------------------------------------------------------------------------
# Критерий 1: mandatory применён точно по yaml; 55/75 без reliability
# ---------------------------------------------------------------------------

def test_mandatory_multipliers_exactly_from_yaml(case_plan):
    case, plan = case_plan
    sc = load_scenario(os.path.join(REPO, "configs", "mandatory_stress.yaml"))
    r = run_plan(case, plan, sc)
    # спрос 2038: 250×1.15 = 287.5; критический 170×1.15 = 195.5
    yb = {y.year: y for y in r.service.yearly_balance}
    assert yb[2038].demand_total_t == pytest.approx(287.5)
    assert yb[2038].demand_critical_t == pytest.approx(195.5)
    # 2035–2037 без изменений
    assert yb[2035].demand_total_t == pytest.approx(100.0)
    assert yb[2037].demand_critical_t == pytest.approx(135.0)
    # цена A 2038 = 6.2×1.25; 2040 = 6.2 (множитель только 2038–2039)
    assert r.case.effective_price_mln_per_t[("A", 2038)] == pytest.approx(7.75)
    assert r.case.effective_price_mln_per_t[("B", 2039)] == pytest.approx(8.9 * 1.25)
    assert r.case.effective_price_mln_per_t[("A", 2040)] == pytest.approx(6.2)
    # reservation rate и CAPEX не меняются (notes yaml)
    assert r.case.source("A").reservation_rate_mln_per_t_year_capacity == 0.45


def test_isru_shares_not_multiplied_by_reliability(case_plan):
    """55%/75% — ФАКТИЧЕСКИЕ доли: actual/planned == share, НЕ share×reliability
    (reliability D: 2038:0.78, 2039:0.90, 2040:0.93)."""
    case, plan = case_plan
    sc = load_scenario(os.path.join(REPO, "configs", "mandatory_stress.yaml"))
    r = run_plan(case, plan, sc)
    for year, share, rel in ((2038, 0.55, 0.78), (2039, 0.75, 0.90), (2040, 1.0, 0.93)):
        planned = sum(v for (s, p), v in r.deliveries.planned_by_source_period.items()
                      if s == "D" and p.startswith(str(year)))
        actual = sum(v for (s, p), v in r.deliveries.actual_by_source_period.items()
                     if s == "D" and p.startswith(str(year)))
        assert planned > 0
        assert actual == pytest.approx(planned * share, abs=1e-9), (
            f"{year}: actual/planned должно быть ровно {share} (без reliability)")
        assert actual != pytest.approx(planned * share * rel, abs=1e-6)


def test_loss_ceiling_checks_present_only_where_enabled(case_plan):
    case, plan = case_plan
    r_base = run_plan(case, plan, load_scenario(os.path.join(REPO, "configs", "base.yaml")))
    r_mand = run_plan(case, plan, load_scenario(os.path.join(REPO, "configs", "mandatory_stress.yaml")))
    assert not [c for c in r_base.checks if c.rule_id == "STRESS_LOSS_LIMIT"]
    loss = [c for c in r_mand.checks if c.rule_id == "STRESS_LOSS_LIMIT"]
    assert {c.period for c in loss} == {"2038", "2039", "2040"}


# ---------------------------------------------------------------------------
# R01: MANDATORY_STRESS не смешан с TEAM без явного combined-сценария
# ---------------------------------------------------------------------------

def test_r01_is_explicit_combined_only():
    """Единственный сценарий, содержащий множители mandatory + долю D 0.40 —
    TEAM_ISRU_UNDERDELIVERY_COMBINED (явный combined); обычные TEAM-конфиги
    mandatory-множителей не содержат."""
    for name in os.listdir(TEAM):
        if not name.endswith(".yaml"):
            continue
        sc = load_scenario(os.path.join(TEAM, name))
        has_mand_demand = str(sc.demand_multiplier.get("2038", 1.0)) == "1.15"
        if name == "TEAM_ISRU_UNDERDELIVERY_COMBINED.yaml":
            assert has_mand_demand, "combined обязан содержать множители mandatory"
            assert sc.actual_delivery_share["Lunar-ISRU"]["2038"] == 0.40
            assert sc.loss_ceiling.get("enabled") is True
        else:
            assert not has_mand_demand, (
                f"{name}: MANDATORY_STRESS смешан с TEAM без combined-объявления")


def test_combined_share_040_applied_once(case_plan):
    """В combined доля D 2038 = 0.40 (не 0.55×0.40 и не ×reliability)."""
    case, plan = case_plan
    sc = load_scenario(os.path.join(TEAM, "TEAM_ISRU_UNDERDELIVERY_COMBINED.yaml"))
    r, _, _ = wp3lib.run_team(case, plan, sc)
    planned = sum(v for (s, p), v in r.deliveries.planned_by_source_period.items()
                  if s == "D" and p.startswith("2038"))
    actual = sum(v for (s, p), v in r.deliveries.actual_by_source_period.items()
                 if s == "D" and p.startswith("2038"))
    assert planned > 0
    assert actual == pytest.approx(planned * 0.40, abs=1e-9)


# ---------------------------------------------------------------------------
# Критерий 4: гео-модуль — до/после, экспорт, восстановление цен
# ---------------------------------------------------------------------------

def test_geo_single_application_and_restoration(case_plan):
    case, plan = case_plan
    sc = load_scenario(os.path.join(TEAM, "TEAM_GEO_CHANNEL_A.yaml"))
    # однократное применение: цена A 2038–2039 = 7.44, остальные годы 6.2
    clean = Scenario(scenario_id=sc.scenario_id,
                     variable_price_multiplier=sc.variable_price_multiplier)
    r = run_plan(case, plan, clean)
    assert r.case.effective_price_mln_per_t[("A", 2038)] == pytest.approx(7.44)
    assert r.case.effective_price_mln_per_t[("A", 2039)] == pytest.approx(7.44)
    assert r.case.effective_price_mln_per_t[("A", 2037)] == pytest.approx(6.2)
    assert r.case.effective_price_mln_per_t[("B", 2038)] == pytest.approx(8.9)
    # резервный тариф и CAPEX не затронуты
    assert r.case.source("A").reservation_rate_mln_per_t_year_capacity == 0.45

    # восстановление: повторная загрузка BASE = исходные числа
    r_before = run_plan(case, plan, Scenario.base())
    r_after = run_plan(load_case(DATA), load_plan(os.path.join(PLANS, "S10.json")),
                       Scenario.base())
    assert load_case(DATA).source("A").variable_cost_mln_per_t == 6.2
    assert [ (y.year, y.sl_total, y.shortage_t) for y in r_before.service.yearly_balance ] == \
           [ (y.year, y.sl_total, y.shortage_t) for y in r_after.service.yearly_balance ]
    assert sum(x.total_mln for x in r_before.costs.financial_breakdown) == \
        pytest.approx(sum(x.total_mln for x in r_after.costs.financial_breakdown))


def test_geo_combined_no_double_count(case_plan):
    case, plan = case_plan
    sc_m = load_scenario(os.path.join(REPO, "configs", "mandatory_stress.yaml"))
    combined = Scenario(
        scenario_id="TEAM_GEO_A_MANDATORY_COMBINED",
        demand_multiplier=dict(sc_m.demand_multiplier),
        critical_demand_multiplier=dict(sc_m.critical_demand_multiplier),
        variable_price_multiplier={
            "Earth-Core": {"2038": 1.25 * 1.20, "2039": 1.25 * 1.20},
            "Earth-Flex": {"2038": 1.25, "2039": 1.25},
        },
        actual_delivery_share=dict(sc_m.actual_delivery_share),
        loss_ceiling=dict(sc_m.loss_ceiling),
    )
    r = run_plan(case, plan, combined)
    assert r.case.effective_price_mln_per_t[("A", 2038)] == pytest.approx(6.2 * 1.25 * 1.20)
    assert r.case.effective_price_mln_per_t[("A", 2038)] != pytest.approx(6.2 * 1.25 * 1.20 * 1.20)


def test_geo_event_export_exists():
    path = os.path.join(RESULTS, "geopolitics", "geo_event.json")
    assert os.path.exists(path)
    import json
    ev = json.load(open(path, encoding="utf-8"))
    assert ev["event_id"] == "geo_channel_a_tariff"
    assert ev["original_price_mln_per_t"] == 6.2
    assert ev["new_price_mln_per_t"]["2038"] == 7.44
    assert ev["multiplier"] == 1.2
    assert "input_diff" in ev and "case_input_version_sha256" in ev


# ---------------------------------------------------------------------------
# Критерий 5: выгрузки совпадают с числами ядра
# ---------------------------------------------------------------------------

def test_exports_match_core_numbers(case_plan):
    case, plan = case_plan
    exp = os.path.join(RESULTS, "stress", "exports", "MANDATORY_STRESS")
    assert os.path.isdir(exp)
    r = run_plan(case, plan, load_scenario(os.path.join(REPO, "configs", "mandatory_stress.yaml")))
    with open(os.path.join(exp, "yearly_balance.csv"), encoding="utf-8") as f:
        rows = {int(row["year"]): row for row in csv.DictReader(f)}
    for y in r.service.yearly_balance:
        assert float(rows[y.year]["sl_total"]) == pytest.approx(y.sl_total)
        assert float(rows[y.year]["shortage_t"]) == pytest.approx(y.shortage_t)
    with open(os.path.join(exp, "financial_breakdown.csv"), encoding="utf-8") as f:
        frows = {int(row["year"]): row for row in csv.DictReader(f)}
    for fr in r.costs.financial_breakdown:
        assert float(frows[fr.year]["total_mln"]) == pytest.approx(fr.total_mln)
        assert float(frows[fr.year]["discounted_mln"]) == pytest.approx(fr.discounted_mln)


# ---------------------------------------------------------------------------
# Критерий 2: каждый риск имеет рассчитанное последствие и меру
# ---------------------------------------------------------------------------

def test_risk_register_complete():
    path = os.path.join(RESULTS, "risk_register.csv")
    assert os.path.exists(path)
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 10
    required = {"risk_id", "event", "cause", "affected_parameter", "period",
                "probability_basis_or_range", "physical_consequence",
                "financial_consequence", "service_consequence",
                "dependencies", "owner", "mitigation", "residual_consequence"}
    for row in rows:
        assert required <= set(row.keys())
        for col in required:
            assert str(row[col]).strip(), f"{row['risk_id']}: пустое поле {col}"


# ---------------------------------------------------------------------------
# Критерий 3: reverse-границы конкретны
# ---------------------------------------------------------------------------

def test_reverse_thresholds_concrete():
    path = os.path.join(RESULTS, "stress", "P02_reverse_thresholds.csv")
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) >= 2
    by_axis = {r["axis"]: r for r in rows}
    # спрос: конкретное число
    dem = next(v for k, v in by_axis.items() if "спроса" in k)
    assert float(dem["threshold"]) > 1.0
    # доля D: конкретное число
    shr = next(v for k, v in by_axis.items() if "доля D" in k)
    assert 0.0 < float(shr["threshold"]) < 1.0
    # цена: границы нет (физические лимиты от цены не зависят) — честно записано
    prc = next(v for k, v in by_axis.items() if "цены A" in k)
    assert "нет границы" in str(prc["threshold"])


def test_p04_grid_complete_and_min_nodes():
    path = os.path.join(RESULTS, "stress", "P04_grid_base.csv")
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 11 * 11 * 11
    broken = [r for r in rows if r["broken"] == "true"]
    assert broken, "в сетке должны быть ломающие узлы"
    nmin = min(float(r["norm"]) for r in broken)
    mins = [r for r in broken if float(r["norm"]) == nmin]
    assert mins  # минимум по норме существует и показан


# ---------------------------------------------------------------------------
# Адаптер D3.4: все 10 TEAM-сценариев исполняются (без «НЕ ИСПОЛНЕН»)
# ---------------------------------------------------------------------------

def test_all_team_scenarios_executed():
    case = load_case(DATA)
    plan = load_plan(os.path.join(PLANS, "S10.json"))
    for name in sorted(os.listdir(TEAM)):
        if not name.endswith(".yaml"):
            continue
        sc = load_scenario(os.path.join(TEAM, name))
        if sc.scenario_id in wp3lib.PRICE_EVENT_SCENARIOS:
            r, _, _ = wp3lib.run_team(case, plan, sc)
        else:
            r, _, journal = wp3lib.run_team(case, plan, sc)
            if sc.scenario_parameters:
                assert journal, f"{name}: журнал адаптера пуст"
        assert r.scenario_id == sc.scenario_id


def test_case_input_not_modified():
    """CASE_INPUT не менялся: sha256 файлов совпадает с зафиксированным."""
    import hashlib
    h = hashlib.sha256(open(os.path.join(DATA, "supply_sources.csv"), "rb").read()).hexdigest()
    assert h.startswith("311f37a5587fa161")
    h2 = hashlib.sha256(open(os.path.join(REPO, "configs", "mandatory_stress.yaml"), "rb").read()).hexdigest()
    # фиксируем текущее значение — тест защищает от случайной правки в будущем
    ref = os.path.join(REPO, "results", "geopolitics", "geo_event.json")
    import json
    ev = json.load(open(ref, encoding="utf-8"))
    assert ev["case_input_version_sha256"]["configs\\mandatory_stress.yaml"] == h2
