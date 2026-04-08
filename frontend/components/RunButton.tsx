"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export function RunButton() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string>("");
  const [isError, setIsError] = useState(false);

  async function trigger() {
    setLoading(true);
    setMessage("");
    setIsError(false);

    try {
      const response = await fetch("/api/run", { method: "POST" });
      const payload = (await response.json()) as {
        ok?: boolean;
        error?: string;
        result?: { run_id?: string };
      };
      if (!response.ok || !payload.ok) {
        setIsError(true);
        setMessage(payload.error ?? "run failed");
      } else {
        setMessage(payload.result?.run_id ? `运行完成：${payload.result.run_id}` : "运行完成");
        router.refresh();
      }
    } catch (error) {
      setIsError(true);
      setMessage(error instanceof Error ? error.message : "unknown error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-1">
      <button
        className="rounded-lg border border-border px-4 py-2 text-sm hover:border-secondaryText disabled:opacity-50"
        disabled={loading}
        onClick={trigger}
        type="button"
      >
        {loading ? "运行中..." : "手动触发 Run"}
      </button>
      {message ? (
        <p className={`text-xs ${isError ? "text-riskHigh" : "text-secondaryText"}`}>{message}</p>
      ) : null}
    </div>
  );
}
