import { useCallback, useRef, useState } from "react";
import { Bot, Check, FileSpreadsheet, ScanSearch, Upload } from "lucide-react";
import { Button, Card, CardBody } from "../ui";

type Stage = "uploading" | "profiling" | "analyzing" | null;

const STAGES: { key: Exclude<Stage, null>; icon: typeof Upload; label: string; sub: string }[] = [
  { key: "uploading", icon: Upload, label: "Uploading your file", sub: "Reading the CSV" },
  { key: "profiling", icon: ScanSearch, label: "Profiling the data", sub: "Column types, ranges, missing values, relationships" },
  { key: "analyzing", icon: Bot, label: "AI agent analyzing", sub: "Understanding what your data is about, writing findings" },
];

function ProgressPanel({ stage }: { stage: Exclude<Stage, null> }) {
  const activeIdx = STAGES.findIndex((s) => s.key === stage);
  return (
    <div className="py-4">
      <h3 className="mb-5 text-center text-sm font-semibold">Working on your data…</h3>
      <div className="mx-auto max-w-sm space-y-4">
        {STAGES.map((s, i) => {
          const done = i < activeIdx;
          const active = i === activeIdx;
          return (
            <div key={s.key} className="flex items-start gap-3">
              <div
                className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full border transition-colors ${
                  done
                    ? "border-good/40 bg-good/10 text-good"
                    : active
                      ? "border-accent/50 bg-accent-soft text-accent"
                      : "border-edge bg-panel-2 text-ink-dim/50"
                }`}
              >
                {done ? (
                  <Check className="h-4 w-4" />
                ) : active ? (
                  <span className="h-4 w-4 animate-spin rounded-full border-2 border-accent/30 border-t-accent" />
                ) : (
                  <s.icon className="h-4 w-4" />
                )}
              </div>
              <div className="min-w-0 pt-0.5">
                <div className={`text-sm font-medium ${active ? "text-ink" : done ? "text-ink-dim" : "text-ink-dim/60"}`}>
                  {s.label}
                  {done && <span className="ml-2 text-[11px] text-good">done</span>}
                </div>
                <div className="text-[11px] leading-snug text-ink-dim">{s.sub}</div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function UploadScreen({
  onSubmit,
  busy,
  stage,
}: {
  onSubmit: (file: File, question: string) => void;
  busy: boolean;
  stage: Stage;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [question, setQuestion] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const pick = useCallback((f: File | undefined | null) => {
    if (f && f.name.toLowerCase().endsWith(".csv")) setFile(f);
  }, []);

  return (
    <div className="mx-auto max-w-2xl">
      <Card>
        <CardBody className="py-8">
          {busy && stage ? (
            <ProgressPanel stage={stage} />
          ) : (
            <>
              <div
                className={`flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-12 transition-colors ${
                  dragOver ? "border-accent bg-accent-soft/40" : "border-edge hover:border-accent/50"
                }`}
                onClick={() => inputRef.current?.click()}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragOver(true);
                }}
                onDragLeave={() => setDragOver(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragOver(false);
                  pick(e.dataTransfer.files?.[0]);
                }}
              >
                <input
                  ref={inputRef}
                  type="file"
                  accept=".csv"
                  className="hidden"
                  onChange={(e) => pick(e.target.files?.[0])}
                />
                {file ? (
                  <>
                    <FileSpreadsheet className="mb-3 h-10 w-10 text-good" />
                    <p className="text-sm font-medium">{file.name}</p>
                    <p className="mt-1 text-xs text-ink-dim">
                      {(file.size / 1024).toFixed(1)} KB — click to change
                    </p>
                  </>
                ) : (
                  <>
                    <Upload className="mb-3 h-10 w-10 text-ink-dim" />
                    <p className="text-sm font-medium">Drop a CSV here, or click to browse</p>
                    <p className="mt-1 text-xs text-ink-dim">
                      Any industry, any tabular data — the agents will figure it out
                    </p>
                  </>
                )}
              </div>

              <label className="mt-6 block">
                <span className="text-xs font-medium text-ink-dim">
                  What decision are you trying to make? (optional — you can refine later)
                </span>
                <textarea
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  rows={2}
                  placeholder='e.g. "Which customers should we focus retention on?" or "How much stock will we need next quarter?"'
                  className="mt-1.5 w-full resize-none rounded-xl border border-edge bg-panel-2 px-3 py-2 text-sm outline-none backdrop-blur placeholder:text-ink-dim/60 focus:border-accent"
                />
              </label>

              <div className="mt-5 flex justify-end">
                <Button disabled={!file || busy} onClick={() => file && onSubmit(file, question)}>
                  Upload & start analysis
                </Button>
              </div>
            </>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
