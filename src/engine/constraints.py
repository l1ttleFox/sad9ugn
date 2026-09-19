"""Проверки ограничений: constraints.csv + правила CASE_RULES.md.

check_constraints(...) -> list[Violation] — ТОЛЬКО нарушения (passed=False),
контракт core_api.md v1.0.

check_all(...) -> list[ConstraintCheck] — ПОЛНЫЙ реестр проверок (passed=true
и false) по result_format.json (решение оркестратора D4.2): UI и экспорт
берут passed-список отсюда, violations — только нарушения.

Реализуемые rule_id:
- из constraints.csv (CASE_INPUT, severity=hard):
  BASE_CRITICAL_SERVICE (SL_crit ≥ 0.99 ежегодно, BASE),
  BASE_TOTAL_SERVICE (SL_total ≥ 0.97 ежегодно, BASE),
  CAPEX_2037 (Σ CAPEX payment_date ≤ 2037-12 ≤ 1800 млн),
  CAPEX_2040 (Σ CAPEX ≤ 2800 млн),
  RESERVE_45D (ежегодно: физический запас на 01.01 ≥ D_y×45/365 ИЛИ
  доказанный контрактный Emergency-эквивалент, units §6),
  EMERGENCY_BASE_STREAK (≤ 2 лет подряд; TA-09: год «базовый» для E,
  если отбор E > 40% served года),
  STRESS_LOSS_LIMIT (losses/throughput ≤ 0.02 с 2038, только MANDATORY_STRESS);
- внутренние (расчётный контур + статика плана):
  CAPACITY_EXCEEDED (reserved > capacity; заказ месяца > доли резерва),
  STORAGE_OVERFLOW (I_end > ёмкость в любом месяце),
  NEGATIVE_INVENTORY (защита: I_end < 0 быть не должно),
  LEAD_TIME_VIOLATION (заказ/поставка раньше возможной по lead time),
  ISRU_WITHOUT_CAPEX (заказы D без финансирования LUNAR_ISRU),
  EARTH_NEW_WITHOUT_EXERCISE (заказы C без exercise EARTH_NEW),
  ISRU_FIRST_YEAR_RELIABILITY (предупреждение severity=soft: план заявляет
  надёжность D 2038 выше 0.78 — в стрессе фактическая доля 0.55).

Формат сообщения о нарушении — README организатора §26: rule_id, период,
факт, лимит, excess, причина на русском. Система диагностирует, не чинит
(CASE_RULES §8).
"""

from __future__ import annotations

import re

from .models import (
    CaseData,
    ConstraintCheck,
    CostResult,
    DeliveriesResult,
    HORIZON_END_YEAR,
    HORIZON_START_YEAR,
    InventoryResult,
    Plan,
    ServiceResult,
    Violation,
)

_PERIOD_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")

# TA-09: канал E считается «базовым» в году при отборе > 40% served года.
EMERGENCY_BASE_SHARE = 0.40
# Порог reliability канала D первого года из CASE_INPUT (2038:0.78).
ISRU_FIRST_YEAR_RELIABILITY = 0.78


def _check(rule_id: str, period: str, passed: bool, actual: float, limit: float,
           message_ru: str, severity: str = "hard",
           source: str = "constraints.csv") -> ConstraintCheck:
    excess = 0.0 if passed else round(abs(actual - limit), 10)
    return ConstraintCheck(
        rule_id=rule_id, period=period, passed=passed,
        actual=actual, limit=limit, excess=excess,
        message_ru=message_ru, severity=severity, source=source,
    )


def _to_violation(c: ConstraintCheck) -> Violation:
    return Violation(
        rule_id=c.rule_id, period=c.period, actual=c.actual,
        limit=c.limit, excess=c.excess, message_ru=c.message_ru,
    )


def _capex_cumulative(plan: Plan, costs: CostResult) -> tuple[float, float]:
    """Σ CAPEX с payment_date ≤ 2037-12 и Σ CAPEX за весь горизонт.

    Используется capex_cumulative_mln финансового блока (платежи до 2035-01
    отнесены на 2035 год — units §3; лимит 1800 охватывает и их).
    """
    cum_2040 = 0.0
    cum_2037 = 0.0
    for row in costs.financial_breakdown:
        cum_2040 += row.capex_mln
        if row.year <= 2037:
            cum_2037 += row.capex_mln
    return cum_2037, cum_2040


def _emergency_offtake_by_year(case: CaseData, plan: Plan,
                               deliveries: DeliveriesResult) -> dict[int, float]:
    """Фактический отбор канала E по годам (т)."""
    offtake: dict[int, float] = {}
    for (sid, period), actual in deliveries.actual_by_source_period.items():
        if sid != "E":
            continue
        m = _PERIOD_RE.match(period)
        if not m:
            continue
        year = int(m.group(1))
        offtake[year] = offtake.get(year, 0.0) + actual
    return offtake


def _contractual_reserve_ok(plan: Plan, case: CaseData, year: int) -> tuple[bool, float, float]:
    """Доказательство контрактного Emergency-эквивалента резерва 45 дней (units §6).

    Возвращает (ok, coverage_t, demand_wait_t): покрытие за период ожидания
    42 дня = reserved_capacity_E × 42/365 должно быть ≥ спроса за 42 дня.
    Требуется заполненный emergency_contract (иначе доказательство отсутствует).
    """
    demand_wait = case.effective_demand_total_t.get(year, 0.0) * 42.0 / 365.0
    ec = plan.decisions.emergency_contract
    if ec is None or ec.reserved_capacity_t_per_year <= 0:
        return False, 0.0, demand_wait
    coverage = ec.reserved_capacity_t_per_year * 42.0 / 365.0
    return coverage >= demand_wait - 1e-9, coverage, demand_wait


def check_all(
    case: CaseData,
    plan: Plan,
    deliveries: DeliveriesResult,
    inventory: InventoryResult,
    service: ServiceResult,
    costs: CostResult,
    extra_violations: list[Violation] | None = None,
) -> list[ConstraintCheck]:
    """ПОЛНЫЙ реестр проверок (passed=true и false) — D4.2.

    extra_violations — нарушения расчётного контура (deliveries/inventory),
    включаются в реестр как есть (source='internal').
    """
    checks: list[ConstraintCheck] = []
    is_base = case.scenario_id == "BASE"
    is_mandatory_stress = case.scenario_id == "MANDATORY_STRESS"
    years = list(range(HORIZON_START_YEAR, HORIZON_END_YEAR + 1))

    # --- ограничения из constraints.csv (CASE_INPUT) -----------------------
    limits = {c.constraint_id: c for c in case.constraints}

    # SL (BASE hard; в стрессе те же уровни — ориентиры устойчивости, units §9)
    yb = {y.year: y for y in service.yearly_balance}
    for year in years:
        b = yb.get(year)
        if b is None:
            continue
        rule_total = "BASE_TOTAL_SERVICE"
        rule_crit = "BASE_CRITICAL_SERVICE"
        lim_total = float(limits[rule_total].value) if rule_total in limits else 0.97
        lim_crit = float(limits[rule_crit].value) if rule_crit in limits else 0.99
        ok_total = b.sl_total >= lim_total - 1e-9
        checks.append(_check(
            rule_total, str(year), ok_total, b.sl_total, lim_total,
            f"SL_total {year}: {b.sl_total:.4f} {'≥' if ok_total else '<'} {lim_total}"
            + ("" if is_base else " (сценарий не BASE — ориентир устойчивости)"),
        ))
        ok_crit = b.sl_critical >= lim_crit - 1e-9
        checks.append(_check(
            rule_crit, str(year), ok_crit, b.sl_critical, lim_crit,
            f"SL_critical {year}: {b.sl_critical:.4f} {'≥' if ok_crit else '<'} {lim_crit}"
            + ("" if is_base else " (сценарий не BASE — ориентир устойчивости)"),
        ))

    # CAPEX-лимиты
    cum_2037, cum_2040 = _capex_cumulative(plan, costs)
    lim_2037 = float(limits["CAPEX_2037"].value) if "CAPEX_2037" in limits else 1800.0
    lim_2040 = float(limits["CAPEX_2040"].value) if "CAPEX_2040" in limits else 2800.0
    ok = cum_2037 <= lim_2037 + 1e-9
    checks.append(_check(
        "CAPEX_2037", "2035-2037", ok, cum_2037, lim_2037,
        f"CAPEX до 2037-12: {cum_2037:.1f} млн {'≤' if ok else '>'} {lim_2037:.0f} млн",
    ))
    ok = cum_2040 <= lim_2040 + 1e-9
    checks.append(_check(
        "CAPEX_2040", "2035-2040", ok, cum_2040, lim_2040,
        f"CAPEX до 2040-12: {cum_2040:.1f} млн {'≤' if ok else '>'} {lim_2040:.0f} млн",
    ))

    # Резерв 45 дней (ежегодно): физический ИЛИ доказанный контрактный
    policy = plan.decisions.inventory_policy
    for year in years:
        b = yb.get(year)
        if b is None:
            continue
        required = b.reserve_required_t
        if policy.reserve_mode == "physical":
            ok = b.reserve_actual_start_t >= required - 1e-9
            checks.append(_check(
                "RESERVE_45D", str(year), ok, b.reserve_actual_start_t, required,
                f"Резерв 45 дн. {year}: запас на 01.01 = {b.reserve_actual_start_t:.2f} т "
                f"{'≥' if ok else '<'} требуемых {required:.2f} т",
            ))
        else:
            ok, coverage, demand_wait = _contractual_reserve_ok(plan, case, year)
            checks.append(_check(
                "RESERVE_45D", str(year), ok, coverage, demand_wait,
                f"Контрактный резерв {year}: Emergency доставит за 42 дня "
                f"{coverage:.2f} т {'≥' if ok else '<'} спроса за 42 дня {demand_wait:.2f} т"
                + ("" if ok else " — доказательство эквивалентности отсутствует"),
            ))

    # EMERGENCY_BASE_STREAK: ≤ 2 лет подряд «базовости» E (TA-09)
    e_offtake = _emergency_offtake_by_year(case, plan, deliveries)
    base_years = {
        y for y in years
        if yb.get(y) is not None and yb[y].served_total_t > 0
        and e_offtake.get(y, 0.0) > EMERGENCY_BASE_SHARE * yb[y].served_total_t
    }
    streak = max_streak = 0
    for y in years:
        streak = streak + 1 if y in base_years else 0
        max_streak = max(max_streak, streak)
    lim_streak = float(limits["EMERGENCY_BASE_STREAK"].value) if "EMERGENCY_BASE_STREAK" in limits else 2.0
    ok = max_streak <= lim_streak + 1e-9
    checks.append(_check(
        "EMERGENCY_BASE_STREAK", "2035-2040", ok, max_streak, lim_streak,
        f"Emergency как базовый канал: максимальная серия {max_streak} год(а) "
        f"(лимит {lim_streak:.0f}); базовые годы: {sorted(base_years) if base_years else 'нет'}",
    ))

    # STRESS_LOSS_LIMIT: только MANDATORY_STRESS, losses/throughput ≤ 0.02 с 2038
    ceiling_cfg = case.loss_ceiling or {}
    if is_mandatory_stress and ceiling_cfg.get("enabled"):
        from_year = int(ceiling_cfg.get("from_year", 2038))
        max_ratio = float(ceiling_cfg.get("max_losses_divided_by_throughput", 0.02))
        for year in years:
            if year < from_year:
                continue
            losses = sum(m.losses_t for m in inventory.monthly_balance
                         if m.period.startswith(str(year)))
            throughput = sum(m.throughput_t for m in inventory.monthly_balance
                             if m.period.startswith(str(year)))
            ratio = losses / throughput if throughput > 0 else 0.0
            ok = ratio <= max_ratio + 1e-9
            checks.append(_check(
                "STRESS_LOSS_LIMIT", str(year), ok, ratio, max_ratio,
                f"Потери/throughput {year}: {ratio:.4f} {'≤' if ok else '>'} {max_ratio:.2f}",
            ))

    # --- статика плана против каталога (внутренние) ------------------------
    for r in plan.decisions.capacity_reservations:
        try:
            capacity = case.source(r.source_id).capacity_t_per_year
        except Exception:
            continue  # неизвестный канал — ловит validate_plan (UNKNOWN_SOURCE)
        # сценарное снижение мощности (адаптер D3.4)
        cap_ov = case.capacity_override.get((r.source_id, r.year))
        effective_capacity = cap_ov if cap_ov is not None else capacity
        ok = r.reserved_capacity_t_per_year <= effective_capacity + 1e-9
        checks.append(_check(
            "CAPACITY_EXCEEDED", str(r.year), ok,
            r.reserved_capacity_t_per_year, effective_capacity,
            f"Резерв канала '{r.source_id}' на {r.year}: "
            f"{r.reserved_capacity_t_per_year:g} т/год "
            f"{'≤' if ok else '>'} мощности {effective_capacity:g} т/год",
            source="internal",
        ))

    # Заказы C/D без соответствующих инвестиций (статика)
    funded: dict[str, str] = {}
    for inv in plan.decisions.investments:
        if inv.action != "none":
            prev = funded.get(inv.investment_id)
            if prev is None or inv.payment_date < prev:
                funded[inv.investment_id] = inv.payment_date
    for rule_id, sid, iid in (
        ("EARTH_NEW_WITHOUT_EXERCISE", "C", "EARTH_NEW"),
        ("ISRU_WITHOUT_CAPEX", "D", "LUNAR_ISRU"),
    ):
        orders = [o for o in plan.decisions.supply_orders
                  if o.source_id == sid and o.ordered_volume_t > 0]
        if not orders:
            continue
        action = "exercise_option" if iid == "EARTH_NEW" else "fund_capex"
        has = any(
            inv.investment_id == iid and inv.action == action
            for inv in plan.decisions.investments
        )
        deadline_ok = True
        if iid == "LUNAR_ISRU" and has:
            deadline_ok = funded.get(iid, "9999") <= "2037-12"
        ok = has and deadline_ok
        period = min(o.period for o in orders)
        vol = sum(o.ordered_volume_t for o in orders)
        reason = (
            f"заказы канала '{sid}' (суммарно {vol:.1f} т, с периода {period}) "
            f"без {action} '{iid}'"
            if not has else
            f"заказы канала '{sid}': финансирование '{iid}' от {funded.get(iid)} "
            f"позднее дедлайна 2037-12"
        )
        checks.append(_check(
            rule_id, period, ok, vol if not ok else 0.0, 0.0,
            ("Нарушение: " + reason) if not ok else
            f"Канал '{sid}': инвестиция '{iid}' ({action}) присутствует в плане",
            source="internal",
        ))

    # ISRU_FIRST_YEAR_RELIABILITY (предупреждение, soft): план заявляет
    # надёжность D первого года выше CASE_INPUT 0.78.
    declared_high = False
    for a in plan.assumptions:
        txt = f"{a.id} {a.value} {a.unit} {a.rationale_ru} {a.scope}".lower()
        if "isru" in txt or "lunar" in txt or "канал d" in txt or "d 2038" in txt:
            try:
                val = float(str(a.value).replace(",", "."))
            except (TypeError, ValueError):
                val = None
            if val is not None and val > ISRU_FIRST_YEAR_RELIABILITY:
                declared_high = True
    checks.append(_check(
        "ISRU_FIRST_YEAR_RELIABILITY", "2038", not declared_high,
        1.0 if declared_high else 0.0, ISRU_FIRST_YEAR_RELIABILITY,
        ("Предупреждение: план заявляет надёжность канала D 2038 выше 0.78 — "
         "в CASE_INPUT reliability 2038 = 0.78, а в MANDATORY_STRESS фактическая "
         "доля поставки 0.55; гарантия недостижима")
        if declared_high else
        "План не заявляет надёжность канала D 2038 выше 0.78 (CASE_INPUT)",
        severity="soft", source="internal",
    ))

    # --- нарушения расчётного контура (deliveries/inventory) ---------------
    internal_violations: list[Violation] = []
    internal_violations.extend(deliveries.violations)
    internal_violations.extend(inventory.violations)
    if extra_violations:
        internal_violations.extend(extra_violations)
    for v in internal_violations:
        checks.append(ConstraintCheck(
            rule_id=v.rule_id, period=v.period, passed=False,
            actual=v.actual, limit=v.limit, excess=v.excess,
            message_ru=v.message_ru, severity="hard", source="internal",
        ))

    # NEGATIVE_INVENTORY — защита: физический запас не должен быть отрицателен
    worst = min((m.i_end_t for m in inventory.monthly_balance), default=0.0)
    ok = worst >= -1e-9
    checks.append(_check(
        "NEGATIVE_INVENTORY", "2035-2040", ok, worst, 0.0,
        f"Минимальный запас на конец месяца за горизонт: {worst:.4f} т "
        f"({'≥ 0 — отрицательного запаса нет' if ok else '< 0 — отрицательный запас!'})",
        source="internal",
    ))

    return checks


def check_constraints(
    case: CaseData,
    plan: Plan,
    inventory: InventoryResult,
    service: ServiceResult,
    costs: CostResult,
    deliveries: DeliveriesResult | None = None,
) -> list[Violation]:
    """Все ограничения constraints.csv + правила CASE_RULES.md (контракт v1.0).

    Каждая Violation: rule_id, year/month, факт, лимит, excess, описание на
    русском. Возвращает ТОЛЬКО нарушения (passed=False); полный passed-список
    — check_all() (D4.2).

    deliveries — необязательный параметр (расширение сигнатуры с значением по
    умолчанию, контракт не нарушен): нужен для EMERGENCY_BASE_STREAK и
    включения помесячных нарушений расчётного контура.
    """
    empty_deliveries = deliveries if deliveries is not None else DeliveriesResult()
    checks = check_all(
        case, plan, empty_deliveries, inventory, service, costs
    )
    return [_to_violation(c) for c in checks if not c.passed]
