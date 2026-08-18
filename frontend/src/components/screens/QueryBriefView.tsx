// Read-only Query Decision Brief (P2.4): the shareable, printable document.
// Every number was recomputed at creation time and every claim was checked
// by the deterministic critic; this view renders the stored brief verbatim.
import { useEffect, useState } from "react";
import { Download, FileText, ShieldCheck } from "lucide-react";
import { api } from "../../api/client";
import type { QueryBrief } from "../../types";
import { saveBlob } from "../../lib/download";
import { QueryChart } from "../QueryChart";

export function QueryBriefView({ briefId }: { briefId: string }) {
  const [brief, setBrief] = useState<QueryBrief | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getQueryBrief(briefId).then(setBrief).catch((e) =>
      setError(e instanceof Error ? e.message : String(e)));
  }, [briefId]);

  if (error) {
    return <div className="mx-auto max-w-3xl p-8 text-sm text-bad">{error}</div>;
  }
  if (!brief) {
    return <div className="mx-auto max-w-3xl p-8 text-sm text-ink-dim">Loading the brief...</div>;
  }

  const download = async (format: "markdown" | "pdf") => {
    const blob = await api.queryBriefFile(brief.id, format);
    saveBlob(blob, format === "pdf" ? "query-brief.pdf" : "query-brief.md");
  };

  return (
    <div className="min-h-full bg-page">
      <div className="mx-auto max-w-3xl space-y-5 px-6 py-8">
        <header className="border-b border-edge pb-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-accent">
                <FileText className="h-3.5 w-3.5" /> Query decision brief
              </p>
              <h1 className="font-display mt-1 text-2xl font-bold">{brief.title}</h1>
              <p className="mt-1 text-xs text-ink-dim">
                Prepared {brief.created_at} from {brief.filename} - every number recomputed
                from the data; {brief.critic.checked} claim(s) checked by the critic
                {brief.critic.flagged_claims > 0
                  ? `, ${brief.critic.flagged_claims} restated from computed values`
                  : ""}.
              </p>
            </div>
            <div className="flex gap-2 print:hidden">
              <button onClick={() => download("markdown")}
                className="flex items-center gap-1.5 rounded-lg border border-edge bg-panel px-3 py-1.5 text-xs font-medium hover:border-accent/40">
                <Download className="h-3.5 w-3.5" /> Markdown
              </button>
              <button onClick={() => download("pdf")}
                className="flex items-center gap-1.5 rounded-lg border border-edge bg-panel px-3 py-1.5 text-xs font-medium hover:border-accent/40">
                <Download className="h-3.5 w-3.5" /> PDF
              </button>
            </div>
          </div>
        </header>

        {brief.takeaway && (
          <section className="rounded-xl border border-accent/30 bg-accent-soft/20 p-4">
            <h2 className="text-[11px] font-semibold uppercase tracking-wider text-ink-dim">
              What to take away
            </h2>
            <p className="mt-1 text-sm leading-relaxed">{brief.takeaway}</p>
          </section>
        )}

        {brief.items.map((item, i) => (
          <section key={i} className="rounded-2xl border border-edge bg-panel p-4 shadow-sm">
            <h2 className="text-sm font-semibold">{i + 1}. {item.question}</h2>
            <p className="mt-2 text-sm font-medium leading-relaxed">{item.headline}</p>
            {item.meaning && (
              <p className="mt-1 text-xs italic leading-relaxed text-ink-dim">{item.meaning}</p>
            )}
            {!item.review.verified && (
              <p className="mt-1 rounded-lg border border-warn/30 bg-warn/5 px-3 py-1.5 text-[11px] text-warn">
                The critic could not verify every number in the original phrasing; the
                statement above is a computed restatement.
              </p>
            )}
            {item.caveats.length > 0 && (
              <ul className="mt-2 space-y-0.5">
                {item.caveats.slice(0, 4).map((c, j) => (
                  <li key={j} className="text-[11px] leading-relaxed text-warn">Caveat: {c}</li>
                ))}
              </ul>
            )}
            <div className="mt-3">
              <QueryChart spec={item.chart}
                result={{ table: item.table, columns: item.columns, dtypes: {},
                          row_counts: item.row_counts, excluded_null_rows: {},
                          coverage_notes: [] }} />
            </div>
            <p className="mt-2 text-[10px] leading-relaxed text-ink-dim">
              Method: {item.sentences.join(" ")}
            </p>
          </section>
        ))}

        <section className="rounded-2xl border border-edge bg-panel p-4 shadow-sm">
          <h2 className="flex items-center gap-1.5 text-sm font-semibold">
            <ShieldCheck className="h-4 w-4 text-accent" /> Data trust panel
          </h2>
          <ul className="mt-2 space-y-1">
            {brief.trust.lines.map((l, i) => (
              <li key={i} className="text-xs leading-relaxed">{l}</li>
            ))}
          </ul>
          <p className="mt-2 text-[11px] italic leading-relaxed text-ink-dim">
            {brief.trust.scope_note}
          </p>
        </section>

        <footer className="border-t border-edge pt-3 text-[10px] leading-relaxed text-ink-dim">
          Provenance: dataset {brief.provenance.artifact_id ?? brief.provenance.dataset_id};
          phrasing mode: {brief.provenance.generated_by}; the exact query plans are stored
          with this brief and every execution is in the activity log.
        </footer>
      </div>
    </div>
  );
}
