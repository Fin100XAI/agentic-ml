// Reliability curve: do the model's probabilities mean what they say?
// Points on the diagonal = honest probabilities; above/below = the model
// under/overstates its confidence.
import { Gauge } from "lucide-react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { RunResult } from "../types";
import { Badge, Card, CardBody, CardHeader } from "./ui";

export function CalibrationPanel({
  cal,
}: {
  cal: NonNullable<RunResult["artifacts"]["calibration"]>;
}) {
  if (cal.skipped) {
    return (
      <Card>
        <CardBody className="py-3">
          <p className="text-xs leading-relaxed text-ink-dim">
            <span className="font-semibold text-ink">Probability check:</span> {cal.note}
          </p>
        </CardBody>
      </Card>
    );
  }
  const pos = cal.labels?.[1] ?? "positive";
  const data = (cal.bins ?? []).map((b) => ({
    predicted: b.predicted,
    observed: b.observed,
    count: b.count,
  }));
  return (
    <Card>
      <CardHeader
        title={
          <span className="flex items-center gap-2">
            <Gauge className="h-4 w-4 text-accent" /> Probability check
          </span>
        }
        subtitle={`When the model says an outcome is X% likely, how often does '${pos}' actually happen? Points near the dotted line mean the percentages are honest.`}
        right={
          <Badge tone={cal.verdict === "well calibrated" ? "good" : "warn"}>{cal.verdict}</Badge>
        }
      />
      <CardBody>
        <div className="flex flex-wrap items-start gap-6">
          <div className="h-52 min-w-64 flex-1">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: -18 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.08)" />
                <XAxis
                  dataKey="predicted" type="number" domain={[0, 1]}
                  tick={{ fontSize: 10 }} tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
                  label={{ value: "model said", position: "insideBottom", offset: -2, fontSize: 10 }}
                />
                <YAxis
                  type="number" domain={[0, 1]}
                  tick={{ fontSize: 10 }} tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
                  label={{ value: "actually happened", angle: -90, position: "insideLeft", offset: 24, fontSize: 10 }}
                />
                <Tooltip
                  formatter={(v) => `${Math.round(Number(v) * 100)}%`}
                  labelFormatter={(v) => `model said ${Math.round(Number(v) * 100)}%`}
                />
                <ReferenceLine
                  segment={[{ x: 0, y: 0 }, { x: 1, y: 1 }]}
                  stroke="#94a3b8" strokeDasharray="4 4"
                />
                <Line
                  type="monotone" dataKey="observed" stroke="#1d4ed8"
                  strokeWidth={2} dot={{ r: 3 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div className="max-w-64 space-y-3">
            <div className="grid grid-cols-2 gap-2">
              <div className="rounded-xl border border-edge bg-panel-2 px-3 py-2">
                <div className="text-[10px] uppercase tracking-wider text-ink-dim" title="Average squared gap between predicted probability and outcome; lower is better.">
                  Brier score
                </div>
                <div className="text-lg font-semibold tabular-nums">{cal.brier}</div>
              </div>
              <div className="rounded-xl border border-edge bg-panel-2 px-3 py-2">
                <div className="text-[10px] uppercase tracking-wider text-ink-dim" title="Weighted gap between what the model said and what happened; under 0.05 reads as honest.">
                  Avg gap
                </div>
                <div className="text-lg font-semibold tabular-nums">{cal.ece}</div>
              </div>
            </div>
            <p className="text-xs leading-relaxed text-ink-dim">{cal.note}</p>
            <p className="text-[10px] text-ink-dim">
              Measured on out-of-fold predictions ({cal.cv_folds}-fold, {cal.n} rows).
            </p>
          </div>
        </div>
      </CardBody>
    </Card>
  );
}
