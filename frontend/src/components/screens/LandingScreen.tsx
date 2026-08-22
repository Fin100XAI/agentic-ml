// The front door, before sign-in: what the platform is and who it is for.
// Deliberately not the workspace - no datasets, no runs, nothing that needs
// a project. Two ways on: read the guide, or sign in and start work.
import { ArrowRight, BookOpen, Database, LineChart, Lock, ScrollText,
  ShieldCheck, Sparkles, UserCheck } from "lucide-react";

const PRODUCTS = [
  {
    icon: Database,
    name: "Data Prep",
    line: "Messy workbooks become a clean table with a contract.",
    detail: "Many sheets, different years, headers two rows deep, totals mixed in with the data. The agents read it first, propose the fixes, and prove the result before it counts as prepared.",
  },
  {
    icon: LineChart,
    name: "Analysis",
    line: "Questions in plain language, answers you can defend.",
    detail: "A findings board before you type anything, then ask whatever you like. Every question becomes a visible plan you approve, and every answer carries its caveats.",
  },
  {
    icon: Sparkles,
    name: "Model Training",
    line: "For what will happen, not just what did.",
    detail: "Who is at risk, how much, where it is heading. The method is recommended and explained, checked on data it never saw, and written up as a brief with a trust rating.",
  },
];

const ASSURANCES = [
  { icon: Lock, label: "Personal data screened before anything runs" },
  { icon: ShieldCheck, label: "Every number computed, never guessed" },
  { icon: UserCheck, label: "Nothing runs without your approval" },
  { icon: ScrollText, label: "Every action on the audit trail" },
];

export function LandingScreen({
  onSignIn,
  onGuide,
}: {
  onSignIn: () => void;
  onGuide: () => void;
}) {
  return (
    <div className="min-h-screen">
      {/* Hero */}
      <div className="maha-band relative overflow-hidden px-6 py-24 text-center sm:py-28">
        <div
          aria-hidden
          className="pointer-events-none absolute -top-32 left-1/2 h-72 w-[46rem] -translate-x-1/2 rounded-full opacity-20 blur-3xl"
          style={{ backgroundImage: "var(--maha-grad)" }}
        />
        <div className="relative mx-auto max-w-[1170px]">
          <p className="maha-eyebrow animate-rise">Maha AI Intelligence Foundry</p>
          <h1 className="maha-display animate-rise mx-auto mt-5 max-w-3xl text-balance text-4xl [animation-delay:60ms] md:text-[56px]">
            Evidence for every decision.{" "}
            <span className="maha-gold-text">Accountability at every step.</span>
          </h1>
          <p className="animate-rise mx-auto mt-6 max-w-2xl text-pretty text-[15px] leading-relaxed text-ink-dim [animation-delay:120ms]">
            Decision support built for government. Departmental data in - scheme
            enrollments, revenue collections, service requests, demand histories - and
            defensible answers out. Agents do the legwork; code computes every number;
            you approve every step.
          </p>
          <div className="animate-rise mt-9 flex flex-wrap items-center justify-center gap-3 [animation-delay:200ms]">
            <button onClick={onSignIn} className="maha-cta inline-flex items-center gap-2">
              Sign in to the workspace <ArrowRight className="h-4 w-4" />
            </button>
            <button
              onClick={onGuide}
              className="inline-flex items-center gap-2 rounded border border-edge px-[22px] py-[14px] text-[13px] uppercase tracking-[0.05em] text-ink transition-colors hover:border-edge-strong"
            >
              <BookOpen className="h-4 w-4" /> Read the guide
            </button>
          </div>
        </div>
      </div>

      {/* The three products */}
      <div className="mx-auto max-w-[1170px] px-6 py-20">
        <p className="maha-eyebrow">What it does</p>
        <h2 className="maha-rule mt-2 text-2xl text-ink md:text-[32px]">
          Three products, one shelf
        </h2>
        <p className="mt-5 max-w-2xl text-sm leading-relaxed text-ink-dim">
          Each stands on its own. What ties them together is the data: a table you
          prepare is stored once and is then available to analyse or to train on, with
          its lineage and its contract intact.
        </p>

        <div data-cascade className="mt-9 grid gap-4 md:grid-cols-3">
          {PRODUCTS.map((p) => (
            <div key={p.name} className="tile rounded-[14px] border border-edge bg-panel p-6">
              <span className="tile-icon inline-flex rounded-lg bg-accent-soft p-2.5">
                <p.icon className="h-5 w-5 text-accent" />
              </span>
              <h3 className="mt-4 text-lg text-ink">{p.name}</h3>
              <p className="mt-1.5 text-sm text-ink">{p.line}</p>
              <p className="mt-3 text-[13px] leading-relaxed text-ink-dim">{p.detail}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Assurances */}
      <div className="maha-band px-6 py-16">
        <div className="mx-auto max-w-[1170px]">
          <p className="maha-eyebrow">Why it can be trusted</p>
          <div className="mt-6 grid gap-x-8 gap-y-4 sm:grid-cols-2 lg:grid-cols-4">
            {ASSURANCES.map((a) => (
              <div key={a.label} className="flex items-start gap-2.5">
                <a.icon className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
                <span className="text-[13px] leading-snug text-ink-dim">{a.label}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="mx-auto max-w-[1170px] px-6 py-14 text-center">
        <button onClick={onSignIn} className="maha-cta inline-flex items-center gap-2">
          Sign in to the workspace <ArrowRight className="h-4 w-4" />
        </button>
        <p className="mt-4 text-[11px] text-faint">
          A prototype for demonstration. Sign-in records who did what; it is not a
          security control.
        </p>
      </div>
    </div>
  );
}
