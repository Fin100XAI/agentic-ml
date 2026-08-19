// Per-group forecast table for panel-mode forecasting: direction, accuracy
// and backtest per group, skipped groups listed with reasons, and a
// drill-down chart per group.
import { useState } from "react";
import { ChevronDown, ChevronRight, Minus, TrendingDown, TrendingUp } from "lucide-react";
import type { RunResult } from "../types";
import { ForecastChart } from "./charts";
import { Badge, Card, CardBody, CardHeader } from "./ui";

export function MultiForecastPanel({ multi }: { multi: NonNullable<RunResult["artifacts"]["multi"]> }) {
  const [open, setOpen] = useState<string | null>(null);
  const ok = multi.groups.filter((g) => g.status === "ok");
  const skipped = multi.groups.filter((g) => g.status === "skipped");

  const DirIcon = ({ d }: { d?: string }) =>
    d === "up" ? <TrendingUp className="h-3.5 w-3.5 text-good" />
    : d === "down" ? <TrendingDown className="h-3.5 w-3.5 text-bad" />
    : <Minus className="h-3.5 w-3.5 text-ink-dim" />;

  return (
    <Card>
      <CardHeader
        title={`Per-${multi.group_column} forecasts`}
        subtitle={`Each group got its own forecast; the headline chart shows the ${multi.agg === "sum" ? "total" : "average"} across them. Click a row to see that group's own history and projection.`}
        right={<Badge tone="accent">{ok.length} of {multi.groups.length} forecast</Badge>}
      />
      <CardBody>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-edge text-[10px] uppercase tracking-wider text-ink-dim">
                <th className="py-1.5 pr-3">{multi.group_column}</th>
                <th className="py-1.5 pr-3">History</th>
                <th className="py-1.5 pr-3">Direction</th>
                <th className="py-1.5 pr-3">Change</th>
                <th className="py-1.5 pr-3">MAPE</th>
                <th className="py-1.5">Backtest</th>
              </tr>
            </thead>
            <tbody>
              {ok.map((g) => (
                <>
                  <tr
                    key={g.name}
                    onClick={() => setOpen(open === g.name ? null : g.name)}
                    className="cursor-pointer border-b border-edge/40 transition-colors hover:bg-panel-2/60"
                  >
                    <td className="flex items-center gap-1 py-1.5 pr-3 font-medium">
                      {open === g.name ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                      {g.name}
                    </td>
                    <td className="py-1.5 pr-3 tabular-nums text-ink-dim">{g.n_points} pts</td>
                    <td className="py-1.5 pr-3"><DirIcon d={g.direction} /></td>
                    <td className="py-1.5 pr-3 tabular-nums">
                      {g.delta_pct != null ? `${g.delta_pct > 0 ? "+" : ""}${g.delta_pct}%` : "-"}
                    </td>
                    <td className="py-1.5 pr-3 tabular-nums">{g.mape_pct ?? "-"}%</td>
                    <td className="py-1.5">
                      {g.backtest && (
                        <Badge tone={g.backtest.verdict === "stable" ? "good" : "warn"}>
                          {g.backtest.verdict} ({g.backtest.folds.join(" / ")}%)
                        </Badge>
                      )}
                    </td>
                  </tr>
                  {open === g.name && g.series && g.forecast && (
                    <tr key={`${g.name}-chart`} className="border-b border-edge/40 bg-panel-2/60">
                      <td colSpan={6} className="px-2 py-3">
                        <ForecastChart
                          series={g.series}
                          forecast={g.forecast}
                          uncertaintyPct={g.mape_pct ?? null}
                        />
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        </div>

        {skipped.length > 0 && (
          <div className="mt-3 rounded-xl border border-warn/40 bg-warn/10 px-4 py-2.5 text-xs">
            <span className="font-semibold">
              {skipped.length} group{skipped.length !== 1 ? "s" : ""} skipped honestly:
            </span>
            <ul className="mt-1 space-y-0.5">
              {skipped.map((g) => (
                <li key={g.name} className="text-ink-dim">
                  <span className="font-medium text-ink">{g.name}</span> - {g.reason}
                </li>
              ))}
            </ul>
          </div>
        )}
      </CardBody>
    </Card>
  );
}
