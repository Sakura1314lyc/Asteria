import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { SearchLog } from "../api/types";
import { SearchLedger } from "./SearchLedger";

const log: SearchLog = {
  schema_version: 1,
  generated_at: "2026-07-31T08:00:00Z",
  topic: "research agents",
  question: "How can they be audited?",
  configured_restrictions: {
    year_from: 2020,
    year_to: 2026,
    languages: ["en"],
    study_types: [],
    max_queries: 5,
    results_per_query: 6,
    max_papers_after_ranking: 12
  },
  summary: {
    planned_executions: 2,
    succeeded: 1,
    failed: 1,
    records_returned_before_deduplication: 4,
    unique_records_after_deduplication: 3,
    duplicates_removed: 1,
    records_selected_after_ranking: 3
  },
  executions: [
    {
      source: "openalex",
      query: "research agents",
      limit: 6,
      started_at: "2026-07-31T08:00:00Z",
      completed_at: "2026-07-31T08:00:01Z",
      duration_ms: 820,
      status: "succeeded",
      result_count: 4,
      endpoint: "https://api.openalex.org/works",
      error: ""
    },
    {
      source: "dblp",
      query: "research agents",
      limit: 6,
      started_at: "2026-07-31T08:00:00Z",
      completed_at: "2026-07-31T08:00:02Z",
      duration_ms: 2000,
      status: "failed",
      result_count: 0,
      endpoint: "https://dblp.org/search/publ/api",
      error: "temporary outage"
    }
  ],
  warnings: [],
  reporting_note: "Execution-level audit trail."
};

describe("SearchLedger", () => {
  it("shows reproducibility details and source failures", () => {
    render(<SearchLedger runId="run-1" log={log} />);

    expect(screen.getByRole("heading", { name: "检索账本" })).toBeInTheDocument();
    expect(screen.getByText("OpenAlex")).toBeInTheDocument();
    expect(screen.getByText("temporary outage")).toBeInTheDocument();
    expect(screen.getByText("2020–2026 · en")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /JSON/ })).toHaveAttribute(
      "href",
      "/runs/run-1/artifacts/search_log.json"
    );
  });
});
