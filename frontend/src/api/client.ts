import type { ModelInfo, Run, UploadResponse } from "../types";

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

  uploadDataset: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<UploadResponse>("/datasets", { method: "POST", body: form });
  },

  listModels: () => request<{ models: ModelInfo[] }>("/models"),

  startRun: (dataset_id: string, question: string) =>
    request<Run>("/runs", json({ dataset_id, question })),

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
    },
  ) => request<Run>(`/runs/${id}/approve-config`, json(body)),

  execute: (id: string) => request<Run>(`/runs/${id}/execute`, { method: "POST" }),
};
