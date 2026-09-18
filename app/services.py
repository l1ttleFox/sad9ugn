"""Единственная граница UI с данными, проверкой плана и будущим ядром."""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from copy import deepcopy
from pathlib import Path

from app.mock_data import MOCK_DIR, SCENARIOS, build_mock


ROOT = Path(__file__).resolve().parents[1]
USE_ENGINE = False  # Волна 2: включить после согласования API и типов ядра.
EXPORT_TABLES = ("yearly_balance", "source_schedule", "inventory_trace",
                 "financial_breakdown", "constraint_checks", "risk_register")


def available_scenarios() -> tuple[str, ...]:
    return SCENARIOS


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
    if plan.get("scenario_id") not in SCENARIOS:
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
        if not isinstance(volume, (int, float)) or volume < 0:
            errors.append(f"Заказ {index}, период {period}: ordered_volume_t должен быть неотрицательным числом.")
    for index, reservation in enumerate(decisions.get("capacity_reservations", []), 1):
        source = reservation.get("source_id")
        year = reservation.get("year")
        value = reservation.get("reserved_capacity_t_per_year")
        if source not in capacities:
            errors.append(f"Резервирование {index}, год {year}: канал source_id={source} отсутствует в CASE_INPUT.")
        if not isinstance(year, int) or not 2035 <= year <= 2040:
            errors.append(f"Резервирование {index}: год {year} вне горизонта 2035–2040.")
        if not isinstance(value, (int, float)) or value < 0:
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
        if not isinstance(value, (int, float)) or value < 0:
            errors.append(f"Политика запаса: {key} должен быть неотрицательным числом.")
    source = policy.get("initial_inventory_source", {})
    if source.get("source_id") not in capacities:
        errors.append("Начальный запас: initial_inventory_source.source_id отсутствует в CASE_INPUT.")
    if policy.get("reserve_mode") not in ("physical", "contractual_emergency"):
        errors.append("Политика запаса: reserve_mode должен быть physical или contractual_emergency.")
    return errors


def get_run_result(scenario_id: str, plan: dict) -> dict:
    """Получить RunResult. Пока всегда мок; переключение на ядро только здесь."""
    if scenario_id not in SCENARIOS:
        raise ValueError(f"Сценарий {scenario_id} недоступен.")
    errors = validate_plan({**plan, "scenario_id": scenario_id})
    if errors:
        raise ValueError("\n".join(errors))
    if USE_ENGINE:
        try:
            from src.engine import load_case, load_scenario, run_plan
            from src.engine import load_plan as engine_load_plan

            case = load_case(str(ROOT / "data"))
            scenario = load_scenario(str(ROOT / "configs" / f"{scenario_id}.yaml"))
            # Тип Plan ядра создаётся через опубликованный loader в волне 2.
            # Временный JSON — только адаптер внутри services.
            import tempfile

            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "plan.json"
                path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
                result = run_plan(case, engine_load_plan(str(path)), scenario)
            return result if isinstance(result, dict) else vars(result)
        except (ImportError, AttributeError, FileNotFoundError, TypeError):
            pass
    path = MOCK_DIR / f"{scenario_id}.json"
    result = json.loads(path.read_text(encoding="utf-8")) if path.exists() else build_mock(scenario_id)
    result = deepcopy(result)
    result["plan_id"] = plan["plan_id"]
    return result


def save_plan_json(plan: dict) -> bytes:
    errors = validate_plan(plan)
    if errors:
        raise ValueError("\n".join(errors))
    return (json.dumps(plan, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


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
