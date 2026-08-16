import type { ActivityEvent, ArtifactInfo, ModelInfo, Run, RunSummary, UploadResponse } from "../types";

const BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      /* keep statusText */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  health: () => request<{ status: string; llm_enabled: boolean; model: string }>("/health"),

  uploadDataset: (file: File, sheet?: string, join?: object) => {
    const form = new FormData();
    form.append("file", file);
    if (sheet) form.append("sheet", sheet);
    if (join) form.append("join", JSON.stringify(join));
    return request<UploadResponse>("/datasets", { method: "POST", body: form });
  },

  listModels: () => request<{ models: ModelInfo[] }>("/models"),

  startRun: (dataset_id: string, question: string) =>
    request<Run>("/runs", json({ dataset_id, question })),

  runEda: (id: string) => request<Run>(`/runs/${id}/eda`, { method: "POST" }),

  getRun: (id: string) => request<Run>(`/runs/${id}`),

  approveEda: (id: string, comment: string) =>
    request<Run>(`/runs/${id}/approve-eda`, json({ comment })),

  approveConfig: (
    id: string,
    body: {
      model_key: string;
      hyperparams: Record<string, unknown>;
      target: string | null;
      features: string[] | null;
      time_column: string | null;
      feature_ids?: string[] | null;
    },
  ) => request<Run>(`/runs/${id}/approve-config`, json(body)),

  execute: (id: string) => request<Run>(`/runs/${id}/execute`, { method: "POST" }),

  compare: (id: string, target: string | null, time_column: string | null) =>
    request<Run>(`/runs/${id}/compare`, json({ target, time_column })),

  autotune: (id: string, target: string | null, time_column: string | null, n_candidates?: number) =>
    request<Run>(`/runs/${id}/autotune`, json({ target, time_column, n_candidates })),

  ask: (id: string, question: string, history: { q: string; a: string }[]) =>
    request<{ answer: string; generated_by: string }>(
      `/runs/${id}/ask`,
      json({ question, history }),
    ),

  listRuns: () => request<{ runs: RunSummary[] }>("/runs"),

  piiReview: (datasetId: string, actions: Record<string, string>) =>
    request<{ dataset_id: string; pii_status: string; masked: boolean }>(
      `/datasets/${datasetId}/pii-review`,
      json({ actions }),
    ),

  getLineage: (artifactId: string) =>
    request<{ lineage: ArtifactInfo[] }>(`/artifacts/${artifactId}/lineage`),

  getActivity: (params: { run_id?: string; event_type?: string; limit?: number }) => {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v != null).map(([k, v]) => [k, String(v)]),
    );
    return request<{ events: ActivityEvent[] }>(`/activity?${qs}`);
  },

  activityCsvUrl: (params: { run_id?: string; event_type?: string }) => {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v != null).map(([k, v]) => [k, String(v)]),
    );
    return `${BASE}/activity.csv?${qs}`;
  },

  downloadReport: (id: string, filename: string) =>
    downloadFile(`/runs/${id}/report`, filename),

  downloadReportPdf: (id: string) =>
    downloadFile(`/runs/${id}/report.pdf`, `decision-brief-${id}.pdf`),
};

async function downloadFile(path: string, filename: string) {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error("Could not generate report.");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
