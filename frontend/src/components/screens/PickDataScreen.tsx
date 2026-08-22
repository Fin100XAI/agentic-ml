// The join between the three products: Analyse and Train both start here.
//
// Prepare writes tables to the project; these two read from it. Rather than
// each growing its own file picker, both land on this screen, choose from the
// same shelf, and carry on. Nothing on the shelf is not a dead end - the
// screen offers to prepare something instead.
import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, ArrowRight, Database, ShieldAlert, Wand2 } from "lucide-react";
import { api } from "../../api/client";
import { Badge, Button, Card, CardBody, Skeleton } from "../ui";

interface DatasetRow {
  id: string; filename: string; n_rows: number;
  n_cols?: number; pii_status?: string;
}

export function PickDataScreen({
  projectId,
  purpose,
  onPick,
  onPrepare,
  onBack,
}: {
  projectId: string;
  /** Only the wording changes; the shelf is the same either way. */
  purpose: "analyse" | "train";
  onPick: (datasetId: string, filename: string) => void;
  onPrepare: () => void;
  onBack: () => void;
}) {
  const [datasets, setDatasets] = useState<DatasetRow[] | null>(null);

  const load = useCallback(() => {
    api.getProjectDetail(projectId)
      .then((d) => setDatasets((d.datasets as DatasetRow[]) || []))
      .catch(() => setDatasets([]));
  }, [projectId]);
  useEffect(load, [load]);

  const analysing = purpose === "analyse";

  return (
    <div className="space-y-6">
      <div>
        <button
          onClick={onBack}
          className="mb-4 inline-flex items-center gap-1.5 text-xs text-ink-dim transition-colors hover:text-accent"
        >
          <ArrowLeft className="h-3.5 w-3.5" /> Back
        </button>
        <p className="maha-eyebrow">{analysing ? "Analyse" : "Train a model"}</p>
        <h2 className="maha-rule mt-2 text-2xl text-ink md:text-[28px]">
          Which table?
        </h2>
        <p className="mt-5 max-w-2xl text-sm leading-relaxed text-ink-dim">
          {analysing
            ? "Everything you have prepared in this project. Pick one and the exploring agents will read it and put the first questions to you."
            : "Everything you have prepared in this project. Pick one, then say what you want to predict - the method is recommended and explained before anything trains."}
        </p>
      </div>

      {datasets === null ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Card key={i}>
              <CardBody className="space-y-2">
                <Skeleton className="h-4 w-2/3" />
                <Skeleton className="h-3 w-1/2" />
                <Skeleton className="mt-3 h-8 w-full rounded" />
              </CardBody>
            </Card>
          ))}
        </div>
      ) : datasets.length === 0 ? (
        <Card>
          <CardBody className="flex flex-col items-start gap-4 py-8 text-center sm:items-center">
            <span className="inline-flex rounded-lg bg-accent-soft p-3">
              <Database className="h-6 w-6 text-accent" />
            </span>
            <div className="sm:text-center">
              <p className="text-sm font-semibold text-ink">Nothing on the shelf yet</p>
              <p className="mx-auto mt-1.5 max-w-md text-[13px] leading-relaxed text-ink-dim">
                {analysing ? "Analysis" : "Training"} reads from tables you have prepared.
                Prepare one and it will be waiting here - and in every other product too.
              </p>
            </div>
            <Button onClick={onPrepare}>
              <Wand2 className="h-3.5 w-3.5" /> Prepare a file <ArrowRight className="h-3.5 w-3.5" />
            </Button>
          </CardBody>
        </Card>
      ) : (
        <div data-cascade className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {datasets.map((ds) => {
            const gated = ds.pii_status === "pending";
            return (
              <Card key={ds.id} className="tile">
                <CardBody className="flex h-full flex-col">
                  <p className="truncate text-sm font-semibold text-ink" title={ds.filename}>
                    {ds.filename}
                  </p>
                  <p className="mt-0.5 text-[11px] tabular-nums text-faint">
                    {ds.n_rows.toLocaleString()} rows
                    {ds.n_cols ? ` · ${ds.n_cols} columns` : ""}
                  </p>
                  {gated && (
                    <p className="mt-2 flex items-center gap-1.5">
                      <ShieldAlert className="h-3.5 w-3.5 text-warn" />
                      <Badge tone="warn">privacy review pending</Badge>
                    </p>
                  )}
                  <div className="mt-4 pt-1">
                    <Button
                      className="w-full"
                      variant="outline"
                      disabled={gated}
                      onClick={() => onPick(ds.id, ds.filename)}
                      title={gated
                        ? "Finish the privacy review before using this table"
                        : `Use ${ds.filename}`}
                    >
                      {analysing ? "Analyse this" : "Train on this"}
                      <ArrowRight className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </CardBody>
              </Card>
            );
          })}
          <Card className="tile border-dashed">
            <CardBody className="flex h-full flex-col items-start justify-center gap-3">
              <p className="text-[13px] text-ink-dim">Need a different file?</p>
              <Button variant="ghost" onClick={onPrepare}>
                <Wand2 className="h-3.5 w-3.5" /> Prepare another
              </Button>
            </CardBody>
          </Card>
        </div>
      )}
    </div>
  );
}
