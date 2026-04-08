from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from backend.agents.conclusion_agent import ConclusionAgent
from backend.agents.parse_agent import ParseAgent
from backend.agents.reasoning_agent import ReasoningAgent
from backend.crawl.crawler_router import fetch
from backend.db.client import insert_rows, update_rows
from backend.db.conclusions import upsert_conclusions
from backend.db.event_nodes import upsert_event_nodes
from backend.db.observations import create_observations
from backend.engine.graph_loader import (
    ConclusionConfig,
    GraphConfig,
    NodeConfig,
    load_graph_config,
)
from backend.observation_service import ObservationService
from backend.engine.probability import confidence_band, final_prob, formula_prob
from backend.utils.id_gen import gen_record_id, gen_run_id
from backend.utils.llm_budget import LLMBudget
from backend.utils.logger import get_logger

logger = get_logger(__name__)


class GraphRunner:
    def __init__(self) -> None:
        self.parse_agent = ParseAgent()
        self.reasoning_agent = ReasoningAgent()
        self.conclusion_agent = ConclusionAgent()
        self.ai_model: str | None = None

    async def run_graph(
        self,
        graph_id: str,
        run_id: str | None = None,
        graph_path: str | None = None,
        observe_first: bool = False,
        observe_topic: str | None = None,
        observe_bot_count: int = 5,
        observe_results_per_bot: int = 5,
        observe_months_back: int = 1,
        observe_source_constraints: list[str] | None = None,
        ai_model: str | None = None,
    ) -> dict[str, Any]:
        budget = LLMBudget(max_calls=50)
        self.parse_agent = ParseAgent(budget=budget)
        self.reasoning_agent = ReasoningAgent(budget=budget)
        self.conclusion_agent = ConclusionAgent(budget=budget)
        self.ai_model = ai_model

        graph = load_graph_config(graph_id=graph_id, graph_path=graph_path)
        run_id = run_id or gen_run_id()

        self._mark_run_started(run_id, graph.graph_id)

        try:
            observations: list[dict[str, Any]] = []
            searched_links = 0
            observe_logs: list[str] = []

            if observe_first:
                observer = ObservationService()
                collected = await observer.collect_for_run(
                    topic=(observe_topic or graph.topic),
                    run_id=run_id,
                    bot_count=observe_bot_count,
                    results_per_bot=observe_results_per_bot,
                    months_back=observe_months_back,
                    source_constraints=observe_source_constraints,
                    ai_model=ai_model,
                    persist=True,
                )
                searched_links = int(collected.get("searched_links", 0))
                observations = collected.get("observations", [])
                observe_logs = collected.get("status_logs", [])
                if not observations:
                    logger.warning(
                        "observe_first enabled but no observations found; skip graph source fallback to preserve constraints"
                    )
            elif not observations:
                observations = await self._collect_observations(graph, run_id)

            node_states: dict[str, dict[str, Any]] = {}

            for layer_index, layer in enumerate(graph.layers, start=1):
                tasks = [
                    self._process_node(
                        node=node,
                        layer_index=layer_index,
                        run_id=run_id,
                        graph_id=graph.graph_id,
                        observations=observations,
                        node_states=node_states,
                    )
                    for node in layer.nodes
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for result in results:
                    if isinstance(result, Exception):
                        logger.exception("Node processing failed: %s", result)
                        continue
                    node_states[result["id"]] = result

            conclusion_rows = await self._build_conclusions(graph, run_id, node_states)
            upsert_conclusions(conclusion_rows)

            self._mark_run_finished(run_id, "done")
            return {
                "run_id": run_id,
                "graph_id": graph.graph_id,
                "status": "done",
                "observations": len(observations),
                "searched_links": searched_links,
                "nodes": len(node_states),
                "conclusions": len(conclusion_rows),
                "observe_logs": observe_logs,
            }
        except Exception:
            self._mark_run_finished(run_id, "failed")
            raise

    async def _collect_observations(self, graph: GraphConfig, run_id: str) -> list[dict[str, Any]]:
        async def _collect_source(source: Any) -> list[dict[str, Any]]:
            try:
                body = await fetch(source.url, {"method": source.method, "tags": source.tags})
                parsed = await self.parse_agent.parse(
                    body,
                    topic=graph.topic,
                    default_tags=source.tags,
                    model=self.ai_model,
                )
                rows: list[dict[str, Any]] = []
                for item in parsed:
                    rows.append(
                        {
                            "id": gen_record_id("obs"),
                            "run_id": run_id,
                            "source": source.method,
                            "content": item["content"],
                            "url": source.url,
                            "confidence": round(float(item["confidence"]), 3),
                            "tags": item.get("tags", []),
                        }
                    )
                return rows
            except Exception as exc:
                logger.warning("Skip source due to error: %s | %s", source.url, exc)
                return []

        grouped = await asyncio.gather(*[_collect_source(source) for source in graph.sources])
        rows = [row for group in grouped for row in group]
        create_observations(rows)
        return rows

    async def _process_node(
        self,
        node: NodeConfig,
        layer_index: int,
        run_id: str,
        graph_id: str,
        observations: list[dict[str, Any]],
        node_states: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        if layer_index == 1:
            return self._process_p1_node(node, layer_index, run_id, graph_id, observations)

        inputs: list[dict[str, Any]] = []
        for item in node.inputs:
            upstream = node_states.get(item.node)
            if not upstream:
                continue
            inputs.append(
                {
                    "node_id": item.node,
                    "label": upstream["label"],
                    "weight": item.weight,
                    "probability": upstream["probability"],
                }
            )

        base = round(formula_prob(inputs), 3)
        delta, reason = await self.reasoning_agent.infer_delta(node.label, inputs, base, model=self.ai_model)
        probability = round(final_prob(base, delta), 3)
        band = confidence_band(probability, layer_index)

        row = {
            "id": node.id,
            "run_id": run_id,
            "graph_id": graph_id,
            "layer": layer_index,
            "label": node.label,
            "probability": probability,
            "formula_prob": base,
            "llm_delta": round(delta, 3),
            "reasoning": reason,
            "inputs": inputs,
            "observation_ids": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        upsert_event_nodes([row])
        return row

    def _process_p1_node(
        self,
        node: NodeConfig,
        layer_index: int,
        run_id: str,
        graph_id: str,
        observations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        matches = [
            item
            for item in observations
            if set(node.observation_tags).intersection(set(item.get("tags", [])))
        ]

        if not matches:
            probability = 0.5
            reason = "no_observations"
            obs_ids: list[str] = []
        else:
            probability = round(
                sum(float(item.get("confidence", 0.5)) for item in matches) / len(matches),
                3,
            )
            reason = "aggregated_from_observations"
            obs_ids = [item["id"] for item in matches]

        band = confidence_band(probability, layer_index)
        row = {
            "id": node.id,
            "run_id": run_id,
            "graph_id": graph_id,
            "layer": layer_index,
            "label": node.label,
            "probability": round(probability, 3),
            "formula_prob": round(probability, 3),
            "llm_delta": 0.0,
            "reasoning": reason,
            "inputs": [],
            "observation_ids": obs_ids,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        upsert_event_nodes([row])
        return row

    async def _build_conclusions(
        self,
        graph: GraphConfig,
        run_id: str,
        node_states: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        layer_index = len(graph.layers) + 1

        for conclusion in graph.conclusions:
            inputs = self._build_conclusion_inputs(conclusion, node_states)
            base = round(formula_prob(inputs), 3)
            band = confidence_band(base, layer_index)
            narrative = await self.conclusion_agent.generate(
                label=conclusion.label,
                probability=base,
                confidence_band=band,
                supporting_nodes=[item["label"] for item in inputs],
                model=self.ai_model,
            )

            rows.append(
                {
                    "id": conclusion.id,
                    "run_id": run_id,
                    "graph_id": graph.graph_id,
                    "label": conclusion.label,
                    "probability": base,
                    "confidence_band": [band[0], band[1]],
                    "narrative": narrative,
                    "supporting_event_ids": [item["node_id"] for item in inputs],
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )

        return rows

    def _build_conclusion_inputs(
        self,
        conclusion: ConclusionConfig,
        node_states: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        inputs: list[dict[str, Any]] = []
        for item in conclusion.inputs:
            upstream = node_states.get(item.node)
            if not upstream:
                continue
            inputs.append(
                {
                    "node_id": item.node,
                    "label": upstream["label"],
                    "weight": item.weight,
                    "probability": upstream["probability"],
                }
            )
        return inputs

    def _mark_run_started(self, run_id: str, graph_id: str) -> None:
        insert_rows(
            "runs",
            [
                {
                    "id": run_id,
                    "graph_id": graph_id,
                    "status": "running",
                    "started_at": datetime.now(timezone.utc).isoformat(),
                }
            ],
        )

    def _mark_run_finished(self, run_id: str, status: str) -> None:
        update_rows(
            "runs",
            match={"id": run_id},
            payload={
                "status": status,
                "finished_at": datetime.now(timezone.utc).isoformat(),
            },
        )
