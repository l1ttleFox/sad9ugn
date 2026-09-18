# Словарь данных

Ниже описаны поля стартового набора. Статус всех значений в `data/*.csv` — `CASE_INPUT`. Решения команды хранятся отдельно.

## `data/demand.csv`

| field | meaning | type | unit | status | allowed range | used in | common mistake |
|---|---|---|---|---|---|---|---|
| `year` | год горизонта | integer | год | CASE_INPUT | 2035–2040 в исходном наборе | demand indexing | переносить ограничения после 2040 автоматически |
| `base_total_t` | общий базовый спрос | number | т/год | CASE_INPUT | >=0 | BASE, stress | прибавлять critical ещё раз |
| `base_critical_t` | критическая часть базового спроса | number | т/год | CASE_INPUT | 0..base_total_t | critical service | трактовать как дополнительный спрос |
| `low_total_t` | низкий общий спрос | number | т/год | CASE_INPUT | >=0 | sensitivity | смешивать с mandatory stress без отдельного сценария |
| `high_total_t` | высокий общий спрос | number | т/год | CASE_INPUT | >=0 | sensitivity | считать mandatory stress тем же сценарием |
| `status` | происхождение поля | enum | — | CASE_INPUT | `CASE_INPUT` | provenance | переписывать как team value |

Критический спрос для low/high не хранится отдельной колонкой: постановка требует сохранять долю критического спроса соответствующего базового года.

## `data/supply_sources.csv`

| field | meaning | type | unit | status | allowed range | used in | common mistake |
|---|---|---|---|---|---|---|---|
| `source_id` | короткий ID A–E | string | — | CASE_INPUT | non-empty | joins | подменять human name ID |
| `name` | машинно-стабильное имя | string | — | CASE_INPUT | non-empty | scenario mapping | писать разные варианты имени в разных файлах |
| `capacity_t_per_year` | максимальная мощность | number | т/год | CASE_INPUT | >=0 | capacity validation | считать её поставкой или запасом |
| `variable_cost_mln_per_t` | переменная цена | number | млн у.е./т | CASE_INPUT | >=0 | procurement cost | добавлять ещё launch cost в контрольной модели |
| `reservation_rate_mln_per_t_year_capacity` | годовая ставка за резервируемую мощность | number | млн у.е. за (т/год) мощности | CASE_INPUT | >=0 | reservation payment | путать с variable cost |
| `take_or_pay_share` | минимальная оплачиваемая доля зарезервированного объёма периода | number | share | CASE_INPUT | 0..1 | contract payment | начислять TOP второй раз |
| `lead_time_min_value` | нижняя граница lead time | number | см. unit | CASE_INPUT | >=0 | timing | превращать диапазон в точное число без допущения |
| `lead_time_max_value` | верхняя граница lead time | number | см. unit | CASE_INPUT | >= min | timing | игнорировать верхнюю границу |
| `lead_time_unit` | исходная единица lead time | enum | day/week/month/year | CASE_INPUT | enum | timing conversion | принудительно считать 6 недель = 1.5 месяца |
| `reliability_profile` | профиль надёжности из кейса | string | coefficient metadata | CASE_INPUT | non-empty | risk analysis | использовать как BASE delivery share |
| `available_from_year` | ранний год доступности, если фиксирован | integer/null | год | CASE_INPUT | >=2035 or null | timing | назначать Earth-New фиксированный год |
| `status` | статус данных | enum | — | CASE_INPUT | CASE_INPUT | provenance | — |
| `notes` | предметное пояснение | string | — | CASE_INPUT | free text | interpretation | использовать note как формулу |

## `data/storage_options.csv`

| field | meaning | type | unit | status | allowed range | used in | common mistake |
|---|---|---|---|---|---|---|---|
| `storage_id` | ID режима/опции | string | — | CASE_INPUT | non-empty | storage selection | — |
| `name` | название | string | — | CASE_INPUT | non-empty | UI/docs | — |
| `capacity_t` | физическая ёмкость | number | т | CASE_INPUT | >=0 | overflow check | путать с annual source capacity |
| `loss_rate_on_throughput` | модельная доля потерь от валового поступления | number | share | CASE_INPUT | 0..1 | losses | начислять повторно на тот же остаток |
| `holding_cost_mln_per_t_year` | стоимость среднего физического запаса | number | млн у.е./т-год | CASE_INPUT | >=0 | holding cost | считать от годового спроса вместо stock-time |
| `capex_mln` | CAPEX режима | number | млн у.е. | CASE_INPUT | >=0 | cumulative CAPEX | дублировать с investment row |
| `fixed_opex_mln_per_year` | дополнительный OPEX | number | млн у.е./год | CASE_INPUT | >=0 | cost | забывать после ввода |
| `available_from_year` | ранний год опции | integer | год | CASE_INPUT | >=2035 | timing | считать это автоматическим вводом |
| `status` | статус | enum | — | CASE_INPUT | CASE_INPUT | provenance | — |
| `notes` | пояснение | string | — | CASE_INPUT | free | interpretation | выдавать 1.2% за реальную универсальную ZBO-метрику |

## `data/investment_options.csv`

| field | meaning | type | unit | status | allowed range | used in | common mistake |
|---|---|---|---|---|---|---|---|
| `investment_id` | ID инвестиционной опции | string | — | CASE_INPUT | non-empty | plan decisions | — |
| `name` | название | string | — | CASE_INPUT | non-empty | UI/docs | — |
| `option_fee_mln` | цена права/опциона | number | млн у.е. | CASE_INPUT | >=0 | CAPEX/cash flow | считать total ещё одной строкой |
| `exercise_cost_mln` | стоимость реализации | number | млн у.е. | CASE_INPUT | >=0 | CAPEX/cash flow | — |
| `total_capex_mln` | полный объём вложений по условию | number | млн у.е. | CASE_INPUT | >=0 | validation | складывать с составляющими как дополнительный платёж |
| `commissioning_rule` | условие ввода | string | — | CASE_INPUT | non-empty | timing | читать как рекомендацию инвестировать |
| `fixed_opex_mln_per_year` | OPEX после ввода | number | млн у.е./год | CASE_INPUT | >=0 | cost | — |
| `status` | статус | enum | — | CASE_INPUT | CASE_INPUT | provenance | — |
| `notes` | пояснение | string | — | CASE_INPUT | free | interpretation | — |

## `data/constraints.csv`

| field | meaning | type | unit | status | allowed range | used in | common mistake |
|---|---|---|---|---|---|---|---|
| `constraint_id` | стабильный ID правила | string | — | CASE_INPUT | non-empty | violations | — |
| `metric` | имя проверяемой метрики | string | — | CASE_INPUT | non-empty | validation | путать с UI label |
| `operator` | знак ограничения | enum-like string | — | CASE_INPUT | `>=`, `<=` | validation | инвертировать условие |
| `value` | порог | number | см. unit | CASE_INPUT | depends | validation | менять для удобства плана |
| `unit` | единица | string | — | CASE_INPUT | non-empty | reporting | сравнивать разные единицы |
| `period` | область по времени | string | — | CASE_INPUT | explicit | validation | применять stress constraint до 2038 |
| `scenario` | область сценария | string | — | CASE_INPUT | BASE/ALL/MANDATORY_STRESS | validation | смешивать scenario scope |
| `severity` | обязательность | string | — | CASE_INPUT | `hard` в starter data | reporting | скрывать violation |
| `status` | статус | enum | — | CASE_INPUT | CASE_INPUT | provenance | — |
| `description` | текст правила | string | — | CASE_INPUT | free | human output | заменять машинную проверку текстом |

## Семантические инварианты

```text
base_critical_t is included in base_total_t
reserved capacity is not inventory
ordered volume is not delivered volume
delivered volume is not served demand
reliability is not BASE delivery share
loss_rate_on_throughput is applied to gross inflow in the control model
```

Эти правила не всегда можно выразить одной JSON Schema. Они должны проверяться бизнес-логикой участника и unit/integration tests.
