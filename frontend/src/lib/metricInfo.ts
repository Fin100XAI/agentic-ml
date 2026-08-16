// Plain-language explanations for every metric the platform can show.
// Written for people with no ML background.

export interface MetricInfo {
  label: string;
  explain: string;
  good: "higher" | "lower" | "context";
}

export const METRIC_INFO: Record<string, MetricInfo> = {
  accuracy: {
    label: "Accuracy",
    explain: "Out of all predictions, how many were correct. 0.80 means 8 out of 10 right.",
    good: "higher",
  },
  precision: {
    label: "Precision",
    explain:
      'When the model says "yes", how often it is actually right. High precision = few false alarms.',
    good: "higher",
  },
  recall: {
    label: "Recall",
    explain:
      'Of all the real "yes" cases, how many the model caught. High recall = few missed cases.',
    good: "higher",
  },
  f1: {
    label: "F1 score",
    explain:
      "A single score balancing precision and recall. Useful when catching cases and avoiding false alarms both matter.",
    good: "higher",
  },
  roc_auc: {
    label: "ROC AUC",
    explain:
      "How well the model separates the two groups. 0.5 = coin flip, 1.0 = perfect separation. Above 0.8 is usually good.",
    good: "higher",
  },
  n_train: { label: "Training rows", explain: "Rows used to teach the model.", good: "context" },
  n_test: {
    label: "Test rows",
    explain: "Rows held back and never shown during training - used to score the model fairly.",
    good: "context",
  },
  silhouette: {
    label: "Silhouette",
    explain:
      "How cleanly separated the groups are, from -1 to 1. Above 0.5 = clear groups; near 0 = groups overlap.",
    good: "higher",
  },
  davies_bouldin: {
    label: "Davies-Bouldin",
    explain: "Another separation score - smaller means tighter, better-separated groups.",
    good: "lower",
  },
  inertia: {
    label: "Inertia",
    explain: "Total distance of points from their group center. Only comparable between runs on the same data.",
    good: "lower",
  },
  n_clusters_found: {
    label: "Groups found",
    explain: "How many distinct groups the algorithm identified in your data.",
    good: "context",
  },
  n_noise_points: {
    label: "Noise points",
    explain: "Rows that didn't fit any group - potential outliers or unusual records worth a look.",
    good: "context",
  },
  mae: {
    label: "MAE",
    explain:
      "Mean absolute error: on average, how far off each forecast was, in the same units as your data.",
    good: "lower",
  },
  rmse: {
    label: "RMSE",
    explain: "Like MAE but punishes big misses more. Useful when large errors are costly.",
    good: "lower",
  },
  mape_pct: {
    label: "MAPE %",
    explain:
      "Average forecast error as a percentage. Under 10% is excellent, 10-25% is usable, above that is rough.",
    good: "lower",
  },
  r2: {
    label: "R²",
    explain:
      "Share of the outcome's variation the model explains. 1.0 = perfect, 0 = no better than guessing the average. Above 0.7 is usually strong.",
    good: "higher",
  },
  n_observations: { label: "Observations", explain: "Number of points in your time series.", good: "context" },
  holdout_size: {
    label: "Holdout size",
    explain: "The last chunk of history hidden from the model to test its forecasts honestly.",
    good: "context",
  },
};

export function metricInfo(key: string): MetricInfo {
  return (
    METRIC_INFO[key] ?? {
      label: key.replace(/_/g, " "),
      explain: "",
      good: "context",
    }
  );
}

// Plain-language descriptions of what each use case is for.
export const USE_CASE_INFO: Record<
  string,
  { title: string; tagline: string; example: string; icon: string }
> = {
  classification: {
    title: "Classification",
    tagline: "Predict a category for each row",
    example: '"Will this customer churn?" · "Is this transaction fraud?"',
    icon: "🎯",
  },
  regression: {
    title: "Regression",
    tagline: "Predict a numeric amount for each row",
    example: '"What will this house sell for?" · "Estimate next month\'s bill"',
    icon: "📐",
  },
  clustering: {
    title: "Clustering",
    tagline: "Discover natural groups in your data",
    example: '"What customer segments do we have?" · "Which records are outliers?"',
    icon: "🧩",
  },
  forecasting: {
    title: "Forecasting",
    tagline: "Predict future values from history",
    example: '"What will sales look like next quarter?" · "Forecast demand"',
    icon: "📈",
  },
};
