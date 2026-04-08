"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { Edge, Node } from "reactflow";

import { GraphView } from "@/components/GraphView";
import type { NodeDetailData } from "@/components/NodeDetail";

type MainTabKey = "observation" | "forcast" | "result";
type MenuKey = "main" | "setting";

type ObservationMeta = {
  query?: string;
  engine?: string;
  title?: string;
  parse_probability?: number;
  source_probability?: number;
  published_at?: string;
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
  months_back: number;
  source_constraints: string[];
  searched_links: number;
  observations_count: number;
  status_logs?: string[];
  observations: ObservationItem[];
};

type Conclusion = {
  id: string;
  label: string;
  probability: number;
  confidence_band?: [number, number];
  narrative?: string;
};

type DashboardPayload = {
  ok: boolean;
  graph?: {
    runId: string | null;
    nodes: Node<NodeDetailData>[];
    edges: Edge[];
  };
  conclusions?: Conclusion[];
  error?: string;
};

const DEFAULT_GRAPH_ID = "hormuz_blockade_7d";
const DEFAULT_MODEL = "minimax/minimax-m1";
const MAIN_TABS: Array<{ key: MainTabKey; label: string }> = [
  { key: "observation", label: "Observation" },
  { key: "forcast", label: "Forcast" },
  { key: "result", label: "Result" },
];
const MENU_ITEMS: Array<{ key: MenuKey; label: string }> = [
  { key: "main", label: "Main" },
  { key: "setting", label: "Setting" },
];

function buildStatusQueries(botCount: number): string[] {
  const count = Math.max(1, Math.min(botCount, 10));
  const lines: string[] = [];
  for (let i = 0; i < count; i += 1) {
    lines.push(`Query #${i + 1}: generating...`);
    lines.push(`Effective Query #${i + 1}: waiting for backend...`);
  }
  return lines;
}

function parseSourceConstraints(input: string): string[] {
  return input
    .split(/[\n,，]/g)
    .map((item) => item.trim())
    .filter(Boolean);
}

function formatTimestamp(raw?: string): string {
  if (!raw) return "-";
  const dt = new Date(raw);
  if (Number.isNaN(dt.getTime())) return raw;
  return dt.toLocaleString("zh-CN", { hour12: false });
}

function sortObservations(items: ObservationItem[]): ObservationItem[] {
  return [...items].sort((a, b) => {
    const ta = Date.parse(a.meta?.published_at ?? "");
    const tb = Date.parse(b.meta?.published_at ?? "");
    if (Number.isNaN(ta) && Number.isNaN(tb)) return b.id.localeCompare(a.id);
    if (Number.isNaN(ta)) return 1;
    if (Number.isNaN(tb)) return -1;
    return tb - ta;
  });
}

function probabilityTextColor(probability: number): string {
  if (probability > 0.7) return "text-[#d94848]";
  if (probability > 0.4) return "text-[#c98b1d]";
  return "text-[#2f8a3f]";
}

export function MatrixWorkspace() {
  const [activeMenu, setActiveMenu] = useState<MenuKey>("main");
  const [activeMainTab, setActiveMainTab] = useState<MainTabKey>("observation");

  const [topic, setTopic] = useState("黄金未来1个月是否会涨");
  const [botCount, setBotCount] = useState(5);
  const [resultsPerBot, setResultsPerBot] = useState(5);
  const [monthsBack, setMonthsBack] = useState(1);
  const [sourceConstraintsInput, setSourceConstraintsInput] = useState("");
  const [modelOptions, setModelOptions] = useState<string[]>([DEFAULT_MODEL]);
  const [aiModel, setAiModel] = useState(DEFAULT_MODEL);

  const [observationLoading, setObservationLoading] = useState(false);
  const [observationError, setObservationError] = useState("");
  const [observationResult, setObservationResult] = useState<ObserveResult | null>(null);
  const [statusLogs, setStatusLogs] = useState<string[]>([]);
  const [visibleCount, setVisibleCount] = useState(10);

  const [runLoading, setRunLoading] = useState(false);
  const [runMessage, setRunMessage] = useState("");
  const [runError, setRunError] = useState("");

  const [dashboardLoading, setDashboardLoading] = useState(false);
  const [dashboardError, setDashboardError] = useState("");
  const [runId, setRunId] = useState<string | null>(null);
  const [graphNodes, setGraphNodes] = useState<Node<NodeDetailData>[]>([]);
  const [graphEdges, setGraphEdges] = useState<Edge[]>([]);
  const [conclusions, setConclusions] = useState<Conclusion[]>([]);

  const statusRef = useRef<HTMLDivElement | null>(null);

  const sourceConstraints = useMemo(
    () => parseSourceConstraints(sourceConstraintsInput),
    [sourceConstraintsInput],
  );
  const sortedObservations = useMemo(
    () => sortObservations(observationResult?.observations ?? []),
    [observationResult],
  );

  useEffect(() => {
    async function loadModels() {
      try {
        const response = await fetch("/api/models", { method: "GET", cache: "no-store" });
        const payload = (await response.json()) as { ok?: boolean; models?: string[] };
        if (!response.ok || !payload.ok || !Array.isArray(payload.models) || payload.models.length === 0) {
          return;
        }
        setModelOptions(payload.models);
        setAiModel((prev) => (payload.models?.includes(prev) ? prev : payload.models![0]));
      } catch {
        // Keep default model if model API is unavailable.
      }
    }
    void loadModels();
  }, []);

  useEffect(() => {
    void refreshDashboard();
  }, []);

  useEffect(() => {
    if (!statusRef.current) return;
    statusRef.current.scrollTop = statusRef.current.scrollHeight;
  }, [statusLogs]);

  async function refreshDashboard() {
    setDashboardLoading(true);
    setDashboardError("");

    try {
      const response = await fetch(`/api/dashboard?graph_id=${encodeURIComponent(DEFAULT_GRAPH_ID)}`, {
        method: "GET",
        cache: "no-store",
      });
      const payload = (await response.json()) as DashboardPayload;
      if (!response.ok || !payload.ok) {
        setDashboardError(payload.error ?? "failed to load dashboard data");
        return;
      }
      setRunId(payload.graph?.runId ?? null);
      setGraphNodes(payload.graph?.nodes ?? []);
      setGraphEdges(payload.graph?.edges ?? []);
      setConclusions(payload.conclusions ?? []);
    } catch (error) {
      setDashboardError(error instanceof Error ? error.message : "failed to load dashboard data");
    } finally {
      setDashboardLoading(false);
    }
  }

  async function generateObservation() {
    if (!topic.trim()) return;

    setObservationLoading(true);
    setObservationError("");
    setObservationResult(null);
    setVisibleCount(10);
    setStatusLogs([
      `Start fetch: ${topic.trim()}`,
      `Config: bots=${botCount}, per_bot=${resultsPerBot}, months_back=${monthsBack}, model=${aiModel}`,
      `Source constraints: ${sourceConstraints.length > 0 ? sourceConstraints.join(", ") : "none"}`,
    ]);

    const fakeQueries = buildStatusQueries(botCount);
    let cursor = 0;
    const timer = setInterval(() => {
      if (cursor >= fakeQueries.length) {
        setStatusLogs((prev) => {
          if (prev[prev.length - 1] === "Waiting for page responses...") return prev;
          return [...prev, "Waiting for page responses..."];
        });
        return;
      }
      const query = fakeQueries[cursor];
      cursor += 1;
      if (!query) return;
      setStatusLogs((prev) => [...prev, `正在抓取: ${query}`]);
    }, 900);

    try {
      const response = await fetch("/api/observe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          topic,
          bot_count: botCount,
          results_per_bot: resultsPerBot,
          months_back: monthsBack,
          source_constraints: sourceConstraints,
          ai_model: aiModel,
        }),
      });

      const payload = (await response.json()) as {
        ok?: boolean;
        error?: string;
        result?: ObserveResult;
      };

      if (!response.ok || !payload.ok || !payload.result) {
        setObservationError(payload.error ?? "observation failed");
        return;
      }

      const result = payload.result;
      setObservationResult(result);
      setStatusLogs((prev) => [
        ...prev,
        ...(result.status_logs ?? []),
        `Done: links=${result.searched_links}, observations=${result.observations_count}`,
      ]);
    } catch (error) {
      setObservationError(error instanceof Error ? error.message : "observation failed");
    } finally {
      clearInterval(timer);
      setObservationLoading(false);
    }
  }

  async function triggerRun() {
    setRunLoading(true);
    setRunError("");
    setRunMessage("");
    try {
      const response = await fetch("/api/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          graph_id: DEFAULT_GRAPH_ID,
          topic,
          bot_count: botCount,
          results_per_bot: resultsPerBot,
          months_back: monthsBack,
          source_constraints: sourceConstraints,
          ai_model: aiModel,
        }),
      });
      const payload = (await response.json()) as {
        ok?: boolean;
        error?: string;
        result?: { run_id?: string; observations?: number; conclusions?: number };
      };
      if (!response.ok || !payload.ok) {
        setRunError(payload.error ?? "run failed");
        return;
      }
      setRunMessage(
        payload.result?.run_id
          ? `运行完成: ${payload.result.run_id} (observations=${payload.result.observations ?? 0}, conclusions=${payload.result.conclusions ?? 0})`
          : "运行完成",
      );
      await refreshDashboard();
      setActiveMainTab("forcast");
      setActiveMenu("main");
    } catch (error) {
      setRunError(error instanceof Error ? error.message : "run failed");
    } finally {
      setRunLoading(false);
    }
  }

  return (
    <section className="min-h-screen border border-[#d9dbe1] bg-[#f7f7f9] text-[#1f2430]">
      <div className="grid min-h-screen lg:grid-cols-[220px_1fr]">
        <aside className="border-r border-[#dedfe5] bg-[#f0f1f5] p-4">
          <div className="mb-6 flex items-center gap-2">
            <span className="text-sm font-semibold">Matrix Console</span>
          </div>
          <nav className="space-y-1">
            {MENU_ITEMS.map((item) => (
              <button
                key={item.key}
                className={`w-full rounded-md px-3 py-2 text-left text-sm ${
                  activeMenu === item.key
                    ? "bg-white text-[#111827] shadow-sm"
                    : "text-[#5e6472] hover:bg-white/70"
                }`}
                onClick={() => setActiveMenu(item.key)}
                type="button"
              >
                {item.label}
              </button>
            ))}
          </nav>
        </aside>

        <main className="space-y-4 p-5">
          {activeMenu === "main" ? (
            <div className="flex gap-1 border-b border-[#e4e5ea] pb-2">
              {MAIN_TABS.map((tab) => (
                <button
                  key={tab.key}
                  className={`rounded-md px-3 py-1.5 text-sm ${
                    activeMainTab === tab.key
                      ? "bg-white text-[#111827] shadow-sm"
                      : "text-[#6b7280] hover:text-[#374151]"
                  }`}
                  onClick={() => setActiveMainTab(tab.key)}
                  type="button"
                >
                  {tab.label}
                </button>
              ))}
            </div>
          ) : null}

          {activeMenu === "setting" ? (
            <section className="space-y-4 rounded-xl border border-[#e4e5ea] bg-white p-4">
              <h2 className="text-lg font-semibold">Setting</h2>
              <div className="grid gap-3 md:grid-cols-2">
                <label className="space-y-1 text-sm">
                  <span className="text-[#6b7280]">bots 数量（默认5）</span>
                  <input
                    className="w-full rounded-md border border-[#d9dbe1] bg-white px-3 py-2 text-sm outline-none focus:border-[#8d93a4]"
                    max={10}
                    min={1}
                    onChange={(e) => setBotCount(Number(e.target.value))}
                    type="number"
                    value={botCount}
                  />
                </label>

                <label className="space-y-1 text-sm">
                  <span className="text-[#6b7280]">每 bot 条数（默认5）</span>
                  <input
                    className="w-full rounded-md border border-[#d9dbe1] bg-white px-3 py-2 text-sm outline-none focus:border-[#8d93a4]"
                    max={10}
                    min={1}
                    onChange={(e) => setResultsPerBot(Number(e.target.value))}
                    type="number"
                    value={resultsPerBot}
                  />
                </label>

                <label className="space-y-1 text-sm">
                  <span className="text-[#6b7280]">AI 模型（默认 minimax）</span>
                  <select
                    className="w-full rounded-md border border-[#d9dbe1] bg-white px-3 py-2 text-sm outline-none focus:border-[#8d93a4]"
                    onChange={(e) => setAiModel(e.target.value)}
                    value={aiModel}
                  >
                    {modelOptions.map((model) => (
                      <option key={model} value={model}>
                        {model}
                      </option>
                    ))}
                  </select>
                </label>

                <label className="space-y-1 text-sm">
                  <span className="text-[#6b7280]">信源时间（最近 n 个月，默认1）</span>
                  <input
                    className="w-full rounded-md border border-[#d9dbe1] bg-white px-3 py-2 text-sm outline-none focus:border-[#8d93a4]"
                    max={24}
                    min={1}
                    onChange={(e) => setMonthsBack(Number(e.target.value))}
                    type="number"
                    value={monthsBack}
                  />
                </label>
              </div>

              <label className="block space-y-1 text-sm">
                <span className="text-[#6b7280]">
                  信源约束（逗号分隔，示例：reuters.com, ft.com, washingtonpost.com, nikkei.com）
                </span>
                <textarea
                  className="h-28 w-full rounded-md border border-[#d9dbe1] bg-white px-3 py-2 text-sm outline-none focus:border-[#8d93a4]"
                  onChange={(e) => setSourceConstraintsInput(e.target.value)}
                  placeholder="留空表示不限制信源"
                  value={sourceConstraintsInput}
                />
              </label>
            </section>
          ) : null}

          {activeMenu === "main" && activeMainTab === "observation" ? (
            <section className="space-y-4 rounded-xl border border-[#e4e5ea] bg-white p-4">
              <div className="grid gap-3 md:grid-cols-[1fr_220px]">
                <input
                  className="rounded-md border border-[#d9dbe1] bg-white px-3 py-2 text-sm outline-none focus:border-[#8d93a4]"
                  onChange={(e) => setTopic(e.target.value)}
                  placeholder="例如：黄金未来1个月是否会涨"
                  value={topic}
                />
                <button
                  className="rounded-md border border-[#cfd2da] bg-[#f5f6fa] px-4 py-2 text-sm hover:bg-[#eceff6] disabled:opacity-50"
                  disabled={observationLoading}
                  onClick={generateObservation}
                  type="button"
                >
                  {observationLoading ? "Fetching..." : "Generate Observation"}
                </button>
              </div>

              <div className="rounded-lg border border-[#e4e5ea] bg-[#fafbfc] px-3 py-2 text-xs text-[#6b7280]">
                <span>Current config: </span>
                <span>bots={botCount}</span>
                <span className="mx-2">|</span>
                <span>per_bot={resultsPerBot}</span>
                <span className="mx-2">|</span>
                <span>months_back={monthsBack}</span>
                <span className="mx-2">|</span>
                <span>model={aiModel}</span>
                <span className="mx-2">|</span>
                <span>
                  source_constraints=
                  {sourceConstraints.length > 0 ? sourceConstraints.join(", ") : "none"}
                </span>
              </div>

              <div className="rounded-lg border border-[#e4e5ea] bg-[#fafbfc] p-3">
                <p className="mb-2 text-xs text-[#6b7280]">状态栏</p>
                <div className="h-44 overflow-auto pr-1 text-xs leading-6 text-[#4b5563]" ref={statusRef}>
                  {statusLogs.length === 0 ? (
                    <p>等待开始...</p>
                  ) : (
                    statusLogs.map((log, idx) => <p key={`${idx}-${log}`}>{log}</p>)
                  )}
                </div>
              </div>

              {observationError ? <p className="text-sm text-[#dc2626]">{observationError}</p> : null}

              {observationResult ? (
                <div className="space-y-3">
                  <p className="text-xs text-[#6b7280]">
                    run_id: {observationResult.run_id} | links: {observationResult.searched_links} | observations:{" "}
                    {observationResult.observations_count}
                  </p>
                  <p className="text-xs text-[#6b7280]">
                    Effective constraints from backend:{" "}
                    {observationResult.source_constraints.length > 0
                      ? observationResult.source_constraints.join(", ")
                      : "none"}
                  </p>
                  <div className="space-y-2">
                    {sortedObservations.slice(0, visibleCount).map((item) => (
                      <article className="rounded-lg border border-[#e4e5ea] bg-white p-3" key={item.id}>
                        <p className="text-sm leading-6">{item.content}</p>
                        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-[#6b7280]">
                          <span>概率: {item.probability.toFixed(3)}</span>
                          <span>来源: {item.source}</span>
                          <span>时间: {formatTimestamp(item.meta?.published_at)}</span>
                        </div>
                        <a
                          className="mt-1 block break-all text-xs text-[#4f46e5] underline"
                          href={item.url}
                          rel="noreferrer"
                          target="_blank"
                        >
                          {item.url}
                        </a>
                      </article>
                    ))}
                  </div>
                  {visibleCount < sortedObservations.length ? (
                    <button
                      className="rounded-md border border-[#d9dbe1] px-4 py-2 text-sm hover:bg-[#f6f7fb]"
                      onClick={() => setVisibleCount((prev) => prev + 10)}
                      type="button"
                    >
                      加载更多 ▼
                    </button>
                  ) : null}
                </div>
              ) : null}
            </section>
          ) : null}

          {activeMenu === "main" && activeMainTab === "forcast" ? (
            <section className="space-y-4">
              <div className="rounded-xl border border-[#e4e5ea] bg-white p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h2 className="text-lg font-semibold">Forcast</h2>
                    <p className="text-xs text-[#6b7280]">Run: {runId ?? "暂无可用 run"}</p>
                  </div>
                  <div className="flex gap-2">
                    <button
                      className="rounded-md border border-[#cfd2da] bg-[#f5f6fa] px-4 py-2 text-sm hover:bg-[#eceff6] disabled:opacity-50"
                      disabled={runLoading}
                      onClick={triggerRun}
                      type="button"
                    >
                      {runLoading ? "运行中..." : "手动触发 Run"}
                    </button>
                    <button
                      className="rounded-md border border-[#cfd2da] bg-[#f5f6fa] px-4 py-2 text-sm hover:bg-[#eceff6] disabled:opacity-50"
                      disabled={dashboardLoading}
                      onClick={refreshDashboard}
                      type="button"
                    >
                      刷新数据
                    </button>
                  </div>
                </div>
                {runMessage ? <p className="mt-2 text-sm text-[#4b5563]">{runMessage}</p> : null}
                {runError ? <p className="mt-2 text-sm text-[#dc2626]">{runError}</p> : null}
                {dashboardError ? <p className="mt-2 text-sm text-[#dc2626]">{dashboardError}</p> : null}
              </div>

              {graphNodes.length === 0 ? (
                <div className="rounded-xl border border-[#e4e5ea] bg-white p-6 text-sm text-[#6b7280]">
                  当前图暂无节点数据。请先触发至少一次成功运行。
                </div>
              ) : (
                <div className="rounded-xl border border-[#e4e5ea] bg-white p-2">
                  <GraphView edges={graphEdges} nodes={graphNodes} />
                </div>
              )}
            </section>
          ) : null}

          {activeMenu === "main" && activeMainTab === "result" ? (
            <section className="space-y-4">
              <div className="rounded-xl border border-[#e4e5ea] bg-white p-4">
                <h2 className="text-lg font-semibold">Result</h2>
              </div>

              {conclusions.length === 0 ? (
                <div className="rounded-xl border border-[#e4e5ea] bg-white p-6 text-sm text-[#6b7280]">
                  暂无结论数据，请先触发一次运行。
                </div>
              ) : (
                <div className="grid gap-4 md:grid-cols-2">
                  {conclusions.map((item) => (
                    <article className="rounded-xl border border-[#e4e5ea] bg-white p-4" key={item.id}>
                      <h3 className="text-base font-semibold">{item.label}</h3>
                      <p className={`mt-2 text-2xl font-semibold ${probabilityTextColor(item.probability)}`}>
                        {(item.probability * 100).toFixed(1)}%
                      </p>
                      <p className="mt-1 text-xs text-[#6b7280]">
                        CI: [{item.confidence_band?.[0] ?? "-"}, {item.confidence_band?.[1] ?? "-"}]
                      </p>
                      <p className="mt-3 text-sm text-[#4b5563]">{item.narrative ?? "暂无 narrative"}</p>
                    </article>
                  ))}
                </div>
              )}
            </section>
          ) : null}
        </main>
      </div>
    </section>
  );
}
