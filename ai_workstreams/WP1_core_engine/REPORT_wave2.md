# REPORT — WP1 волна 2: финансовый блок (finance.py, calculate_costs)

Исполнитель: WP1, ветка `wp1-core`. Дата: 2026-09-19.

## Что сделано

| Файл | Содержание |
|---|---|
| `src/engine/finance.py` | Полная реализация `calculate_costs(case, plan, deliveries, inventory) -> CostResult` по `financial_breakdown` result_format.json: переменные платежи с take-or-pay через max (единственный вход TOP, без второго платежа), резервные платежи с прората по start_month, хранение 0.72 × средний запас (TA-08), CAPEX по датам платежей (EARTH_NEW 90/270, LUNAR_ISRU 1250, ZBO 180) + `capex_cumulative_mln`, фиксированный OPEX (ZBO +12/год с месяца ввода по TA-05; ISRU +70/год с 2038 при финансировании ≤ 2037-12; прората первого года), дисконтирование PV = CF/(1.10)^(t−2035) (TA-06/TA-07), `cost_per_served_t_mln` (None при served = 0), оплата подготовительного заказа в год paid_in = 2035 (units §3). Вспомогательные функции `_ordered_by_year`, `_reserved_by_year`, `_capex_amount`, `_reservation_fraction`, `_isru_funded_before_2038`. |
| `src/engine/__init__.py` | `run_plan` подключает costs (единственное изменение —按计划 промпта «обновлённый run_plan»): `costs = calculate_costs(effective_case, ...)` и передача в RunResult вместо пустой заглушки. |
| `src/engine/models.py` | `FinancialRow.cost_per_served_t_mln: Optional[float] = None` (п.7 задания: при served = 0 — None, не 0.0; тип поля заготовки волны 1 уточнён). `ENGINE_VERSION = "0.2.0-wave2"`. |
| `tests/test_engine_wave2.py` | 27 тестов (V03/V04/V05, ручной пример A-канала, прората, дисконтирование, CAPEX-профиль, OPEX-прората, STRESS ×1.25, подготовительный заказ, cost_per_served, ошибки ввода). |
| `requirements.txt` | `jsonschema>=4.0,<5` в секцию «инструменты/тесты» — выполнение решения D1.3 (в ядро не добавлено; используется инструментом WP3 validate_team_scenarios.py). |

Код волны 1 НЕ переписывался; багфиксов волны 1 не потребовалось.

## Результаты pytest

```
python -m pytest tests/ -q
53 passed, 1 warning in 0.14s
```

26 тестов волны 1 + 27 новых тестов волны 2. (Warning — DeprecationWarning плагина pytest_asyncio из глобального окружения, к ядру отношения не имеет, как и в волне 1.)

## Контрольные примеры: вход → ожидание → факт

### Критерий приёмки 2 — векторы expected_checks.json

| Вектор | Вход | Ожидание | Факт (тест) |
|---|---|---|---|
| V03 | reserved 100 т/год A (TOP 0.70), заказ 50 т, цена 2 млн/т, тариф резерва 0 | Q_pay = max(50, 70) = 70 → 140 млн | procurement = 140.0 ✓ (`test_v03_take_or_pay_minimum`) |
| V04 | те же входы | платёж 140, второго TOP-платежа нет | procurement = 140.0, total = 140.0, take_or_pay_extra = 40.0 (справочно) ✓ (`test_v04_no_double_take_or_pay`) |
| V05 | reserved 100 т/год B, rate 0.4, start_month = 7 (доля 0.5) | 100 × 0.4 × 0.5 = 20 млн | reservation = 20.0 ✓ (`test_v05_reservation_prorata`) |

### Критерий приёмки 3 — ручной пример годового платежа канала A

Вход: резерв A = 190 т/год (2035), годовой заказ A = 150 т, TOP 70%, цена 6.2 млн/т, тариф резервирования 0.45.

| Величина | Ожидание (ручной расчёт) | Факт (код) |
|---|---|---|
| TOP-минимум | 0.70 × 190 = 133 т | — |
| Q_pay | max(150, 133) = 150 т | — |
| Переменный платёж | 150 × 6.2 = **930.0** млн | 930.0 ✓ |
| Резервирование | 190 × 0.45 = **85.5** млн | 85.5 ✓ |
| take_or_pay_extra (справочно) | 0 (заказ выше минимума) | 0.0 ✓ |

Тест `test_manual_example_channel_a`; продублировано прямым прогоном `calculate_costs` на реальных data/: procurement 930.0, reservation 85.5, total 1015.5.

### Прочие контрольные примеры

| Вход | Ожидание | Факт (тест) |
|---|---|---|
| Заказ A 10 т одним месяцем, резерв 190 т/год | Q_pay = max(10, 133) = 133 → 133×6.2 = 824.6 (годовой контроль TOP, не помесячный) | 824.6 ✓ (`test_top_period_is_calendar_year`) |
| Резерв C 100 т/год в 2036 и 2037, exercise 2035-06 → ввод C с 2037 | 2036: TOP-минимума нет (procurement 0, резерв 30); 2037: TOP 0.5×100 = 50 т → 355 | ✓ (`test_top_c_only_after_commissioning`) |
| EARTH_NEW: buy 2035-03 (90) + exercise 2036-06 (270) | capex 2035 = 90, 2036 = 270, сумма 360, третьего платежа нет; cumulative 2036 = 360 | ✓ (`test_capex_earth_new_profile`) |
| ZBO fund_capex 2036-05 (ввод 2036-06, TA-05) | OPEX 2036 = 12×7/12 = 7.0, с 2037 = 12.0 | ✓ (`test_fixed_opex_zbo_prorata_midyear`) |
| ZBO fund_capex 2036-01 (ввод 2036-02) | OPEX 2036 = 11.0 | ✓ (`test_fixed_opex_zbo_january_payment`) |
| LUNAR_ISRU fund_capex 2037-06 | OPEX +70/год в 2038–2040, в 2037 = 0; capex 1250 в 2037 | ✓ (`test_fixed_opex_isru_from_2038`) |
| Начальный запас 12 т весь горизонт | holding = 0.72 × 12 = 8.64/год | ✓ (`test_holding_cost_constant_inventory`) |
| Запас 24 т, спрос 24 т/год (2 т/мес), падение 24→0 | Σ (I_start+I_end)/2 / 12 = 12 → holding 2035 = 8.64 | ✓ (`test_holding_cost_average_of_monthly_means`) |
| CAPEX 1250 в 2037 | PV = 1250/1.1² = 1033.06 | ✓ (`test_discounting_manual_example`) |
| ZBO 2038-01 | CF2038 = 180 + 11 = 191 → PV = 191/1.1³ = 143.50 | ✓ (`test_discount_factor_by_year`) |
| MANDATORY_STRESS: A/B 100+50 т в 2038/2039/2040 | 2038–2039: 100×6.2×1.25 + 50×8.9×1.25 = 1331.25; 2040: ×1.0 = 1065.0; тарифы резерва и CAPEX шоком не меняются | ✓ (`test_stress_price_multiplier_only_ab_2038_2039`, `test_stress_does_not_change_reservation_rates`) |
| Начальный запас 65 т подготовительным заказом у A, paid_in 2035 | платёж 65×6.2 = 403.0 в 2035, в прочих годах 0; при резерве A 100 — Q_order = 65 входит в max(65, 70) = 70 → 434.0 (один раз) | ✓ (`test_initial_inventory_paid_in_2035`, `test_initial_inventory_counts_into_top_max`) |
| served = 0 в году | cost_per_served_t_mln = None | ✓ (`test_cost_per_served_and_none_on_zero`) |
| Платёж CAPEX 2041-06 / дата «2036» | исключение с русским сообщением, называющим дату | ✓ (`test_capex_payment_date_out_of_horizon_raises_russian`, `test_capex_malformed_payment_date_raises_russian`) |

### Критерий приёмки 4 — нет двойного счёта TOP

`grep -n "top" src/engine/finance.py`: TOP входит только в `max()` —
`q_pay = max(q_order, top_min)` (finance.py:308), платёж `procurement += price * q_pay` (:309).
Единственное прочее использование — справочная метрика `top_extra += price * max(0.0, top_min - q_order)` (:311), которая в `total_mln` НЕ входит (total = capex + procurement + reservation + holding + fixed_opex, :327). Второго платежа нет (V04 подтверждён: total = 140 = procurement при нулевых прочих компонентах).

## Изменения в коде волны 1

Багфиксы не потребовались. Служебные правки (в рамках задания «обновлённый run_plan»):
1. `__init__.py` — `run_plan` вызывает `calculate_costs` и передаёт результат в `RunResult.costs` (была заглушка `CostResult()`); обновлён docstring.
2. `models.py` — тип `FinancialRow.cost_per_served_t_mln` изменён с `float = 0.0` на `Optional[float] = None` (п.7 задания: при served = 0 — None; 0.0 искажал бы смысл). `ENGINE_VERSION` поднят до `0.2.0-wave2`.

Расчётные модули волны 1 (loader, validator, scenario, deliveries, inventory) не изменялись.

## Принятые трактовки (в рамках замороженных контрактов)

1. **Q_order года** = фактически принятый к исполнению отбор заказов года (логика deliveries.py): заказ недоступного канала (LEAD_TIME_VIOLATION) и излишек сверх месячной доли резерва (CAPACITY_EXCEEDED) физически не отбираются и не оплачиваются. Годовой заказ ('YYYY') распределяется равномерно по 12 месяцам, прората резерва (start_month) учитывается в месячном лимите — идентично deliveries.py.
2. **Заказы с поставкой за горизонт** (M+L > 2040-12) относятся к Q_order года размещения и оплачиваются (обязательство принято; объём в баланс не попадает — решение 3 волны 1). Консервативная трактовка, подтверждение — вопрос 2 ниже.
3. **TOP_share канала до года доступности = 0** (C: 0.50 только начиная с года ввода = exercise + 24 мес, TA-02). Значения — из supply_sources.csv, жёстко не зашиты.
4. **Подготовительный заказ**: объём initial_inventory_source добавляется к Q_order канала в год paid_in (2035) и оплачивается через общий механизм max() — ровно один раз (двойного счёта нет: initial_inventory_t в баланс поставки не дублируется, units §3).
5. **CAPEX**: сумма берётся из investment_options.csv по действию (buy_option → option_fee 90; exercise_option → exercise_cost 270; fund_capex → total_capex: LUNAR_ISRU 1250, ZBO 180) — 90+270 = 360, третьего платежа нет (§12). Год = год payment_date; даты до 2035-01 относятся на 2035 (units §3). Дата вне горизонта — исключение на русском.
6. **Ставка хранения** — holding_cost_mln_per_t_year из storage_options (0.72, одинакова для BASE и ZBO); **OPEX ZBO/ISRU** — fixed_opex_mln_per_year из investment_options.csv (12 и 70).
7. **Резервирование Emergency** оплачивается по общему правилу (тариф 0.35 канала E) — «контракт предусматривает резервирование» (units §7).
8. **Дисконтирование** — конец года: все потоки года суммируются в total_mln и делятся на (1.10)^(year − 2035) (TA-06/TA-07).

## Сверка с ручным расчётом WP2 волны 1 (reference_values.json, S10)

Прогон ядра на планах WP2 (`plans/S10.json` + BASE, `plans/S10_STRESS.json` + MANDATORY_STRESS):

| Показатель | Ядро (w2) | WP2 ref | Комментарий |
|---|---|---|---|
| procurement 2040, BASE | 1714.11 | 1714.11 | ✓ полное совпадение |
| procurement 2040, STRESS (S10_STRESS) | 1777.27 | 1777.27 | ✓ (цена ×1.25 совпадает) |
| reservation 2040 | 102.0 | 102.0 | ✓ |
| fixed_opex 2040 | 82.0 | 82.0 | ✓ |
| capex_cum 2037 | 1430.0 | 1430.0 | ✓ |
| total_cost BASE | 11674.93 | 12399.28 | расхождение ≈ −5.8% |
| total_cost STRESS | 13789.61 | 14510.85 | расхождение ≈ −5.0% |
| served 2040, STRESS | 425.74 | 448.5 | физический контур |
| holding 2040 | 1.26–6.19 | 29.58–39.38 | следствие траектории запаса |

**Финансовые формулы совпадают полностью** (все денежные компоненты, кроме holding, и цена STRESS — вплоть до копеек). Расхождение итогов даёт НЕ финансовый блок, а физический контур волны 1: ядро ограничивает месячный отбор строго reserved/12 года ЗАКАЗА (S10: заказ A 11.667 т/мес при резерве 100 т/год → CAPACITY_EXCEEDED, поставка урезана до 8.33 т/мес, 37–51 нарушение на план), тогда как модель WP2 бронирует объём по ёмкости года ПОСТАВКИ (arrival-year room). Отсюда меньше delivered → меньше запас → меньше holding, меньше served. Это расхождение > 0.5% — по D2.2 оно найдено в конвенциях (лимит отбора: месяц заказа vs месяц/год поставки) и выносится оркестратору (вопрос 1), а не «чинится» молча в одной из сторон.

## Вопросы оркестратору

1. **Семантика месячного лимита отбора (CAPACITY_EXCEEDED)**: deliveries.py волны 1 ограничивает заказ месяца долей reserved/12 года ЗАКАЗА; модель WP2w1 — ёмкостью года ПОСТАВКИ (lead time A = 12 мес сдвигает год). На финансовых итогах S10 это −5…−6%. Требуется единая трактовка до WP2w2/WP3w2 (сверка будет бессмысленна при разных конвенциях). Финансовый блок ядра следует трактовке волны 1 (оплачивается только фактически принятый отбор); при смене решения правка потребуется в deliveries.py + `_ordered_by_year` (обе — WP1 волна 3).
2. **Оплата заказов с поставкой за горизонтом**: заказ 2040 года у A поставляется в 2041 (вне модели). Сейчас оплачивается в году размещения (обязательство принято). Подтвердить или изменить на «не оплачивается» (влияние только на 2040 год).
3. **cost_per_served_t_mln = None при served = 0**: для экспорта (волна 3, export.schema.json организатора) None сериализуется в null/пустую ячейку — подтвердить приемлемость, либо оговорить значение-заполнитель.
4. **Дубликаты (source_id, year) в capacity_reservations** сворачиваются как max/минимум start_month (конвенция волны 1). Для финансов это же значит, что резерв оплачивается один раз по суммарной мощности max — подтвердить (альтернатива: суммировать дубликаты как отдельные лоты).

## Передать следующей волне (WP1 волна 3)

- `CostResult.financial_breakdown` готов для `check_constraints`: `capex_cumulative_mln` (лимиты 1800/2800 — CAPEX_2037/CAPEX_2040), `total_mln`, `discounted_mln` (NPV-сравнение), `cost_per_served_t_mln` (None допустим!).
- `export_results`: financial_breakdown сериализуется напрямую по result_format.json; `take_or_pay_extra_mln` — справочная колонка (не платёж).
- Для полного списка проверок passed=true/false (D4.2) финансовые поля уже агрегированы по годам.
- Адаптер `scenario_parameters` (D3.4) — финансовый блок читает только effective-поля `case`, override параметров CASE_INPUT-копии подхватится автоматически.
- `_ordered_by_year` (finance.py) дублирует логику лимитов deliveries.py — при изменении семантики лимита отбора (вопрос 1) править ОБА места синхронно.

## Git

Коммит `wp1: финансы ...` в ветку `wp1-core`, push выполнен. Файлы волны: `src/engine/finance.py`, `src/engine/models.py` (2 служебные правки), `src/engine/__init__.py` (подключение costs), `tests/test_engine_wave2.py`, `requirements.txt` (+jsonschema в секцию инструментов по D1.3), настоящий отчёт. CASE_INPUT (`data/**`, `configs/*.yaml`, `docs/CALCULATION_RULES.md`), контракты `00_contracts/**`, чужие WP-папки — не изменялись.
