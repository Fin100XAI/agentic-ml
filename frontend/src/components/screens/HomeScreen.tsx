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
import { GlossaryManager } from "../GlossaryManager";
import { IntakePanel } from "../IntakePanel";
import { ModelsPanel } from "../ModelsPanel";
import { RunDiffModal } from "../RunDiffModal";
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

// The four kinds of analysis, framed as the questions an administrator
// actually asks - no algorithm names on the landing page.
const QUESTIONS = [
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
    icon: GitCompareArrows,
    title: "What groups exist?",
    kind: "Discover segments",
    example: "Segment citizens, villages or facilities into natural groups so schemes can be targeted, not blanket.",
  },
  {
    icon: LineChart,
    title: "Where is it heading?",
    kind: "Project the future",
    example: "Project revenue collections, service demand or supply needs - per district, with honest uncertainty.",
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
}: {
  recentRuns: RunSummary[];
  projectName?: string;
  projectId?: string;
  onStart: () => void;
  onResume: (id: string) => void;
  onRetrain?: (entry: RegistryEntry, datasetId: string) => void;
  onOpenRetrainRun?: (runId: string, prefill: { model_key: string; hyperparams: Record<string, unknown>; target: string | null }) => void;
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
          receive a brief an officer can act on and defend: what drives outcomes,
          which groups need attention, where things are heading. Personal data is
          screened before any analysis, every number is computed - never guessed -
          nothing runs without your approval, and every action lands on an audit
          trail fit for review.
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
          Bring the question - the recommendation agent picks the right analysis method from
          your data and explains its choice. You approve before anything runs.
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
