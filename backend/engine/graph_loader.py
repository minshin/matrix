from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class SourceConfig:
    url: str
    method: str = "auto"
    tags: list[str] = field(default_factory=list)


@dataclass
class NodeInput:
    node: str
    weight: float


@dataclass
class NodeConfig:
    id: str
    label: str
    observation_tags: list[str] = field(default_factory=list)
    inputs: list[NodeInput] = field(default_factory=list)


@dataclass
class LayerConfig:
    id: str
    label: str
    nodes: list[NodeConfig]


@dataclass
class ConclusionConfig:
    id: str
    label: str
    inputs: list[NodeInput]


@dataclass
class GraphConfig:
    graph_id: str
    name: str
    version: int
    topic: str
    sources: list[SourceConfig]
    layers: list[LayerConfig]
    conclusions: list[ConclusionConfig]


def load_graph_config(graph_id: str, graph_path: str | None = None) -> GraphConfig:
    path = Path(graph_path) if graph_path else Path("graphs") / f"{graph_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Graph file not found: {path}")

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))

    graph = GraphConfig(
        graph_id=payload["graph_id"],
        name=payload["name"],
        version=int(payload.get("version", 1)),
        topic=payload["topic"],
        sources=[SourceConfig(**source) for source in payload.get("sources", [])],
        layers=[
            LayerConfig(
                id=layer["id"],
                label=layer["label"],
                nodes=[
                    NodeConfig(
                        id=node["id"],
                        label=node["label"],
                        observation_tags=node.get("observation_tags", []),
                        inputs=[NodeInput(**item) for item in node.get("inputs", [])],
                    )
                    for node in layer.get("nodes", [])
                ],
            )
            for layer in payload.get("layers", [])
        ],
        conclusions=[
            ConclusionConfig(
                id=item["id"],
                label=item["label"],
                inputs=[NodeInput(**node_input) for node_input in item.get("inputs", [])],
            )
            for item in payload.get("conclusions", [])
        ],
    )

    _validate_graph(graph)
    return graph


def _validate_graph(graph: GraphConfig) -> None:
    node_to_layer: dict[str, int] = {}
    layer_ids: set[str] = set()

    for layer_index, layer in enumerate(graph.layers):
        if layer.id in layer_ids:
            raise ValueError(f"Duplicate layer id: {layer.id}")
        layer_ids.add(layer.id)

        for node in layer.nodes:
            if node.id in node_to_layer:
                raise ValueError(f"Duplicate node id: {node.id}")
            node_to_layer[node.id] = layer_index

    for layer_index, layer in enumerate(graph.layers):
        if layer_index == 0:
            for node in layer.nodes:
                if node.inputs:
                    raise ValueError(f"P1 node should not have inputs: {node.id}")
            continue

        for node in layer.nodes:
            for item in node.inputs:
                if item.node not in node_to_layer:
                    raise ValueError(f"Node '{node.id}' references missing input '{item.node}'")

                source_layer = node_to_layer[item.node]
                if source_layer == layer_index:
                    raise ValueError(f"Node '{node.id}' has same-layer dependency '{item.node}'")
                if source_layer != layer_index - 1:
                    raise ValueError(
                        f"Node '{node.id}' cross-layer dependency '{item.node}' not allowed"
                    )

    for conclusion in graph.conclusions:
        for item in conclusion.inputs:
            if item.node not in node_to_layer:
                raise ValueError(
                    f"Conclusion '{conclusion.id}' references missing node '{item.node}'"
                )
