"""Модели данных расчётного ядра.

Датаклассы строго по контрактам:
- ai_workstreams/00_contracts/result_format.json (RunResult, monthly_balance, ...);
- ai_workstreams/00_contracts/plan_format.json (Plan, decisions);
- ai_workstreams/00_contracts/core_api.md (CaseData, Scenario, Violation).

Единицы (units_and_conventions.md §1):
- объёмы — тонны (*_t), мощности — т/год (*_t_per_year);
- деньги — млн у.е. в постоянных ценах 2035 г. (*_mln);
- цены — млн у.е./т (*_mln_per_t);
- доли — 0..1 (sl_*, *_share, loss_rate);
- периоды — строки 'YYYY' или 'YYYY-MM'.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# Версия ядра и версия контракта (фиксируются в meta результата).
ENGINE_VERSION = "0.1.0-wave1"
CONTRACT_VERSION = "1.0"

# Горизонт планирования: 72 месячных периода 2035-01 … 2040-12.
HORIZON_START_YEAR = 2035
HORIZON_END_YEAR = 2040

# Учебный год = 365 дней (CASE_INPUT); месяц = 365/12 дня (TA-01).
DAYS_PER_YEAR = 365.0
DAYS_PER_MONTH = DAYS_PER_YEAR / 12.0

# Ставка дисконтирования (TA-06) и момент приведения (t0).
DISCOUNT_RATE = 0.10
DISCOUNT_T0 = 2035


class CaseLoadError(Exception):
    """Ошибка загрузки/разбора входных данных.

    Сообщение всегда на русском и называет файл, строку (где применимо)
    и параметр/период, с которым возникла проблема.
    """


# ---------------------------------------------------------------------------
# CASE_INPUT (data/*.csv)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DemandRow:
    """Строка demand.csv: спрос по годам (тонны)."""

    year: int
    base_total_t: float
    base_critical_t: float
    low_total_t: float
    high_total_t: float
    status: str = "CASE_INPUT"


@dataclass(frozen=True)
class SupplySource:
    """Строка supply_sources.csv: канал снабжения.

    lead_time хранится в ИСХОДНЫХ единицах CASE_INPUT (month/week/...) —
    конвертация выполняется явно в deliveries.py (units_and_conventions.md §2).
    reliability_profile — только метаданные риск-блока (WP3); в расчёте
    BASE и MANDATORY_STRESS НЕ участвует (CALCULATION_RULES §11).
    """

    source_id: str
    name: str
    capacity_t_per_year: float
    variable_cost_mln_per_t: float
    reservation_rate_mln_per_t_year_capacity: float
    take_or_pay_share: float
    lead_time_min_value: float
    lead_time_max_value: float
    lead_time_unit: str
    reliability_profile: str
    available_from_year: Optional[int]
    status: str = "CASE_INPUT"
    notes: str = ""


@dataclass(frozen=True)
class StorageOption:
    """Строка storage_options.csv: режим хранения (BASE / ZBO)."""

    storage_id: str
    name: str
    capacity_t: float
    loss_rate_on_throughput: float
    holding_cost_mln_per_t_year: float
    capex_mln: float
    fixed_opex_mln_per_year: float
    available_from_year: int
    status: str = "CASE_INPUT"
    notes: str = ""


@dataclass(frozen=True)
class InvestmentOption:
    """Строка investment_options.csv: инвестиционная опция."""

    investment_id: str
    name: str
    option_fee_mln: float
    exercise_cost_mln: float
    total_capex_mln: float
    commissioning_rule: str
    fixed_opex_mln_per_year: float
    status: str = "CASE_INPUT"
    notes: str = ""


@dataclass(frozen=True)
class ConstraintRow:
    """Строка constraints.csv: обязательное ограничение кейса."""

    constraint_id: str
    metric: str
    operator: str
    value: float
    unit: str
    period: str
    scenario: str
    severity: str
    status: str = "CASE_INPUT"
    description: str = ""


@dataclass
class CaseData:
    """Полный набор входных данных кейса.

    Поля effective_* — действующие значения после apply_scenario
    (в BASE совпадают с исходными). Исходные base_* не мутируются.
    """

    demand: list[DemandRow]
    supply_sources: list[SupplySource]
    storage_options: list[StorageOption]
    investment_options: list[InvestmentOption]
    constraints: list[ConstraintRow]

    # Действующий (сценарный) спрос по годам: {год: тонны}.
    effective_demand_total_t: dict[int, float] = field(default_factory=dict)
    effective_demand_critical_t: dict[int, float] = field(default_factory=dict)
    # Действующие (сценарные) цены по каналам и годам: {(source_id, год): млн у.е./т}.
    effective_price_mln_per_t: dict[tuple[str, int], float] = field(default_factory=dict)
    # Фактические доли поставки из сценария: {(source_id, год): 0..1}.
    actual_delivery_share: dict[tuple[str, int], float] = field(default_factory=dict)
    # Потолок потерь (loss_ceiling) сценария.
    loss_ceiling: dict[str, Any] = field(default_factory=dict)
    # Идентификатор применённого сценария (BASE по умолчанию).
    scenario_id: str = "BASE"

    def source(self, source_id: str) -> SupplySource:
        """Канал по идентификатору; ошибка — на русском."""
        for s in self.supply_sources:
            if s.source_id == source_id:
                return s
        raise CaseLoadError(
            f"Канал снабжения '{source_id}' не найден в supply_sources.csv"
        )

    def storage(self, storage_id: str) -> StorageOption:
        """Режим хранения по идентификатору; ошибка — на русском."""
        for s in self.storage_options:
            if s.storage_id == storage_id:
                return s
        raise CaseLoadError(
            f"Режим хранения '{storage_id}' не найден в storage_options.csv"
        )


# ---------------------------------------------------------------------------
# Сценарий (configs/*.yaml, scenario.schema.json)
# ---------------------------------------------------------------------------

@dataclass
class Scenario:
    """Сценарий: множители спроса/цен, фактические доли поставки, loss ceiling.

    Структура множителей допускает ключ 'default' и/или ключи-годы ('2038')
    и вложенность по каналам (variable_price_multiplier: {Earth-Core: {2038: 1.25}}).
    """

    scenario_id: str
    status: str = "CASE_INPUT"
    label_ru: str = ""
    demand_multiplier: dict[str, float] = field(default_factory=lambda: {"default": 1.0})
    critical_demand_multiplier: dict[str, float] = field(default_factory=lambda: {"default": 1.0})
    variable_price_multiplier: dict[str, Any] = field(default_factory=lambda: {"default": 1.0})
    actual_delivery_share: dict[str, Any] = field(default_factory=lambda: {"default": 1.0})
    loss_ceiling: dict[str, Any] = field(default_factory=lambda: {"enabled": False})
    notes: list[str] = field(default_factory=list)

    @staticmethod
    def base() -> "Scenario":
        """BASE-сценарий: все множители 1.0, потолок потерь выключен."""
        return Scenario(scenario_id="BASE")


# ---------------------------------------------------------------------------
# План участника (plan_format.json)
# ---------------------------------------------------------------------------

@dataclass
class SupplyOrder:
    """Заказ на отбор: source_id, период ('YYYY' или 'YYYY-MM'), объём (т)."""

    source_id: str
    period: str
    ordered_volume_t: float


@dataclass
class CapacityReservation:
    """Резервирование мощности канала на год (т/год), start_month — 1..12."""

    source_id: str
    year: int
    reserved_capacity_t_per_year: float
    start_month: int = 1


@dataclass
class Investment:
    """Инвестиционное действие: investment_id, action, payment_date ('YYYY-MM')."""

    investment_id: str
    action: str
    payment_date: str


@dataclass
class InitialInventorySource:
    """Источник формирования начального запаса (предстартовый заказ).

    По units_and_conventions.md §3 объём учитывается ОДИН раз: либо как
    initial_inventory_t (I_start 2035-01), либо как поставка месяца — не оба.
    """

    source_id: str
    order_period: str
    delivery_period: str
    volume_t: float
    paid_in: str


@dataclass
class InventoryPolicy:
    """Политика запаса плана."""

    initial_inventory_t: float = 0.0
    initial_inventory_source: Optional[InitialInventorySource] = None
    reserve_mode: str = "physical"
    target_month_end_inventory_t: float = 0.0


@dataclass
class EmergencyContract:
    """Параметры договорного Emergency-резерва (reserve_mode=contractual_emergency)."""

    reserved_capacity_t_per_year: float = 0.0
    activation_lead_days: float = 42.0
    coverage_volume_t: float = 0.0
    notes_ru: str = ""


@dataclass
class PlanDecisions:
    """Раздел decisions плана."""

    supply_orders: list[SupplyOrder] = field(default_factory=list)
    capacity_reservations: list[CapacityReservation] = field(default_factory=list)
    investments: list[Investment] = field(default_factory=list)
    inventory_policy: InventoryPolicy = field(default_factory=InventoryPolicy)
    emergency_contract: Optional[EmergencyContract] = None


@dataclass
class Assumption:
    """Запись реестра TEAM_ASSUMPTION плана."""

    id: str
    value: Any
    unit: str
    rationale_ru: str
    scope: str = ""


@dataclass
class Plan:
    """План участника по схеме plan_format.json."""

    plan_id: str
    scenario_id: str
    decisions: PlanDecisions
    assumptions: list[Assumption] = field(default_factory=list)
    version: str = ""


# ---------------------------------------------------------------------------
# Результаты расчёта (result_format.json)
# ---------------------------------------------------------------------------

@dataclass
class Violation:
    """Нарушение ограничения: rule_id, период, факт, лимит, excess, сообщение (рус.)."""

    rule_id: str
    period: str
    actual: float
    limit: float
    excess: float
    message_ru: str


@dataclass
class MonthBalance:
    """Помесячный материальный баланс (элемент monthly_balance)."""

    period: str
    i_start_t: float
    delivered_t: float
    throughput_t: float
    losses_t: float
    served_total_t: float
    served_critical_t: float
    demand_total_t: float
    demand_critical_t: float
    shortage_t: float
    i_end_t: float
    storage_mode: str
    storage_capacity_t: float


@dataclass
class YearBalance:
    """Годовая агрегация (элемент yearly_balance) с показателями сервиса."""

    year: int
    demand_total_t: float
    demand_critical_t: float
    delivered_t: float
    losses_t: float
    served_total_t: float
    served_critical_t: float
    shortage_t: float
    sl_total: float
    sl_critical: float
    i_start_t: float
    i_end_t: float
    reserve_required_t: float
    reserve_actual_start_t: float
    reserve_ok: bool


@dataclass
class SourceScheduleRow:
    """Помесячно по каналу: reserved / ordered / planned / actual (элемент source_schedule)."""

    source_id: str
    period: str
    reserved_capacity_t_per_year: float
    ordered_volume_t: float
    planned_delivery_t: float
    actual_delivery_t: float
    lead_time_applied: str


@dataclass
class InventoryTracePoint:
    """Точка inventory_trace для графиков."""

    period: str
    inventory_t: float
    reserve_threshold_t: float
    capacity_t: float


@dataclass
class DeliveriesResult:
    """Результат calculate_deliveries: факт поставок по месяцам + schedule.

    delivered_by_period — фактическое поступление (actual_delivery_t)
    по месяцам 'YYYY-MM' (в BASE = planned; в стрессе — с учётом
    actual_delivery_share сценария; reliability НЕ умножается).
    """

    delivered_by_period: dict[str, float] = field(default_factory=dict)
    planned_by_period: dict[str, float] = field(default_factory=dict)
    # Детализация по каналам: {(source_id, 'YYYY-MM'): planned/actual}.
    planned_by_source_period: dict[tuple[str, str], float] = field(default_factory=dict)
    actual_by_source_period: dict[tuple[str, str], float] = field(default_factory=dict)
    # Заказы, распределённые по месяцам: {(source_id, 'YYYY-MM'): т}.
    ordered_by_source_period: dict[tuple[str, str], float] = field(default_factory=dict)
    # Резервы по каналам и годам: {(source_id, год): т/год}.
    reserved_by_source_year: dict[tuple[str, int], float] = field(default_factory=dict)
    # Раскрытые конвенции lead time по каналам: {source_id: строка}.
    lead_time_applied: dict[str, str] = field(default_factory=dict)
    source_schedule: list[SourceScheduleRow] = field(default_factory=list)
    violations: list[Violation] = field(default_factory=list)


@dataclass
class InventoryResult:
    """Результат calculate_inventory: помесячный баланс + нарушения."""

    monthly_balance: list[MonthBalance] = field(default_factory=list)
    inventory_trace: list[InventoryTracePoint] = field(default_factory=list)
    violations: list[Violation] = field(default_factory=list)


@dataclass
class ServiceResult:
    """Результат calculate_service: годовые агрегаты и уровни сервиса."""

    yearly_balance: list[YearBalance] = field(default_factory=list)


@dataclass
class FinancialRow:
    """Годовая строка financial_breakdown (заполняется в волне 2)."""

    year: int
    capex_mln: float = 0.0
    capex_cumulative_mln: float = 0.0
    procurement_mln: float = 0.0
    reservation_mln: float = 0.0
    take_or_pay_extra_mln: float = 0.0
    holding_mln: float = 0.0
    fixed_opex_mln: float = 0.0
    total_mln: float = 0.0
    discounted_mln: float = 0.0
    cost_per_served_t_mln: float = 0.0


@dataclass
class CostResult:
    """Результат calculate_costs (волна 2)."""

    financial_breakdown: list[FinancialRow] = field(default_factory=list)


@dataclass
class RiskEntry:
    """Запись risk_register (заполняется WP3, волна 3)."""

    risk_id: str
    scenario_id: str
    consequence_t: float = 0.0
    consequence_mln: float = 0.0
    consequence_sl: float = 0.0
    probability_basis_ru: str = ""


@dataclass
class RiskReport:
    """Результат evaluate_risks (волна 3)."""

    risk_register: list[RiskEntry] = field(default_factory=list)


@dataclass
class ComparisonResult:
    """Результат compare_scenarios (волна 3)."""

    rows: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class RunMeta:
    """Служебная информация результата (result_format.json: meta)."""

    engine_version: str = ENGINE_VERSION
    contract_version: str = CONTRACT_VERSION
    timestep: str = "monthly"
    discount_rate: float = DISCOUNT_RATE
    discount_t0: int = DISCOUNT_T0
    assumptions_reference: str = "ai_workstreams/00_contracts/units_and_conventions.md"
    generated_at: str = ""
    random_seed: Optional[int] = None


@dataclass
class RunResult:
    """Единый конверт результата run_plan (result_format.json)."""

    scenario_id: str
    plan_id: str
    deliveries: DeliveriesResult
    inventory: InventoryResult
    service: ServiceResult
    costs: CostResult = field(default_factory=CostResult)
    violations: list[Violation] = field(default_factory=list)
    risks: RiskReport = field(default_factory=RiskReport)
    comparison: Optional[ComparisonResult] = None
    meta: RunMeta = field(default_factory=RunMeta)
