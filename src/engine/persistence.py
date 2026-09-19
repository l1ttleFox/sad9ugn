"""Сохранение/загрузка планов: JSON по схеме plan_format.json.

save_plan — сериализация датакласса Plan (idempotent: save → load → save
даёт байт-в-байт тот же JSON). load_saved_plan — загрузка с валидацией
структуры (loader._parse_plan_dict: обязательные поля, типы; ошибки —
CaseLoadError с русским сообщением, называющим файл и параметр).
"""

from __future__ import annotations

import json
import os
from typing import Any

from .loader import load_plan
from .models import Plan


def plan_to_dict(plan: Plan) -> dict[str, Any]:
    """Сериализация Plan в словарь plan_format.json (ключи — английские)."""
    d = plan.decisions
    policy: dict[str, Any] = {
        "initial_inventory_t": d.inventory_policy.initial_inventory_t,
        "reserve_mode": d.inventory_policy.reserve_mode,
        "target_month_end_inventory_t": d.inventory_policy.target_month_end_inventory_t,
    }
    src = d.inventory_policy.initial_inventory_source
    if src is not None:
        policy["initial_inventory_source"] = {
            "source_id": src.source_id,
            "order_period": src.order_period,
            "delivery_period": src.delivery_period,
            "volume_t": src.volume_t,
            "paid_in": src.paid_in,
        }
    out: dict[str, Any] = {
        "plan_id": plan.plan_id,
        "scenario_id": plan.scenario_id,
        "decisions": {
            "supply_orders": [
                {
                    "source_id": o.source_id,
                    "period": o.period,
                    "ordered_volume_t": o.ordered_volume_t,
                }
                for o in d.supply_orders
            ],
            "capacity_reservations": [
                {
                    "source_id": r.source_id,
                    "year": r.year,
                    "reserved_capacity_t_per_year": r.reserved_capacity_t_per_year,
                    "start_month": r.start_month,
                }
                for r in d.capacity_reservations
            ],
            "investments": [
                {
                    "investment_id": i.investment_id,
                    "action": i.action,
                    "payment_date": i.payment_date,
                }
                for i in d.investments
            ],
            "inventory_policy": policy,
        },
        "assumptions": [
            {
                "id": a.id,
                "value": a.value,
                "unit": a.unit,
                "rationale_ru": a.rationale_ru,
                "scope": a.scope,
            }
            for a in plan.assumptions
        ],
    }
    if plan.version:
        out["version"] = plan.version
    if d.emergency_contract is not None:
        out["decisions"]["emergency_contract"] = {
            "reserved_capacity_t_per_year": d.emergency_contract.reserved_capacity_t_per_year,
            "activation_lead_days": d.emergency_contract.activation_lead_days,
            "coverage_volume_t": d.emergency_contract.coverage_volume_t,
            "notes_ru": d.emergency_contract.notes_ru,
        }
    return out


def save_plan(plan: Plan, path: str) -> None:
    """Сохранение плана в JSON по схеме plan_format.json."""
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(plan_to_dict(plan), f, ensure_ascii=False, indent=2)
        f.write("\n")


def load_saved_plan(path: str) -> Plan:
    """Загрузка ранее сохранённого плана с валидацией структуры.

    Использует loader.load_plan (тот же разбор и те же русские сообщения
    об ошибках, что и для планов участника).
    """
    return load_plan(path)
