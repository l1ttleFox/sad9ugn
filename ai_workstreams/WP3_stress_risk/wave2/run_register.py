"""Финальный risk_register: results/risk_register.csv (+ risk_register.md)
и блок адаптации (триггеры, время реакции по lead times).

Поля — README организатора §22 (risk_id, event, cause, affected_parameter,
period, probability_basis_or_range, physical_consequence,
financial_consequence, service_consequence, dependencies, owner,
mitigation, residual_consequence). Последствия РАССЧИТАНЫ ядром
(прогоны P03/P01/P05 на FINAL-планах), probability_basis — сценарный
диапазон без частоты (STRESS_PROTOCOL, D3.2/D3.3).

Значения — FINAL-планы WP2 (FINAL_BASE / FINAL_STRESS, стратегия S10).
INVENTORY_SHOCK_APPLIED — информационное событие (D8.3), не hard-нарушение.
"""

from __future__ import annotations

import csv
import json
import os

from wp3lib import (
    RESULTS,
    base_case,
    base_plan,
    base_scenario,
    mandatory_scenario,
    meta_block,
    pv_of,
    run_plan,
    run_team,
    stress_plan,
    team_scenario,
    shortage_of,
    violation_signature,
    write_csv,
    write_json,
)

OUT_STRESS = os.path.join(RESULTS, "stress")


def read_p03() -> dict[str, dict]:
    """Строки P03_risks.csv по risk_id (числа — из уже рассчитанного P03)."""
    path = os.path.join(OUT_STRESS, "P03_risks.csv")
    with open(path, encoding="utf-8") as f:
        return {row["risk_id"]: row for row in csv.DictReader(f)}


def facts() -> dict:
    """Ключевые факты FINAL_BASE/FINAL_STRESS для формул последствий."""
    case = base_case()
    r_base = run_plan(case, base_plan(), base_scenario())
    r_mand = run_plan(case, stress_plan(), mandatory_scenario())
    d38_base = sum(
        v for (s, p), v in r_base.deliveries.planned_by_source_period.items()
        if s == "D" and p.startswith("2038")
    )
    d38_stress = sum(
        v for (s, p), v in r_mand.deliveries.planned_by_source_period.items()
        if s == "D" and p.startswith("2038")
    )
    i07 = next(
        m.i_start_t for m in r_base.inventory.monthly_balance if m.period == "2038-07"
    )
    thr38 = sum(
        m.throughput_t for m in r_base.inventory.monthly_balance
        if m.period.startswith("2038")
    )
    thr3637 = sum(
        m.throughput_t for m in r_base.inventory.monthly_balance
        if m.period[:4] in ("2036", "2037")
    )
    cum37 = sum(
        r.capex_mln for r in r_base.costs.financial_breakdown if r.year <= 2037
    )
    return {
        "d38_base": d38_base, "d38_stress": d38_stress, "i07": i07,
        "thr38": thr38, "thr3637": thr3637, "cum37": cum37,
        "pv_base": pv_of(r_base), "pv_stress": pv_of(r_mand),
    }


def main() -> None:
    p03 = read_p03()
    f = facts()

    def g(rid, col):
        return p03[rid][col]

    rows = [
        {
            "risk_id": "R01",
            "event": "Поставка ISRU ниже обязательных 55% (0.55→0.40 в 2038)",
            "cause": "Проблемы добычи и переработки лунного ISRU",
            "affected_parameter": "actual_delivery_share D 2038: 0.55→0.40 (COMBINED с MANDATORY_STRESS — явный комбинированный сценарий TEAM_ISRU_UNDERDELIVERY_COMBINED)",
            "period": "2038",
            "probability_basis_or_range": "сценарный подход: тяжесть без частоты; условная доля 0.40 (интервал чувствительности, не вероятность)",
            "physical_consequence": f"недопоставка ≈ 0.15×{f['d38_stress']:.1f} = {0.15*f['d38_stress']:.1f} т; дефицит не возникает (0.0 т), но запас на 2039-01 падает до 40.6 т < резерва 45.4 т",
            "financial_consequence": f"ΔPV {g('R01','d_pv_mln')} млн против MANDATORY_STRESS (расходы снижаются — поставки D срезаны)",
            "service_consequence": "SL не падает (1.000); 2 новых нарушения RESERVE_45D (2039, 2040) — истощение запаса ниже 45-дневного резерва",
            "dependencies": "только как явный combined с MANDATORY_STRESS (план FINAL_STRESS); резерв B и запас",
            "owner": "Оператор ISRU",
            "mitigation": g("R01", "mitigation") + f"; план FINAL_MIT_R01; стоимость ΔPV {g('R01','mitigation_cost_pv_mln')} млн",
            "residual_consequence": f"остаток Δshort {g('R01','residual_d_shortage_t')} т, новых нарушений {g('R01','residual_new_violations')}; остаточная стоимость {g('R01','residual_d_pv_mln')} млн PV",
        },
        {
            "risk_id": "R02",
            "event": "Ввод ISRU сдвигается на 2039 (доступность D 2038-01→2039-01)",
            "cause": "Задержка пусконаладки",
            "affected_parameter": "commissioning_override D + actual_delivery_share D 2038: 0.0",
            "period": "2038",
            "probability_basis_or_range": "сценарный подход: тяжесть без частоты; задержка 12 мес — условная граница (В3)",
            "physical_consequence": f"недопоставка всего плана D 2038 ≈ {f['d38_base']:.1f} т; суммарный дефицит {g('R02','d_shortage_t')} т (запас смягчает первые месяцы, SL 2038 = 0.9474)",
            "financial_consequence": f"ΔPV {g('R02','d_pv_mln')} млн (переменные платежи D не возникают; CAPEX ISRU 1250 сохранён)",
            "service_consequence": f"{g('R02','new_violations')} новых нарушений: BASE_TOTAL_SERVICE (2038), LEAD_TIME_VIOLATION (заказы D 2037–2038 недоступного канала), RESERVE_45D (2039–2040)",
            "dependencies": "отдельно от обязательного стресса; возможна замена B (headroom 110 т/год, lead 4 мес)",
            "owner": "Оператор ISRU",
            "mitigation": g("R02", "mitigation") + f"; план FINAL_MIT_R02; стоимость ΔPV {g('R02','mitigation_cost_pv_mln')} млн",
            "residual_consequence": f"остаток Δshort {g('R02','residual_d_shortage_t')} т, новых нарушений {g('R02','residual_new_violations')} (перезаказ устраняет и LEAD_TIME_VIOLATION); ΔPV {g('R02','residual_d_pv_mln')} млн",
        },
        {
            "risk_id": "R03",
            "event": "Отказ ZBO-криокулера: потери режима ZBO 1.2%→4.5% в 2038",
            "cause": "Отказ теплоотвода",
            "affected_parameter": "storage_loss_override ZBO 2038-01…2038-12: 0.012→0.045",
            "period": "2038",
            "probability_basis_or_range": "сценарный подход: тяжесть без частоты; длительность 12 мес — условная граница",
            "physical_consequence": f"доп. потери 0.033×throughput_2038 ≈ {0.033*f['thr38']:.1f} т; дефицит 0.0 т — запас FINAL_BASE (буфер TD-01) поглощает потери",
            "financial_consequence": f"ΔPV {g('R03','d_pv_mln')} млн (потери не оплачиваются)",
            "service_consequence": f"новых нарушений {g('R03','new_violations')} (SL=1.000; резерв 45 дн. на 2039-01: 40.5 ≥ 39.5 — впритык, но соблюдён)",
            "dependencies": "поверх BASE; потолок 2% потерь проверяется только в combined-тесте с mandatory",
            "owner": "Оператор депо",
            "mitigation": g("R03", "mitigation"),
            "residual_consequence": f"остаток = последствию: 0.0 т дефицита, 0 нарушений; запас прочности резерва мал (+1.0 т) — мониторинг обязателен",
        },
        {
            "risk_id": "R04",
            "event": "MMOD-пробой ёмкости: разовое списание 25% запаса (интервал 10–50%)",
            "cause": "Орбитальный микрометеороид/мусор",
            "affected_parameter": "inventory_shock 2038-07: share 0.25 от I_start до поставок (интервал чувствительности 0.10/0.50 — D3.2, три сценарные точки без частоты)",
            "period": "2038-07",
            "probability_basis_or_range": "сценарный подход: тяжесть без частоты; интервал 10–50% сценарно (В7/D3.2), частоту не выдумывать",
            "physical_consequence": f"разовая потеря 0.25×I_start(2038-07) = {0.25*f['i07']:.2f} т (I_start = {f['i07']:.1f} т). Интервал 10–50% масштабирует линейно: {0.10*f['i07']:.1f}–{0.50*f['i07']:.1f} т. Дефицита нет (0.0 т), но при 25% и 50% запас ниже 45-дневного резерва на 2039-01/2040-01; при 10% нарушений нет",
            "financial_consequence": f"ΔPV {g('R04','d_pv_mln')} млн (потерянный объём уже оплачен — невозвратные закупки ≈ {0.25*f['i07']*6.2:.1f} млн по цене A 6.2)",
            "service_consequence": f"SL не меняется (1.000); 2 новых нарушения RESERVE_45D (2039, 2040) при доле 25%; INVENTORY_SHOCK_APPLIED — информационное событие (D8.3), не hard-нарушение",
            "dependencies": "поверх BASE; эффект зависит от текущего запаса (25% × I_start)",
            "owner": "Оператор депо",
            "mitigation": g("R04", "mitigation") + f"; план FINAL_MIT_R04; стоимость ΔPV {g('R04','mitigation_cost_pv_mln')} млн",
            "residual_consequence": f"остаток Δshort {g('R04','residual_d_shortage_t')} т, новых нарушений {g('R04','residual_new_violations')} (мера закрывает весь интервал 10–50%); ΔPV {g('R04','residual_d_pv_mln')} млн",
        },
        {
            "risk_id": "R05",
            "event": "Аварийная цена E выше тарифа (13.8→17.25 млн/т, +25%)",
            "cause": "Спот-волатильность рынка аварийных пусков",
            "affected_parameter": "variable_price_multiplier Emergency 2038–2039: 1.25 (однократное применение — D8.4: плоский price override удалён из YAML)",
            "period": "2038–2039",
            "probability_basis_or_range": "сценарный подход: тяжесть без частоты; условный +25%",
            "physical_consequence": "0 т (FINAL-план S10 не использует канал E — заказов/отборов нет; эффективная цена E 2038 = 17.25 подтверждена прогоном)",
            "financial_consequence": f"ΔPV {g('R05','d_pv_mln')} млн (нулевой прямой эффект); потенциальная формула 3.45×Q_pay,E при активации E",
            "service_consequence": "0 п.п.; косвенных нарушений нет",
            "dependencies": "поверх BASE; только при активации E (в FINAL E не активирован)",
            "owner": "Закупки",
            "mitigation": "не требуется для FINAL (E не используется); для планов с активным E — заблаговременный перенос объёмов на B/D",
            "residual_consequence": "0 (нулевой эффект)",
        },
        {
            "risk_id": "R06",
            "event": "Позднее исполнение опциона C (exercise +12 мес)",
            "cause": "Решение принято после контрольной даты",
            "affected_parameter": "plan_investment_shift EARTH_NEW/exercise_option +12 мес (копия плана)",
            "period": "2037–2039",
            "probability_basis_or_range": "сценарный подход: тяжесть без частоты; условный сдвиг 12 мес",
            "physical_consequence": "0 т для FINAL — в плане S10 нет инвестиции EARTH_NEW (адаптер D3.4 зафиксировал no-op в журнале). Для альтернатив с каналом C (S14/S18/S21) сдвиг exercise на 12 мес отодвигает доступность 130 т/год C за 2040 — риск содержателен, но вне FINAL-плана",
            "financial_consequence": f"ΔPV {g('R06','d_pv_mln')} млн для FINAL",
            "service_consequence": "0 п.п.; нарушений нет",
            "dependencies": "нужна пара планов; scenario YAML не меняет решение; lead time 24 мес (TA-02)",
            "owner": "Планирование",
            "mitigation": "не применима к FINAL (нет C); общий принцип — gate-решение не позднее 24 мес до потребности; для планов с C — exercise не позднее 2037-12 под поставку 2040",
            "residual_consequence": "0 для FINAL (нулевой эффект); для альтернатив с C — до 130 т/год неуспевшей мощности",
        },
        {
            "risk_id": "R07",
            "event": "Смета ISRU превышена на 15% (1250→1437.5 млн)",
            "cause": "Строительно-пусковые затраты",
            "affected_parameter": "investment_capex_override LUNAR_ISRU: 1250→1437.5 (D3.3: допустим через адаптер, каталог CASE_INPUT не меняется)",
            "period": "2036-06 (дата платежа плана)",
            "probability_basis_or_range": "сценарный подход: тяжесть без частоты; условный +15%",
            "physical_consequence": "0 т (финансовый шок)",
            "financial_consequence": f"+187.5 млн CAPEX; ΔPV {g('R07','d_pv_mln')} млн; CAPEX cum 2037 FINAL: {f['cum37']:.0f}→{f['cum37']+187.5:.1f} ≤ 1800 — лимит НЕ нарушен (headroom FINAL = {1800-f['cum37']-187.5:.1f} млн после шока; до шока {1800-f['cum37']:.0f} млн)",
            "service_consequence": f"{g('R07','new_violations')} нарушений. Для альтернатив с headroom 10 млн (S14/S18/S21, CAPEX 1790) этот же шок нарушает CAPEX_2037 (1977.5 > 1800) — связка с Q8 WP2/D3.3",
            "dependencies": "поверх BASE; чувствителен к прочим CAPEX до 2037",
            "owner": "Инвестиционный комитет",
            "mitigation": "не требуется для FINAL (лимит не нарушен, headroom 370 млн); для планов с headroom 10 млн — staged funding (S25) или перенос части платежа за 2037",
            "residual_consequence": f"{g('R07','residual_d_pv_mln')} млн PV при сохранении всех лимитов",
        },
        {
            "risk_id": "R08",
            "event": "Канал A теряет мощность в 2038 (190→152 т/год, −20%)",
            "cause": "Ограничение производства или доступности провайдера A",
            "affected_parameter": "source_capacity_override A 2038: 190→152",
            "period": "2038",
            "physical_consequence": "срез поставок A 2038 на 38 т (заказы 190 → исполнение 152); дефицит 0.0 т — запас 40.2 т на 2038-01 и буфер TD-01 амортизируют срез, но резерв 45 дн. на 2039–2040 падает ниже нормы",
            "probability_basis_or_range": "сценарный подход: тяжесть без частоты; условное −20%",
            "financial_consequence": f"ΔPV {g('R08','d_pv_mln')} млн (срезанные объёмы не оплачиваются переменными, но резерв 190 т/год оплачен — переплата TOP A 0.70×190=133 ≤ 152 не возникает)",
            "service_consequence": f"{g('R08','new_violations')} новых нарушений: CAPACITY_EXCEEDED (помесячный отбор A 15.83 > лимит 12.67 т/мес при мощности 152, заказы 2037) + RESERVE_45D (2039–2040); SL не падает (1.000)",
            "dependencies": "поверх BASE; НЕ бонусный price event (R10) — шоки разделены",
            "owner": "Провайдер A",
            "mitigation": g("R08", "mitigation") + f"; план FINAL_MIT_R08; стоимость ΔPV {g('R08','mitigation_cost_pv_mln')} млн",
            "residual_consequence": f"остаток Δshort {g('R08','residual_d_shortage_t')} т, новых нарушений {g('R08','residual_new_violations')} (перезаказ закрывает и CAPACITY_EXCEEDED — заказы A уменьшены); ΔPV {g('R08','residual_d_pv_mln')} млн",
        },
        {
            "risk_id": "R09",
            "event": "Деградация MLI базового хранения (потери 4.5%→6% в 2036–2037)",
            "cause": "Тепловой режим до ввода ZBO",
            "affected_parameter": "storage_loss_override BASE 2036-01…2037-12: 0.045→0.06",
            "period": "2036–2037",
            "probability_basis_or_range": "сценарный подход: тяжесть без частоты; условные +1.5 п.п.",
            "physical_consequence": f"доп. потери 0.015×throughput_2036-37 ≈ {0.015*f['thr3637']:.1f} т; дефицит 0.0 т — запас поглощает",
            "financial_consequence": f"ΔPV {g('R09','d_pv_mln')} млн",
            "service_consequence": f"{g('R09','new_violations')} нарушений (I 2038-01 = 39.0 ≥ резерва 30.8)",
            "dependencies": "поверх BASE; только до ввода ZBO (с 2036-07 — режим ZBO)",
            "owner": "Оператор депо",
            "mitigation": g("R09", "mitigation"),
            "residual_consequence": f"остаток = последствию: 0.0 т, 0 нарушений; риск полностью поглощается запасом FINAL-плана",
        },
        {
            "risk_id": "R10",
            "event": "Геополитический тариф канала A (+20%: 6.2→7.44 млн/т в 2038–2039)",
            "cause": "Изменение условий поставки (условный бонусный сценарий, не прогноз)",
            "affected_parameter": "variable_price_multiplier Earth-Core 2038–2039: 1.2 (однократное применение — D8.4; экспорт geo_event.json)",
            "period": "2038–2039",
            "probability_basis_or_range": "сценарный подход: тяжесть без частоты; условный +20%",
            "physical_consequence": "0 т (тарифный шок; поставки не меняются)",
            "financial_consequence": f"ΔPV {g('R10','d_pv_mln')} млн; ΔTotalCost {p03['R10']['d_total_mln']} млн = Δцены 1.24 млн/т × Q_pay,A(2038-39) = 1.24×380 т (заказы A 190+190 > TOP 133); сторона провайдера A: +471.2 млн выручки (P05_parties.csv)",
            "service_consequence": f"0 п.п.; {g('R10','new_violations')} нарушений",
            "dependencies": "поверх BASE; НЕ совмещать автоматически с mandatory +25% — combined только отдельным сценарием TEAM_GEO_A_MANDATORY_COMBINED (6.2×1.25×1.20=9.30)",
            "owner": "Закупки",
            "mitigation": g("R10", "mitigation"),
            "residual_consequence": f"{g('R10','residual_d_pv_mln')} млн PV (полностью остаётся у заказчика при неизменном плане)",
        },
    ]

    cols = list(rows[0].keys())
    write_csv(os.path.join(RESULTS, "risk_register.csv"), cols, rows)

    # --- markdown-версия ---
    md = ["# Реестр рисков — результаты расчётов на ядре (WP3 волна 2, FINAL)", "",
          "Планы: **FINAL_BASE / FINAL_STRESS** (results/plans/, стратегия S10 «ISRU base», "
          "WP2 wave2-final-1.0). Контроль: BASE на FINAL_BASE (R01 — MANDATORY_STRESS "
          "на FINAL_STRESS). Последствия рассчитаны ядром (run_plan, ENGINE_VERSION "
          "0.3.0-wave3, ядро после D8), не порядки «на глаз». "
          "INVENTORY_SHOCK_APPLIED — информационное событие (D8.3).", "",
          "| ID | Событие | Δ физика | Δ финансы | Δ сервис | Мера (стоимость) | Остаток |",
          "|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append(
            f"| {r['risk_id']} | {r['event'][:60]} | {r['physical_consequence'][:70]} "
            f"| {r['financial_consequence'][:70]} | {r['service_consequence'][:60]} "
            f"| {r['mitigation'][:80]} | {r['residual_consequence'][:70]} |"
        )
    md += ["", "Полные поля (README §22): `results/risk_register.csv`.", "",
           "## Блок адаптации (триггеры, время реакции, стоимость, пределы)", ""]
    md.append(open(os.path.join(os.path.dirname(__file__), "adaptation_block.md"),
                   encoding="utf-8").read())
    with open(os.path.join(RESULTS, "risk_register.md"), "w", encoding="utf-8") as f_:
        f_.write("\n".join(md))

    write_json(os.path.join(OUT_STRESS, "P03_register_meta.json"), meta_block(
        "risk_register", f"{base_plan().plan_id}+{stress_plan().plan_id}",
        extra={"protocol": "P03/register",
               "note": "вероятности не назначаются: сценарный подход "
                       "(STRESS_PROTOCOL) — тяжесть без частоты"}))

    print("risk_register.csv/md записаны:", len(rows), "рисков (FINAL)")


if __name__ == "__main__":
    main()
