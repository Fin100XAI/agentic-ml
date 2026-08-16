// Landing screen: what the platform can do, its agents, models, and past runs.
import {
  ArrowRight,
  BarChart3,
  Bot,
  FileUp,
  GitCompare,
  Play,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import type { ModelInfo, RunSummary } from "../../types";
import { USE_CASE_INFO } from "../../lib/metricInfo";
import { Badge, Button, Card, CardBody } from "../ui";

const AGENTS = [
  {
    name: "EDA Agent",
    icon: Search,
    does: "Reads your data the moment you upload it: column types, missing values, correlations, likely prediction targets.",
    gives: "A plain-language briefing on what your dataset contains.",
  },
  {
    name: "Recommendation Agent",
    icon: Bot,
    does: "Matches your goal + data shape to the right kind of analysis, ranks the models, and suggests settings computed from your actual data.",
    gives: "A recommended model with settings you approve or adjust.",
  },
  {
    name: "Interpretation Agent",
    icon: BarChart3,
    does: "Reads the trained model's scores and charts, judges how well it did, and tells you what to try next.",
    gives: "Results explained in plain language, not jargon.",
  },
];

const PIPELINE = [
  { icon: FileUp, label: "Upload CSV" },
  { icon: Search, label: "Agent explores it" },
  { icon: Settings2, label: "You approve the approach" },
  { icon: Play, label: "Evidence engines run" },
  { icon: BarChart3, label: "Decision brief + actions" },
];

const FEATURES = [
  {
    icon: ShieldCheck,
    title: "You stay in control",
    text: "Agents propose - nothing runs until you approve. Every decision is logged on a timeline.",
  },
  {
    icon: GitCompare,
    title: "Compare all models at once",
    text: "One click trains every model for your task and ranks them, so you don't have to guess.",
  },
  {
    icon: Sparkles,
    title: "Settings suggested from your data",
    text: "Group counts, seasonality, tree depths - computed from the dataset you uploaded, with the reasoning shown.",
  },
];

export function HomeScreen({
  models,
  recentRuns,
  onStart,
  onResume,
}: {
  models: ModelInfo[];
  recentRuns: RunSummary[];
  onStart: () => void;
  onResume: (id: string) => void;
}) {
  const useCases = ["classification", "regression", "clustering", "forecasting"];

  return (
    <div className="space-y-10">
      {/* Hero */}
      <div className="rounded-2xl border border-edge bg-gradient-to-br from-panel via-panel to-accent-soft/30 px-8 py-10 text-center">
        <h2 className="mx-auto max-w-2xl text-2xl font-bold leading-snug">
          Turn raw data into decisions.
          <span className="text-accent"> No data-science degree required.</span>
        </h2>
        <p className="mx-auto mt-3 max-w-xl text-sm leading-relaxed text-ink-dim">
          Upload a spreadsheet and get a decision brief: what's driving outcomes, what
          groups exist, where things are heading - with recommended actions and an honest
          read on how much to trust them. AI agents do the analysis; you approve every step.
        </p>
        <Button className="mt-6 px-6" onClick={onStart}>
          Start a new analysis <ArrowRight className="h-4 w-4" />
        </Button>

        {/* Mini pipeline */}
        <div className="mt-8 flex flex-wrap items-center justify-center gap-2">
          {PIPELINE.map((p, i) => (
            <div key={p.label} className="flex items-center gap-2">
              {i > 0 && <div className="h-px w-5 bg-edge" />}
              <div className="flex items-center gap-1.5 rounded-full border border-edge bg-panel px-3 py-1.5 text-[11px] text-ink-dim">
                <p.icon className="h-3.5 w-3.5 text-accent" />
                {p.label}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* What you can analyze */}
      <section>
        <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-ink-dim">
          What you can analyze
        </h3>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {useCases.map((uc) => {
            const info = USE_CASE_INFO[uc];
            const ucModels = models.filter((m) => m.use_case === uc);
            return (
              <Card key={uc} className="transition-colors hover:border-accent/50">
                <CardBody>
                  <div className="text-2xl">{info.icon}</div>
                  <h4 className="mt-2 text-sm font-semibold">{info.title}</h4>
                  <p className="mt-0.5 text-xs text-ink-dim">{info.tagline}</p>
                  <p className="mt-2 text-[11px] italic leading-snug text-ink-dim/80">{info.example}</p>
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {ucModels.map((m) => (
                      <Badge key={m.key} tone="accent">{m.name}</Badge>
                    ))}
                  </div>
                </CardBody>
              </Card>
            );
          })}
        </div>
      </section>

      {/* Agents */}
      <section>
        <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-ink-dim">
          Meet your agents
        </h3>
        <div className="grid gap-4 md:grid-cols-3">
          {AGENTS.map((a) => (
            <Card key={a.name}>
              <CardBody>
                <div className="flex items-center gap-2">
                  <span className="rounded-lg bg-accent-soft p-2">
                    <a.icon className="h-4 w-4 text-accent" />
                  </span>
                  <h4 className="text-sm font-semibold">{a.name}</h4>
                </div>
                <p className="mt-3 text-xs leading-relaxed text-ink-dim">{a.does}</p>
                <p className="mt-2 border-t border-edge pt-2 text-[11px] leading-snug text-good">
                  → {a.gives}
                </p>
              </CardBody>
            </Card>
          ))}
        </div>
      </section>

      {/* Platform features */}
      <section>
        <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-ink-dim">
          Built for people, not just data scientists
        </h3>
        <div className="grid gap-4 md:grid-cols-3">
          {FEATURES.map((f) => (
            <div key={f.title} className="rounded-xl border border-edge bg-panel-2/50 px-4 py-3.5">
              <div className="flex items-center gap-2">
                <f.icon className="h-4 w-4 text-warn" />
                <h4 className="text-xs font-semibold">{f.title}</h4>
              </div>
              <p className="mt-1.5 text-[11px] leading-relaxed text-ink-dim">{f.text}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Recent runs */}
      {recentRuns.length > 0 && (
        <section>
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-ink-dim">
            This session's analyses
          </h3>
          <Card>
            <CardBody className="divide-y divide-edge/60 p-0">
              {recentRuns.map((r) => (
                <button
                  key={r.id}
                  onClick={() => onResume(r.id)}
                  className="flex w-full items-center justify-between px-5 py-3 text-left transition-colors hover:bg-panel-2/60"
                >
                  <div>
                    <div className="text-sm font-medium">{r.filename}</div>
                    <div className="text-[11px] text-ink-dim">
                      {r.question || "no question set"}
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <Badge tone={r.stage === "interpret" || r.stage === "compare" ? "good" : "warn"}>
                      {r.stage}
                    </Badge>
                    <ArrowRight className="h-4 w-4 text-ink-dim" />
                  </div>
                </button>
              ))}
            </CardBody>
          </Card>
        </section>
      )}
    </div>
  );
}
