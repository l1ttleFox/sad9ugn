"""Финансовый блок: переменные платежи, take-or-pay, резервирование, хранение,
CAPEX, дисконтирование (r=0.10, t0=2035). Реализуется в WP1 волне 2."""

from __future__ import annotations

from .models import CaseData, CostResult, DeliveriesResult, InventoryResult, Plan


def calculate_costs(
    case: CaseData,
    plan: Plan,
    deliveries: DeliveriesResult,
    inventory: InventoryResult,
) -> CostResult:
    """Переменные платежи (с take-or-pay через max), резервирование, хранение,
    фиксированный OPEX, CAPEX по датам, дисконтирование (r=0.10, t0=2035).

    ЗАГЛУШКА: реализуется в волне 2 (prompt_wave2.md).
    """
    raise NotImplementedError(
        "calculate_costs: финансовый блок будет реализован в WP1 волне 2"
    )
