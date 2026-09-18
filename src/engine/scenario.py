"""Применение сценария к данным кейса.

apply_scenario возвращает НОВЫЙ CaseData (исходный не мутируется) с:
- множителями общего и критического спроса (по годам);
- множителями переменных цен (по каналам и годам);
- фактическими долями поставки (actual_delivery_share);
- флагом/порогом loss_ceiling.

BASE — все множители 1.0 (delivered = planned, reliability НЕ участвует).

Формат блоков сценария (configs/*.yaml):
- {'default': 1.0} — одно значение для всех годов;
- {'2038': 1.15, ...} — по годам;
- {'Earth-Core': {'2038': 1.25}, ...} — по каналам (имя канала из
  supply_sources.csv) и годам; внутри канала допустим 'default'.

ВНИМАНИЕ: фактические доли поставки (например ISRU 0.55 в MANDATORY_STRESS)
применяются к плановым объёмам ОДИН раз и НЕ умножаются на reliability
(CALCULATION_RULES §11, units_and_conventions.md §9).
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .models import CaseData, Scenario


def _lookup(block: dict[str, Any], channel_name: str | None, year: int) -> float:
    """Поиск множителя в блоке сценария.

    Порядок: блок может быть плоским ({'default'/'YYYY': float}) или вложенным
    по каналам ({channel: {...}}). Возврат: значение канала за год →
    'default' канала → общее за год → общий 'default' → 1.0.
    """
    if not block:
        return 1.0
    yk = str(year)

    chan: dict[str, Any] | None = None
    if channel_name is not None:
        val = block.get(channel_name)
        if isinstance(val, dict):
            chan = val

    def pick(d: dict[str, Any] | None) -> float | None:
        if d is None:
            return None
        if yk in d:
            return float(d[yk])
        if "default" in d:
            return float(d["default"])
        return None

    for candidate in (chan, block):
        got = pick(candidate)
        if got is not None:
            return got
    return 1.0


def apply_scenario(case: CaseData, scenario: Scenario) -> CaseData:
    """Возвращает новый CaseData с применёнными множителями сценария."""
    new_case = deepcopy(case)
    new_case.scenario_id = scenario.scenario_id
    new_case.loss_ceiling = deepcopy(scenario.loss_ceiling) or {"enabled": False}

    # Спрос: общий и критический множители по годам.
    for d in case.demand:
        m_total = _lookup(scenario.demand_multiplier, None, d.year)
        m_crit = _lookup(scenario.critical_demand_multiplier, None, d.year)
        total = d.base_total_t * m_total
        crit = d.base_critical_t * m_crit
        # Критический спрос вложен в общий (FAQ): не может превысить общий.
        new_case.effective_demand_total_t[d.year] = total
        new_case.effective_demand_critical_t[d.year] = min(crit, total)

    # Цены по каналам и годам + фактические доли поставки.
    for s in case.supply_sources:
        for d in case.demand:
            m_price = _lookup(scenario.variable_price_multiplier, s.name, d.year)
            new_case.effective_price_mln_per_t[(s.source_id, d.year)] = (
                s.variable_cost_mln_per_t * m_price
            )
            new_case.actual_delivery_share[(s.source_id, d.year)] = _lookup(
                scenario.actual_delivery_share, s.name, d.year
            )

    return new_case
