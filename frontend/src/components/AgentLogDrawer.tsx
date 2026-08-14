// Slide-out panel showing every agent decision: what it did, why, how long.
import { Bot, Clock, X } from "lucide-react";
import type { AgentLogEntry } from "../types";
import { Badge } from "./ui";

const AGENT_COLOR: Record<string, string> = {
  Profiler: "bg-slate-500",
  "EDA agent": "bg-indigo-500",
  "Recommendation agent": "bg-violet-500",
  "Settings suggester": "bg-cyan-600",
  "Model runner": "bg-emerald-600",
  "Interpretation agent": "bg-amber-600",
  "Insight engine": "bg-rose-500",
  "Brief agent": "bg-fuchsia-600",
};

export function AgentLogDrawer({
  entries,
  open,
  onClose,
}: {
  entries: AgentLogEntry[];
  open: boolean;
  onClose: () => void;
}) {
  if (!open) return null;
  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-40 bg-slate-900/20 backdrop-blur-sm" onClick={onClose} />
      {/* Drawer */}
      <aside className="fixed right-0 top-0 z-50 flex h-full w-full max-w-md flex-col border-l border-edge bg-white/85 shadow-2xl shadow-slate-900/20 backdrop-blur-2xl">
        <div className="flex items-center justify-between border-b border-edge px-5 py-4">
          <div className="flex items-center gap-2">
            <Bot className="h-4 w-4 text-accent" />
            <h3 className="text-sm font-semibold">Agent activity</h3>
            <Badge tone="neutral">{entries.length} steps</Badge>
          </div>
          <button onClick={onClose} className="rounded-lg p-1.5 text-ink-dim transition-colors hover:bg-slate-500/10 hover:text-ink">
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {entries.length === 0 ? (
            <p className="text-sm text-ink-dim">
              Nothing yet — agent decisions will appear here as the analysis progresses.
            </p>
          ) : (
            <ol className="relative space-y-5 before:absolute before:left-[7px] before:top-2 before:h-[calc(100%-16px)] before:w-px before:bg-edge">
              {entries.map((e, i) => (
                <li key={i} className="relative pl-6">
                  <span
                    className={`absolute left-0 top-1.5 h-[15px] w-[15px] rounded-full border-2 border-white ${AGENT_COLOR[e.agent] ?? "bg-slate-400"}`}
                  />
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <span className="text-xs font-semibold">{e.agent}</span>
                    <Badge tone={e.generated_by === "claude" ? "accent" : "neutral"}>
                      {e.generated_by}
                    </Badge>
                    <span className="inline-flex items-center gap-1 text-[10px] text-ink-dim">
                      <Clock className="h-3 w-3" />
                      {e.duration_ms >= 1000 ? `${(e.duration_ms / 1000).toFixed(1)}s` : `${e.duration_ms}ms`}
                    </span>
                  </div>
                  <div className="mt-0.5 text-xs font-medium text-ink">{e.action}</div>
                  {e.decision && (
                    <p className="mt-1 break-words text-[11px] leading-relaxed text-ink-dim">
                      {e.decision}
                    </p>
                  )}
                  {e.reasoning && (
                    <p className="mt-1 break-words rounded-lg border border-edge bg-panel-2 px-2.5 py-1.5 text-[11px] italic leading-relaxed text-ink-dim">
                      {e.reasoning}
                    </p>
                  )}
                </li>
              ))}
            </ol>
          )}
        </div>

        <div className="border-t border-edge px-5 py-3 text-[10px] leading-snug text-ink-dim">
          "deterministic" = computed directly from your data (no AI). "claude" = reasoned by the
          AI model. "heuristic" = rule-based fallback when no API key is set.
        </div>
      </aside>
    </>
  );
}
