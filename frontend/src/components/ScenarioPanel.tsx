// What-if panel: perturb up to three inputs of a registered model and see how
// the prediction responds - with honest extrapolation warnings and permanent
// correlation-not-causation framing.
import { useEffect, useState } from "react";
import { FlaskConical, LineChart as LineChartIcon } from "lucide-react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api/client";
import type { ScenarioMeta, ScenarioResult } from "../types";
import { Badge, Button, Card, CardBody, CardHeader } from "./ui";

export function ScenarioPanel({ modelId, version }: { modelId: string; version: number }) {
  const [meta, setMeta] = useState<ScenarioMeta | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  const [values, setValues] = useState<Record<string, number>>({});
  const [active, setActive] = useState<string[]>([]);
  const [result, setResult] = useState<ScenarioResult | null>(null);
  const [curve, setCurve] = useState<{ feature: string; points: { x: number; y: number }[] } | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.scenarioMeta(modelId, version)
      .then((m) => {
        setMeta(m);
        if (m.features.length > 0) {
          setActive([m.features[0].column]);
          setValues(Object.fromEntries(m.features.map((f) => [f.column, Number(f.baseline ?? f.min)])));
        }
      })
      .catch(() => setUnavailable(true));
  }, [modelId, version]);

  if (unavailable || !meta || meta.features.length === 0) return null;

  const featureOf = (col: string) => meta.features.find((f) => f.column === col)!;
  const outside = (col: string) => {
    const f = featureOf(col);
    const v = values[col];
    return v < f.min || v > f.max;
  };

  const ask = async () => {
    setBusy(true);
    setCurve(null);
    try {
      const perturbations = Object.fromEntries(active.map((c) => [c, values[c]]));
      setResult(await api.runScenario(modelId, version, perturbations));
    } finally {
      setBusy(false);
    }
  };

  const drawCurve = async () => {
    setBusy(true);
    try {
      const c = await api.scenarioCurve(modelId, version, active[0]);
      setCurve({ feature: c.feature, points: c.points });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardHeader
        title={
          <span className="flex items-center gap-2">
            <FlaskConical className="h-4 w-4 text-accent" /> What if…?
          </span>
        }
        subtitle="Move an input and see how the model's prediction responds. Sliders cover the range actually seen in training; typing beyond it is allowed but flagged as guesswork."
      />
      <CardBody className="space-y-3">
        {active.map((col) => {
          const f = featureOf(col);
          return (
            <div key={col} className="flex flex-wrap items-center gap-2">
              <select
                value={col}
                onChange={(e) => {
                  const next = e.target.value;
                  setActive((a) => a.map((c) => (c === col ? next : c)));
                }}
                className="rounded-lg border border-edge bg-panel-2 px-2 py-1 text-xs"
              >
                {meta.features
                  .filter((x) => x.column === col || !active.includes(x.column))
                  .map((x) => (
                    <option key={x.column} value={x.column}>{x.label}</option>
                  ))}
              </select>
              <input
                type="range"
                min={f.min}
                max={f.max}
                step={(f.max - f.min) / 100 || 1}
                value={Math.min(Math.max(values[col] ?? f.min, f.min), f.max)}
                onChange={(e) => setValues((v) => ({ ...v, [col]: Number(e.target.value) }))}
                className="w-40 accent-accent"
              />
              <input
                type="number"
                value={values[col] ?? ""}
                onChange={(e) => setValues((v) => ({ ...v, [col]: Number(e.target.value) }))}
                className={`w-24 rounded-lg border px-2 py-1 text-xs tabular-nums ${
                  outside(col) ? "border-warn bg-warn/10" : "border-edge bg-panel-2"
                }`}
              />
              {outside(col) && <Badge tone="warn">outside observed range</Badge>}
              {active.length > 1 && (
                <button
                  onClick={() => setActive((a) => a.filter((c) => c !== col))}
                  className="text-[11px] text-ink-dim hover:text-bad"
                >
                  remove
                </button>
              )}
            </div>
          );
        })}
        <div className="flex flex-wrap items-center gap-2">
          {active.length < 3 && meta.features.length > active.length && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                const next = meta.features.find((f) => !active.includes(f.column));
                if (next) setActive((a) => [...a, next.column]);
              }}
            >
              + another input
            </Button>
          )}
          <Button size="sm" onClick={ask} disabled={busy}>
            What happens?
          </Button>
          <Button variant="outline" size="sm" onClick={drawCurve} disabled={busy}>
            <LineChartIcon className="h-3.5 w-3.5" /> Response curve for {featureOf(active[0]).label}
          </Button>
        </div>

        {result && (
          <div className="rounded-2xl border border-edge bg-panel-2 px-4 py-3">
            <div className="flex flex-wrap items-center gap-4 text-sm">
              <span>
                Typical record: <span className="font-semibold tabular-nums">{result.baseline}</span>
              </span>
              <span>
                With your change: <span className="font-semibold tabular-nums">{result.perturbed}</span>
              </span>
              <Badge tone={Math.abs(result.change) < 0.01 ? "neutral" : result.change > 0 ? "warn" : "good"}>
                {result.change > 0 ? "+" : ""}{result.change} {result.response}
              </Badge>
              {result.extrapolations.length > 0 && (
                <Badge tone="warn">extrapolating beyond training data</Badge>
              )}
            </div>
            {result.phrased && <p className="mt-2 text-xs leading-relaxed">{result.phrased}</p>}
            <p className="mt-2 text-[10px] leading-snug text-ink-dim">{result.caveat}</p>
          </div>
        )}

        {curve && (
          <div className="rounded-2xl border border-edge bg-panel-2 p-3">
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={curve.points} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
                <CartesianGrid stroke="var(--chart-grid)" />
                <XAxis dataKey="x" tick={{ stroke: "var(--chart-axis)", fontSize: 10 }} tickFormatter={(v) => String(Math.round(v * 100) / 100)} />
                <YAxis tick={{ stroke: "var(--chart-axis)", fontSize: 10 }} domain={["auto", "auto"]} />
                <Tooltip contentStyle={{ fontSize: 12, borderRadius: 10 }} />
                <Line type="monotone" dataKey="y" stroke="var(--color-accent)" strokeWidth={2} dot={false} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
            <p className="mt-1 text-[10px] leading-snug text-ink-dim">
              Predicted {meta.response} as {featureOf(curve.feature).label.toLowerCase()} sweeps its
              observed range, with everything else typical. Correlation, not proven cause.
            </p>
          </div>
        )}
      </CardBody>
    </Card>
  );
}
