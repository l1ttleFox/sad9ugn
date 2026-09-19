"""Общая библиотека WP3 волны 2 (повторный прогон на FINAL-планах).

Правила (prompt_wave2.md, STRESS_PROTOCOL, решения D3/D8,
REFRESH_WP3_AFTER_FINAL.md):
- ядро, CASE_INPUT (data/**, configs/base.yaml, configs/mandatory_stress.yaml)
  и FINAL-планы WP2 НЕ изменяются;
- BASE-контроль: results/plans/FINAL_BASE.json (план BASE-среды);
- MANDATORY_STRESS: results/plans/FINAL_STRESS.json (план стресс-среды —
  TD-01 demand-chasing пересчитан под стрессовый профиль WP2);
- фиксированные стресс-исследования (P02, P04) — на НЕИЗМЕННОМ FINAL_BASE
  (P01/P02 §1: один и тот же план для BASE и исследовательского прогона);
- TEAM-сценарии — через адаптер ядра apply_scenario_parameters (D3.4);
  R01 (COMBINED) — единственный сценарий поверх MANDATORY_STRESS,
  прогоняется на FINAL_STRESS;
- для R05/R10 (TEAM_PRICE_SPIKE_E / TEAM_GEO_CHANNEL_A) цена применяется
  ОДИН раз через variable_price_multiplier: двойной плоский price override
  удалён из YAML решением оркестратора D8.4;
- INVENTORY_SHOCK_APPLIED — информационное событие (D8.3), не входит
  в hard-нарушения для ранжирования риска.
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
PLANS_DIR = os.path.join(REPO, "results", "plans")
PLAN_PATH = os.path.join(PLANS_DIR, "FINAL_BASE.json")
PLAN_STRESS_PATH = os.path.join(PLANS_DIR, "FINAL_STRESS.json")
TEAM_DIR = os.path.join(REPO, "ai_workstreams", "WP3_stress_risk", "configs", "team")
RESULTS = os.path.join(REPO, "results")

PLAN_LABEL = "FINAL (WP2 wave2-final-1.0, стратегия S10 «ISRU base»)"
WORKING_PLAN_NOTE = (
    "Расчёты выполнены на FINAL-планах WP2: BASE-контроль — "
    "results/plans/FINAL_BASE.json, MANDATORY_STRESS — "
    "results/plans/FINAL_STRESS.json (стратегия S10; два операционных "
    "плана одной стратегии под среды BASE и MANDATORY_STRESS)"
)

# Информационные записи, исключаемые из hard-нарушений при ранжировании
# риска (D8.3): INVENTORY_SHOCK_APPLIED фиксирует факт применения шока,
# а не нарушение ограничения CASE_INPUT.
INFO_RULE_IDS = {"INVENTORY_SHOCK_APPLIED"}

# Сценарии-ценовые события: цена применяется ОДИН раз через
# variable_price_multiplier (D8.4: плоский price-override удалён из YAML).
PRICE_EVENT_SCENARIOS = {"TEAM_PRICE_SPIKE_E", "TEAM_GEO_CHANNEL_A"}


def base_case() -> CaseData:
    return load_case(DATA_DIR)


def base_plan() -> Plan:
    """FINAL_BASE — план BASE-среды (контроль P01/P02/P03/P04/P05)."""
    return load_plan(PLAN_PATH)


def stress_plan() -> Plan:
    """FINAL_STRESS — план стресс-среды (MANDATORY_STRESS, R01 COMBINED)."""
    return load_plan(PLAN_STRESS_PATH)


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

    Для ценовых событий (R05/R10) YAML после D8.4 содержит только
    variable_price_multiplier (scenario_parameters — скалярная метадата
    `event:`), поэтому прогон идёт штатным run_plan: множитель применяется
    ровно один раз. Возвращает (result, действующий план, журнал).
    """
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
    """Множество (rule_id, period) нарушенных проверок из checks
    (без информационных записей INFO_RULE_IDS — D8.3)."""
    return {
        (c.rule_id, c.period)
        for c in result.checks
        if not c.passed and c.rule_id not in INFO_RULE_IDS
    }


def info_signature(result: RunResult) -> set[tuple[str, str]]:
    """Информационные записи (INVENTORY_SHOCK_APPLIED и т.п.) отдельно."""
    return {
        (c.rule_id, c.period)
        for c in result.checks
        if not c.passed and c.rule_id in INFO_RULE_IDS
    }


def new_violations(
    result: RunResult, base: RunResult
) -> list[tuple[str, str]]:
    """НОВЫЕ hard-нарушения относительно базового прогона (сортированы)."""
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
# Конструирование сценариев и адаптивных планов (копии, FINAL-планы и
# CASE_INPUT не меняются)
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


def scale_channel_year_orders(
    plan: Plan, source_id: str, year: int, factor: float
) -> Plan:
    """Масштабировать заказы канала за год (копия плана) — для мер вида
    «срезать недоступный объём A и заместить его B» (R08)."""
    for o in plan.decisions.supply_orders:
        if o.source_id == source_id and o.period.startswith(str(year)):
            o.ordered_volume_t = round(o.ordered_volume_t * factor, 4)
    return plan


def reduce_channel_year_orders(
    plan: Plan, source_id: str, year: int, cut_t: float
) -> Plan:
    """Уменьшить годовые заказы канала на cut_t (пропорционально месяцам)."""
    total = sum(
        o.ordered_volume_t for o in plan.decisions.supply_orders
        if o.source_id == source_id and o.period.startswith(str(year))
        and o.ordered_volume_t > 0
    )
    if total <= 0:
        return plan
    factor = max(0.0, (total - cut_t) / total)
    return scale_channel_year_orders(plan, source_id, year, factor)


def remove_channel_year_orders(
    plan: Plan, source_id: str, year: int
) -> Plan:
    """Полностью снять заказы канала за год (недоступный канал — R02)."""
    plan.decisions.supply_orders = [
        o for o in plan.decisions.supply_orders
        if not (o.source_id == source_id and o.period.startswith(str(year)))
    ]
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


def file_sha256(path: str) -> str:
    import hashlib

    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


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
        "plan_files": {
            "BASE": "results/plans/FINAL_BASE.json",
            "MANDATORY_STRESS": "results/plans/FINAL_STRESS.json",
        },
        "plan_sha256": {
            "FINAL_BASE.json": file_sha256(PLAN_PATH),
            "FINAL_STRESS.json": file_sha256(PLAN_STRESS_PATH),
        },
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
    h.update(open(PLAN_STRESS_PATH, "rb").read())
    return h.hexdigest()[:32]
