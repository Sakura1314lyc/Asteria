import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Project } from "../api/types";
import { ResearchSpine } from "./ResearchSpine";

const project = {
  id: "project-1",
  name: "Agent review",
  topic: "research agents",
  research_question: "How are agents evaluated?",
  review_type: "systematic",
  language: "zh-CN",
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
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
  stats: {
    total: 5,
    documents: 2,
    pending: 2,
    included: 2,
    excluded: 1,
    maybe: 0
  },
  runs: [
    {
      id: "run-1",
      project_id: "project-1",
      status: "waiting_for_screening",
      stage: "searched",
      run_dir: "run",
      config: {},
      error: "",
      created_at: "2026-08-01T00:00:00Z",
      updated_at: "2026-08-01T00:00:00Z"
    }
  ],
  reports: []
} satisfies Project;

describe("ResearchSpine", () => {
  it("marks the human screening gate as the active phase", () => {
    render(<ResearchSpine project={project} />);

    const screening = screen.getByText("筛选").closest("li");
    expect(screening).toHaveClass("is-active");
    expect(screen.getByText("3/5 已判断")).toBeInTheDocument();
    expect(screen.getByText("检索").closest("li")).toHaveClass("is-complete");
  });
});
