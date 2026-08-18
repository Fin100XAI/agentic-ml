// Run-vs-run comparison: side-by-side header, computed deltas, a plain
// "what changed" narrative, and a markdown export.
import { useEffect, useState } from "react";
import { Download, GitCompareArrows } from "lucide-react";
import { api } from "../api/client";
import type { RunDiffResult } from "../types";
import { Badge, Button, Card, CardBody } from "./ui";
import { genLabel } from "../lib/labels";

export function RunDiffModal({
  runA,
  runB,
  onClose,
}: {
  runA: string;
  runB: string;
  onClose: () => void;
}) {
  const [result, setResult] = useState<RunDiffResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.diffRuns(runA, runB).then(setResult).catch((e) => setError(String(e?.message ?? e)));
  }, [runA, runB]);

  const downloadMd = () => {
    if (!result) return;
    const blob = new Blob([result.markdown], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `run-comparison-${runA}-vs-${runB}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <>
      <div className="fixed inset-0 z-40 bg-slate-900/25 backdrop-blur-sm" onClick={onClose} />
      <div className="fixed left-1/2 top-1/2 z-50 w-full max-w-3xl -translate-x-1/2 -translate-y-1/2 px-4">
        <Card className="max-h-[85vh] overflow-y-auto bg-white/95">
          <CardBody>
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <GitCompareArrows className="h-5 w-5 text-accent" />
                <h3 className="text-sm font-semibold">What changed between these analyses</h3>
              </div>
              <div className="flex items-center gap-2">
                {result && (
                  <Button variant="outline" size="sm" onClick={downloadMd}>
                    <Download className="h-3.5 w-3.5" /> Markdown
                  </Button>
                )}
                <Button variant="ghost" size="sm" onClick={onClose}>Close</Button>
              </div>
            </div>

            {error && (
              <p className="mt-3 rounded-xl border border-warn/40 bg-warn/10 px-4 py-2.5 text-xs">
                {error}
              </p>
            )}
            {!result && !error && <p className="mt-4 text-sm text-ink-dim">Comparing…</p>}

            {result && (
              <div className="mt-4 space-y-4">
                {/* Side-by-side header */}
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  {(["a", "b"] as const).map((side) => {
                    const r = result.diff[side];
                    return (
                      <div key={side} className="rounded-2xl border border-edge bg-panel-2 px-4 py-3">
                        <div className="flex items-center justify-between">
                          <Badge tone={side === "a" ? "neutral" : "accent"}>
                            {side === "a" ? "Earlier (A)" : "Later (B)"}
                          </Badge>
                          {r.trust_tier && <Badge tone="neutral">{r.trust_tier} trust</Badge>}
                        </div>
                        <p className="mt-1.5 truncate text-xs font-semibold" title={r.filename}>{r.filename}</p>
                        <p className="truncate text-[11px] text-ink-dim" title={r.question}>{r.question || "(no question)"}</p>
                        <p className="mt-1 text-[10px] tabular-nums text-ink-dim">
                          {result.diff.data.rows[side === "a" ? 0 : 1].toLocaleString()} rows
                          · {r.created_at.slice(0, 10)}
                        </p>
                      </div>
                    );
                  })}
                </div>

                {/* Narrative */}
                <div className="rounded-xl border border-accent/30 bg-accent-soft/20 px-4 py-3">
                  <div className="mb-1 flex items-center gap-2">
                    <span className="text-xs font-semibold uppercase tracking-wider text-ink-dim">
                      What changed and what it means
                    </span>
                    <Badge tone={result.generated_by === "claude" ? "accent" : "neutral"}>
                      {genLabel(result.generated_by)}
                    </Badge>
                  </div>
                  <p className="text-sm leading-relaxed">{result.narrative}</p>
                </div>

                {/* Metric deltas */}
                {Object.keys(result.diff.metrics).length > 0 && (
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                    {Object.entries(result.diff.metrics).slice(0, 8).map(([k, m]) => (
                      <div key={k} className="rounded-2xl border border-edge bg-panel-2 px-3 py-2">
                        <div className="truncate text-[10px] uppercase tracking-wider text-ink-dim">{k}</div>
                        <div className="text-sm font-semibold tabular-nums">
                          {m.a} → {m.b}
                          <span className={`ml-1 text-[11px] ${m.delta > 0 ? "text-good" : m.delta < 0 ? "text-bad" : "text-ink-dim"}`}>
                            ({m.delta > 0 ? "+" : ""}{m.delta})
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* Distribution drift */}
                {result.diff.data.drift.length > 0 && (
                  <div className="overflow-x-auto rounded-xl border border-edge">
                    <table className="w-full text-left text-[11px]">
                      <thead>
                        <tr className="border-b border-edge bg-panel-2 text-[10px] uppercase tracking-wider text-ink-dim">
                          <th className="px-3 py-1.5">Shared column</th>
                          <th className="px-3 py-1.5">Distribution change (PSI)</th>
                          <th className="px-3 py-1.5">Read as</th>
                        </tr>
                      </thead>
                      <tbody>
                        {result.diff.data.drift.map((d) => (
                          <tr key={d.column} className="border-b border-edge/40">
                            <td className="px-3 py-1.5 font-medium">{d.column}</td>
                            <td className="px-3 py-1.5 tabular-nums">{d.psi}</td>
                            <td className="px-3 py-1.5">
                              <Badge tone={d.label === "stable" ? "good" : d.label === "moderate shift" ? "warn" : "bad"}>
                                {d.label}
                              </Badge>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {/* Driver changes */}
                {(result.diff.findings.drivers.entered.length > 0 ||
                  result.diff.findings.drivers.dropped.length > 0 ||
                  result.diff.findings.drivers.top_changed) && (
                  <div className="rounded-2xl border border-edge bg-panel-2 px-4 py-3 text-xs">
                    <span className="font-semibold">Driver changes: </span>
                    {result.diff.findings.drivers.top_changed && (
                      <span>top driver {result.diff.findings.drivers.a[0]} → {result.diff.findings.drivers.b[0]}. </span>
                    )}
                    {result.diff.findings.drivers.entered.length > 0 && (
                      <span>New: {result.diff.findings.drivers.entered.join(", ")}. </span>
                    )}
                    {result.diff.findings.drivers.dropped.length > 0 && (
                      <span>No longer prominent: {result.diff.findings.drivers.dropped.join(", ")}.</span>
                    )}
                  </div>
                )}
              </div>
            )}
          </CardBody>
        </Card>
      </div>
    </>
  );
}
