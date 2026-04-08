from __future__ import annotations

from typing import Any

from backend.db.client import insert_rows


def create_observations(rows: list[dict[str, Any]]) -> int:
    return insert_rows("observations", rows)
