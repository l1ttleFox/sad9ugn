# Повторный прогон WP4 после публикации FINAL-планов

Скопируйте текст ниже первым сообщением в новую сессию ИИ на устройстве WP4.

```text
Ты — исполнитель финального обновления WP4 (Streamlit UI) проекта «Топливный космоконтур 2035».

Интерфейс уже интегрирован с ядром, но предыдущая приёмка была выполнена на предварительном S10. Нужно подтвердить полный пользовательский сценарий на FINAL-планах и актуальном ядре после решения D8, без добавления расчётной логики в UI.

ПРЕДВАРИТЕЛЬНАЯ ПРОВЕРКА:
1. git clone git@github.com:l1ttleFox/sad9ugn.git && cd sad9ugn
   Если SSH недоступен: git clone https://github.com/l1ttleFox/sad9ugn.git
2. git checkout wp4-ui
3. git fetch origin --prune
4. git merge origin/main
5. Убедись, что существуют:
   - results/plans/FINAL_BASE.json
   - results/plans/FINAL_STRESS.json
   - ai_workstreams/WP2_strategy_economics/REPORT_wave2.md
6. Если FINAL-планов нет — НИЧЕГО не меняй и не коммить. Остановись: «WP4 refresh заблокирован: WP2 FINAL не опубликован».

ОБЯЗАТЕЛЬНО ПРОЧИТАЙ:
- ai_workstreams/ORCHESTRATOR_DECISIONS.md, особенно D4 и D8;
- ai_workstreams/WP4_ui/prompt_wave2.md;
- текущий ai_workstreams/WP4_ui/REPORT_wave2.md (числа S10 исторические и должны быть заменены);
- ai_workstreams/WP2_strategy_economics/REPORT_wave2.md;
- results/plans/FINAL_BASE.json, FINAL_STRESS.json;
- ai_workstreams/00_contracts/core_api.md, plan_format.json, result_format.json;
- docs/ИНСТРУКЦИЯ.md.

АКТУАЛЬНЫЕ УСЛОВИЯ:
- D8 устранил ложные CAPACITY_EXCEEDED: мощность проверяется по году физической поставки;
- UI не должен показывать старые «45 нарушений S10»;
- полный список constraint_checks приходит только из ядра;
- реестр договоров сохраняется отдельно как <plan_id>_contracts.json;
- геополитический price multiplier применяется один раз;
- WP3 может обновляться параллельно: UI должен автообнаруживать TEAM-конфиги/results, но не зависеть от заранее записанных результатов риска.

ЗАДАНИЕ:

1. Проверить интеграцию с актуальным ядром:
   - services вызывает только load_case/load_plan/load_scenario/run_plan/export_results/save_plan/load_saved_plan/compare_scenarios;
   - никакой формульной логики расчёта в app/;
   - USE_ENGINE=True и мок-режим не активируется при нормальном запуске.

2. Сделать FINAL-планы главными демо-планами:
   - кнопки «FINAL BASE» и «FINAL STRESS» видимы и загружают нужный файл;
   - fallback S10 оставить только с явной маркировкой «предварительный план» и использовать лишь если FINAL отсутствует;
   - scenario_id плана и выбранного сценария согласованы;
   - FINAL_BASE при открытии имеет 0 hard-нарушений. Если нет — остановись и эскалируй WP2, не скрывай нарушение.

3. Повторить полный пользовательский сценарий:
   - открыть FINAL_BASE;
   - изменить заказ, резерв и инвестицию;
   - пересчитать и показать изменения баланса/расходов/нарушений;
   - переключить BASE↔MANDATORY_STRESS;
   - открыть FINAL_STRESS;
   - сравнить сценарии;
   - сохранить план + contracts.json;
   - повторно открыть;
   - экспортировать CSV и XLSX.

4. Проверить экранные данные:
   - SL_total и SL_critical отдельно;
   - единицы на всех KPI/графиках;
   - ограничения: passed и failed берутся из result.checks;
   - цвет не единственный признак;
   - scenario_id/plan_id видны;
   - BASE vs STRESS сравниваются на одной базе.

5. Проверить экспорт:
   - пять чисел UI = CSV = RunResult (выбери показатели FINAL_BASE, укажи их в отчёте);
   - XLSX содержит те же таблицы;
   - meta содержит scenario_id, plan_id, units, assumptions_reference, engine_version;
   - сохранение/повторное открытие плана воспроизводит тот же расчёт.

6. Проверить геополитический модуль:
   - коэффициент цены применяется один раз;
   - до/после видны в UI;
   - «восстановить контрольные цены» возвращает BASE до символа;
   - CASE_INPUT-файлы не мутируются.

7. TEAM-сценарии и риски:
   - автообнаруживать все 10 TEAM YAML;
   - если обновлённые WP3 results доступны — показывать их;
   - если WP3 ещё работает, UI должен считать TEAM через ядро и не использовать устаревшие статические цифры;
   - не показывать INVENTORY_SHOCK_APPLIED как hard-нарушение.

8. Производительность/доступность:
   - холодный прогон FINAL_BASE <3 секунд;
   - AppTest всех 7 разделов: 0 исключений, 0 неожиданных st.error;
   - invalid plans дают русские сообщения без traceback;
   - обновить docs/ИНСТРУКЦИЯ.md: FINAL BASE/STRESS — основной маршрут эксперта.

9. Обновить tests/test_ui_wave2.py:
   - использовать FINAL-планы;
   - не ожидать искусственного failed-check у корректного BASE;
   - проверить автообнаружение двух FINAL-файлов;
   - проверить пять чисел UI/CSV;
   - проверить save/load contracts;
   - проверить геовосстановление;
   - общий python -m pytest tests/ -q зелёный;
   - python tests/run_control_checks.py = 10/10.

10. Переписать ai_workstreams/WP4_ui/REPORT_wave2.md:
   - указать plan_id FINAL_BASE/FINAL_STRESS;
   - заменить старые числа S10;
   - удалить замечание о 45 ложных нарушениях (D8 решено);
   - привести два актуальных примера «до/после»;
   - таблицу пяти чисел UI=CSV;
   - результаты AppTest, pytest, времени прогона и геовосстановления.

ГРАНИЦЫ:
- не менять src/engine/**, data/**, configs/base.yaml, configs/mandatory_stress.yaml, контракты и FINAL-планы;
- расчётная логика запрещена в UI;
- разрешено менять app/**, tests/test_ui_wave2.py, docs/ИНСТРУКЦИЯ.md и REPORT_wave2.md;
- весь UI и отчёт — на русском.

КРИТЕРИИ ГОТОВНОСТИ:
- FINAL-планы загружаются кнопками;
- FINAL_BASE без hard-нарушений;
- полный пользовательский сценарий проходит без разработчика;
- UI=CSV=ядро;
- save/reopen + contracts работают;
- геовосстановление побайтовое;
- AppTest зелёный, общий pytest зелёный, V01–V10 10/10;
- отчёт не содержит устаревших чисел S10 до D8.

ЗАВЕРШЕНИЕ:
git add только разрешённые файлы
git commit -m "wp4: финальная проверка UI на FINAL-планах"
git push origin wp4-ui

После push остановись и выведи: plan_id BASE/STRESS, число hard-нарушений FINAL_BASE, пять сверенных чисел, время прогона, AppTest/pytest/V01–V10, открытые блокеры.
```
