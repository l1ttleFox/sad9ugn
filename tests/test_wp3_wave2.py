"""Тесты приёмки WP3 волны 2 (prompt_wave2.md §Критерии приёмки,
REFRESH_WP3_AFTER_FINAL.md п.9) — на FINAL-планах.

Все проверки — на ядре (run_plan): BASE — results/plans/FINAL_BASE.json,
MANDATORY_STRESS — results/plans/FINAL_STRESS.json. CASE_INPUT не меняется.
Запуск: python -m pytest tests/test_wp3_wave2.py -q
"""

from __future__ import annotations

import csv
import json
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
PLANS = os.path.join(REPO, "results", "plans")
TEAM = os.path.join(REPO, "ai_workstreams", "WP3_stress_risk", "configs", "team")
RESULTS = os.path.join(REPO, "results")


@pytest.fixture(scope="module")
def case_plan():
    return (
        load_case(DATA),
        load_plan(os.path.join(PLANS, "FINAL_BASE.json")),
        load_plan(os.path.join(PLANS, "FINAL_STRESS.json")),
    )


# ---------------------------------------------------------------------------
# Критерий готовности: FINAL_BASE не имеет hard-нарушений
# ---------------------------------------------------------------------------

def test_final_base_clean(case_plan):
    case, plan_base, _ = case_plan
    r = run_plan(case, plan_base, load_scenario(os.path.join(REPO, "configs", "base.yaml")))
    sig = wp3lib.violation_signature(r)
    assert sig == set(), f"FINAL BASE имеет hard-нарушения: {sorted(sig)}"
    assert min(y.sl_total for y in r.service.yearly_balance) == pytest.approx(1.0)
    assert min(y.sl_critical for y in r.service.yearly_balance) == pytest.approx(1.0)


def test_final_stress_clean(case_plan):
    case, _, plan_stress = case_plan
    r = run_plan(case, plan_stress,
                 load_scenario(os.path.join(REPO, "configs", "mandatory_stress.yaml")))
    sig = wp3lib.violation_signature(r)
    assert sig == set(), f"FINAL STRESS имеет hard-нарушения: {sorted(sig)}"


# ---------------------------------------------------------------------------
# Критерий 1: mandatory применён точно по yaml; 55/75 без reliability
# ---------------------------------------------------------------------------

def test_mandatory_multipliers_exactly_from_yaml(case_plan):
    case, _, plan_stress = case_plan
    sc = load_scenario(os.path.join(REPO, "configs", "mandatory_stress.yaml"))
    r = run_plan(case, plan_stress, sc)
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
    (reliability D: 2038:0.78, 2039:0.90, 2040:0.93). Доказательство — в
    прогоне MANDATORY_STRESS (FINAL_STRESS)."""
    case, _, plan_stress = case_plan
    sc = load_scenario(os.path.join(REPO, "configs", "mandatory_stress.yaml"))
    r = run_plan(case, plan_stress, sc)
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
    case, plan_base, plan_stress = case_plan
    r_base = run_plan(case, plan_base,
                      load_scenario(os.path.join(REPO, "configs", "base.yaml")))
    r_mand = run_plan(case, plan_stress,
                      load_scenario(os.path.join(REPO, "configs", "mandatory_stress.yaml")))
    assert not [c for c in r_base.checks if c.rule_id == "STRESS_LOSS_LIMIT"]
    loss = [c for c in r_mand.checks if c.rule_id == "STRESS_LOSS_LIMIT"]
    assert {c.period for c in loss} == {"2038", "2039", "2040"}
    assert all(c.passed for c in loss), "потолок потерь 2% нарушен в FINAL STRESS"


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
    case, _, plan_stress = case_plan
    sc = load_scenario(os.path.join(TEAM, "TEAM_ISRU_UNDERDELIVERY_COMBINED.yaml"))
    r, _, _ = wp3lib.run_team(case, plan_stress, sc)
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
    case, plan_base, _ = case_plan
    sc = load_scenario(os.path.join(TEAM, "TEAM_GEO_CHANNEL_A.yaml"))
    # однократное применение: цена A 2038–2039 = 7.44, остальные годы 6.2
    r, _, journal = wp3lib.run_team(case, plan_base, sc)
    assert r.case.effective_price_mln_per_t[("A", 2038)] == pytest.approx(7.44)
    assert r.case.effective_price_mln_per_t[("A", 2039)] == pytest.approx(7.44)
    assert r.case.effective_price_mln_per_t[("A", 2037)] == pytest.approx(6.2)
    assert r.case.effective_price_mln_per_t[("B", 2038)] == pytest.approx(8.9)
    # D8.4: плоский price override удалён — event лишь метаданные (журнал)
    assert any("метаданные" in j for j in journal)
    # резервный тариф и CAPEX не затронуты
    assert r.case.source("A").reservation_rate_mln_per_t_year_capacity == 0.45

    # восстановление: повторная загрузка BASE = исходные числа
    r_before = run_plan(case, plan_base, Scenario.base())
    r_after = run_plan(load_case(DATA),
                       load_plan(os.path.join(PLANS, "FINAL_BASE.json")),
                       Scenario.base())
    assert load_case(DATA).source("A").variable_cost_mln_per_t == 6.2
    assert [(y.year, y.sl_total, y.shortage_t) for y in r_before.service.yearly_balance] == \
           [(y.year, y.sl_total, y.shortage_t) for y in r_after.service.yearly_balance]
    assert sum(x.total_mln for x in r_before.costs.financial_breakdown) == \
        pytest.approx(sum(x.total_mln for x in r_after.costs.financial_breakdown))


def test_geo_combined_no_double_count(case_plan):
    case, _, plan_stress = case_plan
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
    r = run_plan(case, plan_stress, combined)
    assert r.case.effective_price_mln_per_t[("A", 2038)] == pytest.approx(6.2 * 1.25 * 1.20)
    assert r.case.effective_price_mln_per_t[("A", 2038)] != pytest.approx(6.2 * 1.25 * 1.20 * 1.20)


def test_geo_event_export_exists():
    path = os.path.join(RESULTS, "geopolitics", "geo_event.json")
    assert os.path.exists(path)
    ev = json.load(open(path, encoding="utf-8"))
    assert ev["event_id"] == "geo_channel_a_tariff"
    assert ev["original_price_mln_per_t"] == 6.2
    assert ev["new_price_mln_per_t"]["2038"] == 7.44
    assert ev["multiplier"] == 1.2
    assert ev["single_application_ok"] is True
    assert ev["plan_id"] == "FINAL_BASE"
    assert "input_diff" in ev and "case_input_version_sha256" in ev
    summary = json.load(open(os.path.join(RESULTS, "geopolitics", "P05_summary.json"),
                             encoding="utf-8"))
    assert summary["restoration"]["ok"] is True


# ---------------------------------------------------------------------------
# Критерий 5: выгрузки совпадают с числами ядра (текущий run_plan)
# ---------------------------------------------------------------------------

def test_exports_match_core_numbers(case_plan):
    case, plan_base, plan_stress = case_plan
    exp = os.path.join(RESULTS, "stress", "exports", "MANDATORY_STRESS")
    assert os.path.isdir(exp)
    r = run_plan(case, plan_stress,
                 load_scenario(os.path.join(REPO, "configs", "mandatory_stress.yaml")))
    meta = json.load(open(os.path.join(exp, "meta.json"), encoding="utf-8"))
    assert meta["plan_id"] == "FINAL_STRESS"
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

    exp_b = os.path.join(RESULTS, "stress", "exports", "BASE")
    meta_b = json.load(open(os.path.join(exp_b, "meta.json"), encoding="utf-8"))
    assert meta_b["plan_id"] == "FINAL_BASE"
    rb = run_plan(case, plan_base, load_scenario(os.path.join(REPO, "configs", "base.yaml")))
    with open(os.path.join(exp_b, "yearly_balance.csv"), encoding="utf-8") as f:
        rows_b = {int(row["year"]): row for row in csv.DictReader(f)}
    for y in rb.service.yearly_balance:
        assert float(rows_b[y.year]["sl_total"]) == pytest.approx(y.sl_total)
        assert float(rows_b[y.year]["shortage_t"]) == pytest.approx(y.shortage_t)


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
        # последствие должно содержать числа (рассчитано ядром, не «на глаз»)
        assert any(ch.isdigit() for ch in row["physical_consequence"]), row["risk_id"]


def test_p03_all_risks_quantified():
    path = os.path.join(RESULTS, "stress", "P03_risks.csv")
    with open(path, encoding="utf-8") as f:
        rows = {r["risk_id"]: r for r in csv.DictReader(f)}
    assert len(rows) == 10
    for rid, r in rows.items():
        assert r["mitigation"].strip(), rid
        assert r["residual_new_violations"] != "", rid
        # R02/R08 (содержательные физические риски) закрыты мерой полностью
        if rid in ("R02", "R08"):
            assert int(r["residual_new_violations"]) == 0, rid


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
    for fname in ("P04_grid_base.csv", "P04_grid_mandatory.csv"):
        path = os.path.join(RESULTS, "stress", fname)
        with open(path, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 11 * 11 * 11
        broken = [r for r in rows if r["broken"] == "true"]
        assert broken, f"{fname}: в сетке должны быть ломающие узлы"
        nmin = min(float(r["norm"]) for r in broken)
        mins = [r for r in broken if float(r["norm"]) == nmin]
        assert mins  # минимум по норме существует и показан
    with open(os.path.join(RESULTS, "stress", "P04_grid_base.csv"),
              encoding="utf-8") as f:
        base_rows = list(csv.DictReader(f))
    assert all(r["plan_id"] == "FINAL_BASE" for r in base_rows)
    with open(os.path.join(RESULTS, "stress", "P04_grid_mandatory.csv"),
              encoding="utf-8") as f:
        mand_rows = list(csv.DictReader(f))
    assert all(r["plan_id"] == "FINAL_STRESS" for r in mand_rows)


# ---------------------------------------------------------------------------
# Адаптер D3.4: все 10 TEAM-сценариев исполняются (без «НЕ ИСПОЛНЕН»)
# ---------------------------------------------------------------------------

def test_all_team_scenarios_executed():
    case = load_case(DATA)
    plan = load_plan(os.path.join(PLANS, "FINAL_BASE.json"))
    plan_s = load_plan(os.path.join(PLANS, "FINAL_STRESS.json"))
    for name in sorted(os.listdir(TEAM)):
        if not name.endswith(".yaml"):
            continue
        sc = load_scenario(os.path.join(TEAM, name))
        p = plan_s if sc.scenario_id == "TEAM_ISRU_UNDERDELIVERY_COMBINED" else plan
        r, _, journal = wp3lib.run_team(case, p, sc)
        if sc.scenario_parameters:
            assert journal, f"{name}: журнал адаптера пуст"
        assert r.scenario_id == sc.scenario_id


# ---------------------------------------------------------------------------
# Информационные события не ранжируются как hard (D8.3)
# ---------------------------------------------------------------------------

def test_inventory_shock_is_info_not_hard():
    path = os.path.join(RESULTS, "stress", "P03_risks.csv")
    with open(path, encoding="utf-8") as f:
        rows = {r["risk_id"]: r for r in csv.DictReader(f)}
    r04 = rows["R04"]
    assert "INVENTORY_SHOCK_APPLIED" not in r04["new_violation_rules"]
    # шок учтён как информационное событие
    assert int(r04["info_events"]) >= 1


def test_case_input_not_modified():
    """CASE_INPUT не менялся: sha256 файлов совпадает с зафиксированным
    (нормализация LF/CRLF — D8.5)."""
    import hashlib
    raw = open(os.path.join(DATA, "supply_sources.csv"), "rb").read()
    h = hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()
    assert h == "182139c4870402024f540d0f010b4396db2fad77bf5a35449e04cbe584ef0977"
    raw2 = open(os.path.join(REPO, "configs", "mandatory_stress.yaml"), "rb").read()
    h2 = hashlib.sha256(raw2.replace(b"\r\n", b"\n")).hexdigest()
    # фиксируем текущее значение — тест защищает от случайной правки в будущем
    ref = os.path.join(REPO, "results", "geopolitics", "geo_event.json")
    ev = json.load(open(ref, encoding="utf-8"))
    assert ev["case_input_version_sha256"]["configs/mandatory_stress.yaml"] == h2


def test_final_plans_not_modified():
    """FINAL-планы не изменялись WP3: sha256 совпадает со значением в meta."""
    import hashlib
    for name in ("FINAL_BASE.json", "FINAL_STRESS.json"):
        p = os.path.join(PLANS, name)
        h = hashlib.sha256(open(p, "rb").read()).hexdigest()
        meta = json.load(open(os.path.join(RESULTS, "stress", "P01_meta.json"),
                              encoding="utf-8"))
        assert meta["plan_sha256"][name] == h
