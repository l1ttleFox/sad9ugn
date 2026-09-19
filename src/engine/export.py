"""Экспорт результатов по export.schema.json организатора (CSV, опционально XLSX).

export_results(result, path, fmt) создаёт в каталоге path:
- yearly_balance.csv, source_schedule.csv, inventory_trace.csv,
  financial_breakdown.csv, constraint_checks.csv, risk_register.csv;
- meta.json (scenario_id, plan_id, units, assumptions_reference,
  engine_version, generated_at, discount_rate, discount_t0, random_seed,
  scenario_journal).

fmt: 'csv' (по умолчанию) или 'xlsx' (pandas + openpyxl, допустимая
зависимость ядра). Возвращает список созданных файлов.

Числа сериализуются с repr-точностью (float через %.10g) — повторная
загрузка CSV совпадает с внутренними значениями (критерий приёмки волны 3).
cost_per_served_t_mln = None → пустая ячейка.
"""

from __future__ import annotations

import csv
import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from .models import RunResult

# Состав и порядок колонок файлов экспорта.
_YEARLY_COLUMNS = [
    "year", "demand_total_t", "demand_critical_t", "delivered_t", "losses_t",
    "served_total_t", "served_critical_t", "shortage_t", "sl_total",
    "sl_critical", "i_start_t", "i_end_t", "reserve_required_t",
    "reserve_actual_start_t", "reserve_ok",
]
_SCHEDULE_COLUMNS = [
    "source_id", "period", "reserved_capacity_t_per_year", "ordered_volume_t",
    "planned_delivery_t", "actual_delivery_t", "lead_time_applied",
]
_TRACE_COLUMNS = ["period", "inventory_t", "reserve_threshold_t", "capacity_t"]
_FINANCE_COLUMNS = [
    "year", "capex_mln", "capex_cumulative_mln", "procurement_mln",
    "reservation_mln", "take_or_pay_extra_mln", "holding_mln",
    "fixed_opex_mln", "total_mln", "discounted_mln", "cost_per_served_t_mln",
]
_CHECK_COLUMNS = [
    "rule_id", "period", "passed", "actual", "limit", "excess",
    "severity", "source", "message_ru",
]
_RISK_COLUMNS = [
    "risk_id", "scenario_id", "consequence_t", "consequence_mln",
    "consequence_sl", "probability_basis_ru",
]

_UNITS = {
    "volumes": "t",
    "capacity": "t/year",
    "money": "mln units (constant 2035 prices)",
    "prices": "mln units/t",
    "shares": "0..1",
    "period": "YYYY or YYYY-MM",
    "holding_cost": "mln units/(t*year)",
}


def _fmt(value: Any) -> str:
    """Сериализация значения ячейки: float — %.10g, bool — true/false, None — пусто."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.10g}"
    return str(value)


def _write_csv(path: str, columns: list[str], rows: list[dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        for row in rows:
            writer.writerow([_fmt(row.get(col)) for col in columns])


def _yearly_rows(result: RunResult) -> list[dict[str, Any]]:
    return [asdict(y) for y in result.service.yearly_balance]


def _schedule_rows(result: RunResult) -> list[dict[str, Any]]:
    return [asdict(r) for r in result.deliveries.source_schedule]


def _trace_rows(result: RunResult) -> list[dict[str, Any]]:
    return [asdict(p) for p in result.inventory.inventory_trace]


def _finance_rows(result: RunResult) -> list[dict[str, Any]]:
    return [asdict(r) for r in result.costs.financial_breakdown]


def _check_rows(result: RunResult) -> list[dict[str, Any]]:
    rows = [asdict(c) for c in result.checks]
    # Если checks пуст (прогон вне run_plan), берём violations как passed=False.
    if not rows:
        rows = [
            {
                "rule_id": v.rule_id, "period": v.period, "passed": False,
                "actual": v.actual, "limit": v.limit, "excess": v.excess,
                "severity": "hard", "source": "internal",
                "message_ru": v.message_ru,
            }
            for v in result.violations
        ]
    return rows


def _risk_rows(result: RunResult) -> list[dict[str, Any]]:
    return [asdict(r) for r in result.risks.risk_register]


def _meta(result: RunResult) -> dict[str, Any]:
    meta = result.meta
    case_journal = list(getattr(result.case, "scenario_journal", []) or [])
    generated = meta.generated_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    return {
        "scenario_id": result.scenario_id,
        "plan_id": result.plan_id,
        "units": _UNITS,
        "assumptions_reference": meta.assumptions_reference,
        "engine_version": meta.engine_version,
        "contract_version": meta.contract_version,
        "timestep": meta.timestep,
        "discount_rate": meta.discount_rate,
        "discount_t0": meta.discount_t0,
        "generated_at": generated,
        "random_seed": meta.random_seed,
        "scenario_journal": case_journal,
    }


def export_results(result: RunResult, path: str, fmt: str = "csv") -> list[str]:
    """Выгрузка результата: CSV-файлы + meta.json в каталог path.

    fmt='xlsx' — один файл results.xlsx с теми же листами (pandas/openpyxl).
    Возвращает список созданных файлов.
    """
    fmt_norm = str(fmt or "csv").lower()
    if fmt_norm not in ("csv", "xlsx"):
        raise ValueError(
            f"Недопустимый формат экспорта '{fmt}' (допустимы: csv, xlsx)"
        )

    os.makedirs(path, exist_ok=True)
    tables: dict[str, tuple[list[str], list[dict[str, Any]]]] = {
        "yearly_balance": (_YEARLY_COLUMNS, _yearly_rows(result)),
        "source_schedule": (_SCHEDULE_COLUMNS, _schedule_rows(result)),
        "inventory_trace": (_TRACE_COLUMNS, _trace_rows(result)),
        "financial_breakdown": (_FINANCE_COLUMNS, _finance_rows(result)),
        "constraint_checks": (_CHECK_COLUMNS, _check_rows(result)),
        "risk_register": (_RISK_COLUMNS, _risk_rows(result)),
    }

    created: list[str] = []
    if fmt_norm == "csv":
        for name, (columns, rows) in tables.items():
            fpath = os.path.join(path, f"{name}.csv")
            _write_csv(fpath, columns, rows)
            created.append(fpath)
        meta_path = os.path.join(path, "meta.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(_meta(result), f, ensure_ascii=False, indent=2)
            f.write("\n")
        created.append(meta_path)
        return created

    # xlsx: pandas + openpyxl (допустимая зависимость ядра).
    import pandas as pd

    xlsx_path = os.path.join(path, "results.xlsx")
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        for name, (columns, rows) in tables.items():
            df = pd.DataFrame(rows, columns=columns)
            df.to_excel(writer, sheet_name=name, index=False)
        meta_df = pd.DataFrame(
            [{"key": k, "value": json.dumps(v, ensure_ascii=False)
              if isinstance(v, (dict, list)) else v}
             for k, v in _meta(result).items()]
        )
        meta_df.to_excel(writer, sheet_name="meta", index=False)
    created.append(xlsx_path)
    return created
