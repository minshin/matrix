from __future__ import annotations

import asyncio

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from backend.db.runs import get_running_run
from backend.engine.graph_runner import GraphRunner
from backend.llm import list_available_models
from backend.observation_service import ObservationService

app = FastAPI(title="Matrix Backend", version="0.1.0")
_graph_locks: dict[str, asyncio.Lock] = {}


class RunRequest(BaseModel):
    graph_id: str
    graph_path: str | None = None
    observe_first: bool = False
    observe_topic: str | None = None
    observe_bot_count: int = 5
    observe_results_per_bot: int = 5
    observe_months_back: int = 1
    observe_source_constraints: list[str] = Field(default_factory=list)
    ai_model: str | None = None


class ObserveRequest(BaseModel):
    topic: str
    bot_count: int = 5
    results_per_bot: int = 5
    months_back: int = 1
    source_constraints: list[str] = Field(default_factory=list)
    ai_model: str | None = None


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/models")
def models() -> dict[str, list[str]]:
    return {"models": list_available_models()}


@app.post("/run")
async def run(request: RunRequest) -> dict:
    lock = _graph_locks.setdefault(request.graph_id, asyncio.Lock())
    if lock.locked():
        raise HTTPException(
            status_code=409,
            detail={
                "code": "RUN_ALREADY_IN_PROGRESS",
                "message": f"graph {request.graph_id} is already running",
            },
        )

    try:
        async with lock:
            running = get_running_run(request.graph_id)
            if running:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "RUN_ALREADY_IN_PROGRESS",
                        "message": f"graph {request.graph_id} is already running",
                        "run_id": running.get("id"),
                    },
                )

            runner = GraphRunner()
            return await runner.run_graph(
                graph_id=request.graph_id,
                graph_path=request.graph_path,
                observe_first=request.observe_first,
                observe_topic=request.observe_topic,
                observe_bot_count=request.observe_bot_count,
                observe_results_per_bot=request.observe_results_per_bot,
                observe_months_back=request.observe_months_back,
                observe_source_constraints=request.observe_source_constraints,
                ai_model=request.ai_model,
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/observe")
async def observe(request: ObserveRequest) -> dict:
    lock_key = f"observe::{request.topic.strip().lower()}"
    lock = _graph_locks.setdefault(lock_key, asyncio.Lock())
    if lock.locked():
        raise HTTPException(
            status_code=409,
            detail={
                "code": "OBSERVE_ALREADY_IN_PROGRESS",
                "message": f"topic {request.topic} is already running",
            },
        )

    try:
        async with lock:
            service = ObservationService()
            return await service.run(
                topic=request.topic,
                bot_count=request.bot_count,
                results_per_bot=request.results_per_bot,
                months_back=request.months_back,
                source_constraints=request.source_constraints,
                ai_model=request.ai_model,
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
