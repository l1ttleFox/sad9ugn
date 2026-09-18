"""Проверка всех ограничений constraints.csv и правил CASE_RULES.md.
Реализуется в WP1 волне 3."""

from __future__ import annotations

from .models import CaseData, CostResult, InventoryResult, Plan, ServiceResult, Violation


def check_constraints(
    case: CaseData,
    plan: Plan,
    inventory: InventoryResult,
    service: ServiceResult,
    costs: CostResult,
) -> list[Violation]:
    """Все ограничения constraints.csv + правила CASE_RULES.md.

    ЗАГЛУШКА: реализуется в волне 3 (prompt_wave3.md).
    """
    raise NotImplementedError(
        "check_constraints: блок ограничений будет реализован в WP1 волне 3"
    )
