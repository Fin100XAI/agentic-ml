// Shared types mirroring backend responses.

export interface UploadResponse {
  dataset_id: string;
  filename: string;
  n_rows: number;
  n_cols: number;
  columns: string[];
}

export interface ColumnProfile {
  name: string;
  role: string;
  dtype: string;
  missing_count: number;
  missing_pct: number | null;
  unique_count: number;
  sample_values: unknown[];
  stats?: {
    min: number | null;
    max: number | null;
    mean: number | null;
    std: number | null;
    median: number | null;
  };
  histogram?: { counts: number[]; edges: (number | null)[] };
  top_values?: { value: unknown; count: number }[];
}

export interface Profile {
  n_rows: number;
  n_cols: number;
  columns: ColumnProfile[];
  preview: Record<string, unknown>[];
  missingness: {
    total_missing_cells: number;
    pct_missing: number | null;
    columns_with_missing: string[];
  };
  correlations: { a: string; b: string; corr: number | null }[];
  candidate_targets: { name: string; role: string; score: number }[];
  suggested_use_cases: string[];
}

export interface Eda {
  summary: string;
  key_findings: string[];
  suggested_questions: string[];
  generated_by: string;
}

export interface RankedModel {
  key: string;
  rationale: string;
}

export interface Recommendation {
  use_case: string;
  reasoning: string;
  ranked_models: RankedModel[];
  target: string | null;
  time_column: string | null;
  generated_by: string;
}

export interface ParamSpec {
  name: string;
  label: string;
  type: "int" | "float" | "select" | "bool";
  default: unknown;
  description: string;
  min?: number;
  max?: number;
  step?: number;
  options?: (string | number)[];
}

export interface ModelInfo {
  key: string;
  name: string;
  use_case: string;
  description: string;
  strengths: string;
  param_schema: ParamSpec[];
}

export interface DecisionNode {
  stage: string;
  title: string;
  status: "pending" | "proposed" | "approved" | "done" | "error";
  agent_output: Record<string, unknown>;
  human_input: Record<string, unknown>;
  detail: string;
  timestamp: string;
}

export interface RunResult {
  metrics: Record<string, number | null>;
  artifacts: {
    confusion_matrix?: { labels: string[]; matrix: number[][] };
    feature_importance?: { feature: string; importance: number }[];
    class_distribution?: { label: string; count: number }[];
    scatter?: { points: { x: number; y: number; cluster: number }[]; axes: string[] };
    cluster_sizes?: { cluster: number; count: number }[];
    series?: { t: string; actual: number; predicted?: number }[];
    forecast?: { t: string; forecast: number }[];
  };
}

export interface Interpretation {
  summary: string;
  assessment: "strong" | "moderate" | "weak" | "inconclusive";
  highlights: string[];
  next_steps: string[];
  generated_by: string;
}

export interface Run {
  id: string;
  dataset_id: string;
  filename: string;
  question: string;
  stage: string;
  error: string | null;
  decisions: DecisionNode[];
  profile: Profile | null;
  eda: Eda | null;
  recommendation: Recommendation | null;
  config: {
    model_key: string;
    model_name: string;
    use_case: string;
    hyperparams: Record<string, unknown>;
    target: string | null;
    features: string[] | null;
    time_column: string | null;
  } | null;
  result: RunResult | null;
  interpretation: Interpretation | null;
}
