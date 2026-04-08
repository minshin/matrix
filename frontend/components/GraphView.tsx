"use client";

import { useMemo, useState } from "react";
import ReactFlow, { Background, Controls, Edge, Node } from "reactflow";
import "reactflow/dist/style.css";

import { NodeDetail, NodeDetailData } from "@/components/NodeDetail";

type GraphNode = Node<NodeDetailData>;

type GraphViewProps = {
  nodes: GraphNode[];
  edges: Edge[];
};

export function GraphView({ nodes, edges }: GraphViewProps) {
  const [selected, setSelected] = useState<NodeDetailData | null>(null);

  const stableNodes = useMemo(
    () =>
      nodes.map((node) => ({
        ...node,
        style: {
          border: "1px solid #333",
          borderRadius: 12,
          padding: 8,
          background: "#1E293B",
          color: "#F0F0F0",
          width: 230,
          ...node.style,
        },
      })),
    [nodes],
  );

  return (
    <section className="grid gap-4 lg:grid-cols-[1fr_320px]">
      <div className="panel h-[72vh] overflow-hidden p-2">
        <ReactFlow
          nodes={stableNodes}
          edges={edges.map((edge) => ({ ...edge, style: { stroke: "#333" } }))}
          onNodeClick={(_, node) => setSelected(node.data)}
          fitView
        >
          <Background color="#222" gap={18} />
          <Controls />
        </ReactFlow>
      </div>
      <NodeDetail node={selected} />
    </section>
  );
}
