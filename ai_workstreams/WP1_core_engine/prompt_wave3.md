# WP1 Волна 3 — Расчётное ядро: ограничения, сценарии, сохранение, экспорт

## Роль
Ты — senior Python-разработчик. Финальная волна ядра: проверки ограничений, точка входа run_plan, сохранение/загрузка планов, экспорт. От этой волны зависит критерий 4 (ограничения стандартного плана) и 19–20 (функциональность контура).

## Обязательное чтение
1. Контракты `00_contracts/` (все три + units §6, §9, §11).
2. `docs/CALCULATION_RULES.md` §13–14, `docs/CASE_RULES.md` §8 (что считается неисполнимым планом), `docs/STRESS_PROTOCOL.md`.
3. `data/constraints.csv` — реестр hard-ограничений CASE_INPUT.
4. REPORT_wave1/2 — текущее состояние кода.
5. `tests/examples/` — invalid_plan_examples организатора (over_capacity, negative_reservation, malformed_scenario).

## Задание
1. **`constraints.py`** → `check_constraints(...) -> list[Violation]`. Реализовать ВСЕ проверки с rule_id:
   - из constraints.csv: `BASE_CRITICAL_SERVICE` (SL_crit ≥ 0.99 ежегодно, BASE hard), `BASE_TOTAL_SERVICE` (≥0.97), `CAPEX_2037` (≤1800), `CAPEX_2040` (≤2800), `RESERVE_45D` (ежегодно, физический или доказанный контрактный), `EMERGENCY_BASE_STREAK` (≤2 года подряд, трактовка TA-09), `STRESS_LOSS_LIMIT` (losses/throughput ≤ 0.02 с 2038, только MANDATORY_STRESS);
   - внутренние: `CAPACITY_EXCEEDED` (reserved/order > capacity), `STORAGE_OVERFLOW` (I > ёмкость в любом месяце), `NEGATIVE_INVENTORY` (защита), `LEAD_TIME_VIOLATION` (поставка раньше возможной по lead time), `ISRU_WITHOUT_CAPEX` (заказы D без финансирования), `EARTH_NEW_WITHOUT_EXERCISE` (заказы C без exercise), `ISRU_FIRST_YEAR_RELIABILITY` (предупреждение, если план объявляет надёжность D 2038 > 0.78 как гарантию).
   - Каждая Violation: rule_id, period, actual, limit, excess, message_ru (год, величина, причина — формат из README организатора §26).
   - Пройденные проверки тоже попадают в constraint_checks (passed=true) — жюри хочет видеть полную картину.
2. **`compare.py`** → `compare_scenarios(results) -> ComparisonResult`: таблица по сценариям — total_mln, discounted_mln, SL по годам, shortage, reserve_ok, число нарушений, capex_cumulative. Плюс дельты STRESS−BASE.
3. **`persistence.py`** → `save_plan/load_saved_plan` (JSON по plan_format.json, валидация при загрузке).
4. **`export.py`** → `export_results(result, path, fmt)`: CSV (и опционально XLSX через pandas/openpyxl) по export.schema.json: yearly_balance.csv, source_schedule.csv, inventory_trace.csv, financial_breakdown.csv, constraint_checks.csv, risk_register.csv + meta.json (scenario_id, plan_id, units, assumptions_reference, engine_version, generated_at). Добавить `assumptions_reference` → путь к реестру TA.
5. **`risks.py`** → `evaluate_risks`: прогон списка TEAM_* сценариев через run_plan и сбор последствий (дельты тонн/млн/SL) в risk_register. Интерфейс готов к наполнению реестра из WP3.
6. **`run_plan`** — собрать полный конвейер в единую точку входа (контракт core_api.md). Один и тот же путь используется тестами, UI и экспортом.
7. **Интеграционные тесты** `tests/test_engine_wave3.py`:
   - прогон BASE эталонного плана (составить минимальный выполнимый: B покрывает 2035; показать результат);
   - прогон MANDATORY_STRESS того же плана — убедиться, что применились ×1.15 спрос, ×1.25 цены A/B 2038–39, ISRU 0.55/0.75, loss ceiling;
   - invalid_plan_examples организатора дают ожидаемые нарушения (over_capacity → CAPACITY_EXCEEDED; negative_reservation → ошибка валидации; malformed_scenario → понятная ошибка);
   - V08 (capacity 10, reserved 12 → excess 2);
   - экспорт → повторная загрузка CSV → числа совпадают;
   - сохранённый план повторно открывается и даёт тот же результат (идемпотентность).
8. **`tests/run_control_checks.py`** — скрипт-прогон всех V01–V10 с выводом таблицы «case / expected / actual / OK?» (для защиты и README).

## Что НЕ делать
- Не изобретать стратегии и «починку» неисполнимых планов (система диагностирует, не чинит — CASE_RULES §8).
- Не менять контракты; предложения — в REPORT.
- Monte Carlo, робастная оптимизация — не здесь (WP3).

## Критерии приёмки
1. `python -m pytest tests/ -q` — все зелёные; `python tests/run_control_checks.py` — V01–V10 10/10 OK.
2. Эталонный BASE-план: все hard-нарушения отсутствуют; STRESS-прогон показывает эффект каждого изменения отдельно (в отчёте — декомпозиция: спрос/цены/ISRU/потолок).
3. Нарушения выводятся в требуемом формате (пример в отчёте).
4. Экспорт совпадает с внутренними числами (сверить 3 значения вручную).
5. REPORT_wave3.md: итоговая архитектура, как run_plan связан с UI-контрактом, известные ограничения ядра, готовность к WP2/WP3/WP4 волнам 2.
6. Git: `wp1: ограничения и экспорт ...` → push `wp1-core`.
