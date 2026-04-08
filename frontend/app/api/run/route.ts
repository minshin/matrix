import { NextRequest, NextResponse } from "next/server";

type RunPayload = {
  graph_id?: string;
  topic?: string;
  bot_count?: number;
  results_per_bot?: number;
  months_back?: number;
  source_constraints?: string[];
  ai_model?: string;
};

export async function POST(request: NextRequest) {
  const endpoint = process.env.BACKEND_RUN_ENDPOINT?.trim() || "http://127.0.0.1:8000/run";
  const parsedTimeout = Number(process.env.BACKEND_RUN_TIMEOUT_MS ?? "300000");
  const timeoutMs = Number.isFinite(parsedTimeout) && parsedTimeout > 0 ? parsedTimeout : 300000;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const body = (await request.json().catch(() => ({}))) as RunPayload;
    const parsedBotCount = Number(body.bot_count ?? process.env.OBSERVE_BOT_COUNT ?? "5");
    const parsedResultsPerBot = Number(body.results_per_bot ?? process.env.OBSERVE_RESULTS_PER_BOT ?? "5");
    const parsedMonths = Number(body.months_back ?? "1");

    const observeBotCount =
      Number.isFinite(parsedBotCount) && parsedBotCount > 0 ? Math.min(parsedBotCount, 10) : 5;
    const observeResultsPerBot =
      Number.isFinite(parsedResultsPerBot) && parsedResultsPerBot > 0
        ? Math.min(parsedResultsPerBot, 10)
        : 5;
    const observeMonthsBack =
      Number.isFinite(parsedMonths) && parsedMonths > 0 ? Math.min(parsedMonths, 24) : 1;
    const sourceConstraints = Array.isArray(body.source_constraints)
      ? body.source_constraints.map((item) => String(item).trim()).filter(Boolean)
      : [];

    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        graph_id: body.graph_id?.trim() || "hormuz_blockade_7d",
        observe_first: true,
        observe_topic: body.topic?.trim() || undefined,
        observe_bot_count: observeBotCount,
        observe_results_per_bot: observeResultsPerBot,
        observe_months_back: observeMonthsBack,
        observe_source_constraints: sourceConstraints,
        ai_model: body.ai_model?.trim() || undefined,
      }),
      cache: "no-store",
      signal: controller.signal,
    });
    clearTimeout(timeout);

    if (!response.ok) {
      let backendError = `backend ${response.status}`;
      try {
        const payload = (await response.json()) as {
          detail?: string | { message?: string; run_id?: string };
        };
        if (typeof payload.detail === "string") {
          backendError = `backend ${response.status}: ${payload.detail}`;
        } else if (payload.detail?.message) {
          const runSuffix = payload.detail.run_id ? ` (run_id=${payload.detail.run_id})` : "";
          backendError = `backend ${response.status}: ${payload.detail.message}${runSuffix}`;
        }
      } catch {
        const text = await response.text();
        if (text) backendError = `backend ${response.status}: ${text}`;
      }

      const status = response.status === 409 ? 409 : 502;
      return NextResponse.json({ ok: false, error: backendError }, { status });
    }

    const payload = await response.json();
    return NextResponse.json({ ok: true, result: payload }, { status: 200 });
  } catch (error) {
    return NextResponse.json(
      {
        ok: false,
        error: `failed to call ${endpoint}: ${error instanceof Error ? error.message : "unknown error"}`,
      },
      { status: 502 },
    );
  } finally {
    clearTimeout(timeout);
  }
}
