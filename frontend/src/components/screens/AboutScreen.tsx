// Platform guide: a presentation-grade page for demos and new users - what
// the platform is, how it works (visual flows), and why it can be trusted.
// Written for a government audience; readable by tech and non-tech alike.
// Visual language: RoleSprint (rolesprint.io) - a dark full-bleed page,
// layered dark cards on translucent hairlines, Plus Jakarta Sans, the
// periwinkle/teal/violet accent trio, gradient pill CTA. Copy style: short
// sentences, bullets over paragraphs, big gradient stat numbers. Judgment
// states keep green/amber tones. Motion: staggered hero, scroll reveals.
import { useState } from "react";
import {
  Activity,
  AlertTriangle,
  Ban,
  Bot,
  Box,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Columns3,
  Compass,
  Database,
  FileCheck2,
  FileText,
  FileUp,
  Gauge,
  GitCompareArrows,
  Hash,
  HelpCircle,
  Inbox,
  Landmark,
  Layers,
  Lightbulb,
  LineChart,
  ListChecks,
  Lock,
  MapPin,
  MessageSquare,
  MonitorSmartphone,
  ScrollText,
  Search,
  Server,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Target,
  UserCheck,
  Users,
  Wrench,
} from "lucide-react";
import { Reveal } from "../Reveal";

/* ---------- content ---------- */

// Big and verifiable: 17 agents (roster below), 36 states + 640 districts
// in the bundled boundary files, en/hi/mr phrasing, ~20 chart + map forms.
const STATS = [
  { value: "2", label: "ways to work" },
  { value: "17", label: "AI agents" },
  { value: "12", label: "models on tap" },
  { value: "20+", label: "charts & maps" },
  { value: "3", label: "languages" },
  { value: "676", label: "map areas, offline" },
  { value: "100%", label: "actions logged" },
  { value: "0", label: "numbers invented by AI" },
];

const PILLARS = [
  {
    icon: Lock,
    title: "Privacy before analysis",
    text: "Mobile numbers, Aadhaar-like IDs, PAN, names, addresses - caught and masked or dropped BEFORE any analysis or AI call sees a row.",
  },
  {
    icon: ShieldCheck,
    title: "Numbers computed, never guessed",
    text: "Every figure is calculated in code. The AI only explains and phrases. Each output is badged AI or heuristic.",
  },
  {
    icon: CheckCircle2,
    title: "You approve every step",
    text: "Agents propose. Nothing runs without approval - data fixes, the approach, settings, features, thresholds.",
  },
  {
    icon: ScrollText,
    title: "An audit trail fit for review",
    text: "Every upload, AI call, approval, training job and export is logged. Originals stay read-only with a content hash.",
  },
];

// The two paths, as scannable bullets instead of paragraphs.
const ASK_PATH = [
  "A findings board before you type: leaders, trends, year-on-year shifts",
  "Three scouts read the data first - its shape, its topics, the questions worth asking",
  "Every question becomes a visible plan you approve before it runs",
  "District and state results offer a map view; every answer carries its caveats",
  "Selected answers compile into a critic-checked brief",
  "Saved questions become indicators that refresh with next month's file",
  "Phrased in English, Hindi or Marathi",
];

const MODEL_PATH = [
  "For what WILL happen: who is at risk, how much, where it is heading",
  "Health checks, fixes and features - each one approved by you",
  "The right method recommended and explained in plain language",
  "Honesty checks on data the model never saw",
  "A decision brief with a trust rating, already critic-reviewed",
  "Models become versioned assets that score next month's file",
];

// Step zero: the data checkup that runs before any exploration.
const CHECKUP = [
  {
    icon: Hash,
    title: "Numbers in text costumes",
    text: "'1,234' stored as text cannot be ranked, trended or mapped. Found, shown, converted - with your approval.",
  },
  {
    icon: MapPin,
    title: "Same place, five spellings",
    text: "Orissa, Orrisa, ODISHA - split spellings split your totals. Merges proposed; approved spellings are remembered.",
  },
  {
    icon: FileCheck2,
    title: "The original never changes",
    text: "Every fix creates a new copy with lineage back to its parent. The file you uploaded stays untouched.",
  },
];

// The working rhythm: who does what, in order. actor: ai | you | machine
const FLOW: { actor: "ai" | "you" | "machine"; title: string; text: string; icon: any }[] = [
  { actor: "you", icon: FileUp, title: "Upload the file", text: "CSV or Excel - multi-sheet workbooks combine in one click." },
  { actor: "you", icon: Columns3, title: "Approve column names", text: "Fix cryptic headers; the original stays untouched." },
  { actor: "machine", icon: Lock, title: "Privacy screen runs", text: "Personal data flagged; you choose mask, drop or keep." },
  { actor: "you", icon: FileCheck2, title: "Decide the data checkup", text: "Text-numbers converted, place spellings merged - your call, first." },
  { actor: "ai", icon: Bot, title: "Agents explore + propose", text: "Findings charted, fixes proposed, leakage risks flagged." },
  { actor: "you", icon: UserCheck, title: "Approve the approach", text: "Pick or adjust the method; tick fixes and features." },
  { actor: "machine", icon: Gauge, title: "Train + honesty checks", text: "Stability, probabilities and error slices - on unseen data." },
  { actor: "ai", icon: Sparkles, title: "Brief drafted, critic reviews", text: "Every claim checked against the computed numbers." },
  { actor: "you", icon: Landmark, title: "Decide - with cover", text: "Trust rating, caveats, and the audit trail behind it." },
];

const LINEAGE = [
  { icon: FileUp, label: "Original file", note: "read-only + hash" },
  { icon: Columns3, label: "Approved names", note: "rename artifact" },
  { icon: Lock, label: "Privacy mask", note: "PII artifact" },
  { icon: FileCheck2, label: "Approved fixes", note: "checkup artifact" },
  { icon: Sparkles, label: "Engineered features", note: "feature artifact" },
  { icon: Landmark, label: "Trained model", note: "versioned, never overwritten" },
  { icon: Target, label: "Predictions", note: "score artifact" },
];

const USE_CASES = [
  { icon: Search, title: "What does the data say?", kind: "Answered in seconds", example: "Totals, toppers, trends, shares - charted, mapped and explained the moment you upload." },
  { icon: MapPin, title: "Which areas stand out?", kind: "Maps + outliers", example: "Results on offline India maps, state or district level. Values that sit far outside the rest get flagged." },
  { icon: Users, title: "Who needs attention?", kind: "Classification", example: "Beneficiaries at risk of dropping out. Applications that need senior review." },
  { icon: Target, title: "How much will it be?", kind: "Regression", example: "Property valuations, expected collections per ward, likely claim amounts." },
  { icon: GitCompareArrows, title: "What groups exist?", kind: "Clustering", example: "Natural segments of citizens, villages or facilities - so schemes target, not blanket." },
  { icon: LineChart, title: "Where is it heading?", kind: "Forecasting", example: "Revenue, demand and supply projections per district - with honest uncertainty." },
];

const LIFECYCLE = [
  { icon: Landmark, title: "Model registry", text: "Every trained model is a numbered version - purpose, data fingerprint, settings, scores." },
  { icon: Target, title: "Score new files", text: "Next month's file goes through the exact training-time preparation - even with renamed columns." },
  { icon: Activity, title: "Drift monitor", text: "Degraded is only said when accuracy actually fell." },
  { icon: SlidersHorizontal, title: "What-if scenarios", text: "Move a driver, watch the prediction respond - with extrapolation warnings." },
  { icon: Gauge, title: "Decision threshold", text: "Trade missed cases against false alarms; your choice is what scoring uses." },
  { icon: Inbox, title: "Intake inbox", text: "Recurring files queued for one-click review. Nothing ever auto-runs." },
];

// Compact roster: names on the page, the one-liner lives in the tooltip.
const AGENTS: { icon: any; name: string; does: string }[] = [
  { icon: Database, name: "EDA agent", does: "reads and explains your dataset" },
  { icon: Box, name: "Shape scout", does: "reads what KIND of dataset this is" },
  { icon: Layers, name: "Domain scout", does: "groups columns into topics and suggests a focus" },
  { icon: HelpCircle, name: "Question scout", does: "picks diverse opening questions worth asking" },
  { icon: Compass, name: "Explorer agents", does: "answer the first questions before you type anything" },
  { icon: Lightbulb, name: "Analyst agent", does: "explains what each finding means, in your language" },
  { icon: AlertTriangle, name: "Anomaly scout", does: "flags values that sit far outside the rest" },
  { icon: MapPin, name: "Place harmonizer", does: "catches the same place spelled differently" },
  { icon: ListChecks, name: "Query planner", does: "turns plain-language questions into typed, visible plans" },
  { icon: Target, name: "Recommendation agent", does: "picks the method and checks your question fits the data" },
  { icon: Wrench, name: "Remediation agent", does: "phrases the data-fix proposals" },
  { icon: Sparkles, name: "Feature agent", does: "suggests derived measures worth adding" },
  { icon: Gauge, name: "Interpretation agent", does: "judges how well the model did" },
  { icon: FileText, name: "Brief agent", does: "writes the decision brief to the evidence level" },
  { icon: ShieldCheck, name: "Critic agent", does: "checks every claim in every brief against the computed numbers" },
  { icon: MessageSquare, name: "Ask-the-data agent", does: "answers follow-ups from the run's own facts" },
  { icon: GitCompareArrows, name: "Compare summarizer", does: "explains the model leaderboard" },
];

// The character, as four chips - full sentence in the tooltip.
const CHARACTER: { icon: any; name: string; detail: string }[] = [
  { icon: Gauge, name: "Trust ratings, not just scores", detail: "Weak evidence turns recommended actions into hypotheses to verify." },
  { icon: CheckCircle2, name: "Cross-validated numbers", detail: "Headline metrics come from data the model never saw." },
  { icon: ShieldCheck, name: "A critic reviews every brief", detail: "Claims are checked before you read them." },
  { icon: Ban, name: "Honest refusals", detail: "Too little data? Said openly. A column that gives the answer away? Blocked." },
];

/* ---------- small building blocks ---------- */

// The accent trio rotates across sections, RoleSprint style.
const ACCENTS = {
  blue: { text: "text-rs-blue", bg: "bg-rs-blue/10", ring: "ring-rs-blue/25" },
  teal: { text: "text-rs-teal", bg: "bg-rs-teal/10", ring: "ring-rs-teal/25" },
  violet: { text: "text-rs-violet", bg: "bg-rs-violet/10", ring: "ring-rs-violet/25" },
} as const;
type Accent = keyof typeof ACCENTS;

// Section head: small tracked uppercase eyebrow in an accent, big tight title.
function GuideSection({ eyebrow, accent = "blue", title, sub }: { eyebrow: string; accent?: Accent; title: string; sub?: string }) {
  return (
    <div className="mb-5">
      <p className={`text-[11px] font-bold uppercase tracking-[0.2em] ${ACCENTS[accent].text}`}>{eyebrow}</p>
      <h3 className="mt-1.5 text-2xl font-bold tracking-tight text-rs-fg md:text-3xl">{title}</h3>
      {sub && <p className="mt-2 max-w-2xl text-xs leading-relaxed text-rs-muted">{sub}</p>}
    </div>
  );
}

// Dark raised card on a translucent hairline; border brightens on hover.
function RsCard({ className = "", children }: { className?: string; children: React.ReactNode }) {
  return (
    <div
      className={`lift rounded-3xl border border-rs-line bg-rs-raised transition-colors hover:border-rs-line-strong ${className}`}
    >
      {children}
    </div>
  );
}

// Icon tile in an accent tint.
function IconTile({ icon: Icon, accent }: { icon: any; accent: Accent }) {
  const a = ACCENTS[accent];
  return (
    <span className={`inline-flex rounded-xl p-2 ${a.bg} ring-1 ring-inset ${a.ring}`}>
      <Icon className={`h-4 w-4 ${a.text}`} />
    </span>
  );
}

// One bullet line of a path card.
function PathItem({ text, accent }: { text: string; accent: Accent }) {
  return (
    <li className="flex items-start gap-2 text-xs leading-relaxed text-rs-muted">
      <Check className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${ACCENTS[accent].text}`} />
      {text}
    </li>
  );
}

const ACTOR_STYLE = {
  ai: { dot: "bg-rs-blue text-rs-ink", chip: "bg-rs-blue/10 text-rs-blue ring-rs-blue/25", label: "AI proposes" },
  you: { dot: "bg-rs-teal text-rs-ink", chip: "bg-rs-teal/10 text-rs-teal ring-rs-teal/25", label: "You decide" },
  machine: { dot: "bg-rs-faint text-rs-ink", chip: "bg-rs-fg/5 text-rs-muted ring-rs-fg/10", label: "Machine computes" },
} as const;

const GRADIENT = "bg-[linear-gradient(100deg,#45e0c8,#6e8bff_55%,#b98cff)]";

/* ---------- page ---------- */

export function AboutScreen({ onStart }: { onStart?: () => void }) {
  // Under the hood is for the technical evaluator - hidden until asked for.
  const [hoodOpen, setHoodOpen] = useState(false);
  return (
    // The whole guide is one full-bleed dark page, edge to edge - the app
    // shell renders it without the centered container.
    <div className="font-jakarta min-h-screen bg-rs-ink px-4 py-12 sm:px-8 md:px-12">
      <div className="mx-auto max-w-5xl space-y-16">
        {/* Hero */}
        <div className="pt-2 text-center">
          <p className="animate-rise text-[11px] font-bold uppercase tracking-[0.22em] text-rs-blue">
            Platform guide
          </p>
          <h2 className="animate-rise mx-auto mt-4 max-w-3xl text-balance text-4xl font-extrabold leading-[1.05] tracking-tight text-rs-fg [animation-delay:60ms] md:text-5xl">
            Decision support for government,{" "}
            <span className={`${GRADIENT} bg-clip-text text-transparent`}>
              with accountability built in.
            </span>
          </h2>
          <p className="animate-rise mx-auto mt-5 max-w-2xl text-pretty text-sm leading-relaxed text-rs-muted [animation-delay:120ms]">
            Departmental data in, defensible answers out. Ask in plain language and get
            charted, mapped answers in seconds - or train a model for predictions with a
            brief an officer can defend. Agents do the legwork. Code computes every number.
            You approve every step.
          </p>
          {/* Big stat grid */}
          <div className="animate-rise mx-auto mt-10 grid max-w-4xl grid-cols-2 gap-x-4 gap-y-8 [animation-delay:200ms] sm:grid-cols-4">
            {STATS.map((s) => (
              <div key={s.label}>
                <div className={`${GRADIENT} bg-clip-text text-4xl font-extrabold tabular-nums tracking-tight text-transparent md:text-5xl`}>
                  {s.value}
                </div>
                <div className="mt-1.5 text-[10px] font-semibold uppercase tracking-wider text-rs-muted">
                  {s.label}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Trust pillars */}
        <Reveal>
          <section>
            <GuideSection eyebrow="The foundations" accent="teal" title="Why a government can trust it" />
            <div data-cascade className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
              {PILLARS.map((p, i) => (
                <RsCard key={p.title} className="p-5">
                  <IconTile icon={p.icon} accent={(["teal", "blue", "violet", "blue"] as Accent[])[i]} />
                  <h4 className="mt-3 text-sm font-bold text-rs-fg">{p.title}</h4>
                  <p className="mt-2 text-[11px] leading-relaxed text-rs-muted">{p.text}</p>
                </RsCard>
              ))}
            </div>
          </section>
        </Reveal>

        {/* The fork: two ways to work */}
        <Reveal>
          <section>
            <GuideSection
              eyebrow="The fork"
              accent="blue"
              title="Two ways to work"
              sub="Same protections either way - approved names, the privacy screen, the data checkup. You choose the direction; switching later is one click."
            />
            <div data-cascade className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <RsCard className="p-6">
                <div className="flex flex-wrap items-center gap-2.5">
                  <IconTile icon={Sparkles} accent="teal" />
                  <h4 className="text-base font-bold text-rs-fg">Understand & ask</h4>
                  <span className="rounded-full bg-rs-teal/10 px-2.5 py-0.5 text-[10px] font-semibold text-rs-teal ring-1 ring-inset ring-rs-teal/25">
                    answers in seconds
                  </span>
                </div>
                <ul className="mt-4 space-y-2">
                  {ASK_PATH.map((t) => (
                    <PathItem key={t} text={t} accent="teal" />
                  ))}
                </ul>
              </RsCard>
              <RsCard className="p-6">
                <div className="flex flex-wrap items-center gap-2.5">
                  <IconTile icon={Landmark} accent="violet" />
                  <h4 className="text-base font-bold text-rs-fg">Train a model</h4>
                  <span className="rounded-full bg-rs-violet/10 px-2.5 py-0.5 text-[10px] font-semibold text-rs-violet ring-1 ring-inset ring-rs-violet/25">
                    predictions with cover
                  </span>
                </div>
                <ul className="mt-4 space-y-2">
                  {MODEL_PATH.map((t) => (
                    <PathItem key={t} text={t} accent="violet" />
                  ))}
                </ul>
              </RsCard>
            </div>
          </section>
        </Reveal>

        {/* Step zero: the data checkup */}
        <Reveal>
          <section>
            <GuideSection
              eyebrow="Step zero"
              accent="violet"
              title="First, the data checkup"
              sub="Real files arrive messy. The checkup runs before ANY analysis - and the agents explore only after your decision, so they read the clean version, once."
            />
            <div data-cascade className="grid grid-cols-1 gap-4 md:grid-cols-3">
              {CHECKUP.map((c, i) => (
                <RsCard key={c.title} className="p-5">
                  <IconTile icon={c.icon} accent={(["violet", "teal", "blue"] as Accent[])[i]} />
                  <h4 className="mt-3 text-sm font-bold text-rs-fg">{c.title}</h4>
                  <p className="mt-2 text-[11px] leading-relaxed text-rs-muted">{c.text}</p>
                </RsCard>
              ))}
            </div>
          </section>
        </Reveal>

        {/* The working rhythm: timeline with actor lanes */}
        <Reveal>
          <section>
            <GuideSection
              eyebrow="The working rhythm"
              accent="teal"
              title="How a decision gets made"
              sub="AI proposes. Machines compute. Every consequential step waits for a human. One file, upload to decision - the ask path follows the same rhythm on every question."
            />
            <div className="mb-4 flex flex-wrap items-center gap-3">
              {(Object.keys(ACTOR_STYLE) as (keyof typeof ACTOR_STYLE)[]).map((k) => (
                <span key={k} className="flex items-center gap-1.5 text-[11px] text-rs-muted">
                  <span className={`h-2.5 w-2.5 rounded-full ${ACTOR_STYLE[k].dot.split(" ")[0]}`} />
                  {ACTOR_STYLE[k].label}
                </span>
              ))}
            </div>
            <div className="relative">
              {/* center spine */}
              <div className="absolute bottom-4 left-4 top-1 w-px bg-rs-line-strong md:left-1/2" />
              <div data-cascade className="space-y-3">
                {FLOW.map((s, i) => {
                  const st = ACTOR_STYLE[s.actor];
                  const left = i % 2 === 0;
                  return (
                    <div key={s.title} className={`relative flex md:w-1/2 ${left ? "" : "md:ml-auto"}`}>
                      {/* node on the spine */}
                      <span
                        className={`absolute top-4 z-10 flex h-8 w-8 items-center justify-center rounded-full ring-4 ring-rs-ink ${st.dot} left-0 ${
                          left ? "md:left-auto md:right-0 md:translate-x-1/2" : "md:-translate-x-1/2"
                        }`}
                      >
                        <span className="text-[11px] font-bold">{i + 1}</span>
                      </span>
                      <div className={`ml-12 flex-1 md:ml-0 ${left ? "md:mr-8" : "md:ml-8"}`}>
                        <div className="lift rounded-2xl border border-rs-line bg-rs-raised p-4 transition-colors hover:border-rs-line-strong">
                          <div className="flex flex-wrap items-center gap-2">
                            <s.icon className="h-4 w-4 text-rs-blue" />
                            <h4 className="text-sm font-bold text-rs-fg">{s.title}</h4>
                            <span className={`ml-auto rounded-full px-2 py-0.5 text-[10px] font-medium ring-1 ring-inset ${st.chip}`}>
                              {st.label}
                            </span>
                          </div>
                          <p className="mt-1.5 text-[11px] leading-relaxed text-rs-muted">{s.text}</p>
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
              accent="blue"
              title="What happens to your data"
              sub="The original is read-only with a fingerprint. Every change is a NEW copy pointing back at its parent - any number in any brief traces to the exact data it came from."
            />
            <div className="rounded-3xl border border-rs-line bg-rs-raised p-5">
              <div data-cascade className="flex flex-wrap items-center justify-center gap-y-4">
                {LINEAGE.map((l, i) => (
                  <div key={l.label} className="flex items-center">
                    <div className="flex w-28 flex-col items-center text-center">
                      <span className={`flex h-10 w-10 items-center justify-center rounded-xl ${i === 0 ? `${GRADIENT} text-rs-ink` : "bg-rs-elevated text-rs-teal ring-1 ring-inset ring-rs-line"}`}>
                        <l.icon className="h-4.5 w-4.5" />
                      </span>
                      <span className="mt-1.5 text-[11px] font-semibold leading-tight text-rs-fg">{l.label}</span>
                      <span className="text-[9px] uppercase tracking-wide text-rs-faint">{l.note}</span>
                    </div>
                    {i < LINEAGE.length - 1 && (
                      <svg className="mx-0.5 h-4 w-6 shrink-0 text-rs-faint" viewBox="0 0 24 16" fill="none">
                        <path d="M0 8h18m0 0-5-5m5 5-5 5" stroke="currentColor" strokeWidth="1.6" />
                      </svg>
                    )}
                  </div>
                ))}
              </div>
              <p className="mt-4 border-t border-rs-line pt-3 text-center text-[11px] text-rs-muted">
                Every arrow is a recorded step in the audit trail. Nothing is edited in place.
              </p>
            </div>
          </section>
        </Reveal>

        {/* Use cases */}
        <Reveal>
          <section>
            <GuideSection eyebrow="Applications" accent="violet" title="The questions it can answer" />
            <div data-cascade className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
              {USE_CASES.map((u, i) => {
                const accent = (["teal", "blue", "violet", "blue", "teal", "violet"] as Accent[])[i];
                const a = ACCENTS[accent];
                return (
                  <RsCard key={u.title} className="p-5">
                    <div className="flex items-center justify-between gap-2">
                      <IconTile icon={u.icon} accent={accent} />
                      <span className={`rounded-full px-2.5 py-0.5 text-[10px] font-semibold ${a.bg} ${a.text} ring-1 ring-inset ${a.ring}`}>
                        {u.kind}
                      </span>
                    </div>
                    <h4 className="mt-3 text-sm font-bold text-rs-fg">{u.title}</h4>
                    <p className="mt-2 text-[11px] leading-relaxed text-rs-muted">{u.example}</p>
                  </RsCard>
                );
              })}
            </div>
          </section>
        </Reveal>

        {/* What you receive: brief mockup */}
        <Reveal>
          <section>
            <GuideSection
              eyebrow="The deliverable"
              accent="teal"
              title="What you receive"
              sub="Not a dashboard to interpret. A brief to act on, confidence stated up front."
            />
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
              <div className="lg:col-span-3">
                {/* stylized decision brief */}
                <div className="rounded-3xl border border-rs-line bg-rs-elevated p-6">
                  <div className="flex items-center justify-between border-b border-rs-line pb-3">
                    <div>
                      <p className="text-[10px] uppercase tracking-wider text-rs-faint">Decision brief</p>
                      <h4 className="text-sm font-bold text-rs-fg">
                        Which beneficiaries are at risk of dropping out?
                      </h4>
                    </div>
                    <span className="rounded-full bg-rs-good/10 px-2.5 py-1 text-[10px] font-semibold text-rs-good ring-1 ring-inset ring-rs-good/25">
                      evidence: strong
                    </span>
                  </div>
                  <div className="mt-3 space-y-2.5">
                    <div>
                      <p className="text-[10px] font-semibold uppercase tracking-wider text-rs-blue">Executive summary</p>
                      <div className="mt-1 space-y-1">
                        <div className="h-2 w-full rounded bg-rs-fg/10" />
                        <div className="h-2 w-11/12 rounded bg-rs-fg/10" />
                        <div className="h-2 w-4/5 rounded bg-rs-fg/5" />
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-2.5">
                      <div>
                        <p className="text-[10px] font-semibold uppercase tracking-wider text-rs-blue">Key findings</p>
                        <div className="mt-1 space-y-1">
                          <div className="h-2 w-full rounded bg-rs-fg/10" />
                          <div className="h-2 w-5/6 rounded bg-rs-fg/5" />
                          <div className="h-2 w-4/6 rounded bg-rs-fg/5" />
                        </div>
                      </div>
                      <div>
                        <p className="text-[10px] font-semibold uppercase tracking-wider text-rs-blue">Recommended actions</p>
                        <div className="mt-1 space-y-1">
                          <div className="h-2 w-full rounded bg-rs-fg/10" />
                          <div className="h-2 w-5/6 rounded bg-rs-fg/5" />
                          <div className="h-2 w-3/6 rounded bg-rs-fg/5" />
                        </div>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 rounded-xl border border-rs-line bg-rs-raised px-3 py-2">
                      <ShieldCheck className="h-3.5 w-3.5 shrink-0 text-rs-teal" />
                      <p className="text-[10px] leading-snug text-rs-muted">
                        Critic-reviewed: claims checked against the computed numbers, causal
                        caveats added, hedged to the evidence level.
                      </p>
                    </div>
                  </div>
                </div>
              </div>
              <div data-cascade className="space-y-3 lg:col-span-2">
                {[
                  ["Plain language first", "Jargon lives behind info buttons. Every metric has a one-line explanation."],
                  ["Charts that explain themselves", "Each chart carries a caption saying what to read off it."],
                  ["Shareable + printable", "A read-only briefing link, plus markdown and PDF exports."],
                  ["Ask the data", "A grounded chat answers follow-ups from the run's own numbers. It cannot make things up."],
                ].map(([t, d]) => (
                  <div key={t} className="lift rounded-2xl border border-rs-line bg-rs-raised p-4 transition-colors hover:border-rs-line-strong">
                    <h5 className="text-xs font-bold text-rs-fg">{t}</h5>
                    <p className="mt-1 text-[11px] leading-relaxed text-rs-muted">{d}</p>
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
              accent="blue"
              title="After the first analysis"
              sub="The first analysis is the beginning. Trained models become managed assets."
            />
            <div data-cascade className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
              {LIFECYCLE.map((l, i) => (
                <RsCard key={l.title} className="p-5">
                  <div className="flex items-center gap-2.5">
                    <IconTile icon={l.icon} accent={(["blue", "teal", "violet", "teal", "blue", "violet"] as Accent[])[i]} />
                    <h4 className="text-sm font-bold text-rs-fg">{l.title}</h4>
                  </div>
                  <p className="mt-2.5 text-[11px] leading-relaxed text-rs-muted">{l.text}</p>
                </RsCard>
              ))}
            </div>
          </section>
        </Reveal>

        {/* The workforce: 17 name-only pills, one-liners in the tooltips */}
        <Reveal>
          <section>
            <GuideSection
              eyebrow="The workforce"
              accent="teal"
              title="17 agents, one rule"
              sub="Each one proposes or phrases. None computes a number or acts alone. Hover a name for what it does."
            />
            <div data-cascade className="flex flex-wrap gap-2">
              {AGENTS.map((a, i) => {
                const ac = ACCENTS[(["teal", "blue", "violet"] as Accent[])[i % 3]];
                return (
                  <span
                    key={a.name}
                    title={a.does}
                    className="lift flex cursor-default items-center gap-1.5 rounded-full border border-rs-line bg-rs-raised px-3 py-1.5 text-xs font-semibold text-rs-fg transition-colors hover:border-rs-line-strong"
                  >
                    <a.icon className={`h-3.5 w-3.5 ${ac.text}`} />
                    {a.name}
                  </span>
                );
              })}
            </div>
            <p className="mt-3 text-[11px] text-rs-faint">
              No AI connection? Everything still works - badged heuristic, visibly.
            </p>
          </section>
        </Reveal>

        {/* The character: four chips, details in the tooltips */}
        <Reveal>
          <section>
            <GuideSection eyebrow="The character" accent="violet" title="Honest by design" />
            <div data-cascade className="flex flex-wrap gap-2">
              {CHARACTER.map((c, i) => {
                const ac = ACCENTS[(["violet", "teal", "blue", "violet"] as Accent[])[i]];
                return (
                  <span
                    key={c.name}
                    title={c.detail}
                    className="lift flex cursor-default items-center gap-1.5 rounded-full border border-rs-line bg-rs-raised px-3 py-1.5 text-xs font-semibold text-rs-fg transition-colors hover:border-rs-line-strong"
                  >
                    <c.icon className={`h-3.5 w-3.5 ${ac.text}`} />
                    {c.name}
                  </span>
                );
              })}
            </div>
          </section>
        </Reveal>

        {/* For the technical reader - hidden until asked for */}
        <Reveal>
          <section className="text-center">
            <button
              onClick={() => setHoodOpen((o) => !o)}
              className="inline-flex items-center gap-2 rounded-full border border-rs-line bg-rs-raised px-5 py-2.5 text-sm font-semibold text-rs-fg transition-colors duration-150 ease-out hover:border-rs-line-strong active:scale-[0.98]"
            >
              <Server className="h-4 w-4 text-rs-blue" />
              Under the hood
              {hoodOpen ? <ChevronUp className="h-4 w-4 text-rs-muted" /> : <ChevronDown className="h-4 w-4 text-rs-muted" />}
            </button>
            {hoodOpen && (
            <div className="mt-5 rounded-3xl border border-rs-line bg-rs-raised p-5 text-left">
              <div data-cascade className="flex flex-col items-stretch gap-2 md:flex-row md:items-center">
                {[
                  { icon: MonitorSmartphone, title: "React UI", sub: "TypeScript + Tailwind + Recharts", note: "screens mirror backend types", accent: "teal" as Accent },
                  { icon: Server, title: "FastAPI", sub: "REST + approval gates", note: "audit log, artifact ledger, registry", accent: "blue" as Accent },
                  { icon: Database, title: "Python engine", sub: "pandas / scikit-learn / XGBoost / statsmodels", note: "pure - no web imports; every number computed here", accent: "violet" as Accent },
                ].map((t, i, arr) => (
                  <div key={t.title} className="flex flex-1 items-center">
                    <div className="flex-1 rounded-2xl border border-rs-line bg-rs-elevated p-4 text-center">
                      <t.icon className={`mx-auto h-5 w-5 ${ACCENTS[t.accent].text}`} />
                      <h4 className="mt-1.5 text-sm font-bold text-rs-fg">{t.title}</h4>
                      <p className="text-[11px] text-rs-muted">{t.sub}</p>
                      <p className="mt-1 text-[10px] uppercase tracking-wide text-rs-faint">{t.note}</p>
                    </div>
                    {i < arr.length - 1 && (
                      <svg className="mx-1 hidden h-4 w-8 shrink-0 text-rs-faint md:block" viewBox="0 0 32 16" fill="none">
                        <path d="M0 8h26m0 0-5-5m5 5-5 5M6 8l5-5M6 8l5 5" stroke="currentColor" strokeWidth="1.6" />
                      </svg>
                    )}
                  </div>
                ))}
              </div>
              <div className="mt-4 flex flex-wrap justify-center gap-1.5 border-t border-rs-line pt-3.5">
                {[
                  "SQLite (Postgres-portable)", "content-addressed artifact store", "model plugins via @register",
                  "swappable LLM provider + deterministic fallbacks", "typed query plans - the AI never writes code",
                  "deterministic chart grammar", "36 states + 640 districts mapped offline", "fold-safe validation pipelines",
                  "out-of-fold threshold selection", "fixed seed 42", "Windows-friendly (no C++ toolchain)",
                ].map((chip) => (
                  <span key={chip} className="rounded-full border border-rs-line bg-rs-surface px-2.5 py-1 text-[10px] font-medium text-rs-muted">
                    {chip}
                  </span>
                ))}
              </div>
            </div>
            )}
          </section>
        </Reveal>

        {/* Closing CTA */}
        {onStart && (
          <Reveal>
            <div className="pb-4 text-center">
              <button
                onClick={onStart}
                className={`inline-flex items-center gap-2 rounded-full ${GRADIENT} px-7 py-3.5 text-sm font-bold text-[#07080c] transition-[transform,box-shadow] duration-150 ease-out hover:shadow-[0_12px_44px_-12px_#6e8bffb3] active:scale-[0.98]`}
              >
                Start a new analysis
              </button>
            </div>
          </Reveal>
        )}
      </div>
    </div>
  );
}
