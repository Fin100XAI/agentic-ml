// Analytics path: the exploring agents run starter questions the moment the
// user arrives (deterministic plans through the same executor as Ask), and
// present the initial findings as chart cards. From here the user takes over
// with their own questions; the whole board downloads as a briefing file.
import { useEffect, useState } from "react";
import { ArrowLeft, Compass, Download, MessageSquareText, RefreshCw } from "lucide-react";
import { api } from "../../api/client";
import type { ExploreFinding, ExploreResponse } from "../../types";
import { genLabel } from "../../lib/labels";
import { saveBlob } from "../../lib/download";
import { QueryChart } from "../QueryChart";
import { Badge, Button, Card, CardBody, CardHeader, Spinner } from "../ui";

// Boards survive leaving the screen (e.g. into Ask and back) so returning is
// instant and the exploration is not re-run - and not re-logged - each visit.
// The in-flight promise doubles as a StrictMode/double-mount guard: one
// exploration per dataset, ever, unless it failed.
const boardCache = new Map<string, ExploreResponse>();
const inFlight = new Map<string, Promise<ExploreResponse>>();

export function AnalyticsScreen({
  datasetId,
  filename,
  onAsk,
  onBack,
}: {
  datasetId: string;
  filename: string;
  onAsk: (question?: string) => void;
  onBack: () => void;
}) {
  const cached = boardCache.get(datasetId) ?? null;
  const [resp, setResp] = useState<ExploreResponse | null>(cached);
  const [busy, setBusy] = useState(cached === null);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  const explore = async () => {
    setBusy(true);
    setError(null);
    try {
      let p = inFlight.get(datasetId);
      if (!p) {
        p = api.explore(datasetId);
        inFlight.set(datasetId, p);
      }
      const r = await p;
      boardCache.set(datasetId, r);
      setResp(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      inFlight.delete(datasetId);
      setBusy(false);
    }
  };

  useEffect(() => {
    if (!boardCache.has(datasetId)) void explore();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasetId]);

  const downloadBoard = async () => {
    if (!resp) return;
    setExporting(true);
    try {
      const blob = await api.exploreExportMd(
        datasetId,
        resp.findings.map((f) => ({
          question: f.question,
          headline: f.headline,
          sentences: f.sentences,
          table: f.result.table.slice(0, 50),
        })),
      );
      saveBlob(blob, "initial-findings.md");
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-lg font-bold">
          <Compass className="h-5 w-5 text-accent" /> Initial findings
        </h2>
        <div className="flex items-center gap-2">
          {resp && resp.findings.length > 0 && (
            <Button variant="outline" size="sm" onClick={downloadBoard} disabled={exporting}>
              {exporting ? <Spinner /> : <Download className="h-3.5 w-3.5" />} Download briefing
            </Button>
          )}
          <Button variant="ghost" size="sm" onClick={onBack}>
            <ArrowLeft className="h-3.5 w-3.5" /> Back
          </Button>
        </div>
      </div>

      <p className="text-xs text-ink-dim">
        The exploring agents scanned <span className="font-semibold text-ink">{filename}</span>,
        asked the first questions on your behalf, and computed every answer directly from the
        data. Take over below with your own question whenever you are ready.
      </p>

      {busy && (
        <Card>
          <CardBody className="flex items-center gap-3 py-8">
            <Spinner />
            <p className="text-sm text-ink-dim">
              Exploring the data - running starter questions through the query engine...
            </p>
          </CardBody>
        </Card>
      )}

      {error && (
        <Card className="border-bad/40">
          <CardBody className="flex items-center justify-between gap-3">
            <p className="text-xs text-bad">{error}</p>
            <Button variant="outline" size="sm" onClick={explore}>
              <RefreshCw className="h-3.5 w-3.5" /> Try again
            </Button>
          </CardBody>
        </Card>
      )}

      {!busy && resp && resp.findings.length === 0 && (
        <Card>
          <CardBody>
            <p className="text-sm text-ink-dim">
              The agents could not form starter questions from this file's columns - ask your
              own question instead.
            </p>
          </CardBody>
        </Card>
      )}

      {!busy &&
        resp?.findings.map((f, i) => (
          <FindingCard key={i} finding={f} generatedBy={resp.generated_by} onAsk={onAsk} />
        ))}

      {!busy && resp && (
        <Card className="border-accent/30">
          <CardBody className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm">
              Your turn - ask anything about this data in plain language.
            </p>
            <Button onClick={() => onAsk()}>
              <MessageSquareText className="h-3.5 w-3.5" /> Ask your own question
            </Button>
          </CardBody>
        </Card>
      )}
    </div>
  );
}

function FindingCard({
  finding,
  generatedBy,
  onAsk,
}: {
  finding: ExploreFinding;
  generatedBy: string;
  onAsk: (question?: string) => void;
}) {
  const [showTable, setShowTable] = useState(false);
  const f = finding;
  return (
    <Card>
      <CardHeader
        title={f.question}
        right={<Badge tone={generatedBy === "claude" ? "accent" : "neutral"}>{genLabel(generatedBy)}</Badge>}
      />
      <CardBody className="space-y-3">
        <p className="text-sm font-medium leading-relaxed">{f.headline}</p>

        {f.caveats.length > 0 && (
          <div className="space-y-1 rounded-lg border border-warn/30 bg-warn/5 px-3 py-2">
            {f.caveats.map((c, i) => (
              <p key={i} className="text-[11px] leading-relaxed text-warn">{c}</p>
            ))}
          </div>
        )}

        <QueryChart spec={f.chart} result={f.result} />

        <div className="flex flex-wrap items-center justify-between gap-2">
          <button
            onClick={() => setShowTable((s) => !s)}
            className="text-[11px] text-ink-dim underline-offset-2 hover:text-ink hover:underline"
          >
            {showTable ? "Hide numbers" : "Show the numbers"}
          </button>
          <button
            onClick={() => onAsk(f.question)}
            className="text-[11px] text-accent underline-offset-2 hover:underline"
          >
            Refine this question
          </button>
        </div>

        {showTable && (
          <div className="overflow-x-auto rounded-lg border border-edge">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-edge bg-panel-2 text-[10px] uppercase tracking-wider text-ink-dim">
                  {f.result.columns.map((c) => (
                    <th key={c} className="px-3 py-2">{c}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {f.result.table.slice(0, 50).map((r, i) => (
                  <tr key={i} className="border-b border-edge/50">
                    {f.result.columns.map((c) => (
                      <td key={c} className="px-3 py-1.5 tabular-nums">
                        {r[c] == null ? <span className="text-ink-dim">-</span> : String(r[c])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <p className="text-[10px] leading-relaxed text-ink-dim">
          {f.sentences.join(" ")}{" "}
          {f.result.row_counts.length > 0 &&
            `(${f.result.row_counts.map((rc) => `${rc.step}: ${rc.rows.toLocaleString()}`).join(" → ")})`}
        </p>
      </CardBody>
    </Card>
  );
}
