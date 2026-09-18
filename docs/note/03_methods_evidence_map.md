# 3. Методы и научная база (evidence map)

Правило трассируемости (STARTER_README §33): `source → supported proposition/method → use in model/framework → limitation`. Внешняя статья **не заменяет CASE_INPUT** и не используется для «доказательства» синтетических цен/мощностей кейса.

**Доступность первоисточников на момент волны 1:** файлы `G:\Temp\opencode\pdf_txt\*.txt` (постановка кейса, критерии, тексты 8 статей) на рабочем устройстве отсутствуют. Карта построена на: (а) evidence map организатора `docs/SCIENTIFIC_BASIS.md` (10 источников, читан полностью); (б) конспектах оркестратора в `ai_workstreams/WP5_docs/prompt_wave1.md` (атрибуция Federgruen/Han, детали методов). Самостоятельно найденных источников в волне 1 нет; детали, помеченные «конспект оркестратора», подлежат сверке с первоисточниками в волне 2 при появлении доступа к pdf_txt.

## 3.1 ВАЖНО: атрибуция двух близких публикаций (проверено оркестратором)

- Файл «Dual sourcing…» из pdf_txt — это **Federgruen, Liu, Lu** (родственная публикация: *Production and Operations Management*, 31(7): 2789–2805, 2022), **НЕ Han et al.**
- **Han, Zhang, Wang & Park (2023)**, «The efficient and stable planning for interrupted supply chain with dual-sourcing strategy: a robust optimization approach considering decision maker's risk attitude», *Omega*, 115: 102775, DOI `10.1016/j.omega.2022.102775` — это файл «The efficient and stable planning…».

Публикации родственны по теме (dual sourcing), поэтому в тексте записки каждая ссылка даётся с полным именем: «Federgruen, Liu, Lu (2022)» или «Han et al. (2023)» — никогда не «Han» для пороговых политик и не «Federgruen» для robust-планирования.

## 3.2 Evidence map: материалы постановщика (10 источников SCIENTIFIC_BASIS.md)

| Источник | Поддерживаемое положение/метод | Реализация в нашей модели | Ограничение применимости |
|---|---|---|---|
| NASA-STD-7009B, *Standard for Models and Simulations* (версия B, doc. date 2024-03-05; implementation guide NASA-HDBK-7009B, 2026) | credibility, verification/validation, uncertainty/sensitivity, трассируемая практика M&S | воспроизводимость (детерминированный `run_plan`), provenance (CASE_INPUT vs TEAM_*), контрольные тесты V01–V10, явный реестр допущений TA-01…TA-09 | не задаёт supply mix, цены, capacities или «правильный» solver; формальная NASA-сертификация работы команды не заявляется |
| Ho, K. (2024), *Space Logistics Modeling and Optimization: Review of the State of the Art*, DOI `10.2514/1.A35982` | space logistics как network-flow/logistics planning + probabilistic analysis + inventory control; инфраструктура и ресурсы координируются совместно | классовая принадлежность нашей модели: depot/inventory/supply/timing/demand — единая логистическая система (архитектура «данные → решения → поставки → баланс → сервис», `01_architecture.md`); framework method-neutral | не определяет числа учебного кейса и не требует одного алгоритма |
| Simonini et al. (2024), *Cryogenic propellant management in space: open challenges and perspectives*, npj Microgravity, DOI `10.1038/s41526-024-00377-5` | долгосрочное криогенное хранение/передача — enabling capability; физика boil-off; нерешённые физические вопросы и набор CFM-операций; ZBO-демонстратор класса RRM3 (деталь по конспекту оркестратора) | предметная мотивация отдельного блока хранения и потерь: два режима (4.5% base / 1.2% ZBO) начисляются на throughput один раз (CR §3); ZBO как инвестиционная опция с 2036 | не подтверждает, что модельные 4.5% или 1.2% — универсальные реальные loss rates; это только CASE_INPUT |
| Sommariva et al. (2023), *Preliminary analyses on technical and economic viability of moon-mined propellant for on-orbit refueling*, Acta Astronautica, DOI `10.1016/j.actaastro.2023.01.004` | технико-экономическое сравнение Earth- и Moon-supplied propellant для орбитального депо; Monte Carlo из-за высокой неопределённости investment/OPEX/revenue; WACC космических проектов 11.5–13%; экономика Луна/Земля ~2:1 (последние два числа — по конспекту оркестратора) | обоснование ставки дисконтирования TA-06 (10% реальная, t0=2035 — консервативное округление диапазона WACC вниз); Обоснованность сравнения Lunar-ISRU (D, 3.0 млн/т) с земными каналами (A/B/C) на единой PV-базе; структура финансирования как опция (`04_contracts.md`) | их conclusion в пользу lunar supply относится к их own assumptions и не переносится как готовый ответ синтетического кейса; у нас Lunar-ISRU — одна из альтернатив, а не заранее выбранный winner |
| Bertsimas, D., Sim, M. (2004), *The Price of Robustness*, Operations Research, DOI `10.1287/opre.1030.0065` | trade-off «номинальная эффективность vs защита от неопределённых данных»; понятие «цены защиты» | методическая опора optional robust-анализа в блоке рисков (WP3): «сколько стоит робастность» — `[[WP2:Q5_robustness_price]]` | robust optimization не обязателен и не создаёт uncertainty set «из воздуха»; интервалы без обоснования недопустимы |
| Linkov, I. et al. (2006), *From comparative risk assessment to multi-criteria decision analysis and adaptive management*, Environment International, DOI `10.1016/j.envint.2006.06.013` | структурированный MCDA, elicitation ценностей стейкхолдеров, adaptive management в условиях неопределённости; swing-weighting (деталь по конспекту оркестратора) | MCDA-рамка выбора финальной стратегии (`05_stakeholders.md`): критерии, нормализация, происхождение весов, правило пересмотра; веса и ранжирование — `[[WP2:mcda_result]]` | не даёт готовые веса стейкхолдеров для этого кейса — starter kit намеренно не задаёт preference vector; веса раскрываются командой |
| JCGM 101:2008, DOI `10.59161/JCGM101-2008` | propagation of probability distributions through a model методом Monte Carlo | ориентир воспроизводимой MC-процедуры: заданные распределения входов, явные зависимости, seed в meta (STRESS_PROTOCOL) | документ про measurement uncertainty; не доказывает вероятностную модель supply/economic рисков кейса и не превращает придуманное распределение в факт |
| Han, Zhang, Wang & Park (2023), *The efficient and stable planning for interrupted supply chain with dual-sourcing strategy: a robust optimization approach…*, Omega 115: 102775, DOI `10.1016/j.omega.2022.102775` | robust-планирование dual sourcing при сбоях с учётом отношения к риску ЛПР; Γ-robust / ε-constraint Парето-подход (детали метода — по конспекту оркестратора) | анализ диверсификации и стоимости гибкого второго источника как класса решений: каналы A (дешёвый, длинный lead time, TOP 70%) и B (дорогой, короткий, без TOP) — наш аналог dual sourcing; стресс-тестирование на сбоях ISRU | не калибрует Earth-Core/Earth-Flex и не доказывает конкретный procurement split кейса |
| Guo, Liu, Song & Wang (2025), *Supply chain resilience: A review from the inventory management perspective*, Fundamental Research 5(2): 450–463, DOI `10.1016/j.fmre.2024.08.002` | resilience-механизмы: prepositioning запасов, multiple sourcing, capacity reservation, гибкие контракты; capacity reservation ≈ virtual inventory; запасы «мостят» lead time (формулировки по конспекту оркестратора) | раздельное моделирование трёх инструментов: (1) физический запас (inventory_policy), (2) резервирование мощности A/B/C/E (capacity_reservations + ReservationPayment), (3) множественность источников; контрактный Emergency-резерв как эквивалент физического (S22 vs S21) | не задаёт точные probability, reserve days или capacities космического кейса |
| Kenny, Eddleman, Keplinger, Stephens, Hartwig & Perrin (2025), *Guidelines for In-Space Cryogenic Propellant Transfer*, AIAA ASCEND 2025, DOI `10.2514/6.2025-4122` (отдельно: презентация Perrin, NASA NTRS 20250003540, и запись NTRS 20250004625 — НЕ один библиографический объект, SCIENTIFIC_BASIS §9) | engineering-контекст in-space криогенной передачи, интерфейсы и безопасность | предметный контекст блока хранения/передачи записки (качественно) | не экономический источник цен/инвестиций кейса; не заменяет детальный engineering design |

## 3.3 Дополнительные источники по конспектам оркестратора (сверх evidence map постановщика)

| Источник | Поддерживаемое положение | Реализация в модели | Ограничение / статус |
|---|---|---|---|
| Federgruen, A., Liu, L., Lu, L. (2022), dual sourcing, *Production and Operations Management*, 31(7): 2789–2805 | пороговые политики dual sourcing (когда и в каком объёме переключаться между дорогим коротким и дешёвым длинным каналом) | логика семейств стратегий S01–S04 (A+B микс, Flex-first): профиль «дешёвый базовый A с TOP + гибкий B для пиков» и политики переключения при стрессе | DOI и полный текст не сверены (pdf_txt недоступен) — библиографические данные привести по первоисточнику в волне 2; НЕ приписывать этой работе robust/Γ-метод (это Han et al. 2023) |
| Tanaka (2014), мегапроекты (по конспекту оркестратора) | инвестиционные гейты (decision gates), опционный подход к мегапроектам, «закон необходимого разнообразия» (управляющая система должна быть не проще управляемой) | структура инвестиционных ворот G1–G4 (`04_contracts.md`); Earth-New как реальный опцион (90 + 270); разнообразие каналов как ответ разнообразию сценариев; структура финансирования как опция | полные библиографические данные и DOI не верифицированы (pdf_txt недоступен); в волне 2 — сверить или перенести в «конспект оркестратора» без цитирования конкретных положений как фактов публикации |

## 3.4 Самостоятельно найденные источники

В волне 1 — **отсутствуют**. Все записи выше происходят либо из evidence map организатора (`docs/SCIENTIFIC_BASIS.md`), либо из конспектов оркестратора (prompt_wave1.md). При доступе к `G:\Temp\opencode\pdf_txt\` в волне 2 каждый источник сверяется с первоисточником; цитирование статей, которые команда не читала, запрещено (prompt_wave1 «Что НЕ делать»).

## 3.5 Библиография

Материалы постановщика (evidence map, `docs/SCIENTIFIC_BASIS.md`):

1. NASA-STD-7009, Version B, *Standard for Models and Simulations*, document date 2024-03-05; NASA-HDBK-7009B (2026). https://standards.nasa.gov/standard/nasa/nasa-std-7009
2. Ho, K. (2024). Space Logistics Modeling and Optimization: Review of the State of the Art. DOI: `10.2514/1.A35982`.
3. Simonini, L. et al. (2024). Cryogenic propellant management in space: open challenges and perspectives. npj Microgravity. DOI: `10.1038/s41526-024-00377-5`.
4. Sommariva, C. et al. (2023). Preliminary analyses on technical and economic viability of moon-mined propellant for on-orbit refueling. Acta Astronautica. DOI: `10.1016/j.actaastro.2023.01.004`.
5. Bertsimas, D., Sim, M. (2004). The Price of Robustness. Operations Research. DOI: `10.1287/opre.1030.0065`.
6. Linkov, I. et al. (2006). From comparative risk assessment to multi-criteria decision analysis and adaptive management. Environment International. DOI: `10.1016/j.envint.2006.06.013`.
7. JCGM 101:2008. Evaluation of measurement data — Supplement 1 to the GUM: Propagation of distributions using a Monte Carlo method. DOI: `10.59161/JCGM101-2008`.
8. Han, Zhang, Wang & Park (2023). The efficient and stable planning for interrupted supply chain with dual-sourcing strategy: a robust optimization approach considering decision maker's risk attitude. Omega, 115: 102775. DOI: `10.1016/j.omega.2022.102775`.
9. Guo, Liu, Song & Wang (2025). Supply chain resilience: A review from the inventory management perspective. Fundamental Research, 5(2): 450–463. DOI: `10.1016/j.fmre.2024.08.002`.
10. Kenny, R.J., Eddleman, D.E., Keplinger, J.D., Stephens, J.R., Hartwig, J.W., Perrin, T.M. (2025). Guidelines for In-Space Cryogenic Propellant Transfer. AIAA ASCEND 2025. DOI: `10.2514/6.2025-4122`. Смежные объекты: презентация Perrin T.M., NASA NTRS Document ID 20250003540 (31st Space Cryogenic Workshop); запись NASA NTRS 20250004625 (указана постановщиком).

По конспектам оркестратора (детали сверить в волне 2):

11. Federgruen, A., Liu, L., Lu, L. (2022). Dual sourcing. Production and Operations Management, 31(7): 2789–2805. [DOI — сверить по первоисточнику; НЕ Han et al.]
12. Tanaka (2014). [полное название и издание — сверить по первоисточнику] — мегапроекты: гейты, опционы, закон необходимого разнообразия.

## 3.6 Что из источников выводить нельзя (сводно)

- Синтетические цены, мощности и лимиты кейса не «доказываются» статьями — это CASE_INPUT.
- `loss_rate` 4.5%/1.2% — модельные коэффициенты, а не реальные характеристики ZBO (Simonini).
- Reliability-коэффициенты CASE_INPUT — не готовые Bernoulli-вероятности и не failure rates без интерпретации команды (SCIENTIFIC_BASIS §10).
- Вывод Sommariva в пользу лунного топлива — не готовый ответ кейса.
- Han et al. не калибрует конкретный procurement split Earth-Core/Earth-Flex.
- Monte Carlo (JCGM 101) не создаёт статистику отказов каналов из ничего.
