// Hover tooltip for plain-language explanations. Pure CSS positioning.
import { HelpCircle } from "lucide-react";
import type { ReactNode } from "react";

export function InfoTip({ text }: { text: string }) {
  if (!text) return null;
  return (
    <span className="group relative inline-flex align-middle">
      <HelpCircle className="h-3.5 w-3.5 cursor-help text-ink-dim/70 transition-colors group-hover:text-accent" />
      <span
        className="pointer-events-none absolute bottom-full left-1/2 z-50 mb-2 w-56 -translate-x-1/2 rounded-lg border border-edge bg-panel-2 px-3 py-2 text-left text-[11px] font-normal normal-case leading-snug tracking-normal text-ink opacity-0 shadow-xl shadow-slate-900/10 transition-opacity duration-150 group-hover:opacity-100"
      >
        {text}
      </span>
    </span>
  );
}

export function LabeledInfo({ label, tip }: { label: ReactNode; tip: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      {label}
      <InfoTip text={tip} />
    </span>
  );
}
