// Landing screen: what the platform can do, its agents, models, and past runs.
import { useState } from "react";
import {
  ArrowRight,
  BarChart3,
  Bot,
  FileUp,
  GitCompareArrows,
  LineChart,
  Play,
  Search,
  Settings2,
  Target,
  Users,
} from "lucide-react";
import type { RegistryEntry, RunSummary } from "../../types";
import { DatasetsPanel } from "../DatasetsPanel";
import { GlossaryManager } from "../GlossaryManager";
import { IndicatorsPanel } from "../IndicatorsPanel";
import { IntakePanel } from "../IntakePanel";
import { ModelsPanel } from "../ModelsPanel";
import { RunDiffModal } from "../RunDiffModal";
import { Badge, Button, Card, CardBody } from "../ui";

const AGENTS = [
  {
    name: "Exploring Agents",
    icon: Search,
    does: "Scan every upload, catch place names spelled differently, and answer the first questions themselves - leaders and laggards, trends, year-on-year changes - as charted findings with plain-language meaning.",
    gives: "A findings board before you type a single question.",
  },
  {
    name: "Query Planner + Analyst",
    icon: Bot,
    does: "Turns your plain-language question into a visible step-by-step plan you approve before it runs; the analyst explains what each answer means - in English, Hindi or Marathi - and a critic checks every claim in every brief.",
    gives: "Charted, mapped, defensible answers in seconds.",
  },
  {
    name: "Modeling Agents",
    icon: BarChart3,
    does: "Recommend the right method for prediction questions, flag leakage and data risks, train with honesty checks on unseen data, and judge the results.",
    gives: "A decision brief with a trust rating you can act on.",
  },
];

const PIPELINE = [
  { icon: FileUp, label: "Upload the file" },
  { icon: Search, label: "Agents screen + explore" },
  { icon: Settings2, label: "You choose the direction" },
  { icon: Play, label: "Ask directly, or train a model" },
  { icon: BarChart3, label: "Charted answers + briefs" },
];

// Framed as the questions an administrator actually asks - no algorithm
// names on the landing page. The first two are answered in seconds on the
// ask path; the rest go down the model path.
const QUESTIONS = [
  {
    icon: Search,
    title: "What does the data say?",
    kind: "Answered in seconds",
    example: "Top and bottom districts, totals and averages, month-by-month movement, shares per scheme - charted, mapped, and explained the moment you upload.",
  },
  {
    icon: Users,
    title: "Who needs attention?",
    kind: "Sort into groups",
    example: "Which beneficiaries are at risk of dropping out of a scheme? Which applications need senior review?",
  },
  {
    icon: Target,
    title: "How much will it be?",
    kind: "Estimate an amount",
    example: "Estimate property valuations, expected collections per ward, or likely claim amounts.",
  },
  {
    icon: LineChart,
    title: "Where is it heading?",
    kind: "Project the future",
    example: "Project revenue collections, service demand or supply needs - per district, with honest uncertainty. Natural groups in the data surface along the way.",
  },
];

export function HomeScreen({
  recentRuns,
  projectName,
  projectId,
  onStart,
  onResume,
  onRetrain,
  onOpenRetrainRun,
  onExploreDataset,
  onAskDataset,
}: {
  recentRuns: RunSummary[];
  projectName?: string;
  projectId?: string;
  onStart: () => void;
  onResume: (id: string) => void;
  onRetrain?: (entry: RegistryEntry, datasetId: string) => void;
  onOpenRetrainRun?: (runId: string, prefill: { model_key: string; hyperparams: Record<string, unknown>; target: string | null }) => void;
  onExploreDataset?: (datasetId: string, filename: string) => void;
  onAskDataset?: (datasetId: string, filename: string) => void;
}) {
  const completedRuns = recentRuns.filter((r) => r.stage === "interpret" || r.stage === "compare");
  const [diffA, setDiffA] = useState("");
  const [diffB, setDiffB] = useState("");
  const [diffOpen, setDiffOpen] = useState(false);

  return (
    <div className="space-y-10">
      {/* Hero */}
      <div className="rounded-2xl border border-edge bg-gradient-to-b from-accent-soft/25 via-panel to-panel px-8 py-14 text-center shadow-sm">
        <p className="text-xs font-bold uppercase tracking-[0.18em] text-accent">
          Agentic ML Workbench{projectName ? ` · ${projectName}` : ""}
        </p>
        <h2 className="mx-auto mt-3 max-w-2xl text-3xl font-bold leading-tight">
          Evidence for every decision.
          <span className="text-accent"> Accountability at every step.</span>
        </h2>
        <p className="mx-auto mt-3 max-w-2xl text-sm leading-relaxed text-ink-dim">
          Decision support built for government. Upload departmental data - scheme
          enrollments, revenue collections, service requests, demand histories - and
          choose your direction: ask questions in plain language and get charted,
          mapped answers in seconds, or train a model for predictions with a decision
          brief an officer can act on and defend. Personal data is screened before
          any analysis, every number is computed - never guessed - nothing runs
          without your approval, and every action lands on an audit trail fit for
          review.
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

      {/* The questions it can answer - no algorithm names on the landing page;
          the recommendation agent picks the method behind the scenes. */}
      <section>
        <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-accent">
          The questions you can answer
        </h3>
        <div className="grid gap-4 md:grid-cols-2">
          {QUESTIONS.map((q) => (
            <Card key={q.title} className="transition-colors hover:border-accent/50">
              <CardBody>
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2.5">
                    <span className="rounded-lg bg-accent-soft p-2">
                      <q.icon className="h-4 w-4 text-accent" />
                    </span>
                    <h4 className="text-sm font-semibold">{q.title}</h4>
                  </div>
                  <Badge tone="accent">{q.kind}</Badge>
                </div>
                <p className="mt-3 text-xs leading-relaxed text-ink-dim">{q.example}</p>
              </CardBody>
            </Card>
          ))}
        </div>
        <p className="mt-2.5 text-[11px] text-ink-dim">
          Bring the question - or none at all. Lookups are answered directly from the data;
          prediction questions get the right method recommended and explained. Either way,
          you approve before anything runs.
        </p>
      </section>

      {/* Agents */}
      <section>
        <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-accent">
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

      {/* Project data dictionary */}
      {/* Your data: direct re-entry into any file's board or Ask thread */}
      {projectId && onExploreDataset && onAskDataset && (
        <DatasetsPanel
          projectId={projectId}
          onExplore={onExploreDataset}
          onAsk={onAskDataset}
        />
      )}

      {/* Saved-query indicators (P2.5) - the project's auto-dashboard */}
      {projectId && <IndicatorsPanel projectId={projectId} />}

      {projectId && <GlossaryManager projectId={projectId} />}

      {/* Trained model versions in this project */}
      {projectId && <ModelsPanel projectId={projectId} onRetrain={onRetrain} />}

      {/* Standing intake rules + approval inbox */}
      {projectId && <IntakePanel projectId={projectId} onOpenRetrainRun={onOpenRetrainRun} />}

      {/* Recent runs */}
      {recentRuns.length > 0 && (
        <section>
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-sm font-semibold uppercase tracking-wider text-accent">
              This session's analyses
            </h3>
            {completedRuns.length >= 2 && (
              <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-ink-dim">
                <GitCompareArrows className="h-3.5 w-3.5" />
                Compare
                <select
                  value={diffA}
                  onChange={(e) => setDiffA(e.target.value)}
                  className="max-w-40 rounded-lg border border-edge bg-white/60 px-2 py-1 text-[11px]"
                >
                  <option value="">earlier run…</option>
                  {completedRuns.map((r) => (
                    <option key={r.id} value={r.id}>{r.filename.slice(0, 28)} · {r.id.slice(0, 6)}</option>
                  ))}
                </select>
                <span>vs</span>
                <select
                  value={diffB}
                  onChange={(e) => setDiffB(e.target.value)}
                  className="max-w-40 rounded-lg border border-edge bg-white/60 px-2 py-1 text-[11px]"
                >
                  <option value="">later run…</option>
                  {completedRuns.map((r) => (
                    <option key={r.id} value={r.id}>{r.filename.slice(0, 28)} · {r.id.slice(0, 6)}</option>
                  ))}
                </select>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={!diffA || !diffB || diffA === diffB}
                  onClick={() => setDiffOpen(true)}
                >
                  What changed?
                </Button>
              </div>
            )}
          </div>
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

      {diffOpen && diffA && diffB && (
        <RunDiffModal runA={diffA} runB={diffB} onClose={() => setDiffOpen(false)} />
      )}
    </div>
  );
}
