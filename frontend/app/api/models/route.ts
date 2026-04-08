import { NextResponse } from "next/server";

export async function GET() {
  const endpoint = process.env.BACKEND_MODELS_ENDPOINT?.trim() || "http://127.0.0.1:8000/models";
  const parsedTimeout = Number(process.env.BACKEND_RUN_TIMEOUT_MS ?? "120000");
  const timeoutMs = Number.isFinite(parsedTimeout) && parsedTimeout > 0 ? parsedTimeout : 120000;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(endpoint, {
      method: "GET",
      cache: "no-store",
      signal: controller.signal,
    });
    clearTimeout(timeout);

    if (!response.ok) {
      const text = await response.text();
      return NextResponse.json(
        { ok: false, error: `backend ${response.status}: ${text}`, models: [] },
        { status: 502 },
      );
    }

    const payload = (await response.json()) as { models?: string[] };
    return NextResponse.json(
      { ok: true, models: Array.isArray(payload.models) ? payload.models : [] },
      { status: 200 },
    );
  } catch (error) {
    return NextResponse.json(
      {
        ok: false,
        error: `failed to call ${endpoint}: ${error instanceof Error ? error.message : "unknown error"}`,
        models: [],
      },
      { status: 502 },
    );
  } finally {
    clearTimeout(timeout);
  }
}
