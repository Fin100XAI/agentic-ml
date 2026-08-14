// Small glass-styled UI primitives.
import { clsx } from "clsx";
import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react";

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={clsx(
        "rounded-2xl border border-edge bg-panel shadow-lg shadow-slate-900/5 backdrop-blur-xl",
        className,
      )}
      {...props}
    />
  );
}

export function CardHeader({
  title,
  subtitle,
  right,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  right?: ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-edge px-5 py-4">
      <div className="min-w-0">
        <h3 className="text-sm font-semibold tracking-wide">{title}</h3>
        {subtitle && <p className="mt-0.5 text-xs text-ink-dim">{subtitle}</p>}
      </div>
      {right && <div className="shrink-0">{right}</div>}
    </div>
  );
}

export function CardBody({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={clsx("px-5 py-4", className)} {...props} />;
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "ghost" | "outline";
  size?: "sm" | "md";
};

export function Button({
  className,
  variant = "primary",
  size = "md",
  ...props
}: ButtonProps) {
  return (
    <button
      className={clsx(
        "inline-flex items-center justify-center gap-2 rounded-xl font-medium transition-all",
        "disabled:cursor-not-allowed disabled:opacity-50",
        size === "sm" ? "px-3 py-1.5 text-xs" : "px-4 py-2 text-sm",
        variant === "primary" &&
          "bg-accent text-white shadow-md shadow-accent/25 hover:bg-accent/90 hover:shadow-lg hover:shadow-accent/30 active:bg-accent/80",
        variant === "outline" &&
          "border border-edge bg-panel-2 text-ink backdrop-blur hover:border-accent/40 hover:bg-white",
        variant === "ghost" && "bg-transparent text-ink-dim hover:text-ink",
        className,
      )}
      {...props}
    />
  );
}

export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "accent" | "good" | "warn" | "bad";
}) {
  return (
    <span
      className={clsx(
        "inline-flex max-w-full items-center truncate rounded-full px-2 py-0.5 text-[11px] font-medium",
        tone === "neutral" && "bg-slate-500/10 text-ink-dim",
        tone === "accent" && "bg-accent-soft text-accent",
        tone === "good" && "bg-good/10 text-good",
        tone === "warn" && "bg-warn/10 text-warn",
        tone === "bad" && "bg-bad/10 text-bad",
      )}
    >
      {children}
    </span>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-ink-dim">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-edge border-t-accent" />
      {label}
    </span>
  );
}

export function Stat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="min-w-0 rounded-xl border border-edge bg-panel-2 px-3 py-2 backdrop-blur">
      <div className="truncate text-[11px] uppercase tracking-wider text-ink-dim" title={label}>
        {label}
      </div>
      <div className="mt-0.5 truncate text-lg font-semibold tabular-nums">{value}</div>
    </div>
  );
}
