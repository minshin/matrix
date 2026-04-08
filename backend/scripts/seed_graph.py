from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from backend.db.client import upsert_rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed graph YAML into graphs table")
    parser.add_argument("--graph-id", required=True, help="graph id, e.g. hormuz_blockade_7d")
    parser.add_argument("--path", default=None, help="optional yaml path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    path = Path(args.path) if args.path else Path("graphs") / f"{args.graph_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"graph file not found: {path}")

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    graph_id = payload["graph_id"]
    graph_name = payload["name"]

    row = {
        "id": graph_id,
        "name": graph_name,
        "config": json.loads(json.dumps(payload, ensure_ascii=False)),
    }
    written = upsert_rows("graphs", [row], on_conflict="id")
    print(f"seeded graphs={written}, id={graph_id}")


if __name__ == "__main__":
    main()
