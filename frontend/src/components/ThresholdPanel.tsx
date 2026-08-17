// Decision-threshold tuner: slide the operating point, watch precision,
// recall, F1 and the confusion matrix move - then approve the one to use
// for scoring. The F1-optimal point is only the suggestion.
import { useState } from "react";
import { SlidersHorizontal } from "lucide-react";
import { api } from "../api/client";
import type { RunResult } from "../types";
import { ConfusionMatrix } from "./charts";
import { Badge, Button, Card, CardBody, CardHeader } from "./ui";

export function ThresholdPanel({
  curve,
  modelId,
  version,
}: {
  curve: NonNullable<RunResult["artifacts"]["threshold_curve"]>;
  modelId?: string;
  version?: number;
}) {
  const [thr, setThr] = useState(curve.suggested);
  const [saved, setSaved] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const point =
    curve.points.reduce((best, p) =>
      Math.abs(p.threshold - thr) < Math.abs(best.threshold - thr) ? p : best,
    curve.points[0]);

  const save = async () => {
    if (!modelId || version == null) return;
    setBusy(true);
    try {
      await api.setThreshold(modelId, version, point.threshold);
      setSaved(point.threshold);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardHeader
        title={
          <span className="flex items-center gap-2">
            <SlidersHorizontal className="h-4 w-4 text-accent" /> Decision threshold
          </span>
        }
        subtitle={`Above this probability the model calls '${curve.labels[1]}'. Move it to trade missed cases against false alarms - the suggested ${curve.suggested} maximizes F1, but the right point depends on which mistake costs you more.`}
      />
      <CardBody>
        <div className="flex flex-wrap items-start gap-6">
          <div className="min-w-60 flex-1">
            <div className="flex items-center gap-3">
              <input
                type="range"
                min={0.05}
                max={0.95}
                step={0.05}
                value={thr}
                onChange={(e) => setThr(Number(e.target.value))}
                className="w-full accent-[#1d4ed8]"
              />
              <span className="w-10 text-sm font-semibold tabular-nums">{point.threshold}</span>
            </div>
            <div className="mt-3 grid grid-cols-3 gap-2">
              {([["precision", "few false alarms"], ["recall", "few missed cases"], ["f1", "balance"]] as const).map(([k, hint]) => (
                <div key={k} className="rounded-xl border border-edge bg-panel-2 px-3 py-2">
                  <div className="text-[10px] uppercase tracking-wider text-ink-dim" title={hint}>{k}</div>
                  <div className="text-lg font-semibold tabular-nums">{point[k]}</div>
                </div>
              ))}
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              {point.threshold === curve.suggested && <Badge tone="good">suggested</Badge>}
              {modelId && version != null && (
                <Button size="sm" onClick={save} disabled={busy || saved === point.threshold}>
                  {saved === point.threshold
                    ? `Saved - scoring uses ${saved}`
                    : `Use ${point.threshold} for scoring`}
                </Button>
              )}
            </div>
          </div>
          <div>
            <ConfusionMatrix
              labels={curve.labels}
              matrix={[
                [point.tn, point.fp],
                [point.fn, point.tp],
              ]}
            />
          </div>
        </div>
      </CardBody>
    </Card>
  );
}
