import { NextRequest, NextResponse } from "next/server";
import type { Edge, Node } from "reactflow";

import type { NodeDetailData } from "@/components/NodeDetail";
import { supabaseServer } from "@/lib/supabase-server";

type RunRow = {
  id: string;
  graph_id: string;
  status: string;
  started_at: string | null;
};

type EventNodeRow = {
  id: string;
  layer: number;
  label: string;
  probability: number;
  formula_prob: number | null;
  llm_delta: number | null;
  reasoning: string | null;
  inputs: unknown;
};

type ConclusionRow = {
  id: string;
  label: string;
  probability: number;
  confidence_band: unknown;
  narrative: string | null;
  supporting_event_ids: unknown;
  created_at: string | null;
};

type GraphData = {
  runId: string | null;
  nodes: Node<NodeDetailData>[];
  edges: Edge[];
};

function layerColor(layer: number, isConclusion = false): string {
  if (isConclusion) return "#3D1F1F";
  if (layer === 1) return "#1E293B";
  if (layer === 2) return "#1E3A2F";
  if (layer === 3) return "#2D1F3D";
  return "#2D1F3D";
}

function toNumber(value: unknown, fallback = 0.5): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function toStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => String(item)).filter(Boolean);
}

function toInputArray(value: unknown): Array<Record<string, unknown>> {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === "object");
}

async function fetchGraphData(graphId: string): Promise<GraphData> {
  if (!supabaseServer) {
    return { runId: null, nodes: [], edges: [] };
  }

  const runResp = await supabaseServer
    .from("runs")
    .select("id,graph_id,status,started_at")
    .eq("graph_id", graphId)
    .eq("status", "done")
    .order("started_at", { ascending: false })
    .limit(1);

  const run = (runResp.data?.[0] as RunRow | undefined) ?? null;
  if (!run) {
    return { runId: null, nodes: [], edges: [] };
  }

  const [eventResp, conclusionResp] = await Promise.all([
    supabaseServer
      .from("event_nodes")
      .select("id,layer,label,probability,formula_prob,llm_delta,reasoning,inputs")
      .eq("run_id", run.id)
      .order("layer", { ascending: true }),
    supabaseServer
      .from("conclusions")
      .select("id,label,probability,narrative,supporting_event_ids")
      .eq("run_id", run.id),
  ]);

  const eventRows = ((eventResp.data ?? []) as EventNodeRow[]).sort(
    (a, b) => a.layer - b.layer || a.id.localeCompare(b.id),
  );
  const conclusionRows = (conclusionResp.data ?? []) as ConclusionRow[];

  const grouped = new Map<number, EventNodeRow[]>();
  for (const row of eventRows) {
    if (!grouped.has(row.layer)) grouped.set(row.layer, []);
    grouped.get(row.layer)!.push(row);
  }

  const layerValues = [...grouped.keys()].sort((a, b) => a - b);
  const layerIndex = new Map(layerValues.map((value, index) => [value, index]));

  const nodes: Node<NodeDetailData>[] = [];

  for (const layer of layerValues) {
    const x = 80 + (layerIndex.get(layer) ?? 0) * 320;
    const rows = grouped.get(layer) ?? [];
    rows.forEach((row, idx) => {
      nodes.push({
        id: row.id,
        type: "default",
        position: { x, y: 60 + idx * 150 },
        data: {
          id: row.id,
          label: row.label,
          probability: toNumber(row.probability, 0.5),
          formula_prob: toNumber(row.formula_prob, 0.5),
          llm_delta: toNumber(row.llm_delta, 0),
          reasoning: row.reasoning ?? "-",
        },
        style: { background: layerColor(layer) },
      });
    });
  }

  const conclusionLayerX = 80 + layerValues.length * 320;
  conclusionRows
    .sort((a, b) => a.id.localeCompare(b.id))
    .forEach((row, idx) => {
      nodes.push({
        id: row.id,
        type: "default",
        position: { x: conclusionLayerX, y: 60 + idx * 150 },
        data: {
          id: row.id,
          label: row.label,
          probability: toNumber(row.probability, 0.5),
          formula_prob: toNumber(row.probability, 0.5),
          llm_delta: 0,
          reasoning: row.narrative ?? "-",
        },
        style: { background: layerColor(0, true) },
      });
    });

  const edgeMap = new Map<string, Edge>();
  for (const row of eventRows) {
    for (const input of toInputArray(row.inputs)) {
      const source = String(input.node_id ?? input.node ?? "");
      if (!source) continue;
      const edgeId = `${source}->${row.id}`;
      edgeMap.set(edgeId, { id: edgeId, source, target: row.id });
    }
  }

  for (const row of conclusionRows) {
    for (const source of toStringArray(row.supporting_event_ids)) {
      const edgeId = `${source}->${row.id}`;
      edgeMap.set(edgeId, { id: edgeId, source, target: row.id });
    }
  }

  return {
    runId: run.id,
    nodes,
    edges: [...edgeMap.values()],
  };
}

async function fetchConclusions(graphId: string): Promise<ConclusionRow[]> {
  if (!supabaseServer) return [];
  const { data, error } = await supabaseServer
    .from("conclusions")
    .select("id,label,probability,confidence_band,narrative,supporting_event_ids,created_at,graph_id")
    .eq("graph_id", graphId)
    .order("created_at", { ascending: false })
    .limit(24);
  if (error) return [];
  return (data ?? []) as ConclusionRow[];
}

export async function GET(request: NextRequest) {
  const graphId = request.nextUrl.searchParams.get("graph_id")?.trim() || "hormuz_blockade_7d";

  const [graph, conclusions] = await Promise.all([fetchGraphData(graphId), fetchConclusions(graphId)]);

  return NextResponse.json({
    ok: true,
    graph_id: graphId,
    graph,
    conclusions,
  });
}
