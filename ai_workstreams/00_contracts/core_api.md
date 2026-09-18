# КОНТРАКТ v1.0 — API расчётного ядра (core_api)

Статус: **ЗАМОРОЖЕН**. Изменения только через оркестратора с bumps версии (v1.1, v2.0...).
Все WP-исполнители обязаны следовать этому контракту. Идентификаторы функций и полей — на английском (соответствуют схемам организатора), документация и комментарии — на русском.

## Модуль: `src/engine/`

Расчётное ядро — чистый Python 3.12+, без зависимостей от UI. Допустимые зависимости: `pandas`, стандартная библиотека.

```
src/engine/
├── __init__.py
├── loader.py        # load_case, load_plan, load_scenario
├── validator.py     # validate_case, validate_plan
├── scenario.py      # apply_scenario
├── deliveries.py    # calculate_deliveries
├── inventory.py     # calculate_inventory, calculate_service
├── finance.py       # calculate_costs
├── constraints.py   # check_constraints
├── risks.py         # evaluate_risks
├── compare.py       # compare_scenarios
├── persistence.py   # save_plan, load_saved_plan
└── export.py        # export_results
```

## Сигнатуры функций (обязательны к реализации в WP1)

```python
def load_case(data_dir: str) -> CaseData:
    """Загрузка CASE_INPUT: demand.csv, supply_sources.csv, storage_options.csv,
    investment_options.csv, constraints.csv. Валидация по схемам data/schemas/.
    Бросает CaseLoadError с понятным сообщением при неполном/противоречивом вводе."""

def validate_case(case: CaseData) -> list[Violation]:
    """Проверка целостности данных (схемы, неотрицательность, вложенность critical в total)."""

def load_scenario(config_path: str) -> Scenario:
    """Загрузка BASE / MANDATORY_STRESS / TEAM_* из configs/*.yaml."""

def load_plan(plan_path: str) -> Plan:
    """Загрузка плана из JSON по схеме plan_format.json."""

def validate_plan(plan: Plan, case: CaseData) -> list[Violation]:
    """Статические проверки плана БЕЗ расчёта: reserved <= capacity,
    инвестиции существуют в каталоге, годы в диапазоне горизонта и т.п."""

def apply_scenario(case: CaseData, scenario: Scenario) -> CaseData:
    """Возвращает НОВЫЙ CaseData с применёнными множителями сценария
    (спрос, цены, фактические доли поставки, потолок потерь).
    Исходный case не мутируется."""

def calculate_deliveries(case: CaseData, plan: Plan) -> DeliveriesResult:
    """Помесячные поставки: заказ -> lead time -> доставка.
    В BASE детерминированно (reliability НЕ умножается!).
    actual_delivery_share из сценария применяется к фактическим объёмам."""

def calculate_inventory(case: CaseData, plan: Plan, deliveries: DeliveriesResult) -> InventoryResult:
    """Помесячный материальный баланс: I_end = I_start + Q_delivered - Losses - Q_served.
    Потери = throughput периода * loss_rate действующего режима.
    I_end >= 0; shortage отдельной метрикой. Ёмкость проверяется каждый месяц."""

def calculate_service(case: CaseData, inventory: InventoryResult) -> ServiceResult:
    """SL_total, SL_critical по годам (общий и критический отдельно).
    Аллокация при дефиците: сначала критический спрос (политика зафиксирована в units_and_conventions.md)."""

def calculate_costs(case: CaseData, plan: Plan, deliveries: DeliveriesResult,
                    inventory: InventoryResult) -> CostResult:
    """Переменные платежи (с take-or-pay через max), резервирование, хранение,
    фиксированный OPEX, CAPEX по датам, дисконтирование (r=0.10, t0=2035)."""

def check_constraints(case: CaseData, plan: Plan, inventory: InventoryResult,
                      service: ServiceResult, costs: CostResult) -> list[Violation]:
    """Все ограничения constraints.csv + правила CASE_RULES.md.
    Каждая Violation содержит: rule_id, year/month, факт, лимит, excess, описание на русском."""

def evaluate_risks(case: CaseData, plan: Plan, base_result: RunResult,
                   risk_scenarios: list[Scenario]) -> RiskReport:
    """Прогон TEAM_* риск-сценариев из реестра; последствия в тоннах, млн у.е., пунктах SL."""

def compare_scenarios(results: dict[str, RunResult]) -> ComparisonResult:
    """Сопоставление BASE vs STRESS vs TEAM_*: расходы, SL, запасы, дефицит, нарушения."""

def save_plan(plan: Plan, path: str) -> None: ...
def load_saved_plan(path: str) -> Plan: ...

def export_results(result: RunResult, path: str, fmt: str = "csv") -> list[str]:
    """Выгрузка по export.schema.json: yearly_balance, source_schedule, inventory_trace,
    financial_breakdown, constraint_checks, risk_register. Возвращает список созданных файлов."""

def run_plan(case: CaseData, plan: Plan, scenario: Scenario) -> RunResult:
    """ГЛАВНАЯ ТОЧКА ВХОДА: полный прогон = apply_scenario -> deliveries -> inventory ->
    service -> costs -> constraints. Используется UI, тестами и экспортом ЕДИНООБРАЗНО."""
```

## Типы данных (dataclasses, определены в `src/engine/models.py`)

Точные поля — в `result_format.json` и `plan_format.json` (соседние файлы). Ключевые правила:

- `RunResult` — единый конверт результата: `scenario_id, plan_id, deliveries, inventory, service, costs, violations, meta`.
- `Violation` — `rule_id: str, period: str ("2038" или "2038-06"), actual: float, limit: float, excess: float, message_ru: str`.
- Все денежные поля — млн у.е. в постоянных ценах 2035 г.; все объёмы — тонны; все периоды — `YYYY` или `YYYY-MM`.

## Обязательства исполнителей

1. WP1 реализует все функции точно по этим сигнатурам.
2. WP4 (UI) вызывает ТОЛЬКО `run_plan`, `export_results`, `save_plan/load_saved_plan`, `compare_scenarios` — не лезет во внутренности.
3. WP2/WP3 используют `run_plan` и свои собственные независимые расчёты (для сверки).
4. Любая функция при недопустимом вводе бросает исключение с сообщением на русском, называющим недостающий/конфликтующий параметр (требование кейса), — никогда не возвращает «тихий» некорректный результат.
