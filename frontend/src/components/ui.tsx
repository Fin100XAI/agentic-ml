// Shared primitives in the Maha AI language: paper cards on a gold-tinged
// hairline at 14px, and buttons as 4px rectangles with uppercase tracked
// labels - the site uses a flat saffron rectangle for its primary action,
// not a pill and not a gradient. Every screen inherits its look from here.
import { clsx } from "clsx";
import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react";

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={clsx(
        "rounded-[14px] border border-edge bg-panel shadow-[var(--maha-sh)]",
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
        <h3 className="text-sm font-semibold">{title}</h3>
        {subtitle && <p className="mt-1 text-xs leading-relaxed text-ink-dim">{subtitle}</p>}
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
        "inline-flex items-center justify-center gap-2 rounded font-medium uppercase tracking-[0.05em] transition-[transform,background-color,border-color,color,box-shadow] duration-150 ease-out",
        "active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50 disabled:active:scale-100",
        size === "sm" ? "px-3.5 py-2 text-[11px]" : "px-[22px] py-3 text-[13px]",
        // Navy ink rather than the site's white: white on this saffron is
        // 2.98:1, under AA at 13px. Same saffron, readable label.
        variant === "primary" &&
          "bg-maha-saffron text-maha-navy-ink hover:bg-maha-saffron-deep",
        variant === "outline" &&
          "border border-edge bg-panel text-ink hover:border-accent/50 hover:text-accent",
        variant === "ghost" && "bg-transparent text-ink-dim hover:bg-panel-2 hover:text-ink",
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
        "inline-flex max-w-full items-center truncate rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset",
        tone === "neutral" && "bg-ink-dim/10 text-ink-dim ring-ink-dim/25",
        tone === "accent" && "bg-accent-soft/70 text-accent ring-accent/20",
        tone === "good" && "bg-good/8 text-good ring-good/20",
        tone === "warn" && "bg-warn/8 text-warn ring-warn/20",
        tone === "bad" && "bg-bad/8 text-bad ring-bad/20",
      )}
    >
      {children}
    </span>
  );
}

export function SectionLabel({ children, sub }: { children: ReactNode; sub?: ReactNode }) {
  return (
    <div className="mb-4">
      <h3 className="text-sm font-semibold uppercase tracking-wider text-accent">{children}</h3>
      {sub && <p className="mt-1 max-w-2xl text-xs leading-relaxed text-ink-dim">{sub}</p>}
    </div>
  );
}

/** A placeholder with the shape of the content that is coming. Better than a
 *  spinner for lists and cards: the layout does not jump when data lands. */
export function Skeleton({ className }: { className?: string }) {
  return <span className={clsx("maha-skeleton block", className)} aria-hidden />;
}

export function Spinner({ label }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-ink-dim">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-edge border-t-accent" />
      {label}
    </span>
  );
}

/** Three breathing dots: an agent is thinking. A spinner says "the page is
 *  loading"; this says "something is deliberating", which is what an agent
 *  call actually is - and it is the site's own idiom for it. */
export function Thinking({ label }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-ink-dim">
      <span className="maha-think inline-flex items-end gap-1 text-accent" aria-hidden>
        <i />
        <i />
        <i />
      </span>
      {label && <span>{label}</span>}
      <span className="sr-only">Working</span>
    </span>
  );
}

export function Stat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="min-w-0 rounded-lg border border-edge bg-panel-2 px-3 py-2">
      <div className="truncate text-[11px] uppercase tracking-wider text-ink-dim" title={label}>
        {label}
      </div>
      <div className="mt-0.5 truncate text-lg font-semibold tabular-nums">{value}</div>
    </div>
  );
}
