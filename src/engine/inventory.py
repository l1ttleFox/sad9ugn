"""Помесячный материальный баланс, потери хранения и уровни сервиса.

Формулы (CALCULATION_RULES §1–§4, §7; units_and_conventions.md §4–§6):
- I_end = I_start + Q_delivered − Losses − Q_served;
- Losses = Throughput × loss_rate действующего режима (один раз;
  throughput = валовое поступление периода, повторный начёт на остаток запрещён);
- Shortage = max(0, Demand − Q_served); I_end ≥ 0 всегда (дефицит — отдельно);
- аллокация при дефиците: сначала критический спрос, затем прочий (§5);
- резерв 45 дней: R_y = D_y × 45 / 365, проверяется на начало каждого года;
- ёмкость хранилища проверяется каждый месяц (переполнение → STORAGE_OVERFLOW).

Смена режима хранения (TA-05): ZBO вводится в месяце, следующем за месяцем
платежа CAPEX (ZBO доступен не ранее 2036-01). До ввода действует BASE
(ёмкость 70 т, потери 4,5%), после — ZBO (120 т, 1,2%).

Спрос распределяется по месяцам равномерно: месяц = 365/12 дня (TA-01),
годовой спрос / 12 (равномерный спрос — допущение реестра TA-01).
"""

from __future__ import annotations

import re

from .deliveries import all_periods, month_index, month_period
from .models import (
    CaseData,
    DAYS_PER_YEAR,
    HORIZON_START_YEAR,
    InventoryResult,
    InventoryTracePoint,
    MonthBalance,
    Plan,
    ServiceResult,
    Violation,
    YearBalance,
    DeliveriesResult,
)

_PERIOD_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")

# Требование резерва — 45 дней (CASE_INPUT).
RESERVE_DAYS = 45.0


def zbo_start_index(plan: Plan) -> int | None:
    """Сквозной номер первого месяца действия ZBO; None — ZBO не введён.

    TA-05: дата ввода ZBO = месяц, следующий за месяцем платежа CAPEX.
    Опция доступна не ранее 2036-01 (units_and_conventions.md §8).
    """
    dates: list[str] = []
    for inv in plan.decisions.investments:
        if inv.investment_id == "ZBO" and inv.action in ("fund_capex", "exercise_option"):
            m = _PERIOD_RE.match(inv.payment_date or "")
            if m:
                y, mo = int(m.group(1)), int(m.group(2))
                # Платёж не ранее 2036-01 (условие доступности опции).
                if (y, mo) >= (2036, 1):
                    dates.append(inv.payment_date)
    if not dates:
        return None
    pay = min(dates)
    py, pm = int(pay[:4]), int(pay[5:7])
    # Ввод — месяц, следующий за месяцем платежа.
    idx = month_index(py, pm) + 1
    return idx


def storage_mode_for_period(case: CaseData, idx: int, zbo_from: int | None) -> tuple[str, float, float]:
    """Действующий режим хранения в месяце idx.

    Возвращает (storage_mode, capacity_t, loss_rate).
    loss_rate учитывает сценарный override периода (case.storage_loss_override,
    адаптер D3.4 — TEAM_MLI_DEGRADATION / TEAM_ZBO_FAILURE).
    """
    period = month_period(idx)
    if zbo_from is not None and idx >= zbo_from:
        try:
            zbo = case.storage("ZBO")
            return "ZBO", zbo.capacity_t, _loss_rate_with_override(
                case, "ZBO", period, zbo.loss_rate_on_throughput
            )
        except Exception:
            pass
    base = case.storage("BASE")
    return "BASE", base.capacity_t, _loss_rate_with_override(
        case, "BASE", period, base.loss_rate_on_throughput
    )


def _loss_rate_with_override(
    case: CaseData, storage_id: str, period: str, base_rate: float
) -> float:
    """Ставка потерь режима с учётом override периода (storage_loss_override).

    Если для storage_id задан интервал (period_start ≤ period ≤ period_end) —
    действует переопределённая ставка, иначе исходная.
    """
    for p_start, p_end, rate in case.storage_loss_override.get(storage_id, []):
        if p_start <= period <= p_end:
            return rate
    return base_rate


def _inventory_shock_lost(case: CaseData, period: str, i_start: float) -> float:
    """Разовая потеря запаса в периоде (inventory_shocks, адаптер D3.4, В7 MMOD).

    base='inventory_start_before_deliveries': потеря = share × I_start месяца.
    """
    lost = 0.0
    for shock in case.inventory_shocks:
        if shock.get("period") == period:
            lost += float(shock.get("share", 0.0)) * i_start
    return lost


def reserve_required_t(demand_total_year_t: float) -> float:
    """Требуемый 45-дневный резерв года: R_y = D_y × 45 / 365 (CASE_INPUT)."""
    return demand_total_year_t * RESERVE_DAYS / DAYS_PER_YEAR


def calculate_inventory(
    case: CaseData, plan: Plan, deliveries: DeliveriesResult
) -> InventoryResult:
    """Помесячный материальный баланс 2035-01 … 2040-12.

    Начальный запас — initial_inventory_t плана (I_start 2035-01).
    Начальный запас НЕ дублируется как поставка месяца (units §3):
    initial_inventory_source — только раскрытие оплаты (волна 2).
    """
    periods = all_periods()
    result = InventoryResult()
    zbo_from = zbo_start_index(plan)

    i_start = float(plan.decisions.inventory_policy.initial_inventory_t)

    for idx, period in enumerate(periods):
        year = HORIZON_START_YEAR + idx // 12

        # Спрос месяца: равномерное распределение годового спроса (TA-01).
        demand_total_m = case.effective_demand_total_t.get(year, 0.0) / 12.0
        demand_crit_m = case.effective_demand_critical_t.get(year, 0.0) / 12.0

        delivered = deliveries.delivered_by_period.get(period, 0.0)
        mode, capacity, loss_rate = storage_mode_for_period(case, idx, zbo_from)

        # Потери: throughput (валовое поступление) × loss_rate действующего
        # режима, ОДИН раз (V06; повторный начёт на остаток — double counting).
        throughput = delivered
        losses = throughput * loss_rate

        # Разовый шок запаса (MMOD и аналоги, адаптер D3.4): отдельный физический
        # механизм потери — НЕ повторный начёт ставок хранения (CR §3).
        shock_lost = _inventory_shock_lost(case, period, i_start)
        if shock_lost > 0.0:
            result.violations.append(
                Violation(
                    rule_id="INVENTORY_SHOCK_APPLIED",
                    period=period,
                    actual=shock_lost,
                    limit=0.0,
                    excess=shock_lost,
                    message_ru=(
                        f"Сценарный шок запаса в период {period}: потеряно "
                        f"{shock_lost:.4f} т (информационная запись применения override)"
                    ),
                )
            )

        # Аллокация при дефиците: сначала критический спрос (§5 конвенций).
        available = i_start + delivered - losses - shock_lost
        available = max(0.0, available)
        served_critical = min(demand_crit_m, available)
        served_total = min(demand_total_m, available)
        # Критический входит в общий: served_total ≥ served_critical всегда.
        served_total = max(served_total, served_critical)

        i_end = max(0.0, available - served_total)
        shortage_total = max(0.0, demand_total_m - served_total)

        # Переполнение ёмкости проверяется каждый месяц (units §6).
        if i_end > capacity + 1e-9:
            result.violations.append(
                Violation(
                    rule_id="STORAGE_OVERFLOW",
                    period=period,
                    actual=i_end,
                    limit=capacity,
                    excess=i_end - capacity,
                    message_ru=(
                        f"Запас в конце периода {period} ({i_end:.4f} т) превышает "
                        f"ёмкость хранилища режима {mode} ({capacity:g} т); "
                        f"излишек {i_end - capacity:.4f} т"
                    ),
                )
            )

        result.monthly_balance.append(
            MonthBalance(
                period=period,
                i_start_t=i_start,
                delivered_t=delivered,
                throughput_t=throughput,
                losses_t=losses,
                served_total_t=served_total,
                served_critical_t=served_critical,
                demand_total_t=demand_total_m,
                demand_critical_t=demand_crit_m,
                shortage_t=shortage_total,
                i_end_t=i_end,
                storage_mode=mode,
                storage_capacity_t=capacity,
            )
        )

        # Порог резерва 45 дней для inventory_trace (по году периода).
        threshold = reserve_required_t(case.effective_demand_total_t.get(year, 0.0))
        result.inventory_trace.append(
            InventoryTracePoint(
                period=period,
                inventory_t=i_end,
                reserve_threshold_t=threshold,
                capacity_t=capacity,
            )
        )

        i_start = i_end

    return result


def calculate_service(case: CaseData, inventory: InventoryResult) -> ServiceResult:
    """Годовая агрегация баланса: SL_total, SL_critical, резерв 45 дней.

    SL = served / demand; при нулевом спросе года SL = 1.0 (явная трактовка
    boundary case по CALCULATION_RULES §7 — без division-by-zero).
    """
    service = ServiceResult()
    by_year: dict[int, list[MonthBalance]] = {}
    for mb in inventory.monthly_balance:
        year = int(mb.period[:4])
        by_year.setdefault(year, []).append(mb)

    for year in sorted(by_year):
        months = by_year[year]
        demand_total = sum(m.demand_total_t for m in months)
        demand_crit = sum(m.demand_critical_t for m in months)
        served_total = sum(m.served_total_t for m in months)
        served_crit = sum(m.served_critical_t for m in months)
        delivered = sum(m.delivered_t for m in months)
        losses = sum(m.losses_t for m in months)
        shortage = sum(m.shortage_t for m in months)

        sl_total = served_total / demand_total if demand_total > 0 else 1.0
        sl_critical = served_crit / demand_crit if demand_crit > 0 else 1.0

        reserve_req = reserve_required_t(demand_total)
        # Физический запас на начало года (январь).
        january = months[0]
        reserve_actual = january.i_start_t

        service.yearly_balance.append(
            YearBalance(
                year=year,
                demand_total_t=demand_total,
                demand_critical_t=demand_crit,
                delivered_t=delivered,
                losses_t=losses,
                served_total_t=served_total,
                served_critical_t=served_crit,
                shortage_t=shortage,
                sl_total=sl_total,
                sl_critical=sl_critical,
                i_start_t=january.i_start_t,
                i_end_t=months[-1].i_end_t,
                reserve_required_t=reserve_req,
                reserve_actual_start_t=reserve_actual,
                reserve_ok=reserve_actual >= reserve_req - 1e-9,
            )
        )

    return service
