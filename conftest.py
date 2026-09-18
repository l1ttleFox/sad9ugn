# Корневой conftest.py: обеспечивает импорт пакета src.engine при запуске
# `python -m pytest tests/ -q` из корня репозитория.
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)


def pytest_configure(config):
    """Базовый каталог временных файлов pytest — внутри репозитория
    (стандартное расположение может быть недоступно на сетевых дисках)."""
    basetemp = os.path.join(ROOT, ".pytest_tmp")
    os.makedirs(basetemp, exist_ok=True)
    config.option.basetemp = basetemp
