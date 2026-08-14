// Compact horizontal decision timeline - replaces the bulky wire diagram.
// Each decision is a small chip with a status dot; hover shows the detail.
import {
  BarChart3,
  Bot,
  Check,
  FileUp,
  GitCompare,
  Lightbulb,
  Play,
  Search,
  Settings2,
  X,
} from "lucide-react";
import type { DecisionNode } from "../types";
import { clsx } from "clsx";

const STAGE_ICON: Record<string, typeof Check> = {
  upload: FileUp,
  eda: Search,
  recommend: Bot,
  configure: Settings2,
  execute: Play,
  interpret: BarChart3,
  compare: GitCompare,
  insights: Lightbulb,
};

const STATUS_STYLE: Record<DecisionNode["status"], { dot: string; ring: string; label: string }> = {
  pending: { dot: "bg-ink-dim/50", ring: "border-edge", label: "pending" },
  proposed: { dot: "bg-warn animate-pulse", ring: "border-warn/50", label: "needs your approval" },
  approved: { dot: "bg-accent", ring: "border-accent/40", label: "approved by you" },
  done: { dot: "bg-good", ring: "border-good/40", label: "completed" },
  error: { dot: "bg-bad", ring: "border-bad/50", label: "failed" },
};

export function Timeline({ decisions }: { decisions: DecisionNode[] }) {
  if (decisions.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-y-2 overflow-x-auto px-4 py-2.5">
      {decisions.map((d, i) => {
        const Icon = STAGE_ICON[d.stage] ?? Check;
        const s = STATUS_STYLE[d.status];
        return (
          <div key={i} className="flex items-center">
            {i > 0 && <div className="mx-1.5 h-px w-4 shrink-0 bg-edge" />}
            <div
              className={clsx(
                "group relative flex shrink-0 cursor-default items-center gap-1.5 rounded-full border bg-panel px-2.5 py-1",
                s.ring,
              )}
            >
              <span className={clsx("h-1.5 w-1.5 rounded-full", s.dot)} />
              <Icon className="h-3 w-3 text-ink-dim" />
              <span className="text-[11px] font-medium">{d.title}</span>
              {d.status === "error" && <X className="h-3 w-3 text-bad" />}
              {/* hover detail */}
              <div className="pointer-events-none absolute left-1/2 top-full z-50 mt-2 w-64 -translate-x-1/2 rounded-lg border border-edge bg-panel-2 px-3 py-2 opacity-0 shadow-xl shadow-slate-900/10 transition-opacity duration-150 group-hover:opacity-100">
                <div className="mb-0.5 text-[11px] font-semibold">
                  {d.title} - <span className="font-normal text-ink-dim">{s.label}</span>
                </div>
                {d.detail && <div className="text-[11px] leading-snug text-ink-dim">{d.detail}</div>}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
