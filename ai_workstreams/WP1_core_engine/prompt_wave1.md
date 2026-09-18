# WP1 Волна 1 — Расчётное ядро: загрузка, поставки, материальный баланс

## Роль
Ты — senior Python-разработчик. Пишешь расчётное ядро системы планирования снабжения орбитального топливного узла (хакатон-кейс «Топливный космоконтур 2035»). Это сердце всего проекта: от его корректности зависит 25 баллов жюри за модель.

## Контекст и обязательное чтение (до кода!)
1. `ai_workstreams/00_contracts/core_api.md` — контракт API (сигнатуры ОБЯЗАТЕЛЬНЫ).
2. `ai_workstreams/00_contracts/units_and_conventions.md` — единицы, месячный шаг, lead times, TEAM_ASSUMPTION TA-01…TA-09.
3. `ai_workstreams/00_contracts/result_format.json` — схема результата.
4. `docs/CALCULATION_RULES.md` — контрольные правила расчёта (CASE_INPUT, нарушать нельзя).
5. `docs/CASE_RULES.md`, `docs/FAQ.md` — границы допустимого.
6. `ai_workstreams/00_contracts/data/` — входные данные (копия CASE_INPUT).

## Задание волны 1
Создать пакет `src/engine/` и реализовать:

1. **`models.py`** — dataclasses: `CaseData`, `Scenario`, `Plan`, `Violation`, `DeliveriesResult`, `InventoryResult`, `RunResult` — строго по полям result_format.json / plan_format.json.
2. **`loader.py`** — `load_case(data_dir)`, `load_scenario(path)`, `load_plan(path)`. Чтение CSV/YAML/JSON в датаклассы. Проверка обязательных полей; при ошибке — исключение `CaseLoadError` с сообщением на русском, называющим файл, строку и параметр.
3. **`validator.py`** — `validate_case` (целостность: critical ≤ total по годам, неотрицательность, enum-поля), `validate_plan` (статика: reserved ≤ capacity; источник C/D заказывается только при наличии инвестиции в плане; периоды в горизонте; investment_id существует).
4. **`scenario.py`** — `apply_scenario(case, scenario) -> CaseData` (новый объект): множители спроса (общий и критический), множители цен по каналам и годам, фактические доли поставки ISRU, флаг/порог loss_ceiling. BASE — все множители 1.0.
5. **`deliveries.py`** — `calculate_deliveries`: помесячно. Заказ месяца M с lead time L → плановая поставка в M+L (TA-04). Lead times в исходных единицах (месяцы; Emergency — 6 недель → поставка в следующем месяце, TA-03; Earth-New — 24 мес политика, TA-02). Ограничение: заказ в месяце ≤ зарезервированная на этот год мощность/12 (равномерно) — иначе Violation CAPACITY_EXCEEDED при расчёте. Доступность каналов: A/B/E с 2035-01, C — через 24 мес после exercise_option, D — с 2038-01 и только если LUNAR_ISRU профинансирован до 2038-01. В BASE delivered = planned; в сценарии с actual_delivery_share — умножение ТОЛЬКО на долю сценария, reliability НЕ трогать (ЗАПРЕЩЕНО, см. CALCULATION_RULES §11).
6. **`inventory.py`** — `calculate_inventory`: помесячный баланс I_end = I_start + delivered − losses − served. Потери = throughput × loss_rate действующего режима (смена режима по TA-05). Аллокация при дефиците: сначала критический (§5 конвенций). I_end ≥ 0, shortage отдельно. Ёмкость проверяется каждый месяц (overflow → Violation STORAGE_OVERFLOW). `calculate_service`: SL_total, SL_critical по годам + годовая агрегация yearly_balance с reserve_required_t (45 дней) и reserve_ok.
7. **`tests/test_engine_wave1.py`** — тесты на контрольных векторах V01 (баланс: 10+30−2−25=13), V02 (shortage=2, I_end=0, не −2), V06 (потери один раз: 20×0.05=1), V07 (резерв: 365×45/365=45), V09 (вложенность: total=100 при critical=60) — значения из `tests/validation/expected_checks.json`. Плюс тесты: lead time A (заказ 2035-01 → поставка 2036-01), Emergency 6 недель, смена режима хранения среди года, ISRU share 0.55 без повторного умножения (аналог V10 на данных кейса).

## Что НЕ делать в этой волне
- Финансы (`finance.py`), ограничения (`constraints.py`), риски, сравнение, экспорт, save/load — волна 2–3. Создай файлы-заглушки с `raise NotImplementedError`.
- UI, оптимизатор, Monte Carlo.
- НЕ менять: контракты, data/, configs/, docs/.

## Формат результата
- Код в `src/engine/` (файлы по контракту core_api.md), тесты в `tests/`.
- `requirements.txt` в корне: python ≥3.12, pandas, pyyaml, pytest (с версиями).
- `ai_workstreams/WP1_core_engine/REPORT_wave1.md`: что сделано, принятые решения, результаты прогона pytest, вопросы оркестратору.

## Критерии приёмки
1. `python -m pytest tests/ -q` — все тесты зелёные.
2. Загрузка реальных data/*.csv и configs/*.yaml проходит без ошибок.
3. Для синтетического простого плана (только канал B, ровные заказы) баланс сходится вручную (привести ручной расчёт в отчёте для 2–3 месяцев).
4. В BASE нигде не встречается умножение на reliability (показать grep в отчёте).
5. Сообщения об ошибках — на русском, с параметром и периодом.
6. Git: коммиты `wp1: ...`, push в ветку `wp1-core`.
