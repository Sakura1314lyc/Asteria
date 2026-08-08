import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Project } from "../api/types";
import { EvidenceSignal } from "./EvidenceSignal";

const project = {
  id: "project-1",
  name: "Agent review",
  topic: "research agents",
  research_question: "How are research agents evaluated?",
  review_type: "systematic",
  language: "zh-CN",
  protocol: {
    review_type: "systematic",
    population: [],
    intervention: [],
    comparison: [],
    outcomes: [],
    include_keywords: [],
    exclude_keywords: [],
    year_from: null,
    year_to: null,
    languages: [],
    study_types: [],
    notes: ""
  },
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
  stats: { total: 8, documents: 0 },
  reports: [],
  runs: [
    {
      id: "run-1",
      project_id: "project-1",
      status: "waiting_for_screening",
      stage: "searched",
      artifacts_available: false,
      config: {},
      error: "",
      created_at: "2026-08-01T00:00:00Z",
      updated_at: "2026-08-01T00:00:00Z"
    }
  ]
} satisfies Project;

describe("EvidenceSignal", () => {
  it("derives the signal from real project stages", () => {
    const { container } = render(<EvidenceSignal projects={[project]} />);

    expect(
      screen.getByLabelText(
        "项目证据信号：方案100%，检索100%，筛选0%，证据0%，报告0%"
      )
    ).toBeInTheDocument();
    expect(container.querySelector("g.is-active")).toBeInTheDocument();
  });
});
