// Rough expected-duration hints for every waiting point, scaled to data size.
// These are honest ranges, not promises - better than an anonymous spinner.

function size(rows: number): "s" | "m" | "l" {
  if (rows < 5_000) return "s";
  if (rows < 50_000) return "m";
  return "l";
}

export function eta(stage: string, rows: number, llm: boolean): string {
  const s = size(rows);
  switch (stage) {
    case "profiling":
      return s === "s" ? "usually a few seconds" : s === "m" ? "usually 5-15 s" : "usually 15-60 s";
    case "analyzing":
      return llm ? "usually 10-30 s" : "a moment";
    case "recommend":
      return llm ? "usually 10-25 s" : "a few seconds";
    case "train":
      return s === "s" ? "usually 5-20 s" : s === "m" ? "usually 20-60 s" : "may take 1-3 min";
    case "compare":
      return s === "s" ? "usually 20-90 s" : s === "m" ? "usually 1-3 min" : "may take several minutes";
    case "autotune":
      return s === "s" ? "usually 1-2 min" : s === "m" ? "usually 2-4 min" : "may take 5+ min";
    case "ask":
      return "usually 5-15 s";
    default:
      return "";
  }
}
