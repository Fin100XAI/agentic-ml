import { useEffect, useMemo, useState } from "react";
import { Bot, Play, Settings2 } from "lucide-react";
import type { ModelInfo, ParamSpec, Profile, Recommendation } from "../../types";
import { Badge, Button, Card, CardBody, CardHeader, Spinner } from "../ui";

function ParamField({
  spec,
  value,
  onChange,
}: {
  spec: ParamSpec;
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  return (
    <label className="block">
      <div className="flex items-baseline justify-between">
        <span className="text-xs font-medium">{spec.label}</span>
        <span className="text-[10px] text-ink-dim">{spec.name}</span>
      </div>
      {spec.type === "select" ? (
        <select
          value={String(value)}
          onChange={(e) => onChange(e.target.value)}
          className="mt-1 w-full rounded-lg border border-edge bg-panel-2 px-3 py-1.5 text-sm outline-none focus:border-accent"
        >
          {spec.options?.map((o) => (
            <option key={String(o)} value={String(o)}>
              {String(o)}
            </option>
          ))}
        </select>
      ) : spec.type === "bool" ? (
        <input
          type="checkbox"
          checked={Boolean(value)}
          onChange={(e) => onChange(e.target.checked)}
          className="mt-2 h-4 w-4 accent-[#4f8ef7]"
        />
      ) : (
        <input
          type="number"
          value={value === null || value === undefined ? "" : Number(value)}
          min={spec.min}
          max={spec.max}
          step={spec.step ?? (spec.type === "int" ? 1 : 0.01)}
          onChange={(e) =>
            onChange(e.target.value === "" ? spec.default : Number(e.target.value))
          }
          className="mt-1 w-full rounded-lg border border-edge bg-panel-2 px-3 py-1.5 text-sm tabular-nums outline-none focus:border-accent"
        />
      )}
      {spec.description && (
        <p className="mt-1 text-[11px] leading-snug text-ink-dim">{spec.description}</p>
      )}
    </label>
  );
}

export function ConfigureScreen({
  profile,
  recommendation,
  models,
  onRun,
  busy,
}: {
  profile: Profile;
  recommendation: Recommendation;
  models: ModelInfo[];
  onRun: (config: {
    model_key: string;
    hyperparams: Record<string, unknown>;
    target: string | null;
    time_column: string | null;
  }) => void;
  busy: boolean;
}) {
  const useCaseModels = useMemo(
    () => models.filter((m) => m.use_case === recommendation.use_case),
    [models, recommendation.use_case],
  );
  const rankedKeys = recommendation.ranked_models.map((r) => r.key);
  const ordered = useMemo(
    () =>
      [...useCaseModels].sort(
        (a, b) =>
          (rankedKeys.indexOf(a.key) + 99 * Number(rankedKeys.indexOf(a.key) < 0)) -
          (rankedKeys.indexOf(b.key) + 99 * Number(rankedKeys.indexOf(b.key) < 0)),
      ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [useCaseModels, recommendation],
  );

  const [selectedKey, setSelectedKey] = useState(ordered[0]?.key ?? "");
  const selected = ordered.find((m) => m.key === selectedKey) ?? ordered[0];

  const [params, setParams] = useState<Record<string, unknown>>({});
  const [target, setTarget] = useState<string | null>(recommendation.target);
  const [timeColumn, setTimeColumn] = useState<string | null>(recommendation.time_column);

  // Reset params to defaults whenever the model changes.
  useEffect(() => {
    if (!selected) return;
    const defaults: Record<string, unknown> = {};
    for (const p of selected.param_schema) defaults[p.name] = p.default;
    setParams(defaults);
  }, [selected?.key]); // eslint-disable-line react-hooks/exhaustive-deps

  const needsTarget = recommendation.use_case !== "clustering";
  const targetOptions = profile.columns
    .filter((c) =>
      recommendation.use_case === "forecasting"
        ? c.role === "numeric"
        : c.role !== "identifier",
    )
    .map((c) => c.name);
  const timeOptions = profile.columns
    .filter((c) => c.role === "datetime" || c.role === "text" || c.role === "identifier")
    .map((c) => c.name);

  if (!selected) return null;

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      {/* Agent recommendation + model cards */}
      <div className="space-y-6 lg:col-span-2">
        <Card>
          <CardHeader
            title={
              <span className="flex items-center gap-2">
                <Bot className="h-4 w-4 text-accent" /> Recommendation agent
              </span>
            }
            right={
              <div className="flex gap-2">
                <Badge tone="accent">{recommendation.use_case}</Badge>
                <Badge tone={recommendation.generated_by === "claude" ? "accent" : "neutral"}>
                  {recommendation.generated_by}
                </Badge>
              </div>
            }
          />
          <CardBody>
            <p className="text-sm leading-relaxed text-ink-dim">{recommendation.reasoning}</p>
          </CardBody>
        </Card>

        <div className="grid gap-4 md:grid-cols-3">
          {ordered.map((m, idx) => {
            const ranked = recommendation.ranked_models.find((r) => r.key === m.key);
            const active = m.key === selected.key;
            return (
              <button
                key={m.key}
                onClick={() => setSelectedKey(m.key)}
                className={`rounded-xl border p-4 text-left transition-all ${
                  active
                    ? "border-accent bg-accent-soft/40 shadow-lg shadow-accent/10"
                    : "border-edge bg-panel hover:border-accent/50"
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold">{m.name}</span>
                  {idx === 0 && <Badge tone="good">recommended</Badge>}
                </div>
                <p className="mt-1.5 text-[11px] leading-snug text-ink-dim">{m.description}</p>
                {ranked && (
                  <p className="mt-2 border-t border-edge/60 pt-2 text-[11px] italic leading-snug text-ink-dim">
                    {ranked.rationale}
                  </p>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Hyperparameter form (auto-generated from param_schema) */}
      <Card className="h-fit">
        <CardHeader
          title={
            <span className="flex items-center gap-2">
              <Settings2 className="h-4 w-4 text-warn" /> {selected.name} configuration
            </span>
          }
          subtitle="Adjust, then approve & run"
        />
        <CardBody className="space-y-4">
          {needsTarget && (
            <label className="block">
              <span className="text-xs font-medium">
                {recommendation.use_case === "forecasting" ? "Series to forecast" : "Target column"}
              </span>
              <select
                value={target ?? ""}
                onChange={(e) => setTarget(e.target.value || null)}
                className="mt-1 w-full rounded-lg border border-edge bg-panel-2 px-3 py-1.5 text-sm outline-none focus:border-accent"
              >
                <option value="">— choose —</option>
                {targetOptions.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>
          )}

          {recommendation.use_case === "forecasting" && (
            <label className="block">
              <span className="text-xs font-medium">Time column (optional)</span>
              <select
                value={timeColumn ?? ""}
                onChange={(e) => setTimeColumn(e.target.value || null)}
                className="mt-1 w-full rounded-lg border border-edge bg-panel-2 px-3 py-1.5 text-sm outline-none focus:border-accent"
              >
                <option value="">— row order —</option>
                {timeOptions.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>
          )}

          <div className="space-y-3 border-t border-edge pt-4">
            {selected.param_schema.map((spec) => (
              <ParamField
                key={spec.name}
                spec={spec}
                value={params[spec.name] ?? spec.default}
                onChange={(v) => setParams((p) => ({ ...p, [spec.name]: v }))}
              />
            ))}
          </div>

          <div className="pt-2">
            {busy ? (
              <Spinner label="Training & evaluating…" />
            ) : (
              <Button
                className="w-full"
                disabled={needsTarget && !target}
                onClick={() =>
                  onRun({
                    model_key: selected.key,
                    hyperparams: params,
                    target,
                    time_column: timeColumn,
                  })
                }
              >
                <Play className="h-4 w-4" /> Approve & run model
              </Button>
            )}
          </div>
        </CardBody>
      </Card>
    </div>
  );
}
