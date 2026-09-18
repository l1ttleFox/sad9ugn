# -*- coding: utf-8 -*-
"""
WP2 manual_calc — независимая месячная модель (72 периода 2035-01…2040-12).

Реализация формул: docs/CALCULATION_RULES.md + units_and_conventions.md (TA-01…TA-09).
Код src/engine НЕ используется и НЕ читается (требование независимости, волна 1).

Порядок расчёта месяца:
  1) поставки по lead time (заказы, размещённые L месяцев назад; E — реактивный, TA-03);
  2) throughput = delivered (+ начальный запас в 2035-01, §3 конвенций — платёж 2035);
  3) losses = throughput × loss_rate действующего режима (ОДИН раз, §4/CALC §3);
  4) available = I_start + delivered − losses; served_total = min(D_t, available);
     served_critical = min(D_c, available) — критический входит в общий (§5);
  5) I_end = max(0, available − served_total); shortage = D_t − served_total ≥ 0;
  6) проверки: I_end ≤ capacity (STORAGE_OVERFLOW), резерв 45 дн. на 1 января, SL.

BASE: delivered = planned (reliability НЕ умножается, §9 конвенций / V10).
STRESS: спрос ×1.15 с 2038; цены A/B ×1.25 в 2038–39; ISRU 0.55/0.75 — фактические
доли, повторно на reliability НЕ умножаются.

Заказная политика (TEAM_DECISION, единая для всех стратегий):
 - непросроченные каналы (priority-список): «demand-chasing» — в месяце m размещается
   заказ с поставкой в m+L_s под потребность месяца m+L_s (спрос + потери + целевой
   запас − проекция запаса − уже забронированные поставки), в пределах резерва;
 - Emergency (E): реактивный — в месяце m заказ под дефицит месяца m+1 (TA-03:
   поставка в следующем месяце), если проекция запаса m+1 ниже пола резерва.
Один и тот же plan definition прогоняется в BASE и STRESS (STRESS_PROTOCOL: сравнение
на одном плане); реактивное правило E — единственная адаптация, объявлена явно.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from mc_data import (
    CaseData, Scenario, YEARS, N_MONTHS, LEAD_MONTHS, DISCOUNT_RATE,
    DISCOUNT_T0, HOLDING_COST, m_idx, m_period, m_year, m_month,
)

EPS = 1e-9

CAPEX_ITEMS = {
    ("EARTH_NEW", "buy_option"): 90.0,
    ("EARTH_NEW", "exercise_option"): 270.0,
    ("LUNAR_ISRU", "fund_capex"): 1250.0,
    ("ZBO", "fund_capex"): 180.0,
}


# ---------------------------------------------------------------------------
# Структуры плана и результата
# ---------------------------------------------------------------------------

@dataclass
class PlanDef:
    """Определение стратегии в терминах plan_format.json."""
    plan_id: str
    family: str
    name_ru: str
    reservations: dict[str, dict[int, float]] = field(default_factory=dict)  # sid → год → т/год
    start_months: dict[str, int] = field(default_factory=dict)               # sid → месяц старта в первом году
    investments: list[tuple[str, str, str]] = field(default_factory=list)    # (id, action, YYYY-MM)
    priority: list[str] = field(default_factory=lambda: ["D", "C", "A", "B"])
    initial_inventory_t: float = 0.0
    initial_inventory_source: str = "A"
    reserve_mode: str = "physical"             # physical | contractual_emergency
    reserve_target_days: float = 45.0          # S21 — 60 (кандидат TA-10)
    buffer_t: float = 7.0                      # оперативный буфер сверх резерва
    use_emergency: bool = True                 # реактивные заказы E
    adaptive: bool = False                     # S16/S25 — ветви по сценарию
    branch_rule_ru: str = ""                   # для адаптивных S16/S25
    notes_ru: str = ""


@dataclass
class MonthRow:
    period: str
    year: int
    i_start: float
    delivered: float
    throughput: float
    losses: float
    served_total: float
    served_critical: float
    demand_total: float
    demand_critical: float
    shortage: float
    i_end: float
    storage_mode: str
    storage_capacity: float
    orders: dict[str, float] = field(default_factory=dict)
    arrivals: dict[str, float] = field(default_factory=dict)


@dataclass
class YearFin:
    year: int
    capex: float = 0.0
    procurement: float = 0.0
    reservation: float = 0.0
    top_extra: float = 0.0
    holding: float = 0.0
    fixed_opex: float = 0.0
    total: float = 0.0
    discounted: float = 0.0
    served_total: float = 0.0
    sl_total: float = 1.0
    sl_critical: float = 1.0
    shortage: float = 0.0
    i_start_jan: float = 0.0
    reserve_required: float = 0.0
    cost_per_served: float = 0.0


@dataclass
class Check:
    rule_id: str
    period: str
    passed: bool
    actual: float
    limit: float
    excess: float
    message_ru: str


@dataclass
class RunResult:
    plan_id: str
    scenario_id: str
    months: list[MonthRow]
    years: dict[int, YearFin]
    checks: list[Check]
    total_cost: float
    total_pv: float
    total_shortage: float
    served_total: float
    demand_total: float
    capex_2037: float
    capex_2040: float
    min_sl_total: float
    min_sl_critical: float
    violations: list[Check]
    shortage_2038_2040: float = 0.0


# ---------------------------------------------------------------------------
# Инвестиционные даты
# ---------------------------------------------------------------------------

def inv_date(plan: PlanDef, inv_id: str, action: str) -> str | None:
    for iid, act, date in plan.investments:
        if iid == inv_id and act == action:
            return date
    return None


def zbo_active_idx(plan: PlanDef) -> int | None:
    """Индекс месяца, с которого ZBO действует (месяц после платежа, TA-05)."""
    d = inv_date(plan, "ZBO", "fund_capex")
    if d is None:
        return None
    idx = m_idx(int(d[:4]), int(d[5:7])) + 1
    return idx if idx < N_MONTHS else None


def c_available_idx(plan: PlanDef) -> int | None:
    """C доступен: exercise + 24 мес (TA-02)."""
    d = inv_date(plan, "EARTH_NEW", "exercise_option")
    if d is None:
        return None
    idx = m_idx(int(d[:4]), int(d[5:7])) + LEAD_MONTHS["C"]
    return idx if idx < N_MONTHS else None


def d_available_idx(plan: PlanDef) -> int | None:
    """D доступен с 2038-01 при финансировании не позже 2037-12 (§8)."""
    d = inv_date(plan, "LUNAR_ISRU", "fund_capex")
    if d is None:
        return None
    if m_idx(int(d[:4]), int(d[5:7])) <= m_idx(2037, 12):
        return m_idx(2038, 1)
    return None  # дедлайн нарушен — канал не вводится (нарушение фиксируется в checks)


def source_available_idx(plan: PlanDef, case: CaseData, sid: str) -> int:
    if sid == "C":
        idx = c_available_idx(plan)
        return idx if idx is not None else 10 ** 6
    if sid == "D":
        idx = d_available_idx(plan)
        return idx if idx is not None else 10 ** 6
    src = case.sources[sid]
    return m_idx(src.available_from or 2035, 1)


# ---------------------------------------------------------------------------
# Спрос, резерв, цены
# ---------------------------------------------------------------------------

def demand_month(case: CaseData, sc: Scenario, idx: int) -> tuple[float, float]:
    y = m_year(idx)
    mult = sc.demand_mult.get(y, 1.0)
    return case.demand_total[y] * mult / 12.0, case.demand_critical[y] * mult / 12.0


def reserve_required(case: CaseData, sc: Scenario, year: int, days: float) -> float:
    """R_y = D_y(сценарий, год) × days / 365 (§6)."""
    return case.demand_total[year] * sc.demand_mult.get(year, 1.0) * days / 365.0


def price_with_mult(case: CaseData, sc: Scenario, sid: str, year: int) -> float:
    return case.sources[sid].var_cost * sc.price_mult.get(sid, {}).get(year, 1.0)


def res_year(plan: PlanDef, sid: str, year: int) -> tuple[float, float]:
    """(резерв т/год, доля года period_fraction) с учётом start_month в первом году."""
    res = plan.reservations.get(sid, {}).get(year, 0.0)
    if res <= 0:
        return 0.0, 0.0
    frac = 1.0
    first = min(plan.reservations[sid])
    start = plan.start_months.get(sid, 1)
    if year == first and start > 1:
        frac = (12 - start + 1) / 12.0
    return res, frac


def res_month_cap(plan: PlanDef, sid: str, idx: int) -> float:
    """Месячный лимит отгрузки канала (т в месяц) с учётом прораты первого года."""
    res, frac = res_year(plan, sid, m_year(idx))
    if res <= 0:
        return 0.0
    first = min(plan.reservations[sid])
    start = plan.start_months.get(sid, 1)
    if m_year(idx) == first and m_month(idx) < start:
        return 0.0
    return res * frac / 12.0


# ---------------------------------------------------------------------------
# Основной прогон
# ---------------------------------------------------------------------------

def run_plan(case: CaseData, sc: Scenario, plan: PlanDef) -> RunResult:
    zbo_idx = zbo_active_idx(plan)
    base_store = case.storages["BASE"]
    zbo_store = case.storages["ZBO"]

    months: list[MonthRow] = []
    checks: list[Check] = []

    # статические проверки: резерв ≤ capacity
    for sid, yr_map in plan.reservations.items():
        cap = case.sources[sid].capacity
        for y, r in yr_map.items():
            if r > cap + EPS:
                checks.append(Check("CAPACITY_EXCEEDED", str(y), False, r, cap, r - cap,
                                    f"Резерв {sid} в {y}: {r:.1f} > мощности {cap:.0f} т/год"))

    # CAPEX по датам платежей
    capex_by_month: dict[int, float] = {}
    for iid, act, date in plan.investments:
        if act == "none":
            continue
        amt = CAPEX_ITEMS[(iid, act)]
        idx = m_idx(int(date[:4]), int(date[5:7]))
        capex_by_month[idx] = capex_by_month.get(idx, 0.0) + amt

    # бронирование поставок: (sid, год доставки) → забронировано т (годовой лимит = резерв)
    booked: dict[tuple[str, int], float] = {}
    arrivals: dict[int, dict[str, float]] = {}   # idx → sid → плановая поставка
    orders_log: dict[int, dict[str, float]] = {}

    def year_room(sid: str, arr_idx: int) -> float:
        res, frac = res_year(plan, sid, m_year(arr_idx))
        return max(0.0, res * frac - booked.get((sid, m_year(arr_idx)), 0.0))

    def place(arr_idx: int, sid: str, q: float) -> float:
        if q <= EPS or arr_idx >= N_MONTHS:
            return 0.0
        month_room = res_month_cap(plan, sid, arr_idx) - arrivals.get(arr_idx, {}).get(sid, 0.0)
        q = max(0.0, min(q, year_room(sid, arr_idx), max(0.0, month_room)))
        if q <= EPS:
            return 0.0
        arrivals.setdefault(arr_idx, {})[sid] = arrivals.get(arr_idx, {}).get(sid, 0.0) + q
        key = (sid, m_year(arr_idx))
        booked[key] = booked.get(key, 0.0) + q
        return q

    def inventory_target(idx: int) -> float:
        """Целевой запас на конец месяца: max(резерв текущего года, резерв следующего
        года — проверка на 1 января) + оперативный буфер. Look-ahead обязателен:
        при lead time 4–12 мес накопить запас за декабрь невозможно."""
        y = m_year(idx)
        days = plan.reserve_target_days
        req = reserve_required(case, sc, y, days)
        if y < 2040:
            req = max(req, reserve_required(case, sc, y + 1, days))
        return req + plan.buffer_t

    def projected_start(now: int, target_idx: int, i_now: float) -> float:
        """Проекция I_start(target_idx) по размещённым поставкам и спросу, без новых заказов."""
        proj = i_now
        for k in range(now + 1, target_idx):
            d_t, _ = demand_month(case, sc, k)
            arr = sum(arrivals.get(k, {}).values())
            if k in sc.isru_actual_share and "D" in arrivals.get(k, {}):
                arr -= arrivals[k]["D"] * (1.0 - sc.isru_actual_share[k])
            proj = max(0.0, proj + arr - d_t)
        return proj

    inv_start = plan.initial_inventory_t

    for idx in range(N_MONTHS):
        y = m_year(idx)
        d_t, d_c = demand_month(case, sc, idx)

        zbo_on = zbo_idx is not None and idx >= zbo_idx
        loss_rate = zbo_store.loss_rate if zbo_on else base_store.loss_rate
        capacity = zbo_store.capacity if zbo_on else base_store.capacity
        mode = "ZBO" if zbo_on else "BASE"

        arr = dict(arrivals.get(idx, {}))
        # STRESS: фактические доли ISRU применяются к plan-объёмам (без reliability!)
        if "D" in arr and y in sc.isru_actual_share:
            arr["D"] *= sc.isru_actual_share[y]
        delivered = sum(arr.values())

        throughput = delivered + (plan.initial_inventory_t if idx == 0 else 0.0)
        losses = throughput * loss_rate

        available = inv_start + delivered - losses
        served_total = min(d_t, max(0.0, available))
        served_critical = min(d_c, max(0.0, available))
        i_end = max(0.0, available - served_total)
        shortage = max(0.0, d_t - served_total)

        ord_this: dict[str, float] = {}

        # --- реактивный Emergency: заказ в idx под дефицит idx+1 (TA-03) ---
        if plan.use_emergency and idx + 1 < N_MONTHS and res_year(plan, "E", m_year(idx + 1))[0] > 0:
            nxt = idx + 1
            nd_t, _ = demand_month(case, sc, nxt)
            nxt_arr = sum(arrivals.get(nxt, {}).values())
            if m_year(nxt) in sc.isru_actual_share and "D" in arrivals.get(nxt, {}):
                nxt_arr -= arrivals[nxt]["D"] * (1.0 - sc.isru_actual_share[m_year(nxt)])
            floor = inventory_target(nxt - 1)  # требуемый запас на конец nxt-1 = начало nxt
            proj = i_end + nxt_arr * (1 - loss_rate) - nd_t
            if proj < floor - EPS:
                q = place(nxt, "E", floor - proj)
                if q > EPS:
                    ord_this["E"] = ord_this.get("E", 0.0) + q

        # --- demand-chasing по приоритетам для непросроченных каналов ---
        # Netting-правило (TEAM_DECISION): канал s не бронирует объём, который позже
        # смогут закрыть более приоритетные каналы с МЕНЬШИМ lead time (короткие
        # каналы ещё не заказаны в момент заказа длинного — иначе дешёвый D
        # вытеснялся бы дорогим A, заказываемым за 12 мес).
        for pi, sid in enumerate(plan.priority):
            arr_idx = idx + LEAD_MONTHS[sid]
            if arr_idx >= N_MONTHS or arr_idx < source_available_idx(plan, case, sid):
                continue
            if year_room(sid, arr_idx) <= EPS:
                continue
            nd_t, _ = demand_month(case, sc, arr_idx)
            target = inventory_target(arr_idx)
            proj_start = projected_start(idx, arr_idx, i_end)
            have = sum(arrivals.get(arr_idx, {}).values())
            if m_year(arr_idx) in sc.isru_actual_share and "D" in arrivals.get(arr_idx, {}):
                have -= arrivals[arr_idx]["D"] * (1.0 - sc.isru_actual_share[m_year(arr_idx)])
            # потенциал более приоритетных каналов с меньшим lead time (будут заказаны позже)
            future_cheap = 0.0
            for sid2 in plan.priority[:pi]:
                if LEAD_MONTHS[sid2] < LEAD_MONTHS[sid] and arr_idx >= source_available_idx(plan, case, sid2):
                    cap2 = res_month_cap(plan, sid2, arr_idx)
                    booked2 = arrivals.get(arr_idx, {}).get(sid2, 0.0)
                    if m_year(arr_idx) in sc.isru_actual_share and sid2 == "D":
                        booked2 *= sc.isru_actual_share[m_year(arr_idx)]
                        cap2 *= sc.isru_actual_share[m_year(arr_idx)]  # фактическая доля стресса
                    future_cheap += max(0.0, cap2 - booked2)
            need = max(0.0, nd_t * (1 + loss_rate) + target - proj_start - have - future_cheap)
            q = place(arr_idx, sid, need)
            if q > EPS:
                ord_this[sid] = ord_this.get(sid, 0.0) + q

        orders_log[idx] = ord_this
        months.append(MonthRow(
            period=m_period(idx), year=y, i_start=inv_start, delivered=delivered,
            throughput=throughput, losses=losses, served_total=served_total,
            served_critical=served_critical, demand_total=d_t, demand_critical=d_c,
            shortage=shortage, i_end=i_end, storage_mode=mode, storage_capacity=capacity,
            orders=dict(ord_this), arrivals=dict(arr),
        ))

        if i_end > capacity + EPS:
            checks.append(Check("STORAGE_OVERFLOW", m_period(idx), False, i_end, capacity,
                                i_end - capacity,
                                f"Запас {i_end:.1f} т > ёмкости {capacity:.0f} т в {m_period(idx)}"))
        inv_start = i_end

    # ------------------------------------------------------------------
    # Годовые агрегаты и финансы
    # ------------------------------------------------------------------
    years: dict[int, YearFin] = {y: YearFin(year=y) for y in YEARS}
    order_year_vol: dict[tuple[str, int], float] = {}
    for idx, ordm in orders_log.items():
        for sid, q in ordm.items():
            key = (sid, m_year(idx))
            order_year_vol[key] = order_year_vol.get(key, 0.0) + q

    for mr in months:
        yf = years[mr.year]
        yf.served_total += mr.served_total
        yf.shortage += mr.shortage
        # holding: 0.72 × time-weighted средний запас (TA-08: среднее (I_start+I_end)/2 по месяцам)
        yf.holding += HOLDING_COST * (mr.i_start + mr.i_end) / 2.0 / 12.0

    for mr in months:
        if mr.period.endswith("-01"):
            years[mr.year].i_start_jan = mr.i_start

    # CAPEX
    for idx, amt in capex_by_month.items():
        years[m_year(idx)].capex += amt
    # фикс. OPEX: ZBO +12/год после ввода (прората), ISRU +70/год с 2038
    if zbo_idx is not None:
        for idx in range(zbo_idx, N_MONTHS):
            years[m_year(idx)].fixed_opex += zbo_store.fixed_opex / 12.0
    d_idx = d_available_idx(plan)
    if d_idx is not None:
        for idx in range(d_idx, N_MONTHS):
            years[m_year(idx)].fixed_opex += 70.0 / 12.0

    # Резервирование (прората) и переменные платежи (TOP через max, §7)
    for sid in ["A", "B", "C", "D", "E"]:
        for y in YEARS:
            res, frac = res_year(plan, sid, y)
            if res > 0:
                years[y].reservation += case.sources[sid].res_rate * res * frac
            q_order = order_year_vol.get((sid, y), 0.0)
            # начальный запас 2035 — заказ подготовительного периода источника (чаще A)
            if y == 2035 and sid == plan.initial_inventory_source and plan.initial_inventory_t > 0:
                q_order += plan.initial_inventory_t
            top_base = res * frac
            q_pay = max(q_order, case.sources[sid].top_share * top_base)
            price = price_with_mult(case, sc, sid, y)
            years[y].procurement += price * q_pay
            years[y].top_extra += price * max(0.0, case.sources[sid].top_share * top_base - q_order)

    total_cost = total_pv = 0.0
    for y in YEARS:
        yf = years[y]
        yf.total = yf.capex + yf.procurement + yf.reservation + yf.holding + yf.fixed_opex
        yf.discounted = yf.total / (1 + DISCOUNT_RATE) ** (y - DISCOUNT_T0)   # TA-06/07
        yf.cost_per_served = yf.total / yf.served_total if yf.served_total > EPS else float("nan")
        total_cost += yf.total
        total_pv += yf.discounted

    # ------------------------------------------------------------------
    # Проверки ограничений (численно, по каждому году)
    # ------------------------------------------------------------------
    cum_2037 = sum(years[y].capex for y in YEARS if y <= 2037)
    cum_2040 = sum(years[y].capex for y in YEARS)
    checks.append(Check("CAPEX_2037", "2035-2037", cum_2037 <= 1800 + EPS, cum_2037, 1800.0,
                        max(0.0, cum_2037 - 1800.0),
                        f"CAPEX до 2037-12: {cum_2037:.0f} млн {'≤' if cum_2037 <= 1800 else '>'} 1800 млн"))
    checks.append(Check("CAPEX_2040", "2035-2040", cum_2040 <= 2800 + EPS, cum_2040, 2800.0,
                        max(0.0, cum_2040 - 2800.0),
                        f"CAPEX до 2040-12: {cum_2040:.0f} млн {'≤' if cum_2040 <= 2800 else '>'} 2800 млн"))

    e_offtake: dict[int, float] = {y: 0.0 for y in YEARS}
    losses_y: dict[int, float] = {y: 0.0 for y in YEARS}
    thr_y: dict[int, float] = {y: 0.0 for y in YEARS}
    for mr in months:
        e_offtake[mr.year] += mr.arrivals.get("E", 0.0)
        losses_y[mr.year] += mr.losses
        thr_y[mr.year] += mr.throughput

    min_sl_t = min_sl_c = 1.0
    for y in YEARS:
        yf = years[y]
        d_tot = case.demand_total[y] * sc.demand_mult.get(y, 1.0)
        d_crit = case.demand_critical[y] * sc.demand_mult.get(y, 1.0)
        serv_t = sum(mr.served_total for mr in months if mr.year == y)
        serv_c = sum(mr.served_critical for mr in months if mr.year == y)
        sl_t = serv_t / d_tot if d_tot > EPS else 1.0
        sl_c = serv_c / d_crit if d_crit > EPS else 1.0
        yf.sl_total, yf.sl_critical = sl_t, sl_c
        yf.reserve_required = reserve_required(case, sc, y, 45.0)
        min_sl_t, min_sl_c = min(min_sl_t, sl_t), min(min_sl_c, sl_c)
        hard = sc.scenario_id == "BASE"
        ok_t, ok_c = sl_t >= 0.97 - EPS, sl_c >= 0.99 - EPS
        checks.append(Check("BASE_TOTAL_SERVICE" if hard else "STRESS_TOTAL_SERVICE", str(y),
                            ok_t, sl_t, 0.97, max(0.0, 0.97 - sl_t),
                            f"SL_total {y}: {sl_t:.4f} {'≥' if ok_t else '<'} 0.97"))
        checks.append(Check("BASE_CRITICAL_SERVICE" if hard else "STRESS_CRITICAL_SERVICE", str(y),
                            ok_c, sl_c, 0.99, max(0.0, 0.99 - sl_c),
                            f"SL_critical {y}: {sl_c:.4f} {'≥' if ok_c else '<'} 0.99"))

        if plan.reserve_mode == "physical":
            ok = yf.i_start_jan >= yf.reserve_required - EPS
            checks.append(Check("RESERVE_45D", str(y), ok, yf.i_start_jan, yf.reserve_required,
                                max(0.0, yf.reserve_required - yf.i_start_jan),
                                f"Резерв 45 дн. {y}: запас 01.01 = {yf.i_start_jan:.2f} т "
                                f"{'≥' if ok else '<'} {yf.reserve_required:.2f} т"))
        else:
            # контрактный Emergency-резерв (§6): объём, доставляемый за период ожидания
            # 42 дня = e_cap × 42/365, должен покрыть спрос за 42 дня; иначе — нарушение
            wait_frac = 42.0 / 365.0
            demand_wait = d_tot * wait_frac            # спрос за период ожидания
            e_cap = res_year(plan, "E", y)[0]
            coverage = e_cap * wait_frac               # сколько E физически привезёт за 42 дня
            ok = coverage >= demand_wait - EPS
            checks.append(Check("RESERVE_45D", str(y), ok, coverage, demand_wait,
                                max(0.0, demand_wait - coverage),
                                f"Контрактный резерв {y}: E может доставить за 42 дня "
                                f"{coverage:.2f} т (={e_cap:.0f}×42/365) "
                                f"{'≥' if ok else '<'} спроса за 42 дня {demand_wait:.2f} т"))

        if sc.loss_ceiling_from is not None and y >= sc.loss_ceiling_from:
            ratio = losses_y[y] / thr_y[y] if thr_y[y] > EPS else 0.0
            ok = ratio <= sc.loss_ceiling + EPS
            checks.append(Check("STRESS_LOSS_LIMIT", str(y), ok, ratio, sc.loss_ceiling,
                                max(0.0, ratio - sc.loss_ceiling),
                                f"Потери/throughput {y}: {ratio:.4f} "
                                f"{'≤' if ok else '>'} {sc.loss_ceiling:.2f}"))

    # EMERGENCY_BASE_STREAK (TA-09: E базовый, если отбор > 40% served года)
    base_years = {y for y in YEARS if years[y].served_total > EPS and
                  e_offtake[y] > 0.40 * years[y].served_total}
    streak = max_streak = 0
    for y in YEARS:
        streak = streak + 1 if y in base_years else 0
        max_streak = max(max_streak, streak)
    checks.append(Check("EMERGENCY_BASE_STREAK", "2035-2040", max_streak <= 2, max_streak, 2,
                        max(0, max_streak - 2),
                        f"Emergency как база: макс. серия {max_streak} год(а) (лимит 2); "
                        f"базовые годы: {sorted(base_years) if base_years else 'нет'}"))

    # дедлайн ISRU (платёж ≤ 2037-12)
    d_date = inv_date(plan, "LUNAR_ISRU", "fund_capex")
    if d_date is not None:
        ok = d_date <= "2037-12"
        checks.append(Check("ISRU_DEADLINE", d_date, ok, 0.0 if ok else 1.0, 0.0,
                            0.0 if ok else 1.0,
                            f"Финансирование ISRU {d_date}: {'в срок (≤2037-12)' if ok else 'ПОСЛЕ дедлайна 2037-12 — канал D не вводится'}"))

    violations = [c for c in checks if not c.passed]
    return RunResult(
        plan_id=plan.plan_id, scenario_id=sc.scenario_id, months=months, years=years,
        checks=checks, total_cost=total_cost, total_pv=total_pv,
        total_shortage=sum(mr.shortage for mr in months),
        served_total=sum(mr.served_total for mr in months),
        demand_total=sum(mr.demand_total for mr in months),
        capex_2037=cum_2037, capex_2040=cum_2040,
        min_sl_total=min_sl_t, min_sl_critical=min_sl_c, violations=violations,
        shortage_2038_2040=sum(years[y].shortage for y in (2038, 2039, 2040)),
    )


