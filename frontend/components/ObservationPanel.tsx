"use client";

import { useState } from "react";

type ObservationMeta = {
  query?: string;
  engine?: string;
  title?: string;
  parse_probability?: number;
  source_probability?: number;
};

type ObservationItem = {
  id: string;
  content: string;
  probability: number;
  url: string;
  source: string;
  tags: string[];
  meta?: ObservationMeta;
};

type ObserveResult = {
  run_id: string;
  topic: string;
  bot_count: number;
  results_per_bot: number;
  searched_links: number;
  observations_count: number;
  observations: ObservationItem[];
};

export function ObservationPanel() {
  const [topic, setTopic] = useState("黄金未来1个月是否会涨");
  const [botCount, setBotCount] = useState(5);
  const [resultsPerBot, setResultsPerBot] = useState(5);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>("");
  const [result, setResult] = useState<ObserveResult | null>(null);

  async function runObserve() {
    setLoading(true);
    setError("");

    try {
      const response = await fetch("/api/observe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          topic,
          bot_count: botCount,
          results_per_bot: resultsPerBot,
        }),
      });

      const payload = (await response.json()) as {
        ok?: boolean;
        error?: string;
        result?: ObserveResult;
      };

      if (!response.ok || !payload.ok || !payload.result) {
        setResult(null);
        setError(payload.error ?? "observation failed");
        return;
      }

      setResult(payload.result);
    } catch (err) {
      setResult(null);
      setError(err instanceof Error ? err.message : "unknown error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="panel space-y-4 p-4">
      <div>
        <h2 className="text-xl font-semibold">Observation 层开发面板</h2>
        <p className="mt-1 text-xs text-secondaryText">
          输入命题，按配置启动搜索 bots（默认 5 bots × 5 结果）。
        </p>
      </div>

      <div className="grid gap-3 md:grid-cols-[1fr_120px_140px_160px]">
        <input
          className="rounded-lg border border-border bg-black/20 px-3 py-2 text-sm outline-none focus:border-secondaryText"
          onChange={(e) => setTopic(e.target.value)}
          placeholder="例如：黄金未来1个月是否会涨"
          value={topic}
        />

        <label className="flex items-center gap-2 text-xs text-secondaryText">
          bots
          <input
            className="w-full rounded-lg border border-border bg-black/20 px-2 py-2 text-sm text-primaryText"
            max={10}
            min={1}
            onChange={(e) => setBotCount(Number(e.target.value))}
            type="number"
            value={botCount}
          />
        </label>

        <label className="flex items-center gap-2 text-xs text-secondaryText">
          每 bot 条数
          <input
            className="w-full rounded-lg border border-border bg-black/20 px-2 py-2 text-sm text-primaryText"
            max={10}
            min={1}
            onChange={(e) => setResultsPerBot(Number(e.target.value))}
            type="number"
            value={resultsPerBot}
          />
        </label>

        <button
          className="rounded-lg border border-border px-4 py-2 text-sm hover:border-secondaryText disabled:opacity-50"
          disabled={loading || !topic.trim()}
          onClick={runObserve}
          type="button"
        >
          {loading ? "搜索中..." : "生成 Observation"}
        </button>
      </div>

      {error ? <p className="text-sm text-riskHigh">{error}</p> : null}

      {result ? (
        <div className="space-y-3">
          <p className="text-xs text-secondaryText">
            run_id: {result.run_id} | links: {result.searched_links} | observations: {result.observations_count}
          </p>

          <div className="max-h-[420px] space-y-2 overflow-auto pr-1">
            {result.observations.map((item) => (
              <article className="rounded-lg border border-border bg-black/10 p-3" key={item.id}>
                <p className="text-sm leading-6">{item.content}</p>
                <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-secondaryText">
                  <span>概率: {item.probability.toFixed(3)}</span>
                  <span>source: {item.source}</span>
                  <span>parse: {item.meta?.parse_probability ?? "-"}</span>
                  <span>source_score: {item.meta?.source_probability ?? "-"}</span>
                </div>
                <a className="mt-1 block break-all text-xs text-secondaryText underline" href={item.url} rel="noreferrer" target="_blank">
                  {item.url}
                </a>
              </article>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}
