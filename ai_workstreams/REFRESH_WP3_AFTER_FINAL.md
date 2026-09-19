# Повторный прогон WP3 после публикации FINAL-планов

Скопируйте текст ниже первым сообщением в новую сессию ИИ на устройстве WP3.

```text
Ты — исполнитель повторного прогона WP3 (стресс-тестирование и риски) проекта «Топливный космоконтур 2035».

Предыдущая волна WP3 технически реализована, но её результаты были рассчитаны на предварительном плане S10 до окончательного выбора WP2 и до исправления ядра D8. Твоя задача — НЕ переписывать методологию заново, а воспроизводимо пересчитать все результаты на FINAL-планах и обновить отчёт/выгрузки.

ПРЕДВАРИТЕЛЬНАЯ ПРОВЕРКА (обязательна до любых изменений):
1. git clone git@github.com:l1ttleFox/sad9ugn.git && cd sad9ugn
   Если SSH недоступен: git clone https://github.com/l1ttleFox/sad9ugn.git
2. git checkout wp3-stress
3. git fetch origin --prune
4. git merge origin/main
5. Убедись, что существуют:
   - results/plans/FINAL_BASE.json
   - results/plans/FINAL_STRESS.json
   - ai_workstreams/WP2_strategy_economics/REPORT_wave2.md
   - results/scenario_comparison.md (или явно указанный WP2 эквивалент)
6. Если хотя бы одного обязательного файла нет — НИЧЕГО не пересчитывай и не коммить. Остановись с сообщением: «WP3 refresh заблокирован: WP2 FINAL не опубликован», перечисли отсутствующие пути.

ОБЯЗАТЕЛЬНО ПРОЧИТАЙ ПОЛНОСТЬЮ:
- ai_workstreams/ORCHESTRATOR_DECISIONS.md, особенно D3 и D8;
- ai_workstreams/WP3_stress_risk/prompt_wave2.md;
- ai_workstreams/WP3_stress_risk/REPORT_wave1.md;
- текущий ai_workstreams/WP3_stress_risk/REPORT_wave2.md (это исторический отчёт на S10; его числа нельзя переносить в финал без пересчёта);
- ai_workstreams/WP2_strategy_economics/REPORT_wave2.md;
- results/plans/FINAL_BASE.json и FINAL_STRESS.json;
- docs/STRESS_PROTOCOL.md;
- ai_workstreams/WP3_stress_risk/protocols/P01_mandatory_stress.md ... P05_geopolitics.md;
- ai_workstreams/00_contracts/core_api.md, result_format.json, units_and_conventions.md.

АКТУАЛЬНЫЕ РЕШЕНИЯ ОРКЕСТРАТОРА:
- мощность ограничивает физическую поставку в году поставки, не в году размещения заказа (D8);
- допуск округления месячной мощности — 0.001 т;
- S10 на исправленном ядре имел 0 нарушений BASE и сверку PV в пределах 0.5%, но финальные расчёты выполняются только на FINAL-планах;
- TEAM_GEO_CHANNEL_A и TEAM_PRICE_SPIKE_E используют только variable_price_multiplier: двойной price override удалён;
- MANDATORY_STRESS нельзя смешивать с TEAM-сценариями, кроме явно именованного combined-сценария;
- reliability не умножается на поставки BASE и не применяется повторно к долям ISRU 0.55/0.75;
- INVENTORY_SHOCK_APPLIED — информационное событие, не hard-нарушение для ранжирования риска.

ЗАДАНИЕ:

1. Переключи WP3-скрипты на FINAL-планы:
   - BASE-контроль: results/plans/FINAL_BASE.json;
   - MANDATORY_STRESS: results/plans/FINAL_STRESS.json;
   - если WP2 выбрал единую стратегию и файлы идентичны — это допустимо, но отметь в отчёте;
   - не изменяй FINAL-планы.

2. Перезапусти P01 — обязательный стресс:
   - BASE на FINAL_BASE;
   - MANDATORY_STRESS на FINAL_STRESS;
   - четыре изолированных фактора F1 спрос, F2 цены, F3 ISRU, F4 loss ceiling;
   - проверь точные множители yaml;
   - сформируй актуальные P01_yearly_balance, financial_breakdown, summary, violations, meta;
   - явно докажи actual/planned D = 0.55, 0.75, 1.00 без reliability.

3. Перезапусти P02 — чувствительность:
   - low/high demand с пропорциональным critical demand;
   - цена A/B ±20%; ставка 5/10/15%; доля ISRU; lead time C 18/24 только если C есть в FINAL-плане;
   - tornado и reverse-пороги;
   - порог определяется относительно чистого, выполнимого FINAL BASE. Если FINAL BASE уже имеет hard-нарушение — это блокер, а не база для reverse stress: остановись и эскалируй WP2.

4. Перезапусти P04 reverse stress:
   - grid спрос × цена A × доля D;
   - отдельно BASE и MANDATORY_STRESS;
   - покажи область исполнимости и минимальные ломающие комбинации;
   - не считать цену физическим триггером, если ограничение зависит только от расходов и OPEX-бюджет не задан.

5. Перезапусти все 10 TEAM-рисков P03:
   - последствия в тоннах, PV и SL;
   - мера, стоимость меры, остаточный риск;
   - меры должны учитывать состав FINAL-плана: если в нём есть C/E, не оставляй автоматически старую меру «только B» без проверки альтернатив;
   - для R07 CAPEX +15% пересчитай фактический headroom FINAL-плана;
   - для R06 Earth-New delay: если C есть в FINAL, риск должен стать содержательным, а не no-op;
   - MMOD считать 10/25/50% текущего запаса без выдуманной вероятности;
   - INVENTORY_SHOCK_APPLIED исключить из числа hard-нарушений.

6. Перезапусти P05 геополитический модуль:
   - event → параметр → пересчёт → эффект;
   - цена применяется один раз;
   - BASE после восстановления совпадает с исходным до символа;
   - отдельный combined-сценарий с mandatory, без двойного начисления;
   - обнови results/geopolitics/*.

7. Обнови все выгрузки:
   - results/stress/*;
   - results/stress/exports/*;
   - results/geopolitics/*;
   - results/risk_register.csv и .md;
   - results/plans_adaptive/* — меры должны быть производными от FINAL-плана, а не от старого S10.

8. Обнови ai_workstreams/WP3_stress_risk/REPORT_wave2.md:
   - в первой строке контекста указать FINAL_BASE/FINAL_STRESS и их plan_id;
   - удалить предупреждения про старые 45 нарушений S10 и нерешённую конвенцию: D8 её уже решил;
   - привести актуальные числа BASE/STRESS, декомпозицию, sensitivity, reverse, топ-3 риска, геополитику;
   - указать commit ядра и sha256 FINAL-планов;
   - дать отдельный блок «Ключевые числа для WP5».

9. Тесты:
   - адаптируй tests/test_wp3_wave2.py к FINAL-планам;
   - CASE_INPUT не изменять; SHA-тесты должны нормализовать LF/CRLF;
   - python -m pytest tests/ -q — весь suite зелёный;
   - python tests/run_control_checks.py — 10/10;
   - проверить, что exports соответствуют текущему run_plan;
   - проверить, что FINAL_BASE не имеет hard-нарушений.

ГРАНИЦЫ:
- не менять src/engine/**: найденный баг фиксируй в REPORT и останови зависимый расчёт;
- не менять data/**, configs/base.yaml, configs/mandatory_stress.yaml, контракты и FINAL-планы;
- разрешено менять только WP3-скрипты/тесты, TEAM-конфиги (если нужна корректировка без изменения mandatory), results/stress, results/geopolitics, results/risk_register.*, results/plans_adaptive и REPORT_wave2.md;
- весь человекочитаемый текст — на русском;
- не выдавать сценарную тяжесть за вероятность.

КРИТЕРИИ ГОТОВНОСТИ:
- FINAL_BASE имеет 0 hard-нарушений;
- P01–P05 пересчитаны на FINAL;
- каждый из 10 рисков имеет численное последствие, меру и остаток;
- 55/75% применены один раз;
- гео-цена применена один раз и BASE восстанавливается;
- общий pytest зелёный и V01–V10 = 10/10;
- REPORT_wave2 не содержит устаревших чисел S10 до D8.

ЗАВЕРШЕНИЕ:
git add только разрешённые файлы
git commit -m "wp3: финальный повтор стрессов и рисков на FINAL-планах"
git push origin wp3-stress

После push остановись и выведи: plan_id BASE/STRESS, нарушения FINAL_BASE, PV/shortage BASE→STRESS, топ-3 риска, результаты pytest/V01–V10, открытые блокеры.
```
