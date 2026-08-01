import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Outlet, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import type { Project, ProjectPaper } from "../api/types";
import { DocumentsPage } from "./DocumentsPage";

const project = {
  id: "prj_test",
  name: "Systems review",
  topic: "distributed systems",
  research_question: "How are systems evaluated?",
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
  created_at: "2026-07-31T00:00:00Z",
  updated_at: "2026-07-31T00:00:00Z",
  stats: {
    total: 1,
    documents: 0
  }
} satisfies Project;

const candidate = {
  id: 7,
  evidence_id: "P007",
  screening_status: "included",
  paper: {
    paper_id: "P007",
    title: "Repeatable systems evaluation"
  }
} as ProjectPaper;

function ProjectOutlet() {
  return <Outlet context={{ project }} />;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("DocumentsPage", () => {
  it("keeps the paper preselected when uploading from full-text review", async () => {
    vi.spyOn(api, "listDocuments").mockResolvedValue([]);
    vi.spyOn(api, "listPapers").mockResolvedValue([candidate]);
    const upload = vi.spyOn(api, "uploadDocument").mockResolvedValue({
      id: "doc_test",
      project_id: project.id,
      filename: "paper.txt",
      sha256: "abc",
      media_type: "text/plain",
      page_count: 1,
      paper_id: candidate.id,
      created_at: "2026-07-31T00:00:00Z"
    });
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } }
    });

    const { container } = render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/documents?paper_id=7"]}>
          <Routes>
            <Route element={<ProjectOutlet />}>
              <Route path="/documents" element={<DocumentsPage />} />
            </Route>
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );

    expect(
      await screen.findByDisplayValue("P007 · Repeatable systems evaluation")
    ).toBeInTheDocument();
    const file = new File(["full report"], "paper.txt", {
      type: "text/plain"
    });
    const input = container.querySelector<HTMLInputElement>(
      'input[type="file"]'
    );
    expect(input).not.toBeNull();
    fireEvent.change(input!, { target: { files: [file] } });

    await waitFor(() => {
      expect(upload).toHaveBeenCalledWith(project.id, file, candidate.id);
    });
  });
});
