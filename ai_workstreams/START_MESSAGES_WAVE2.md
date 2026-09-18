# Стартовые сообщения волна 2+ (запуск по порядку D7 из ORCHESTRATOR_DECISIONS.md)

Порядок: **шаг 1** — WP1w2 (сейчас, одно устройство). **Шаг 2** — WP1w3 (после приёмки). **Шаг 3** — WP2w2 + WP3w2 + WP4w2 (параллельно, 3 устройства, после приёмки WP1w3). **Шаг 4** — WP5w2. **Шаг 5** — WP6.

Перед запуском каждой следующей группы оркестратор подтверждает приёмку предыдущей (проверка REPORT и pytest).

---

## ШАГ 1 — Устройство 1: WP1 волна 2 (финансы)

```
Ты — исполнитель пакета WP1 (волна 2) проекта «Топливный космоконтур 2035».

Порядок работы:
1. git clone git@github.com:l1ttleFox/sad9ugn.git && cd sad9ugn   (если SSH недоступен — HTTPS: https://github.com/l1ttleFox/sad9ugn.git)
2. git checkout wp1-core
3. Прочитай ПОЛНОСТЬЮ, по порядку:
   - ai_workstreams/README.md
   - ai_workstreams/ORCHESTRATOR_DECISIONS.md (решения D1–D7 — ОБЯЗАТЕЛЬНЫ, особенно D1: jsonschema не добавляем в ядро, CAPACITY_EXCEEDED единый)
   - ai_workstreams/WP1_core_engine/prompt_wave2.md (твоё задание)
   - ai_workstreams/WP1_core_engine/REPORT_wave1.md (что уже сделано, раздел «Передать следующей волне» — там готовые точки подключения)
   - ai_workstreams/00_contracts/core_api.md, units_and_conventions.md (§7 платежи, §8 CAPEX, §10 финансы; реестр TA обновлён: TA-10, TD-01, TD-02)
   - docs/CALCULATION_RULES.md §5, §6, §8, §9, §12
4. Реализуй финансовый блок (finance.py, calculate_costs) и тесты по prompt_wave2.md. Код волны 1 не переписывай — только подключай; багфиксы волны 1 допустимы с описанием в отчёте.
5. Проверь по критериям приёмки prompt_wave2.md (V03/V04/V05, ручной пример A-канала, grep на двойной TOP).
6. Напиши REPORT_wave2.md (результаты pytest, таблица «вход→ожидание→факт» для контрольных примеров, изменения в коде волны 1 если были, вопросы).
7. git add (только свои файлы) → git commit -m "wp1: финансы ..." → git push origin wp1-core
Жёсткие правила: только ветка wp1-core; CASE_INPUT и контракты не менять; русский текст; после push — стоп и краткое резюме.
```

## ШАГ 2 — Устройство 1: WP1 волна 3 (ограничения, run_plan, экспорт)

```
Ты — исполнитель пакета WP1 (волна 3) проекта «Топливный космоконтур 2035».

Порядок работы:
1. git clone git@github.com:l1ttleFox/sad9ugn.git && cd sad9ugn   (или HTTPS)
2. git checkout wp1-core
3. Прочитай ПОЛНОСТЬЮ:
   - ai_workstreams/ORCHESTRATOR_DECISIONS.md (обязательны: D1.3 — jsonschema только в инструментах; D3.4 — адаптер scenario_parameters; D4.2 — constraint_checks с полным списком passed/не passed)
   - ai_workstreams/WP1_core_engine/prompt_wave3.md (твоё задание)
   - REPORT_wave1.md и REPORT_wave2.md (состояние кода)
   - ai_workstreams/00_contracts/* (все), docs/CALCULATION_RULES.md §13–14, docs/CASE_RULES.md §8, docs/STRESS_PROTOCOL.md
4. Реализуй по prompt_wave3.md: constraints.py (ВСЕ rule_id + полный passed-список по D4.2), compare.py, persistence.py, export.py, risks.py, финальный run_plan, адаптер scenario_parameters (D3.4: override копии CaseData с проверкой исходного значения и журналом), интеграционные тесты, tests/run_control_checks.py (V01–V10).
5. ВАЖНО для сверки с WP2: прогони эталонные значения из ai_workstreams/WP2_strategy_economics/manual_calc/reference_values.json (8 ключевых: S10 BASE 2040 procurement 1714.11, PV S10 9951.40 и т.д.) через run_plan с планами из ai_workstreams/WP2_strategy_economics/plans/ (S10.json, S14.json) — расхождения включи в отчёт (эталон допустимого расхождения 0.5%; если больше — ищи причину в конвенциях TD-01/TD-02, затем эскалируй; планы WP2 и reference_values НЕ изменять).
6. Проверь по критериям приёмки prompt_wave3.md + п.5 выше.
7. REPORT_wave3.md (итоги V01–V10, результаты сверки с reference_values — таблица, архитектура run_plan, ограничения ядра) → commit "wp1: ограничения, экспорт, run_plan ..." → push origin wp1-core.
Жёсткие правила: только ветка wp1-core; CASE_INPUT/контракты/файлы WP2 не менять; русский текст; после push — стоп и резюме.
```

## ШАГ 3a — Устройство 2: WP2 волна 2 (прогон на ядре, финальная стратегия) — ПОСЛЕ приёмки WP1w3

```
Ты — исполнитель пакета WP2 (волна 2) проекта «Топливный космоконтур 2035».

Порядок работы:
1. git clone git@github.com:l1ttleFox/sad9ugn.git && cd sad9ugn (или HTTPS)
2. git checkout wp2-strategy && git merge origin/wp1-core   (ядро нужно в твоей ветке; конфликты маловероятны — ваши файлы не пересекаются)
3. Прочитай ПОЛНОСТЬЮ:
   - ai_workstreams/ORCHESTRATOR_DECISIONS.md (D2: TA-10 только для S21; TD-01/TD-02 — политика заказов и начальный запас сохранены; D7)
   - ai_workstreams/WP2_strategy_economics/prompt_wave2.md (твоё задание)
   - свой RESULTS_wave1.md и REPORT_wave1.md (эталонные числа, топ-5: S10, S14, S18, S21, S25)
   - ai_workstreams/WP1_core_engine/REPORT_wave3.md (состояние ядра, результаты сверки reference_values — начни отсюда, чтобы не повторять найденные расхождения)
   - ai_workstreams/00_contracts/core_api.md, result_format.json
4. Выполни prompt_wave2.md: прогон топ-5 детально (BASE+STRESS), остальных 20 — сокращённо; таблица сверки «ручной расчёт↔ядро» (расхождение >0.5% без объяснения → баг-репорт в REPORT, ядро НЕ правь); финальный выбор + MCDA; сохранённые планы results/plans/FINAL_BASE.json, FINAL_STRESS.json; выгрузки results/exports/; scenario_comparison.md (одностраничная основа); чувствительность ставки 5/10/15% и lead time C 18/24.
5. Критерии приёмки prompt_wave2.md. Особое внимание: если ядро даёт лучший PV у другой стратегии (не S10) после сверки — не цепляйся за волну 1: выбор делается по СВЕРЕННЫМ числам ядра, с объяснением отличий от ручного расчёта.
6. REPORT_wave2.md (сверка, финал, MCDA, расхождения) → commit "wp2: прогон стратегий на ядре, финальная стратегия" → push origin wp2-strategy.
Жёсткие правила: только ветка wp2-strategy; ядро/CASE_INPUT/контракты не менять; русский текст; после push — стоп и резюме.
```

## ШАГ 3b — Устройство 3: WP3 волна 2 (стрессы и риски на ядре) — ПОСЛЕ приёмки WP1w3

```
Ты — исполнитель пакета WP3 (волна 2) проекта «Топливный космоконтур 2035».

Порядок работы:
1. git clone git@github.com:l1ttleFox/sad9ugn.git && cd sad9ugn (или HTTPS)
2. git checkout wp3-stress && git merge origin/wp1-core
3. Прочитай ПОЛНОСТЬЮ:
   - ai_workstreams/ORCHESTRATOR_DECISIONS.md (D3: В6 — доля критического в low/high подтверждена; В7 — MMOD интервально 10/25/50%; В8 — TEAM_CAPEX_OVERRUN допустим через адаптер; D3.4 — адаптер scenario_parameters реализован в ядре волной 3 — используй его вместо собственного; если в merged-ядре адаптера нет — используй свой и помечай результаты «через адаптер WP3»)
   - ai_workstreams/WP3_stress_risk/prompt_wave2.md (твоё задание)
   - свои protocols/P01–P05, risk_register.yaml, configs/team/*.yaml (10 сценариев)
   - ai_workstreams/WP1_core_engine/REPORT_wave3.md (состояние ядра)
   - ai_workstreams/WP2_strategy_economics/REPORT_wave2.md и results/plans/FINAL_*.json, ЕСЛИ уже опубликованы (если нет — используй S10.json из plans/ как рабочий план и помечай результаты «на S10, до FINAL»; после публикации FINAL перезапусти ключевые тесты на FINAL-плане)
4. Выполни prompt_wave2.md: P01 декомпозиция стресса (4 промежуточных теста по одному фактору), P02 чувствительность + tornado + пороги, P04 reverse stress (grid), P03 все 10 TEAM-рисков с мерами и остаточным риском, P05 геополитический модуль (до/после, экспорт, восстановление цен), results/risk_register.csv, блок адаптации (триггеры, время реакции по lead times).
5. Критерии приёмки prompt_wave2.md. Обязательная проверка: 55%/75% ISRU не умножены на reliability (показать в отчёте); MANDATORY_STRESS не смешан с TEAM без явного combined-сценария (R01).
6. REPORT_wave2.md (ключевые числа для WP5: эффект стресса по годам, топ-3 риска, reverse-пороги, гео-результат) → commit "wp3: стресс-расчёты и реестр рисков" → push origin wp3-stress.
Жёсткие правила: только ветка wp3-stress; ядро/CASE_INPUT/mandatory_stress.yaml не менять; вероятности не выдумывать; русский текст; после push — стоп и резюме.
```

## ШАГ 3c — Устройство 4: WP4 волна 2 (интеграция UI с ядром) — ПОСЛЕ приёмки WP1w3

```
Ты — исполнитель пакета WP4 (волна 2) проекта «Топливный космоконтур 2035».

Порядок работы:
1. git clone git@github.com:l1ttleFox/sad9ugn.git && cd sad9ugn (или HTTPS; push через HTTPS — права Maks0Ny выданы)
2. git checkout wp4-ui && git merge origin/wp1-core
3. Прочитай ПОЛНОСТЬЮ:
   - ai_workstreams/ORCHESTRATOR_DECISIONS.md (D4: реестр договоров — отдельный файл <plan_id>_contracts.json; passed-список comes из constraint_checks ядра — UI не выдумывает успешные проверки)
   - ai_workstreams/WP4_ui/prompt_wave2.md (твоё задание) и свой REPORT_wave1.md + REPORT_wave2.md (подготовка уже сделана: USE_ENGINE, адаптер, каталог планов)
   - ai_workstreams/WP1_core_engine/REPORT_wave3.md (реальные типы возврата run_plan)
   - ai_workstreams/00_contracts/core_api.md, result_format.json
4. Выполни prompt_wave2.md: переключение services на ядро, полный пользовательский сценарий, save/load в results/plans/, экспорт CSV/XLSX, TEAM_*-сценарии из configs/ (после merge wp3-stress, если доступен; иначе — из ai_workstreams/WP3_stress_risk/configs/team/), геополитический модуль, демо-кнопки FINAL-планов (появятся после WP2w2 — сделай автообнаружение), docs/ИНСТРУКЦИЯ.md.
   Примечание: если FINAL-планы WP2 ещё не опубликованы — тестируй на S10.json из ai_workstreams/WP2_strategy_economics/plans/; автообнаружение FINAL подхватит их позже без правок кода.
5. Критерии приёмки prompt_wave2.md, включая 5 чисел UI==CSV, примеры «до/после» изменения решения, восстановление BASE после геосценария до символа.
6. REPORT_wave2.md (обнови существующий: что закрыто из списка «Что осталось») → commit "wp4: интеграция UI с ядром" → push origin wp4-ui.
Жёсткие правила: только ветка wp4-ui; ядро не менять (баги → REPORT); никакой расчётной логики в UI; русский интерфейс; после push — стоп и резюме.
```

## ШАГ 4 — Устройство 5: WP5 волна 2 (финальная записка) — ПОСЛЕ приёмки WP2w2 и WP3w2

```
Ты — исполнитель пакета WP5 (волна 2) проекта «Топливный космоконтур 2035».

Порядок работы:
1. git clone git@github.com:l1ttleFox/sad9ugn.git && cd sad9ugn (или HTTPS)
2. git checkout wp5-docs && git merge origin/main   (в main к этому времени будут wp1-core, wp2-strategy, wp3-stress)
3. Прочитай ПОЛНОСТЬЮ:
   - ai_workstreams/ORCHESTRATOR_DECISIONS.md (D5: первоисточники теперь В РЕПОЗИТОРИИ — docs/sources_txt/*.txt, критерии — docs/КРИТЕРИИ_ОЦЕНКИ.txt, постановка — docs/ПОСТАНОВКА_КЕЙСА.txt; TA-10 — только S21 research)
   - ai_workstreams/WP5_docs/prompt_wave2.md (твоё задание) и свой REPORT_wave1.md (реестр 35 плейсхолдеров)
   - ai_workstreams/WP2_strategy_economics/RESULTS_wave1.md, REPORT_wave2.md, results/ (финальная стратегия, MCDA, comparison)
   - ai_workstreams/WP3_stress_risk/REPORT_wave2.md, results/stress/, results/risk_register.csv, results/geopolitics/
4. Выполни prompt_wave2.md: замени ВСЕ 35 плейсхолдеров (grep '[[' = 0), напиши 09–12 + RESUME_1page.md, собери docs/УПРАВЛЕНЧЕСКАЯ_ЗАПИСКА.md (8–12 страниц), сверь первоисточники по docs/sources_txt/ (сними пометки «по конспекту оркестратора»: DOI Federgruen POM 31(7), Tanaka Procedia SBS 119, WACC Sommariva, RRM3 Simonini), карта критериев по docs/КРИТЕРИИ_ОЦЕНКИ.txt (все 20 пунктов).
5. Проверь: каждое число трассируется до results/ (таблица трассировки в отчёте); объём 8–12 страниц.
6. REPORT_wave2.md → commit "wp5: финальная записка" → push origin wp5-docs.
Жёсткие правила: только ветка wp5-docs; числа из результатов НЕ менять; расхождения источников → REPORT; русский текст; после push — стоп и резюме.
```

## ШАГ 5 — Устройство 6: WP6 (презентация и сборка) — ПОСЛЕ приёмки WP5w2

```
Ты — исполнитель пакета WP6 (волна 1) проекта «Топливный космоконтур 2035».

Порядок работы:
1. git clone git@github.com:l1ttleFox/sad9ugn.git && cd sad9ugn (или HTTPS)
2. git checkout wp6-present && git merge origin/main
3. Прочитай ПОЛНОСТЬЮ:
   - ai_workstreams/WP6_presentation_repo/prompt_wave1.md (твоё задание)
   - docs/УПРАВЛЕНЧЕСКАЯ_ЗАПИСКА.md, docs/note/RESUME_1page.md
   - results/ (планы, экспорты, comparison, risk_register, stress, geopolitics)
   - ai_workstreams/INTEGRATION_CHECKLIST.md (финальный прогон)
   - docs/ПОСТАНОВКА_КЕЙСА.txt (раздел «Состав итогового решения» — чек-лист сдачи)
4. Выполни prompt_wave1.md: презентация ≤12 слайдов (Marp-markdown или reveal.js HTML — то, что собирается бесплатно; слайд 5 — воронка 25→топ-5→финал), корневой README.md (порядок проверки из кейса), docs/ИСТОЧНИКИ.md, финальный requirements.txt, .gitignore, чистый прогон на свежем клоне (install→pytest→streamlit→FINAL-планы→экспорт) — результат в REPORT.
5. Критерии приёмки prompt_wave1.md; каждое число слайдов трассируется в results/.
6. REPORT_wave1.md → commit "wp6: презентация и финальный README" → push origin wp6-present.
Жёсткие правила: только ветка wp6-present; результаты WP1–WP5 не менять; русский текст; после push — стоп и резюме.
```
