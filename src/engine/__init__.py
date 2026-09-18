"""Расчётное ядро системы планирования снабжения орбитального топливного узла.

Контракт API: ai_workstreams/00_contracts/core_api.md (v1.0, заморожен).
Главная точка входа — run_plan (полный прогон сценария).

Волна 1: загрузка (loader), проверки (validator), сценарии (scenario),
поставки (deliveries), материальный баланс и сервис (inventory).
Финансы, ограничения, риски, сравнение, save/load, экспорт — заглушки
до волн 2–3.
"""

from __future__ import annotations

from datetime import datetime, timezone

from .models import (
    Assumption,
    CapacityReservation,
    CaseData,
    CaseLoadError,
    ComparisonResult,
    ConstraintRow,
    CostResult,
    DeliveriesResult,
    DemandRow,
    EmergencyContract,
    InitialInventorySource,
    InventoryPolicy,
    InventoryResult,
    InventoryTracePoint,
    Investment,
    InvestmentOption,
    MonthBalance,
    Plan,
    PlanDecisions,
    RiskEntry,
    RiskReport,
    RunMeta,
    RunResult,
    Scenario,
    ServiceResult,
    SourceScheduleRow,
    StorageOption,
    SupplyOrder,
    SupplySource,
    Violation,
    YearBalance,
)
from .loader import load_case, load_plan, load_scenario, plan_from_dict
from .validator import validate_case, validate_plan
from .scenario import apply_scenario
from .deliveries import (
    all_periods,
    calculate_deliveries,
    channel_available_from,
    lead_time_months,
    month_index,
    month_period,
)
from .inventory import (
    calculate_inventory,
    calculate_service,
    reserve_required_t,
    storage_mode_for_period,
    zbo_start_index,
)
from .finance import calculate_costs
from .constraints import check_constraints
from .risks import evaluate_risks
from .compare import compare_scenarios
from .persistence import save_plan, load_saved_plan
from .export import export_results

__all__ = [
    # загрузка
    "load_case",
    "load_plan",
    "load_scenario",
    "plan_from_dict",
    "CaseLoadError",
    # проверки
    "validate_case",
    "validate_plan",
    # расчёт
    "apply_scenario",
    "calculate_deliveries",
    "calculate_inventory",
    "calculate_service",
    "calculate_costs",
    "check_constraints",
    "evaluate_risks",
    "compare_scenarios",
    "save_plan",
    "load_saved_plan",
    "export_results",
    "run_plan",
    # модели
    "CaseData",
    "Scenario",
    "Plan",
    "PlanDecisions",
    "SupplyOrder",
    "CapacityReservation",
    "Investment",
    "InventoryPolicy",
    "InitialInventorySource",
    "EmergencyContract",
    "Assumption",
    "Violation",
    "DeliveriesResult",
    "InventoryResult",
    "ServiceResult",
    "CostResult",
    "RiskReport",
    "RiskEntry",
    "ComparisonResult",
    "RunResult",
    "RunMeta",
    "MonthBalance",
    "YearBalance",
    "SourceScheduleRow",
    "InventoryTracePoint",
    "DemandRow",
    "SupplySource",
    "StorageOption",
    "InvestmentOption",
    "ConstraintRow",
]


def run_plan(case: CaseData, plan: Plan, scenario: Scenario) -> RunResult:
    """ГЛАВНАЯ ТОЧКА ВХОДА: полный прогон = apply_scenario → deliveries →
    inventory → service → costs → constraints (core_api.md).

    Используется UI (WP4), тестами и экспортом ЕДИНООБРАЗНО.

    Волна 1: финансовый блок (costs) и полное ограничение (check_constraints)
    ещё не реализованы — в результат включаются нарушения расчётного контура
    (CAPACITY_EXCEEDED, LEAD_TIME_VIOLATION, STORAGE_OVERFLOW), costs пуст.
    """
    effective_case = apply_scenario(case, scenario)

    deliveries = calculate_deliveries(effective_case, plan)
    inventory = calculate_inventory(effective_case, plan, deliveries)
    service = calculate_service(effective_case, inventory)

    violations: list[Violation] = []
    violations.extend(deliveries.violations)
    violations.extend(inventory.violations)

    meta = RunMeta(
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )

    return RunResult(
        scenario_id=scenario.scenario_id,
        plan_id=plan.plan_id,
        deliveries=deliveries,
        inventory=inventory,
        service=service,
        costs=CostResult(),
        violations=violations,
        meta=meta,
    )
