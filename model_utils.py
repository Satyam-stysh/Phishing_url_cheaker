from __future__ import annotations

import json
from pathlib import Path


DEFAULT_THRESHOLD = 0.5


def load_threshold(model_path: str) -> float:
    metadata_path = Path(model_path).with_suffix(".meta.json")
    if not metadata_path.exists():
        return DEFAULT_THRESHOLD

    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return DEFAULT_THRESHOLD

    threshold = payload.get("threshold", DEFAULT_THRESHOLD)
    try:
        return float(threshold)
    except (TypeError, ValueError):
        return DEFAULT_THRESHOLD
