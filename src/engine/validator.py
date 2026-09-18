"""Статические проверки данных кейса и плана (БЕЗ расчёта баланса).

validate_case — целостность CASE_INPUT: вложенность critical ≤ total,
неотрицательность, enum-поля, годы горизонта.

validate_plan — статика плана: reserved ≤ capacity, источники C/D заказываются
только при наличии инвестиции, периоды в горизонте, investment_id существует
в каталоге. Каждое нарушение возвращается как Violation с сообщением на русском.
"""

from __future__ import annotations

import re

from .models import (
    CaseData,
    HORIZON_END_YEAR,
    HORIZON_START_YEAR,
    Plan,
    Violation,
)

# Допустимые значения enum-полей (plan_format.json, CASE_INPUT).
_VALID_SOURCE_IDS = {"A", "B", "C", "D", "E"}
_VALID_INVESTMENT_IDS = {"EARTH_NEW", "LUNAR_ISRU", "ZBO"}
_VALID_ACTIONS = {"buy_option", "exercise_option", "fund_capex", "none"}
_VALID_RESERVE_MODES = {"physical", "contractual_emergency"}

_PERIOD_YEAR_RE = re.compile(r"^(20(?:3[5-9]|4[0-9]))$")
_PERIOD_MONTH_RE = re.compile(r"^(20(?:3[5-9]|4[0-9]))-(0[1-9]|1[0-2])$")

# Инвестиции, без которых канал недоступен (units_and_conventions.md §8):
# C (Earth-New) — после exercise_option EARTH_NEW; D (Lunar-ISRU) — после
# fund_capex LUNAR_ISRU не позднее 2037-12.
_INVESTMENT_REQUIRED_FOR_SOURCE = {"C": "EARTH_NEW", "D": "LUNAR_ISRU"}


def validate_case(case: CaseData) -> list[Violation]:
    """Проверка целостности CASE_INPUT. Возвращает список Violation (пустой — ОК)."""
    v: list[Violation] = []

    def add(rule_id: str, period: str, actual: float, limit: float, message_ru: str) -> None:
        v.append(
            Violation(
                rule_id=rule_id,
                period=period,
                actual=actual,
                limit=limit,
                excess=round(actual - limit, 10),
                message_ru=message_ru,
            )
        )

    # --- demand.csv: неотрицательность и вложенность critical ≤ total ---
    years_seen: set[int] = set()
    for d in case.demand:
        period = str(d.year)
        if d.year in years_seen:
            add("DATA_DUPLICATE_YEAR", period, d.year, d.year,
                f"demand.csv: год {d.year} встречается более одного раза")
        years_seen.add(d.year)
        if d.year < HORIZON_START_YEAR or d.year > HORIZON_END_YEAR:
            add("DATA_YEAR_OUT_OF_HORIZON", period, d.year, HORIZON_END_YEAR,
                f"demand.csv: год {d.year} вне горизонта {HORIZON_START_YEAR}–{HORIZON_END_YEAR}")
        for fname, val in (
            ("base_total_t", d.base_total_t),
            ("base_critical_t", d.base_critical_t),
            ("low_total_t", d.low_total_t),
            ("high_total_t", d.high_total_t),
        ):
            if val < 0:
                add("DATA_NEGATIVE", period, val, 0.0,
                    f"demand.csv: параметр '{fname}' года {d.year} отрицателен ({val} т)")
        if d.base_critical_t > d.base_total_t:
            add("DATA_CRITICAL_GT_TOTAL", period, d.base_critical_t, d.base_total_t,
                f"demand.csv: критический спрос {d.base_critical_t} т года {d.year} "
                f"превышает общий спрос {d.base_total_t} т (critical ≤ total)")
        if d.base_total_t > 0 and not (d.low_total_t <= d.base_total_t <= d.high_total_t):
            add("DATA_RANGE_INCONSISTENT", period, d.base_total_t, d.high_total_t,
                f"demand.csv: для года {d.year} нарушено соотношение "
                f"low_total_t ≤ base_total_t ≤ high_total_t ({d.low_total_t}/{d.base_total_t}/{d.high_total_t})")
        if d.status != "CASE_INPUT":
            add("DATA_BAD_STATUS", period, 0.0, 0.0,
                f"demand.csv: строка года {d.year} имеет status '{d.status}' вместо 'CASE_INPUT'")

    expected_years = set(range(HORIZON_START_YEAR, HORIZON_END_YEAR + 1))
    missing_years = sorted(expected_years - years_seen)
    if missing_years:
        add("DATA_MISSING_YEARS", f"{missing_years[0]}", float(len(missing_years)), 0.0,
            f"demand.csv: отсутствуют годы горизонта: {missing_years}")

    # --- supply_sources.csv ---
    source_ids_seen: set[str] = set()
    for s in case.supply_sources:
        if s.source_id in source_ids_seen:
            add("DATA_DUPLICATE_SOURCE", s.source_id, 0.0, 0.0,
                f"supply_sources.csv: канал '{s.source_id}' описан более одного раза")
        source_ids_seen.add(s.source_id)
        if s.capacity_t_per_year < 0:
            add("DATA_NEGATIVE", s.source_id, s.capacity_t_per_year, 0.0,
                f"supply_sources.csv: мощность канала '{s.source_id}' отрицательна "
                f"({s.capacity_t_per_year} т/год)")
        if s.variable_cost_mln_per_t < 0:
            add("DATA_NEGATIVE", s.source_id, s.variable_cost_mln_per_t, 0.0,
                f"supply_sources.csv: цена канала '{s.source_id}' отрицательна "
                f"({s.variable_cost_mln_per_t} млн у.е./т)")
        if not (0.0 <= s.take_or_pay_share <= 1.0):
            add("DATA_ENUM_RANGE", s.source_id, s.take_or_pay_share, 1.0,
                f"supply_sources.csv: take_or_pay_share канала '{s.source_id}' = "
                f"{s.take_or_pay_share} вне диапазона 0..1")
        if s.lead_time_unit not in ("day", "week", "month", "year"):
            add("DATA_ENUM", s.source_id, 0.0, 0.0,
                f"supply_sources.csv: lead_time_unit канала '{s.source_id}' = "
                f"'{s.lead_time_unit}' — недопустимое значение")
        if s.lead_time_min_value < 0 or s.lead_time_max_value < s.lead_time_min_value:
            add("DATA_LEAD_TIME_RANGE", s.source_id, s.lead_time_max_value, s.lead_time_min_value,
                f"supply_sources.csv: lead time канала '{s.source_id}' задан некорректно "
                f"(min={s.lead_time_min_value}, max={s.lead_time_max_value})")
        if s.available_from_year is not None and not (
            HORIZON_START_YEAR <= s.available_from_year <= HORIZON_END_YEAR
        ):
            add("DATA_YEAR_OUT_OF_HORIZON", s.source_id, s.available_from_year, HORIZON_END_YEAR,
                f"supply_sources.csv: available_from_year канала '{s.source_id}' = "
                f"{s.available_from_year} вне горизонта")
        if s.status != "CASE_INPUT":
            add("DATA_BAD_STATUS", s.source_id, 0.0, 0.0,
                f"supply_sources.csv: канал '{s.source_id}' имеет status '{s.status}' вместо 'CASE_INPUT'")

    # --- storage_options.csv ---
    storage_ids_seen: set[str] = set()
    for st in case.storage_options:
        if st.storage_id in storage_ids_seen:
            add("DATA_DUPLICATE_STORAGE", st.storage_id, 0.0, 0.0,
                f"storage_options.csv: режим хранения '{st.storage_id}' описан более одного раза")
        storage_ids_seen.add(st.storage_id)
        if st.capacity_t < 0:
            add("DATA_NEGATIVE", st.storage_id, st.capacity_t, 0.0,
                f"storage_options.csv: ёмкость режима '{st.storage_id}' отрицательна ({st.capacity_t} т)")
        if not (0.0 <= st.loss_rate_on_throughput <= 1.0):
            add("DATA_ENUM_RANGE", st.storage_id, st.loss_rate_on_throughput, 1.0,
                f"storage_options.csv: loss_rate_on_throughput режима '{st.storage_id}' = "
                f"{st.loss_rate_on_throughput} вне диапазона 0..1")

    if "BASE" not in storage_ids_seen:
        add("DATA_MISSING_STORAGE", "BASE", 0.0, 0.0,
            "storage_options.csv: отсутствует обязательный базовый режим хранения 'BASE'")

    # --- investment_options.csv ---
    investment_ids_seen: set[str] = set()
    for inv in case.investment_options:
        if inv.investment_id in investment_ids_seen:
            add("DATA_DUPLICATE_INVESTMENT", inv.investment_id, 0.0, 0.0,
                f"investment_options.csv: опция '{inv.investment_id}' описана более одного раза")
        investment_ids_seen.add(inv.investment_id)
        if inv.total_capex_mln < 0 or inv.option_fee_mln < 0 or inv.exercise_cost_mln < 0:
            add("DATA_NEGATIVE", inv.investment_id, inv.total_capex_mln, 0.0,
                f"investment_options.csv: отрицательные платежи у опции '{inv.investment_id}'")

    # --- constraints.csv: enum-поля ---
    for c in case.constraints:
        if c.operator not in (">=", "<=", ">", "<", "=="):
            add("DATA_ENUM", c.constraint_id, 0.0, 0.0,
                f"constraints.csv: оператор '{c.operator}' ограничения '{c.constraint_id}' недопустим")
        if c.severity not in ("hard", "soft"):
            add("DATA_ENUM", c.constraint_id, 0.0, 0.0,
                f"constraints.csv: severity '{c.severity}' ограничения '{c.constraint_id}' недопустимо")

    return v


def _period_in_horizon(period: str) -> bool:
    """Период 'YYYY' или 'YYYY-MM' в горизонте 2035–2040.

    Формат схемы plan_format.json допускает 2035–2049, поэтому диапазон
    лет проверяется явно по горизонту планирования.
    """
    m = _PERIOD_MONTH_RE.match(period) or _PERIOD_YEAR_RE.match(period)
    if m is None:
        return False
    year = int(m.group(1))
    return HORIZON_START_YEAR <= year <= HORIZON_END_YEAR


def validate_plan(plan: Plan, case: CaseData) -> list[Violation]:
    """Статические проверки плана БЕЗ расчёта баланса.

    Проверяет: reserved ≤ capacity; заказы C/D только при инвестиции в плане;
    периоды в горизонте; investment_id существует в каталоге; неотрицательность;
    корректность enum-полей плана.
    """
    v: list[Violation] = []

    def add(rule_id: str, period: str, actual: float, limit: float, message_ru: str) -> None:
        v.append(
            Violation(
                rule_id=rule_id,
                period=period,
                actual=actual,
                limit=limit,
                excess=round(actual - limit, 10),
                message_ru=message_ru,
            )
        )

    catalog_source_ids = {s.source_id for s in case.supply_sources}
    catalog_investment_ids = {i.investment_id for i in case.investment_options}
    reserved_capacity = {
        (r.source_id, r.year): r.reserved_capacity_t_per_year
        for r in plan.decisions.capacity_reservations
    }

    # --- capacity_reservations ---
    for r in plan.decisions.capacity_reservations:
        period = str(r.year)
        if r.source_id not in catalog_source_ids:
            add("UNKNOWN_SOURCE", period, 0.0, 0.0,
                f"План '{plan.plan_id}': канал '{r.source_id}' (год {r.year}) "
                f"не найден в каталоге supply_sources")
            continue
        if r.year < HORIZON_START_YEAR or r.year > HORIZON_END_YEAR:
            add("PERIOD_OUT_OF_HORIZON", period, r.year, HORIZON_END_YEAR,
                f"План '{plan.plan_id}': год резервирования {r.year} канала '{r.source_id}' "
                f"вне горизонта {HORIZON_START_YEAR}–{HORIZON_END_YEAR}")
        if r.reserved_capacity_t_per_year < 0:
            add("NEGATIVE_RESERVATION", period, r.reserved_capacity_t_per_year, 0.0,
                f"План '{plan.plan_id}': резерв мощности канала '{r.source_id}' "
                f"на {r.year} год отрицателен ({r.reserved_capacity_t_per_year} т/год)")
        if not (1 <= r.start_month <= 12):
            add("BAD_START_MONTH", period, r.start_month, 12,
                f"План '{plan.plan_id}': start_month = {r.start_month} канала '{r.source_id}' "
                f"на {r.year} год вне диапазона 1..12")
        capacity = case.source(r.source_id).capacity_t_per_year
        if r.reserved_capacity_t_per_year > capacity:
            # rule_id CAPACITY_EXCEEDED — по expected_checks.json (V08): reserved 12
            # при capacity 10 т/год → excess 2 т/год.
            add("CAPACITY_EXCEEDED", period, r.reserved_capacity_t_per_year, capacity,
                f"План '{plan.plan_id}': резерв мощности канала '{r.source_id}' "
                f"на {r.year} год ({r.reserved_capacity_t_per_year} т/год) "
                f"превышает доступную мощность ({capacity} т/год)")

    # --- investments ---
    funded: dict[str, str] = {}  # investment_id -> earliest payment_date действия
    for inv in plan.decisions.investments:
        if inv.investment_id not in catalog_investment_ids:
            add("UNKNOWN_INVESTMENT", inv.payment_date, 0.0, 0.0,
                f"План '{plan.plan_id}': investment_id '{inv.investment_id}' "
                f"не найден в каталоге investment_options")
            continue
        if inv.action not in _VALID_ACTIONS:
            add("BAD_INVESTMENT_ACTION", inv.payment_date, 0.0, 0.0,
                f"План '{plan.plan_id}': действие '{inv.action}' опции '{inv.investment_id}' "
                f"недопустимо (допустимы: {sorted(_VALID_ACTIONS)})")
            continue
        if not _PERIOD_MONTH_RE.match(inv.payment_date):
            add("PERIOD_OUT_OF_HORIZON", inv.payment_date, 0.0, 0.0,
                f"План '{plan.plan_id}': payment_date '{inv.payment_date}' опции "
                f"'{inv.investment_id}' не является периодом формата YYYY-MM")
            continue
        # payment_date может относиться к подготовительному периоду (до 2035) —
        # это допустимо (units_and_conventions.md §3), но за горизонт — нет.
        year = int(inv.payment_date[:4])
        if year > HORIZON_END_YEAR:
            add("PERIOD_OUT_OF_HORIZON", inv.payment_date, year, HORIZON_END_YEAR,
                f"План '{plan.plan_id}': платёж '{inv.payment_date}' опции "
                f"'{inv.investment_id}' за пределами горизонта {HORIZON_END_YEAR}")
        if inv.action != "none":
            prev = funded.get(inv.investment_id)
            if prev is None or inv.payment_date < prev:
                funded[inv.investment_id] = inv.payment_date

    # --- supply_orders ---
    for o in plan.decisions.supply_orders:
        period = o.period
        if not _period_in_horizon(period):
            add("PERIOD_OUT_OF_HORIZON", period, 0.0, 0.0,
                f"План '{plan.plan_id}': период заказа '{period}' канала '{o.source_id}' "
                f"вне горизонта {HORIZON_START_YEAR}–{HORIZON_END_YEAR} или неверного формата")
            continue
        if o.source_id not in catalog_source_ids:
            add("UNKNOWN_SOURCE", period, 0.0, 0.0,
                f"План '{plan.plan_id}': канал '{o.source_id}' (период {period}) "
                f"не найден в каталоге supply_sources")
            continue
        if o.ordered_volume_t < 0:
            add("NEGATIVE_ORDER", period, o.ordered_volume_t, 0.0,
                f"План '{plan.plan_id}': заказ канала '{o.source_id}' "
                f"на период {period} отрицателен ({o.ordered_volume_t} т)")
        # Источник C/D заказывается только при наличии инвестиции в плане.
        required_investment = _INVESTMENT_REQUIRED_FOR_SOURCE.get(o.source_id)
        if required_investment and required_investment not in funded:
            add("INVESTMENT_REQUIRED", period, o.ordered_volume_t, 0.0,
                f"План '{plan.plan_id}': заказ канала '{o.source_id}' на период {period} "
                f"без инвестиции '{required_investment}' — канал недоступен")
            continue
        # D: финансирование LUNAR_ISRU должно быть до 2038-01 (дедлайн 2037-12).
        if o.source_id == "D":
            pay = funded.get("LUNAR_ISRU", "")
            if pay and pay >= "2038-01":
                add("ISRU_DEADLINE", period, float(pay[:4]) + int(pay[5:7]) / 12.0, 2038.0,
                    f"План '{plan.plan_id}': финансирование LUNAR_ISRU от {pay} — "
                    f"позднее дедлайна 2037-12, канал D в периоде {period} недоступен")
                continue
        # Заказ в месяце не должен превышать годовую зарезервированную мощность / 12
        # (равномерно) — здесь проверяем только наличие резерва, превышение
        # считается помесячно в calculate_deliveries (CAPACITY_EXCEEDED).
        year = int(period[:4])
        if o.ordered_volume_t > 0 and reserved_capacity.get((o.source_id, year), 0.0) <= 0.0:
            add("NO_RESERVATION_FOR_ORDER", period, o.ordered_volume_t, 0.0,
                f"План '{plan.plan_id}': заказ канала '{o.source_id}' на период {period} "
                f"без резервирования мощности на {year} год")

    # --- inventory_policy ---
    policy = plan.decisions.inventory_policy
    if policy.initial_inventory_t < 0:
        add("NEGATIVE_INITIAL_INVENTORY", str(HORIZON_START_YEAR),
            policy.initial_inventory_t, 0.0,
            f"План '{plan.plan_id}': initial_inventory_t отрицателен "
            f"({policy.initial_inventory_t} т)")
    if policy.reserve_mode not in _VALID_RESERVE_MODES:
        add("BAD_RESERVE_MODE", str(HORIZON_START_YEAR), 0.0, 0.0,
            f"План '{plan.plan_id}': reserve_mode '{policy.reserve_mode}' недопустим "
            f"(допустимы: {sorted(_VALID_RESERVE_MODES)})")
    src = policy.initial_inventory_source
    if src is not None:
        if src.volume_t < 0:
            add("NEGATIVE_INITIAL_INVENTORY", src.delivery_period, src.volume_t, 0.0,
                f"План '{plan.plan_id}': volume_t начального запаса отрицателен "
                f"({src.volume_t} т)")
        if src.volume_t != policy.initial_inventory_t:
            add("INITIAL_INVENTORY_MISMATCH", src.delivery_period,
                src.volume_t, policy.initial_inventory_t,
                f"План '{plan.plan_id}': volume_t предстартового заказа ({src.volume_t} т) "
                f"не совпадает с initial_inventory_t ({policy.initial_inventory_t} т) — "
                f"объём не должен учитываться дважды")
        if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", src.order_period):
            add("PERIOD_OUT_OF_HORIZON", src.order_period, 0.0, 0.0,
                f"План '{plan.plan_id}': order_period '{src.order_period}' "
                f"начального запаса не является периодом формата YYYY-MM")
        if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", src.delivery_period):
            add("PERIOD_OUT_OF_HORIZON", src.delivery_period, 0.0, 0.0,
                f"План '{plan.plan_id}': delivery_period '{src.delivery_period}' "
                f"начального запаса не является периодом формата YYYY-MM")

    return v
