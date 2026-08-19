// Data-fix review: shown after profiling when the health check found issues
// the engine can repair. Approving creates a fixed copy; the original stays.
import { useState } from "react";
import { Wrench } from "lucide-react";
import type { RemediationProposal } from "../types";
import { Badge, Button, Card, CardBody } from "./ui";
import { genLabel } from "../lib/labels";

export function RemediationModal({
  proposals,
  generatedBy,
  busy,
  onApprove,
  onSkip,
}: {
  proposals: RemediationProposal[];
  generatedBy?: string;
  busy: boolean;
  onApprove: (acceptedIds: string[]) => void;
  onSkip: () => void;
}) {
  const [ticked, setTicked] = useState<Set<string>>(
    () => new Set(proposals.filter((p) => p.recommended).map((p) => p.id)),
  );
  const toggle = (id: string) =>
    setTicked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <>
      <div className="fixed inset-0 z-40 bg-slate-900/25 backdrop-blur-sm" />
      <div className="fixed left-1/2 top-1/2 z-50 w-full max-w-2xl -translate-x-1/2 -translate-y-1/2 px-4">
        <Card className="max-h-[85vh] overflow-y-auto bg-panel/95">
          <CardBody>
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Wrench className="h-5 w-5 text-accent" />
                <h3 className="text-sm font-semibold">Suggested data fixes</h3>
              </div>
              <Badge tone={generatedBy === "claude" ? "accent" : "neutral"}>
                {genLabel(generatedBy)}
              </Badge>
            </div>
            <p className="mt-1 text-xs leading-relaxed text-ink-dim">
              The health check found repairable issues. Tick the fixes to apply - they produce a
              fixed working copy with full lineage; the uploaded file is never changed. You can
              also skip and analyze the data exactly as uploaded.
            </p>

            <div className="mt-3 space-y-2">
              {proposals.map((p) => (
                <label
                  key={p.id}
                  className={`flex cursor-pointer items-start gap-2.5 rounded-xl border px-4 py-2.5 transition-all ${
                    ticked.has(p.id)
                      ? "border-accent/50 bg-accent-soft/30"
                      : "border-edge bg-panel-2 hover:border-accent/30"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={ticked.has(p.id)}
                    onChange={() => toggle(p.id)}
                    className="mt-0.5 h-3.5 w-3.5 accent-accent"
                  />
                  <span className="min-w-0">
                    <span className="flex flex-wrap items-center gap-1.5">
                      <span className="text-xs font-semibold">{p.description}</span>
                      <span className="text-[10px] tabular-nums text-ink-dim">
                        {p.affected_rows.toLocaleString()} value{p.affected_rows !== 1 ? "s" : ""} affected
                      </span>
                    </span>
                    <span className="mt-0.5 block text-[11px] leading-snug text-ink-dim">
                      {p.reasoning}
                    </span>
                  </span>
                </label>
              ))}
            </div>

            <div className="mt-4 flex items-center justify-between gap-3">
              <Button variant="ghost" size="sm" onClick={onSkip} disabled={busy}>
                Skip - use data as uploaded
              </Button>
              <Button onClick={() => onApprove([...ticked])} disabled={busy}>
                {busy ? "Applying…" : `Apply ${ticked.size} fix${ticked.size !== 1 ? "es" : ""}`}
              </Button>
            </div>
          </CardBody>
        </Card>
      </div>
    </>
  );
}
