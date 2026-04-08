from __future__ import annotations

import argparse
import asyncio
import json

from backend.engine.graph_runner import GraphRunner


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Matrix graph once")
    parser.add_argument("--graph-id", required=True, help="Graph id, e.g. hormuz_blockade_7d")
    parser.add_argument("--graph-path", default=None, help="Optional YAML path")
    parser.add_argument("--run-id", default=None, help="Optional run id")
    return parser.parse_args()


async def _main() -> None:
    args = parse_args()
    runner = GraphRunner()
    result = await runner.run_graph(
        graph_id=args.graph_id,
        run_id=args.run_id,
        graph_path=args.graph_path,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(_main())
