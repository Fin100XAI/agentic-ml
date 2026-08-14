import { useCallback, useRef, useState } from "react";
import { FileSpreadsheet, Upload } from "lucide-react";
import { Button, Card, CardBody, Spinner } from "../ui";

export function UploadScreen({
  onSubmit,
  busy,
}: {
  onSubmit: (file: File, question: string) => void;
  busy: boolean;
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
          <div
            className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-12 transition-colors ${
              dragOver ? "border-accent bg-accent-soft/30" : "border-edge hover:border-accent/60"
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
              What do you want to understand from this data? (optional — you can refine later)
            </span>
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              rows={2}
              placeholder='e.g. "Which customers are likely to churn?" or "Forecast next quarter sales"'
              className="mt-1.5 w-full resize-none rounded-lg border border-edge bg-panel-2 px-3 py-2 text-sm outline-none placeholder:text-ink-dim/60 focus:border-accent"
            />
          </label>

          <div className="mt-5 flex justify-end">
            {busy ? (
              <Spinner label="Uploading & profiling…" />
            ) : (
              <Button disabled={!file} onClick={() => file && onSubmit(file, question)}>
                Upload & start analysis
              </Button>
            )}
          </div>
        </CardBody>
      </Card>
    </div>
  );
}
