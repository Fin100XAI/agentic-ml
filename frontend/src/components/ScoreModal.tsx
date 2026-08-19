// Score new data with a registered model version: upload a file, get
// predictions with the training-time preprocessing rebuilt from lineage.
import { useRef, useState } from "react";
import { Download, Target, Upload } from "lucide-react";
import { api } from "../api/client";
import type { RegistryEntry, ScoreResult } from "../types";
import { ClassDistributionChart, ResidualHistChart } from "./charts";
import { Badge, Button, Card, CardBody } from "./ui";
import { genLabel } from "../lib/labels";

export function ScoreModal({
  entry,
  onClose,
}: {
  entry: RegistryEntry;
  onClose: () => void;
}) {
  const [result, setResult] = useState<ScoreResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const score = async (file: File) => {
    setBusy(true);
    setError(null);
    try {
      setResult(await api.scoreModel(entry.model_id, entry.version, file));
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
                <Target className="h-5 w-5 text-accent" />
                <h3 className="text-sm font-semibold">
                  Score new data - {entry.model_name} v{entry.version}
                </h3>
              </div>
              <Button variant="ghost" size="sm" onClick={onClose}>Close</Button>
            </div>
            <p className="mt-1 text-xs leading-relaxed text-ink-dim">
              Upload a file with the same columns the model was trained on
              {entry.purpose_statement ? ` ("${entry.purpose_statement}")` : ""}. The exact
              training-time preparation (privacy masking, data fixes, engineered features)
              is applied automatically before predicting.
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
                  onChange={(e) => e.target.files?.[0] && score(e.target.files[0])}
                />
                <Upload className="mb-2 h-8 w-8 text-ink-dim" />
                <p className="text-sm font-medium">
                  {busy ? "Scoring…" : "Drop or pick the file to score"}
                </p>
              </div>
            )}

            {error && (
              <p className="mt-3 rounded-xl border border-bad/40 bg-bad/5 px-4 py-2.5 text-xs leading-relaxed">
                {error}
              </p>
            )}

            {result && (
              <div className="mt-4 space-y-4">
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <Badge tone="good">{result.n.toLocaleString()} rows scored</Badge>
                  {result.reconciliation.renamed.length > 0 && (
                    <Badge tone="accent">
                      {result.reconciliation.renamed.length} column
                      {result.reconciliation.renamed.length !== 1 ? "s" : ""} auto-matched
                    </Badge>
                  )}
                  {result.reconciliation.extra.length > 0 && (
                    <Badge tone="neutral">{result.reconciliation.extra.length} extra ignored</Badge>
                  )}
                  <Badge tone={result.generated_by === "claude" ? "accent" : "neutral"}>
                    {genLabel(result.generated_by)}
                  </Badge>
                </div>

                <p className="text-sm leading-relaxed">{result.summary}</p>
                {result.threshold_note && (
                  <p className="text-[11px] text-ink-dim">{result.threshold_note}</p>
                )}
                {result.replay_warning && (
                  <p className="rounded-lg border border-warn/30 bg-warn/10 px-3 py-2 text-[11px] leading-relaxed text-warn">
                    {result.replay_warning}
                  </p>
                )}

                <div className="rounded-2xl border border-edge bg-panel p-4">
                  <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-dim">
                    How the predictions distribute
                  </h4>
                  {result.distribution.kind === "classes" ? (
                    <ClassDistributionChart data={result.distribution.data} />
                  ) : (
                    <ResidualHistChart data={result.distribution.data} />
                  )}
                </div>

                <div className="overflow-x-auto rounded-xl border border-edge">
                  <table className="w-full text-left text-[11px]">
                    <thead>
                      <tr className="border-b border-edge bg-panel-2 text-[10px] uppercase tracking-wider text-ink-dim">
                        {Object.keys(result.preview[0] ?? {}).map((c) => (
                          <th key={c} className="px-2 py-1.5">{c}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {result.preview.slice(0, 10).map((row, i) => (
                        <tr key={i} className="border-b border-edge/40">
                          {Object.values(row).map((v, j) => (
                            <td key={j} className="whitespace-nowrap px-2 py-1 tabular-nums">
                              {v == null ? "" : String(v)}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <div className="flex justify-between gap-2">
                  <Button variant="outline" size="sm" onClick={() => setResult(null)}>
                    Score another file
                  </Button>
                  <a href={api.artifactDownloadUrl(result.artifact_id)} download>
                    <Button size="sm">
                      <Download className="h-3.5 w-3.5" /> Download all {result.n.toLocaleString()} predictions (CSV)
                    </Button>
                  </a>
                </div>
              </div>
            )}
          </CardBody>
        </Card>
      </div>
    </>
  );
}
