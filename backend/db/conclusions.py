from __future__ import annotations

from typing import Any

from backend.db.client import upsert_rows


def upsert_conclusions(rows: list[dict[str, Any]]) -> int:
    return upsert_rows("conclusions", rows, on_conflict="id,run_id")
