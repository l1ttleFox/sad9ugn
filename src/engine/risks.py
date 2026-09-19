"""Оценка рисков: прогон TEAM_* сценариев через полный конвейер run_plan.

evaluate_risks(case, plan, base_result, risk_scenarios) -> RiskReport:
для каждого сценария считается прогон (с адаптером scenario_parameters D3.4,
если сценарий их содержит) и собираются последствия относительно BASE:
- consequence_t — прирост суммарного дефицита (shortage), т;
- consequence_mln — прирост дисконтированной стоимости (PV), млн у.е.;
- consequence_sl — снижение минимального годового SL_total (пункты доли);
- probability_basis_ru — основание (для TEAM_* — «сценарный подход без
  частоты», STRESS_PROTOCOL: статистики нет — интервал честнее выдуманной
  вероятности).

Интерфейс готов к наполнению реестра из WP3 (risk_id сценария = scenario_id).
Сценарий, который адаптер отказался применять (несовпадение исходного
значения override), даёт запись с пометкой «не исполнен» в
probability_basis_ru, а не нулевые последствия (требование WP3 wave1).
"""

from __future__ import annotations

from .models import (
    CaseData,
    Plan,
    RiskEntry,
    RiskReport,
    RunResult,
    Scenario,
)


def _min_sl(result: RunResult) -> float:
    return min((y.sl_total for y in result.service.yearly_balance), default=1.0)


def _total_pv(result: RunResult) -> float:
    return sum(r.discounted_mln for r in result.costs.financial_breakdown)


def _total_shortage(result: RunResult) -> float:
    return sum(y.shortage_t for y in result.service.yearly_balance)


def evaluate_risks(
    case: CaseData,
    plan: Plan,
    base_result: RunResult,
    risk_scenarios: list[Scenario],
) -> RiskReport:
    """Прогон списка TEAM_* сценариев; последствия в тоннах, млн у.е., пунктах SL.

    run_plan импортируется лениво (из пакета), чтобы не создавать цикл
    импортов __init__ ↔ risks.
    """
    from . import run_plan  # ленивый импорт: избегаем цикла

    report = RiskReport()
    base_pv = _total_pv(base_result)
    base_shortage = _total_shortage(base_result)
    base_sl = _min_sl(base_result)

    for scenario in risk_scenarios:
        effective_case = case
        effective_plan = plan
        try:
            if scenario.scenario_parameters:
                adapted_case, adapted_plan = _apply_params(case, scenario, plan)
                effective_case = adapted_case
                if adapted_plan is not None:
                    effective_plan = adapted_plan
            result = run_plan(effective_case, effective_plan, scenario)
        except ValueError as e:
            # Адаптер не смог применить override (несовпадение исходного
            # значения и т.п.) — риск «не исполнен», НЕ ноль.
            report.risk_register.append(
                RiskEntry(
                    risk_id=scenario.scenario_id,
                    scenario_id=scenario.scenario_id,
                    probability_basis_ru=f"НЕ ИСПОЛНЕН: {e}",
                )
            )
            continue

        delta_t = _total_shortage(result) - base_shortage
        delta_mln = _total_pv(result) - base_pv
        delta_sl = _min_sl(result) - base_sl
        report.risk_register.append(
            RiskEntry(
                risk_id=scenario.scenario_id,
                scenario_id=scenario.scenario_id,
                consequence_t=delta_t,
                consequence_mln=delta_mln,
                consequence_sl=delta_sl,
                probability_basis_ru=(
                    "сценарный подход: тяжесть без частоты (STRESS_PROTOCOL; "
                    "TEAM_ASSUMPTION — параметры сценария)"
                ),
            )
        )
    return report


def _apply_params(case: CaseData, scenario: Scenario, plan: Plan):
    """Обёртка адаптера scenario_parameters (D3.4) — импорт из scenario.py."""
    from .scenario import apply_scenario_parameters

    return apply_scenario_parameters(case, scenario, plan)
