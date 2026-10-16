"""registry.py — the 59 upstream rules (registry.json) keyed by id."""
import json
from pathlib import Path

DATA = json.loads((Path(__file__).resolve().parent / "registry.json").read_text(encoding="utf-8"))
RULES = {r["id"]: r for r in DATA["rules"]}
IMMEDIATE = set(DATA["immediate_tier"])
