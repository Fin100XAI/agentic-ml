// Librarian decision: how should a new file be used in a project that
// already holds data? Stack it, join it, route it to a model - or standalone.
import { GitMerge, Layers3, Library, Target } from "lucide-react";
import type { AssemblyProposal } from "../types";
import { Badge, Button, Card, CardBody } from "./ui";

const KIND_META = {
  stack: { icon: Layers3, label: "Add rows to an existing dataset", tone: "accent" as const },
  join: { icon: GitMerge, label: "Attach columns from an existing dataset", tone: "accent" as const },
  score_route: { icon: Target, label: "Score with a trained model", tone: "good" as const },
};

export function AssemblyModal({
  filename,
  proposals,
  busy,
  onChoose,
  onStandalone,
}: {
  filename: string;
  proposals: AssemblyProposal[];
  busy: boolean;
  onChoose: (p: AssemblyProposal) => void;
  onStandalone: () => void;
}) {
  return (
    <>
      <div className="fixed inset-0 z-40 bg-slate-900/25 backdrop-blur-sm" />
      <div className="fixed left-1/2 top-1/2 z-50 w-full max-w-xl -translate-x-1/2 -translate-y-1/2 px-4">
        <Card className="max-h-[85vh] overflow-y-auto bg-white/95">
          <CardBody>
            <div className="flex items-center gap-2">
              <Library className="h-5 w-5 text-accent" />
              <h3 className="text-sm font-semibold">How should this file be used?</h3>
            </div>
            <p className="mt-1 text-xs leading-relaxed text-ink-dim">
              {filename} looks related to data already in this project. Pick what to do -
              combining creates a new derived dataset; the originals stay untouched.
            </p>

            <div className="mt-3 space-y-2">
              {proposals.map((p, i) => {
                const meta = KIND_META[p.kind];
                return (
                  <button
                    key={i}
                    disabled={busy || p.kind === "score_route"}
                    onClick={() => p.kind !== "score_route" && onChoose(p)}
                    className={`w-full rounded-xl border px-4 py-3 text-left transition-all ${
                      p.kind === "score_route"
                        ? "cursor-default border-edge bg-panel-2 opacity-70"
                        : "border-accent/40 bg-accent-soft/25 hover:border-accent"
                    }`}
                  >
                    <span className="flex flex-wrap items-center gap-2">
                      <meta.icon className="h-4 w-4 text-accent" />
                      <span className="text-sm font-semibold">{meta.label}</span>
                      {p.target_filename && <Badge tone="neutral">{p.target_filename}</Badge>}
                      {p.kind === "score_route" && <Badge tone="good">coming with the model registry</Badge>}
                    </span>
                    <span className="mt-1 block text-[11px] leading-snug text-ink-dim">{p.note}</span>
                  </button>
                );
              })}
            </div>

            <div className="mt-4 flex justify-end">
              <Button variant="ghost" size="sm" onClick={onStandalone} disabled={busy}>
                Treat as a standalone dataset
              </Button>
            </div>
          </CardBody>
        </Card>
      </div>
    </>
  );
}
