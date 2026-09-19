"""Единственная граница UI с данными, проверкой плана и будущим ядром."""

from __future__ import annotations

import csv
import importlib
import tempfile
from dataclasses import asdict, is_dataclass
from functools import lru_cache
import io
import json
import math
import re
import zipfile
from copy import deepcopy
from pathlib import Path

from app.mock_data import MOCK_DIR, SCENARIOS, build_mock


ROOT = Path(__file__).resolve().parents[1]
USE_ENGINE = True  # При наличии опубликованного src/engine используется ядро; иначе демо-моки.
EXPORT_TABLES = ("yearly_balance", "source_schedule", "inventory_trace",
                 "financial_breakdown", "constraint_checks", "risk_register")
TEAM_SCENARIO_DIRS = (
    ROOT / "configs" / "team",
    ROOT / "ai_workstreams" / "WP3_stress_risk" / "configs" / "team",
)


def available_scenarios() -> tuple[str, ...]:
    team = tuple(dict.fromkeys(
        path.stem
        for directory in TEAM_SCENARIO_DIRS
        for path in sorted(directory.glob("TEAM_*.yaml"))
    ))
    base = ("BASE", "MANDATORY_STRESS") if engine_available() else SCENARIOS
    return base + tuple(x for x in team if x not in base)


def source_catalog() -> list[dict]:
    with (ROOT / "data" / "supply_sources.csv").open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def storage_catalog() -> list[dict]:
    with (ROOT / "data" / "storage_options.csv").open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def constraint_catalog() -> list[dict]:
    with (ROOT / "data" / "constraints.csv").open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def default_plan(scenario_id: str = "BASE") -> dict:
    return {
        "plan_id": "UI-MOCK-PLAN", "scenario_id": scenario_id, "version": "1.0",
        "decisions": {
            "supply_orders": [], "capacity_reservations": [], "investments": [],
            "inventory_policy": {
                "initial_inventory_t": 0.0,
                "initial_inventory_source": {"source_id": "A", "order_period": "2034-01",
                                             "delivery_period": "2035-01", "volume_t": 0.0,
                                             "paid_in": "2035"},
                "reserve_mode": "physical", "target_month_end_inventory_t": 0.0,
            },
            "emergency_contract": None,
        },
        "assumptions": [],
    }


def validate_plan(plan: dict) -> list[str]:
    """Клиентская проверка решений по схеме и мощностям из data/*.csv."""
    errors = []
    capacities = {r["source_id"]: float(r["capacity_t_per_year"]) for r in source_catalog()}
    if not str(plan.get("plan_id", "")).strip():
        errors.append("Параметр plan_id: укажите идентификатор плана.")
    if plan.get("scenario_id") not in available_scenarios():
        errors.append("Параметр scenario_id: неизвестный сценарий.")
    decisions = plan.get("decisions", {})
    for index, order in enumerate(decisions.get("supply_orders", []), 1):
        source = order.get("source_id")
        period = str(order.get("period", ""))
        volume = order.get("ordered_volume_t")
        if source not in capacities:
            errors.append(f"Заказ {index}, период {period}: канал source_id={source} отсутствует в CASE_INPUT.")
        if not re.fullmatch(r"20(3[5-9]|4[0-9])(?:-(?:0[1-9]|1[0-2]))?", period):
            errors.append(f"Заказ {index}: период {period} должен быть YYYY или YYYY-MM.")
        if not isinstance(volume, (int, float)) or not math.isfinite(volume) or volume < 0:
            errors.append(f"Заказ {index}, период {period}: ordered_volume_t должен быть неотрицательным числом.")
    for index, reservation in enumerate(decisions.get("capacity_reservations", []), 1):
        source = reservation.get("source_id")
        year = reservation.get("year")
        value = reservation.get("reserved_capacity_t_per_year")
        if source not in capacities:
            errors.append(f"Резервирование {index}, год {year}: канал source_id={source} отсутствует в CASE_INPUT.")
        if not isinstance(year, int) or not 2035 <= year <= 2040:
            errors.append(f"Резервирование {index}: год {year} вне горизонта 2035–2040.")
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            errors.append(f"Резервирование {index}, год {year}: reserved_capacity_t_per_year должен быть неотрицательным числом.")
        elif source in capacities and value > capacities[source]:
            errors.append(f"Резервирование {index}, год {year}: reserved_capacity_t_per_year={value:g} т/год "
                          f"превышает мощность канала {source} {capacities[source]:g} т/год.")
    for index, investment in enumerate(decisions.get("investments", []), 1):
        date = str(investment.get("payment_date", ""))
        if investment.get("investment_id") not in ("EARTH_NEW", "LUNAR_ISRU", "ZBO"):
            errors.append(f"Инвестиция {index}, период {date}: неизвестный investment_id.")
        if investment.get("action") not in ("buy_option", "exercise_option", "fund_capex", "none"):
            errors.append(f"Инвестиция {index}, период {date}: неизвестный action.")
        if not re.fullmatch(r"20(3[4-9]|4[0-9])-(?:0[1-9]|1[0-2])", date):
            errors.append(f"Инвестиция {index}: payment_date={date} должен быть YYYY-MM.")
    policy = decisions.get("inventory_policy", {})
    for key in ("initial_inventory_t", "target_month_end_inventory_t"):
        value = policy.get(key, 0)
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            errors.append(f"Политика запаса: {key} должен быть неотрицательным числом.")
    source = policy.get("initial_inventory_source", {})
    if source.get("source_id") not in capacities:
        errors.append("Начальный запас: initial_inventory_source.source_id отсутствует в CASE_INPUT.")
    if policy.get("reserve_mode") not in ("physical", "contractual_emergency"):
        errors.append("Политика запаса: reserve_mode должен быть physical или contractual_emergency.")
    return errors


def engine_available() -> bool:
    """Включать единый реальный результат только после завершения публичного API WP1."""
    engine_dir = ROOT / "src" / "engine"
    if not USE_ENGINE or not engine_dir.is_dir():
        return False
    required = ("finance.py", "constraints.py", "risks.py", "compare.py",
                "persistence.py", "export.py")
    return all((engine_dir / name).exists() and
               "raise NotImplementedError" not in (engine_dir / name).read_text(encoding="utf-8")
               for name in required)


def _scenario_path(scenario_id: str) -> Path:
    if scenario_id == "BASE":
        return ROOT / "configs" / "base.yaml"
    if scenario_id == "MANDATORY_STRESS":
        return ROOT / "configs" / "mandatory_stress.yaml"
    for directory in TEAM_SCENARIO_DIRS:
        path = directory / f"{scenario_id}.yaml"
        if path.exists():
            return path
    raise ValueError(f"Сценарий {scenario_id}: файл конфигурации TEAM_* не найден.")


@lru_cache(maxsize=1)
def _load_case_cached():
    engine = importlib.import_module("src.engine")
    return engine.load_case(str(ROOT / "data"))


@lru_cache(maxsize=64)
def _run_core_cached(scenario_id: str, plan_json: str):
    engine = importlib.import_module("src.engine")
    scenario = engine.load_scenario(str(_scenario_path(scenario_id)))
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "plan.json"
        path.write_text(plan_json, encoding="utf-8")
        core_plan = engine.load_plan(str(path))
        case = _load_case_cached()
        if scenario.scenario_parameters:
            case, adapted_plan = engine.apply_scenario_parameters(case, scenario, core_plan)
            core_plan = adapted_plan or core_plan
        return engine.run_plan(case, core_plan, scenario)


def _result_dict(result) -> dict:
    """Преобразовать вложенный WP1 RunResult в плоский контракт UI v1.0."""
    if isinstance(result, dict):
        data = deepcopy(result)
    elif is_dataclass(result):
        data = asdict(result)
    elif hasattr(result, "model_dump"):
        data = result.model_dump(mode="json")
    elif hasattr(result, "to_dict"):
        data = result.to_dict()
    else:
        raise TypeError("Ядро вернуло неизвестный тип RunResult.")
    if "monthly_balance" in data:
        return data
    if not all(key in data for key in ("deliveries", "inventory", "service", "costs", "meta")):
        raise ValueError("RunResult ядра не содержит обязательные разделы контракта.")
    checks = data.get("checks")
    if checks is None:
        checks = data.get("constraint_checks")
    if checks is None:
        raise ValueError("RunResult ядра не содержит полного списка constraint_checks (поле checks).")
    return {"scenario_id": data["scenario_id"], "plan_id": data["plan_id"],
            "monthly_balance": data["inventory"]["monthly_balance"],
            "yearly_balance": data["service"]["yearly_balance"],
            "source_schedule": data["deliveries"]["source_schedule"],
            "inventory_trace": data["inventory"]["inventory_trace"],
            "financial_breakdown": data["costs"]["financial_breakdown"],
            "constraint_checks": checks,
            "risk_register": data.get("risks", {}).get("risk_register", []),
            "meta": data["meta"]}


def get_run_result(scenario_id: str, plan: dict) -> dict:
    """Возвращает RunResult; при отсутствии ядра сохраняет демо-режим."""
    if scenario_id not in available_scenarios():
        raise ValueError(f"Сценарий {scenario_id} недоступен.")
    prepared = {**plan, "scenario_id": scenario_id}
    errors = validate_plan(prepared)
    if errors:
        raise ValueError("\n".join(errors))
    if engine_available():
        try:
            result = _run_core_cached(scenario_id, json.dumps(prepared, ensure_ascii=False, sort_keys=True))
            return _result_dict(result)
        except Exception as exc:
            raise ValueError(f"Расчёт сценария {scenario_id}: {exc}") from exc
    if scenario_id not in SCENARIOS:
        raise ValueError(f"Сценарий {scenario_id} ожидает ядро WP1; сейчас доступен только демо-режим до завершения WP1.")
    path = MOCK_DIR / f"{scenario_id}.json"
    result = json.loads(path.read_text(encoding="utf-8")) if path.exists() else build_mock(scenario_id)
    result = deepcopy(result)
    result["plan_id"] = plan["plan_id"]
    return result


def run_geo_scenario(plan: dict, event_label: str, source_id: str,
                     multiplier: float, first_year: int, last_year: int) -> dict:
    """Исследовательский ценовой шок; CASE_INPUT-файлы не изменяются."""
    if not engine_available():
        raise ValueError("Геополитический сценарий ожидает завершения расчётного ядра WP1.")
    if not event_label.strip():
        raise ValueError("Событие: укажите event_label.")
    sources = {row["source_id"]: row["name"] for row in source_catalog()}
    if source_id not in sources:
        raise ValueError(f"Геополитический сценарий: канал {source_id} не существует.")
    if multiplier < 0:
        raise ValueError("Коэффициент цены должен быть неотрицательным.")
    if not 2035 <= first_year <= last_year <= 2040:
        raise ValueError("Период события должен находиться внутри 2035–2040.")
    errors = validate_plan({**plan, "scenario_id": "BASE"})
    if errors:
        raise ValueError("\n".join(errors))
    years_yaml = "\n".join(f"    {year}: {multiplier}" for year in range(first_year, last_year + 1))
    content = ("scenario_id: TEAM_GEO\nlabel_ru: " + json.dumps(event_label, ensure_ascii=False) +
               "\nstatus: TEAM_ASSUMPTION\ndemand_multiplier:\n  default: 1.0\n" +
               "variable_price_multiplier:\n  " + sources[source_id] + ":\n" + years_yaml +
               "\nactual_delivery_share:\n  default: 1.0\nloss_ceiling:\n  enabled: false\n" +
               "notes:\n  - 'Исследовательский ценовой шок; вероятность не задана.'\n")
    engine = importlib.import_module("src.engine")
    with tempfile.TemporaryDirectory() as folder:
        scenario_path = Path(folder) / "TEAM_GEO.yaml"
        scenario_path.write_text(content, encoding="utf-8")
        plan_path = Path(folder) / "plan.json"
        plan_path.write_text(json.dumps({**plan, "scenario_id": "TEAM_GEO"}, ensure_ascii=False), encoding="utf-8")
        try:
            scenario = engine.load_scenario(str(scenario_path))
            core_plan = engine.load_plan(str(plan_path))
            result = engine.run_plan(_load_case_cached(), core_plan, scenario)
            return _result_dict(result)
        except Exception as exc:
            raise ValueError(f"Геополитический сценарий {first_year}–{last_year}: {exc}") from exc


def geo_effect(base: dict, geo: dict) -> dict:
    return {"base_cost_mln": sum(x["total_mln"] for x in base["financial_breakdown"]),
            "geo_cost_mln": sum(x["total_mln"] for x in geo["financial_breakdown"]),
            "base_delivered_t": sum(x["delivered_t"] for x in base["yearly_balance"]),
            "geo_delivered_t": sum(x["delivered_t"] for x in geo["yearly_balance"]),
            "base_shortage_t": sum(x["shortage_t"] for x in base["yearly_balance"]),
            "geo_shortage_t": sum(x["shortage_t"] for x in geo["yearly_balance"])}


def clear_result_cache() -> None:
    _run_core_cached.cache_clear()


def list_saved_plans() -> list[dict]:
    directory = ROOT / "results" / "plans"
    if not directory.exists():
        return []
    found = []
    for path in sorted(directory.glob("*.json")):
        if path.name.endswith("_contracts.json"):
            continue
        try:
            plan = load_plan_json(path.read_bytes())
            found.append({"file": path.name, "plan_id": plan["plan_id"],
                          "scenario_id": plan["scenario_id"]})
        except ValueError:
            continue
    return found


def _safe_plan_stem(name: str) -> str:
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name.strip()).strip(" .")
    return stem[:80] or "plan"


def _resolve_catalog_path(filename: str) -> Path:
    if filename.startswith("wp2::"):
        directory = (ROOT / "ai_workstreams" / "WP2_strategy_economics" / "plans").resolve()
        relative = filename.removeprefix("wp2::")
    else:
        directory = (ROOT / "results" / "plans").resolve()
        relative = filename
    path = (directory / relative).resolve()
    if path.parent != directory or path.suffix.lower() != ".json":
        raise ValueError("Имя плана: недопустимый путь к файлу.")
    return path


def contracts_json(plan_id: str, contracts: list[dict]) -> bytes:
    def json_value(value):
        if hasattr(value, "item"):
            try:
                value = value.item()
            except (TypeError, ValueError):
                pass
        if isinstance(value, float) and not math.isfinite(value):
            return None
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        return str(value)

    cleaned = []
    for row in contracts:
        cleaned.append({
            str(key): json_value(value)
            for key, value in row.items()
        })
    payload = {"plan_id": plan_id, "version": "1.0", "contracts": cleaned}
    return (json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def save_plan_to_catalog(plan: dict, name: str, contracts: list[dict] | None = None) -> str:
    if not name.strip():
        raise ValueError("Имя сохранения: укажите название плана.")
    prepared = deepcopy(plan)
    prepared["plan_id"] = name.strip()
    payload = save_plan_json(prepared)
    directory = ROOT / "results" / "plans"
    directory.mkdir(parents=True, exist_ok=True)
    safe_stem = _safe_plan_stem(name)
    path = directory / f"{safe_stem}.json"
    if engine_available():
        engine = importlib.import_module("src.engine")
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "plan.json"
            source.write_bytes(payload)
            engine.save_plan(engine.load_plan(str(source)), str(path))
    else:
        path.write_bytes(payload)
    if contracts is not None:
        (directory / f"{safe_stem}_contracts.json").write_bytes(
            contracts_json(prepared["plan_id"], contracts)
        )
    return path.name


def load_plan_from_catalog(filename: str) -> dict:
    path = _resolve_catalog_path(filename)
    if not path.exists():
        raise ValueError(f"Файл плана {filename} не найден.")
    if engine_available():
        engine = importlib.import_module("src.engine")
        return asdict(engine.load_saved_plan(str(path)))
    return load_plan_json(path.read_bytes())


def load_contracts_from_catalog(filename: str) -> list[dict]:
    path = _resolve_catalog_path(filename)
    if filename.startswith("wp2::"):
        return []
    contracts_path = path.with_name(f"{path.stem}_contracts.json")
    if not contracts_path.exists():
        return []
    try:
        payload = json.loads(contracts_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Реестр договоров {contracts_path.name}: неверный JSON ({exc}).") from exc
    rows = payload.get("contracts") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"Реестр договоров {contracts_path.name}: поле contracts должно быть списком объектов.")
    return rows


def final_plan_files() -> list[dict]:
    finals = [
        {
            **item,
            "label": (
                f"FINAL STRESS — {item['plan_id']}"
                if item["scenario_id"] == "MANDATORY_STRESS"
                else f"FINAL BASE — {item['plan_id']}"
            ),
        }
        for item in list_saved_plans()
        if "FINAL" in item["plan_id"].upper() or "FINAL" in item["file"].upper()
    ]
    if finals:
        return finals
    wp2_dir = ROOT / "ai_workstreams" / "WP2_strategy_economics" / "plans"
    candidates = sorted(wp2_dir.glob("*FINAL*.json"))
    fallback = False
    if not candidates and (wp2_dir / "S10.json").exists():
        candidates = [wp2_dir / "S10.json"]
        fallback = True
    found = []
    for path in candidates:
        try:
            plan = load_plan_json(path.read_bytes())
        except ValueError:
            continue
        found.append({
            "file": f"wp2::{path.name}",
            "plan_id": plan["plan_id"],
            "scenario_id": plan["scenario_id"],
            "label": (
                f"{plan['plan_id']} (до публикации FINAL)"
                if fallback
                else (
                    f"FINAL STRESS — {plan['plan_id']}"
                    if plan["scenario_id"] == "MANDATORY_STRESS"
                    else f"FINAL BASE — {plan['plan_id']}"
                )
            ),
        })
    return found


def apply_decision_rows(plan: dict, section: str, rows: list[dict]) -> dict:
    """Проверить правки таблицы и вернуть обновлённый план без мутации исходника."""
    allowed = {
        "supply_orders": ("source_id", "period", "ordered_volume_t"),
        "capacity_reservations": ("source_id", "year", "reserved_capacity_t_per_year", "start_month"),
        "investments": ("investment_id", "action", "payment_date"),
    }
    if section not in allowed:
        raise ValueError(f"Раздел решений {section} неизвестен.")
    cleaned = []
    for index, row in enumerate(rows, 1):
        item = {}
        for key in allowed[section]:
            value = row.get(key)
            if isinstance(value, float) and math.isnan(value):
                value = None
            if key in ("year", "start_month") and isinstance(value, (int, float)) and math.isfinite(value):
                if value.is_integer() if isinstance(value, float) else True:
                    value = int(value)
            item[key] = value
        if all(value is None or value == "" for value in item.values()):
            continue
        cleaned.append(item)
    candidate = deepcopy(plan)
    candidate["decisions"][section] = cleaned
    errors = validate_plan(candidate)
    if errors:
        raise ValueError("\n".join(errors))
    return candidate


def save_plan_json(plan: dict) -> bytes:
    errors = validate_plan(plan)
    if errors:
        raise ValueError("\n".join(errors))
    return (json.dumps(plan, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def load_plan_json(payload: bytes) -> dict:
    try:
        plan = json.loads(payload.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Файл плана: неверный JSON ({exc}).") from exc
    if not isinstance(plan, dict):
        raise ValueError("Файл плана: корнем должен быть объект JSON.")
    errors = validate_plan(plan)
    if errors:
        raise ValueError("\n".join(errors))
    return plan


def export_core_archive(scenario_id: str, plan: dict, fmt: str = "csv") -> bytes:
    """Экспорт того же кэшированного RunResult через API ядра."""
    if not engine_available():
        raise ValueError("Экспорт ядра недоступен: публичный API WP1 ещё не завершён.")
    if fmt not in ("csv", "xlsx"):
        raise ValueError(f"Формат экспорта {fmt} не поддерживается.")
    engine = importlib.import_module("src.engine")
    prepared = {**plan, "scenario_id": scenario_id}
    core_result = _run_core_cached(scenario_id, json.dumps(prepared, ensure_ascii=False, sort_keys=True))
    with tempfile.TemporaryDirectory() as folder:
        try:
            paths = engine.export_results(core_result, folder, fmt=fmt)
        except Exception as exc:
            raise ValueError(f"Выгрузка сценария {scenario_id}: {exc}") from exc
        if not paths:
            raise ValueError(f"Выгрузка сценария {scenario_id}: ядро не создало файлов.")
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for name in paths:
                path = Path(name)
                if not path.is_absolute():
                    path = Path(folder) / path
                if not path.exists():
                    raise ValueError(f"Выгрузка сценария {scenario_id}: файл {path.name} не найден.")
                archive.write(path, arcname=path.name)
            result = _result_dict(core_result)
            envelope_meta = {"scenario_id": scenario_id, "plan_id": result["plan_id"],
                             "periods": [row["year"] for row in result["yearly_balance"]],
                             "units": {"volume": "т", "capacity": "т/год",
                                       "money": "млн у.е. (цены 2035)", "service_level": "доля"},
                             "assumptions_reference": result["meta"]["assumptions_reference"],
                             "meta": result["meta"]}
            archive.writestr("export_meta.json", json.dumps(envelope_meta, ensure_ascii=False, indent=2))
        return output.getvalue()


def export_csv_zip(result: dict) -> bytes:
    """Шесть таблиц CSV и конверт, совместимый с export.schema.json."""
    envelope = {"scenario_id": result["scenario_id"], "plan_id": result["plan_id"],
                "units": {"volume": "т", "capacity": "т/год", "money": "млн у.е. (цены 2035)",
                          "service_level": "доля"},
                "assumptions_reference": result["meta"]["assumptions_reference"],
                **{name: result.get(name, []) for name in EXPORT_TABLES}}
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("export_envelope.json", json.dumps(envelope, ensure_ascii=False, indent=2))
        for name in EXPORT_TABLES:
            rows = envelope[name]
            stream = io.StringIO()
            if rows:
                fields = list(dict.fromkeys(key for row in rows for key in row))
                writer = csv.DictWriter(stream, fieldnames=("scenario_id", "plan_id", *fields))
                writer.writeheader()
                for row in rows:
                    writer.writerow({"scenario_id": result["scenario_id"],
                                     "plan_id": result["plan_id"], **row})
            archive.writestr(f"{name}.csv", "\ufeff" + stream.getvalue())
    return output.getvalue()



def overview_summary(result: dict) -> dict:
    years = result["yearly_balance"]
    costs = result["financial_breakdown"]
    return {
        "demand_t": sum(x["demand_total_t"] for x in years),
        "served_t": sum(x["served_total_t"] for x in years),
        "shortage_t": sum(x["shortage_t"] for x in years),
        "cost_mln": sum(x["total_mln"] for x in costs),
        "annual_rows": [{"Год": y["year"], "Спрос, т": y["demand_total_t"],
                         "Поставки, т": y["delivered_t"], "Запас на конец, т": y["i_end_t"],
                         "Потери, т": y["losses_t"], "Расходы, млн у.е.": c["total_mln"],
                         "Дефицит, т": y["shortage_t"]}
                        for y, c in zip(years, costs)],
    }


def chart_thresholds() -> dict:
    values = {r["constraint_id"]: float(r["value"]) for r in constraint_catalog()}
    return {"capex_2037": values["CAPEX_2037"], "capex_2040": values["CAPEX_2040"],
            "sl_total": values["BASE_TOTAL_SERVICE"],
            "sl_critical": values["BASE_CRITICAL_SERVICE"]}


def scenario_deltas(base: dict, stress: dict) -> list[dict]:
    return [{"Год": b["year"],
             "Изменение спроса, т": round(s["demand_total_t"] - b["demand_total_t"], 3),
             "Изменение дефицита, т": round(s["shortage_t"] - b["shortage_t"], 3),
             "Изменение расходов, млн у.е.": round(sf["total_mln"] - bf["total_mln"], 3),
             "Изменение SL общего, п.п.": round((s["sl_total"] - b["sl_total"]) * 100, 3)}
            for b, s, bf, sf in zip(base["yearly_balance"], stress["yearly_balance"],
                                     base["financial_breakdown"], stress["financial_breakdown"])]


def scenario_comparison(base: dict, stress: dict) -> list[dict]:
    rows = []
    for title, item in (("Базовый", base), ("Обязательный стресс", stress)):
        years = item["yearly_balance"]
        rows.append({"Сценарий": title,
                     "Расходы, млн у.е.": round(sum(x["total_mln"] for x in item["financial_breakdown"]), 2),
                     "SL общий, доля": round(sum(x["served_total_t"] for x in years) / sum(x["demand_total_t"] for x in years), 4),
                     "SL критический, доля": round(sum(x["served_critical_t"] for x in years) / sum(x["demand_critical_t"] for x in years), 4),
                     "Запас на конец 2040, т": years[-1]["i_end_t"],
                     "Дефицит, т": round(sum(x["shortage_t"] for x in years), 2),
                     "Нарушения, шт.": sum(not x["passed"] for x in item["constraint_checks"])})
    return rows


def violation_count(result: dict) -> int:
    return sum(not item["passed"] for item in result["constraint_checks"])
