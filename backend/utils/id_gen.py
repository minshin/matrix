from __future__ import annotations

from uuid import uuid4


def gen_run_id() -> str:
    return f"run_{uuid4().hex[:12]}"


def gen_record_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"
