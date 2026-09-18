# -*- coding: utf-8 -*-
"""
WP2 manual_calc — определения 25 кандидатных стратегий S01–S25 (prompt_wave1.md).

Резервирование мощностей — TEAM_DECISION (объём заказа/резерва выбирает команда).
Политика заказов — единый demand-chasing (см. mc_model.py). E — реактивный.

Ключевые ёмкостные факты (CASE_INPUT):
  A=190, B=110, C=130, D=120, E=80 т/год; storage BASE=70 / ZBO=120 т.
  BASE-2040 спрос 390; STRESS-2040 448.5; STRESS-2039 368.
  A+B=300, A+B+E=380 < 390 → семейство A/B проваливает BASE-2040 физически.
  A+B+C=430 < 448.5 → без D или E стресс-2040 не проходит.
"""
from __future__ import annotations

from mc_model import PlanDef
from mc_data import YEARS


def _res(years_vals: list[float], start_year: int = 2035) -> dict[int, float]:
    return {y: v for y, v in zip(range(start_year, start_year + len(years_vals)), years_vals)}


def build_strategies() -> list[PlanDef]:
    P: list[PlanDef] = []

    # ==================== Семейство A — без инвестиций ====================
    P.append(PlanDef(
        plan_id="S01", family="A", name_ru="Pure Core (только A, без инвестиций)",
        reservations={"A": _res([100, 140, 190, 190, 190, 190])},
        priority=["A"], use_emergency=False,
        initial_inventory_t=70.0,
        notes_ru="Контроль: A lead=12мес → поставки A только с 2036; весь 2035 из запаса 70 т при спросе 100 т → дефицит 30 т.",
    ))
    P.append(PlanDef(
        plan_id="S02", family="A", name_ru="Core+Flex (A+B)",
        reservations={"A": _res([100, 140, 190, 190, 190, 190]),
                      "B": _res([110, 110, 110, 110, 110, 110])},
        priority=["A", "B"], use_emergency=False,
        initial_inventory_t=65.0,
        notes_ru="A+B=300 < 390 (2040 BASE) — физический провал поздних лет.",
    ))
    P.append(PlanDef(
        plan_id="S03", family="A", name_ru="Core+Flex+Spot (A+B+E)",
        reservations={"A": _res([100, 140, 190, 190, 190, 190]),
                      "B": _res([110, 110, 110, 110, 110, 110]),
                      "E": _res([20, 20, 20, 80, 80, 80])},
        priority=["A", "B"], use_emergency=True,
        initial_inventory_t=65.0,
        notes_ru="A+B+E=380 < 390 (2040 BASE): даже полный E не закрывает 2040.",
    ))
    P.append(PlanDef(
        plan_id="S04", family="A", name_ru="Flex-first (B основной, A минимальный)",
        reservations={"A": _res([70, 98, 133, 175, 190, 190]),
                      "B": _res([110, 110, 110, 110, 110, 110])},
        priority=["B", "A"], use_emergency=False,
        initial_inventory_t=65.0,
        notes_ru="A ≈ TOP-безубыточность (Q_order ≥ 0.7×Q_reserved) в ранние годы.",
    ))

    # ==================== Семейство B — только ZBO ====================
    P.append(PlanDef(
        plan_id="S05", family="B", name_ru="Core+Flex+ZBO",
        reservations={"A": _res([100, 140, 190, 190, 190, 190]),
                      "B": _res([110, 110, 110, 110, 110, 110])},
        investments=[("ZBO", "fund_capex", "2036-01")],
        priority=["A", "B"], use_emergency=False,
        initial_inventory_t=65.0,
    ))
    P.append(PlanDef(
        plan_id="S06", family="B", name_ru="ZBO+Spot (A+B+E+ZBO)",
        reservations={"A": _res([100, 140, 190, 190, 190, 190]),
                      "B": _res([110, 110, 110, 110, 110, 110]),
                      "E": _res([20, 20, 20, 80, 80, 80])},
        investments=[("ZBO", "fund_capex", "2036-01")],
        priority=["A", "B"], use_emergency=True,
        initial_inventory_t=65.0,
    ))

    # ==================== Семейство C — Earth-New без ISRU ====================
    P.append(PlanDef(
        plan_id="S07", family="C", name_ru="New early (A+B+C, exercise 2035)",
        reservations={"A": _res([100, 140, 190, 190, 190, 190]),
                      "B": _res([110, 110, 110, 110, 110, 110]),
                      "C": _res([130, 130, 130, 130], start_year=2037)},
        investments=[("EARTH_NEW", "buy_option", "2035-01"),
                     ("EARTH_NEW", "exercise_option", "2035-01")],
        priority=["C", "A", "B"], use_emergency=False,
        initial_inventory_t=65.0,
        notes_ru="C доступен с 2037-01 (exercise 2035-01 + 24 мес, TA-02). A+B+C=430 < 448.5 (стресс-2040).",
    ))
    P.append(PlanDef(
        plan_id="S08", family="C", name_ru="New+ZBO (A+C+ZBO, B минимальный)",
        reservations={"A": _res([100, 140, 190, 190, 190, 190]),
                      "B": _res([40, 60, 70, 70, 70, 70]),
                      "C": _res([130, 130, 130, 130], start_year=2037)},
        investments=[("EARTH_NEW", "buy_option", "2035-01"),
                     ("EARTH_NEW", "exercise_option", "2035-01"),
                     ("ZBO", "fund_capex", "2036-01")],
        priority=["C", "A", "B"], use_emergency=False,
        initial_inventory_t=65.0,
    ))
    P.append(PlanDef(
        plan_id="S09", family="C", name_ru="New+Flex, Core-light (B+C+ZBO, A урезан)",
        reservations={"A": _res([70, 98, 133, 175, 190, 190]),
                      "B": _res([110, 110, 110, 110, 110, 110]),
                      "C": _res([130, 130, 130, 130], start_year=2037)},
        investments=[("EARTH_NEW", "buy_option", "2035-01"),
                     ("EARTH_NEW", "exercise_option", "2035-01"),
                     ("ZBO", "fund_capex", "2036-01")],
        priority=["C", "B", "A"], use_emergency=False,
        initial_inventory_t=65.0,
        notes_ru="Проверка: можно ли жить почти без дорогого TOP-канала A.",
    ))

    # ==================== Семейство D — ISRU-ядро ====================
    P.append(PlanDef(
        plan_id="S10", family="D", name_ru="ISRU base (A+B+D+ZBO, ISRU 2036)",
        reservations={"A": _res([100, 140, 190, 190, 190, 190]),
                      "B": _res([110, 110, 110, 110, 110, 110]),
                      "D": _res([120, 120, 120], start_year=2038)},
        investments=[("LUNAR_ISRU", "fund_capex", "2036-06"),
                     ("ZBO", "fund_capex", "2036-06")],
        priority=["D", "A", "B"], use_emergency=False,
        initial_inventory_t=65.0,
        notes_ru="ZBO ввод 2036-07 (до 2038 — потолок потерь стресса). A+B+D=420 < 448.5 (стресс-2040).",
    ))
    P.append(PlanDef(
        plan_id="S11", family="D", name_ru="ISRU no ZBO (контроль на нарушение)",
        reservations={"A": _res([100, 140, 190, 190, 190, 190]),
                      "B": _res([110, 110, 110, 110, 110, 110]),
                      "D": _res([120, 120, 120], start_year=2038)},
        investments=[("LUNAR_ISRU", "fund_capex", "2036-06")],
        priority=["D", "A", "B"], use_emergency=False,
        initial_inventory_t=65.0,
        notes_ru="Контроль: без ZBO потери 4.5% > 2% — нарушение STRESS_LOSS_LIMIT с 2038 (Q2).",
    ))
    P.append(PlanDef(
        plan_id="S12", family="D", name_ru="ISRU gradual A (резерв A растёт ступенчато)",
        reservations={"A": _res([70, 98, 133, 140, 190, 190]),
                      "B": _res([110, 110, 110, 110, 110, 110]),
                      "D": _res([120, 120, 120], start_year=2038)},
        investments=[("LUNAR_ISRU", "fund_capex", "2036-06"),
                     ("ZBO", "fund_capex", "2036-06")],
        priority=["D", "A", "B"], use_emergency=False,
        initial_inventory_t=65.0,
        notes_ru="Минимизация TOP-сжигания A в ранние годы.",
    ))
    P.append(PlanDef(
        plan_id="S13", family="D", name_ru="ISRU Core-light (B+D+ZBO, A минимальный)",
        reservations={"A": _res([70, 98, 133, 140, 150, 150]),
                      "B": _res([110, 110, 110, 110, 110, 110]),
                      "D": _res([120, 120, 120], start_year=2038)},
        investments=[("LUNAR_ISRU", "fund_capex", "2036-06"),
                     ("ZBO", "fund_capex", "2036-06")],
        priority=["D", "B", "A"], use_emergency=False,
        initial_inventory_t=65.0,
        notes_ru="Максимум гибкости, минимум take-or-pay.",
    ))

    # ==================== Семейство E — полные инвестиции ====================
    P.append(PlanDef(
        plan_id="S14", family="E", name_ru="Full early (A+B+C+D+ZBO, exercise C 2035)",
        reservations={"A": _res([100, 140, 190, 190, 190, 190]),
                      "B": _res([110, 110, 110, 110, 110, 110]),
                      "C": _res([130, 130, 130, 130], start_year=2037),
                      "D": _res([120, 120, 120], start_year=2038)},
        investments=[("EARTH_NEW", "buy_option", "2035-01"),
                     ("EARTH_NEW", "exercise_option", "2035-01"),
                     ("ZBO", "fund_capex", "2036-06"),
                     ("LUNAR_ISRU", "fund_capex", "2036-06")],
        priority=["D", "C", "A", "B"], use_emergency=False,
        initial_inventory_t=65.0,
        notes_ru="CAPEX 1250+360+180=1790 ≤ 1800 (запас 10 млн!). A+B+C+D=550 ≥ 448.5.",
    ))
    P.append(PlanDef(
        plan_id="S15", family="E", name_ru="Full late (exercise C 2037 → мощность с 2039)",
        reservations={"A": _res([100, 140, 190, 190, 190, 190]),
                      "B": _res([110, 110, 110, 110, 110, 110]),
                      "C": _res([130, 130], start_year=2039),
                      "D": _res([120, 120, 120], start_year=2038)},
        investments=[("EARTH_NEW", "buy_option", "2035-01"),
                     ("EARTH_NEW", "exercise_option", "2037-01"),
                     ("ZBO", "fund_capex", "2036-06"),
                     ("LUNAR_ISRU", "fund_capex", "2036-06")],
        priority=["D", "C", "A", "B"], use_emergency=False,
        initial_inventory_t=65.0,
        notes_ru="Проверка: успевает ли C к пику 2039–2040 (exercise 2037-01 + 24 = 2039-01).",
    ))
    P.append(PlanDef(
        plan_id="S16", family="E", name_ru="Option-hold (опцион C куплен 2035, exercise — решение 2038)",
        reservations={"A": _res([100, 140, 190, 190, 190, 190]),
                      "B": _res([110, 110, 110, 110, 110, 110]),
                      "D": _res([120, 120, 120], start_year=2038)},
        investments=[("EARTH_NEW", "buy_option", "2035-01"),
                     ("ZBO", "fund_capex", "2036-06"),
                     ("LUNAR_ISRU", "fund_capex", "2036-06")],
        priority=["D", "A", "B"], use_emergency=False,
        initial_inventory_t=65.0, adaptive=True,
        branch_rule_ru=("Ворота 2038-01: фактическая доля поставки ISRU-2038 ≤ 0.60 (стресс 0.55) "
                        "→ exercise C в 2038-01 (мощность с 2040-01, 270 млн, CAPEX≤2037 не затрагивает); "
                        "иначе (BASE, доля 1.0) → опцион не реализуется (списаны только 90 млн)."),
        notes_ru="Адаптивная: две ветви (BASE — без exercise; STRESS — exercise 2038-01).",
    ))

    # ==================== Семейство F — политики резервирования A ====================
    _fedf = [("EARTH_NEW", "buy_option", "2035-01"),
             ("EARTH_NEW", "exercise_option", "2035-01"),
             ("ZBO", "fund_capex", "2036-06"),
             ("LUNAR_ISRU", "fund_capex", "2036-06")]
    P.append(PlanDef(
        plan_id="S17", family="F", name_ru="A aggressive (резерв A=190 с 2035)",
        reservations={"A": _res([190, 190, 190, 190, 190, 190]),
                      "B": _res([110, 110, 110, 110, 110, 110]),
                      "C": _res([130, 130, 130, 130], start_year=2037),
                      "D": _res([120, 120, 120], start_year=2038)},
        investments=list(_fedf),
        priority=["D", "C", "A", "B"], use_emergency=False,
        initial_inventory_t=65.0,
        notes_ru="Цена TOP-сжигания: 2035–2036 спрос 100–140 при резерве 190 (Q3).",
    ))
    P.append(PlanDef(
        plan_id="S18", family="F", name_ru="A demand-tracking (A ≈ спрос − (B+C+D) + 10%)",
        reservations={"A": _res([100, 132, 154, 154, 187, 190]),
                      "B": _res([110, 110, 110, 110, 110, 110]),
                      "C": _res([130, 130, 130, 130], start_year=2037),
                      "D": _res([120, 120, 120], start_year=2038)},
        investments=list(_fedf),
        priority=["D", "C", "A", "B"], use_emergency=False,
        initial_inventory_t=65.0,
        notes_ru="2035: A+B=210≥100; 2036: 242≥140; 2037: 264+... ≥190; 2038: 374≥250; 2039: 407≥320; 2040: 410≥390 (BASE). В стрессе 2040: 410+D... A+B+C+D=537≥448.5.",
    ))
    P.append(PlanDef(
        plan_id="S19", family="F", name_ru="A minimal (резерв A под TOP-безубыточность)",
        reservations={"A": _res([70, 98, 133, 140, 150, 150]),
                      "B": _res([110, 110, 110, 110, 110, 110]),
                      "C": _res([130, 130, 130, 130], start_year=2037),
                      "D": _res([120, 120, 120], start_year=2038)},
        investments=list(_fedf),
        priority=["D", "C", "B", "A"], use_emergency=False,
        initial_inventory_t=65.0,
        notes_ru="A = ceil(прогноз/0.7) так, чтобы Q_order ≥ 0.7×Q_reserved; 2040: A+B+C+D=460 ≥ 448.5 (стресс) — на грани.",
    ))

    # ==================== Семейство G — робастность ====================
    P.append(PlanDef(
        plan_id="S20", family="G", name_ru="Robust mix (B=110 все годы + E-контракт + физрезерв)",
        reservations={"A": _res([100, 140, 190, 190, 190, 190]),
                      "B": _res([110, 110, 110, 110, 110, 110]),
                      "C": _res([130, 130, 130, 130], start_year=2037),
                      "D": _res([120, 120, 120], start_year=2038),
                      "E": _res([20, 20, 20, 80, 80, 80])},
        investments=list(_fedf),
        priority=["D", "C", "A", "B"], use_emergency=True,
        initial_inventory_t=65.0,
        buffer_t=8.0,
        notes_ru="Цель — минимальный дефицит в стрессе любой ценой: A+B+C+D+E=630.",
    ))
    P.append(PlanDef(
        plan_id="S21", family="G", name_ru="Deep reserve (целевой запас 60 дней — кандидат TA-10)",
        reservations={"A": _res([100, 140, 190, 190, 190, 190]),
                      "B": _res([110, 110, 110, 110, 110, 110]),
                      "C": _res([130, 130, 130, 130], start_year=2037),
                      "D": _res([120, 120, 120], start_year=2038)},
        investments=list(_fedf),
        priority=["D", "C", "A", "B"], use_emergency=False,
        initial_inventory_t=65.0,
        reserve_target_days=60.0,
        notes_ru="Новое допущение 60 дней — кандидат TA-10 (в REPORT). Проверка 45 дн. остаётся в силе.",
    ))
    P.append(PlanDef(
        plan_id="S22", family="G", name_ru="Contractual emergency reserve (45 дн. через контракт E)",
        reservations={"A": _res([100, 140, 190, 190, 190, 190]),
                      "B": _res([110, 110, 110, 110, 110, 110]),
                      "C": _res([130, 130, 130, 130], start_year=2037),
                      "D": _res([120, 120, 120], start_year=2038),
                      "E": _res([80, 80, 80, 80, 80, 80])},
        investments=list(_fedf),
        priority=["D", "C", "A", "B"], use_emergency=True,
        initial_inventory_t=65.0,
        reserve_mode="contractual_emergency",
        buffer_t=2.0,
        notes_ru=("Резерв 45 дн. доказывается контрактом E (мощность ≥ спроса за 42 дня, lead 42 дн.). "
                  "Показываем ЧИСЛОВО, что в 2040 потребность за 42 дня 51.6 т > мощности E 80 т/год "
                  "× (42/365) — контракт НЕ покрывает ожидание без физзапаса."),
    ))

    # ==================== Семейство H — тайминг инвестиций ====================
    P.append(PlanDef(
        plan_id="S23", family="H", name_ru="ZBO late (оплата 2037-12, ввод 2038-01)",
        reservations={"A": _res([100, 140, 190, 190, 190, 190]),
                      "B": _res([110, 110, 110, 110, 110, 110]),
                      "C": _res([130, 130, 130, 130], start_year=2037),
                      "D": _res([120, 120, 120], start_year=2038)},
        investments=[("EARTH_NEW", "buy_option", "2035-01"),
                     ("EARTH_NEW", "exercise_option", "2035-01"),
                     ("LUNAR_ISRU", "fund_capex", "2036-06"),
                     ("ZBO", "fund_capex", "2037-12")],
        priority=["D", "C", "A", "B"], use_emergency=False,
        initial_inventory_t=65.0,
        notes_ru="Проверка: потолок потерь ≤2% ровно с 2038 (ZBO действует с 2038-01) и CAPEX_2037=1790.",
    ))
    P.append(PlanDef(
        plan_id="S24", family="H", name_ru="ISRU last-moment (финансирование 2037-12)",
        reservations={"A": _res([100, 140, 190, 190, 190, 190]),
                      "B": _res([110, 110, 110, 110, 110, 110]),
                      "C": _res([130, 130, 130, 130], start_year=2037),
                      "D": _res([120, 120, 120], start_year=2038)},
        investments=[("EARTH_NEW", "buy_option", "2035-01"),
                     ("EARTH_NEW", "exercise_option", "2035-01"),
                     ("ZBO", "fund_capex", "2036-06"),
                     ("LUNAR_ISRU", "fund_capex", "2037-12")],
        priority=["D", "C", "A", "B"], use_emergency=False,
        initial_inventory_t=65.0,
        notes_ru="CAPEX_2037: 90+270+180+1250=1790 ≤ 1800 (запас 10 млн).",
    ))
    P.append(PlanDef(
        plan_id="S25", family="H", name_ru="Staged gates (G1 2035 → G4 2038, адаптивная)",
        reservations={"A": _res([100, 140, 190, 190, 190, 190]),
                      "B": _res([110, 110, 110, 110, 110, 110]),
                      "D": _res([120, 120, 120], start_year=2038)},
        investments=[("EARTH_NEW", "buy_option", "2035-01"),
                     ("ZBO", "fund_capex", "2036-06"),
                     ("LUNAR_ISRU", "fund_capex", "2037-12")],
        priority=["D", "A", "B"], use_emergency=False,
        initial_inventory_t=65.0, adaptive=True,
        branch_rule_ru=("G1 2035: A-минимум+B, опцион C куплен (90). G2 2036: ZBO (180). "
                        "G3 2037-12: ISRU (1250). G4 2038-01: если фактическая доля ISRU-2038 ≤ 0.60 "
                        "(стресс) → exercise C (270; мощность с 2040-01); иначе (BASE) → не exercise. "
                        "Ветви расходятся на G4."),
        notes_ru="C в базовом определении не резервируется; ветвь STRESS добавляет резерв C 2040.",
    ))

    return P


def make_branch(base_plan: PlanDef, scenario_id: str) -> PlanDef:
    """Ветви адаптивных стратегий S16/S25 (явное правило — в branch_rule_ru).

    STRESS-ветвь: exercise C в 2038-01 → C доступен 2040-01 (24 мес, TA-02),
    резерв C=130 только в 2040 (стрессовый спрос 448.5 > A+B+D=420).
    BASE-ветвь: опцион не реализуется (списаны 90 млн — невозвратные).
    """
    import copy
    p = copy.deepcopy(base_plan)
    p.plan_id = base_plan.plan_id
    if scenario_id == "MANDATORY_STRESS":
        p.investments = p.investments + [("EARTH_NEW", "exercise_option", "2038-01")]
        p.reservations.setdefault("C", {})[2040] = 130.0
        p.priority = ["D", "C", "A", "B"] if "C" not in p.priority else p.priority
        p.name_ru = base_plan.name_ru + " [ветвь STRESS: exercise C 2038-01]"
    else:
        p.name_ru = base_plan.name_ru + " [ветвь BASE: опцион C не реализован]"
    return p




