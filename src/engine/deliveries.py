"""Помесячный расчёт поставок: заказ → lead time → доставка.

Конвенции (units_and_conventions.md §2, TEAM_ASSUMPTION TA-01…TA-04):
- заказ в месяце M с lead time L месяцев → плановая поставка в M+L (TA-04);
- lead times хранятся в ИСХОДНЫХ единицах CASE_INPUT и конвертируются явно:
  * A Earth-Core: 12 month → +12 месяцев;
  * B Earth-Flex: 4 month → +4 месяца;
  * C Earth-New: диапазон 18–24 month, политика контрольных расчётов —
    24 месяца (консервативно, TA-02);
  * D Lunar-ISRU: 1–2 month, политика — 2 месяца (TA-02);
  * E Emergency: 6 week = 42 дня → поставка в следующем месяце (TA-03).
- ограничение отбора: заказ в месяце ≤ зарезервированная мощность года / 12
  (равномерно); превышение → Violation CAPACITY_EXCEEDED, поставка
  ограничивается резервом (физический объём сверх контракта недоступен);
- доступность каналов: A/B/E — с 2035-01; C — через 24 месяца после
  exercise_option; D — с 2038-01 и только если LUNAR_ISRU профинансирован
  до 2038-01 (дедлайн 2037-12).

ВАЖНО (CALCULATION_RULES §11): в BASE delivered = planned; умножение на
reliability ЗАПРЕЩЕНО. В сценарии с actual_delivery_share фактический
объём = planned × доля сценария (один раз, без reliability).
"""

from __future__ import annotations

import re

from .models import (
    CaseData,
    DeliveriesResult,
    HORIZON_END_YEAR,
    HORIZON_START_YEAR,
    Plan,
    SourceScheduleRow,
    Violation,
)

_PERIOD_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


def month_index(year: int, month: int) -> int:
    """Сквозной номер месяца (2035-01 → 0)."""
    return (year - HORIZON_START_YEAR) * 12 + (month - 1)


def month_period(idx: int) -> str:
    """Период 'YYYY-MM' по сквозному номеру месяца."""
    y = HORIZON_START_YEAR + idx // 12
    m = idx % 12 + 1
    return f"{y:04d}-{m:02d}"


def all_periods() -> list[str]:
    """Все 72 периода горизонта 2035-01 … 2040-12."""
    return [month_period(i) for i in range(12 * (HORIZON_END_YEAR - HORIZON_START_YEAR + 1))]


def lead_time_months(case: CaseData, source_id: str) -> tuple[int, str]:
    """Lead time канала в месяцах месячной сетки + раскрытая конвенция.

    Политика для диапазонов — консервативная граница max (TA-02);
    для Emergency 6 week — поставка в следующем месяце (TA-03).
    """
    s = case.source(source_id)
    unit = s.lead_time_unit
    if unit == "month":
        months = int(round(s.lead_time_max_value))
        if s.lead_time_min_value != s.lead_time_max_value:
            desc = (
                f"{s.lead_time_min_value:g}-{s.lead_time_max_value:g} month "
                f"(policy: {months})"
            )
        else:
            desc = f"{months} month"
        return months, desc
    if unit == "week":
        # 6 недель = 42 дня; в месячной дискретизации (TA-03) заказ 1-го числа
        # месяца → поставка не ранее 12-го числа следующего месяца → следующий месяц.
        return 1, f"{s.lead_time_max_value:g} week (42 days → next month, TA-03)"
    if unit == "day":
        days = float(s.lead_time_max_value)
        months = max(1, int(-(-days // (365.0 / 12.0))))  # округление вверх
        return months, f"{days:g} day (→ {months} month)"
    if unit == "year":
        months = int(round(s.lead_time_max_value * 12))
        return months, f"{s.lead_time_max_value:g} year (→ {months} month)"
    raise ValueError(
        f"Недопустимая единица lead time '{unit}' канала '{source_id}' в supply_sources.csv"
    )


def channel_available_from(plan: Plan, case: CaseData, source_id: str) -> int | None:
    """Сквозной номер первого месяца доступности канала; None — недоступен никогда.

    A/B/E: available_from_year из данных (2035-01).
    C (Earth-New): через 24 месяца после exercise_option (TA-02, TA-04).
    D (Lunar-ISRU): с 2038-01, только если fund_capex LUNAR_ISRU ≤ 2037-12.
    """
    s = case.source(source_id)

    def _payments(investment_id: str, action: str | None = None) -> list[str]:
        return [
            inv.payment_date
            for inv in plan.decisions.investments
            if inv.investment_id == investment_id
            and inv.action != "none"
            and (action is None or inv.action == action)
            and _PERIOD_RE.match(inv.payment_date or "")
        ]

    if source_id == "C":
        dates = _payments("EARTH_NEW", "exercise_option")
        if not dates:
            return None
        pay = min(dates)
        py, pm = int(pay[:4]), int(pay[5:7])
        # Мощность доступна через 24 месяца после exercise (политика TA-02).
        return month_index(py, pm) + 24

    if source_id == "D":
        dates = _payments("LUNAR_ISRU", "fund_capex")
        if not dates:
            return None
        pay = min(dates)
        if pay > "2037-12":
            # Финансирование позднее дедлайна 2037-12 — канал не вводится.
            return None
        start_year = s.available_from_year or HORIZON_START_YEAR
        return month_index(max(start_year, HORIZON_START_YEAR), 1)

    start_year = s.available_from_year or HORIZON_START_YEAR
    return month_index(max(start_year, HORIZON_START_YEAR), 1)


def calculate_deliveries(case: CaseData, plan: Plan) -> DeliveriesResult:
    """Помесячные поставки по всем заказам плана.

    Возвращает DeliveriesResult с planned/actual по месяцам и каналам,
    source_schedule (раскрытие lead time) и нарушениями (CAPACITY_EXCEEDED,
    LEAD_TIME_VIOLATION).
    """
    periods = all_periods()
    n_months = len(periods)
    result = DeliveriesResult()
    result.lead_time_applied = {
        s.source_id: lead_time_months(case, s.source_id)[1] for s in case.supply_sources
    }

    # --- Резервы: {(source_id, год): т/год} и месяц начала (start_month) ---
    reserved: dict[tuple[str, int], float] = {}
    reserve_start_month: dict[tuple[str, int], int] = {}
    for r in plan.decisions.capacity_reservations:
        key = (r.source_id, r.year)
        reserved[key] = max(reserved.get(key, 0.0), r.reserved_capacity_t_per_year)
        reserve_start_month[key] = min(reserve_start_month.get(key, 12), r.start_month)
    result.reserved_by_source_year = dict(reserved)

    # --- Заказы: распределение по месяцам (годовой заказ — равномерно) ---
    ordered: dict[tuple[str, int], float] = {}  # (source_id, month_idx) → т
    for o in plan.decisions.supply_orders:
        if o.ordered_volume_t <= 0:
            continue
        m = _PERIOD_RE.match(o.period)
        if m:
            idx = month_index(int(m.group(1)), int(m.group(2)))
            if 0 <= idx < n_months:
                ordered[(o.source_id, idx)] = ordered.get((o.source_id, idx), 0.0) + o.ordered_volume_t
            continue
        ym = re.match(r"^(\d{4})$", o.period)
        if ym:
            year = int(ym.group(1))
            if HORIZON_START_YEAR <= year <= HORIZON_END_YEAR:
                share = o.ordered_volume_t / 12.0
                for mm in range(12):
                    idx = month_index(year, mm + 1)
                    ordered[(o.source_id, idx)] = ordered.get((o.source_id, idx), 0.0) + share

    # --- Доступность каналов по плану ---
    available_from = {
        s.source_id: channel_available_from(plan, case, s.source_id)
        for s in case.supply_sources
    }

    planned_by_src: dict[tuple[str, int], float] = {}
    actual_by_src: dict[tuple[str, int], float] = {}

    # --- Помесячный проход по заказам ---
    for (source_id, idx), volume in sorted(ordered.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        period = month_period(idx)
        year = HORIZON_START_YEAR + idx // 12
        month_no = idx % 12 + 1

        avail = available_from.get(source_id)
        if avail is None or idx < avail:
            # Канал недоступен в месяце заказа — заказ не исполняется.
            result.violations.append(
                Violation(
                    rule_id="LEAD_TIME_VIOLATION",
                    period=period,
                    actual=volume,
                    limit=0.0,
                    excess=volume,
                    message_ru=(
                        f"Заказ канала '{source_id}' на период {period} ({volume} т) не может "
                        f"быть исполнен: канал недоступен в этом периоде "
                        f"(требуется инвестиция/ввод согласно условиям кейса)"
                    ),
                )
            )
            continue

        # Ограничение отбора: заказ в месяце ≤ зарезервированная мощность года / 12.
        rsv_year = reserved.get((source_id, year), 0.0)
        # Сценарное снижение мощности канала (адаптер D3.4, capacity_override):
        # физический отбор не может превышать действующую мощность года.
        cap_override = case.capacity_override.get((source_id, year))
        if cap_override is not None:
            rsv_year = min(rsv_year, cap_override)
        start_month = reserve_start_month.get((source_id, year), 1)
        monthly_limit = (rsv_year / 12.0) if month_no >= start_month else 0.0
        effective_volume = volume
        if volume > monthly_limit + 1e-9:
            excess = volume - monthly_limit
            result.violations.append(
                Violation(
                    rule_id="CAPACITY_EXCEEDED",
                    period=period,
                    actual=volume,
                    limit=monthly_limit,
                    excess=excess,
                    message_ru=(
                        f"Заказ канала '{source_id}' в период {period} ({volume:.4f} т) превышает "
                        f"месячную долю зарезервированной мощности {year} года "
                        f"({monthly_limit:.4f} т = {rsv_year:g} т/год ÷ 12); "
                        f"излишек {excess:.4f} т"
                    ),
                )
            )
            # Физический отбор сверх зарезервированной мощности невозможен —
            # поставка ограничивается лимитом (нарушение зафиксировано выше).
            effective_volume = monthly_limit

        # Поставка: заказ в M → доставка в M+L (TA-04).
        lag, _ = lead_time_months(case, source_id)
        delivery_idx = idx + lag
        if delivery_idx < n_months:
            planned_by_src[(source_id, delivery_idx)] = (
                planned_by_src.get((source_id, delivery_idx), 0.0) + effective_volume
            )
        # Заказы, поставка которых выходит за горизонт, просто не поступают
        # (финансовые последствия — в волне 2).

    # --- Фактические доли сценария (БЕЗ умножения на reliability) ---
    for (source_id, idx), planned in sorted(planned_by_src.items()):
        period = month_period(idx)
        year = HORIZON_START_YEAR + idx // 12
        share = case.actual_delivery_share.get((source_id, year), 1.0)
        actual = planned * share
        result.planned_by_source_period[(source_id, period)] = planned
        result.actual_by_source_period[(source_id, period)] = actual
        result.planned_by_period[period] = result.planned_by_period.get(period, 0.0) + planned
        result.delivered_by_period[period] = result.delivered_by_period.get(period, 0.0) + actual

    # --- Заказы по месяцам (для source_schedule) ---
    for (source_id, idx), volume in ordered.items():
        if 0 <= idx < n_months:
            result.ordered_by_source_period[(source_id, month_period(idx))] = volume

    # --- source_schedule: помесячно по каждому каналу ---
    for s in case.supply_sources:
        for idx in range(n_months):
            period = month_period(idx)
            year = HORIZON_START_YEAR + idx // 12
            rsv_year = reserved.get((s.source_id, year), 0.0)
            start_month = reserve_start_month.get((s.source_id, year), 1)
            month_no = idx % 12 + 1
            rsv_month = rsv_year if month_no >= start_month else 0.0
            ordered_v = result.ordered_by_source_period.get((s.source_id, period), 0.0)
            planned_v = result.planned_by_source_period.get((s.source_id, period), 0.0)
            actual_v = result.actual_by_source_period.get((s.source_id, period), 0.0)
            if rsv_month == 0.0 and ordered_v == 0.0 and planned_v == 0.0:
                continue  # не плодим пустые строки
            result.source_schedule.append(
                SourceScheduleRow(
                    source_id=s.source_id,
                    period=period,
                    reserved_capacity_t_per_year=rsv_month,
                    ordered_volume_t=ordered_v,
                    planned_delivery_t=planned_v,
                    actual_delivery_t=actual_v,
                    lead_time_applied=result.lead_time_applied[s.source_id],
                )
            )

    return result
