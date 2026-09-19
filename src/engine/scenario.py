"""Применение сценария к данным кейса.

apply_scenario возвращает НОВЫЙ CaseData (исходный не мутируется) с:
- множителями общего и критического спроса (по годам);
- множителями переменных цен (по каналам и годам);
- фактическими долями поставки (actual_delivery_share);
- флагом/порогом loss_ceiling.

BASE — все множители 1.0 (delivered = planned, reliability НЕ участвует).

Формат блоков сценария (configs/*.yaml):
- {'default': 1.0} — одно значение для всех годов;
- {'2038': 1.15, ...} — по годам;
- {'Earth-Core': {'2038': 1.25}, ...} — по каналам (имя канала из
  supply_sources.csv) и годам; внутри канала допустим 'default'.

ВНИМАНИЕ: фактические доли поставки (например ISRU 0.55 в MANDATORY_STRESS)
применяются к плановым объёмам ОДИН раз и НЕ умножаются на reliability
(CALCULATION_RULES §11, units_and_conventions.md §9).
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .models import CaseData, Plan, Scenario


def _lookup(block: dict[str, Any], channel_name: str | None, year: int) -> float:
    """Поиск множителя в блоке сценария.

    Порядок: блок может быть плоским ({'default'/'YYYY': float}) или вложенным
    по каналам ({channel: {...}}). Возврат: значение канала за год →
    'default' канала → общее за год → общий 'default' → 1.0.
    """
    if not block:
        return 1.0
    yk = str(year)

    chan: dict[str, Any] | None = None
    if channel_name is not None:
        val = block.get(channel_name)
        if isinstance(val, dict):
            chan = val

    def pick(d: dict[str, Any] | None) -> float | None:
        if d is None:
            return None
        if yk in d:
            return float(d[yk])
        if "default" in d:
            return float(d["default"])
        return None

    for candidate in (chan, block):
        got = pick(candidate)
        if got is not None:
            return got
    return 1.0


def apply_scenario(case: CaseData, scenario: Scenario) -> CaseData:
    """Возвращает новый CaseData с применёнными множителями сценария."""
    new_case = deepcopy(case)
    new_case.scenario_id = scenario.scenario_id
    new_case.loss_ceiling = deepcopy(scenario.loss_ceiling) or {"enabled": False}

    # Спрос: общий и критический множители по годам.
    for d in case.demand:
        m_total = _lookup(scenario.demand_multiplier, None, d.year)
        m_crit = _lookup(scenario.critical_demand_multiplier, None, d.year)
        total = d.base_total_t * m_total
        crit = d.base_critical_t * m_crit
        # Критический спрос вложен в общий (FAQ): не может превысить общий.
        new_case.effective_demand_total_t[d.year] = total
        new_case.effective_demand_critical_t[d.year] = min(crit, total)

    # Цены по каналам и годам + фактические доли поставки.
    for s in case.supply_sources:
        for d in case.demand:
            m_price = _lookup(scenario.variable_price_multiplier, s.name, d.year)
            new_case.effective_price_mln_per_t[(s.source_id, d.year)] = (
                s.variable_cost_mln_per_t * m_price
            )
            new_case.actual_delivery_share[(s.source_id, d.year)] = _lookup(
                scenario.actual_delivery_share, s.name, d.year
            )

    # Override фактических долей поставки (адаптер D3.4) — поверх множителей
    # сценария (TEAM_ISRU_DELAY: доля D 2038 = 0.0).
    for key, share in case.actual_delivery_share_override.items():
        new_case.actual_delivery_share[key] = share

    return new_case


# ---------------------------------------------------------------------------
# Адаптер scenario_parameters (решение оркестратора D3.4, волна 3)
# ---------------------------------------------------------------------------

def _shift_month(date: str, months: int) -> str:
    """Сдвиг даты 'YYYY-MM' на months месяцев."""
    y, m = int(date[:4]), int(date[5:7])
    idx = (y - 2000) * 12 + (m - 1) + months
    return f"{2000 + idx // 12:04d}-{idx % 12 + 1:02d}"


def apply_scenario_parameters(
    case: CaseData, scenario: Scenario, plan: Plan | None = None
) -> tuple[CaseData, Plan | None]:
    """Адаптер расширенного поля TEAM-сценариев `scenario_parameters` (D3.4).

    Возвращает КОПИЮ CaseData (и копию Plan, если меняются решения плана)
    с применёнными override параметров CASE_INPUT. Обязательные условия:
    - каждое переопределение проверяет ИСХОДНОЕ значение параметра:
      при несовпадении — ValueError с русским сообщением (имя параметра,
      ожидание/факт) — «молчаливая» подмена данных запрещена (CASE_RULES §4);
    - каждое применение журналируется в `case.scenario_journal`;
    - исходный case/plan не мутируются.

    Рекомендуемый порядок: load_case → apply_scenario_parameters →
    apply_scenario (override цены канала входит в effective-цены автоматически;
    при применении ПОСЛЕ apply_scenario effective-цены пересчитываются
    пропорционально).

    Поддерживаемые override (по конфигурациям WP3 configs/team/*.yaml):
    - `source_capacity_override`: {source_id, year, original_capacity_t_per_year,
      new_capacity_t_per_year} — сценарное снижение мощности канала в году;
    - `investment_capex_override`: {investment_id, original_capex_mln,
      new_capex_mln} — перерасход CAPEX опции (В8: TEAM_CAPEX_OVERRUN);
    - `commissioning_override`: {source_id, original_available_from,
      new_available_from} — сдвиг даты ввода канала ('YYYY-MM');
    - `storage_loss_override`: {storage_id, period_start, period_end,
      original_loss_rate, new_loss_rate} — деградация потерь режима хранения;
    - `inventory_shock`: {period, lost_inventory_share, base,
      original_lost_inventory_t} — разовая потеря доли запаса (В7: MMOD);
    - `plan_investment_shift`: {investment_id, action, shift_months} — сдвиг
      платежа в плане (R06: задержка exercise EARTH_NEW);
    - блок с `source_id` + `new_price_mln_per_t` (например 'event'
      TEAM_GEO_CHANNEL_A, TEAM_PRICE_SPIKE_E) — переопределение цены канала.

    Ключи, не являющиеся override (например sensitivity_*), журналируются
    как игнорируемые; неизвестный override — ValueError (не молчим).
    """
    from dataclasses import replace

    params = scenario.scenario_parameters or {}
    new_case = deepcopy(case)
    new_plan = deepcopy(plan) if plan is not None else None
    journal = new_case.scenario_journal

    def _fail(msg: str) -> None:
        raise ValueError(f"Сценарий '{scenario.scenario_id}': {msg}")

    # Плоский блок цены канала (TEAM_PRICE_SPIKE_E, TEAM_GEO_CHANNEL_A):
    # сам scenario_parameters содержит source_id + new_price_mln_per_t.
    if isinstance(params, dict) and "new_price_mln_per_t" in params:
        params = {"price_override": params}

    for key, block in params.items():
        # --- блоки, не являющиеся override (журналируем и пропускаем) ---
        if key.startswith("sensitivity"):
            journal.append(f"[{scenario.scenario_id}] '{key}': параметр чувствительности — не override, проигнорирован адаптером")
            continue
        if not isinstance(block, dict):
            # Скалярная метадата события (event: <id>, label и т.п.) — не override.
            journal.append(f"[{scenario.scenario_id}] '{key}={block}': метаданные сценария — не override, проигнорированы адаптером")
            continue

        # --- переопределение цены канала (плоский блок или вложенный) ---
        blocks: list[tuple[str, dict[str, Any]]] = []
        if isinstance(block, dict) and "new_price_mln_per_t" in block:
            blocks.append((key, block))
        elif isinstance(block, dict):
            for sub_key, sub in block.items():
                if isinstance(sub, dict) and "new_price_mln_per_t" in sub:
                    blocks.append((f"{key}.{sub_key}", sub))
        if blocks:
            for label, pb in blocks:
                sid = str(pb.get("source_id") or "")
                try:
                    src = new_case.source(sid)
                except Exception:
                    _fail(f"override '{label}': канал '{sid}' не найден в supply_sources.csv")
                orig = float(pb["original_price_mln_per_t"])
                newp = float(pb["new_price_mln_per_t"])
                if abs(src.variable_cost_mln_per_t - orig) > 1e-9:
                    _fail(
                        f"override '{label}': исходная цена канала '{sid}' "
                        f"{src.variable_cost_mln_per_t} млн у.е./т не совпадает "
                        f"с заявленной original_price_mln_per_t={orig}"
                    )
                ratio = newp / orig if orig else 0.0
                new_case.supply_sources = [
                    replace(src, variable_cost_mln_per_t=newp)
                    if s.source_id == sid else s
                    for s in new_case.supply_sources
                ]
                # effective-цены пересчитываются пропорционально (работает и до,
                # и после apply_scenario).
                for (esid, year), price in list(new_case.effective_price_mln_per_t.items()):
                    if esid == sid:
                        new_case.effective_price_mln_per_t[(esid, year)] = price * ratio
                journal.append(
                    f"[{scenario.scenario_id}] цена канала '{sid}': {orig} → {newp} млн у.е./т (override '{label}')"
                )
            continue

        if not isinstance(block, dict):
            _fail(f"параметр '{key}' должен быть словарём override")

        if key == "source_capacity_override":
            sid = str(block.get("source_id") or "")
            src = new_case.source(sid)
            orig = float(block["original_capacity_t_per_year"])
            newc = float(block["new_capacity_t_per_year"])
            if abs(src.capacity_t_per_year - orig) > 1e-9:
                _fail(
                    f"override '{key}': исходная мощность канала '{sid}' "
                    f"{src.capacity_t_per_year} т/год не совпадает с заявленной "
                    f"original_capacity_t_per_year={orig}"
                )
            year = int(block["year"])
            new_case.capacity_override[(sid, year)] = newc
            journal.append(
                f"[{scenario.scenario_id}] мощность канала '{sid}' в {year}: "
                f"{orig} → {newc} т/год"
            )
            continue

        if key == "investment_capex_override":
            iid = str(block.get("investment_id") or "")
            opt = None
            for o in new_case.investment_options:
                if o.investment_id == iid:
                    opt = o
                    break
            if opt is None:
                _fail(f"override '{key}': опция '{iid}' не найдена в investment_options.csv")
            orig = float(block["original_capex_mln"])
            newc = float(block["new_capex_mln"])
            if abs(opt.total_capex_mln - orig) > 1e-9:
                _fail(
                    f"override '{key}': исходный CAPEX опции '{iid}' "
                    f"{opt.total_capex_mln} млн не совпадает с заявленным "
                    f"original_capex_mln={orig}"
                )
            new_case.investment_options = [
                replace(opt, total_capex_mln=newc, exercise_cost_mln=newc)
                if o.investment_id == iid else o
                for o in new_case.investment_options
            ]
            journal.append(
                f"[{scenario.scenario_id}] CAPEX опции '{iid}': {orig} → {newc} млн у.е."
            )
            continue

        if key == "actual_delivery_share":
            # Фактические доли поставки по каналам и годам (TEAM_ISRU_DELAY):
            # ключи — ИМЕНА каналов из supply_sources.csv, значения — доли
            # (плоские по годам). Применяются поверх множителей сценария.
            for channel_name, years_block in block.items():
                if not isinstance(years_block, dict):
                    _fail(
                        f"override '{key}': блок канала '{channel_name}' "
                        f"должен быть словарём год→доля"
                    )
                src_row = None
                for s in new_case.supply_sources:
                    if s.name == channel_name:
                        src_row = s
                        break
                if src_row is None:
                    _fail(
                        f"override '{key}': канал '{channel_name}' не найден "
                        f"в supply_sources.csv"
                    )
                for year_key, share in years_block.items():
                    year = int(str(year_key))
                    share_f = float(share)
                    if not (0.0 <= share_f <= 1.0):
                        _fail(
                            f"override '{key}': доля канала '{channel_name}' "
                            f"за {year} = {share_f} вне диапазона 0..1"
                        )
                    new_case.actual_delivery_share_override[(src_row.source_id, year)] = share_f
                    journal.append(
                        f"[{scenario.scenario_id}] фактическая доля канала "
                        f"'{src_row.source_id}' ({channel_name}) в {year}: → {share_f}"
                    )
            continue

        if key == "commissioning_override":
            sid = str(block.get("source_id") or "")
            src = new_case.source(sid)
            orig_from = str(block["original_available_from"])  # 'YYYY-MM'
            new_from = str(block["new_available_from"])
            cur = f"{src.available_from_year:04d}-01" if src.available_from_year else None
            if cur != orig_from:
                _fail(
                    f"override '{key}': исходная дата ввода канала '{sid}' "
                    f"'{cur}' не совпадает с заявленной original_available_from='{orig_from}'"
                )
            new_case.supply_sources = [
                replace(src, available_from_year=int(new_from[:4]))
                if s.source_id == sid else s
                for s in new_case.supply_sources
            ]
            journal.append(
                f"[{scenario.scenario_id}] ввод канала '{sid}': {orig_from} → {new_from}"
            )
            continue

        if key == "storage_loss_override":
            stid = str(block.get("storage_id") or "")
            st = new_case.storage(stid)
            orig = float(block["original_loss_rate"])
            newr = float(block["new_loss_rate"])
            if abs(st.loss_rate_on_throughput - orig) > 1e-9:
                _fail(
                    f"override '{key}': исходные потери режима '{stid}' "
                    f"{st.loss_rate_on_throughput} не совпадают с заявленными "
                    f"original_loss_rate={orig}"
                )
            p_start = str(block["period_start"])
            p_end = str(block["period_end"])
            new_case.storage_loss_override.setdefault(stid, []).append(
                (p_start, p_end, newr)
            )
            journal.append(
                f"[{scenario.scenario_id}] потери режима '{stid}' в {p_start}…{p_end}: "
                f"{orig} → {newr}"
            )
            continue

        if key == "inventory_shock":
            orig_lost = float(block.get("original_lost_inventory_t", 0.0))
            if abs(orig_lost) > 1e-9:
                _fail(
                    f"override '{key}': исходные потери запаса не равны "
                    f"original_lost_inventory_t={orig_lost}"
                )
            new_case.inventory_shocks.append(
                {
                    "period": str(block["period"]),
                    "share": float(block["lost_inventory_share"]),
                    "base": str(block.get("base", "inventory_start_before_deliveries")),
                }
            )
            journal.append(
                f"[{scenario.scenario_id}] шок запаса {block['period']}: "
                f"потеря {float(block['lost_inventory_share']) * 100:g}% запаса"
            )
            continue

        if key == "plan_investment_shift":
            if new_plan is None:
                _fail(f"override '{key}': требуется план (plan=...), план не передан")
            iid = str(block.get("investment_id") or "")
            action = str(block.get("action") or "")
            shift = int(block["shift_months"])
            shifted = 0
            for inv in new_plan.decisions.investments:
                if inv.investment_id == iid and inv.action == action:
                    old = inv.payment_date
                    inv.payment_date = _shift_month(old, shift)
                    journal.append(
                        f"[{scenario.scenario_id}] платёж {iid}/{action}: "
                        f"{old} → {inv.payment_date} (сдвиг {shift} мес)"
                    )
                    shifted += 1
            if shifted == 0:
                # В плане нет такой инвестиции — сдвигать нечего (no-op).
                # Не ошибка: TEAM-сценарии прогоняются на разных планах;
                # факт неприменимости override виден в журнале.
                journal.append(
                    f"[{scenario.scenario_id}] override '{key}': в плане "
                    f"'{new_plan.plan_id}' нет инвестиции '{iid}' с действием "
                    f"'{action}' — не применён (no-op)"
                )
            continue

        _fail(f"неподдерживаемый override '{key}' в scenario_parameters")

    return new_case, new_plan
