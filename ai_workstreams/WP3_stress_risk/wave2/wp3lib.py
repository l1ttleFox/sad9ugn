"""Общая библиотека WP3 волны 2: загрузка входов, прогон сценариев, утилиты.

Правила (prompt_wave2.md, STRESS_PROTOCOL, решения D3):
- ядро, CASE_INPUT (data/**, configs/base.yaml, configs/mandatory_stress.yaml)
  НЕ изменяются;
- FINAL-планы WP2 не опубликованы → рабочий план S10.json («на S10, до FINAL»);
- один и тот же план для BASE и всех исследовательских прогонов (P01 §1);
- TEAM-сценарии — через адаптер ядра apply_scenario_parameters (D3.4);
- для R05/R10 (TEAM_PRICE_SPIKE_E / TEAM_GEO_CHANNEL_A) цена применяется
  ОДИН раз: в YAML событие продублировано (variable_price_multiplier +
  price-override в scenario_parameters) — одновременное применение обоих
  блоков даёт двойной начёт (баг конфигов WP3 волны 1, зафиксирован в
  REPORT_wave2). Используется год-точный блок variable_price_multiplier.
"""

from __future__ import annotations

import copy
import json
import os
import sys
from dataclasses import asdict
from typing import Any, Optional

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "src"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from engine import (  # noqa: E402
    apply_scenario_parameters,
    load_case,
    load_plan,
    load_scenario,
    run_plan,
)
from engine.models import (  # noqa: E402
    CaseData,
    Plan,
    RunResult,
    Scenario,
    SupplyOrder,
    CapacityReservation,
    Investment,
)

DATA_DIR = os.path.join(REPO, "data")
PLAN_PATH = os.path.join(
    REPO, "ai_workstreams", "WP2_strategy_economics", "plans", "S10.json"
)
TEAM_DIR = os.path.join(REPO, "ai_workstreams", "WP3_stress_risk", "configs", "team")
RESULTS = os.path.join(REPO, "results")

PLAN_LABEL = "S10, до FINAL"
WORKING_PLAN_NOTE = (
    "FINAL-планы WP2 (results/plans/FINAL_*.json) на момент расчёта не "
    "опубликованы — все результаты помечены «на S10, до FINAL»"
)

# Сценарии-ценовые события: применяем ТОЛЬКО variable_price_multiplier
# (один раз); price-override в scenario_parameters игнорируем — иначе
# двойной начёт (см. docstring).
PRICE_EVENT_SCENARIOS = {"TEAM_PRICE_SPIKE_E", "TEAM_GEO_CHANNEL_A"}


def base_case() -> CaseData:
    return load_case(DATA_DIR)


def base_plan() -> Plan:
    return load_plan(PLAN_PATH)


def base_scenario() -> Scenario:
    return load_scenario(os.path.join(REPO, "configs", "base.yaml"))


def mandatory_scenario() -> Scenario:
    return load_scenario(os.path.join(REPO, "configs", "mandatory_stress.yaml"))


def team_scenario(name: str) -> Scenario:
    return load_scenario(os.path.join(TEAM_DIR, f"{name}.yaml"))


def run_team(
    case: CaseData, plan: Plan, scenario: Scenario
) -> tuple[RunResult, Optional[Plan], list[str]]:
    """Прогон TEAM-сценария через адаптер ядра D3.4.

    Для ценовых событий (R05/R10) — прогон без scenario_parameters
    (множитель уже задан год-точным блоком variable_price_multiplier,
    однократное применение). Возвращает (result, действующий план, журнал).
    """
    if scenario.scenario_id in PRICE_EVENT_SCENARIOS:
        clean = Scenario(
            scenario_id=scenario.scenario_id,
            status=scenario.status,
            label_ru=scenario.label_ru,
            demand_multiplier=scenario.demand_multiplier,
            critical_demand_multiplier=scenario.critical_demand_multiplier,
            variable_price_multiplier=scenario.variable_price_multiplier,
            actual_delivery_share=scenario.actual_delivery_share,
            loss_ceiling=scenario.loss_ceiling,
            notes=list(scenario.notes),
        )
        r = run_plan(case, plan, clean)
        journal = [
            f"[{scenario.scenario_id}] однократное применение события через "
            f"variable_price_multiplier (price-override в scenario_parameters "
            f"проигнорирован: дублирует множитель — предотвращён двойной начёт)"
        ]
        return r, plan, journal
    if scenario.scenario_parameters:
        case2, plan2 = apply_scenario_parameters(case, scenario, plan)
        r = run_plan(case2, plan2 or plan, scenario)
        return r, plan2, list(case2.scenario_journal)
    r = run_plan(case, plan, scenario)
    return r, plan, []


# ---------------------------------------------------------------------------
# Метрики
# ---------------------------------------------------------------------------

def pv_of(result: RunResult, rate: float = 0.10, t0: int = 2035) -> float:
    """PV по годовым total_mln (для ставки 0.10 совпадает с ядром;
    0.05/0.15 — пост-обработка financial_breakdown, ядро не меняется:
    физика от ставки не зависит, TA-06)."""
    return sum(
        r.total_mln / (1.0 + rate) ** (r.year - t0)
        for r in result.costs.financial_breakdown
    )


def total_cost_of(result: RunResult) -> float:
    return sum(r.total_mln for r in result.costs.financial_breakdown)


def shortage_of(result: RunResult) -> float:
    return sum(y.shortage_t for y in result.service.yearly_balance)


def min_sl_total(result: RunResult) -> float:
    return min(y.sl_total for y in result.service.yearly_balance)


def min_sl_crit(result: RunResult) -> float:
    return min(y.sl_critical for y in result.service.yearly_balance)


def violation_signature(result: RunResult) -> set[tuple[str, str]]:
    """Множество (rule_id, period) нарушенных проверок из checks."""
    return {(c.rule_id, c.period) for c in result.checks if not c.passed}


def new_violations(
    result: RunResult, base: RunResult
) -> list[tuple[str, str]]:
    """НОВЫЕ нарушения относительно базового прогона (сортированы)."""
    return sorted(violation_signature(result) - violation_signature(base))


def capex_cum(result: RunResult, through_year: int) -> float:
    return sum(
        r.capex_mln
        for r in result.costs.financial_breakdown
        if r.year <= through_year
    )


def yearly_row(result: RunResult) -> list[dict[str, Any]]:
    return [asdict(y) for y in result.service.yearly_balance]


def finance_row(result: RunResult) -> list[dict[str, Any]]:
    return [asdict(r) for r in result.costs.financial_breakdown]


# ---------------------------------------------------------------------------
# Конструирование сценариев и адаптивных планов (копии, CASE_INPUT не меняется)
# ---------------------------------------------------------------------------

def demand_scenario(sid: str, mult: dict[int, float]) -> Scenario:
    """Множитель спроса (общий И критический одновременно, D3.1: доля
    критического сохраняется — критический множитель равен общему)."""
    block = {str(y): float(m) for y, m in mult.items()}
    return Scenario(
        scenario_id=sid,
        status="TEAM_ASSUMPTION",
        demand_multiplier=block,
        critical_demand_multiplier=dict(block),
    )


def price_mult_scenario(sid: str, channel: str, mult: dict[int, float]) -> Scenario:
    return Scenario(
        scenario_id=sid,
        status="TEAM_ASSUMPTION",
        variable_price_multiplier={channel: {str(y): m for y, m in mult.items()}},
    )


def isru_share_scenario(sid: str, shares: dict[int, float]) -> Scenario:
    return Scenario(
        scenario_id=sid,
        status="TEAM_ASSUMPTION",
        actual_delivery_share={"Lunar-ISRU": {str(y): s for y, s in shares.items()}},
    )


def grid_scenario(
    sid: str, demand_mult: float, price_a_mult: float, d_share: float
) -> Scenario:
    """Узел сетки P04: спрос ×d_m (все годы), цена A ×p_m (все годы),
    фактическая доля D = d_share (2038–2040)."""
    years = [str(y) for y in range(2035, 2041)]
    return Scenario(
        scenario_id=sid,
        status="TEAM_ASSUMPTION",
        demand_multiplier={y: demand_mult for y in years},
        critical_demand_multiplier={y: demand_mult for y in years},
        variable_price_multiplier={"Earth-Core": {y: price_a_mult for y in years}},
        actual_delivery_share={
            "Lunar-ISRU": {str(y): d_share for y in (2038, 2039, 2040)}
        },
    )


def clone_plan(plan: Plan, new_id: str) -> Plan:
    p = copy.deepcopy(plan)
    p.plan_id = new_id
    return p


def add_orders(plan: Plan, orders: list[tuple[str, str, float]]) -> Plan:
    """Добавить заказы (source_id, 'YYYY-MM', т) к копии плана."""
    for sid, period, vol in orders:
        plan.decisions.supply_orders.append(
            SupplyOrder(source_id=sid, period=period, ordered_volume_t=vol)
        )
    return plan


def set_reservation(
    plan: Plan, source_id: str, year: int, capacity: float
) -> Plan:
    """Установить/добавить резерв мощности (source, год) в копии плана."""
    for r in plan.decisions.capacity_reservations:
        if r.source_id == source_id and r.year == year:
            r.reserved_capacity_t_per_year = capacity
            return plan
    plan.decisions.capacity_reservations.append(
        CapacityReservation(
            source_id=source_id, year=year, reserved_capacity_t_per_year=capacity
        )
    )
    return plan


def write_csv(path: str, columns: list[str], rows: list[dict[str, Any]]) -> None:
    import csv

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(columns)
        for row in rows:
            w.writerow([_fmt(row.get(c)) for c in columns])


def write_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def _fmt(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return f"{v:.10g}"
    return str(v)


def meta_block(scenario_id: str, plan_id: str, extra: Optional[dict] = None) -> dict:
    import subprocess
    from datetime import datetime, timezone

    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True
    ).stdout.strip()
    m = {
        "case_input_sha256": _dir_sha(),
        "repo_commit": sha,
        "plan_id": plan_id,
        "plan_file": "ai_workstreams/WP2_strategy_economics/plans/S10.json",
        "plan_note": PLAN_LABEL,
        "scenario_id": scenario_id,
        "engine_version": "0.3.0-wave3",
        "contract_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "random_seed": None,
        "deterministic": True,
    }
    if extra:
        m.update(extra)
    return m


def _dir_sha() -> str:
    import hashlib

    h = hashlib.sha256()
    for root, _dirs, files in os.walk(DATA_DIR):
        for name in sorted(files):
            p = os.path.join(root, name)
            h.update(name.encode())
            h.update(open(p, "rb").read())
    for cfg in ("base.yaml", "mandatory_stress.yaml"):
        p = os.path.join(REPO, "configs", cfg)
        h.update(cfg.encode())
        h.update(open(p, "rb").read())
    h.update(open(PLAN_PATH, "rb").read())
    return h.hexdigest()[:32]
