"""Детерминированные синтетические данные для первой волны UI.

Числа намеренно отличаются от CASE_INPUT и не являются результатом стратегий.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


MOCK_DIR = Path(__file__).resolve().parent / "mocks"
SOURCES = ("A", "B", "C", "D", "E")
SCENARIOS = ("BASE", "MANDATORY_STRESS", "TEAM_RESEARCH")


def build_mock(scenario_id: str) -> dict:
    """Собрать правдоподобный RunResult строго с ключами result_format v1.0."""
    if scenario_id not in SCENARIOS:
        raise ValueError(f"Неизвестный сценарий: {scenario_id}")
    factor = {"BASE": 1.0, "MANDATORY_STRESS": 1.18, "TEAM_RESEARCH": 1.09}[scenario_id]
    delivery_factor = {"BASE": 1.0, "MANDATORY_STRESS": 0.88, "TEAM_RESEARCH": 0.94}[scenario_id]
    monthly, schedule, inventory, yearly, finance, checks = [], [], [], [], [], []
    cumulative_capex = 0.0
    previous_end = 37.0
    for year in range(2035, 2041):
        first_inventory = previous_end
        annual = {key: 0.0 for key in (
            "demand_total_t", "demand_critical_t", "delivered_t", "losses_t",
            "served_total_t", "served_critical_t", "shortage_t")}
        source_total = {source: 0.0 for source in SOURCES}
        for month in range(1, 13):
            period = f"{year}-{month:02d}"
            demand = round((8.35 + (year - 2035) * 4.47 + (month % 4) * 0.13) * factor, 3)
            critical = round(demand * 0.69, 3)
            planned = round((demand * 0.93 + 0.58) / delivery_factor, 3)
            delivered = round(planned * delivery_factor, 3)
            losses = round(delivered * (0.013 if year >= 2038 else 0.034), 3)
            available = round(previous_end + delivered - losses, 3)
            served = round(min(demand, max(0.0, available - 2.0)), 3)
            served_critical = round(min(critical, served), 3)
            shortage = round(max(0.0, demand - served), 3)
            end = round(max(0.0, available - served), 3)
            capacity = 123.0 if year >= 2038 else 73.0
            row = {
                "period": period, "i_start_t": previous_end, "delivered_t": delivered,
                "throughput_t": delivered, "losses_t": losses, "served_total_t": served,
                "served_critical_t": served_critical, "demand_total_t": demand,
                "demand_critical_t": critical, "shortage_t": shortage,
                "i_end_t": end, "storage_mode": "ZBO" if year >= 2038 else "BASE",
                "storage_capacity_t": capacity,
            }
            monthly.append(row)
            inventory.append({"period": period, "inventory_t": end,
                              "reserve_threshold_t": round(demand * 12 * 45 / 365, 3),
                              "capacity_t": capacity})
            for key in annual:
                annual[key] += row[key]
            shares = (0.37, 0.23, 0.19, 0.14, 0.07)
            for source, share in zip(SOURCES, shares):
                volume = round(delivered * share, 3)
                source_total[source] += volume
                schedule.append({
                    "source_id": source, "period": period,
                    "reserved_capacity_t_per_year": {"A": 61.0, "B": 43.0, "C": 37.0,
                                                     "D": 29.0, "E": 17.0}[source],
                    "ordered_volume_t": round(planned * share, 3),
                    "planned_delivery_t": round(planned * share, 3),
                    "actual_delivery_t": volume,
                    "lead_time_applied": {"A": "12 month", "B": "4 month", "C": "24 month",
                                          "D": "2 month", "E": "6 week"}[source],
                })
            previous_end = end
        annual = {key: round(value, 3) for key, value in annual.items()}
        reserve = round(annual["demand_total_t"] * 45 / 365, 3)
        total_sl = round(annual["served_total_t"] / annual["demand_total_t"], 5)
        critical_sl = round(annual["served_critical_t"] / annual["demand_critical_t"], 5)
        yearly.append({"year": year, **annual, "sl_total": total_sl,
                       "sl_critical": critical_sl, "i_start_t": first_inventory,
                       "i_end_t": previous_end, "reserve_required_t": reserve,
                       "reserve_actual_start_t": first_inventory,
                       "reserve_ok": first_inventory >= reserve})
        capex = 347.0 if year == 2037 else (193.0 if year == 2038 else 0.0)
        cumulative_capex += capex
        procurement = round(sum(source_total[s] * {"A": 5.8, "B": 8.3, "C": 6.7,
                                                         "D": 2.7, "E": 12.4}[s]
                                for s in SOURCES), 3)
        reservation = round(32.0 + (year - 2035) * 1.7, 3)
        holding = round((first_inventory + previous_end) / 2 * 0.68, 3)
        opex = 13.0 if year >= 2038 else 0.0
        total = round(capex + procurement + reservation + holding + opex, 3)
        finance.append({"year": year, "capex_mln": capex,
                        "capex_cumulative_mln": cumulative_capex,
                        "procurement_mln": procurement, "reservation_mln": reservation,
                        "take_or_pay_extra_mln": 0.0, "holding_mln": holding,
                        "fixed_opex_mln": opex, "total_mln": total,
                        "discounted_mln": round(total / 1.1 ** (year - 2035), 3),
                        "cost_per_served_t_mln": round(total / annual["served_total_t"], 4)})
        for rule, actual, limit, passed, unit in (
            ("BASE_TOTAL_SERVICE", total_sl, 0.97, total_sl >= 0.97, "доля"),
            ("BASE_CRITICAL_SERVICE", critical_sl, 0.99, critical_sl >= 0.99, "доля"),
            ("RESERVE_45D", first_inventory, reserve, first_inventory >= reserve, "т"),
        ):
            checks.append({"rule_id": rule, "period": str(year), "passed": passed,
                           "actual": actual, "limit": limit,
                           "excess": round(abs(actual - limit), 5) if not passed else 0.0,
                           "message_ru": (f"{rule}: {year}, факт {actual:.3f} {unit}, "
                                          f"порог {limit:.3f} {unit}; "
                                          + ("условие выполнено" if passed else "условие нарушено"))})
    # Намеренные нарушения для проверки представления на всех сценариях.
    checks.extend([
        {"rule_id": "CAPACITY_EXCEEDED", "period": "2038-06", "passed": False,
         "actual": 84.7, "limit": 80.0, "excess": 4.7,
         "message_ru": "Синтетический пример: в 2038-06 заказ аварийного канала превышает мощность на 4,7 т."},
        {"rule_id": "LEAD_TIME_VIOLATION", "period": "2037-04", "passed": False,
         "actual": 3.0, "limit": 4.0, "excess": 1.0,
         "message_ru": "Синтетический пример: заказ канала B в 2037-04 размещён на месяц позднее допустимого срока."},        {"rule_id": "CAPEX_2037", "period": "2037", "passed": True,
         "actual": 347.0, "limit": 1800.0, "excess": 0.0,
         "message_ru": "Синтетический CAPEX до 2037 года находится в пределах лимита."},
        {"rule_id": "CAPEX_2040", "period": "2040", "passed": True,
         "actual": 540.0, "limit": 2800.0, "excess": 0.0,
         "message_ru": "Синтетический CAPEX до 2040 года находится в пределах лимита."},
    ])
    if scenario_id == "MANDATORY_STRESS":
        checks.append({"rule_id": "STRESS_LOSS_LIMIT", "period": "2038", "passed": False,
                       "actual": 0.027, "limit": 0.02, "excess": 0.007,
                       "message_ru": "Синтетический пример: доля потерь в 2038 году выше порога на 0,007."})
    else:
        checks.append({"rule_id": "EMERGENCY_BASE_STREAK", "period": "2035–2040",
                       "passed": True, "actual": 1.0, "limit": 2.0, "excess": 0.0,
                       "message_ru": "Синтетический пример: аварийный канал не используется как базовый более двух лет подряд."})
    return {
        "scenario_id": scenario_id, "plan_id": "MOCK-PLAN-01",
        "monthly_balance": monthly, "yearly_balance": yearly,
        "source_schedule": schedule, "inventory_trace": inventory,
        "financial_breakdown": finance, "constraint_checks": checks,
        "risk_register": [
            {"risk_id": "MOCK-R1", "scenario_id": "TEAM_RESEARCH", "consequence_t": round(11.4 * factor, 3),
             "consequence_mln": round(74.2 * factor, 3), "consequence_sl": round(0.023 * factor, 5),
             "probability_basis_ru": "Синтетический риск; вероятность не оценена."},
            {"risk_id": "MOCK-R2", "scenario_id": "TEAM_RESEARCH", "consequence_t": round(6.3 * factor, 3),
             "consequence_mln": round(39.6 * factor, 3), "consequence_sl": round(0.011 * factor, 5),
             "probability_basis_ru": "Синтетический риск; вероятность не оценена."},
        ],
        "meta": {"engine_version": "MOCK", "contract_version": "1.0", "timestep": "monthly",
                 "discount_rate": 0.10, "discount_t0": 2035,
                 "assumptions_reference": "ai_workstreams/00_contracts/units_and_conventions.md",
                 "generated_at": datetime(2026, 9, 19, tzinfo=timezone.utc).isoformat(),
                 "random_seed": None},
    }


def write_mocks() -> None:
    MOCK_DIR.mkdir(parents=True, exist_ok=True)
    for scenario in SCENARIOS:
        (MOCK_DIR / f"{scenario}.json").write_text(
            json.dumps(build_mock(scenario), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")


if __name__ == "__main__":
    write_mocks()

