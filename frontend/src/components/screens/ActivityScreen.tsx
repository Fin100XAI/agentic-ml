// Full unified activity log: every file event, agent call, approval,
// training job and export - filterable, with CSV download.
import { useCallback, useEffect, useRef, useState } from "react";
import { Download, RefreshCw, ScrollText } from "lucide-react";
import { api } from "../../api/client";
import type { ActivityEvent } from "../../types";
import { Badge, Button, Card, CardBody, CardHeader } from "../ui";

const EVENT_TYPES = [
  "all", "file_upload", "pii_review", "agent_call", "approval", "decline",
  "transform", "train", "score", "drift", "intake", "query_plan", "query_execute", "export", "error",
] as const;

const EVENT_TONE: Record<string, "neutral" | "accent" | "good" | "warn" | "bad"> = {
  approval: "good",
  train: "accent",
  error: "bad",
  decline: "warn",
  export: "accent",
  transform: "accent",
  pii_review: "warn",
  intake: "accent",
  query_plan: "accent",
  query_execute: "accent",
};

export function ActivityScreen({
  currentRunId,
  projectId,
}: {
  currentRunId?: string;
  projectId?: string;
}) {
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [eventType, setEventType] = useState<string>("all");
  const [runScope, setRunScope] = useState<"all" | "current">(currentRunId ? "current" : "all");
  const [loading, setLoading] = useState(false);

  const filters = {
    event_type: eventType === "all" ? undefined : eventType,
    run_id: runScope === "current" ? currentRunId : undefined,
    project_id: runScope === "current" ? undefined : projectId,
  };

  // Monotonic request id: quick filter toggles race, and the response for an
  // OLD filter must never display under the new one.
  const reqSeq = useRef(0);
  const refresh = useCallback(() => {
    const seq = ++reqSeq.current;
    setLoading(true);
    api
      .getActivity({ ...filters, limit: 300 })
      .then((r) => {
        if (reqSeq.current === seq) setEvents(r.events);
      })
      .catch(() => {
        if (reqSeq.current === seq) setEvents([]);
      })
      .finally(() => {
        if (reqSeq.current === seq) setLoading(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [eventType, runScope, currentRunId]);

  useEffect(refresh, [refresh]);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader
          title={
            <span className="flex items-center gap-2">
              <ScrollText className="h-4 w-4 text-accent" /> Activity log
            </span>
          }
          subtitle="Everything that happened, in order: uploads, agent calls (with mode and latency), your approvals, training jobs and exports."
          right={
            <div className="flex items-center gap-2">
              <Button variant="outline" size="sm" onClick={refresh}>
                <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} /> Refresh
              </Button>
              <a href={api.activityCsvUrl(filters)} download>
                <Button variant="outline" size="sm">
                  <Download className="h-3.5 w-3.5" /> CSV
                </Button>
              </a>
            </div>
          }
        />
        <CardBody>
          {/* Filters */}
          <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-2">
            <div className="flex flex-wrap items-center gap-1">
              {EVENT_TYPES.map((t) => (
                <button
                  key={t}
                  onClick={() => setEventType(t)}
                  className={`rounded-full border px-2.5 py-1 text-[11px] transition-all ${
                    eventType === t
                      ? "border-accent/40 bg-accent/10 font-medium text-accent"
                      : "border-edge bg-panel-2 text-ink-dim"
                  }`}
                >
                  {t.replace("_", " ")}
                </button>
              ))}
            </div>
            {currentRunId && (
              <label className="flex items-center gap-1.5 text-[11px] text-ink-dim">
                Scope
                <select
                  value={runScope}
                  onChange={(e) => setRunScope(e.target.value as "all" | "current")}
                  className="rounded-lg border border-edge bg-panel-2 px-2 py-1 text-[11px] text-ink"
                >
                  <option value="all">everything</option>
                  <option value="current">this analysis</option>
                </select>
              </label>
            )}
          </div>

          {/* Table */}
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-edge text-[10px] uppercase tracking-wider text-ink-dim">
                  <th className="py-2 pr-3">When</th>
                  <th className="py-2 pr-3">Who</th>
                  <th className="py-2 pr-3">Event</th>
                  <th className="py-2 pr-3">Mode</th>
                  <th className="py-2 pr-3">Latency</th>
                  <th className="py-2 pr-3">Tokens</th>
                  <th className="py-2">Detail</th>
                </tr>
              </thead>
              <tbody>
                {events.map((e) => (
                  <tr key={e.id} className="border-b border-edge/50 align-top">
                    <td className="whitespace-nowrap py-2 pr-3 tabular-nums text-ink-dim">
                      {e.ts.slice(0, 19).replace("T", " ")}
                    </td>
                    <td className="py-2 pr-3 font-medium">{e.actor}</td>
                    <td className="py-2 pr-3">
                      <Badge tone={EVENT_TONE[e.event_type] ?? "neutral"}>
                        {e.event_type.replace("_", " ")}
                      </Badge>
                    </td>
                    <td className="py-2 pr-3">
                      {e.mode && (
                        <Badge tone={e.mode === "llm" ? "accent" : "neutral"}>{e.mode}</Badge>
                      )}
                    </td>
                    <td className="whitespace-nowrap py-2 pr-3 tabular-nums text-ink-dim">
                      {e.latency_ms != null ? `${e.latency_ms} ms` : ""}
                    </td>
                    <td className="whitespace-nowrap py-2 pr-3 tabular-nums text-ink-dim">
                      {e.tokens_in != null ? `${e.tokens_in} in / ${e.tokens_out ?? 0} out` : ""}
                    </td>
                    <td className="max-w-md py-2">
                      {e.payload && (
                        <details>
                          <summary className="cursor-pointer truncate text-ink-dim">
                            {summarize(e.payload)}
                          </summary>
                          <pre className="mt-1 max-h-48 overflow-auto rounded-lg bg-panel-2 p-2 text-[10px] leading-snug">
                            {JSON.stringify(e.payload, null, 2)}
                          </pre>
                        </details>
                      )}
                    </td>
                  </tr>
                ))}
                {events.length === 0 && !loading && (
                  <tr>
                    <td colSpan={7} className="py-6 text-center text-ink-dim">
                      Nothing logged yet for this filter.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </CardBody>
      </Card>
    </div>
  );
}

function summarize(payload: Record<string, unknown>): string {
  const parts: string[] = [];
  for (const key of ["action", "gate", "format", "filename", "model", "stage", "error"]) {
    if (payload[key] != null) parts.push(`${key}: ${String(payload[key]).slice(0, 60)}`);
  }
  return parts.join(" - ") || JSON.stringify(payload).slice(0, 80);
}
