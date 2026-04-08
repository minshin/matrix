export type NodeDetailData = {
  id: string;
  label: string;
  probability: number;
  formula_prob?: number;
  llm_delta?: number;
  reasoning?: string;
};

export function NodeDetail({ node }: { node: NodeDetailData | null }) {
  if (!node) {
    return <aside className="panel p-4 text-sm text-secondaryText">点击节点查看详情</aside>;
  }

  return (
    <aside className="panel p-4 text-sm">
      <h3 className="text-base font-semibold">{node.label}</h3>
      <p className="mt-2 font-mono">P: {node.probability.toFixed(3)}</p>
      <p className="font-mono">Formula: {(node.formula_prob ?? 0).toFixed(3)}</p>
      <p className="font-mono">Delta: {(node.llm_delta ?? 0).toFixed(3)}</p>
      <p className="mt-2 text-secondaryText">{node.reasoning ?? "-"}</p>
    </aside>
  );
}
