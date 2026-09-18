# Контрольные правила расчёта

Этот документ задаёт минимальную семантику, по которой можно проверить цифровой контур. Он не задаёт стратегию закупок, оптимизатор или инвестиционный выбор.

## 1. Материальный баланс

```text
I_end = I_start + Q_delivered - Losses - Q_served
```

Единицы всех величин — тонны для одного и того же временного периода.

- `I_start` — физический запас на начало периода;
- `Q_delivered` — фактически поступивший валовый объём;
- `Losses` — модельные потери текущего периода;
- `Q_served` — объём, выданный потребителям;
- `I_end` — физический остаток.

Boundary condition: `I_end >= 0` как физическое состояние. Если ресурсов не хватает, дефицит выводится отдельно.

## 2. Дефицит

```text
Shortage = max(0, Demand - Q_served)
```

`Shortage` измеряется в тоннах. Отрицательный inventory не используется как обозначение shortage.

См. synthetic cases V01 и V02 в `validation/control_cases.md`.

## 3. Потери

```text
Throughput = gross inflow during the period
Losses = Throughput * loss_rate
```

`loss_rate` — доля, `Throughput` — тонны, поэтому `Losses` — тонны.

В контрольной модели один и тот же механизм потерь применяется один раз к валовому поступлению. Если после этого тем же коэффициентом уменьшить closing inventory без отдельного физического механизма, получится double counting.

## 4. 45-дневный резерв

```text
R_y = D_y * 45 / 365
```

- `D_y` — общий спрос соответствующего года и сценария;
- `R_y` — требуемый эквивалент 45 дней, т.

Для organiser control conversion используется 365 дней. Физический запас проверяется на начало года. Договорный Emergency может считаться эквивалентом только если команда показывает достаточный объём и срок прибытия, закрывающий период ожидания.

## 5. Take-or-pay

Для договорного периода:

```text
Q_pay = max(Q_order, take_or_pay_share * Q_reserved_period)
VariablePayment = price * Q_pay
```

Единицы:

- `Q_order`, `Q_reserved_period`, `Q_pay` — т;
- `price` — млн у.е./т;
- `VariablePayment` — млн у.е.

Минимальный оплачиваемый объём уже учтён внутри `max(...)`. Не добавляйте take-or-pay вторым отдельным платежом поверх `VariablePayment`.

## 6. Плата за резервирование мощности

Для полного или неполного года:

```text
ReservationPayment = reservation_rate * annual_reserved_capacity * period_fraction
```

- `reservation_rate` — млн у.е. за единицу т/год резервируемой мощности;
- `annual_reserved_capacity` — т/год;
- `period_fraction` — доля года;
- результат — млн у.е.

Если команда использует более мелкий временной шаг, она обязана не дублировать годовой reservation charge по каждому месяцу.

## 7. Service level

```text
SL_total = served_total / demand_total
SL_critical = served_critical / demand_critical
```

Обе величины — доли 0..1 при положительном спросе.

В BASE проверяются ежегодные минимумы:

```text
SL_total >= 0.97
SL_critical >= 0.99
```

Критический спрос входит в общий. Следовательно, `served_critical` также входит в `served_total`.

Boundary case при нулевом спросе должен быть определён реализацией явно; нельзя получать неинтерпретируемый division-by-zero.

## 8. Полная стоимость

Минимальное разложение:

```text
TotalCost = Procurement + Reservation + Holding + FixedOPEX + CAPEX
```

Где каждый компонент считается один раз. Условие кейса не задаёт выручку и стоимость провала миссии, поэтому такие величины нельзя добавлять в контрольный TotalCost как organiser fact.

### Holding cost

В постановке стоимость хранения задана в млн у.е./т-год. База — средний физический запас с учётом времени. Реализация может использовать интеграл/сумму по выбранному timestep, но должна раскрыть метод.

## 9. Дисконтирование

Если команда использует NPV/discounted cost:

```text
PV_t = CF_t / (1 + r)^(t - t0)
```

- `r` — раскрытая реальная ставка;
- `t0` — раскрытый момент приведения;
- все альтернативы сравниваются на одной ставке и базе цен.

Если ставка не задана организатором, она относится к `TEAM_ASSUMPTION`.

## 10. Lead time и временной шаг

Команда выбирает внутренний timestep сама. Он должен быть достаточно подробным, чтобы:

- учитывать 6-недельный Emergency lead time;
- различать 4 месяца Earth-Flex и 12 месяцев Earth-Core;
- учитывать диапазоны Earth-New 18–24 месяца и Lunar-ISRU 1–2 месяца после ввода;
- обнаруживать внутригодовой shortage;
- обнаруживать storage overflow;
- корректно prorate reservation charges и holding cost.

Starter data сохраняет исходную единицу lead time. Если модель переводит недели/месяцы в дни, конвенция conversion становится явным implementation assumption.

## 11. Reliability

Контрольный BASE детерминирован:

```text
Wrong for BASE: delivered = planned * reliability
```

Своевременно заказанные доступные плановые объёмы поступают по плану. Reliability анализируется отдельно как риск с раскрытым математическим смыслом.

Точно так же mandatory stress ISRU 55%/75% не умножается повторно на reliability.

## 12. Earth-New CAPEX

Контрольная трактовка:

```text
90 + 270 = 360 mln units
```

`360` — итоговая стоимость механизма, а не дополнительный третий платёж.

## 13. Capacity и storage checks

Минимально нужны независимые проверки:

```text
reserved_capacity <= source_capacity
scheduled/offtake volume <= contractually available volume under team's model
physical_inventory <= active_storage_capacity
```

Если violation возникает, его следует показывать как отдельный результат с периодом и величиной excess.

## 14. Emergency

Emergency нельзя использовать как основу снабжения более двух последовательных лет. Кроме annual capacity, модель должна учитывать шестинедельный lead time. Штраф или денежная компенсация не создают физический ресурс.

## 15. Частичные периоды и ежегодные обязательства

Annual take-or-pay и reservation semantics не нужно автоматически превращать в независимые ежемесячные минимумы. Если команда моделирует отдельный контракт с другой периодичностью как research extension, это должно быть явно отделено от organiser control rules.
