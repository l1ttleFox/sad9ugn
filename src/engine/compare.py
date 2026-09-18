"""Сопоставление сценариев: BASE vs STRESS vs TEAM_*.
Реализуется в WP1 волне 3."""

from __future__ import annotations

from .models import ComparisonResult, RunResult


def compare_scenarios(results: dict[str, RunResult]) -> ComparisonResult:
    """Сопоставление BASE vs STRESS vs TEAM_*: расходы, SL, запасы, дефицит, нарушения.

    ЗАГЛУШКА: реализуется в волне 3 (prompt_wave3.md).
    """
    raise NotImplementedError(
        "compare_scenarios: модуль сравнения будет реализован в WP1 волне 3"
    )
