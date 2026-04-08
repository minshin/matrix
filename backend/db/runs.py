from __future__ import annotations

from typing import Any

from backend.db.client import get_supabase_client


def get_running_run(graph_id: str) -> dict[str, Any] | None:
    client = get_supabase_client()
    if client is None:
        return None

    response = (
        client.table("runs")
        .select("id,graph_id,status,started_at")
        .eq("graph_id", graph_id)
        .eq("status", "running")
        .order("started_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = response.data or []
    return rows[0] if rows else None
