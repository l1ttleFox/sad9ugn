# Научная и методическая база

Научные источники здесь не используются для «доказательства» синтетических цен, мощностей и лимитов кейса. Для каждой публикации фиксируется более узкая связь: **что источник поддерживает, как это применяется в framework и чего из него выводить нельзя**.

## Evidence map

| Source | What it supports | How it is used in this framework | What it does not support |
|---|---|---|---|
| NASA-STD-7009B, *Standard for Models and Simulations* | credibility, verification, validation, uncertainty/sensitivity and traceable M&S practice | reproducibility, provenance, control cases, explicit assumptions, validation route | не задаёт supply mix, цены, capacities или «правильный» solver |
| Koki Ho (2024), *Space Logistics Modeling and Optimization: Review of the State of the Art*, DOI `10.2514/1.A35982` | space logistics as network-flow/logistics planning, probabilistic performance analysis and inventory control; need to coordinate infrastructure and resources | объясняет, почему depot/inventory/supply/timing следует рассматривать как единую logistics system, а не только как trajectory problem | не определяет числа учебного кейса и не требует одного алгоритма |
| Simonini et al. (2024), *Cryogenic propellant management in space: open challenges and perspectives*, DOI `10.1038/s41526-024-00377-5` | long-duration cryogenic storage/transfer as enabling capability; physical knowledge gaps and multiple CFM operations | предметная мотивация storage, transfer и отдельного отношения к cryogenic losses | не подтверждает, что модельные 4.5% или 1.2% являются универсальными реальными loss rates |
| Sommariva et al. (2023), *Preliminary analyses on technical and economic viability of moon-mined propellant for on-orbit refueling*, DOI `10.1016/j.actaastro.2023.01.004` | technical-economic comparison of Earth- and Moon-supplied propellant to an orbital depot; high uncertainty in investment/OPEX/revenue assumptions | пример того, что lunar-vs-Earth architecture сравнивается на общей economic/technical basis с uncertainty analysis | вывод статьи в пользу lunar supply нельзя переносить как готовый ответ этого синтетического кейса |
| Bertsimas & Sim (2004), *The Price of Robustness*, DOI `10.1287/opre.1030.0065` | trade-off between nominal performance and protection against uncertain data in robust optimization | методическое основание для optional robust analysis и понятия «цены защиты» | robust optimization не является обязательным методом и не создаёт uncertainty set из воздуха |
| Linkov et al. (2006), *From comparative risk assessment to multi-criteria decision analysis and adaptive management*, DOI `10.1016/j.envint.2006.06.013` | structured MCDA, stakeholder value elicitation, adaptive management under uncertainty | объясняет, почему weights/normalization должны быть открыты и почему решение можно пересматривать при новой информации | не даёт готовые веса стейкхолдеров для этого кейса |
| JCGM 101:2008, DOI `10.59161/JCGM101-2008` | propagation of probability distributions through a model using Monte Carlo in measurement uncertainty | ориентир для reproducible Monte Carlo mechanics: specified input distributions, dependence assumptions and numerical procedure | документ относится к measurement uncertainty и не доказывает вероятностную модель supply/economic risks этого кейса |
| Han, Zhang, Wang & Park (2023), *The efficient and stable planning for interrupted supply chain with dual-sourcing strategy: a robust optimization approach considering decision maker's risk attitude*, Omega 115, 102775, DOI `10.1016/j.omega.2022.102775` | dual-source/robust sourcing decisions under disruption and shortage trade-offs | поддерживает анализ диверсификации и стоимости гибкого второго источника как класса решений | не калибрует Earth-Core/Earth-Flex и не доказывает конкретный procurement split |
| Guo, Liu, Song & Wang (2025), *Supply chain resilience: A review from the inventory management perspective*, Fundamental Research 5(2), 450–463, DOI `10.1016/j.fmre.2024.08.002` | inventory prepositioning, multiple sourcing, capacity reservation and flexible contracts as resilience mechanisms | поддерживает раздельное моделирование redundancy, inventory и reservation | не задаёт точные probability, reserve days или capacities в космическом кейсе |
| Kenny, Eddleman, Keplinger, Stephens, Hartwig & Perrin (2025), *Guidelines for In-Space Cryogenic Propellant Transfer* | engineering guidance around in-space cryogenic transfer and early CONOPS | предметный контекст transfer and interface/safety considerations | не является экономическим источником цен/инвестиций кейса и не заменяет детальный engineering design |

## 1. Credibility и проверяемость модели

NASA-STD-7009B используется здесь как официальный ориентир по дисциплине models & simulations. На дату подготовки репозитория NASA Technical Standards System показывает активный `NASA-STD-7009`, Version B, document date 2024-03-05. В 2026 году NASA также выпустила `NASA-HDBK-7009B` как implementation guide к стандарту.

Применение к starter repository ограниченное и практическое: source traceability, verification checks, reproducibility, sensitivity/uncertainty disclosure. Репозиторий не заявляет, что участническая работа обязана проходить формальную NASA certification.

Official links:

- https://standards.nasa.gov/standard/nasa/nasa-std-7009
- https://standards.nasa.gov/standard/NASA/NASA-HDBK-7009

## 2. Space logistics как система потоков и запасов

Обзор Koki Ho выделяет network-flow modeling/optimization, probabilistic modeling/queueing и inventory control как основные logistics-driven классы методов для space applications. Для кейса это оправдывает архитектуру, в которой supply, depot capacity, inventory, timing и demand service рассматриваются совместно.

DOI: https://doi.org/10.2514/1.A35982

Framework при этом остаётся method-neutral: команда может использовать rule-based planning, simulation, LP/MILP, robust methods или другой прозрачный метод.

## 3. Криогенное хранение и transfer

Simonini et al. показывают, что долгосрочное cryogenic storage и on-orbit transfer связаны с большим набором CFM операций и нерешённых физических вопросов. Это поддерживает предметную правдоподобность отдельного storage/loss block.

DOI: https://doi.org/10.1038/s41526-024-00377-5

Из статьи нельзя выводить, что `loss_rate=0.012` — реальная характеристика всех ZBO systems. В starter kit это только `CASE_INPUT`.

## 4. Лунный источник и экономическая неопределённость

Sommariva et al. сравнивают Earth-supplied и Moon-supplied propellant architectures для orbiting depot и используют Monte Carlo из-за высокой неопределённости investment/OPEX/revenue estimates.

DOI: https://doi.org/10.1016/j.actaastro.2023.01.004

Их conclusion относится к их own assumptions. В этом кейсе Lunar-ISRU — одна из альтернатив, а не заранее выбранный winner.

## 5. Robust analysis

Bertsimas & Sim формализуют trade-off between nominal objective and robustness against uncertain data. Это полезная методическая опора для команды, если она строит uncertainty set и хочет показать price of robustness.

DOI: https://doi.org/10.1287/opre.1030.0065

Robust method не заменяет mandatory stress и не даёт права придумывать интервалы без обоснования.

## 6. MCDA и adaptive management

Linkov et al. рассматривают MCDA как structured decision framework и связывают его с stakeholder values и adaptive management under uncertainty.

DOI: https://doi.org/10.1016/j.envint.2006.06.013

В кейсе это отражено правилом: если команда использует MCDA, нужны критерии, normalization, weights, происхождение weights и sensitivity. Starter kit намеренно не задаёт готовый stakeholder preference vector.

## 7. Monte Carlo: метод не заменяет основание входов

JCGM 101:2008 описывает propagation of probability distributions through a mathematical model методом Monte Carlo в контексте measurement uncertainty. Для кейса он полезен как ориентир по воспроизводимой процедуре, если команда уже имеет обоснованные distributions/dependencies.

Official page: https://www.bipm.org/en/doi/10.59161/jcgm101-2008

Ограничение принципиально: документ не создаёт статистику отказов Earth/Lunar channels и не превращает придуманное распределение в факт. Поэтому постановка допускает scenario/interval analysis там, где статистической базы нет.

## 8. Diversification, flexible supply и resilience

Работы Han et al. и Guo et al. полезны не как калькулятор параметров, а как подтверждение класса trade-offs: redundancy и flexible sourcing снижают disruption exposure, но имеют cost; capacity reservation и inventory — разные инструменты resilience.

- Han et al.: https://doi.org/10.1016/j.omega.2022.102775
- Guo et al.: https://doi.org/10.1016/j.fmre.2024.08.002

## 9. ISCPT: не смешивать связанные публикации

Для `Guidelines for In-Space Cryogenic Propellant Transfer` существуют как минимум связанные публичные объекты:

1. NASA NTRS presentation Thomas M. Perrin, `Document ID 20250003540`, 31st Space Cryogenic Workshop: https://ntrs.nasa.gov/citations/20250003540
2. AIAA ASCEND 2025 conference paper Robert J. Kenny, David E. Eddleman, Jacob D. Keplinger, Jonathan R. Stephens, Jason W. Hartwig, Thomas M. Perrin, DOI `10.2514/6.2025-4122`: https://doi.org/10.2514/6.2025-4122
3. Указанная постановщиком NASA NTRS record `20250004625`: https://ntrs.nasa.gov/citations/20250004625

В документации они не выдаются за один и тот же библиографический объект. Presentation используется как подтверждение контекста ISCPT/CFM guidelines; conference paper — как отдельная публикация.

## 10. Что делать с вероятностями

В исходных данных кейса есть reliability coefficients, но нет полной statistical model outages. Поэтому framework не объявляет их Bernoulli probabilities, expected-delivery multipliers или failure rates без дополнительной интерпретации команды.

Если команда использует probability distribution или Monte Carlo, она отдельно обосновывает meaning, dependence and parameter source. При недостатке статистики допустим scenario/interval approach.
