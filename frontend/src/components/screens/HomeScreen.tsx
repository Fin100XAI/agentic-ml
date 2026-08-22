// Landing screen: what the platform can do, its agents, models, and past runs.
// Motion: staggered hero entrance on load, scroll reveals per section, hover
// lifts on cards - all transform/opacity, strong ease-out, reduced-motion safe.
import { useState } from "react";
import {
  ArrowRight,
  BarChart3,
  Bot,
  FileUp,
  GitCompareArrows,
  LineChart,
  Lock,
  Play,
  ScrollText,
  Library as LibraryIcon,
  Search,
  Settings2,
  ShieldCheck,
  Target,
  UserCheck,
  Users,
  Wand2,
} from "lucide-react";
import type { RegistryEntry, RunSummary } from "../../types";
import { DatasetsPanel } from "../DatasetsPanel";
import { GlossaryManager } from "../GlossaryManager";
import { IndicatorsPanel } from "../IndicatorsPanel";
import { IntakePanel } from "../IntakePanel";
import { ModelsPanel } from "../ModelsPanel";
import { Reveal } from "../Reveal";
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

// The trust points, as a scannable row instead of a wall of text.
const ASSURANCES = [
  { icon: Lock, label: "Personal data screened first" },
  { icon: ShieldCheck, label: "Every number computed, never guessed" },
  { icon: UserCheck, label: "Nothing runs without your approval" },
  { icon: ScrollText, label: "Every action on the audit trail" },
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

// Section opener in the Maha AI idiom: saffron eyebrow, serif head, gold
// rule. SectionLabel stays as it is for the rest of the app.
function MahaHeading({ eyebrow, title, sub }: { eyebrow: string; title: string; sub?: string }) {
  return (
    <div className="mb-6">
      <p className="maha-eyebrow">{eyebrow}</p>
      <h3 className="maha-rule mt-2 text-2xl text-ink md:text-[28px]">{title}</h3>
      {sub && <p className="mt-4 max-w-2xl text-sm leading-relaxed text-ink-dim">{sub}</p>}
    </div>
  );
}

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
  onPrep,
  onLibrary,
  projectSlot,
}: {
  recentRuns: RunSummary[];
  projectName?: string;
  projectId?: string;
  onStart: () => void;
  onPrep?: () => void;
  onLibrary?: () => void;
  /** The project chooser, shown on the landing page when nothing is open.
   *  Passed in rather than imported so this screen stays presentational. */
  projectSlot?: React.ReactNode;
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
      {/* Hero: a navy band on paper, the way the Maha AI sections alternate.
          Tokens flip inside .maha-band, so everything below paints itself. */}
      <div className="maha-band relative overflow-hidden rounded-2xl border border-edge px-8 py-16 text-center">
        <div
          aria-hidden
          className="pointer-events-none absolute -top-24 left-1/2 h-56 w-[38rem] -translate-x-1/2 rounded-full opacity-25 blur-3xl"
          style={{ backgroundImage: "var(--maha-grad)" }}
        />
        <p className="maha-eyebrow animate-rise">
          Agentic ML Workbench{projectName ? ` · ${projectName}` : ""}
        </p>
        <h2 className="maha-display animate-rise mx-auto mt-5 max-w-3xl text-balance text-4xl [animation-delay:60ms] md:text-5xl">
          Evidence for every decision.{" "}
          <span className="maha-gold-text">Accountability at every step.</span>
        </h2>
        <p className="animate-rise mx-auto mt-6 max-w-2xl text-pretty text-[15px] leading-relaxed text-ink-dim [animation-delay:120ms]">
          Decision support built for government. Upload departmental data - scheme
          enrollments, revenue collections, service requests, demand histories - and
          choose your direction: ask questions in plain language and get charted,
          mapped answers in seconds, or train a model for predictions with a decision
          brief an officer can act on and defend.
        </p>
        <div className="animate-rise mx-auto mt-7 flex max-w-3xl flex-wrap items-center justify-center gap-x-6 gap-y-2 [animation-delay:180ms]">
          {ASSURANCES.map((a) => (
            <span key={a.label} className="flex items-center gap-1.5 text-xs text-ink-dim">
              <a.icon className="h-3.5 w-3.5 text-accent" />
              {a.label}
            </span>
          ))}
        </div>
        {/* With no project open the work cannot start yet, so the hero
            points at the chooser below instead of offering dead buttons. */}
        <div className="animate-rise mt-8 flex flex-wrap items-center justify-center gap-3 [animation-delay:240ms]">
          {!projectId ? (
            <a
              href="#choose-project"
              className="maha-cta inline-flex items-center gap-2 rounded-full px-7 py-3 text-[13px] uppercase tracking-[0.12em] transition-transform duration-200 hover:-translate-y-0.5"
            >
              Choose a project to begin <ArrowRight className="h-4 w-4" />
            </a>
          ) : (
            <button
              onClick={onStart}
              className="maha-cta inline-flex items-center gap-2 rounded-full px-7 py-3 text-[13px] uppercase tracking-[0.12em] transition-transform duration-200 hover:-translate-y-0.5"
            >
              Start a new analysis <ArrowRight className="h-4 w-4" />
            </button>
          )}
          {projectId && onPrep && (
            <button
              onClick={onPrep}
              className="inline-flex items-center gap-2 rounded-full border border-edge px-6 py-3 text-[13px] uppercase tracking-[0.12em] text-ink transition-colors hover:border-edge-strong"
            >
              <Wand2 className="h-4 w-4" /> Prepare a messy file
            </button>
          )}
          {projectId && onLibrary && (
            <button
              onClick={onLibrary}
              className="inline-flex items-center gap-2 rounded-full border border-edge px-6 py-3 text-[13px] uppercase tracking-[0.12em] text-ink transition-colors hover:border-edge-strong"
            >
              <LibraryIcon className="h-4 w-4" /> Library
            </button>
          )}
        </div>

        {/* Mini pipeline */}
        <div className="animate-rise mt-10 flex flex-wrap items-center justify-center gap-2 [animation-delay:300ms]">
          {PIPELINE.map((p, i) => (
            <div key={p.label} className="flex items-center gap-2">
              {i > 0 && <div className="h-px w-5 bg-edge" />}
              <div className="flex items-center gap-1.5 rounded-full border border-edge bg-panel px-3.5 py-1.5 text-[11px] text-ink-dim">
                <span className="maha-figure text-[10px] font-semibold text-accent">{i + 1}</span>
                <p.icon className="h-3.5 w-3.5 text-accent" />
                {p.label}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Pick the project first: everything else on this page is about what
          the platform does, but nothing can be uploaded or explored until
          the work has somewhere to live. */}
      {!projectId && projectSlot && (
        <section id="choose-project" className="scroll-mt-24">
          <MahaHeading
            eyebrow="Start here"
            title="Choose a project"
            sub="A project holds related datasets, analyses, models and their audit trail together. Open an existing one, or create a new one."
          />
          {projectSlot}
        </section>
      )}

      {/* The questions it can answer - no algorithm names on the landing page;
          the recommendation agent picks the method behind the scenes. */}
      <Reveal>
        <section>
          <MahaHeading
            eyebrow="Applications"
            title="The questions you can answer"
          />
          <div data-cascade className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {QUESTIONS.map((q) => (
              <Card key={q.title} className="tile">
                <CardBody>
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2.5">
                      <span className="tile-icon rounded-lg bg-accent/10 p-2 ring-1 ring-inset ring-accent/25">
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
      </Reveal>

      {/* Agents */}
      <Reveal>
        <section>
          <MahaHeading eyebrow="The agents" title="Meet your agents" />
          <div data-cascade className="grid grid-cols-1 gap-4 md:grid-cols-3">
            {AGENTS.map((a) => (
              <Card key={a.name} className="tile">
                <CardBody>
                  <div className="flex items-center gap-2">
                    <span className="tile-icon rounded-lg bg-accent/10 p-2 ring-1 ring-inset ring-accent/25">
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
      </Reveal>

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
            <div>
              <p className="maha-eyebrow">This session</p>
              <h3 className="mt-1.5 text-xl text-ink">Analyses you have run</h3>
            </div>
            {completedRuns.length >= 2 && (
              <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-ink-dim">
                <GitCompareArrows className="h-3.5 w-3.5" />
                Compare
                <select
                  value={diffA}
                  onChange={(e) => setDiffA(e.target.value)}
                  className="max-w-40 rounded-lg border border-edge bg-panel-2 px-2 py-1 text-[11px]"
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
                  className="max-w-40 rounded-lg border border-edge bg-panel-2 px-2 py-1 text-[11px]"
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
                  className="group flex w-full items-center justify-between px-5 py-3 text-left transition-colors hover:bg-panel-2/60"
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
                    <ArrowRight className="h-4 w-4 text-ink-dim transition-transform duration-200 group-hover:translate-x-0.5" />
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
