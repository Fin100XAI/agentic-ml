// The toolbar's overflow. Everything that is not navigation lives here -
// the library, the guide, the activity log, the theme, signing out - so the
// bar itself carries only where you are and where you can go.
//
// Closes on outside click, on Escape, and on choosing something. Focus
// returns to the trigger, because a menu that strands the keyboard is worse
// than no menu.
import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { ChevronDown, User } from "lucide-react";

export interface MenuItem {
  label: string;
  icon: ReactNode;
  onClick: () => void;
  detail?: string;
  active?: boolean;
}

export function ToolbarMenu({
  label,
  sublabel,
  groups,
}: {
  label: string;
  sublabel?: string;
  /** Rendered with a hairline between each group. */
  groups: MenuItem[][];
}) {
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!wrap.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        trigger.current?.focus();
      }
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={wrap} className="relative">
      <button
        ref={trigger}
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-haspopup="menu"
        className="flex items-center gap-1.5 rounded border border-edge bg-panel-2 px-2 py-1.5 text-[11px] text-ink-dim transition-colors hover:border-edge-strong hover:text-accent sm:px-2.5"
        title={sublabel ? `${label} - ${sublabel}` : label}
      >
        {/* The name is capped hard and disappears entirely on small screens.
            A toolbar is not the place to render someone's full title - the
            menu itself carries it, and the bar keeps its room for the
            stepper. */}
        <User className="h-3.5 w-3.5 shrink-0 sm:hidden" />
        <span className="hidden max-w-[7.5rem] truncate sm:inline lg:max-w-[9rem]">{label}</span>
        <ChevronDown
          className={`h-3 w-3 shrink-0 transition-transform duration-200 ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && (
        <div
          role="menu"
          className="maha-rin absolute right-0 top-[calc(100%+6px)] z-50 w-60 overflow-hidden rounded-[14px] border border-edge bg-panel shadow-[var(--maha-sh-lg)]"
        >
          {sublabel && (
            <p className="border-b border-edge px-3.5 py-2.5 text-[11px] leading-snug text-faint">
              {sublabel}
            </p>
          )}
          {groups.map((group, gi) => (
            <div key={gi} className={gi > 0 ? "border-t border-edge" : ""}>
              {group.map((item) => (
                <button
                  key={item.label}
                  role="menuitem"
                  onClick={() => {
                    setOpen(false);
                    item.onClick();
                  }}
                  className={`flex w-full items-center gap-2.5 px-3.5 py-2.5 text-left text-xs transition-colors hover:bg-panel-2 ${
                    item.active ? "text-accent" : "text-ink"
                  }`}
                >
                  <span className="shrink-0 text-accent">{item.icon}</span>
                  <span className="min-w-0">
                    <span className="block truncate">{item.label}</span>
                    {item.detail && (
                      <span className="block truncate text-[10px] text-faint">{item.detail}</span>
                    )}
                  </span>
                </button>
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
