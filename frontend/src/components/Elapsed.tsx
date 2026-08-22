// Live elapsed timer + expected duration + cannot-stop notice for long waits.
import { useEffect, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { Thinking } from "./ui";

export function Elapsed({ running }: { running: boolean }) {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    if (!running) return;
    setSeconds(0);
    const t = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [running]);
  const mm = Math.floor(seconds / 60);
  const ss = String(seconds % 60).padStart(2, "0");
  return (
    <span className="tabular-nums">
      {mm}:{ss}
    </span>
  );
}

export function BusyStatus({
  running,
  label,
  expected,
  cannotStop = true,
}: {
  running: boolean;
  label: string;
  expected: string;
  cannotStop?: boolean;
}) {
  if (!running) return null;
  return (
    <div className="flex flex-col items-center gap-2 py-2">
      {/* Deliberating dots rather than a spinner: this wait is an agent
          reasoning and a model training, not a page loading. */}
      <Thinking label={label} />
      <div className="text-xs text-ink-dim">
        elapsed <Elapsed running={running} /> · {expected}
      </div>
      {cannotStop && (
        <div className="flex items-center gap-1.5 rounded-full border border-warn/30 bg-warn/10 px-3 py-1 text-[11px] text-warn">
          <AlertTriangle className="h-3 w-3" />
          This step can't be stopped midway - please keep the tab open
        </div>
      )}
    </div>
  );
}
