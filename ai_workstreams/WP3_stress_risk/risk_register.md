# Реестр рисков WP3, волна 1

Риски условны; значения задают тяжесть теста, не вероятность события. Формулы используют фиксированный план; фактические последствия считаются ядром в волне 2. `Q_pay` включает take-or-pay. Прямые потери в тоннах могут превращаться в дефицит только после пересчёта запасов и альтернативных поставок.

| ID | Событие | Вход модели | Количественная оценка до прогона |
|---|---|---|---|
| R01 | Поставка ISRU ниже обязательных 55% | `configs/team/TEAM_ISRU_UNDERDELIVERY_COMBINED.yaml / actual_delivery_share.Lunar-ISRU.2038` | 0.15 × Q_D,plan,2038 т недопоставки |
| R02 | Ввод ISRU сдвигается на 2039 | `configs/team/TEAM_ISRU_DELAY.yaml / scenario_parameters.commissioning_override` | Q_D,plan,2038 т недопоставки; до 120 т/год мощности |
| R03 | Отказ ZBO-криокулера | `configs/team/TEAM_ZBO_FAILURE.yaml / scenario_parameters.storage_loss_override` | 0.033 × throughput_2038 т дополнительных потерь |
| R04 | MMOD-пробой ёмкости | `configs/team/TEAM_MMOD.yaml / scenario_parameters.inventory_shock` | 0.25 × I_start,2038-07 т разовой потери |
| R05 | Аварийная цена E выше тарифа | `configs/team/TEAM_PRICE_SPIKE_E.yaml / variable_price_multiplier.Emergency.2038,2039` | 3.45 × Q_pay,E,2038:2039 млн дополнительных расходов |
| R06 | Позднее исполнение опциона C | `configs/team/TEAM_EARTH_NEW_EXERCISE_DELAY.yaml / scenario_parameters.plan_investment_shift` | до min(130, Q_C,plan,2039) т неуспевшей мощности за год |
| R07 | Смета ISRU превышена на 15% | `configs/team/TEAM_CAPEX_OVERRUN.yaml / scenario_parameters.investment_capex_override` | 187.5 млн дополнительных CAPEX; проверить лимит 1800 |
| R08 | Канал A теряет мощность | `configs/team/TEAM_CHANNEL_A_CAPACITY.yaml / scenario_parameters.source_capacity_override` | до 38 т дефицита мощности при полной резервации |
| R09 | Деградация MLI базового хранения | `configs/team/TEAM_MLI_DEGRADATION.yaml / scenario_parameters.storage_loss_override` | 0.015 × throughput_2036:2037 т дополнительных потерь |
| R10 | Геополитический тариф канала A | `configs/team/TEAM_GEO_CHANNEL_A.yaml / variable_price_multiplier.Earth-Core.2038,2039` | 1.24 × Q_pay,A,2038:2039 млн дополнительных расходов |

## Правило реализации

Поля `scenario_parameters` расширяют открытую JSON-схему, но текущее API WP1 перечисляет только множители спроса, цен, доли фактической доставки и потолок потерь. Адаптер волны 2 должен применить эти поля к **копии** CaseData/Plan до `run_plan`, сверить исходное значение и отказать при несовпадении. R01 требует отдельного явно именованного combined-сценария с обязательным стрессом; R06 требует отдельной версии плана. R08/R09 имеют отдельные TEAM-файлы с явными полями для адаптера волны 2.
