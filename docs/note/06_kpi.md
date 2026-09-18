# 6. KPI надёжности и экономики

Все формулы — из `docs/CALCULATION_RULES.md` (CR) и контракта `units_and_conventions.md`; целевые значения — из `data/constraints.csv` (CASE_INPUT). Способ контроля — расчётное ядро `run_plan` + экспорт (те же числа в UI, экспорте и записке — критерий 5 оценки). Значения по финальной стратегии подставляет волна 2.

## 6.1 KPI надёжности

| KPI | Формула | Цель | Способ контроля | Значения (финальная стратегия) |
|---|---|---|---|---|
| **SL_total** (уровень обслуживания общий, по годам) | `SL_total = served_total / demand_total` (CR §7) | ≥ 0.97 ежегодно (BASE, hard); в стрессе — ориентир устойчивости | `calculate_service`; проверка BASE_TOTAL_SERVICE | BASE: `[[WP3:SL_stress_final]]`; STRESS: там же |
| **SL_critical** (критический спрос) | `SL_critical = served_critical / demand_critical` (CR §7) | ≥ 0.99 ежегодно (BASE, hard); в стрессе — ориентир | `calculate_service`; аллокация — сначала критический (units §5); проверка BASE_CRITICAL_SERVICE | там же |
| **Reserve coverage days** (покрытие 45-дневного резерва) | `R_y = D_y * 45 / 365` — требуемый эквивалент; факт — физический запас на начало года либо доказанный контрактный Emergency (CR §4, units §6) | ≥ 45 дней ежегодно, от спроса ДАННОГО сценария | `check_constraints`; RESERVE_45D; для E — покрытие периода ожидания 42 дня | `[[WP3:reserve45_checks]]` |
| **Shortage** (дефицит) | `Shortage = max(0, Demand - Q_served)` (CR §2) | 0 в BASE; в стрессе — минимизировать и показать численно | помесячно `calculate_inventory`; годовая сводка в экспорте yearly_balance | `[[WP3:shortage_2038_stress]]` |
| **Losses / throughput** (потери) | `Losses = Throughput * loss_rate` действующего режима (CR §3); KPI — отношение losses/throughput | ≤ 0.02 в 2038–2040 (MANDATORY_STRESS, hard); 4.5% base / 1.2% ZBO — режимные коэффициенты | помесячно; STRESS_LOSS_LIMIT; ZBO вводится с месяца после платежа (TA-05) | `[[WP3:loss_ceiling_check]]` |
| **I_end ≥ 0 и I_end ≤ storage_capacity** | физическое состояние баланса; переполнение — нарушение (CR §1, §13) | без отрицательного запаса и без STORAGE_OVERFLOW каждый месяц | `calculate_inventory` + `check_constraints` | в составе `[[WP3:stress_table_by_years]]` |
| **Время реакции** | lead times каналов (CASE_INPUT): E — 42 дня (TA-03), B — 4 мес, D — 1–2 мес (политика 2), A — 12 мес, C — 18–24 мес (политика 24, TA-02) | окно реакции ≤ окно дефицита: разрыв покрывается каналом, успевающим до исчерпания запаса | `calculate_deliveries`; reverse stress на задержку | `[[WP3:lead_time_reaction]]` |

## 6.2 KPI экономики

| KPI | Формула | Цель | Способ контроля | Значения (финальная стратегия) |
|---|---|---|---|---|
| **PV расходов** | `PV_t = CF_t / (1 + r)^(t - t0)`, r = 0.10 реальная, t0 = 2035, конец года (CR §9; TA-06, TA-07) | минимальный среди допустимых стратегий на единой ставке; чувствительность 5–15% | `calculate_costs`; все альтернативы на одной ставке | BASE: `[[WP2:PV_final_BASE]]`; STRESS: `[[WP2:PV_final_STRESS]]` |
| **TotalCost** | `TotalCost = Procurement + Reservation + Holding + FixedOPEX + CAPEX` (CR §8); каждый компонент один раз; выручки и стоимости срыва миссии НЕТ | — | `calculate_costs`; financial_breakdown в экспорте | в составе `[[WP2:top5_comparison]]` |
| **Cost per served ton** | `TotalCost / served_total` (производная от CR §8 и §7) | минимизация; сравнение каналов: D 3.0 < A 6.2 < C 7.1 < B 8.9 < E 13.8 млн/т (CASE_INPUT) | экспорт financial_breakdown + yearly_balance | BASE: `[[WP2:cost_per_served_t_BASE]]`; STRESS: `[[WP2:cost_per_served_t_STRESS]]` |
| **TOP burn** (переплата сверх отбора) | справочная метрика `take_or_pay_extra_mln` = `price * (Q_pay − Q_order)` при `Q_pay = max(Q_order, TOP_share * Q_reserved)` (CR §5, units §7); TOP не прибавляется вторым платежом | минимизировать в ранние годы низкого спроса | `calculate_costs`; по каналам A (70%) и C (50% после ввода) | `[[WP2:TOP_burn_final]]` |
| **CAPEX headroom** | `1800 − Σ CAPEX(payment_date ≤ 2037-12)` и `2800 − Σ CAPEX(≤ 2040-12)` (constraints.csv; units §8) | > 0 (hard); запас < 50 млн — фактор риска перерасхода | `check_constraints`; CAPEX_2037 / CAPEX_2040; EARTH_NEW = 90+270=360, третьего платежа нет | `[[WP2:Q8_capex_headroom]]` |
| **Reservation payments** | `ReservationPayment = reservation_rate * annual_reserved_capacity * period_fraction` (CR §6) | минимизация при сохранении доступности | prorata неполного года; не дублировать годовой платёж по месяцам | в составе `[[WP2:top5_comparison]]` |
| **Стоимость робастности** | PV(робастная стратегия) − PV(рабочая) против выигрыша в shortage стресса; «цена защиты» по Bertsimas & Sim (2004) | обоснованный trade-off, не «робастность любой ценой» | compare_scenarios; скрининг S20/S21 | `[[WP2:Q5_robustness_price]]` |
| **Ценность опциона Earth-New** | разница стоимостей адаптивной и неадаптивной ветвей против платы 90 млн (CR §12: 90+270=360) | > 0 при сохранении CAPEX headroom | ветви S16/S25 с явным правилом ветвления | `[[WP2:option_value_C]]` |

## 6.3 Правила контроля KPI

1. **Ежегодность:** SL, резерв 45 дней, CAPEX-лимиты — по каждому году 2035–2040 в данном сценарии; внутригодовой shortage и overflow — помесячно (CR §10 требует дискретизации, их обнаруживающей).
2. **Сценарность:** KPI в BASE и MANDATORY_STRESS считаются от спроса/цен ДАННОГО сценария; сравнение — на одном плане или с явно показанной адаптацией (STRESS_PROTOCOL).
3. **Нарушение — не ремонт:** если KPI не достигается (особенно SL в стрессе), система показывает дефицит, период, величину и причину; исходные данные задним числом не увеличиваются (units §9, CASE_RULES §4).
4. **Трассируемость:** каждое число KPI в записке происходит из экспорта `export_results` (yearly_balance, financial_breakdown, constraint_checks, risk_register) — таблица трассировки в REPORT волны 2.
