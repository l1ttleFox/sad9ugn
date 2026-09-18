"""Выгрузка результатов по export.schema.json (CSV/XLSX).
Реализуется в WP1 волне 3."""

from __future__ import annotations

from .models import RunResult


def export_results(result: RunResult, path: str, fmt: str = "csv") -> list[str]:
    """Выгрузка: yearly_balance, source_schedule, inventory_trace,
    financial_breakdown, constraint_checks, risk_register.

    ЗАГЛУШКА: реализуется в волне 3 (prompt_wave3.md).
    """
    raise NotImplementedError(
        "export_results: выгрузка результатов будет реализована в WP1 волне 3"
    )
