# -*- coding: utf-8 -*-
"""
WP2 manual_calc — загрузка CASE_INPUT и базовые структуры.

НЕЗАВИСИМАЯ реализация команды WP2 (волна 1). Код src/engine НЕ используется.
Формулы: docs/CALCULATION_RULES.md, ai_workstreams/00_contracts/units_and_conventions.md.

Единицы: тонны (т), млн у.е. (постоянные цены 2035 г.), доли 0..1, периоды YYYY / YYYY-MM.
"""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field

# Корень репозитория (…/sad9ugn). Данные читаем ТОЛЬКО из data/ (CASE_INPUT, неизменяемо).
_HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
DATA_DIR = os.path.join(REPO_ROOT, "data")

YEARS = [2035, 2036, 2037, 2038, 2039, 2040]
N_MONTHS = 72  # 2035-01 … 2040-12

# Конвенции TEAM_ASSUMPTION (реестр units_and_conventions.md §12)
MONTH_DAYS = 365.0 / 12.0          # TA-01
LEAD_C_MONTHS = 24                  # TA-02: Earth-New консервативно 24 мес
LEAD_D_MONTHS = 2                   # политика: Lunar-ISRU 2 мес после ввода
LEAD_E_MONTHS = 1                   # TA-03: Emergency 42 дня → следующий месяц
DISCOUNT_RATE = 0.10                # TA-06
DISCOUNT_T0 = 2035                  # TA-06
HOLDING_COST = 0.72                 # млн у.е./(т·год), CASE_INPUT

# Lead time по каналам, месяцев (TA-04: заказ в M → поставка в M+L)
LEAD_MONTHS = {"A": 12, "B": 4, "C": LEAD_C_MONTHS, "D": LEAD_D_MONTHS, "E": LEAD_E_MONTHS}


def m_idx(year: int, month: int) -> int:
    """Индекс месяца 0..71 (0 = 2035-01)."""
    return (year - 2035) * 12 + (month - 1)


def m_period(idx: int) -> str:
    """Период YYYY-MM по индексу."""
    return f"{2035 + idx // 12:04d}-{idx % 12 + 1:02d}"


def m_year(idx: int) -> int:
    return 2035 + idx // 12


def m_month(idx: int) -> int:
    return idx % 12 + 1


@dataclass
class Source:
    source_id: str
    name: str
    capacity: float            # т/год
    var_cost: float            # млн у.е./т
    res_rate: float            # млн у.е. за (т/год)
    top_share: float           # доля take-or-pay (A=0.70, C=0.50)
    lead_months: int
    available_from: int | None  # None = зависит от инвестиций (C)


@dataclass
class Storage:
    storage_id: str
    capacity: float
    loss_rate: float
    holding_cost: float
    capex: float
    fixed_opex: float
    available_from: int


@dataclass
class CaseData:
    demand_total: dict[int, float]      # т/год
    demand_critical: dict[int, float]   # т/год (входит в общий!)
    sources: dict[str, Source]
    storages: dict[str, Storage]
    reserve_days: float = 45.0
    year_days: float = 365.0


def load_case(data_dir: str = DATA_DIR) -> CaseData:
    """Загрузка CASE_INPUT из data/*.csv (только чтение)."""
    demand_total: dict[int, float] = {}
    demand_critical: dict[int, float] = {}
    with open(os.path.join(data_dir, "demand.csv"), newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            y = int(row["year"])
            demand_total[y] = float(row["base_total_t"])
            demand_critical[y] = float(row["base_critical_t"])

    sources: dict[str, Source] = {}
    with open(os.path.join(data_dir, "supply_sources.csv"), newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            sid = row["source_id"]
            avail = row["available_from_year"].strip()
            lead = LEAD_MONTHS[sid]  # конвенции TA-02/03/04
            sources[sid] = Source(
                source_id=sid,
                name=row["name"],
                capacity=float(row["capacity_t_per_year"]),
                var_cost=float(row["variable_cost_mln_per_t"]),
                res_rate=float(row["reservation_rate_mln_per_t_year_capacity"]),
                top_share=float(row["take_or_pay_share"]),
                lead_months=lead,
                available_from=int(avail) if avail else None,
            )

    storages: dict[str, Storage] = {}
    with open(os.path.join(data_dir, "storage_options.csv"), newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            storages[row["storage_id"]] = Storage(
                storage_id=row["storage_id"],
                capacity=float(row["capacity_t"]),
                loss_rate=float(row["loss_rate_on_throughput"]),
                holding_cost=float(row["holding_cost_mln_per_t_year"]),
                capex=float(row["capex_mln"]),
                fixed_opex=float(row["fixed_opex_mln_per_year"]),
                available_from=int(row["available_from_year"]),
            )

    return CaseData(demand_total, demand_critical, sources, storages)


# ---------------------------------------------------------------------------
# Сценарии (CASE_INPUT: configs/base.yaml, configs/mandatory_stress.yaml)
# ---------------------------------------------------------------------------

@dataclass
class Scenario:
    scenario_id: str
    demand_mult: dict[int, float] = field(default_factory=dict)          # год → множитель
    price_mult: dict[str, dict[int, float]] = field(default_factory=dict)  # name канала → год → множитель
    isru_actual_share: dict[int, float] = field(default_factory=dict)     # год → фактическая доля D
    loss_ceiling_from: int | None = None                                  # год, с которого потолок потерь
    loss_ceiling: float | None = None


def make_base() -> Scenario:
    return Scenario(scenario_id="BASE")


def make_stress() -> Scenario:
    return Scenario(
        scenario_id="MANDATORY_STRESS",
        demand_mult={2035: 1.0, 2036: 1.0, 2037: 1.0, 2038: 1.15, 2039: 1.15, 2040: 1.15},
        price_mult={
            "A": {2035: 1.0, 2036: 1.0, 2037: 1.0, 2038: 1.25, 2039: 1.25, 2040: 1.0},
            "B": {2035: 1.0, 2036: 1.0, 2037: 1.0, 2038: 1.25, 2039: 1.25, 2040: 1.0},
        },
        isru_actual_share={2038: 0.55, 2039: 0.75, 2040: 1.0},
        loss_ceiling_from=2038,
        loss_ceiling=0.02,
    )
