"""Сопоставление сценариев: BASE vs STRESS vs TEAM_*.

compare_scenarios(results) -> ComparisonResult:
- строка на сценарий: total_mln, discounted_mln (PV), SL по годам, shortage,
  reserve_ok, число нарушений, capex_cumulative;
- дельты относительно BASE (STRESS − BASE) для каждого небазового сценария.

Результат — список словарей rows (ComparisonResult.rows), пригодный для
таблиц UI (WP4) и экспорта. Ключи — на английском (идентификаторы), значения
описаний — на русском.
"""

from __future__ import annotations

from typing import Any

from .models import ComparisonResult, RunResult


def _scenario_summary(name: str, result: RunResult) -> dict[str, Any]:
    """Сводка одного сценария: деньги, SL, запас, нарушения."""
    costs = result.costs.financial_breakdown
    total_mln = sum(r.total_mln for r in costs)
    discounted_mln = sum(r.discounted_mln for r in costs)
    capex_cum = costs[-1].capex_cumulative_mln if costs else 0.0
    shortage_t = sum(y.shortage_t for y in result.service.yearly_balance)
    sl_total_by_year = {
        str(y.year): round(y.sl_total, 6) for y in result.service.yearly_balance
    }
    sl_critical_by_year = {
        str(y.year): round(y.sl_critical, 6) for y in result.service.yearly_balance
    }
    reserve_ok_all = all(y.reserve_ok for y in result.service.yearly_balance)
    return {
        "scenario_id": name,
        "plan_id": result.plan_id,
        "total_mln": round(total_mln, 6),
        "discounted_mln": round(discounted_mln, 6),
        "capex_cumulative_mln": round(capex_cum, 6),
        "shortage_t": round(shortage_t, 6),
        "sl_total_by_year": sl_total_by_year,
        "sl_critical_by_year": sl_critical_by_year,
        "reserve_ok_all_years": reserve_ok_all,
        "violations_count": len(result.violations),
    }


def _delta_vs_base(row: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    """Дельты (сценарий − BASE) по скалярным метрикам и SL по годам."""
    delta: dict[str, Any] = {
        "scenario_id": row["scenario_id"],
        "delta_total_mln": round(row["total_mln"] - base["total_mln"], 6),
        "delta_discounted_mln": round(
            row["discounted_mln"] - base["discounted_mln"], 6
        ),
        "delta_shortage_t": round(row["shortage_t"] - base["shortage_t"], 6),
        "delta_violations": row["violations_count"] - base["violations_count"],
    }
    delta_sl_total = {}
    for year, sl in row["sl_total_by_year"].items():
        base_sl = base["sl_total_by_year"].get(year)
        if base_sl is not None:
            delta_sl_total[year] = round(sl - base_sl, 6)
    delta["delta_sl_total_by_year"] = delta_sl_total
    return delta


def compare_scenarios(results: dict[str, RunResult]) -> ComparisonResult:
    """Сопоставление сценариев: расходы, SL, запасы, дефицит, нарушения.

    results: {scenario_id: RunResult}. BASE (если присутствует) — опорная
    точка для дельт. Возвращает ComparisonResult: rows = сводки сценариев +
    строки 'delta_<id>' с дельтами относительно BASE.
    """
    comparison = ComparisonResult()
    if not results:
        return comparison

    summaries = {name: _scenario_summary(name, res) for name, res in results.items()}
    base_name = "BASE" if "BASE" in summaries else next(iter(summaries))
    base = summaries[base_name]

    comparison.rows.append(
        {"row_type": "summary", "base_scenario": base_name}
    )
    for name in results:
        comparison.rows.append({"row_type": "scenario", **summaries[name]})
    for name in results:
        if name != base_name:
            comparison.rows.append(
                {"row_type": "delta", **_delta_vs_base(summaries[name], base)}
            )
    return comparison
