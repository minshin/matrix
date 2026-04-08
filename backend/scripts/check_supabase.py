from __future__ import annotations

from backend.db.client import get_supabase_client

REQUIRED_TABLES = [
    "graphs",
    "runs",
    "observations",
    "event_nodes",
    "conclusions",
]


def main() -> None:
    client = get_supabase_client()
    if client is None:
        print("[FAIL] Supabase client unavailable. Check SUPABASE_URL/SUPABASE_SERVICE_KEY.")
        raise SystemExit(1)

    print("[OK] Supabase client initialized")

    has_error = False
    for table in REQUIRED_TABLES:
        try:
            result = client.table(table).select("*", count="exact").limit(1).execute()
            print(f"[OK] {table}: reachable, rows={result.count}")
        except Exception as exc:
            has_error = True
            print(f"[FAIL] {table}: {exc}")

    if has_error:
        print("\nMissing tables? Run SQL in sql/init_schema.sql in Supabase SQL Editor, then re-run this check.")
        raise SystemExit(2)


if __name__ == "__main__":
    main()
