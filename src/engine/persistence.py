"""Сохранение/загрузка планов (save/load). Реализуется в WP1 волне 3."""

from __future__ import annotations

from .models import Plan


def save_plan(plan: Plan, path: str) -> None:
    """Сохранение плана в JSON по схеме plan_format.json.

    ЗАГЛУШКА: реализуется в волне 3 (prompt_wave3.md).
    """
    raise NotImplementedError(
        "save_plan: сохранение планов будет реализовано в WP1 волне 3"
    )


def load_saved_plan(path: str) -> Plan:
    """Загрузка ранее сохранённого плана.

    ЗАГЛУШКА: реализуется в волне 3; до этого используйте loader.load_plan.
    """
    raise NotImplementedError(
        "load_saved_plan: загрузка сохранённых планов будет реализована в WP1 волне 3"
    )
