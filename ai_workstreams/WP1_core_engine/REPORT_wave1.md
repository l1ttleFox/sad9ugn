# REPORT — WP1 волна 1: расчётное ядро (загрузка, поставки, баланс)

Исполнитель: WP1, ветка `wp1-core`. Дата: 2026-09-19.

## Что сделано

Создан пакет `src/engine/` (контракт core_api.md v1.0):

| Файл | Содержание |
|---|---|
| `models.py` | Датаклассы: `CaseData`, `Scenario`, `Plan` (+`PlanDecisions`, `SupplyOrder`, `CapacityReservation`, `Investment`, `InventoryPolicy`, `InitialInventorySource`, `EmergencyContract`, `Assumption`), `Violation`, `DeliveriesResult`, `InventoryResult`, `ServiceResult`, `MonthBalance`, `YearBalance`, `SourceScheduleRow`, `InventoryTracePoint`, `RunResult`, `RunMeta`, а также заготовки `CostResult`/`RiskReport`/`ComparisonResult` под волну 2–3. Поля строго по result_format.json / plan_format.json. |
| `loader.py` | `load_case`, `load_scenario`, `load_plan`, `plan_from_dict`; исключение `CaseLoadError` — сообщения на русском с именем файла, строкой и параметром. |
| `validator.py` | `validate_case` (вложенность critical ≤ total, неотрицательность, enum-поля, горизонт, low ≤ base ≤ high, дубликаты, обязательный режим BASE) и `validate_plan` (reserved ≤ capacity, заказы C/D только при инвестиции, дедлайн LUNAR_ISRU ≤ 2037-12, периоды в горизонте, investment_id в каталоге, mismatch начального запаса). |
| `scenario.py` | `apply_scenario` — НОВЫЙ `CaseData` (deepcopy, исходный не мутируется): множители общего и критического спроса, цены по каналам и годам, `actual_delivery_share`, `loss_ceiling`. BASE — множители 1.0. |
| `deliveries.py` | `calculate_deliveries` — помесячно, lead times в исходных единицах + раскрытые конвенции (`lead_time_applied` в source_schedule): A=12 month, B=4 month, C=«18-24 month (policy: 24)» (TA-02), D=2 month (политика), E=6 week → следующий месяц (TA-03). Заказ M → поставка M+L (TA-04). Лимит отбора: заказ месяца ≤ reserved/12, иначе `CAPACITY_EXCEEDED` и поставка ограничивается лимитом. Доступность: A/B/E с available_from_year; C — через 24 мес после `exercise_option`; D — с 2038-01 при `fund_capex` LUNAR_ISRU ≤ 2037-12. BASE: delivered = planned; `actual_delivery_share` применяется ОДИН раз, reliability не используется. |
| `inventory.py` | `calculate_inventory` — помесячный баланс I_end = I_start + delivered − losses − served; потери = throughput × loss_rate действующего режима (один раз); аллокация — сначала критический спрос; I_end ≥ 0, shortage отдельно; проверка ёмкости каждый месяц (`STORAGE_OVERFLOW`). Смена режима по TA-05 (ZBO — месяц после платежа, не ранее 2036). `calculate_service` — SL_total/SL_critical по годам, yearly_balance с reserve_required_t = D_y×45/365 и reserve_ok (I_start января). |
| `finance.py`, `constraints.py`, `risks.py`, `compare.py`, `persistence.py`, `export.py` | Заглушки `raise NotImplementedError` (волны 2–3). |
| `__init__.py` | Экспорт API + `run_plan` (главная точка входа; в волне 1 costs/check_constraints не вызываются — заглушки, в RunResult включаются нарушения расчётного контура). |

Прочее:
- `tests/test_engine_wave1.py` — 26 тестов (контрольные векторы + интеграция).
- `requirements.txt` — python ≥3.12, pandas, pyyaml, pytest с диапазонами версий.
- `conftest.py` (корень) — sys.path для импорта `src.engine` + basetemp pytest внутри репозитория (на этой машине стандартный tmp на сетевом диске недоступен).
- `.gitignore` — добавлена строка `.pytest_tmp/` (единственное изменение вне своих файлов; служебное).

## Результаты pytest

```
python -m pytest tests/ -q
26 passed, 1 warning in 0.07s
```

(Warning — DeprecationWarning плагина pytest_asyncio из глобального окружения, к ядру отношения не имеет.)

## Покрытие контрольных векторов (tests/validation/expected_checks.json)

| Вектор | Ожидание | Тест |
|---|---|---|
| V01 | closing = 13 (10+30−2−25) | `test_v01_material_balance` |
| V02 | served=8, shortage=2, closing=0, не −2 | `test_v02_shortage_not_negative_inventory` |
| V06 | losses = 1 (20×0.05, один раз) | `test_v06_losses_once_on_throughput` |
| V07 | reserve = 45 (365×45/365) | `test_v07_reserve_45_days` |
| V08 | CAPACITY_EXCEEDED, excess 2 | `test_v08_capacity_exceeded` (статика) + `test_v08_monthly_oftake_capacity_exceeded` (помесячно) |
| V09 | total = 100 при critical = 60 | `test_v09_critical_nested_in_total` |
| V10-аналог | 10 × 0.55 = 5.5 без reliability 0.78 | `test_v10_analog_isru_share_without_reliability` (на канале D реальных данных) |

Дополнительно по заданию волны:
- lead time A: заказ 2035-01 → поставка 2036-01 (`test_lead_time_a_12_months`);
- Emergency 6 недель → следующий месяц (`test_lead_time_emergency_6_weeks_next_month`);
- смена режима хранения среди года (`test_zbo_switch_midyear`, `test_zbo_not_earlier_than_2036`);
- C: политика 24 мес + LEAD_TIME_VIOLATION до ввода (`test_lead_time_c_policy_24_months`, `test_channel_c_unavailable_before_exercise_plus_24`);
- D: дедлайн финансирования (`test_channel_d_requires_isru_financed_before_2038`);
- STORAGE_OVERFLOW (`test_storage_overflow_violation`);
- загрузка реальных data/*.csv и configs/*.yaml + apply_scenario (`test_load_real_case`, `test_load_real_scenarios_and_apply`);
- некорректные входы (`test_load_case_missing_file`, `test_load_invalid_plan_examples`, `test_load_malformed_scenario`).

## Критерий 3 — ручной расчёт (план только канал B, ровные заказы)

План: резерв B = 120 т/год на 2035; годовой заказ B = 120 т (распределяется равномерно, 10 т/мес); начальный запас 0; спрос 2035 — синтетические 60 т/год (5 т/мес); потери BASE 4,5%. Lead time B = 4 мес → поставки с 2035-05. Тест `test_b_only_plan_manual_balance`.

| Период | I_start | delivered | losses (4,5%) | served | I_end | Ручная проверка |
|---|---|---|---|---|---|---|
| 2035-01…04 | 0 | 0 | 0 | 0 (дефицит 5 т/мес) | 0 | поставок ещё нет (lead time 4 мес) |
| 2035-05 | 0 | 10 | 0.45 | 5 | 4.55 | 0+10−0.45−5=4.55 |
| 2035-06 | 4.55 | 10 | 0.45 | 5 | 9.10 | 4.55+10−0.45−5=9.10 |
| 2035-07 | 9.10 | 10 | 0.45 | 5 | 13.65 | 9.10+10−0.45−5=13.65 |

Итоги года в тесте: delivered = 80 (8 поставок × 10), served = 40 (8 × 5), SL_total = 40/60, reserve_required = 60×45/365 ≈ 7.397, reserve_ok = False (запас на 01.01 = 0). Совпадает с расчётом ядра.

## Критерий 4 — в BASE нет умножения на reliability

Поиск `reliability` по `src/`:

```
src/engine/scenario.py:9,18    — комментарии («reliability НЕ участвует», «НЕ умножаются на reliability»)
src/engine/models.py:68,392    — комментарии; :81 — поле данных reliability_profile (загрузка CASE_INPUT)
src/engine/loader.py:151       — чтение поля reliability_profile из CSV (как данные)
src/engine/deliveries.py:20-21,248 — комментарии («БЕЗ умножения на reliability»)
```

Ни одного арифметического использования `reliability_profile` в расчёте нет: фактическая поставка формируется как `planned × actual_delivery_share` (в BASE share = 1.0 → delivered = planned). Поле хранится исключительно как метаданные риск-блока WP3.

## Принятые решения (в рамках замороженных контрактов)

1. **CAPACITY_EXCEEDED при расчёте**: заказ сверх месячной доли резерва фиксируется как Violation, а поставка ограничивается лимитом (физический отбор сверх контрактной мощности невозможен). Нарушение показывается численно — соответствует CASE_RULES §8 («система не обязана чинить план, но обязана назвать причину, период и величину»).
2. **Годовой заказ** (`period='YYYY'`) распределяется равномерно по 12 месяцам — прямо по описанию поля в plan_format.json.
3. **Заказы за горизонтом** (поставка M+L > 2040-12) в баланс не попадают; финансовые последствия — волна 2.
4. **Критический спрос в стрессе**: min(critical×mult, total×mult) — критический никогда не превышает общий (FAQ «критический входит в общий»).
5. **variable_price_multiplier ищется по имени канала** (`Earth-Core` и т.д. — как в mandatory_stress.yaml), сопоставление через `SupplySource.name`.
6. **reserve_ok** считается по физическому запасу на начало января года; договорный Emergency-вариант (reserve_mode=contractual_emergency) — проверка в волне 3 (check_constraints).
7. **SL при нулевом спросе** = 1.0 (явная трактовка boundary case по CALCULATION_RULES §7, без division-by-zero).
8. **start_month резервирования**: месяцы до start_month в год резервирования имеют лимит 0 (прората); финансовые прората — волна 2.
9. **`RunResult`** хранит подструктуры (`deliveries`, `inventory`, `service`, `costs`, `violations`, `meta`) по core_api.md; развёртка в плоский JSON result_format.json (monthly_balance/yearly_balance/...) — задача `export_results` (волна 3).

## Отклонения от контрактов

Не применялись. Предложений по изменению контрактов нет.

## Вопросы оркестратору

1. **Файлы `tests/examples/invalid_plan_examples/over_capacity.json` и `negative_reservation.json`** используют ключ `reserved_capacity_t` и синтетический `source_id: Source-X`, что не соответствует замороженному plan_format.json (`reserved_capacity_t_per_year`, enum A–E). Наш `load_plan` на них бросает `CaseLoadError` с русским сообщением, называющим файл и отсутствующий параметр (это и проверяет тест). Требуется ли вместо этого поддерживать «расширенный» синтетический формат Source-X (FAQ про расширяемость) — или примеры организатора остаются как есть и обрабатываются на уровне отдельного теста расширяемости в волне 3? Контракты менять не предлагаю; фиксирую трактовку.
2. **rule_id статической проверки reserved > capacity**: в expected_checks.json (V08) ожидается `CAPACITY_EXCEEDED`; в result_format.json тот же id перечислен среди «внутренних» нарушений расчёта. Использован единый `CAPACITY_EXCEEDED` и для статики, и для помесячного отбора (с разным excess). Если волна 3 ожидает отдельный id для статики (например RESERVED_OVER_CAPACITY) — сообщите, переименуем в волну 3.
3. **`load_case` и «валидация по схемам data/schemas/»**: схемы организатора — JSON Schema; в core_api.md допустимые зависимости ядра — pandas + stdlib, поэтому валидация реализована программно (эквивалентные проверки в loader + `validate_case`), без библиотеки jsonschema. Если оркестратор хочет буквальную проверку схемами — нужна зависимость `jsonschema` в requirements (предложение, не применяю).

## Передать следующей волне (WP1 волна 2 — финансы)

- `calculate_deliveries` уже возвращает: `ordered_by_source_period` (заказы по месяцам), `reserved_by_source_year`, `planned/actual_by_source_period`, `source_schedule` (в т.ч. помесячный reserved с учётом start_month), `lead_time_applied` — достаточно для take-or-pay (годовой Q_order vs TOP_share×Q_reserved), резервирования с прората и variable payments по effective-ценам (`case.effective_price_mln_per_t`). Для прората резервирования в волне 2 читать `start_month` из `plan.decisions.capacity_reservations`.
- `case.effective_demand_*`, `actual_delivery_share`, `loss_ceiling` — после `apply_scenario`; в волне 2 брать effective-поля, не base.
- `InitialInventorySource.paid_in` — расходы подготовительных заказов отнести на 2035 (units §3).
- Holding: средний запас = среднее (I_start+I_end)/2 по месяцам (TA-08), ставка 0.72; fixed OPEX ZBO +12/год после ввода (месяц ввода = `zbo_start_index` из inventory.py), ISRU +70/год с 2038.
- `MonthBalance.storage_mode` позволит начислять ZBO OPEX с месяца ввода.

## Git

Коммит(ы) `wp1: ...` в ветку `wp1-core`, push выполнен. Файлы волны: `src/engine/**`, `tests/test_engine_wave1.py`, `requirements.txt`, `conftest.py`, `.gitignore` (+1 строка), настоящий отчёт. CASE_INPUT, контракты, configs, docs — не изменялись.
