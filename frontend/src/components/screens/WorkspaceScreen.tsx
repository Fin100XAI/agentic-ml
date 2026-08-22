// The workspace: what you see the moment you are signed in.
//
// Three products as three doors, and the work you have already done. That is
// all - the explanatory material lives on the landing page and in the guide,
// not here, because this screen is for someone who has come to do a job.
//
// The three are linked by the shelf rather than welded into an order: Prepare
// WRITES tables to the project, Analyse and Train READ from it. Entering a
// door with nothing on the shelf is not a dead end - it offers to prepare
// something first.
import { useCallback, useEffect, useState } from "react";
import {
  ArrowRight, Database, FileText, LineChart, RefreshCw, Sparkles,
} from "lucide-react";
import { api } from "../../api/client";
import { Badge, Button, Card, CardBody, Skeleton } from "../ui";

interface DatasetRow {
  id: string; filename: string; n_rows: number;
  n_cols?: number; pii_status?: string;
}
interface RunRow {
  id: string; filename: string; question: string | null;
  stage: string; created_at?: string | number;
}

const FINISHED = new Set(["interpret", "compare"]);

function when(v: string | number | undefined): string {
  if (v === undefined || v === null) return "";
  const d = new Date(typeof v === "number" ? v * 1000 : v);
  return Number.isNaN(d.getTime())
    ? ""
    : d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export function WorkspaceScreen({
  projectId,
  projectName,
  onPrepare,
  onAnalyse,
  onTrain,
  onOpenRun,
}: {
  projectId: string;
  projectName?: string;
  onPrepare: () => void;
  onAnalyse: () => void;
  onTrain: () => void;
  onOpenRun: (runId: string) => void;
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

  const ready = datasets.filter((d) => d.pii_status !== "pending").length;
  const reports = runs.filter((r) => FINISHED.has(r.stage)).length;

  const PRODUCTS = [
    {
      key: "prep",
      icon: Database,
      name: "Prepare data",
      line: "Turn a file into a table with a contract.",
      count: loading ? null : `${datasets.length} ${datasets.length === 1 ? "table" : "tables"} prepared`,
      cta: "Start preparing",
      onClick: onPrepare,
      primary: true,
    },
    {
      key: "analyse",
      icon: LineChart,
      name: "Analyse",
      line: "Findings, charts and answers to your questions.",
      count: loading ? null : ready ? `${ready} ready to analyse` : "nothing prepared yet",
      cta: ready ? "Choose a table" : "Prepare one first",
      onClick: ready ? onAnalyse : onPrepare,
      primary: false,
    },
    {
      key: "train",
      icon: Sparkles,
      name: "Train a model",
      line: "Predict what happens next, with a decision brief.",
      count: loading ? null : ready ? `${ready} ready to train on` : "nothing prepared yet",
      cta: ready ? "Choose a table" : "Prepare one first",
      onClick: ready ? onTrain : onPrepare,
      primary: false,
    },
  ];

  return (
    <div className="space-y-10">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="maha-eyebrow">{projectName || "Workspace"}</p>
          <h2 className="maha-rule mt-2 text-2xl text-ink md:text-[28px]">
            What would you like to do?
          </h2>
        </div>
        <Button variant="ghost" size="sm" onClick={load} disabled={loading}>
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} /> Refresh
        </Button>
      </div>

      {/* ------------------------------------------------ the three doors */}
      <div data-cascade className="grid gap-4 md:grid-cols-3">
        {PRODUCTS.map((p) => (
          <Card key={p.key} className="tile flex flex-col">
            <CardBody className="flex h-full flex-col">
              <span className="tile-icon inline-flex w-fit rounded-lg bg-accent-soft p-2.5">
                <p.icon className="h-5 w-5 text-accent" />
              </span>
              <h3 className="mt-4 text-lg text-ink">{p.name}</h3>
              <p className="mt-1 text-[13px] leading-relaxed text-ink-dim">{p.line}</p>
              <div className="mt-3 min-h-[20px]">
                {p.count === null
                  ? <Skeleton className="h-3.5 w-28" />
                  : <span className="text-[11px] tabular-nums text-faint">{p.count}</span>}
              </div>
              <div className="mt-4 pt-1">
                <Button
                  variant={p.primary ? "primary" : "outline"}
                  onClick={p.onClick}
                  className="w-full"
                >
                  {p.cta} <ArrowRight className="h-3.5 w-3.5" />
                </Button>
              </div>
            </CardBody>
          </Card>
        ))}
      </div>

      {/* ------------------------------------------- past work, and only that */}
      <section>
        <div className="mb-3 flex items-baseline justify-between gap-3">
          <h3 className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.14em] text-accent">
            <FileText className="h-3.5 w-3.5" /> Past analyses and reports
          </h3>
          {!loading && runs.length > 0 && (
            <span className="text-[11px] tabular-nums text-faint">
              {reports} of {runs.length} finished
            </span>
          )}
        </div>

        {loading ? (
          <Card>
            <CardBody className="space-y-3">
              {[0, 1, 2].map((i) => (
                <div key={i} className="flex items-center justify-between gap-4">
                  <div className="min-w-0 flex-1 space-y-1.5">
                    <Skeleton className="h-3.5 w-2/3" />
                    <Skeleton className="h-3 w-1/3" />
                  </div>
                  <Skeleton className="h-5 w-20 rounded-full" />
                </div>
              ))}
            </CardBody>
          </Card>
        ) : runs.length === 0 ? (
          <Card>
            <CardBody>
              <p className="text-sm text-ink-dim">
                Nothing yet. Prepare a table and the analyses you run against it collect
                here - with their briefs, ready to reopen.
              </p>
            </CardBody>
          </Card>
        ) : (
          <Card>
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
                      <div className="truncate text-sm">{r.question || "no question set"}</div>
                      <div className="truncate text-[11px] text-faint">
                        {r.filename}{when(r.created_at) ? ` · ${when(r.created_at)}` : ""}
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-3">
                      <Badge tone={done ? "good" : "warn"}>
                        {done ? "report ready" : r.stage}
                      </Badge>
                      <ArrowRight className="h-4 w-4 text-faint transition-transform duration-200 group-hover:translate-x-0.5" />
                    </div>
                  </button>
                );
              })}
            </CardBody>
          </Card>
        )}
      </section>
    </div>
  );
}
