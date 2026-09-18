"""Streamlit UI оператора. Запуск: streamlit run app/main.py."""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from app.services import (apply_decision_rows, available_scenarios, chart_thresholds, clear_result_cache,
                           constraint_catalog, default_plan, engine_available, final_plan_files,
                           list_saved_plans, load_plan_from_catalog, save_plan_to_catalog,
                           export_core_archive, geo_effect, run_geo_scenario,
                      export_csv_zip, get_run_result, load_plan_json,
                      save_plan_json, source_catalog, storage_catalog, validate_plan,
                      overview_summary, scenario_comparison, scenario_deltas, violation_count)


st.set_page_config(page_title="Топливный космоконтур 2035", page_icon="🚀", layout="wide")

SCENARIO_LABELS = {"BASE": "Базовый", "MANDATORY_STRESS": "Обязательный стресс",
                   "TEAM_RESEARCH": "Исследовательский (синтетический)"}
PAGES = ("Обзор", "Графики", "План и контракты", "Ограничения", "Сценарии", "Риски", "Сохранение")


def frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def table(rows: list[dict], labels: dict[str, str] | None = None) -> None:
    data = frame(rows)
    if labels:
        data = data.rename(columns=labels)
    st.dataframe(data, use_container_width=True, hide_index=True)


def metric(label: str, value: float, unit: str, fmt: str = ",.1f") -> None:
    st.metric(label, f"{value:{fmt}} {unit}")


def overview(result: dict) -> None:
    st.header("Обзор")
    st.caption(f"Сценарий: {SCENARIO_LABELS.get(result['scenario_id'], result['scenario_id'])} · расчёт: {result['meta']['engine_version']} · все числа синтетические")
    years = result["yearly_balance"]
    summary = overview_summary(result)
    cols = st.columns(4)
    with cols[0]:
        metric("Спрос, 2035–2040", summary["demand_t"], "т")
    with cols[1]:
        metric("Обслужено, 2035–2040", summary["served_t"], "т")
    with cols[2]:
        metric("Дефицит, 2035–2040", summary["shortage_t"], "т")
    with cols[3]:
        metric("Расходы, 2035–2040", summary["cost_mln"], "млн у.е.")
    st.subheader("Уровень обслуживания по годам")
    table([{"Год": y["year"], "SL общий, доля": y["sl_total"],
            "SL критический, доля": y["sl_critical"]} for y in years])
    st.subheader("Материальный и финансовый обзор")
    table(summary["annual_rows"])


def graphs(result: dict, base: dict, stress: dict) -> None:
    st.header("Графики")
    st.caption("Синтетические показатели; пороги и ёмкости подписаны в единицах CASE_INPUT.")
    source = frame(result["source_schedule"])
    supply = source.pivot_table(index="period", columns="source_id", values="actual_delivery_t", aggfunc="sum")
    st.subheader("Поставки по каналам, т/месяц")
    st.bar_chart(supply, stack=True)
    balance = frame(result["monthly_balance"]).set_index("period")
    st.subheader("Спрос и обслуженный спрос, т/месяц")
    st.line_chart(balance[["demand_total_t", "served_total_t"]].rename(
        columns={"demand_total_t": "Спрос", "served_total_t": "Обслужено"}))
    trace = frame(result["inventory_trace"]).set_index("period")
    st.subheader("Запас, порог 45 дней и ёмкость, т")
    st.line_chart(trace.rename(columns={"inventory_t": "Запас", "reserve_threshold_t": "Порог 45 дней",
                                        "capacity_t": "Ёмкость"}))
    finance = frame(result["financial_breakdown"]).set_index("year")
    st.subheader("Расходы по годам, млн у.е.")
    st.bar_chart(finance[["procurement_mln", "reservation_mln", "holding_mln",
                          "capex_mln", "fixed_opex_mln"]].rename(columns={
                              "procurement_mln": "Закупки", "reservation_mln": "Резервирование",
                              "holding_mln": "Хранение", "capex_mln": "CAPEX",
                              "fixed_opex_mln": "OPEX"}), stack=True)
    st.subheader("Накопленный CAPEX и лимиты, млн у.е.")
    capex = finance[["capex_cumulative_mln"]].rename(columns={"capex_cumulative_mln": "CAPEX"}).copy()
    limits = chart_thresholds()
    capex["Лимит до 2037"] = limits["capex_2037"]
    capex["Лимит до 2040"] = limits["capex_2040"]
    st.line_chart(capex)
    st.subheader("SL по годам и минимальные уровни, доля")
    service = frame(result["yearly_balance"]).set_index("year")[["sl_total", "sl_critical"]].copy()
    service = service.rename(columns={"sl_total": "SL общий", "sl_critical": "SL критический"})
    service["Минимум общий"] = limits["sl_total"]
    service["Минимум критический"] = limits["sl_critical"]
    st.line_chart(service)
    st.subheader("BASE и стресс: разницы по годам")
    table(scenario_deltas(base, stress))


def editable_decision_table(plan: dict, section: str, labels: dict[str, str]) -> None:
    rows = plan["decisions"][section]
    if not rows:
        return
    st.caption("Измените ячейки или удалите строку, затем нажмите «Применить изменения».")
    edited = st.data_editor(frame(rows), num_rows="dynamic", use_container_width=True,
        hide_index=True, column_config={key: st.column_config.Column(label)
                                        for key, label in labels.items()},
        key=f"editor_{section}_{plan['plan_id']}")
    if st.button("Применить изменения", key=f"apply_{section}"):
        try:
            st.session_state.plan = apply_decision_rows(plan, section, edited.to_dict(orient="records"))
            st.success("Изменения плана сохранены в текущей сессии.")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))


def plan_page(plan: dict) -> None:
    st.header("План и контракты")
    if not engine_available():
        st.info("Демо-режим: полный API ядра WP1 ещё не готов; изменения решений не меняют синтетические показатели.")
    plan["plan_id"] = st.text_input("Идентификатор плана", value=plan["plan_id"])
    decisions = plan["decisions"]
    sources = source_catalog()
    source_ids = [row["source_id"] for row in sources]
    with st.expander("Заказы по каналам и периодам", expanded=True):
        table(decisions["supply_orders"], {"source_id": "Канал", "period": "Период",
                                            "ordered_volume_t": "Заказ, т"})
        editable_decision_table(plan, "supply_orders", {"source_id": "Канал", "period": "Период",
                                                       "ordered_volume_t": "Заказ, т"})
        with st.form("order_form"):
            c1, c2, c3 = st.columns(3)
            source = c1.selectbox("Канал", source_ids, key="order_source")
            period = c2.text_input("Период YYYY или YYYY-MM", "2035-01")
            volume = c3.number_input("Заказ, т", min_value=0.0, value=1.0)
            if st.form_submit_button("Добавить заказ"):
                item = {"source_id": source, "period": period, "ordered_volume_t": volume}
                candidate = json.loads(json.dumps(plan))
                candidate["decisions"]["supply_orders"].append(item)
                errors = validate_plan(candidate)
                if errors:
                    st.error("\n".join(errors))
                else:
                    decisions["supply_orders"].append(item)
                    st.success("Заказ добавлен.")
                    st.rerun()
        if decisions["supply_orders"] and st.button("Удалить последний заказ"):
            decisions["supply_orders"].pop()
            st.rerun()
    with st.expander("Резервирование мощностей", expanded=True):
        table(decisions["capacity_reservations"], {"source_id": "Канал", "year": "Год",
                "reserved_capacity_t_per_year": "Мощность, т/год", "start_month": "Месяц начала"})
        editable_decision_table(plan, "capacity_reservations", {"source_id": "Канал", "year": "Год",
            "reserved_capacity_t_per_year": "Мощность, т/год", "start_month": "Месяц начала"})
        with st.form("reserve_form"):
            c1, c2, c3, c4 = st.columns(4)
            source = c1.selectbox("Канал", source_ids, key="reserve_source")
            year = c2.number_input("Год", 2035, 2040, 2035)
            capacity = c3.number_input("Резерв, т/год", min_value=0.0, value=1.0)
            start_month = c4.number_input("Месяц начала", 1, 12, 1)
            if st.form_submit_button("Добавить резервирование"):
                item = {"source_id": source, "year": int(year),
                        "reserved_capacity_t_per_year": capacity, "start_month": int(start_month)}
                candidate = json.loads(json.dumps(plan))
                candidate["decisions"]["capacity_reservations"].append(item)
                errors = validate_plan(candidate)
                if errors:
                    st.error("\n".join(errors))
                else:
                    decisions["capacity_reservations"].append(item)
                    st.success("Резервирование добавлено.")
                    st.rerun()
        if decisions["capacity_reservations"] and st.button("Удалить последнее резервирование"):
            decisions["capacity_reservations"].pop()
            st.rerun()
    with st.expander("Инвестиции"):
        table(decisions["investments"], {"investment_id": "Опция", "action": "Действие",
                                         "payment_date": "Дата платежа"})
        editable_decision_table(plan, "investments", {"investment_id": "Опция", "action": "Действие",
                                                     "payment_date": "Дата платежа"})
        with st.form("investment_form"):
            c1, c2, c3 = st.columns(3)
            investment = c1.selectbox("Опция", ("EARTH_NEW", "LUNAR_ISRU", "ZBO"))
            action = c2.selectbox("Действие", ("buy_option", "exercise_option", "fund_capex", "none"))
            date = c3.text_input("Дата платежа YYYY-MM", "2036-01")
            if st.form_submit_button("Добавить инвестицию"):
                item = {"investment_id": investment, "action": action, "payment_date": date}
                candidate = json.loads(json.dumps(plan))
                candidate["decisions"]["investments"].append(item)
                errors = validate_plan(candidate)
                if errors:
                    st.error("\n".join(errors))
                else:
                    decisions["investments"].append(item)
                    st.success("Инвестиция добавлена.")
                    st.rerun()
        if decisions["investments"] and st.button("Удалить последнюю инвестицию"):
            decisions["investments"].pop()
            st.rerun()
    with st.expander("Политика запаса и аварийный контракт"):
        policy = decisions["inventory_policy"]
        policy["initial_inventory_t"] = st.number_input("Начальный запас на 01.01.2035, т",
                                                          min_value=0.0, value=float(policy["initial_inventory_t"]))
        origin = policy["initial_inventory_source"]
        origin["source_id"] = st.selectbox("Источник начального запаса", source_ids,
                                           index=source_ids.index(origin["source_id"]))
        origin["order_period"] = st.text_input("Период предстартового заказа", origin["order_period"])
        origin["delivery_period"] = st.text_input("Период поставки", origin["delivery_period"])
        origin["volume_t"] = st.number_input("Объём предстартового заказа, т",
                                              min_value=0.0, value=float(origin["volume_t"]))
        origin["paid_in"] = st.text_input("Год оплаты", origin["paid_in"])
        policy["reserve_mode"] = st.selectbox("Способ резерва", ("physical", "contractual_emergency"),
                                               index=("physical", "contractual_emergency").index(policy["reserve_mode"]))
        policy["target_month_end_inventory_t"] = st.number_input("Целевой запас на конец месяца, т",
            min_value=0.0, value=float(policy.get("target_month_end_inventory_t", 0.0)))
        if policy["reserve_mode"] == "contractual_emergency":
            contract = decisions.get("emergency_contract") or {}
            contract["reserved_capacity_t_per_year"] = st.number_input("Аварийный резерв, т/год",
                min_value=0.0, value=float(contract.get("reserved_capacity_t_per_year", 0.0)))
            contract["activation_lead_days"] = st.number_input("Срок активации, дни",
                min_value=0.0, value=float(contract.get("activation_lead_days", 42.0)))
            contract["coverage_volume_t"] = st.number_input("Покрытие, т", min_value=0.0,
                value=float(contract.get("coverage_volume_t", 0.0)))
            contract["notes_ru"] = st.text_area("Обоснование покрытия", contract.get("notes_ru", ""))
            decisions["emergency_contract"] = contract
        else:
            decisions["emergency_contract"] = None
    st.subheader("Реестр контрактов")
    st.caption("Рабочий реестр оператора; условия договора хранятся в этой сессии и не входят в plan_format.json.")
    st.session_state.contracts = st.data_editor(st.session_state.contracts, num_rows="dynamic",
        use_container_width=True, hide_index=True, key="contracts_editor")
    st.caption("Мощности и сроки из CASE_INPUT")
    table([{"Канал": r["source_id"], "Контрагент": r["name"],
            "Мощность, т/год": r["capacity_t_per_year"],
            "Срок поставки": f"{r['lead_time_min_value']}–{r['lead_time_max_value']} {r['lead_time_unit']}",
            "TOP, доля": r["take_or_pay_share"],
            "Тариф резервирования, млн у.е./(т/год)": r["reservation_rate_mln_per_t_year_capacity"]}
           for r in sources])
    st.caption("Режимы хранения из CASE_INPUT")
    table([{"Режим": r["storage_id"], "Ёмкость, т": r["capacity_t"],
            "Потери, доля": r["loss_rate_on_throughput"]} for r in storage_catalog()])


def constraints(result: dict) -> None:
    st.header("Ограничения")
    checks = result["constraint_checks"]
    failed = [x for x in checks if not x["passed"]]
    st.metric("Нарушений", violation_count(result))
    st.caption("Каждая запись содержит правило, период, факт, лимит и причину. Цвет дополнен значком и текстом.")
    for item in checks:
        label = "❌ НАРУШЕНО" if not item["passed"] else "✅ ВЫПОЛНЕНО"
        with st.expander(f"{label} · {item['rule_id']} · {item['period']}", expanded=not item["passed"]):
            st.write(f"Факт: **{item['actual']}** · лимит: **{item['limit']}** · отклонение: **{item.get('excess', 0)}**")
            st.write(item["message_ru"])
    st.subheader("Исходный каталог ограничений CASE_INPUT")
    table([{"Правило": c["constraint_id"], "Порог": c["value"], "Единица": c["unit"],
            "Сценарий": c["scenario"], "Период": c["period"]} for c in constraint_catalog()])


def scenarios(result: dict, base: dict, stress: dict) -> None:
    st.header("Сценарии")
    st.write(f"Выбран: **{SCENARIO_LABELS.get(result['scenario_id'], result['scenario_id'])}**. Переключатель находится слева.")
    if st.button("Пересчитать"):
        errors = validate_plan(st.session_state.plan)
        if errors:
            st.error("\n".join(errors))
        else:
            clear_result_cache()
            st.success("Расчёт обновлён." if engine_available() else "Демо-мок обновлён; решения плана не меняют синтетические показатели.")
            st.rerun()
    st.subheader("BASE и MANDATORY_STRESS на общей базе")
    table(scenario_comparison(base, stress))
    st.subheader("Геополитический исследовательский сценарий")
    st.caption("Событие меняет только переменную цену выбранного канала в указанные годы; вероятность не задаётся.")
    with st.form("geo_form"):
        event_label = st.text_input("Название события")
        source_id = st.selectbox("Затронутый канал", [row["source_id"] for row in source_catalog()])
        multiplier = st.number_input("Коэффициент переменной цены", min_value=0.0, value=1.25)
        first_year = st.number_input("Первый год", min_value=2035, max_value=2040, value=2038)
        last_year = st.number_input("Последний год", min_value=2035, max_value=2040, value=2039)
        submitted = st.form_submit_button("Рассчитать эффект события", disabled=not engine_available())
    if submitted:
        try:
            st.session_state.geo_result = run_geo_scenario(st.session_state.plan, event_label,
                source_id, multiplier, int(first_year), int(last_year))
            st.session_state.geo_plan_snapshot = json.dumps(st.session_state.plan, sort_keys=True, ensure_ascii=False)
        except ValueError as exc:
            st.error(str(exc))
    if ("geo_result" in st.session_state and
            st.session_state.geo_plan_snapshot != json.dumps(st.session_state.plan, sort_keys=True, ensure_ascii=False)):
        del st.session_state.geo_result
        del st.session_state.geo_plan_snapshot
    if "geo_result" in st.session_state:
        st.write("Эффект относительно контрольного BASE")
        effect = geo_effect(base, st.session_state.geo_result)
        table([{"Показатель": "Расходы, млн у.е.", "BASE": effect["base_cost_mln"],
                "Событие": effect["geo_cost_mln"]},
               {"Показатель": "Поставки, т", "BASE": effect["base_delivered_t"],
                "Событие": effect["geo_delivered_t"]},
               {"Показатель": "Дефицит, т", "BASE": effect["base_shortage_t"],
                "Событие": effect["geo_shortage_t"]}])
        if st.button("Восстановить контрольные цены"):
            del st.session_state.geo_result
            del st.session_state.geo_plan_snapshot
            st.rerun()
    if not engine_available():
        st.info("Расчёт геополитического сценария станет доступен после завершения ядра WP1.")


def risks(result: dict) -> None:
    st.header("Риски")
    if result["meta"]["engine_version"] == "MOCK":
        st.warning("Реестр ниже — синтетическая заглушка. Вероятности не оценены.")
    table(result.get("risk_register", []), {"risk_id": "Риск", "scenario_id": "Сценарий",
        "consequence_t": "Последствие, т", "consequence_mln": "Последствие, млн у.е.",
        "consequence_sl": "Изменение SL, доля", "probability_basis_ru": "Основание вероятности"})


def persistence(result: dict, plan: dict) -> None:
    st.header("Сохранение")
    st.caption("План сохраняется в JSON. Выгрузка результата содержит конверт export.schema.json и шесть CSV.")
    try:
        payload = save_plan_json(plan)
        st.download_button("Скачать план JSON", payload, file_name=f"{plan['plan_id']}.json",
                           mime="application/json")
    except ValueError as exc:
        st.error(str(exc))
    st.subheader("Каталог сохранённых планов")
    save_name = st.text_input("Сохранить как", value=plan["plan_id"])
    if st.button("Сохранить в каталог"):
        try:
            filename = save_plan_to_catalog(plan, save_name)
            st.success(f"План сохранён: {filename}")
        except (ValueError, OSError) as exc:
            st.error(str(exc))
    saved = list_saved_plans()
    if saved:
        choice = st.selectbox("Открыть из каталога", saved,
                              format_func=lambda item: f"{item['plan_id']} · {item['scenario_id']} · {item['file']}")
        if st.button("Открыть выбранный план"):
            try:
                st.session_state.plan = load_plan_from_catalog(choice["file"])
                st.session_state.loaded_scenario_id = st.session_state.plan["scenario_id"]
                st.rerun()
            except (ValueError, OSError) as exc:
                st.error(str(exc))
    else:
        st.info("В каталоге results/plans/ пока нет сохранённых планов.")
    uploaded = st.file_uploader("Открыть сохранённый план JSON", type="json")
    if uploaded is not None and st.button("Загрузить план"):
        try:
            st.session_state.plan = load_plan_json(uploaded.getvalue())
            st.session_state.loaded_scenario_id = st.session_state.plan["scenario_id"]
            st.success("План загружен.")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
    try:
        csv_payload = (export_core_archive(result["scenario_id"], plan, "csv")
                       if engine_available() else export_csv_zip(result))
        st.download_button("Выгрузить результат CSV (ZIP)", csv_payload,
            file_name=f"{result['scenario_id']}_{result['plan_id']}_{result['meta']['engine_version']}.zip",
            mime="application/zip")
        if engine_available():
            xlsx_payload = export_core_archive(result["scenario_id"], plan, "xlsx")
            st.download_button("Выгрузить результат XLSX (ZIP)", xlsx_payload,
                file_name=f"{result['scenario_id']}_{result['plan_id']}_XLSX.zip", mime="application/zip")
    except (ValueError, ImportError) as exc:
        st.error(str(exc))


if "scenario_id" not in st.session_state:
    st.session_state.scenario_id = "BASE"
if "plan" not in st.session_state:
    st.session_state.plan = default_plan()
if "loaded_scenario_id" in st.session_state:
    st.session_state.scenario_id = st.session_state.pop("loaded_scenario_id")
if "contracts" not in st.session_state:
    st.session_state.contracts = pd.DataFrame(columns=[
        "Контрагент", "Канал", "Объём, т", "Начало", "Конец", "Срок поставки",
        "Резервирование, т/год", "TOP, доля", "Оплата", "Правила пересмотра"])

st.sidebar.title("Топливный космоконтур 2035")
page = st.sidebar.radio("Раздел", PAGES)
scenario_id = st.sidebar.selectbox("Сценарий", available_scenarios(),
    format_func=lambda value: SCENARIO_LABELS.get(value, f"Исследовательский: {value}"), key="scenario_id")
if engine_available():
    st.sidebar.success("Расчётное ядро доступно")
else:
    st.sidebar.warning("🧪 ДЕМО: синтетические данные, не результаты стратегии")
finals = final_plan_files()
if finals:
    st.sidebar.caption("Готовые планы")
    for item in finals:
        if st.sidebar.button(f"Загрузить {item['plan_id']}", key=f"final_{item['file']}"):
            try:
                st.session_state.plan = load_plan_from_catalog(item["file"])
                st.session_state.loaded_scenario_id = st.session_state.plan["scenario_id"]
                st.rerun()
            except (ValueError, OSError) as exc:
                st.sidebar.error(str(exc))
plan = st.session_state.plan
plan["scenario_id"] = scenario_id
try:
    result = get_run_result(scenario_id, plan)
    base = get_run_result("BASE", plan)
    stress = get_run_result("MANDATORY_STRESS", plan)
except ValueError as exc:
    st.error(f"План или расчёт требует исправления: {exc}")
    if page == "План и контракты":
        plan_page(plan)
        st.stop()
    if engine_available():
        st.stop()
    result = get_run_result("BASE", default_plan("BASE"))
    base = get_run_result("BASE", default_plan("BASE"))
    stress = get_run_result("MANDATORY_STRESS", default_plan("MANDATORY_STRESS"))

st.caption(f"Сценарий: {SCENARIO_LABELS.get(scenario_id, scenario_id)} · период: 2035–2040 · версия: {result['meta']['engine_version']}")

if page == "Обзор":
    overview(result)
elif page == "Графики":
    graphs(result, base, stress)
elif page == "План и контракты":
    plan_page(plan)
elif page == "Ограничения":
    constraints(result)
elif page == "Сценарии":
    scenarios(result, base, stress)
elif page == "Риски":
    risks(result)
else:
    persistence(result, plan)

