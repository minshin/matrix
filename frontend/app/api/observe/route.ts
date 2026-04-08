import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest) {
  const endpoint =
    process.env.BACKEND_OBSERVE_ENDPOINT?.trim() || "http://127.0.0.1:8000/observe";
  const parsedTimeout = Number(
    process.env.BACKEND_OBSERVE_TIMEOUT_MS ?? process.env.BACKEND_RUN_TIMEOUT_MS ?? "180000",
  );
  const timeoutMs = Number.isFinite(parsedTimeout) && parsedTimeout > 0 ? parsedTimeout : 180000;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const payload = (await request.json()) as {
      topic?: string;
      bot_count?: number;
      results_per_bot?: number;
      months_back?: number;
      source_constraints?: string[];
      ai_model?: string;
    };

    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        topic: payload.topic,
        bot_count: payload.bot_count,
        results_per_bot: payload.results_per_bot,
        months_back: payload.months_back,
        source_constraints: payload.source_constraints,
        ai_model: payload.ai_model,
      }),
      cache: "no-store",
      signal: controller.signal,
    });
    clearTimeout(timeout);

    if (!response.ok) {
      const text = await response.text();
      return NextResponse.json(
        { ok: false, error: `backend ${response.status}: ${text}` },
        { status: response.status === 409 ? 409 : 502 },
      );
    }

    const data = await response.json();
    return NextResponse.json({ ok: true, result: data }, { status: 200 });
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
