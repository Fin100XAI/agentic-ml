// Platform guide: a presentation-grade page for demos and new users - what
// the platform is, how it works (visual flows), and why it can be trusted.
// Written for a government audience; readable by tech and non-tech alike.
// Visual language: Maha AI sovereign style (mahaai.fin100x.ai) - deep navy
// hero bands, gold authority accents and card rails, saffron CTAs, serif
// headings, white cards on hairline borders. Judgment colors (green/amber/
// red) stay reserved for judgment states. Motion: staggered hero entrance,
// scroll reveals with a 50ms cascade - transform/opacity, reduced-motion safe.
import {
  Activity,
  Bot,
  CheckCircle2,
  Columns3,
  Database,
  FileCheck2,
  FileUp,
  Gauge,
  GitCompareArrows,
  Inbox,
  Landmark,
  LineChart,
  Lock,
  MonitorSmartphone,
  ScrollText,
  Server,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Target,
  UserCheck,
  Users,
} from "lucide-react";
import { Reveal } from "../Reveal";

/* ---------- content ---------- */

const STATS = [
  { value: "2", label: "ways to work" },
  { value: "12", label: "models on tap" },
  { value: "14", label: "AI agents" },
  { value: "100%", label: "of actions logged" },
  { value: "0", label: "numbers invented by AI" },
];

const PILLARS = [
  {
    icon: Lock,
    title: "Privacy before analysis",
    text: "Personal data - mobile numbers, Aadhaar-like IDs, PAN, names, addresses - is detected and masked or dropped BEFORE any analysis or AI call ever sees a row.",
  },
  {
    icon: ShieldCheck,
    title: "Numbers computed, never guessed",
    text: "Every figure is calculated deterministically in code. The AI only explains and phrases - it cannot invent a number. Each output is badged AI or heuristic.",
  },
  {
    icon: CheckCircle2,
    title: "An officer approves every step",
    text: "Agents propose; nothing runs without approval - data fixes, the approach, settings, features, thresholds. Authority stays with the human.",
  },
  {
    icon: ScrollText,
    title: "An audit trail fit for review",
    text: "Every upload, AI call, approval, decline, transformation, training job and export is logged. Originals are stored read-only with a content hash.",
  },
];

// The working rhythm: who does what, in order. actor: ai | you | machine
const FLOW: { actor: "ai" | "you" | "machine"; title: string; text: string; icon: any }[] = [
  { actor: "you", icon: FileUp, title: "Upload the file", text: "CSV or Excel - multi-sheet workbooks combine in one click." },
  { actor: "you", icon: Columns3, title: "Approve column names", text: "Fix cryptic headers; the original file stays untouched." },
  { actor: "machine", icon: Lock, title: "Privacy screen runs", text: "Personal data flagged; you choose mask / drop / keep per column." },
  { actor: "ai", icon: Bot, title: "Agents explore + propose", text: "The data explained in plain language; fixes and questions proposed; leakage risks flagged." },
  { actor: "you", icon: UserCheck, title: "Approve the approach", text: "Pick the recommended method or adjust; tick fixes and features; answer each leakage flag." },
  { actor: "machine", icon: Gauge, title: "Train + honesty checks", text: "The model trains; stability, probability quality and error slices are measured on data it never saw." },
  { actor: "ai", icon: Sparkles, title: "Brief drafted, critic reviews", text: "Findings and actions written to the evidence level; a critic AI checks every claim against the numbers." },
  { actor: "you", icon: Landmark, title: "Decide - with cover", text: "Act on a brief you can defend: trust rating, caveats, and the full audit trail behind it." },
];

const LINEAGE = [
  { icon: FileUp, label: "Original file", note: "read-only + hash" },
  { icon: Columns3, label: "Approved names", note: "rename artifact" },
  { icon: Lock, label: "Privacy mask", note: "PII artifact" },
  { icon: FileCheck2, label: "Approved fixes", note: "remediation artifact" },
  { icon: Sparkles, label: "Engineered features", note: "feature artifact" },
  { icon: Landmark, label: "Trained model", note: "versioned, never overwritten" },
  { icon: Target, label: "Predictions", note: "score artifact" },
];

const USE_CASES = [
  { icon: Users, title: "Who needs attention?", kind: "Classification", example: "Which beneficiaries are at risk of dropping out of a scheme? Which applications need senior review?" },
  { icon: Target, title: "How much will it be?", kind: "Regression", example: "Estimate property valuations, expected collections per ward, or likely claim amounts." },
  { icon: GitCompareArrows, title: "What groups exist?", kind: "Clustering", example: "Segment citizens, villages or facilities into natural groups so schemes can be targeted, not blanket." },
  { icon: LineChart, title: "Where is it heading?", kind: "Forecasting", example: "Project revenue collections, service demand or supply needs - per district, with honest uncertainty." },
];

const LIFECYCLE = [
  { icon: Landmark, title: "Model registry", text: "Every trained model is a numbered version with its purpose, data fingerprint, settings and scores." },
  { icon: Target, title: "Score new files", text: "Next month's file gets predictions through the exact training-time preparation - even with renamed columns." },
  { icon: Activity, title: "Drift monitor", text: "Is new data still like the training data? Degraded is only said when accuracy actually fell." },
  { icon: SlidersHorizontal, title: "What-if scenarios", text: "Move a driver and watch the prediction respond - with extrapolation warnings and causal caveats." },
  { icon: Gauge, title: "Decision threshold", text: "Trade missed cases against false alarms on cross-validated numbers; your choice is what scoring uses." },
  { icon: Inbox, title: "Intake inbox", text: "Recurring files are recognized and queued for one-click review. Nothing ever auto-runs." },
];

const AGENTS = [
  ["EDA agent", "reads and explains your dataset"],
  ["Explorer agents", "ask and answer the first questions before you type anything"],
  ["Analyst agent", "explains what each finding means, in your language"],
  ["Anomaly scout", "flags values that sit far outside the rest"],
  ["Place harmonizer", "catches the same place spelled differently"],
  ["Query planner", "turns plain-language questions into typed, visible plans"],
  ["Recommendation agent", "picks the method and checks your question fits the data"],
  ["Remediation agent", "phrases the data-fix proposals"],
  ["Feature agent", "suggests derived measures worth adding"],
  ["Interpretation agent", "judges how well the model did"],
  ["Brief agent", "writes the decision brief to the evidence level"],
  ["Critic agent", "checks every claim in every brief against the computed numbers"],
  ["Ask-the-data agent", "answers follow-ups from the run's own facts"],
  ["Compare summarizer", "explains the model leaderboard"],
];

/* ---------- small building blocks ---------- */

// Section head, Maha style: gold uppercase eyebrow over a large serif title.
function GuideSection({ eyebrow, title, sub }: { eyebrow: string; title: string; sub?: string }) {
  return (
    <div className="mb-5">
      <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-gold-deep">{eyebrow}</p>
      <h3 className="font-serif mt-1 text-2xl font-semibold tracking-tight text-navy-ink md:text-3xl">
        {title}
      </h3>
      {sub && <p className="mt-2 max-w-2xl text-xs leading-relaxed text-ink-dim">{sub}</p>}
    </div>
  );
}

// White card on hairline border with the soft navy shadow; goldRail adds the
// signature gold left edge.
function MahaCard({ goldRail, className = "", children }: { goldRail?: boolean; className?: string; children: React.ReactNode }) {
  return (
    <div
      className={`lift rounded-2xl border border-hair bg-white shadow-soft ${
        goldRail ? "border-l-[3px] border-l-gold" : ""
      } ${className}`}
    >
      {children}
    </div>
  );
}

const ACTOR_STYLE = {
  ai: { dot: "bg-navy text-white", chip: "bg-navy/5 text-navy ring-navy/15", label: "AI proposes" },
  you: { dot: "bg-gold text-navy-ink", chip: "bg-gold/10 text-gold-deep ring-gold/25", label: "You decide" },
  machine: { dot: "bg-slate-400 text-white", chip: "bg-slate-500/10 text-ink-dim ring-slate-500/15", label: "Machine computes" },
} as const;

/* ---------- page ---------- */

export function AboutScreen({ onStart }: { onStart?: () => void }) {
  return (
    <div className="mx-auto max-w-5xl space-y-14 pb-12">
      {/* Hero: deep navy sovereign band + stat strip */}
      <div className="overflow-hidden rounded-2xl bg-[radial-gradient(130%_100%_at_76%_8%,#28427a_0%,#1a2e5e_44%,#13234c_100%)] shadow-soft-lg">
        <div className="px-8 py-14 text-center">
          <p className="animate-rise text-xs font-bold uppercase tracking-[0.2em] text-gold-soft">
            Platform guide
          </p>
          <h2 className="font-serif animate-rise mx-auto mt-3 max-w-3xl text-balance text-3xl font-semibold leading-tight tracking-tight text-white [animation-delay:60ms] md:text-5xl">
            Decision support for government,
            <span className="text-gold-bright"> with accountability built in.</span>
          </h2>
          <p className="animate-rise mx-auto mt-5 max-w-2xl text-pretty text-sm leading-relaxed text-mist/80 [animation-delay:120ms]">
            The Agentic ML Workbench turns departmental data - scheme enrollments, revenue
            collections, service requests, demand histories - into answers an officer can act
            on and defend. Upload a file and choose your direction: get charted answers to
            plain-language questions in seconds, or train a model for predictions. Either way,
            AI agents do the legwork, code computes every number, the officer approves every
            step, and everything lands on an audit trail.
          </p>
        </div>
        <div className="animate-rise grid grid-cols-2 divide-x divide-white/10 border-t border-white/10 bg-navy-ink/60 [animation-delay:200ms] sm:grid-cols-5">
          {STATS.map((s) => (
            <div key={s.label} className="px-3 py-4 text-center">
              <div className="font-serif text-2xl font-semibold tabular-nums text-gold-soft">{s.value}</div>
              <div className="mt-0.5 text-[10px] uppercase tracking-wider text-mist/60">{s.label}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Trust pillars */}
      <Reveal>
        <section>
          <GuideSection eyebrow="The foundations" title="Why a government can trust it" />
          <div data-cascade className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
            {PILLARS.map((p) => (
              <MahaCard key={p.title} goldRail className="p-5">
                <span className="inline-flex rounded-lg bg-navy-deep p-2">
                  <p.icon className="h-4 w-4 text-gold-soft" />
                </span>
                <h4 className="mt-2.5 text-sm font-semibold text-navy-ink">{p.title}</h4>
                <p className="mt-2 text-[11px] leading-relaxed text-ink-dim">{p.text}</p>
              </MahaCard>
            ))}
          </div>
        </section>
      </Reveal>

      {/* The fork: two ways to work */}
      <Reveal>
        <section>
          <GuideSection
            eyebrow="The fork"
            title="Two ways to work"
            sub="Every uploaded file gets the same protections - approved column names, the privacy screen, spell-check on place names - and then the officer chooses the direction. Switching later is one click; both directions share the same protected copy of the data."
          />
          <div data-cascade className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <MahaCard goldRail className="p-5">
              <div className="flex items-center gap-2.5">
                <span className="rounded-lg bg-navy-deep p-2">
                  <Sparkles className="h-4 w-4 text-gold-soft" />
                </span>
                <h4 className="text-sm font-semibold text-navy-ink">Understand & ask</h4>
                <span className="rounded-full bg-gold/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-gold-deep ring-1 ring-inset ring-gold/25">
                  answers in seconds
                </span>
              </div>
              <p className="mt-3 text-xs leading-relaxed text-ink-dim">
                Exploring agents scan the file and answer the first questions themselves -
                leaders and laggards, trends and year-on-year changes, splits and totals -
                as charted findings with plain-language meaning, in English, Hindi or
                Marathi. Then the officer takes over: every question becomes a visible
                step-by-step plan approved before it runs, follow-ups show exactly what
                changed, district results offer a map view, and selected answers compile
                into a critic-checked brief. Saved questions become dashboard indicators
                that refresh when next month's file arrives.
              </p>
            </MahaCard>
            <MahaCard className="p-5">
              <div className="flex items-center gap-2.5">
                <span className="rounded-lg bg-navy-deep p-2">
                  <Landmark className="h-4 w-4 text-gold-soft" />
                </span>
                <h4 className="text-sm font-semibold text-navy-ink">Train a model</h4>
                <span className="rounded-full bg-navy/5 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-navy ring-1 ring-inset ring-navy/15">
                  predictions with cover
                </span>
              </div>
              <p className="mt-3 text-xs leading-relaxed text-ink-dim">
                For questions about what WILL happen - who is at risk, how much to expect,
                where demand is heading - the full guided path below: health checks and
                fixes, a recommended method with honest settings, training with stability
                and probability checks on unseen data, and a decision brief with a trust
                rating a critic has already reviewed. Trained models become managed,
                versioned assets that score next month's file.
              </p>
            </MahaCard>
          </div>
        </section>
      </Reveal>

      {/* The working rhythm: timeline with actor lanes */}
      <Reveal>
        <section>
          <GuideSection
            eyebrow="The working rhythm"
            title="How a decision gets made"
            sub="The division of labor is the design: AI proposes, machines compute, and every consequential step waits for a human. Follow one file down the model path, from upload to decision - the ask path follows the same rhythm with interpret-approve-run on every question."
          />
          <div className="mb-4 flex flex-wrap items-center gap-3">
            {(Object.keys(ACTOR_STYLE) as (keyof typeof ACTOR_STYLE)[]).map((k) => (
              <span key={k} className="flex items-center gap-1.5 text-[11px] text-ink-dim">
                <span className={`h-2.5 w-2.5 rounded-full ${ACTOR_STYLE[k].dot.split(" ")[0]}`} />
                {ACTOR_STYLE[k].label}
              </span>
            ))}
          </div>
          <div className="relative">
            {/* center spine */}
            <div className="absolute bottom-4 left-4 top-1 w-px bg-gold/30 md:left-1/2" />
            <div data-cascade className="space-y-3">
              {FLOW.map((s, i) => {
                const st = ACTOR_STYLE[s.actor];
                const left = i % 2 === 0;
                return (
                  <div key={s.title} className={`relative flex md:w-1/2 ${left ? "" : "md:ml-auto"}`}>
                    {/* node on the spine */}
                    <span
                      className={`absolute top-4 z-10 flex h-8 w-8 items-center justify-center rounded-full ring-4 ring-surface ${st.dot} left-0 ${
                        left ? "md:left-auto md:right-0 md:translate-x-1/2" : "md:-translate-x-1/2"
                      }`}
                    >
                      <span className="text-[11px] font-bold">{i + 1}</span>
                    </span>
                    <div className={`ml-12 flex-1 md:ml-0 ${left ? "md:mr-8" : "md:ml-8"}`}>
                      <div className="lift rounded-xl border border-hair bg-white p-4 shadow-soft">
                        <div className="flex flex-wrap items-center gap-2">
                          <s.icon className="h-4 w-4 text-navy" />
                          <h4 className="text-sm font-semibold text-navy-ink">{s.title}</h4>
                          <span className={`ml-auto rounded-full px-2 py-0.5 text-[10px] font-medium ring-1 ring-inset ${st.chip}`}>
                            {st.label}
                          </span>
                        </div>
                        <p className="mt-1.5 text-[11px] leading-relaxed text-ink-dim">{s.text}</p>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </section>
      </Reveal>

      {/* Data lineage chain */}
      <Reveal>
        <section>
          <GuideSection
            eyebrow="Chain of custody"
            title="What happens to your data"
            sub="The original file is stored read-only with a fingerprint. Every change creates a NEW copy that points back at its parent - so any number in any brief can be traced to the exact data it came from."
          />
          <div className="rounded-2xl border border-hair bg-white p-5 shadow-soft">
            <div data-cascade className="flex flex-wrap items-center justify-center gap-y-4">
              {LINEAGE.map((l, i) => (
                <div key={l.label} className="flex items-center">
                  <div className="flex w-28 flex-col items-center text-center">
                    <span className={`flex h-10 w-10 items-center justify-center rounded-xl ${i === 0 ? "bg-navy-deep text-gold-soft" : "bg-gold/10 text-navy"}`}>
                      <l.icon className="h-4.5 w-4.5" />
                    </span>
                    <span className="mt-1.5 text-[11px] font-semibold leading-tight text-navy-ink">{l.label}</span>
                    <span className="text-[9px] uppercase tracking-wide text-ink-dim">{l.note}</span>
                  </div>
                  {i < LINEAGE.length - 1 && (
                    <svg className="mx-0.5 h-4 w-6 shrink-0 text-gold/50" viewBox="0 0 24 16" fill="none">
                      <path d="M0 8h18m0 0-5-5m5 5-5 5" stroke="currentColor" strokeWidth="1.6" />
                    </svg>
                  )}
                </div>
              ))}
            </div>
            <p className="mt-4 border-t border-hair pt-3 text-center text-[11px] text-ink-dim">
              Every arrow is a recorded step in the audit trail. Nothing is edited in place; the
              original never changes.
            </p>
          </div>
        </section>
      </Reveal>

      {/* Use cases */}
      <Reveal>
        <section>
          <GuideSection eyebrow="Applications" title="The questions it can answer" />
          <div data-cascade className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {USE_CASES.map((u) => (
              <MahaCard key={u.title} className="p-5">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2.5">
                    <span className="rounded-lg bg-navy-deep p-2">
                      <u.icon className="h-4 w-4 text-gold-soft" />
                    </span>
                    <h4 className="text-sm font-semibold text-navy-ink">{u.title}</h4>
                  </div>
                  <span className="rounded-full bg-navy/5 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-navy ring-1 ring-inset ring-navy/15">
                    {u.kind}
                  </span>
                </div>
                <p className="mt-3 text-xs leading-relaxed text-ink-dim">{u.example}</p>
              </MahaCard>
            ))}
          </div>
        </section>
      </Reveal>

      {/* What you receive: brief mockup */}
      <Reveal>
        <section>
          <GuideSection
            eyebrow="The deliverable"
            title="What you receive"
            sub="The output is not a dashboard to interpret - it is a brief to act on, with its confidence stated up front."
          />
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
            <div className="lg:col-span-3">
              {/* stylized decision brief */}
              <div className="rounded-2xl border border-hair border-l-[3px] border-l-gold bg-white p-6 shadow-soft">
                <div className="flex items-center justify-between border-b border-hair pb-3">
                  <div>
                    <p className="text-[10px] uppercase tracking-wider text-gold-deep">Decision brief</p>
                    <h4 className="font-serif text-base font-semibold text-navy-ink">
                      Which beneficiaries are at risk of dropping out?
                    </h4>
                  </div>
                  <span className="rounded-full bg-good/10 px-2.5 py-1 text-[10px] font-semibold text-good ring-1 ring-inset ring-good/20">
                    evidence: strong
                  </span>
                </div>
                <div className="mt-3 space-y-2.5">
                  <div>
                    <p className="text-[10px] font-semibold uppercase tracking-wider text-navy">Executive summary</p>
                    <div className="mt-1 space-y-1">
                      <div className="h-2 w-full rounded bg-mist" />
                      <div className="h-2 w-11/12 rounded bg-mist" />
                      <div className="h-2 w-4/5 rounded bg-mist/70" />
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-2.5">
                    <div>
                      <p className="text-[10px] font-semibold uppercase tracking-wider text-navy">Key findings</p>
                      <div className="mt-1 space-y-1">
                        <div className="h-2 w-full rounded bg-mist" />
                        <div className="h-2 w-5/6 rounded bg-mist/70" />
                        <div className="h-2 w-4/6 rounded bg-mist/70" />
                      </div>
                    </div>
                    <div>
                      <p className="text-[10px] font-semibold uppercase tracking-wider text-navy">Recommended actions</p>
                      <div className="mt-1 space-y-1">
                        <div className="h-2 w-full rounded bg-mist" />
                        <div className="h-2 w-5/6 rounded bg-mist/70" />
                        <div className="h-2 w-3/6 rounded bg-mist/70" />
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 rounded-lg border border-gold/25 bg-gold/[0.06] px-3 py-2">
                    <ShieldCheck className="h-3.5 w-3.5 shrink-0 text-gold-deep" />
                    <p className="text-[10px] leading-snug text-ink-dim">
                      Reviewed by the critic agent - claims checked against the computed numbers,
                      causal caveats added, hedged to the evidence level.
                    </p>
                  </div>
                </div>
              </div>
            </div>
            <div data-cascade className="space-y-3 lg:col-span-2">
              {[
                ["Plain language first", "Jargon lives behind info buttons; every metric has a one-line explanation."],
                ["Charts that explain themselves", "Drivers, segments, forecasts - each with a caption saying what to read off it."],
                ["Shareable + printable", "A read-only briefing link for stakeholders, plus markdown and PDF exports."],
                ["Ask the data", "A grounded chat answers follow-ups from the run's own numbers - it cannot make things up."],
              ].map(([t, d]) => (
                <div key={t} className="lift rounded-xl border border-hair bg-white p-4 shadow-soft">
                  <h5 className="text-xs font-semibold text-navy-ink">{t}</h5>
                  <p className="mt-1 text-[11px] leading-relaxed text-ink-dim">{d}</p>
                </div>
              ))}
            </div>
          </div>
        </section>
      </Reveal>

      {/* Lifecycle */}
      <Reveal>
        <section>
          <GuideSection
            eyebrow="The long run"
            title="After the first analysis"
            sub="The first analysis is the beginning, not the end - trained models become managed assets."
          />
          <div data-cascade className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {LIFECYCLE.map((l) => (
              <MahaCard key={l.title} className="p-5">
                <div className="flex items-center gap-2">
                  <l.icon className="h-4 w-4 text-navy" />
                  <h4 className="text-sm font-semibold text-navy-ink">{l.title}</h4>
                </div>
                <p className="mt-2 text-[11px] leading-relaxed text-ink-dim">{l.text}</p>
              </MahaCard>
            ))}
          </div>
        </section>
      </Reveal>

      {/* Agents + honesty */}
      <Reveal>
        <section data-cascade className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <MahaCard className="p-5">
            <GuideSection eyebrow="The workforce" title="The AI team" />
            <ul className="space-y-1.5">
              {AGENTS.map(([name, does]) => (
                <li key={name} className="flex items-baseline gap-2 text-xs">
                  <span className="w-44 shrink-0 font-semibold text-navy-ink">{name}</span>
                  <span className="text-ink-dim">{does}</span>
                </li>
              ))}
            </ul>
            <p className="mt-3 border-t border-hair pt-3 text-[11px] leading-relaxed text-ink-dim">
              Every agent has a rule-based fallback, so the platform keeps working with no AI
              connection at all - outputs are simply badged heuristic instead of AI. Heuristic
              mode is a visible state, never a silent one.
            </p>
          </MahaCard>
          <MahaCard goldRail className="p-5">
            <GuideSection eyebrow="The character" title="Honest by design" />
            <ul className="space-y-2.5 text-xs leading-relaxed text-ink-dim">
              <li>
                <span className="font-semibold text-navy-ink">Trust ratings, not just scores.</span>{" "}
                When the evidence is weak, recommended actions become hypotheses to verify - in
                the app, the report and the PDF.
              </li>
              <li>
                <span className="font-semibold text-navy-ink">Cross-validated numbers.</span>{" "}
                Headline metrics and decision thresholds are measured on data the model never saw
                during training.
              </li>
              <li>
                <span className="font-semibold text-navy-ink">A critic reviews every brief.</span>{" "}
                Claims are checked against the computed numbers before you read them.
              </li>
              <li>
                <span className="font-semibold text-navy-ink">Honest refusals.</span>{" "}
                Too little data? The check says skipped and why. A column that gives the answer
                away? Flagged, and anything derived from it is blocked.
              </li>
            </ul>
          </MahaCard>
        </section>
      </Reveal>

      {/* For the technical reader */}
      <Reveal>
        <section>
          <GuideSection
            eyebrow="Under the hood"
            title="For the technical evaluator"
            sub="The architecture is three clean tiers, and the AI is replaceable."
          />
          <div className="rounded-2xl border border-hair bg-white p-5 shadow-soft">
            <div data-cascade className="flex flex-col items-stretch gap-2 md:flex-row md:items-center">
              {[
                { icon: MonitorSmartphone, title: "React UI", sub: "TypeScript + Tailwind + Recharts", note: "screens mirror backend types" },
                { icon: Server, title: "FastAPI", sub: "REST + approval gates", note: "audit log, artifact ledger, registry" },
                { icon: Database, title: "Python engine", sub: "pandas / scikit-learn / XGBoost / statsmodels", note: "pure - no web imports; every number computed here" },
              ].map((t, i, arr) => (
                <div key={t.title} className="flex flex-1 items-center">
                  <div className="flex-1 rounded-xl bg-[radial-gradient(120%_120%_at_70%_0%,#1e355e_0%,#13234c_100%)] p-4 text-center ring-1 ring-inset ring-gold/25">
                    <t.icon className="mx-auto h-5 w-5 text-gold-soft" />
                    <h4 className="font-serif mt-1.5 text-sm font-semibold text-white">{t.title}</h4>
                    <p className="text-[11px] text-mist/70">{t.sub}</p>
                    <p className="mt-1 text-[10px] uppercase tracking-wide text-mist/50">{t.note}</p>
                  </div>
                  {i < arr.length - 1 && (
                    <svg className="mx-1 hidden h-4 w-8 shrink-0 text-gold/50 md:block" viewBox="0 0 32 16" fill="none">
                      <path d="M0 8h26m0 0-5-5m5 5-5 5M6 8l5-5M6 8l5 5" stroke="currentColor" strokeWidth="1.6" />
                    </svg>
                  )}
                </div>
              ))}
            </div>
            <div className="mt-4 flex flex-wrap justify-center gap-1.5 border-t border-hair pt-3.5">
              {[
                "SQLite (Postgres-portable)", "content-addressed artifact store", "model plugins via @register",
                "swappable LLM provider + deterministic fallbacks", "typed query plans - the AI never writes code",
                "deterministic chart grammar", "bundled offline India boundary maps", "fold-safe validation pipelines",
                "out-of-fold threshold selection", "fixed seed 42", "Windows-friendly (no C++ toolchain)",
              ].map((chip) => (
                <span key={chip} className="rounded-full bg-navy/5 px-2.5 py-1 text-[10px] font-medium text-navy-deep ring-1 ring-inset ring-navy/10">
                  {chip}
                </span>
              ))}
            </div>
          </div>
        </section>
      </Reveal>

      {/* Footer / status: navy band with saffron CTA */}
      <Reveal>
        <div className="rounded-2xl bg-[radial-gradient(130%_100%_at_50%_0%,#1e355e_0%,#13234c_100%)] px-6 py-8 text-center shadow-soft-lg">
          <p className="mx-auto max-w-2xl text-xs leading-relaxed text-mist/75">
            This is a proof of concept running locally: single user, no login, data never leaves
            this machine. Production hardening (roles and sign-in, on-premise or air-gapped
            deployment, Postgres, backups) is the planned next phase. Sample datasets are included
            - every feature on this page can be demonstrated with them.
          </p>
          {onStart && (
            <button
              onClick={onStart}
              className="mt-5 inline-flex items-center gap-2 rounded bg-saffron px-6 py-3 text-[13px] font-medium uppercase tracking-[0.65px] text-white transition-[transform,background-color] duration-150 ease-out hover:bg-saffron-deep active:scale-[0.98]"
            >
              Start a new analysis
            </button>
          )}
        </div>
      </Reveal>
    </div>
  );
}
