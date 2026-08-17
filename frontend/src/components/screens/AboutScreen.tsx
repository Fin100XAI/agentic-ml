// Platform guide: a self-contained presentation/reference page for new users
// and evaluators - what the platform is, how a decision gets made, what it
// can answer, and why it can be trusted. Written for a government audience.
import {
  Activity,
  BarChart3,
  Bot,
  CheckCircle2,
  Columns3,
  FileSearch,
  FileUp,
  Gauge,
  GitCompareArrows,
  Inbox,
  Landmark,
  LineChart,
  Lock,
  ScrollText,
  Shield,
  ShieldCheck,
  SlidersHorizontal,
  Target,
  Users,
} from "lucide-react";
import { Badge, Card, CardBody } from "../ui";

const PILLARS = [
  {
    icon: Lock,
    title: "Privacy before analysis",
    text: "Personal data - mobile numbers, Aadhaar-like IDs, PAN, names, addresses - is detected and masked or dropped BEFORE any analysis or AI call. No model and no AI ever sees unscreened records.",
  },
  {
    icon: ShieldCheck,
    title: "Numbers computed, never guessed",
    text: "Every figure is calculated deterministically in code. The AI only explains and phrases - it cannot invent a number. Each output is badged AI or heuristic so you always know the source.",
  },
  {
    icon: CheckCircle2,
    title: "An officer approves every step",
    text: "Agents propose; nothing runs without your approval - data fixes, the analysis approach, model settings, engineered features, decision thresholds. Authority stays with the human.",
  },
  {
    icon: ScrollText,
    title: "An audit trail fit for review",
    text: "Every upload, AI call, approval, decline, transformation, training job and export is logged with who, what and when. Original files are stored read-only with a content hash - nothing is ever overwritten.",
  },
];

const STEPS = [
  { icon: FileUp, title: "Upload", text: "A CSV or Excel file - multi-sheet workbooks can be combined in one click." },
  { icon: Columns3, title: "Check columns", text: "Fix cryptic headers before analysis; originals stay untouched." },
  { icon: Shield, title: "Privacy screen", text: "Personal data is masked or dropped before anything else runs." },
  { icon: FileSearch, title: "Explore", text: "The AI profiles the data, explains it in plain language, and proposes questions worth asking." },
  { icon: Bot, title: "Approve the approach", text: "A recommended method with settings computed from your data; leakage risks flagged for your decision." },
  { icon: BarChart3, title: "Train + verify", text: "The model trains, then honesty checks run: stability, probability quality, error slices." },
  { icon: Landmark, title: "Decision brief", text: "Findings, recommended actions and an honest trust rating - reviewed by a critic AI before you see it." },
  { icon: Activity, title: "Operate", text: "Score new files, watch for drift, test what-if scenarios, and let the intake inbox queue recurring work." },
];

const USE_CASES = [
  {
    icon: Users,
    title: "Who needs attention?",
    kind: "Classification",
    example: "Which beneficiaries are at risk of dropping out of a scheme? Which applications need senior review?",
  },
  {
    icon: Target,
    title: "How much will it be?",
    kind: "Regression",
    example: "Estimate property valuations, expected collections per ward, or likely claim amounts.",
  },
  {
    icon: GitCompareArrows,
    title: "What groups exist?",
    kind: "Clustering",
    example: "Segment citizens, villages or facilities into natural groups so schemes can be targeted, not blanket.",
  },
  {
    icon: LineChart,
    title: "Where is it heading?",
    kind: "Forecasting",
    example: "Project revenue collections, service demand or supply needs - per district, per facility, with honest uncertainty.",
  },
];

const LIFECYCLE = [
  { icon: Landmark, title: "Model registry", text: "Every trained model is a numbered version with its purpose, exact data fingerprint, settings and scores. Retraining creates the next version - nothing is overwritten." },
  { icon: Target, title: "Score new files", text: "Drop next month's file on a registered model: columns match automatically (even renamed ones), the training-time preparation replays exactly, and every row gets a prediction." },
  { icon: Activity, title: "Drift monitor", text: "Is the new data still like the training data? Distribution shifts per column, and real accuracy decay when outcomes are included - degraded is only said when accuracy actually fell." },
  { icon: SlidersHorizontal, title: "What-if scenarios", text: "Move a driver from its observed baseline and see how the prediction responds - with extrapolation warnings and a standing correlation-is-not-causation caveat." },
  { icon: Gauge, title: "Decision threshold", text: "For yes/no predictions, a slider shows the trade-off between missed cases and false alarms on cross-validated numbers; the threshold you approve is what scoring uses." },
  { icon: Inbox, title: "Intake inbox", text: "Standing rules recognize recurring files and queue score / drift-check / retrain proposals. Approve executes, decline discards - nothing ever auto-runs." },
];

const AGENTS = [
  ["EDA agent", "reads and explains your dataset"],
  ["Recommendation agent", "picks the method and checks your question fits the data"],
  ["Remediation agent", "phrases the data-fix proposals"],
  ["Feature agent", "suggests derived measures worth adding"],
  ["Interpretation agent", "judges how well the model did"],
  ["Brief agent", "writes the decision brief to the evidence level"],
  ["Critic agent", "reviews the brief against the computed numbers before you see it"],
  ["Ask-the-data agent", "answers follow-up questions from the run's own facts"],
  ["Compare summarizer", "explains the model leaderboard"],
];

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-accent">{children}</h3>
  );
}

export function AboutScreen({ onStart }: { onStart?: () => void }) {
  return (
    <div className="mx-auto max-w-5xl space-y-12 pb-12">
      {/* Hero */}
      <div className="rounded-2xl border border-edge bg-gradient-to-b from-accent-soft/25 via-panel to-panel px-8 py-12 text-center shadow-sm">
        <p className="text-xs font-bold uppercase tracking-[0.18em] text-accent">Platform guide</p>
        <h2 className="mx-auto mt-3 max-w-3xl text-3xl font-bold leading-tight">
          Decision support for government,
          <span className="text-accent"> with accountability built in.</span>
        </h2>
        <p className="mx-auto mt-4 max-w-2xl text-sm leading-relaxed text-ink-dim">
          The Agentic ML Workbench turns departmental data - scheme enrollments, revenue
          collections, service requests, demand histories - into decision briefs an officer
          can act on and defend. A team of AI agents does the analytical legwork; machine
          learning computes every number; the officer approves every step; and everything
          lands on an audit trail. No data-science background required.
        </p>
      </div>

      {/* Trust pillars */}
      <section>
        <SectionLabel>Why a government can trust it</SectionLabel>
        <div className="grid gap-4 md:grid-cols-2">
          {PILLARS.map((p) => (
            <Card key={p.title}>
              <CardBody>
                <div className="flex items-center gap-2.5">
                  <span className="rounded-lg bg-accent-soft p-2">
                    <p.icon className="h-4 w-4 text-accent" />
                  </span>
                  <h4 className="text-sm font-semibold">{p.title}</h4>
                </div>
                <p className="mt-3 text-xs leading-relaxed text-ink-dim">{p.text}</p>
              </CardBody>
            </Card>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section>
        <SectionLabel>How a decision gets made</SectionLabel>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {STEPS.map((s, i) => (
            <div key={s.title} className="rounded-xl border border-edge bg-panel p-4 shadow-sm">
              <div className="flex items-center gap-2">
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent text-[11px] font-bold text-white">
                  {i + 1}
                </span>
                <s.icon className="h-4 w-4 text-accent" />
                <h4 className="text-sm font-semibold">{s.title}</h4>
              </div>
              <p className="mt-2 text-[11px] leading-relaxed text-ink-dim">{s.text}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Use cases */}
      <section>
        <SectionLabel>The questions it can answer</SectionLabel>
        <div className="grid gap-4 md:grid-cols-2">
          {USE_CASES.map((u) => (
            <Card key={u.title}>
              <CardBody>
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2.5">
                    <span className="rounded-lg bg-accent-soft p-2">
                      <u.icon className="h-4 w-4 text-accent" />
                    </span>
                    <h4 className="text-sm font-semibold">{u.title}</h4>
                  </div>
                  <Badge tone="accent">{u.kind}</Badge>
                </div>
                <p className="mt-3 text-xs leading-relaxed text-ink-dim">{u.example}</p>
              </CardBody>
            </Card>
          ))}
        </div>
      </section>

      {/* Lifecycle */}
      <section>
        <SectionLabel>After the first analysis</SectionLabel>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {LIFECYCLE.map((l) => (
            <Card key={l.title}>
              <CardBody>
                <div className="flex items-center gap-2">
                  <l.icon className="h-4 w-4 text-accent" />
                  <h4 className="text-sm font-semibold">{l.title}</h4>
                </div>
                <p className="mt-2 text-[11px] leading-relaxed text-ink-dim">{l.text}</p>
              </CardBody>
            </Card>
          ))}
        </div>
      </section>

      {/* Agents + honesty */}
      <section className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardBody>
            <SectionLabel>The AI team</SectionLabel>
            <ul className="space-y-1.5">
              {AGENTS.map(([name, does]) => (
                <li key={name} className="flex items-baseline gap-2 text-xs">
                  <span className="w-44 shrink-0 font-semibold">{name}</span>
                  <span className="text-ink-dim">{does}</span>
                </li>
              ))}
            </ul>
            <p className="mt-3 border-t border-edge pt-3 text-[11px] leading-relaxed text-ink-dim">
              Every agent has a rule-based fallback, so the platform keeps working with no
              AI connection at all - outputs are simply badged heuristic instead of AI.
              Heuristic mode is a visible state, never a silent one.
            </p>
          </CardBody>
        </Card>
        <Card>
          <CardBody>
            <SectionLabel>Honest by design</SectionLabel>
            <ul className="space-y-2.5 text-xs leading-relaxed text-ink-dim">
              <li>
                <span className="font-semibold text-ink">Trust ratings, not just scores.</span>{" "}
                Every brief carries an evidence rating; when the evidence is weak, recommended
                actions are reframed as hypotheses to verify - in the app, the report and the PDF.
              </li>
              <li>
                <span className="font-semibold text-ink">Cross-validated numbers.</span>{" "}
                Headline metrics and decision thresholds are measured on data the model never
                saw during training - the honest version, marked cross-validated.
              </li>
              <li>
                <span className="font-semibold text-ink">A critic reviews every brief.</span>{" "}
                Claims are checked against the computed numbers and hedged before you read them,
                with correlation-is-not-causation caveats where they belong.
              </li>
              <li>
                <span className="font-semibold text-ink">Honest refusals.</span>{" "}
                Too little data? The check says skipped and why. A column that gives the answer
                away? Flagged, and anything derived from it is blocked. Probabilities that cannot
                be read literally? The brief says so.
              </li>
            </ul>
          </CardBody>
        </Card>
      </section>

      {/* Footer / status */}
      <div className="rounded-xl border border-edge bg-panel-2 px-6 py-5 text-center">
        <p className="text-xs leading-relaxed text-ink-dim">
          This is a proof of concept running locally: single user, no login, data never leaves
          this machine. Production hardening (roles and sign-in, on-premise or air-gapped
          deployment, Postgres, backups) is the planned next phase. Sample datasets are included
          - every feature on this page can be demonstrated with them.
        </p>
        {onStart && (
          <button
            onClick={onStart}
            className="mt-4 inline-flex items-center gap-2 rounded-lg bg-accent px-5 py-2 text-sm font-medium text-white shadow-sm transition-all hover:bg-accent/90 active:scale-[0.98]"
          >
            Start a new analysis
          </button>
        )}
      </div>
    </div>
  );
}
