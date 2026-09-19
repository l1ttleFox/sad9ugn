# Топливный космоконтур 2035 — решение кейса КосмоХакатон 2026

Decision-support система планирования снабжения орбитального топливного узла на 2035–2040 гг. Расчётное ядро (Python) считает баланс топлива, сервис, расходы (PV), нарушения ограничений и риски для любого плана оператора; рабочее место оператора (Streamlit) позволяет менять решения, сравнивать BASE и обязательный стресс, сохранять планы и выгружать CSV/XLSX. Финальная стратегия — **S10 «ISRU base»**: PV 9 961.31 млн у.е. (BASE) / 11 498.45 млн (MANDATORY_STRESS), SL = 1.000, дефицит 0 т, 0 hard-нарушений в обоих сценариях.

**Ключевые материалы:** [управленческая записка](docs/УПРАВЛЕНЧЕСКАЯ_ЗАПИСКА.md) · [резюме 1 стр. BASE vs STRESS](docs/note/RESUME_1page.md) · [презентация (12 слайдов)](presentation/presentation.md) · [реестр рисков](results/risk_register.md) · [инструкция оператору](docs/ИНСТРУКЦИЯ.md) · [источники](docs/ИСТОЧНИКИ.md)

## Состав репозитория

```
src/engine/        — расчётное ядро: загрузка данных, сценарии, поставки, баланс,
                     финансы (PV), ограничения, риски, сравнение, save/load, экспорт.
                     Единая точка входа — run_plan (её используют UI, экспорт и тесты)
app/               — рабочее место оператора (Streamlit): план, пересчёт, нарушения,
                     BASE↔STRESS, риски, геополитика, сохранение, экспорт CSV/XLSX
data/              — CASE_INPUT организатора (НЕ изменяется; контроль sha256): спрос,
                     каналы A–E, хранилища, инвестиции, ограничения + схемы JSON
configs/           — сценарии: base.yaml, mandatory_stress.yaml, team/*.yaml (10 TEAM_*)
tests/             — 118 автотестов: контрольные векторы V01–V10 (run_control_checks.py),
                     интеграционные волны 1–3, UI, стресс-протоколы; examples/ —
                     invalid_plan_examples организатора
results/           — сохранённые планы (plans/FINAL_BASE.json, FINAL_STRESS.json,
                     plans_adaptive/FINAL_MIT_*), экспорты (exports/FINAL_*/, top5_BASE/*),
                     скрининг 25 стратегий, MCDA, сверка ручного расчёта, стресс-протоколы
                     P01–P04 (stress/), геополитика P05 (geopolitics/), реестр рисков,
                     сравнение сценариев (scenario_comparison.md/.csv)
docs/              — управленческая записка (8–12 стр.), расширенные разделы note/00–12,
                     RESUME_1page.md, инструкция оператору, правила расчёта, ИСТОЧНИКИ.md,
                     материалы постановщика (ПОСТАНОВКА_КЕЙСА.txt, КРИТЕРИИ_ОЦЕНКИ.txt)
presentation/      — презентация ≤12 слайдов (Marp markdown + собранные PDF/HTML),
                     speaker_notes.md (тезисы спикера + трассировка чисел)
ai_workstreams/    — материалы разработки: контракты модулей, промпты и отчёты
                     параллельных work-packages WP1–WP6, независимый ручной расчёт WP2
```

## Зависимости и установка

- Python **3.12+** (проверено на 3.12, Windows); интернет для `pip install`.
- Установка:

```bash
git clone https://github.com/l1ttleFox/sad9ugn.git
cd sad9ugn
python -m venv .venv            # рекомендуется виртуальное окружение
# Windows: .venv\Scripts\activate   Linux/Mac: source .venv/bin/activate
python -m pip install -r requirements.txt
```

Версии зафиксированы в `requirements.txt`: streamlit 1.48.1, pandas 2.3.2, openpyxl 3.1.5, pyyaml 6.0.3, pytest 8.4.2, jsonschema 4.26.0.

## Запуск UI и тестов

```bash
python -m streamlit run app/main.py     # рабочее место оператора
python -m pytest tests/ -q              # 118 passed
python tests/run_control_checks.py      # контрольные векторы V01–V10: ИТОГ 10/10 OK
```

## Порядок проверки (как в кейсе: установка → стандартный сценарий → обязательный стресс → дополнительные тесты → сравнение и выгрузка)

### Шаг 0. Установка и запуск

1. Установить зависимости (см. выше): `python -m pip install -r requirements.txt`.
2. `python -m pytest tests/ -q` — **ожидаемо: 118 passed**.
3. `python tests/run_control_checks.py` — **ожидаемо: ИТОГ: 10/10 OK** (V01–V10: арифметика поставок, баланса, TOP-платежа, резерва, потерь, PV, capacity, вложенности критического спроса, стресс-доли без reliability).
4. `python -m streamlit run app/main.py` — в левой панели статус «Расчётное ядро доступно», период 2035–2040, кнопки демонстрационных планов.

### Шаг 1. Стандартный сценарий (BASE)

1. В UI слева: **«Загрузить FINAL BASE — FINAL_BASE»**.
2. На «Обзоре»/«Графиках» проверить ожидаемые числа (`results/exports/FINAL_BASE/`):
   - расходы: total **12 411.71 млн у.е.**, PV **9 961.31 млн** (r = 10%, t0 = 2035);
   - обслужено **1 390.0 т**, дефицит **0 т**, SL_total = SL_critical = **1.000** все годы;
   - CAPEX: **1 430 млн** в 2036-06 (ISRU 1 250 + ZBO 180),накопленный CAPEX ≤2037 = 1 430 ≤ 1 800 (headroom 370);
   - резерв 45 дн. на 01.01.2040: **57.60 ≥ 48.08 т**.
3. На «Ограничениях» — полный реестр проверок, все hard-правила «ВЫПОЛНЕНО», нарушений **0**.

### Шаг 2. Обязательный стресс-тест (MANDATORY_STRESS)

1. В UI слева: **«Загрузить FINAL STRESS — FINAL_STRESS»** (план откроется в согласованном сценарии MANDATORY_STRESS: спрос ×1.15 с 2038, цены A/B ×1.25 в 2038–2039, доли ISRU 0.55/0.75, потолок потерь ≤2%).
2. Ожидаемые числа (`results/exports/FINAL_STRESS/`): total **14 523.27 млн**, PV **11 498.45 млн** (+1 537.14, +15.4% к BASE); обслужено **1 534.0 т**; SL = **1.000**; дефицит **0**; нарушений **0**; потери **1.2% ≤ 2%**; резерв 45 дн. на 01.01.2040: **60.78 ≥ 55.29 т**.
3. Альтернатива без UI (тот же расчёт ядром; пример для bash — на Windows сохраните код между `PY` в файл `check_final.py` и выполните `python check_final.py` из корня репозитория):

```bash
python - <<'PY'
import sys; sys.path.insert(0, "src")
from engine import load_case, load_plan, load_scenario, run_plan
case = load_case("data")
for pid, cfg in (("FINAL_BASE","configs/base.yaml"), ("FINAL_STRESS","configs/mandatory_stress.yaml")):
    r = run_plan(case, load_plan(f"results/plans/{pid}.json"), load_scenario(cfg))
    pv = sum(x.discounted_mln for x in r.costs.financial_breakdown)
    print(pid, f"PV={pv:.2f}", f"violations={len(r.violations)}")
PY
```

   **Ожидаемо:** `FINAL_BASE PV=9961.31 violations=0`, `FINAL_STRESS PV=11498.45 violations=0`.

### Шаг 3. Дополнительные тесты

1. **Чувствительность low/high demand** (просчитана): `results/stress/P02_tornado.csv` — low ×0.8: 38 нарушений STORAGE_OVERFLOW (план «заточен» под базовый спрос); high (487.5 т в 2040): дефицит 225.4 т, SL 0.7999, 8 нарушений — честно зафиксировано, кросс-валидировано (`results/exports/sensitivity_demand_low_high.csv`).
2. **Стресс на неадаптированном плане** (`results/stress/P01_summary.csv`, строка MANDATORY_ON_FIXED_BASE): дефицит 130.7 т, SL 0.943/0.849/0.869, 5 нарушений — цена отсутствия адаптации.
3. **Командные риски R01–R10** (`results/risk_register.csv/.md`, `results/stress/P03_risks.csv`): последствия рассчитаны ядром; адаптивные планы мер — `results/plans_adaptive/FINAL_MIT_R01/R02/R04/R08.json` (остаток 0 т / 0 нарушений).
4. **Геополитический бонус** (`results/geopolitics/P05_summary.json`): тариф A +20% → +471.19 млн total / +337.92 млн PV, физика цела; восстановление цен — побайтово идентично BASE (`restoration.ok = true`). В UI: «Сценарии» → собственное событие → «Восстановить контрольные цены».
5. **Расширяемость (Source-X / 2041 год)** — на копии набора, CASE_INPUT не изменяется:

```bash
python -m pytest tests/test_engine_wave3.py -q -k extensibility
```

   Тест копирует `data/`, дописывает строку шестого канала Source-X в supply_sources.csv — ядро подхватывает его **через данные, без правки кода** (lead time, TOP, резервирование считаются по общим формулам). Продление горизонта на 2041: добавить строки 2041 в demand.csv копии и изменить одну константу `HORIZON_END_YEAR` (`src/engine/models.py:27`) — горизонт является параметром модели, а не данных; исходные лимиты CASE_INPUT на 2041 НЕ переносятся молча (требуется явное TEAM_ASSUMPTION-решение, см. `docs/FAQ.md` §«Можно ли прогнозировать 2041+?»).
6. **Невалидный ввод**: `tests/examples/invalid_plan_examples/` — UI и loader отклоняют с русским сообщением (параметр + период), без traceback.

### Шаг 4. Сравнение и выгрузка

1. В UI «Сценарии» → таблица сравнения BASE↔STRESS (функция ядра compare_scenarios на одном плане). Эталон: `results/scenario_comparison.md/.csv`.
2. Экспорт: кнопка **CSV** (ZIP: yearly_balance, source_schedule, inventory_trace, financial_breakdown, constraint_checks, risk_register, meta.json) или **XLSX** (те же таблицы). meta.json содержит scenario, единицы, assumptions_reference, engine_version, sha256 входов, random_seed=null.
3. Сверка: числа UI == числа экспорта == `results/exports/FINAL_*/` (тесты `tests/test_engine_wave3.py::test_export_csv_roundtrip`, `tests/test_ui_wave2.py`).
4. Повторное открытие: «Сохранение» → задать plan_id → сохранить → загрузить снова — план и договоры восстанавливаются.

## Где что лежит

| Что | Где |
|---|---|
| Входные данные (CASE_INPUT) | `data/*.csv` + `data/schemas/` (не изменяются; sha256-контроль в тестах) |
| Допущения команды (реестр TA-01…TA-10) | `docs/note/02_data_assumptions.md` |
| Расчётные модули и формулы | `src/engine/` (контракт `ai_workstreams/00_contracts/core_api.md`), правила `docs/CALCULATION_RULES.md` |
| Сохранённые планы | `results/plans/FINAL_BASE.json`, `FINAL_STRESS.json`; меры рисков — `results/plans_adaptive/` |
| Экспорты и сравнение | `results/exports/` (FINAL, top5, screening_25, mcda, reconciliation, sensitivity), `results/scenario_comparison.*` |
| Стресс-протоколы P01–P05 | `results/stress/`, `results/geopolitics/`; протоколы — `ai_workstreams/WP3_stress_risk/protocols/` |
| Реестр рисков | `results/risk_register.csv/.md`, `docs/note/11_risk_results.md` |
| Записка, презентация, источники | `docs/УПРАВЛЕНЧЕСКАЯ_ЗАПИСКА.md`, `presentation/`, `docs/ИСТОЧНИКИ.md` |

## Границы прототипа

Это decision-support прототип для планирования и анализа, **не** система управления реальным оборудованием: агрегированный ресурс в тоннах (без разделения LOX/LH2), детерминированный BASE, месячный шаг, учебные синтетические цены, «безвыручковая» экономика, Monte Carlo не применялся (сценарный/интервальный подход), горизонт 2035–2040 (2041+ — исследовательский). Полностью: `docs/note/07_limitations.md`.

## Команда / контакты

- Сычев Алексей
- Асанди Максим
- Юрийчук Михаил

---

*Материалы разработки (промпты, отчёты, контракты параллельных work-packages, независимый ручной расчёт) — в `ai_workstreams/`; они не требуются для проверки решения, но показывают происхождение каждого числа.*
