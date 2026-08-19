// Drift check: is new data still like the data this model version learned on?
// Plain verdict up front; the per-column numbers live behind a toggle.
import { useRef, useState } from "react";
import { Activity, ChevronDown, ChevronRight, RefreshCw, Upload } from "lucide-react";
import { api } from "../api/client";
import type { DriftResult, RegistryEntry } from "../types";
import { Badge, Button, Card, CardBody } from "./ui";
import { genLabel } from "../lib/labels";

const VERDICT = {
  stable: { tone: "good" as const, title: "Stable - familiar ground" },
  drifting: { tone: "warn" as const, title: "Drifting - the data has moved" },
  degraded: { tone: "bad" as const, title: "Degraded - accuracy has dropped" },
};

export function DriftModal({
  entry,
  onClose,
  onRetrain,
}: {
  entry: RegistryEntry;
  onClose: () => void;
  onRetrain?: () => void;
}) {
  const [result, setResult] = useState<DriftResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showNumbers, setShowNumbers] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const check = async (file: File) => {
    setBusy(true);
    setError(null);
    try {
      setResult(await api.driftCheck(entry.model_id, entry.version, file));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div className="fixed inset-0 z-40 bg-slate-900/25 backdrop-blur-sm" onClick={onClose} />
      <div className="fixed left-1/2 top-1/2 z-50 w-full max-w-2xl -translate-x-1/2 -translate-y-1/2 px-4">
        <Card className="max-h-[85vh] overflow-y-auto bg-panel/95">
          <CardBody>
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Activity className="h-5 w-5 text-accent" />
                <h3 className="text-sm font-semibold">
                  Drift check - {entry.model_name} v{entry.version}
                </h3>
              </div>
              <Button variant="ghost" size="sm" onClick={onClose}>Close</Button>
            </div>
            <p className="mt-1 text-xs leading-relaxed text-ink-dim">
              Upload recent data to see whether it still looks like what this model was trained
              on. Include the outcome column if you have it - that also checks whether accuracy
              is holding up.
            </p>

            {!result && (
              <div
                className="mt-4 flex cursor-pointer flex-col items-center rounded-2xl border-2 border-dashed border-edge px-6 py-8 transition-colors hover:border-accent/50"
                onClick={() => inputRef.current?.click()}
              >
                <input
                  ref={inputRef}
                  type="file"
                  accept=".csv,.xlsx,.xls"
                  className="hidden"
                  onChange={(e) => e.target.files?.[0] && check(e.target.files[0])}
                />
                <Upload className="mb-2 h-8 w-8 text-ink-dim" />
                <p className="text-sm font-medium">{busy ? "Checking…" : "Drop or pick the recent data file"}</p>
              </div>
            )}

            {error && (
              <p className="mt-3 rounded-xl border border-bad/40 bg-bad/5 px-4 py-2.5 text-xs">{error}</p>
            )}

            {result && (
              <div className="mt-4 space-y-4">
                {/* Verdict banner */}
                <div className={`rounded-xl border px-4 py-3 ${
                  result.verdict === "stable" ? "border-good/40 bg-good/5"
                  : result.verdict === "drifting" ? "border-warn/40 bg-warn/10"
                  : "border-bad/40 bg-bad/5"
                }`}>
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={VERDICT[result.verdict].tone}>{result.verdict}</Badge>
                    <span className="text-sm font-semibold">{VERDICT[result.verdict].title}</span>
                    <Badge tone={result.generated_by === "claude" ? "accent" : "neutral"}>
                      {genLabel(result.generated_by)}
                    </Badge>
                  </div>
                  <p className="mt-1.5 text-xs leading-relaxed">{result.narrative}</p>
                </div>

                {/* Performance decay */}
                {result.decay && (
                  <div className="flex flex-wrap gap-3">
                    <div className="rounded-2xl border border-edge bg-panel-2 px-4 py-2">
                      <div className="text-[10px] uppercase tracking-wider text-ink-dim">
                        {result.decay.metric} at training
                      </div>
                      <div className="text-lg font-semibold tabular-nums">{result.decay.train}</div>
                    </div>
                    <div className="rounded-2xl border border-edge bg-panel-2 px-4 py-2">
                      <div className="text-[10px] uppercase tracking-wider text-ink-dim">
                        {result.decay.metric} on this data
                      </div>
                      <div className="text-lg font-semibold tabular-nums">
                        {result.decay.new}
                        <span className={`ml-1.5 text-xs ${result.decay.degraded ? "text-bad" : "text-ink-dim"}`}>
                          ({result.decay.relative_change_pct > 0 ? "-" : "+"}
                          {Math.abs(result.decay.relative_change_pct)}%)
                        </span>
                      </div>
                    </div>
                  </div>
                )}

                {/* Schema issues */}
                {(result.schema.missing.length > 0 || result.schema.renamed.length > 0) && (
                  <div className="flex flex-wrap gap-2 text-xs">
                    {result.schema.missing.map((m) => (
                      <Badge key={m} tone="bad">missing: {m}</Badge>
                    ))}
                    {result.schema.renamed.map((r) => (
                      <Badge key={r.from} tone="neutral">{r.from} → {r.to}</Badge>
                    ))}
                  </div>
                )}

                {/* The numbers, behind a toggle */}
                <button
                  onClick={() => setShowNumbers(!showNumbers)}
                  className="flex items-center gap-1 text-xs font-medium text-accent hover:underline"
                >
                  {showNumbers ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                  {showNumbers ? "Hide" : "Show"} the per-column numbers
                </button>
                {showNumbers && (
                  <div className="overflow-x-auto rounded-xl border border-edge">
                    <table className="w-full text-left text-[11px]">
                      <thead>
                        <tr className="border-b border-edge bg-panel-2 text-[10px] uppercase tracking-wider text-ink-dim">
                          <th className="px-3 py-1.5">Column</th>
                          <th className="px-3 py-1.5">Test</th>
                          <th className="px-3 py-1.5">Score</th>
                          <th className="px-3 py-1.5">Read as</th>
                        </tr>
                      </thead>
                      <tbody>
                        {result.columns.map((c) => (
                          <tr key={c.column} className="border-b border-edge/40">
                            <td className="px-3 py-1.5 font-medium">{c.column}</td>
                            <td className="px-3 py-1.5 text-ink-dim">
                              {c.kind === "numeric" ? "PSI" : "chi-square p"}
                            </td>
                            <td className="px-3 py-1.5 tabular-nums">{c.score}</td>
                            <td className="px-3 py-1.5">
                              <Badge tone={c.label === "stable" ? "good" : c.label === "moderate shift" ? "warn" : "bad"}>
                                {c.label}
                              </Badge>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                <div className="flex justify-between gap-2">
                  <Button variant="outline" size="sm" onClick={() => setResult(null)}>
                    Check another file
                  </Button>
                  {result.verdict !== "stable" && onRetrain && (
                    <Button size="sm" onClick={() => { onClose(); onRetrain(); }}>
                      <RefreshCw className="h-3.5 w-3.5" /> Retrain this model
                    </Button>
                  )}
                </div>
              </div>
            )}
          </CardBody>
        </Card>
      </div>
    </>
  );
}
