"""Проверка TEAM YAML по замороженной схеме организатора."""
from pathlib import Path
import json

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "data/schemas/scenario.schema.json").read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA)
FILES = sorted((Path(__file__).parent / "configs/team").glob("TEAM_*.yaml"))
if not FILES:
    raise SystemExit("Не найдены TEAM_*.yaml")
failed = False
for path in FILES:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    errors = sorted(VALIDATOR.iter_errors(data), key=lambda e: list(map(str, e.path)))
    if errors:
        failed = True
        for error in errors:
            print(f"ОШИБКА {path.name}: {error.json_path}: {error.message}")
    else:
        print(f"OK {path.name}: schema 2020-12")
raise SystemExit(1 if failed else 0)
