// The workspace library: every dataset in the project and every analysis
// run against it, on ONE screen. Before this, a file was only reachable by
// re-uploading it and a past run only from the session list that emptied on
// reload - so work done last month was effectively gone.
//
// A prepared table registered from the Prep Studio lands here too, as an
// ordinary dataset, which is what makes the two pipelines one product.
import { useCallback, useEffect, useState } from "react";
import {
  ArrowRight,
  Compass,
  Database,
  FileText,
  MessageSquareText,
  RefreshCw,
  Wand2,
} from "lucide-react";
import { api } from "../../api/client";
import type { RegistryEntry } from "../../types";
import { IndicatorsPanel } from "../IndicatorsPanel";
import { ModelsPanel } from "../ModelsPanel";
import { Badge, Button, Card, CardBody, Spinner } from "../ui";

interface DatasetRow {
  id: string;
  filename: string;
  n_rows: number;
  n_cols?: number;
  pii_status?: string;
}

interface RunRow {
  id: string;
  filename: string;
  question: string | null;
  stage: string;
  created_at?: string | number;
}

// Runs that reached a brief are readable; the rest are still in progress.
const FINISHED = new Set(["interpret", "compare"]);

function when(v: string | number | undefined): string {
  if (v === undefined || v === null) return "";
  const d = new Date(typeof v === "number" ? v * 1000 : v);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export function LibraryScreen({
  projectId,
  projectName,
  onExplore,
  onAsk,
  onOpenRun,
  onUpload,
  onPrep,
  onRetrain,
}: {
  projectId: string;
  projectName?: string;
  onExplore: (datasetId: string, filename: string) => void;
  onAsk: (datasetId: string, filename: string) => void;
  onOpenRun: (runId: string) => void;
  onUpload: () => void;
  onPrep: () => void;
  onRetrain?: (entry: RegistryEntry, datasetId: string) => void;
}) {
  const [datasets, setDatasets] = useState<DatasetRow[]>([]);
  const [runs, setRuns] = useState<RunRow[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    api.getProjectDetail(projectId)
      .then((d) => {
        setDatasets((d.datasets as DatasetRow[]) || []);
        setRuns((d.runs as RunRow[]) || []);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [projectId]);

  useEffect(load, [load]);

  // Analyses grouped under the file they were run against, so a dataset
  // card can say what has already been asked of it.
  const runsByFile = runs.reduce<Record<string, RunRow[]>>((acc, r) => {
    (acc[r.filename] ||= []).push(r);
    return acc;
  }, {});

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-xl font-semibold">
            Library{projectName ? ` · ${projectName}` : ""}
          </h2>
          <p className="mt-1 text-xs text-ink-dim">
            Every file in this project and every analysis run against it. Nothing here
            needs re-uploading - pick up where you left off.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" size="sm" onClick={load} disabled={loading}>
            {loading ? <Spinner /> : <RefreshCw className="h-3.5 w-3.5" />} Refresh
          </Button>
          <Button variant="outline" size="sm" onClick={onPrep}>
            <Wand2 className="h-3.5 w-3.5" /> Prepare a messy file
          </Button>
          <Button size="sm" onClick={onUpload}>
            Upload a file <ArrowRight className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {/* ---------------------------------------------------------- data */}
      <section>
        <h3 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-accent">
          <Database className="h-3.5 w-3.5" /> Datasets
          <span className="font-normal text-ink-dim">({datasets.length})</span>
        </h3>
        {datasets.length === 0 ? (
          <Card className="mt-3">
            <CardBody>
              <p className="text-sm text-ink-dim">
                No files yet. Upload one, or run a messy workbook through the Prep Studio
                first - a prepared table arrives here as an ordinary dataset.
              </p>
            </CardBody>
          </Card>
        ) : (
          <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {datasets.map((ds) => {
              const gated = ds.pii_status === "pending";
              const mine = runsByFile[ds.filename] || [];
              return (
                <Card key={ds.id} className="tile">
                  <CardBody className="flex h-full flex-col">
                    <p className="truncate text-sm font-semibold" title={ds.filename}>
                      {ds.filename}
                    </p>
                    <p className="mt-0.5 text-[11px] tabular-nums text-ink-dim">
                      {ds.n_rows.toLocaleString()} rows
                      {ds.n_cols ? ` · ${ds.n_cols} columns` : ""}
                    </p>
                    {gated && (
                      <p className="mt-2">
                        <Badge tone="warn">privacy review pending</Badge>
                      </p>
                    )}
                    {mine.length > 0 && (
                      <p className="mt-2 text-[11px] text-ink-dim">
                        {mine.length} {mine.length === 1 ? "analysis" : "analyses"} run
                      </p>
                    )}
                    <div className="mt-3 flex gap-1.5 pt-1">
                      <Button
                        size="sm"
                        variant="outline"
                        className="flex-1"
                        disabled={gated}
                        onClick={() => onExplore(ds.id, ds.filename)}
                        title="Open the findings board for this file"
                      >
                        <Compass className="h-3.5 w-3.5" /> Explore
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        className="flex-1"
                        disabled={gated}
                        onClick={() => onAsk(ds.id, ds.filename)}
                        title="Ask this file a question"
                      >
                        <MessageSquareText className="h-3.5 w-3.5" /> Ask
                      </Button>
                    </div>
                  </CardBody>
                </Card>
              );
            })}
          </div>
        )}
      </section>

      {/* ------------------------------------------------------- analyses */}
      <section>
        <h3 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-accent">
          <FileText className="h-3.5 w-3.5" /> Analyses and reports
          <span className="font-normal text-ink-dim">({runs.length})</span>
        </h3>
        {runs.length === 0 ? (
          <Card className="mt-3">
            <CardBody>
              <p className="text-sm text-ink-dim">
                No analyses yet. Explore a dataset above, or train a model - finished runs
                and their decision briefs collect here.
              </p>
            </CardBody>
          </Card>
        ) : (
          <Card className="mt-3">
            <CardBody className="divide-y divide-edge/60 p-0">
              {runs.map((r) => {
                const done = FINISHED.has(r.stage);
                return (
                  <button
                    key={r.id}
                    onClick={() => onOpenRun(r.id)}
                    className="group flex w-full items-center justify-between gap-3 px-5 py-3 text-left transition-colors hover:bg-panel-2/60"
                  >
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium">
                        {r.question || "no question set"}
                      </div>
                      <div className="truncate text-[11px] text-ink-dim">
                        {r.filename}
                        {when(r.created_at) ? ` · ${when(r.created_at)}` : ""}
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-3">
                      <Badge tone={done ? "good" : "warn"}>
                        {done ? "report ready" : r.stage}
                      </Badge>
                      <ArrowRight className="h-4 w-4 text-ink-dim transition-transform duration-200 group-hover:translate-x-0.5" />
                    </div>
                  </button>
                );
              })}
            </CardBody>
          </Card>
        )}
      </section>

      {/* Saved indicators and trained models already know how to render
          themselves; the library is simply where they belong. */}
      <IndicatorsPanel projectId={projectId} />
      <ModelsPanel projectId={projectId} onRetrain={onRetrain} />
    </div>
  );
}
