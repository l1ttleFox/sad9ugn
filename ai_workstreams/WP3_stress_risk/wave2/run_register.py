"""Финальный risk_register: results/risk_register.csv (+ risk_register.md)
и блок адаптации (триггеры, время реакции по lead times).

Поля — README организатора §22 (risk_id, event, cause, affected_parameter,
period, probability_basis_or_range, physical_consequence,
financial_consequence, service_consequence, dependencies, owner,
mitigation, residual_consequence). Последствия РАССЧИТАНЫ ядром
(прогоны P03/P01/P05), probability_basis — сценарный диапазон без частоты
(STRESS_PROTOCOL, D3.2/D3.3).

Все значения — план S10 («до FINAL», FINAL-планы WP2 не опубликованы).
"""

from __future__ import annotations

import os

from wp3lib import (
    RESULTS,
    base_case,
    base_plan,
    base_scenario,
    meta_block,
    pv_of,
    run_plan,
    run_team,
    team_scenario,
    write_csv,
    write_json,
)

OUT_STRESS = os.path.join(RESULTS, "stress")


def mmod_lost_t() -> float:
    """Фактическая потеря запаса MMOD (25% I_start 2038-07) в тоннах."""
    case = base_case()
    plan = base_plan()
    r_base = run_plan(case, plan, base_scenario())
    i_start = next(
        m.i_start_t for m in r_base.inventory.monthly_balance if m.period == "2038-07"
    )
    return 0.25 * i_start


def isru_2038_planned() -> float:
    case = base_case()
    plan = base_plan()
    r = run_plan(case, plan, base_scenario())
    return sum(
        v for (s, p), v in r.deliveries.planned_by_source_period.items()
        if s == "D" and p.startswith("2038")
    )


def a_pay_2038_39() -> float:
    """Q_pay канала A 2038–2039 (для формулы R10)."""
    # A: заказы 190/год 2038-2039 (резерв 190, TOP 0.7×190=133 < 190)
    return 190.0 + 190.0


def main() -> None:
    mmod_t = mmod_lost_t()
    d38 = isru_2038_planned()

    rows = [
        {
            "risk_id": "R01",
            "event": "Поставка ISRU ниже обязательных 55% (0.55→0.40 в 2038)",
            "cause": "Проблемы добычи и переработки лунного ISRU",
            "affected_parameter": "actual_delivery_share D 2038: 0.55→0.40 (COMBINED с MANDATORY_STRESS — явный комбинированный сценарий TEAM_ISRU_UNDERDELIVERY_COMBINED)",
            "period": "2038",
            "probability_basis_or_range": "сценарный подход: тяжесть без частоты; условная доля 0.40 (интервал чувствительности, не вероятность)",
            "physical_consequence": f"недопоставка ≈ 0.15×{d38:.1f} = {0.15*d38:.1f} т; суммарный дефицит +7.8 т против MANDATORY_STRESS",
            "financial_consequence": "ΔPV ≈ +0.0 млн (против MANDATORY_STRESS: расходы не растут — поставки уже срезаны стрессом)",
            "service_consequence": "min SL_total −2.12 п.п. (2038: 0.7836→0.7624); новых нарушений нет (SL в 2038 уже ниже 0.97 из-за конвенции лимита отбора)",
            "dependencies": "только как явный combined с MANDATORY_STRESS; резерв B/E и запас",
            "owner": "Оператор ISRU",
            "mitigation": "+8 т заказов B на окно поставки 2038 (заказы 2037-09…2038-08, lead 4 мес); план S10_MIT_R01; стоимость ΔPV +64.2 млн",
            "residual_consequence": "остаток Δshort −0.1 т (дефицит закрыт), новых нарушений 0; остаточная стоимость +64.2 млн PV",
        },
        {
            "risk_id": "R02",
            "event": "Ввод ISRU сдвигается на 2039 (доступность D 2038-01→2039-01)",
            "cause": "Задержка пусконаладки",
            "affected_parameter": "commissioning_override D + actual_delivery_share D 2038: 0.0",
            "period": "2038",
            "probability_basis_or_range": "сценарный подход: тяжесть без частоты; задержка 12 мес — условная граница (В3)",
            "physical_consequence": f"недопоставка всего плана D 2038 ≈ {d38:.1f} т; суммарный дефицит +55.8 т",
            "financial_consequence": "ΔPV −154.8 млн (переменные платежи D не возникают; CAPEX ISRU 1250 сохранён)",
            "service_consequence": "13 новых нарушений: BASE_TOTAL_SERVICE (2038, SL 0.7836) и LEAD_TIME_VIOLATION (заказы D 2037 недоступного канала)",
            "dependencies": "отдельно от обязательного стресса; возможна замена B/C/E",
            "owner": "Оператор ISRU",
            "mitigation": "+53 т заказов B на окно 2038 (lead 4 мес); план S10_MIT_R02; стоимость ΔPV +367.8 млн",
            "residual_consequence": "остаток Δshort +3.9 т; 13 нарушений (LEAD_TIME_VIOLATION по заказам D неустранимы без переписывания заказов плана — фиксированный план сохраняет заказы недоступного канала); ΔPV +213.0 млн",
        },
        {
            "risk_id": "R03",
            "event": "Отказ ZBO-криокулера: потери режима ZBO 1.2%→4.5% в 2038",
            "cause": "Отказ теплоотвода",
            "affected_parameter": "storage_loss_override ZBO 2038-01…2038-12: 0.012→0.045",
            "period": "2038",
            "probability_basis_or_range": "сценарный подход: тяжесть без частоты; длительность 12 мес — условная граница",
            "physical_consequence": "доп. потери 0.033×throughput_2038 ≈ +8.2 т; суммарный дефицит +8.2 т",
            "financial_consequence": "ΔPV ≈ −0.1 млн (потери не оплачиваются; эффект на закупки через запас пренебрежим)",
            "service_consequence": "1 новое нарушение BASE_TOTAL_SERVICE 2038 (0.7777→0.7526)",
            "dependencies": "поверх BASE; потолок 2% потерь проверяется только в combined-тесте с mandatory",
            "owner": "Оператор депо",
            "mitigation": "+9 т заказов B на окно 2038 (lead 4 мес); план S10_MIT_R03; стоимость ΔPV +62.6 млн",
            "residual_consequence": "остаток Δshort −0.1 т, нарушений 0; ΔPV +62.4 млн",
        },
        {
            "risk_id": "R04",
            "event": "MMOD-пробой ёмкости: разовое списание 25% запаса (интервал 10–50%)",
            "cause": "Орбитальный микрометеороид/мусор",
            "affected_parameter": "inventory_shock 2038-07: share 0.25 от I_start до поставок (интервал чувствительности 0.1/0.5 — D3.2)",
            "period": "2038-07",
            "probability_basis_or_range": "сценарный подход: тяжесть без частоты; интервал 10–50% сценарно (В7/D3.2), частоту не выдумывать",
            "physical_consequence": f"разовая потеря 0.25×I_start(2038-07) = {mmod_t:.3f} т (запас ядра в 2038-07 ≈ {mmod_t/0.25:.2f} т при конвенции лимита отбора WP1w3; дефицит не возникает). Интервал 10–50% масштабирует потерю линейно: {0.10*mmod_t/0.25:.2f}–{0.50*mmod_t/0.25:.2f} т",
            "financial_consequence": f"ΔPV ≈ 0.0 млн (потерянный объём уже оплачен — невозвратные закупки ≈ {mmod_t*6.2:.2f} млн по цене A 6.2)",
            "service_consequence": "SL не меняется; фиксируется информационная запись INVENTORY_SHOCK_APPLIED (вопрос 5 WP1w3 оркестратору: перенести в checks-only)",
            "dependencies": "поверх BASE; эффект зависит от текущего запаса (25% × I_start)",
            "owner": "Оператор депо",
            "mitigation": "+1 т заказов B с поставкой 2038-08…2038-12 (ПОСЛЕ шока — дозаказ до шока увеличил бы списание); план S10_MIT_R04; стоимость ΔPV +7.7 млн",
            "residual_consequence": "остаток Δshort 0.0 т (шок не создаёт дефицита — мера-страховка для интервала 10–50%); ΔPV +7.7 млн",
        },
        {
            "risk_id": "R05",
            "event": "Аварийная цена E выше тарифа (13.8→17.25 млн/т, +25%)",
            "cause": "Спот-волатильность рынка аварийных пусков",
            "affected_parameter": "variable_price_multiplier Emergency 2038–2039: 1.25 (однократное применение — см. баг дублирования в REPORT_wave2)",
            "period": "2038–2039",
            "probability_basis_or_range": "сценарный подход: тяжесть без частоты; условный +25%",
            "physical_consequence": "0 т (план S10 не использует канал E — заказов/отборов нет)",
            "financial_consequence": "ΔPV +0.0 млн (нулевой прямой эффект); потенциальная формула 3.45×Q_pay,E при активации E",
            "service_consequence": "0 п.п.; косвенных нарушений нет",
            "dependencies": "поверх BASE; только при активации E (у S10 E не активирован)",
            "owner": "Закупки",
            "mitigation": "не требуется для S10; для планов с активным E — заблаговременный перенос объёмов на B/D",
            "residual_consequence": "0 (нулевой эффект)",
        },
        {
            "risk_id": "R06",
            "event": "Позднее исполнение опциона C (exercise +12 мес)",
            "cause": "Решение принято после контрольной даты",
            "affected_parameter": "plan_investment_shift EARTH_NEW/exercise_option +12 мес (копия плана)",
            "period": "2037–2039",
            "probability_basis_or_range": "сценарный подход: тяжесть без частоты; условный сдвиг 12 мес",
            "physical_consequence": "0 т для S10 — в плане нет инвестиции EARTH_NEW (адаптер D3.4: no-op, журнал сохранён); для планов с C — до min(130, Q_C) т неуспевшей мощности",
            "financial_consequence": "ΔPV +0.0 млн для S10",
            "service_consequence": "0 п.п.; нарушений нет",
            "dependencies": "нужна пара планов; scenario YAML не меняет решение; lead time 24 мес (TA-02)",
            "owner": "Планирование",
            "mitigation": "не применима к S10 (нет C); общий принцип — gate-решение не позднее 24 мес до потребности",
            "residual_consequence": "0 (нулевой эффект)",
        },
        {
            "risk_id": "R07",
            "event": "Смета ISRU превышена на 15% (1250→1437.5 млн)",
            "cause": "Строительно-пусковые затраты",
            "affected_parameter": "investment_capex_override LUNAR_ISRU: 1250→1437.5 (D3.3: допустим через адаптер, каталог CASE_INPUT не меняется)",
            "period": "2036-06 (дата платежа плана)",
            "probability_basis_or_range": "сценарный подход: тяжесть без частоты; условный +15%",
            "physical_consequence": "0 т (финансовый шок)",
            "financial_consequence": "+187.5 млн CAPEX; ΔPV +170.4 млн; CAPEX cum 2037: 1430→1617.5 ≤ 1800 — лимит НЕ нарушен (headroom 182.5 млн)",
            "service_consequence": "0 п.п.; нарушений нет. Для стратегий с headroom 10 млн (S14/S18/S21, CAPEX 1790) этот же шок нарушает CAPEX_2037 (1977.5 > 1800) — связка с Q8 WP2",
            "dependencies": "поверх BASE; чувствителен к прочим CAPEX до 2037",
            "owner": "Инвестиционный комитет",
            "mitigation": "не требуется для S10 (лимит не нарушен); для планов с headroom 10 млн — staged funding (S25) или перенос части платежа за 2037",
            "residual_consequence": "+170.4 млн PV при сохранении всех лимитов",
        },
        {
            "risk_id": "R08",
            "event": "Канал A теряет мощность в 2038 (190→152 т/год, −20%)",
            "cause": "Ограничение производства или доступности провайдера A",
            "affected_parameter": "source_capacity_override A 2038: 190→152",
            "period": "2038",
            "probability_basis_or_range": "сценарный подход: тяжесть без частоты; условное −20%",
            "physical_consequence": "срез поставок A 2038 на 29.0 т (заказы 190 → исполнение 152); суммарный дефицит +29.0 т",
            "financial_consequence": "ΔPV −184.6 млн (срезанные объёмы не оплачиваются; TOP A 0.70×190=133 < 152 — переплата TOP не возникает)",
            "service_consequence": "12 новых нарушений: CAPACITY_EXCEEDED (помесячный отбор A 15.83 > лимит 12.67 т/мес) и BASE_TOTAL_SERVICE 2038 (0.7777→0.6777)",
            "dependencies": "поверх BASE; НЕ бонусный price event (R10) — шоки разделены",
            "owner": "Провайдер A",
            "mitigation": "+38 т заказов B на окно 2038 (lead 4 мес, резерв B 110 — headroom 80 т/год); план S10_MIT_R08; стоимость ΔPV +287.5 млн",
            "residual_consequence": "остаток Δshort −1.4 т (дефицит закрыт); 11 нарушений — CAPACITY_EXCEEDED по исходным заказам A фиксированного плана неустранимы мерой по B; ΔPV +102.9 млн",
        },
        {
            "risk_id": "R09",
            "event": "Деградация MLI базового хранения (потери 4.5%→6% в 2036–2037)",
            "cause": "Тепловой режим до ввода ZBO",
            "affected_parameter": "storage_loss_override BASE 2036-01…2037-12: 0.045→0.06",
            "period": "2036–2037",
            "probability_basis_or_range": "сценарный подход: тяжесть без частоты; условные +1.5 п.п.",
            "physical_consequence": "доп. потери 0.015×throughput_2036-37 ≈ +0.9 т; суммарный дефицит +0.9 т",
            "financial_consequence": "ΔPV −0.4 млн",
            "service_consequence": "0 п.п.; новых нарушений нет (запас поглощает)",
            "dependencies": "поверх BASE; только до ввода ZBO (с 2036-07 — режим ZBO)",
            "owner": "Оператор депо",
            "mitigation": "+4.5 т заказов B (поставка 2036-05…2036-10, lead 4 мес); план S10_MIT_R09; стоимость ΔPV +37.3 млн",
            "residual_consequence": "остаток Δshort −3.5 т (мера с запасом), нарушений 0; ΔPV +36.9 млн. Для S10 мера экономически неоправданна: риск поглощается запасом",
        },
        {
            "risk_id": "R10",
            "event": "Геополитический тариф канала A (+20%: 6.2→7.44 млн/т в 2038–2039)",
            "cause": "Изменение условий поставки (условный бонусный сценарий, не прогноз)",
            "affected_parameter": "variable_price_multiplier Earth-Core 2038–2039: 1.2 (однократное применение — P05, экспорт geo_event.json)",
            "period": "2038–2039",
            "probability_basis_or_range": "сценарный подход: тяжесть без частоты; условный +20%",
            "physical_consequence": "0 т (тарифный шок; поставки не меняются)",
            "financial_consequence": f"ΔPV +337.9 млн; ΔTotalCost +471.2 млн = 1.24×Q_pay,A(2038-39) = 1.24×{a_pay_2038_39():.0f} т; сторона провайдера A: +471.2 млн выручки",
            "service_consequence": "0 п.п.; нарушений нет",
            "dependencies": "поверх BASE; НЕ совмещать автоматически с mandatory +25% — combined только отдельным сценарием TEAM_GEO_A_MANDATORY_COMBINED (6.2×1.25×1.20=9.30)",
            "owner": "Закупки",
            "mitigation": "физическая мера в рамках фиксированного плана не применима; управленческая — перенос объёмов 2038–2039 на B (headroom 80 т/год)/D ограничен TOP A=0.70 и лимитом B; в рамках S10 риск принимается",
            "residual_consequence": "+337.9 млн PV (полностью остаётся у заказчика при неизменном плане)",
        },
    ]

    cols = list(rows[0].keys())
    write_csv(os.path.join(RESULTS, "risk_register.csv"), cols, rows)

    # --- markdown-версия ---
    md = ["# Реестр рисков — результаты расчётов на ядре (WP3 волна 2)", "",
          f"План: **S10** ({os.path.basename('S10.json')}, «до FINAL» — FINAL-планы WP2 не опубликованы). "
          "Контроль: BASE (R01 — MANDATORY_STRESS). Последствия рассчитаны ядром "
          "(run_plan, ENGINE_VERSION 0.3.0-wave3), не порядки «на глаз».", "",
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
    with open(os.path.join(RESULTS, "risk_register.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md))

    write_json(os.path.join(OUT_STRESS, "P03_register_meta.json"), meta_block(
        "risk_register", "S10",
        extra={"protocol": "P03/register",
               "note": "вероятности не назначаются: сценарный подход "
                       "(STRESS_PROTOCOL) — тяжесть без частоты"}))

    print("risk_register.csv/md записаны:", len(rows), "рисков")


if __name__ == "__main__":
    main()
