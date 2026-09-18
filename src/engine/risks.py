"""Оценка рисков: прогон TEAM_* риск-сценариев из реестра.
Реализуется в WP1 волне 3 (совместно с WP3)."""

from __future__ import annotations

from .models import CaseData, Plan, RiskReport, RunResult, Scenario


def evaluate_risks(
    case: CaseData,
    plan: Plan,
    base_result: RunResult,
    risk_scenarios: list[Scenario],
) -> RiskReport:
    """Прогон TEAM_* риск-сценариев; последствия в тоннах, млн у.е., пунктах SL.

    ЗАГЛУШКА: реализуется в волне 3 (prompt_wave3.md).
    """
    raise NotImplementedError(
        "evaluate_risks: блок рисков будет реализован в WP1 волне 3"
    )
