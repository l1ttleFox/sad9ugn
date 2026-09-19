"""Финансовый блок: переменные платежи (take-or-pay), резервирование, хранение,
фиксированный OPEX, CAPEX по датам платежей, дисконтирование.

Формулы (CALCULATION_RULES §5, §6, §8, §9, §12; units_and_conventions.md §7, §8, §10):

1. Переменные закупочные платежи по каналам и годам:
   ``Q_pay = max(Q_order_года, TOP_share × Q_reserved_года)``,
   ``payment = price × Q_pay``, price — effective-цена сценария
   (в MANDATORY_STRESS 2038–2039 каналы A и B ×1.25 — уже внутри
   ``case.effective_price_mln_per_t`` после apply_scenario).
   - TOP_share: A = 0.70 всегда; C = 0.50 начиная с года ввода канала
     (через 24 мес после exercise_option, TA-02); остальные 0 —
     значения из supply_sources.csv, обнуляются до года доступности;
   - Q_reserved_года (т) = зарезервированная мощность (т/год) × доля года
     (start_month: неполный год — прората);
   - контрольный период TOP — календарный год; месячный шаг НЕ создаёт
     месячных минимумов (§15 CALCULATION_RULES);
   - TOP НЕ добавляется вторым платежом (V04): ``take_or_pay_extra_mln`` —
     справочная метрика переплаты ``price × max(0, TOP_min − Q_order)``.
2. Резервные платежи: ``rate × annual_reserved_capacity × period_fraction``
   (V05: 100 × 0.4 × 0.5 = 20); Emergency — контракт предусматривает
   резервирование (тариф канала E из supply_sources.csv).
3. Хранение: 0.72 × time-weighted средний запас; среднее по месяцам
   (I_start + I_end)/2, сумма за год / 12 (TA-08).
4. CAPEX по датам платежей из plan.decisions.investments:
   EARTH_NEW buy_option = 90 / exercise_option = 270 (итого 360, третьего
   платежа НЕТ — §12); LUNAR_ISRU fund_capex = 1250; ZBO = 180.
   ``capex_cumulative_mln`` — накопленным итогом (для лимитов 1800/2800, волна 3).
   Платежи подготовительного периода (до 2035-01) относятся на 2035 год (§3 units).
5. Фиксированный OPEX: ZBO +12/год с месяца ввода (TA-05: месяц после платежа,
   не ранее 2036), ISRU +70/год с 2038 (если fund_capex ≤ 2037-12);
   прората по месяцам первого года.
6. Дисконтирование: PV_t = CF_t / (1.10)^(t − 2035), потоки года приводятся
   к концу года (TA-06/TA-07).
7. cost_per_served_t_mln = total_mln / served_total_t года; при served = 0 —
   None (без division-by-zero).
8. Подготовительный период: начальный запас (initial_inventory_source) —
   оплата переменного платежа включается в год paid_in (2035); объём
   учитывается в Q_order года оплаты для take-or-pay max().

Принятые трактовки (раскрыты в REPORT_wave2.md):
- Q_order года = фактически принятый к исполнению отбор заказов года
  (логика deliveries.py): заказы недоступного канала (LEAD_TIME_VIOLATION)
  и излишек сверх месячной доли резерва (CAPACITY_EXCEEDED) не оплачиваются —
  физический отбор невозможен; заказ, размещённый в году, оплачивается
  в этом году, даже если поставка по lead time выходит за горизонт 2040-12
  (обязательство принято — консервативная трактовка, раскрыта в отчёте).
"""

from __future__ import annotations

import re

from .deliveries import (
    channel_available_from,
    month_index,
)
from .inventory import zbo_start_index
from .models import (
    CaseData,
    CostResult,
    DeliveriesResult,
    DISCOUNT_RATE,
    DISCOUNT_T0,
    FinancialRow,
    HORIZON_END_YEAR,
    HORIZON_START_YEAR,
    InventoryResult,
    Plan,
)

_PERIOD_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
_YEAR_RE = re.compile(r"^(\d{4})")


def _parse_year(value: str, what: str) -> int:
    """Год из строки 'YYYY' или 'YYYY-MM'; ошибка — на русском."""
    m = _YEAR_RE.match(str(value or "").strip())
    if not m:
        raise ValueError(f"Не удалось разобрать год из значения '{value}' ({what})")
    return int(m.group(1))


def _investment_option(case: CaseData, investment_id: str):
    for opt in case.investment_options:
        if opt.investment_id == investment_id:
            return opt
    raise ValueError(
        f"Инвестиционная опция '{investment_id}' не найдена в investment_options.csv"
    )


def _capex_amount(case: CaseData, investment_id: str, action: str) -> float:
    """Сумма платежа CAPEX по действию (млн у.е.).

    buy_option → option_fee (EARTH_NEW 90); exercise_option → exercise_cost
    (EARTH_NEW 270; 90 + 270 = 360 итого, третьего платежа нет — §12);
    fund_capex → total_capex (LUNAR_ISRU 1250, ZBO 180); none → 0.
    """
    opt = _investment_option(case, investment_id)
    if action == "buy_option":
        return float(opt.option_fee_mln)
    if action == "exercise_option":
        return float(opt.exercise_cost_mln)
    if action == "fund_capex":
        return float(opt.total_capex_mln)
    if action == "none":
        return 0.0
    raise ValueError(
        f"Недопустимое инвестиционное действие '{action}' опции '{investment_id}' "
        f"в plan.decisions.investments"
    )


def _reservation_fraction(start_month: int) -> float:
    """Доля года резервирования: start_month=1 → 1.0; =7 → 0.5 (прората, V05)."""
    return (13 - start_month) / 12.0


def _reserved_by_year(plan: Plan) -> tuple[dict[tuple[str, int], float], dict[tuple[str, int], int]]:
    """Резервы плана: {(source_id, год): (т/год, start_month)}.

    Дубликаты (source_id, год) сворачиваются как в deliveries.py:
    мощность — max, start_month — min.
    """
    reserved: dict[tuple[str, int], float] = {}
    start_months: dict[tuple[str, int], int] = {}
    for r in plan.decisions.capacity_reservations:
        key = (r.source_id, r.year)
        reserved[key] = max(reserved.get(key, 0.0), r.reserved_capacity_t_per_year)
        start_months[key] = min(start_months.get(key, 12), r.start_month)
    return reserved, start_months


def _ordered_by_year(case: CaseData, plan: Plan) -> dict[tuple[str, int], float]:
    """Q_order по (source_id, год) — фактически принятый к исполнению отбор.

    Логика повторяет deliveries.py: годовой заказ ('YYYY') распределяется
    равномерно по 12 месяцам; заказ недоступного канала (LEAD_TIME_VIOLATION)
    и излишек сверх месячной доли резерва (CAPACITY_EXCEEDED) физически не
    отбираются и не оплачиваются. Заказ, размещённый в году, относится
    к Q_order этого года, даже если поставка по lead time выходит за
    горизонт 2040-12 (обязательство принято).

    Объём подготовительного заказа (initial_inventory_source, units §3)
    добавляется к Q_order канала в год оплаты paid_in (2035).
    """
    n_months = 12 * (HORIZON_END_YEAR - HORIZON_START_YEAR + 1)
    reserved, start_months = _reserved_by_year(plan)
    available_from = {
        s.source_id: channel_available_from(plan, case, s.source_id)
        for s in case.supply_sources
    }

    ordered: dict[tuple[str, int], float] = {}

    def _add(source_id: str, idx: int, volume: float) -> None:
        if idx < 0 or idx >= n_months or volume <= 0:
            return
        avail = available_from.get(source_id)
        if avail is None or idx < avail:
            return  # канал недоступен — заказ не исполняется (нарушение зафиксировано в deliveries)
        year = HORIZON_START_YEAR + idx // 12
        month_no = idx % 12 + 1
        rsv = reserved.get((source_id, year), 0.0)
        # Сценарное снижение мощности (адаптер D3.4) — как в deliveries.py.
        cap_ov = case.capacity_override.get((source_id, year))
        if cap_ov is not None:
            rsv = min(rsv, cap_ov)
        sm = start_months.get((source_id, year), 1)
        limit = (rsv / 12.0) if month_no >= sm else 0.0
        effective = min(volume, limit)  # излишек CAPACITY_EXCEEDED не отбирается
        key = (source_id, year)
        ordered[key] = ordered.get(key, 0.0) + effective

    for o in plan.decisions.supply_orders:
        m = _PERIOD_RE.match(o.period or "")
        if m:
            _add(o.source_id, month_index(int(m.group(1)), int(m.group(2))),
                 o.ordered_volume_t)
            continue
        ym = _YEAR_RE.match(o.period or "")
        if ym:
            year = int(ym.group(1))
            share = o.ordered_volume_t / 12.0
            for mm in range(12):
                _add(o.source_id, month_index(year, mm + 1), share)

    # Подготовительный заказ начального запаса: оплата в год paid_in (2035).
    src = plan.decisions.inventory_policy.initial_inventory_source
    if src is not None and src.volume_t > 0:
        year = _parse_year(src.paid_in, "initial_inventory_source.paid_in")
        key = (src.source_id, year)
        ordered[key] = ordered.get(key, 0.0) + src.volume_t
    return ordered


def _isru_funded_before_2038(plan: Plan) -> bool:
    """LUNAR_ISRU профинансирован до дедлайна 2038-01 (fixed OPEX +70/год)."""
    for inv in plan.decisions.investments:
        if inv.investment_id == "LUNAR_ISRU" and inv.action == "fund_capex":
            m = _PERIOD_RE.match(inv.payment_date or "")
            if m and inv.payment_date <= "2037-12":
                return True
    return False


def calculate_costs(
    case: CaseData,
    plan: Plan,
    deliveries: DeliveriesResult,
    inventory: InventoryResult,
) -> CostResult:
    """Переменные платежи (с take-or-pay через max), резервирование, хранение,
    фиксированный OPEX, CAPEX по датам, дисконтирование (r=0.10, t0=2035).

    Возвращает CostResult с financial_breakdown по годам 2035–2040
    (result_format.json). Ошибки входа — исключения с русским сообщением,
    называющим параметр и период (core_api.md, обязательство 4).
    """
    years = list(range(HORIZON_START_YEAR, HORIZON_END_YEAR + 1))
    result = CostResult()

    reserved, start_months = _reserved_by_year(plan)
    ordered = _ordered_by_year(case, plan)

    # Годы доступности каналов (для TOP_share C «с года ввода» и нуля до ввода).
    available_from = {
        s.source_id: channel_available_from(plan, case, s.source_id)
        for s in case.supply_sources
    }
    first_year: dict[str, int | None] = {}
    for sid, idx in available_from.items():
        first_year[sid] = None if idx is None else HORIZON_START_YEAR + idx // 12

    # --- CAPEX по датам платежей (год платежа; до 2035 → на 2035, units §3) ---
    capex_by_year: dict[int, float] = {y: 0.0 for y in years}
    for inv in plan.decisions.investments:
        m = _PERIOD_RE.match(inv.payment_date or "")
        if not m:
            raise ValueError(
                f"Инвестиция '{inv.investment_id}' (действие '{inv.action}'): "
                f"недопустимая дата платежа '{inv.payment_date}' (ожидается YYYY-MM)"
            )
        amount = _capex_amount(case, inv.investment_id, inv.action)
        year = max(int(m.group(1)), HORIZON_START_YEAR)
        if year > HORIZON_END_YEAR:
            raise ValueError(
                f"Инвестиция '{inv.investment_id}': дата платежа {inv.payment_date} "
                f"вне горизонта планирования {HORIZON_START_YEAR}–{HORIZON_END_YEAR}"
            )
        capex_by_year[year] += amount

    # --- Фиксированный OPEX: число активных месяцев по годам ---
    zbo_opex_per_year = _investment_option(case, "ZBO").fixed_opex_mln_per_year
    isru_opex_per_year = _investment_option(case, "LUNAR_ISRU").fixed_opex_mln_per_year
    zbo_idx = zbo_start_index(plan)
    isru_funded = _isru_funded_before_2038(plan)

    def _active_months(start_idx: int | None, year: int) -> int:
        if start_idx is None:
            return 0
        y0 = HORIZON_START_YEAR + start_idx // 12
        if year < y0:
            return 0
        if year > y0:
            return 12
        return 12 - (start_idx % 12)

    # --- Хранение: 0.72 × средний запас (TA-08) и served по годам ---
    holding_rate = case.storage("BASE").holding_cost_mln_per_t_year
    avg_sum: dict[int, float] = {y: 0.0 for y in years}  # Σ (I_start+I_end)/2 по месяцам
    served_by_year: dict[int, float] = {y: 0.0 for y in years}
    for mb in inventory.monthly_balance:
        y = _parse_year(mb.period, "monthly_balance.period")
        if y not in avg_sum:
            continue
        avg_sum[y] += (mb.i_start_t + mb.i_end_t) / 2.0
        served_by_year[y] += mb.served_total_t

    cumulative_capex = 0.0
    for year in years:
        procurement = 0.0
        reservation = 0.0
        top_extra = 0.0

        for s in case.supply_sources:
            sid = s.source_id
            price = case.effective_price_mln_per_t.get(
                (sid, year), s.variable_cost_mln_per_t
            )

            # Q_reserved года (т) = мощность (т/год) × доля года (прората).
            rsv_cap = reserved.get((sid, year), 0.0)
            fraction = _reservation_fraction(start_months.get((sid, year), 1))
            q_reserved_t = rsv_cap * fraction

            # Резервный платёж: rate × annual_reserved × period_fraction (V05).
            reservation += s.reservation_rate_mln_per_t_year_capacity * rsv_cap * fraction

            # TOP_share: из данных канала; до года доступности — 0
            # (C = 0.50 только начиная с года ввода после exercise + 24 мес).
            top_share = s.take_or_pay_share
            fy = first_year.get(sid)
            if fy is None or year < fy:
                top_share = 0.0

            q_order = ordered.get((sid, year), 0.0)
            top_min = top_share * q_reserved_t
            # Q_pay = max(Q_order, TOP_share × Q_reserved) — TOP входит только
            # в max() и НЕ начисляется вторым платежом (V03, V04).
            q_pay = max(q_order, top_min)
            procurement += price * q_pay
            # Справочная метрика переплаты сверх отбора (не отдельный платёж).
            top_extra += price * max(0.0, top_min - q_order)

        # Подготовительный заказ начального запаса (units §3) ОПЛАЧИВАЕТСЯ
        # здесь же: его объём включён в Q_order года paid_in (2035) в
        # _ordered_by_year, переменный платёж = price × max(Q_order, TOP_min)
        # начисляется один раз — двойного счёта нет.

        capex = capex_by_year[year]
        cumulative_capex += capex

        zbo_months = _active_months(zbo_idx, year)
        isru_months = 12 if (isru_funded and year >= 2038) else 0
        fixed_opex = zbo_opex_per_year * zbo_months / 12.0 + isru_opex_per_year * isru_months / 12.0

        holding = holding_rate * avg_sum[year] / 12.0

        total = capex + procurement + reservation + holding + fixed_opex
        discounted = total / (1.0 + DISCOUNT_RATE) ** (year - DISCOUNT_T0)

        served = served_by_year[year]
        cost_per_served = total / served if served > 0 else None

        result.financial_breakdown.append(
            FinancialRow(
                year=year,
                capex_mln=capex,
                capex_cumulative_mln=cumulative_capex,
                procurement_mln=procurement,
                reservation_mln=reservation,
                take_or_pay_extra_mln=top_extra,
                holding_mln=holding,
                fixed_opex_mln=fixed_opex,
                total_mln=total,
                discounted_mln=discounted,
                cost_per_served_t_mln=cost_per_served,
            )
        )

    return result
