// Small provenance trail: original -> transforms -> the data a run trained on.
// Hashes live in tooltips; the original is never modified.
import { useEffect, useState } from "react";
import { ChevronRight, Database } from "lucide-react";
import { api } from "../api/client";
import type { ArtifactInfo } from "../types";

const STEP_LABEL: Record<string, string> = {
  upload: "original",
  join: "sheets joined",
  stack: "files stacked",
  pii_mask: "PII masked",
  remediation: "data fixes",
  feature_eng: "features added",
};

export function LineageBreadcrumb({ artifactId }: { artifactId: string }) {
  const [chain, setChain] = useState<ArtifactInfo[] | null>(null);

  useEffect(() => {
    api.getLineage(artifactId).then((r) => setChain(r.lineage)).catch(() => setChain(null));
  }, [artifactId]);

  if (!chain || chain.length === 0) return null;
  // lineage arrives child-first; render oldest -> newest
  const steps = [...chain].reverse();

  return (
    <div className="flex flex-wrap items-center gap-1 text-[11px] text-ink-dim">
      <Database className="h-3 w-3" />
      {steps.map((a, i) => (
        <span key={a.id} className="flex items-center gap-1">
          {i > 0 && <ChevronRight className="h-3 w-3 opacity-50" />}
          <span
            className="cursor-help rounded-full border border-edge bg-white/40 px-2 py-0.5"
            title={`${a.kind} artifact ${a.id}\nsha256: ${a.sha256}\n${a.created_at.slice(0, 19)}`}
          >
            {a.kind === "original"
              ? "original"
              : STEP_LABEL[a.transform_type] ?? a.transform_type.replace("_", " ")}
          </span>
        </span>
      ))}
    </div>
  );
}
