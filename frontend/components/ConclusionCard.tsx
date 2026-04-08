export type Conclusion = {
  id: string;
  label: string;
  probability: number;
  confidence_band?: [number, number];
  narrative?: string;
};

function riskColor(probability: number): string {
  if (probability > 0.7) return "text-riskHigh";
  if (probability > 0.4) return "text-riskMid";
  return "text-riskLow";
}

export function ConclusionCard({ item }: { item: Conclusion }) {
  return (
    <article className="panel p-4">
      <h3 className="text-lg font-semibold tracking-wide">{item.label}</h3>
      <p className={`mt-2 font-mono text-2xl ${riskColor(item.probability)}`}>
        {(item.probability * 100).toFixed(1)}%
      </p>
      <p className="mt-1 text-sm text-secondaryText">
        CI: [{item.confidence_band?.[0] ?? "-"}, {item.confidence_band?.[1] ?? "-"}]
      </p>
      <p className="mt-3 text-sm text-secondaryText">{item.narrative ?? "暂无 narrative"}</p>
    </article>
  );
}
