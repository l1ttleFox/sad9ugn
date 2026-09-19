# WP5 REPORT — Волна 2: финальная управленческая записка

Дата: 2026-09-19. Ветка: `wp5-docs`. База: merge origin/main (wp1-core + wp2-strategy FINAL-планы) + merge origin/wp3-stress (e4f791c «wp3: финальный повтор стрессов и рисков на FINAL-планах» — без этого merge в ветке отсутвали актуальные результаты WP3 на FINAL; merge fast-forward, конфликтов нет).

## 1. Статус задания prompt_wave2.md

| Пункт | Статус |
|---|---|
| Все 35 плейсхолдеров заменены; grep `[` `[` = 0 (docs/ + results/) | ✓ (проверено Select-String по всем .md/.txt, кроме sources_txt) |
| `09_strategy_comparison.md` | ✓ создано: скрининг 25×2, отсев с числовыми причинами, топ-5 на ядре, MCDA + swing + ставка, Q1–Q8, опцион C/S16/S25, стоимость робастности |
| `10_stress_results.md` | ✓ создано: BASE vs STRESS по годам, декомпозиция F1–F4, адаптация и её цена, честный ориентир «на неадаптированном плане», sensitivity, reverse-пороги, grid P04 |
| `11_risk_results.md` | ✓ создано: 10 TEAM-рисков с рассчитанными последствиями (т/млн/SL), меры, остатки, триггеры, время реакции, ex-ante/ex-post, пределы; ссылка на `results/risk_register.csv` |
| `12_roadmap_budget.md` | ✓ создано: CAPEX-профиль и бюджет по годам/статьям, лимиты, ворота G1–G5 с количественными условиями (включая G4: доля D-2038 ≤ 0.60 → exercise C), роли, зависимости |
| `RESUME_1page.md` | ✓ создано: одностраничное резюме BASE vs STRESS (решения, различия/совпадения, обоснование) |
| `docs/УПРАВЛЕНЧЕСКАЯ_ЗАПИСКА.md` | ✓ собрано: единый документ, ~3540 слов ≈ 10–11 страниц (бюджет 8–12), все разделы + источники с DOI + приложения со ссылками из текста. pandoc недоступен → PDF не собирался (md — допустимый формат по заданию: «единый документ (или PDF через pandoc если доступен)») |
| `08_geopolitics_bonus.md` дописан числами | ✓ (§8.3: +471.19 млн TotalCost, +337.92 млн PV, стороны по P05_parties.csv, порог переключения k>1.44, combined 9.30, восстановимость) |
| Проверка соответствия критериям | ✓ чек-лист пунктов 6–9, 14–18 — §4 ниже; полная карта всех 20 пунктов — `00_structure.md` |
| Сверка первоисточников по `docs/sources_txt/` | ✓ §3 ниже; пометки «по конспекту оркестратора» сняты (grep «конспект» по docs/note = 0 в значении «не сверено»; упоминания остались только в §3.3/REPORT как описание истории сверки) |
| Evidence map и реестр TA сохранены и актуализированы | ✓ (`03_methods_evidence_map.md` обновлён по первоисточникам; `02_data_assumptions.md`: TA-10 отражён как утверждённый D2.1/D6 только для S21) |

## 2. Таблица трассировки «число → источник» (ключевые числа записки)

Каждое число `docs/УПРАВЛЕНЧЕСКАЯ_ЗАПИСКА.md` и `docs/note/09–12, RESUME` происходит из одного из источников ниже (значения НЕ изменялись; округление — только представление, до 2 знаков):

| Число (в записке) | Значение | Файл-источник |
|---|---|---|
| PV BASE финала | 9961.31 | `results/exports/top5_detailed.csv` (S10 BASE), `results/exports/FINAL_BASE/financial_breakdown.csv`, `results/stress/P01_summary.csv` (строка BASE) |
| PV STRESS финала | 11498.45 (+1537.14, +15.4%) | `results/exports/top5_detailed.csv` (S10 MANDATORY_STRESS), `results/scenario_comparison.csv`, `results/stress/P01_summary.csv` |
| TotalCost BASE / STRESS | 12411.71 / 14523.27 | `results/exports/FINAL_BASE|FINAL_STRESS/financial_breakdown.csv` (Σ total_mln), `results/scenario_comparison.csv` |
| cost/served BASE / STRESS | 8.929 / 9.468 | `results/exports/top5_detailed.csv`, `results/scenario_comparison.csv` |
| SL 1.000/1.000 все годы, shortage 0, 0 нарушений | — | `results/exports/FINAL_BASE|FINAL_STRESS/yearly_balance.csv`, `constraint_checks.csv`; `results/stress/P01_summary.csv` |
| Потери 1.2% ≤ 2%, 3 passed-проверки | — | `results/stress/P01_summary.csv` (loss_ceiling_checks=3, failed=0), `results/exports/FINAL_STRESS/constraint_checks.csv` |
| Резерв: 8.74 / 4.66 т margin; 57.60≥48.08; 60.78≥55.29; 27.24 конечный | — | `results/scenario_comparison.csv` (min_reserve_margin_t), `results/exports/FINAL_STRESS/yearly_balance.csv` |
| Неадаптированный план в стрессе: 130.7 т, SL 0.943/0.849/0.869, 5 нарушений, PV 10489.7, цена адаптации +1008.7 | — | `results/stress/P01_summary.csv` (MANDATORY_ON_FIXED_BASE), `P01_yearly_balance.csv`, `P01_violations.csv`; WP3 REPORT_wave2 §P01 |
| Декомпозиция F1 +86.4 т / F2 +599.0 млн PV / F3 2 нарушения / F4 passed | — | `results/stress/P01_summary.csv` (строки F1–F4), `P01_violations.csv`; WP3 REPORT_wave2 §P01 |
| Tornado: цены ±20% = ∓1487.8; low 38 overflow; high +225.4 т/0.7999; доля D 0.40 +18.8 т | — | `results/stress/P02_tornado.csv`; `results/exports/sensitivity_demand_low_high.csv` (кросс-валидация high: 225.400003/0.79985) |
| Reverse-пороги: спрос ≥1.02 (R45) / ≥1.05 (SL); доля D ≤0.92 / ≤0.40; цены — нет до ×3.0 | — | `results/stress/P02_reverse_thresholds.csv`, `P02_meta.json`; WP3 REPORT_wave2 §P02 |
| Grid: BASE 11/1331, слом d≤0.90 или ×1.05 (SL 0.9709→0.9293, 34.0/11.9 т); MANDATORY 33/1331, слом ×1.05 (SL 0.8950, 49.5 т) | — | `results/stress/P04_grid_base.csv`, `P04_grid_mandatory.csv`, `P04_summary.json` |
| R02: +13.152 т, SL 0.9474, 15 нарушений, мера +529.85, остаток 0/+323.08 | — | `results/risk_register.csv`, `results/stress/P03_risks.csv` |
| R08: 15 нарушений, мера +310.25, остаток 0/+70.17 | — | там же |
| R10: +337.92 PV, +471.19 Total | — | там же; `results/geopolitics/P05_summary.json` |
| R04: −12.28 т, 2 нарушения, мера +140.27; R01: +94.14/82.59; R07: +170.45, 1617.5≤1800, headroom 182.5; R03: 40.5≥39.5; R09: +5.3 т | — | `results/risk_register.csv`, `results/stress/P03_risks.csv` |
| Гео: 7.44, +471.19 = 1.24×380, +337.92 (+3.4%), провайдер A +471.2 (2038/2039: 1177.98→1413.57, +235.6/год), combined 9.30 / PV 11920.85 (+422.40) / Total 15112.25 | — | `results/geopolitics/P05_summary.json`, `P05_parties.csv`, `geo_event.json` |
| Топ-5 ядро: S25 9948.01/12348.74; S18 11807.46/13155.34; S14 11974.84/13168.41; S21 12097.98/13382.30; served 1390/1534 | — | `results/exports/top5_detailed.csv` |
| MCDA: 0.9700/0.8432/0.4549/0.4268/0.3900; swing 0.9850/0.9850/0.8950 vs 0.8872 (FLEXIBILITY S25); веса и опционность | — | `results/exports/mcda.csv`; WP2 REPORT_wave2 §6 |
| Ставка: S10 11053.02/9961.31/9072.13; S25 11086.33/9948.01/9020.36 (BASE); 12846.65/11498.45/10400.10 и 13875.82/12348.74/11102.34 (STRESS) | — | `results/exports/sensitivity_discount_rate.csv`, `results/stress/P02_discount_rate.csv` |
| lead time C 18/24: FINAL — 0; S14/S18/S21 −461.49; S25 STRESS −31.52 | — | `results/exports/sensitivity_lead_time_C.csv` (11974.84−11513.36=461.49 и т.д.), `results/stress/P02_lead_time_C.csv` |
| Сверка ручной↔ядро ≤0.1003% | — | `results/exports/reconciliation.csv`; WP2 REPORT_wave2 §2 |
| Скрининг 25×2 (PV, дефицит, нарушения), отсев, Q1–Q8, ветви S16/S25, правило ветвления ≤0.60, порог опциона P>44%, 217 т/223.7 т/178.9 т, TOP-профили 2304.8/1898.8/1643.8/258.4/339.7, 824.6 млн 2040, headroom 10/280/370, Q6-комбинации 543.4/494.0/424.8 | — | `ai_workstreams/WP2_strategy_economics/RESULTS_wave1.md` §1–§7 (ручной независимый расчёт; статус «ручной расчёт WP2» раскрыт в записке §9); 824.6 — также ядро: `results/exports/FINAL_BASE/financial_breakdown.csv` (take_or_pay_extra_mln 2040) |
| Бюджет по годам (1995.5/2818.8/1447.1/1859.6/2351.2/1939.6; закупки 9974.8; резерв 549.0; хранение 193.9; OPEX 264; CAPEX 1430 2036-06) | — | `results/exports/FINAL_BASE/financial_breakdown.csv`, `results/plans/FINAL_BASE.json` (investments, capacity_reservations) |
| STRESS-годовые: 2859.9/1618.6/2801.4/3254.9/1993.0; закупки 2581.4/3029.6 | — | `results/exports/FINAL_STRESS/financial_breakdown.csv` |
| Заказы: 152/161; целевой запас 55.1/62.3; B 79.7/110.0 в стрессе 2038–39; I_start 40.2/49.1/57.7 | — | `results/plans/FINAL_BASE.json`, `FINAL_STRESS.json`; WP3 REPORT_wave2 §«О планах», `results/risk_register.md` (блок адаптации) |
| Версии/sha256: wave2-final-1.0; 89207ec6…/71090ba3…; ENGINE 0.3.0-wave3; 111 passed; V01–V10 10/10 | — | `results/plans/FINAL_BASE.json` (version), WP3 REPORT_wave2 (шапка), WP2 REPORT_wave2 §9 |

Примечание: числа ручного скрининга WP2 (волна 1, S01–S25) приводятся в §9 с явной пометкой источника; для топ-5 и FINAL записаны числа ЯДРА (различие ≤0.1%, `reconciliation.csv`). Смешения источников в одной таблице нет.

## 3. Сверка первоисточников (D5) — результаты

Сверялось по `docs/sources_txt/*.txt` (8 файлов) + `docs/ПОСТАНОВКА_КЕЙСА.txt` + `docs/КРИТЕРИИ_ОЦЕНКИ.txt`:

1. **Federgruen/Liu/Lu, POM 31(7):2789–2805 (2022)** — библиографические данные ПОДТВЕРЖДЕНЫ: ссылка [99] в `Supply chain resilience…txt` (Guo et al. 2025): «A. Federgruen, Z. Liu, L. Lu, Dual sourcing: Creating and utilizing flexible capacities with a second supply source, Prod. Oper. Manage. 31 (7) (2022) 2789–2805». **РАСХОЖДЕНИЕ (зафиксировано, не усреднено):** содержимое файла `Dual sourcing Creating and utilizing flexible capacities wit.txt` — текст ДРУГОЙ (родственной) работы тех же авторов: «Dual Sourcing under Internal and External Volatilities» (рабочая версия, Columbia/Imperial/CUHK-Shenzhen; в файле нет ни выходных данных POM 31(7), ни DOI). Обе работы — про пороговые политики dual sourcing (в volatilities-тексте: «Optimality of a common threshold policy»). В evidence map цитируется POM-публикация 2022 (данные подтверждены), точный DOI НЕ заявляется (в первоисточниках репозитория отсутствует; не выдумывать). Пометка «по конспекту оркестратора» снята с оговоркой о содержимом файла.
2. **Tanaka (2014)** — ПОДТВЕРЖДЕНО полностью: Hiroshi Tanaka, «Toward project and program management paradigm in the space of complexity: a case study of mega and complex oil and gas development and infrastructure projects», Procedia — Social and Behavioral Sciences 119 (2014) 65–74, doi: 10.1016/j.sbspro.2014.03.010 (27th IPMA World Congress). «Закон необходимого разнообразия» в статье — через Ashby (1958). Оговорка добавлена: формальной методики real options/гейтов статья не даёт — количественные условия G1–G5 являются расчётом команды. Пометка снята, Tanaka остаётся в цитируемых.
3. **WACC Sommariva** — ПОДТВЕРЖДЕНО: «WACC discount rate 13% (Case 1) / 11.50% (Case 2)»; соотношение цен лунного/земного топлива в их бизнес-модели 5.07 / 10.55 M$/kg (порядок «≈2:1» конспект передавал верно). Пометка снята.
4. **RRM3 Simonini** — ПОДТВЕРЖДЕНО: «Robotic Refueling Mission 3 (RRM3) … four months zero boil-off methane storage by means of a cryocooler» (демонстрация прервана: venting expelled all methane prior to transfer). Пометка снята; добавлена честная деталь (демонстратор не завершил передачу) как мотивация риска R03.
5. **Han et al. (2023), Omega 115:102775** — подтверждено (robust optimization, augmented ε-constraint, параметр консервативности Γ как отношение к риску). Атрибуция Federgruen≠Han сохранена.
6. **Guo et al. (2025)** — подтверждено («capacity reservation … referred to as virtual inventory»).
7. **Linkov et al. (2006)** — подтверждено (весовые механизмы, практика Army Corps of Engineers со «swing»-взвешиванием); doi:10.1016/j.envint.2006.06.013.
8. **Постановка и критерии** — `docs/ПОСТАНОВКА_КЕЙСА.txt` и `docs/КРИТЕРИИ_ОЦЕНКИ.txt` прочитаны полностью; карта критериев перестроена по фактической нумерации 1–20 (20 пунктов, 6 разделов, шкала 0–5) — `00_structure.md`.

## 4. Чек-лист критериев (пункты 6–9, 14–18 по `docs/КРИТЕРИИ_ОЦЕНКИ.txt`)

| № | Критерий | Где закрыт в записке | Gap |
|---|---|---|---|
| 6 | Логика архитектуры расчёта | §1 записки + `01_architecture.md`: 9 блоков (входы/выходы/формулы CR/источник метода/границы), mermaid, таблица блок→функция ядра, трассируемость результата | нет |
| 7 | Методы и научные источники | §3 записки + `03_methods_evidence_map.md`: 12 источников, «где использованы», границы (§3.6), допущения отделены от фактов (TA-реестр), сверка по первоисточникам | нет (расхождение файла Federgruen раскрыто) |
| 8 | Сравнение альтернатив | §5 + `09_strategy_comparison.md`: 25 содержательно разных планов на единой базе; выбор объяснён затратами (PV/cost per t), обеспечением спроса (SL/дефицит/резерв) и гибкостью (MCDA-критерий, опцион); ISRU/сложность баллов «сами по себе» не получают — сравнение только по числам | нет |
| 9 | Инвестиции и контракты | §4, §9 + `04_contracts.md`, `12_roadmap_budget.md`: план инвестиций (1430 млн 2036-06) согласован с расчётами и лимитами; TOP/резервы/lead time учтены в выборе (Q3/Q7/Q8); дорожная карта G1–G5 со сроками и зависимостями; реальные контракты не заключались (не требуется) | нет |
| 14 | Реестр ключевых рисков | §7 + `11_risk_results.md` + `results/risk_register.csv`: 10 планоспецифичных рисков (событие/причина/период/параметр/зависимости/owner), а не «общие риски отрасли» | нет |
| 15 | Количественная оценка последствий | §6–7: каждое последствие рассчитано ядром (т/млн/пункты SL); диапазоны обоснованы (MMOD 10–50% D3.2); вероятности не заявляются и баллы риска не выдаются за ущерб; геополитическая оценка цен — R10/§11 (пример, названный в критерии) | нет |
| 16 | Меры и остаточный риск | §7, §11.4: меры отвечают причинам (перезаказ против довеска), стоимость ΔPV, остаток 0 т/0 нарушений (R01/R02/R04/R08), пределы адаптации; обязательный стресс НЕ оценивается повторно в рисках (R01 — явный combined-контроль) | нет |
| 17 | Интересы и показатели сторон | §8 + `05_stakeholders.md`: 8 сторон (оператор, критические и коммерческие потребители, поставщики A–E, финансирующая сторона), KPI/обязательства/кто несёт затраты; эффекты по сторонам численно (гео: заказчик +337.9 / провайдер A +471.2) | нет |
| 18 | Адаптация к изменению рисков | §5 (MCDA: swing-наборы раскрыты, смена лидера только при весе гибкости >36% — обосновано), §8 (конфликты и компромиссы при стрессе), §11.4 (изменение обязательств при мерах); веса не менялись задним числом и не скрывают ухудшение сервиса (SL показан честно, включая неадаптированный план) | нет |

Gaps: не выявлены. Пункты 19–20 (цифровой контур) — вне записки (демонстрация UI WP4 и экспорты; карта в `00_structure.md`).

## 5. Расхождения источников (зафиксированы, НЕ усреднены)

1. **Файл Federgruen в sources_txt** — содержание не соответствует имени файла (родственная работа «Dual Sourcing under Internal and External Volatilities» вместо POM 31(7):2789–2805). Библиоданные POM подтверждены ссылкой [99] Guo et al.; DOI не заявлен (нет в первоисточниках). §3 п.1.
2. **Ручной расчёт WP2 (волна 1) vs ядро (волна 2)**: для топ-5 расхождение ≤0.1003% (объяснено округлением планов до 0.001 т, `reconciliation.csv`); в записке для топ-5/FINAL использованы числа ЯДРА, для 20 остальных стратегий — числа ручного скрининга (с пометкой источника). Не усреднялось.
3. **Исторические числа WP3 «S10 до FINAL»** (первая редакция REPORT_wave2 WP3: 45 нарушений BASE, PV 9297.6, shortage 49.5) — УСТАРЕЛИ: в записку взяты только актуальные FINAL-числа (merge e4f791c). Упоминание 130.7 т — это актуальный MANDATORY_ON_FIXED_BASE из `P01_summary.csv`, а не устаревшие числа.
4. **PV S25 BASE 9938.1 (ручной, волна 1) vs 9948.01 (ядро)** — в записке использовано число ядра; разница 13.31 млн (0.13%) к S10 сохранена как в WP2 REPORT_wave2 §3.
5. **Combined-аддитивность гео+mandatory**: сумма раздельных дельт 1875.06 ≠ combined-дельта 1959.54 (к BASE) — взаимодействие через TOP/запас раскрыто в §11 записки со ссылкой на `P05_summary.json`; не усреднялось.

## 6. Объём и структура

- `docs/УПРАВЛЕНЧЕСКАЯ_ЗАПИСКА.md`: ~3540 слов, ≈10–11 страниц при типовой вёрстке — в пределах 8–12. Детали вынесены в приложения `docs/note/01–12` (ссылки из текста) и `results/`.
- `RESUME_1page.md` — 1 страница (обязательный элемент), дублирует ключевую таблицу сравнения сценариев (числа идентичны `results/scenario_comparison.md`).

## 7. Отклонения от контрактов / что не менялось

Не изменялись: `src/engine/**`, `data/**`, `configs/**`, контракты `00_contracts/**`, `results/**` (только чтение), чужие WP-папки (кроме чтения). Все изменения WP5 — в `docs/note/`, `docs/УПРАВЛЕНЧЕСКАЯ_ЗАПИСКА.md`, `ai_workstreams/WP5_docs/`. Числа из результатов WP2/WP3 не правились.

## 8. Остаточные замечания оркестратору

1. pandoc в среде исполнителя отсутствует — PDF не собран; записка в markdown (задание допускает).
2. В §9.2 записки таблица скрининга — числа ручного расчёта WP2 волны 1; ядровая проверка 50 фиксированных прогонов (`results/exports/screening_25.csv`) подтверждает статусы исполнимости (BASE S10/S14/S18/S21/S25 — 0 нарушений), но её STRESS-режим `fixed_BASE_plan` (стресс на неизменном BASE-плане) закономерно хуже сценарно-специфичного — в записке использован ручной сценарно-специфичный STRESS (консистентно с топ-5). Расхождений по топ-5 нет (≤0.1%).
3. Вопрос WP3 №2/№3 (R06 no-op; отсутствие MIT_R03/R09) — в записке отражены как есть (честный no-op с журналом; меры не требуются при нулевом остатке).

## 9. Git

Коммит: `wp5: финальная записка` → push `origin wp5-docs`.
