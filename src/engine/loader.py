"""Загрузка CASE_INPUT (data/*.csv), сценариев (configs/*.yaml) и планов (JSON).

Все сообщения об ошибках — на русском, с именем файла, номером строки
и названием параметра (требование кейса).
"""

from __future__ import annotations

import csv
import json
import os
from typing import Any, Callable

import yaml

from .models import (
    Assumption,
    CapacityReservation,
    CaseData,
    CaseLoadError,
    ConstraintRow,
    DemandRow,
    EmergencyContract,
    InitialInventorySource,
    InventoryPolicy,
    Investment,
    InvestmentOption,
    Plan,
    PlanDecisions,
    Scenario,
    StorageOption,
    SupplyOrder,
    SupplySource,
)

# Файлы CASE_INPUT, загружаемые load_case из data_dir.
_CASE_FILES = (
    "demand.csv",
    "supply_sources.csv",
    "storage_options.csv",
    "investment_options.csv",
    "constraints.csv",
)


def _read_csv_rows(path: str) -> list[dict[str, str]]:
    """Чтение CSV в список словарей; ошибка — на русском с именем файла."""
    if not os.path.isfile(path):
        raise CaseLoadError(f"Файл '{os.path.basename(path)}' не найден в каталоге данных")
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return [dict(row) for row in reader]


def _require(row: dict[str, str], key: str, fname: str, line: int) -> str:
    """Обязательное поле строки CSV; сообщение называет файл, строку, параметр."""
    if key not in row or row[key] is None or str(row[key]).strip() == "":
        # Пустое значение допустимо только для необязательных полей —
        # вызывающий код решает, где вызывать _require.
        raise CaseLoadError(
            f"Файл '{fname}', строка {line}: отсутствует обязательный параметр '{key}'"
        )
    return str(row[key]).strip()


def _to_float(
    row: dict[str, str], key: str, fname: str, line: int,
    allow_empty: bool = False, default: float = 0.0,
) -> float:
    """Разбор числового поля CSV; ошибка — на русском с параметром и строкой."""
    raw = row.get(key)
    if raw is None or str(raw).strip() == "":
        if allow_empty:
            return default
        raise CaseLoadError(
            f"Файл '{fname}', строка {line}: отсутствует обязательный параметр '{key}'"
        )
    try:
        return float(str(raw).strip())
    except ValueError as e:
        raise CaseLoadError(
            f"Файл '{fname}', строка {line}: параметр '{key}' должен быть числом, получено '{raw}'"
        ) from e


def _to_int(
    row: dict[str, str], key: str, fname: str, line: int, allow_empty: bool = False,
) -> int | None:
    """Разбор целочисленного поля CSV (может быть пустым, если allow_empty)."""
    raw = row.get(key)
    if raw is None or str(raw).strip() == "":
        if allow_empty:
            return None
        raise CaseLoadError(
            f"Файл '{fname}', строка {line}: отсутствует обязательный параметр '{key}'"
        )
    try:
        return int(float(str(raw).strip()))
    except ValueError as e:
        raise CaseLoadError(
            f"Файл '{fname}', строка {line}: параметр '{key}' должен быть целым числом, получено '{raw}'"
        ) from e


def _load_demand(path: str) -> list[DemandRow]:
    fname = os.path.basename(path)
    rows = _read_csv_rows(path)
    out: list[DemandRow] = []
    for i, row in enumerate(rows, start=2):  # строка 1 — заголовок
        year = _to_int(row, "year", fname, i)
        out.append(
            DemandRow(
                year=year,  # type: ignore[arg-type]
                base_total_t=_to_float(row, "base_total_t", fname, i),
                base_critical_t=_to_float(row, "base_critical_t", fname, i),
                low_total_t=_to_float(row, "low_total_t", fname, i),
                high_total_t=_to_float(row, "high_total_t", fname, i),
                status=_require(row, "status", fname, i),
            )
        )
    if not out:
        raise CaseLoadError(f"Файл '{fname}' пуст: нет ни одной строки спроса")
    return out


def _load_supply_sources(path: str) -> list[SupplySource]:
    fname = os.path.basename(path)
    rows = _read_csv_rows(path)
    out: list[SupplySource] = []
    for i, row in enumerate(rows, start=2):
        source_id = _require(row, "source_id", fname, i)
        unit = _require(row, "lead_time_unit", fname, i)
        if unit not in ("day", "week", "month", "year"):
            raise CaseLoadError(
                f"Файл '{fname}', строка {i}: параметр 'lead_time_unit' канала '{source_id}' "
                f"имеет недопустимое значение '{unit}' (допустимы day/week/month/year)"
            )
        out.append(
            SupplySource(
                source_id=source_id,
                name=_require(row, "name", fname, i),
                capacity_t_per_year=_to_float(row, "capacity_t_per_year", fname, i),
                variable_cost_mln_per_t=_to_float(row, "variable_cost_mln_per_t", fname, i),
                reservation_rate_mln_per_t_year_capacity=_to_float(
                    row, "reservation_rate_mln_per_t_year_capacity", fname, i
                ),
                take_or_pay_share=_to_float(row, "take_or_pay_share", fname, i),
                lead_time_min_value=_to_float(row, "lead_time_min_value", fname, i),
                lead_time_max_value=_to_float(row, "lead_time_max_value", fname, i),
                lead_time_unit=unit,
                reliability_profile=_require(row, "reliability_profile", fname, i),
                available_from_year=_to_int(row, "available_from_year", fname, i, allow_empty=True),
                status=_require(row, "status", fname, i),
                notes=str(row.get("notes") or ""),
            )
        )
    if not out:
        raise CaseLoadError(f"Файл '{fname}' пуст: нет ни одного канала снабжения")
    return out


def _load_storage_options(path: str) -> list[StorageOption]:
    fname = os.path.basename(path)
    rows = _read_csv_rows(path)
    out: list[StorageOption] = []
    for i, row in enumerate(rows, start=2):
        out.append(
            StorageOption(
                storage_id=_require(row, "storage_id", fname, i),
                name=_require(row, "name", fname, i),
                capacity_t=_to_float(row, "capacity_t", fname, i),
                loss_rate_on_throughput=_to_float(row, "loss_rate_on_throughput", fname, i),
                holding_cost_mln_per_t_year=_to_float(row, "holding_cost_mln_per_t_year", fname, i),
                capex_mln=_to_float(row, "capex_mln", fname, i),
                fixed_opex_mln_per_year=_to_float(row, "fixed_opex_mln_per_year", fname, i),
                available_from_year=_to_int(row, "available_from_year", fname, i) or 2035,
                status=_require(row, "status", fname, i),
                notes=str(row.get("notes") or ""),
            )
        )
    if not out:
        raise CaseLoadError(f"Файл '{fname}' пуст: нет ни одного режима хранения")
    return out


def _load_investment_options(path: str) -> list[InvestmentOption]:
    fname = os.path.basename(path)
    rows = _read_csv_rows(path)
    out: list[InvestmentOption] = []
    for i, row in enumerate(rows, start=2):
        out.append(
            InvestmentOption(
                investment_id=_require(row, "investment_id", fname, i),
                name=_require(row, "name", fname, i),
                option_fee_mln=_to_float(row, "option_fee_mln", fname, i),
                exercise_cost_mln=_to_float(row, "exercise_cost_mln", fname, i),
                total_capex_mln=_to_float(row, "total_capex_mln", fname, i),
                commissioning_rule=_require(row, "commissioning_rule", fname, i),
                fixed_opex_mln_per_year=_to_float(row, "fixed_opex_mln_per_year", fname, i),
                status=_require(row, "status", fname, i),
                notes=str(row.get("notes") or ""),
            )
        )
    if not out:
        raise CaseLoadError(f"Файл '{fname}' пуст: нет ни одной инвестиционной опции")
    return out


def _load_constraints(path: str) -> list[ConstraintRow]:
    fname = os.path.basename(path)
    rows = _read_csv_rows(path)
    out: list[ConstraintRow] = []
    for i, row in enumerate(rows, start=2):
        out.append(
            ConstraintRow(
                constraint_id=_require(row, "constraint_id", fname, i),
                metric=_require(row, "metric", fname, i),
                operator=_require(row, "operator", fname, i),
                value=_to_float(row, "value", fname, i),
                unit=_require(row, "unit", fname, i),
                period=_require(row, "period", fname, i),
                scenario=_require(row, "scenario", fname, i),
                severity=_require(row, "severity", fname, i),
                status=_require(row, "status", fname, i),
                description=str(row.get("description") or ""),
            )
        )
    if not out:
        raise CaseLoadError(f"Файл '{fname}' пуст: нет ни одного ограничения")
    return out


def load_case(data_dir: str) -> CaseData:
    """Загрузка CASE_INPUT из data_dir: demand.csv, supply_sources.csv,
    storage_options.csv, investment_options.csv, constraints.csv.

    После загрузки инициализирует effective_* значения BASE (множитель 1.0):
    effective-спрос = base_*_t, цены = variable_cost_mln_per_t, доли поставки = 1.0.
    Бросает CaseLoadError с сообщением на русском при неполном/противоречивом вводе.
    """
    if not os.path.isdir(data_dir):
        raise CaseLoadError(f"Каталог данных '{data_dir}' не найден")
    for fname in _CASE_FILES:
        if not os.path.isfile(os.path.join(data_dir, fname)):
            raise CaseLoadError(f"Файл '{fname}' не найден в каталоге данных '{data_dir}'")

    case = CaseData(
        demand=_load_demand(os.path.join(data_dir, "demand.csv")),
        supply_sources=_load_supply_sources(os.path.join(data_dir, "supply_sources.csv")),
        storage_options=_load_storage_options(os.path.join(data_dir, "storage_options.csv")),
        investment_options=_load_investment_options(os.path.join(data_dir, "investment_options.csv")),
        constraints=_load_constraints(os.path.join(data_dir, "constraints.csv")),
    )

    # Инициализация effective_* значениями BASE (до применения сценария).
    for d in case.demand:
        case.effective_demand_total_t[d.year] = d.base_total_t
        case.effective_demand_critical_t[d.year] = d.base_critical_t
    for s in case.supply_sources:
        for d in case.demand:
            case.effective_price_mln_per_t[(s.source_id, d.year)] = s.variable_cost_mln_per_t
            case.actual_delivery_share[(s.source_id, d.year)] = 1.0
    case.loss_ceiling = {"enabled": False}
    case.scenario_id = "BASE"
    return case


def _norm_year_key(key: Any) -> str:
    """Ключи годов в YAML могут прийти как int или str — нормализуем к 'YYYY'."""
    return str(int(key)) if isinstance(key, (int, float)) else str(key)


def _norm_multiplier_block(block: Any, fname: str, param: str) -> dict[str, Any]:
    """Нормализация блока множителей: ключи 'default'/'YYYY' (строки),
    вложенные блоки каналов — рекурсивно."""
    if block is None:
        return {"default": 1.0}
    if not isinstance(block, dict):
        raise CaseLoadError(
            f"Файл '{fname}': параметр '{param}' должен быть словарём, получен {type(block).__name__}"
        )
    out: dict[str, Any] = {}
    for k, v in block.items():
        kk = "default" if str(k) == "default" else _norm_year_key(k)
        if isinstance(v, dict):
            out[kk] = _norm_multiplier_block(v, fname, f"{param}.{kk}")
        else:
            try:
                out[kk] = float(v)
            except (TypeError, ValueError) as e:
                raise CaseLoadError(
                    f"Файл '{fname}': параметр '{param}', ключ '{kk}' — значение '{v}' не является числом"
                ) from e
    return out


def load_scenario(config_path: str) -> Scenario:
    """Загрузка BASE / MANDATORY_STRESS / TEAM_* из YAML (configs/*.yaml)."""
    fname = os.path.basename(config_path)
    if not os.path.isfile(config_path):
        raise CaseLoadError(f"Файл сценария '{fname}' не найден: '{config_path}'")
    with open(config_path, "r", encoding="utf-8") as f:
        try:
            raw = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise CaseLoadError(f"Файл '{fname}': ошибка разбора YAML — {e}") from e
    if not isinstance(raw, dict):
        raise CaseLoadError(f"Файл '{fname}': сценарий должен быть словарём YAML")

    if "scenario_id" not in raw or not str(raw.get("scenario_id") or "").strip():
        raise CaseLoadError(f"Файл '{fname}': отсутствует обязательный параметр 'scenario_id'")
    status = str(raw.get("status") or "").strip()
    if status not in ("CASE_INPUT", "TEAM_ASSUMPTION"):
        raise CaseLoadError(
            f"Файл '{fname}': параметр 'status' имеет недопустимое значение '{status}' "
            f"(допустимы CASE_INPUT / TEAM_ASSUMPTION)"
        )

    loss_ceiling = raw.get("loss_ceiling")
    if loss_ceiling is None:
        loss_ceiling = {"enabled": False}
    if not isinstance(loss_ceiling, dict):
        raise CaseLoadError(f"Файл '{fname}': параметр 'loss_ceiling' должен быть словарём")
    loss_ceiling = {str(k): v for k, v in loss_ceiling.items()}

    return Scenario(
        scenario_id=str(raw["scenario_id"]).strip(),
        status=status,
        label_ru=str(raw.get("label_ru") or ""),
        demand_multiplier=_norm_multiplier_block(raw.get("demand_multiplier"), fname, "demand_multiplier"),
        critical_demand_multiplier=_norm_multiplier_block(
            raw.get("critical_demand_multiplier"), fname, "critical_demand_multiplier"
        ),
        variable_price_multiplier=_norm_multiplier_block(
            raw.get("variable_price_multiplier"), fname, "variable_price_multiplier"
        ),
        actual_delivery_share=_norm_multiplier_block(
            raw.get("actual_delivery_share"), fname, "actual_delivery_share"
        ),
        loss_ceiling=loss_ceiling,
        notes=[str(n) for n in (raw.get("notes") or [])],
    )


def _parse_plan_dict(raw: dict[str, Any], fname: str) -> Plan:
    """Разбор словаря плана (plan_format.json) в датакласс Plan."""
    for key in ("plan_id", "scenario_id", "decisions"):
        if key not in raw or raw[key] in (None, "", {}):
            raise CaseLoadError(
                f"Файл '{fname}': отсутствует обязательный параметр плана '{key}'"
            )
    decisions_raw = raw["decisions"]
    if not isinstance(decisions_raw, dict):
        raise CaseLoadError(f"Файл '{fname}': раздел 'decisions' должен быть объектом")

    for key in ("supply_orders", "capacity_reservations", "investments", "inventory_policy"):
        if key not in decisions_raw:
            raise CaseLoadError(
                f"Файл '{fname}': в разделе 'decisions' отсутствует обязательный параметр '{key}'"
            )

    def _items(section: str) -> list[dict[str, Any]]:
        val = decisions_raw[section]
        if val is None:
            return []
        if not isinstance(val, list):
            raise CaseLoadError(f"Файл '{fname}': раздел 'decisions.{section}' должен быть списком")
        return val

    supply_orders: list[SupplyOrder] = []
    for j, o in enumerate(_items("supply_orders"), start=1):
        for key in ("source_id", "period", "ordered_volume_t"):
            if key not in o:
                raise CaseLoadError(
                    f"Файл '{fname}', decisions.supply_orders[{j}]: отсутствует параметр '{key}'"
                )
        try:
            volume = float(o["ordered_volume_t"])
        except (TypeError, ValueError) as e:
            raise CaseLoadError(
                f"Файл '{fname}', decisions.supply_orders[{j}]: параметр 'ordered_volume_t' "
                f"(период {o['period']}) должен быть числом"
            ) from e
        supply_orders.append(
            SupplyOrder(source_id=str(o["source_id"]), period=str(o["period"]), ordered_volume_t=volume)
        )

    reservations: list[CapacityReservation] = []
    for j, r in enumerate(_items("capacity_reservations"), start=1):
        for key in ("source_id", "year", "reserved_capacity_t_per_year"):
            if key not in r:
                raise CaseLoadError(
                    f"Файл '{fname}', decisions.capacity_reservations[{j}]: отсутствует параметр '{key}'"
                )
        try:
            year = int(r["year"])
            reserved = float(r["reserved_capacity_t_per_year"])
            start_month = int(r.get("start_month", 1))
        except (TypeError, ValueError) as e:
            raise CaseLoadError(
                f"Файл '{fname}', decisions.capacity_reservations[{j}]: числовые поля "
                f"'year'/'reserved_capacity_t_per_year'/'start_month' заданы неверно"
            ) from e
        reservations.append(
            CapacityReservation(
                source_id=str(r["source_id"]),
                year=year,
                reserved_capacity_t_per_year=reserved,
                start_month=start_month,
            )
        )

    investments: list[Investment] = []
    for j, inv in enumerate(_items("investments"), start=1):
        for key in ("investment_id", "action", "payment_date"):
            if key not in inv:
                raise CaseLoadError(
                    f"Файл '{fname}', decisions.investments[{j}]: отсутствует параметр '{key}'"
                )
        investments.append(
            Investment(
                investment_id=str(inv["investment_id"]),
                action=str(inv["action"]),
                payment_date=str(inv["payment_date"]),
            )
        )

    policy_raw = decisions_raw["inventory_policy"]
    if not isinstance(policy_raw, dict):
        raise CaseLoadError(f"Файл '{fname}': раздел 'decisions.inventory_policy' должен быть объектом")
    initial_source: InitialInventorySource | None = None
    if policy_raw.get("initial_inventory_source"):
        src_raw = policy_raw["initial_inventory_source"]
        for key in ("source_id", "order_period", "delivery_period", "volume_t", "paid_in"):
            if key not in src_raw:
                raise CaseLoadError(
                    f"Файл '{fname}', decisions.inventory_policy.initial_inventory_source: "
                    f"отсутствует параметр '{key}'"
                )
        try:
            volume_t = float(src_raw["volume_t"])
        except (TypeError, ValueError) as e:
            raise CaseLoadError(
                f"Файл '{fname}', decisions.inventory_policy.initial_inventory_source: "
                f"параметр 'volume_t' должен быть числом"
            ) from e
        initial_source = InitialInventorySource(
            source_id=str(src_raw["source_id"]),
            order_period=str(src_raw["order_period"]),
            delivery_period=str(src_raw["delivery_period"]),
            volume_t=volume_t,
            paid_in=str(src_raw["paid_in"]),
        )
    try:
        initial_inventory_t = float(policy_raw.get("initial_inventory_t", 0.0) or 0.0)
    except (TypeError, ValueError) as e:
        raise CaseLoadError(
            f"Файл '{fname}', decisions.inventory_policy: параметр 'initial_inventory_t' должен быть числом"
        ) from e
    policy = InventoryPolicy(
        initial_inventory_t=initial_inventory_t,
        initial_inventory_source=initial_source,
        reserve_mode=str(policy_raw.get("reserve_mode") or "physical"),
        target_month_end_inventory_t=float(policy_raw.get("target_month_end_inventory_t", 0.0) or 0.0),
    )

    emergency: EmergencyContract | None = None
    if decisions_raw.get("emergency_contract"):
        ec = decisions_raw["emergency_contract"]
        if not isinstance(ec, dict):
            raise CaseLoadError(
                f"Файл '{fname}': раздел 'decisions.emergency_contract' должен быть объектом"
            )
        emergency = EmergencyContract(
            reserved_capacity_t_per_year=float(ec.get("reserved_capacity_t_per_year", 0.0) or 0.0),
            activation_lead_days=float(ec.get("activation_lead_days", 42.0) or 42.0),
            coverage_volume_t=float(ec.get("coverage_volume_t", 0.0) or 0.0),
            notes_ru=str(ec.get("notes_ru") or ""),
        )

    assumptions: list[Assumption] = []
    for j, a in enumerate(raw.get("assumptions") or [], start=1):
        for key in ("id", "value", "unit", "rationale_ru"):
            if key not in a:
                raise CaseLoadError(f"Файл '{fname}', assumptions[{j}]: отсутствует параметр '{key}'")
        assumptions.append(
            Assumption(
                id=str(a["id"]),
                value=a["value"],
                unit=str(a["unit"]),
                rationale_ru=str(a["rationale_ru"]),
                scope=str(a.get("scope") or ""),
            )
        )

    return Plan(
        plan_id=str(raw["plan_id"]),
        scenario_id=str(raw["scenario_id"]),
        decisions=PlanDecisions(
            supply_orders=supply_orders,
            capacity_reservations=reservations,
            investments=investments,
            inventory_policy=policy,
            emergency_contract=emergency,
        ),
        assumptions=assumptions,
        version=str(raw.get("version") or ""),
    )


def load_plan(plan_path: str) -> Plan:
    """Загрузка плана из JSON по схеме plan_format.json."""
    fname = os.path.basename(plan_path)
    if not os.path.isfile(plan_path):
        raise CaseLoadError(f"Файл плана '{fname}' не найден: '{plan_path}'")
    with open(plan_path, "r", encoding="utf-8") as f:
        try:
            raw = json.load(f)
        except json.JSONDecodeError as e:
            raise CaseLoadError(f"Файл '{fname}': ошибка разбора JSON — {e}") from e
    if not isinstance(raw, dict):
        raise CaseLoadError(f"Файл '{fname}': план должен быть JSON-объектом")
    return _parse_plan_dict(raw, fname)


def plan_from_dict(raw: dict[str, Any], name: str = "<dict>") -> Plan:
    """Построение Plan из словаря (для тестов и UI без промежуточного файла)."""
    return _parse_plan_dict(raw, name)
