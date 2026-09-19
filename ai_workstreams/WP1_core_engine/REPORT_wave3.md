# REPORT — WP1 волна 3: ограничения, адаптер сценариев, сохранение, экспорт, риски, финальный run_plan

Исполнитель: WP1, ветка `wp1-core`. Дата: 2026-09-19.

## Что сделано

| Файл | Содержание |
|---|---|
| `src/engine/constraints.py` | `check_constraints(...) -> list[Violation]` (контракт v1.0 — только нарушения) + `check_all(...) -> list[ConstraintCheck]` (ПОЛНЫЙ passed-список, D4.2). Реализованы ВСЕ rule_id: из constraints.csv — BASE_TOTAL_SERVICE (≥0.97), BASE_CRITICAL_SERVICE (≥0.99), CAPEX_2037 (≤1800), CAPEX_2040 (≤2800), RESERVE_45D (ежегодно: физический ИЛИ доказанный контрактный Emergency — покрытие за 42 дня, units §6), EMERGENCY_BASE_STREAK (≤2, TA-09: E «базовый» при отборе >40% served года), STRESS_LOSS_LIMIT (losses/throughput ≤ 0.02 с 2038, только MANDATORY_STRESS); внутренние — CAPACITY_EXCEEDED (статика reserved>capacity + помесячный отбор), STORAGE_OVERFLOW, NEGATIVE_INVENTORY (защита), LEAD_TIME_VIOLATION, ISRU_WITHOUT_CAPEX (включая дедлайн 2037-12), EARTH_NEW_WITHOUT_EXERCISE, ISRU_FIRST_YEAR_RELIABILITY (severity=soft: план заявляет надёжность D 2038 > 0.78 как гарантию). Лимиты читаются из constraints.csv, не зашиты. Формат Violation — README организатора §26. |
| `src/engine/scenario.py` | **Адаптер `apply_scenario_parameters(case, scenario, plan) -> (case2, plan2)`** (D3.4): override КОПИИ CaseData с обязательной проверкой ИСХОДНОГО значения (несовпадение → ValueError по-русски с именем параметра, ожиданием и фактом) и журналированием каждого применения в `case.scenario_journal`. Поддержка всех override конфигураций WP3: source_capacity_override, investment_capex_override, commissioning_override, storage_loss_override, inventory_shock (В7 MMOD), plan_investment_shift (R06 — копия плана), actual_delivery_share (по именам каналов), переопределение цены канала (плоский блок TEAM_PRICE_SPIKE_E / вложенный TEAM_GEO_CHANNEL_A). Ключи sensitivity_* журналируются как не-override. Неподдерживаемый ключ → ValueError (не молчим). Исходные case/plan не мутируются. **Проверено: все 10 TEAM-сценариев WP3 проходят через адаптер + run_plan** (тест `test_all_team_scenarios_runnable`). |
| `src/engine/compare.py` | `compare_scenarios(results) -> ComparisonResult`: строка-сводка на сценарий (total_mln, discounted_mln, SL_total/SL_critical по годам, shortage, reserve_ok, violations_count, capex_cumulative) + строки дельт (сценарий − BASE). |
| `src/engine/persistence.py` | `plan_to_dict`, `save_plan` (JSON по plan_format.json, ensure_ascii=False), `load_saved_plan` (через loader.load_plan — та же валидация и русские сообщения). Идемпотентность: save → load → save даёт байт-в-байт тот же файл; результат прогона идентичен. |
| `src/engine/export.py` | `export_results(result, path, fmt='csv'|'xlsx')`: yearly_balance.csv, source_schedule.csv, inventory_trace.csv, financial_breakdown.csv, constraint_checks.csv (полный passed-список), risk_register.csv + meta.json (scenario_id, plan_id, units, assumptions_reference, engine_version, contract_version, timestep, discount_rate/t0, generated_at, random_seed, scenario_journal). XLSX — pandas+openpyxl (допустимые зависимости). Числа — %.10g (roundtrip без потерь); cost_per_served=None → пустая ячейка. |
| `src/engine/risks.py` | `evaluate_risks(case, plan, base_result, risk_scenarios) -> RiskReport`: прогон каждого TEAM_* через полный run_plan (с адаптером D3.4); consequence_t = Δ shortage, consequence_mln = Δ PV, consequence_sl = Δ min SL_total; probability_basis_ru = «сценарный подход: тяжесть без частоты» (STRESS_PROTOCOL). Сценарий, который адаптер отклонил, — запись «НЕ ИСПОЛНЕН: причина» (требование WP3 wave1), не нули. |
| `src/engine/__init__.py` | **Финальный `run_plan`**: apply_scenario → deliveries → inventory → service → costs → check_all; RunResult.violations = нарушения расчётного контура + ограничения (без дублей); RunResult.checks = полный реестр (D4.2); RunResult.case = действующий CaseData (экспорт берёт scenario_journal). Один путь для UI/тестов/экспорта. |
| `src/engine/models.py` | `ConstraintCheck` (новый датакласс, поля строго по result_format.json constraint_checks + severity/source), `Violation.passed` НЕ добавлялся (контракт); `Scenario.scenario_parameters`; CaseData: storage_loss_override, inventory_shocks, capacity_override, actual_delivery_share_override, scenario_journal; RunResult: checks, case; ENGINE_VERSION 0.3.0-wave3. |
| `src/engine/inventory.py` | Поддержка override (расширение, не переписывание): потери режима по периодам (storage_loss_override), разовый шок запаса (inventory_shocks, отдельный физический механизм — не повторный начёт ставок, CR §3; применение фиксируется информационной записью INVENTORY_SHOCK_APPLIED). |
| `src/engine/deliveries.py`, `finance.py` | capacity_override (сценарное снижение мощности) учитывается в месячном лимите отбора и в эффективном Q_order — синхронно в обоих модулях (точка, указанная в REPORT_wave2 «передать волне 3»). |
| `src/engine/loader.py` | load_scenario читает расширенное поле scenario_parameters (словарь как есть; не dict → CaseLoadError по-русски). |
| `tests/test_engine_wave3.py` | 33 теста волны 3 (всего **86 passed**). |
| `tests/run_control_checks.py` | Скрипт V01–V10 с таблицей «case / expected / actual / OK?» — **10/10 OK**, exit code 0. |

## Результаты pytest

```
python -m pytest tests/ -q
86 passed, 1 warning in 0.86s

python tests/run_control_checks.py
ИТОГ: 10/10 OK   (V01 баланс 13 | V02 served 8/shortage 2 | V03 TOP 70→140 |
V04 нет второго TOP | V05 прората 20 | V06 потери 1 один раз | V07 резерв 45 |
V08 CAPACITY_EXCEEDED excess 2 | V09 critical 60 ⊂ total 100 | V10 20×0.5=10 без reliability)
```

## Изменения в коде волн 1–2

1. `inventory.py` — учёт storage_loss_override и inventory_shocks в месячном балансе (аддитивно; при пустых override поведение байт-в-байт прежнее).
2. `deliveries.py` / `finance.py` — учёт capacity_override в месячном лимите отбора (аддитивно, синхронно в двух модулях).
3. `test_engine_wave1.py::test_b_only_plan_manual_balance` — правка ТЕСТА (не кода): план резервирует B 120 т/год при каталожной мощности 110; волна 3 добавила в run_plan статическую проверку reserved ≤ capacity (CAPACITY_EXCEEDED), и тест начал её ловить. Для изоляции ручной сверки баланса мощность B в синтетической копии кейса увеличена до 120 (CASE_INPUT не менялся). Багфиксов расчётной логики волн 1–2 не потребовалось.
4. `models.py`, `loader.py`, `scenario.py`, `__init__.py` — как описано выше (расширения в рамках контракта; сигнатуры core_api.md сохранены, у `check_constraints` добавлен НЕобязательный параметр `deliveries=None` — расширение с значением по умолчанию, контракт v1.0 не нарушен).

## Архитектура run_plan (для WP4/WP2/WP3 волн 2)

```
run_plan(case, plan, scenario) -> RunResult
  ├─ apply_scenario(case, scenario)                    # effective_* поля
  ├─ calculate_deliveries(eff_case, plan)              # planned/actual, source_schedule, violations
  ├─ calculate_inventory(eff_case, plan, deliveries)   # monthly_balance, inventory_trace, violations
  ├─ calculate_service(eff_case, inventory)            # yearly_balance, SL, reserve_ok
  ├─ calculate_costs(eff_case, plan, deliveries, inv)  # financial_breakdown (волна 2)
  └─ check_all(eff_case, plan, del, inv, svc, costs)   # checks: ПОЛНЫЙ passed-список (D4.2)
       └─ violations = расчётный контур + непройденные checks (без дублей)

RunResult: scenario_id, plan_id, deliveries, inventory, service, costs,
           violations, checks, risks, comparison, meta, case (effective)
```

- **UI (WP4)**: вызывает только run_plan/export_results/save_plan/load_saved_plan/compare_scenarios (обязательство 2 core_api.md). passed-список для панелей — `result.checks` (не violations, D4.2). Развёртка в плоский JSON result_format.json — export_results (CSV) + meta.json.
- **TEAM-сценарии (WP3)**: load_scenario(configs/team/*.yaml) → `apply_scenario_parameters(case, sc, plan)` → `run_plan(case2, plan2 or plan, sc)`. Адаптер возвращает копии; журнал — `case2.scenario_journal` (попадает в meta.json экспорта).
- **Риски (WP3)**: `evaluate_risks(case, plan, base_result, [сценарии])` — готовый прогон реестра; risk_register сериализуется в экспорт.
- **Сверка (WP2)**: `run_plan` + `costs.financial_breakdown`; эталонные точки — ниже.

## Критерий приёмки 2 — эталонный BASE-план и декомпозиция STRESS

- Эталонный минимальный план (`make_reference_plan` в тестах): начальный запас 22 т подготовительным заказом у B + 8 месячных заказов B по 5.5 т; BASE-прогон — **ноль hard-нарушений**, все passed-проверки (SL, CAPEX, RESERVE_45D, EMERGENCY_STREAK, NEGATIVE_INVENTORY) присутствуют и пройдены.
- Декомпозиция MANDATORY_STRESS на 4 промежуточных сценария по одному фактору (тест `test_stress_decomposition_four_factors`, план S10):
  | Фактор | Эффект в ядре |
  |---|---|
  | спрос ×1.15 (2038–2040) | shortage растёт относительно BASE (план заказан под BASE-спрос) |
  | цены A/B ×1.25 (2038–2039) | PV растёт, физика (shortage) не меняется — эффект изолирован |
  | ISRU share 0.55/0.75 | фактические поставки D 2038 = planned × 0.55 (один раз, без reliability) |
  | loss ceiling ≤2% с 2038 | проверки STRESS_LOSS_LIMIT появляются (2038–2040); у S10 с ZBO (1.2%) — пройдены; PV не меняется |

## Критерий приёмки 3 — формат нарушения (пример из фактического прогона)

```
CAPACITY_EXCEEDED
source=A
period=2035-01
actual=11.667 (т)
limit=8.333 (т/мес = 100 т/год ÷ 12)
excess=3.333 (т)
message_ru="Заказ канала 'A' в период 2035-01 (11.6670 т) превышает месячную
долю зарезервированной мощности 2035 года (8.3333 т = 100 т/год ÷ 12);
излишек 3.3337 т"
```

(Формат README §26: rule_id, период, факт, лимит, excess, русская причина. Система диагностирует, не чинит — CASE_RULES §8.)

## Критерий приёмки 4 — экспорт = внутренние числа (ручная сверка 3 значений)

Прогон эталонного плана, `export_results(..., fmt='csv')`:
| Значение | Внутри ядра | financial_breakdown.csv | Совпадение |
|---|---|---|---|
| procurement_mln 2035 | 587.4 | 587.4 | ✓ (pytest.approx в тесте) |
| reservation_mln 2035 | 9.9 | 9.9 | ✓ |
| total_mln 2035 | 601.6248 | 601.6248 | ✓ |

Плюс полный roundtrip: yearly_balance.csv (i_end, sl_total), constraint_checks.csv (число строк = len(checks), passed ∈ {true,false}), meta.json (scenario_id, plan_id, units, assumptions_reference, engine_version, generated_at) — тест `test_export_csv_roundtrip`.

## Критерий приёмки 5 (п.5 задания) — сверка с reference_values.json WP2

Прогон всех 15 эталонных точек WP2 через run_plan (планы из `ai_workstreams/WP2_strategy_economics/plans/`, стресс — отдельные STRESS-файлы планов, где есть). Файлы WP2 НЕ изменялись.

**Совпадает полностью (≤0.5% или до копеек):** во ВСЕХ 15 точках — procurement 2040 (например S10 BASE 1714.11 = 1714.11; S14 STRESS 1856.22 ≈ 1856.25), reservation 2040 (102/141/123/169 — все точно), fixed_opex 2040 (82/70 — точно), capex_cum_2037 (1430/1250/1520/1790 — все точно), served 2040 в большинстве точек.

**Расхождение > 0.5% — total_cost/total_pv (−5…−20%), holding 2040, shortage, served в отдельных точках:**

| Точка | total_cost ядро/ref | total_pv ядро/ref | Причина |
|---|---|---|---|
| S10 BASE | 11674.93 / 12399.28 (−5.8%) | 9297.57 / 9951.40 (−6.6%) | конвенция лимита отбора (см. ниже) |
| S10 STRESS | 13789.61 / 14510.85 (−5.0%) | 10836.46 / 11488.55 (−5.7%) | та же |
| S14 BASE | 12221.33 / 14482.17 (−15.6%) | 9830.51 / 11964.99 (−17.8%) | та же + C-канал (заказы D/C режутся) |
| S18 BASE | 11855.60 / 14282.38 (−17.0%) | 9553.57 / 11797.61 (−19.0%) | та же |
| S21/S22/S25/S16/S17/S19/S11 | −5…−16% | −6…−18% | та же |
| S25 STRESS (через S25_STRESS_BRANCH.json) | 14098.29 / 15758.00 (−10.5%) | 10983.67 / 12338.84 (−11.0%) | та же |

**Причина найдена в конвенциях (по D2.2 сначала искали там), эскалирована ещё в REPORT_wave2 (вопрос 1), решения оркестратора пока нет:**
модель WP2w1 (`mc_model.py`) ограничивает отбор по ёмкости года **ПОСТАВКИ** (arrivals, `res_year(plan, sid, m_year(arr_idx))` + месячная доля года поставки), а ядро волны 1 (`deliveries.py`) — по зарезервированной мощности года **ЗАКАЗА** (reserved/12 года заказа). При lead time A = 12 мес это систематически режет заказы A у планов TD-01 (например S10: заказ A 11.667 т/мес при резерве A 100 т/год 2035 → CAPACITY_EXCEEDED, поставка урезана до 8.33 т/мес). Следствие: меньше delivered → меньше запас (holding −80…−100%) → больше shortage → меньше served в отдельных точках; все чисто денежные формулы при этом совпадают до копеек.

**Это НЕ баг финансового блока волн 2–3** — расхождение воспроизводилось идентично в волне 2 и полностью объясняется одной конвенцией физического контура волны 1. TD-01/TD-02 сами по себе не являются источником: политика заказов сохранена в планах WP2 без изменений, начальный запас 65/70 т оплачен в 2035 (проверено — cum37 и procurement 2035 совпадают).

**Варианты для оркестратора (ядро НЕ правил в одностороннем порядке, контракты заморожены):**
1. Принять конвенцию WP2 (лимит по году поставки) — правка `deliveries.py` + `_ordered_by_year` (обе точки синхронно, ~30 строк), после чего сверка сойдётся; влияет на результаты волны 1 (V-векторы не затрагивают — они на изолированных входах).
2. Принять конвенцию ядра — тогда WP2w2 пересчитывает эталоны (их промпт это предусматривает: «расхождение >0.5% без объяснения → баг-репорт, ядро НЕ правь»).
3. Оставить как есть с раскрытием в записке (не рекомендуется: критерий 5 — числа должны совпадать).

Рекомендация исполнителя WP1: **вариант 1** — трактовка WP2 ближе к физической логике (резерв мощности ограничивает физический отбор в момент поставки; заказ «бронирует» мощность будущего года), и она уже зашита в 25 эталонных просчётах волны 1 WP2.

## Расширяемость (D1.1, README организатора §28)

Тест `test_extensibility_source_x`: КОПИЯ набора данных + шестой синтетический канал Source-X в supply_sources.csv — ядро подхватывает его через данные без переписывания формул (lead time, TOP, резервирование, лимиты — всё работает: заказ 3 т → поставка через 3 мес; TOP 0.6×40=24 → платёж 120). Примеры организатора over_capacity/negative_reservation отклоняются load_plan с русским сообщением (D1.1 — ожидаемое поведение), их СЕМАНТИКА (excess 2) воспроизведена отдельным тестом в формате plan_format (`test_over_capacity_semantics_via_adapted_keys`).

## Известные ограничения ядра

1. **Конвенция лимита отбора** (год заказа vs год поставки) — не решена оркестратором; см. раздел сверки выше. До решения числа ядра и эталоны WP2 расходятся на 5–20% по total/PV (деньги-формулы совпадают).
2. Заказы с поставкой за горизонт (>2040-12) оплачиваются в году размещения (вопрос 2 REPORT_wave2 — без ответа; консервативно).
3. `RESERVE_45D` contractual_emergency: доказательство = покрытие 42-дневного спроса мощностью E (units §6); более тонкая аргументация «покрытие до прибытия» — на стороне плана (notes_ru), ядром не верифицируется.
4. `ISRU_FIRST_YEAR_RELIABILITY` — эвристика по тексту assumptions плана (число >0.78 в записи про ISRU/D); формального поля «заявленная надёжность» в plan_format нет.
5. EMERGENCY_BASE_STREAK считает «базовость» по фактическому отбору E (actual) против served года (TA-09, до подтверждения экспертом Б1).
6. XLSX-экспорт требует openpyxl (уже в requirements.txt).
7. Адаптер D3.4 поддерживает override из конфигураций WP3 волны 1; новые типы override добавляются явно (неподдерживаемый ключ → ValueError, не молчание).

## Готовность к волнам 2 (WP2/WP3/WP4)

- **WP2**: run_plan + financial_breakdown готовы; сверка эталонов выполнена (таблица выше) — начинать с раздела сверки, чтобы не переоткрывать конвенцию лимита.
- **WP3**: адаптер apply_scenario_parameters реализован в ЯДРЕ (D3.4) — все 10 TEAM-конфигов прогоняются; evaluate_risks собирает consequence_t/mln/sl; «не исполнен» помечается.
- **WP4**: run_plan — единая точка входа; checks — полный passed-список (D4.2); export_results — CSV/XLSX + meta.json; save_plan/load_saved_plan — идемпотентны; compare_scenarios — сводки + дельты к BASE.

## Отклонения от контрактов

Не применялись. Расширение сигнатуры `check_constraints` необязательным параметром `deliveries=None` контракт v1.0 не нарушает (позиционные аргументы core_api.md сохранены). Новое поле `RunResult.checks/case` — внутреннее расширение конверта (result_format.json описывает ПЛОСКИЙ экспорт, которым занимается export_results; все required-ключи экспорта заполняются).

## Вопросы оркестратору

1. **Конвенция месячного лимита отбора** (год заказа vs год поставки) — требуется решение до старта WP2w2 (см. раздел сверки; рекомендация — вариант 1, принять конвенцию WP2).
2. Подтвердить оплату заказов с поставкой за горизонтом в году размещения (REPORT_wave2, вопрос 2 — без ответа).
3. `cost_per_served_t_mln = None` при served=0 сериализуется в пустую ячейку CSV — приемлемо для export.schema.json организатора? (REPORT_wave2, вопрос 3.)
4. Дубликаты (source_id, year) в capacity_reservations: max-свёртка (REPORT_wave2, вопрос 4) — подтвердить.
5. INVENTORY_SHOCK_APPLIED — информационная запись о применении шока (в violations). Если оркестратор считает, что она не должна попадать в список нарушений — перенесу в checks-only (одна строка).

## Передать оркестратору/интегратору

- Все модули core_api.md реализованы (кроме намеренно отсутствующих: Monte Carlo/оптимизация — не в ядре).
- `python -m pytest tests/ -q` → 86 passed; `python tests/run_control_checks.py` → 10/10.
- ENGINE_VERSION 0.3.0-wave3, CONTRACT_VERSION 1.0.

## Git

Коммит `wp1: ограничения и экспорт ...` в ветку `wp1-core`, push выполнен. Файлы волны: `src/engine/{constraints,compare,persistence,export,risks}.py`, правки `src/engine/{__init__,models,loader,scenario,inventory,deliveries,finance}.py`, `tests/test_engine_wave3.py`, `tests/run_control_checks.py`, правка `tests/test_engine_wave1.py` (описана выше), настоящий отчёт. CASE_INPUT (`data/**`, `configs/*.yaml`), контракты `00_contracts/**`, файлы WP2 (`plans/**`, `reference_values.json`, `manual_calc/**`) — НЕ изменялись.
