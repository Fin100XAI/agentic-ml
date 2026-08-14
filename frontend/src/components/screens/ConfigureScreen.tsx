import { useEffect, useMemo, useState } from "react";
import { Bot, Clock3, FlaskConical, GitCompare, Play, Settings2, Sparkles, Undo2 } from "lucide-react";
import type { ModelInfo, ParamSpec, Profile, Recommendation } from "../../types";
import { eta } from "../../lib/eta";
import { BusyStatus } from "../Elapsed";
import { InfoTip } from "../InfoTip";
import { Badge, Button, Card, CardBody, CardHeader, Spinner } from "../ui";

function ParamField({
  spec,
  value,
  suggested,
  onChange,
}: {
  spec: ParamSpec;
  value: unknown;
  suggested: unknown;
  onChange: (v: unknown) => void;
}) {
  const isSuggested = suggested !== undefined && String(value) === String(suggested);
  return (
    <label className="block">
      <div className="flex items-baseline justify-between gap-2">
        <span className="inline-flex items-center gap-1 text-xs font-medium">
          {spec.label}
          <InfoTip text={spec.description} />
        </span>
        {isSuggested && (
          <span className="inline-flex items-center gap-1 text-[10px] text-good">
            <Sparkles className="h-3 w-3" /> suggested
          </span>
        )}
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
          className="mt-2 h-4 w-4 accent-[#4f46e5]"
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
    </label>
  );
}

/** One of the three "what happens next" path cards. */
function PathCard({
  icon: Icon,
  title,
  steps,
  time,
  actionLabel,
  onAction,
  disabled,
  primary,
}: {
  icon: typeof Play;
  title: string;
  steps: string[];
  time: string;
  actionLabel: string;
  onAction: () => void;
  disabled: boolean;
  primary?: boolean;
}) {
  return (
    <div
      className={`flex min-w-0 flex-col rounded-2xl border p-4 backdrop-blur-xl ${
        primary ? "border-accent/50 bg-accent-soft/30" : "border-edge bg-panel"
      }`}
    >
      <div className="flex items-center gap-2">
        <span className={`rounded-lg p-1.5 ${primary ? "bg-accent text-white" : "bg-accent-soft text-accent"}`}>
          <Icon className="h-4 w-4" />
        </span>
        <h4 className="text-sm font-semibold">{title}</h4>
      </div>
      <ol className="mt-3 flex-1 space-y-1.5">
        {steps.map((s, i) => (
          <li key={i} className="flex gap-2 text-[11px] leading-snug text-ink-dim">
            <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-slate-500/10 text-[9px] font-semibold">
              {i + 1}
            </span>
            <span className="min-w-0">{s}</span>
          </li>
        ))}
      </ol>
      <div className="mt-3 flex items-center justify-between gap-2 border-t border-edge/60 pt-2.5">
        <span className="inline-flex items-center gap-1 text-[10px] text-ink-dim">
          <Clock3 className="h-3 w-3" /> {time}
        </span>
        <Button size="sm" variant={primary ? "primary" : "outline"} disabled={disabled} onClick={onAction}>
          {actionLabel}
        </Button>
      </div>
    </div>
  );
}

export function ConfigureScreen({
  profile,
  recommendation,
  models,
  initialModelKey,
  onRun,
  onCompare,
  onAutotune,
  onChangeDirection,
  busy,
  busyLabel,
}: {
  profile: Profile;
  recommendation: Recommendation;
  models: ModelInfo[];
  initialModelKey?: string;
  onRun: (config: {
    model_key: string;
    hyperparams: Record<string, unknown>;
    target: string | null;
    time_column: string | null;
  }) => void;
  onCompare: (target: string | null, time_column: string | null) => void;
  onAutotune: (target: string | null, time_column: string | null) => void;
  onChangeDirection: () => void;
  busy: boolean;
  busyLabel: string;
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

  const [selectedKey, setSelectedKey] = useState(initialModelKey ?? ordered[0]?.key ?? "");
  const [showReasoning, setShowReasoning] = useState(false);
  const selected = ordered.find((m) => m.key === selectedKey) ?? ordered[0];
  const suggestion = recommendation.model_configs?.[selected?.key ?? ""];

  const [params, setParams] = useState<Record<string, unknown>>({});
  const [target, setTarget] = useState<string | null>(recommendation.target);
  const [timeColumn, setTimeColumn] = useState<string | null>(recommendation.time_column);

  // Pre-fill with the agent's data-aware suggestion (fallback: schema defaults).
  useEffect(() => {
    if (!selected) return;
    const sug = recommendation.model_configs?.[selected.key]?.hyperparams ?? {};
    const values: Record<string, unknown> = {};
    for (const p of selected.param_schema) values[p.name] = sug[p.name] ?? p.default;
    setParams(values);
  }, [selected?.key]); // eslint-disable-line react-hooks/exhaustive-deps

  const needsTarget = recommendation.use_case !== "clustering";
  const targetOptions = profile.columns
    .filter((c) =>
      recommendation.use_case === "forecasting" ? c.role === "numeric" : c.role !== "identifier",
    )
    .map((c) => c.name);
  const timeOptions = profile.columns
    .filter((c) => c.role === "datetime" || c.role === "text" || c.role === "identifier")
    .map((c) => c.name);

  if (!selected) return null;
  const suggestedValues = suggestion?.hyperparams ?? {};
  const disabled = (needsTarget && !target) || busy;

  return (
    <div className="space-y-6">
      {/* Recommendation summary - one line, details on demand */}
      <Card>
        <CardBody className="flex flex-wrap items-center justify-between gap-3 py-3.5">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <Bot className="h-4 w-4 shrink-0 text-accent" />
            <span className="text-sm">
              Agent recommends <span className="font-semibold capitalize">{recommendation.use_case}</span>
              {" "}with <span className="font-semibold">{ordered[0]?.name}</span> as top pick
            </span>
            <Badge tone={recommendation.generated_by === "claude" ? "accent" : "neutral"}>
              {recommendation.generated_by}
            </Badge>
            <button
              onClick={() => setShowReasoning((s) => !s)}
              className="text-xs font-medium text-accent hover:underline"
            >
              {showReasoning ? "Hide why" : "Why?"}
            </button>
          </div>
          <Button variant="ghost" size="sm" onClick={onChangeDirection}>
            <Undo2 className="h-3.5 w-3.5" /> Change direction
          </Button>
        </CardBody>
        {showReasoning && (
          <div className="border-t border-edge px-5 py-3">
            <p className="text-xs leading-relaxed text-ink-dim">{recommendation.reasoning}</p>
          </div>
        )}
      </Card>

      {/* Busy status with live timer */}
      {busy && (
        <Card>
          <CardBody>
            <BusyStatus running={busy} label={busyLabel} expected={eta("compare", profile.n_rows, true)} />
          </CardBody>
        </Card>
      )}

      {/* Three paths - what happens if you click each */}
      {!busy && (
        <div className="grid gap-4 md:grid-cols-3">
          <PathCard
            icon={Play}
            title="Run the model"
            primary
            steps={[
              `Trains ${selected.name} with the settings on the right`,
              "Extracts drivers, findings and an executive brief",
              "You land on the decision brief",
            ]}
            time={eta("train", profile.n_rows, true)}
            actionLabel="Run"
            disabled={disabled}
            onAction={() =>
              onRun({ model_key: selected.key, hyperparams: params, target, time_column: timeColumn })
            }
          />
          <PathCard
            icon={FlaskConical}
            title="Auto-tune first"
            steps={[
              `Tries up to 8 setting combos for each of the ${ordered.length} models`,
              "Scores every combo on held-back data",
              "Best settings get pre-filled - you still choose what to run",
            ]}
            time={eta("autotune", profile.n_rows, true)}
            actionLabel="Auto-tune"
            disabled={disabled}
            onAction={() => onAutotune(target, timeColumn)}
          />
          <PathCard
            icon={GitCompare}
            title="Compare everything"
            steps={[
              `Trains all ${ordered.length} models with suggested settings`,
              "Ranks them on a leaderboard",
              "Generate insights with the winner in one click",
            ]}
            time={eta("compare", profile.n_rows, true)}
            actionLabel="Compare"
            disabled={disabled}
            onAction={() => onCompare(target, timeColumn)}
          />
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Model cards */}
        <div className="space-y-4 lg:col-span-2">
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
                    {idx === 0 && <Badge tone="good">top pick</Badge>}
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

          {/* Why these settings */}
          {suggestion?.rationale && (
            <div className="flex items-start gap-2.5 rounded-xl border border-good/30 bg-good/5 px-4 py-3">
              <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-good" />
              <div>
                <div className="text-xs font-semibold text-good">
                  Settings suggested from your data
                </div>
                <p className="mt-0.5 text-xs leading-relaxed text-ink-dim">{suggestion.rationale}</p>
              </div>
            </div>
          )}
        </div>

        {/* Hyperparameter form */}
        <Card className="h-fit">
          <CardHeader
            title={
              <span className="flex items-center gap-2">
                <Settings2 className="h-4 w-4 text-warn" /> {selected.name}
              </span>
            }
            subtitle="Approve the suggested settings, or adjust them"
          />
          <CardBody className="space-y-4">
            {needsTarget && (
              <label className="block">
                <span className="inline-flex items-center gap-1 text-xs font-medium">
                  {recommendation.use_case === "forecasting" ? "Series to forecast" : "What to predict"}
                  <InfoTip
                    text={
                      recommendation.use_case === "forecasting"
                        ? "The numeric column whose future values you want."
                        : "The column whose value the model should learn to predict."
                    }
                  />
                </span>
                <select
                  value={target ?? ""}
                  onChange={(e) => setTarget(e.target.value || null)}
                  className="mt-1 w-full rounded-lg border border-edge bg-panel-2 px-3 py-1.5 text-sm outline-none focus:border-accent"
                >
                  <option value="">- choose -</option>
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
                <span className="inline-flex items-center gap-1 text-xs font-medium">
                  Time column
                  <InfoTip text="The date column that orders your data. Leave as row order if there isn't one." />
                </span>
                <select
                  value={timeColumn ?? ""}
                  onChange={(e) => setTimeColumn(e.target.value || null)}
                  className="mt-1 w-full rounded-lg border border-edge bg-panel-2 px-3 py-1.5 text-sm outline-none focus:border-accent"
                >
                  <option value="">- row order -</option>
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
                  suggested={suggestedValues[spec.name]}
                  onChange={(v) => setParams((p) => ({ ...p, [spec.name]: v }))}
                />
              ))}
            </div>

            <div className="pt-2">
              {busy ? (
                <Spinner label={busyLabel} />
              ) : (
                <>
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
                    <Play className="h-4 w-4" /> Approve & run {selected.name}
                  </Button>
                  <p className="mt-1.5 text-center text-[10px] text-ink-dim">
                    {eta("train", profile.n_rows, true)}
                  </p>
                </>
              )}
            </div>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
