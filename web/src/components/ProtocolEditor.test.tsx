import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import type { Project } from "../api/types";
import { ProjectActivity } from "./ProjectActivity";
import { ProtocolEditor } from "./ProtocolEditor";

const project = {
  id: "prj_protocol",
  name: "Agent evidence review",
  topic: "research agents",
  research_question: "Which evaluations are reproducible?",
  review_type: "systematic",
  language: "zh-CN",
  protocol: {
    review_type: "systematic",
    population: [],
    intervention: [],
    comparison: [],
    outcomes: [],
    include_keywords: ["agent"],
    exclude_keywords: [],
    year_from: null,
    year_to: null,
    languages: ["en"],
    study_types: [],
    notes: ""
  },
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
  stats: { total: 5, documents: 0 },
  runs: []
} satisfies Project;

function renderEditor() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false }
    }
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ProtocolEditor project={project} />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ProtocolEditor", () => {
  it("requires a change and amendment reason before saving", async () => {
    const update = vi.spyOn(api, "updateProtocol").mockResolvedValue({
      ...project,
      protocol: { ...project.protocol, year_from: 2021 }
    });
    renderEditor();
    fireEvent.click(screen.getByRole("button", { name: "修订方案" }));
    const save = screen.getByRole("button", { name: "保存并记录修订" });
    expect(save).toBeDisabled();

    fireEvent.change(screen.getByLabelText("起始年份"), {
      target: { value: "2021" }
    });
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByLabelText(/^本次修订原因/), {
      target: { value: "试检索后收紧时间范围" }
    });
    expect(save).toBeEnabled();
    fireEvent.click(save);

    await waitFor(() => {
      expect(update).toHaveBeenCalledWith(
        project.id,
        expect.objectContaining({ year_from: 2021 }),
        "试检索后收紧时间范围"
      );
    });
    expect(await screen.findByText("方案修订已写入审计记录")).toBeInTheDocument();
  });
});

describe("ProjectActivity", () => {
  it("renders protocol reasons and field-level changes", () => {
    render(
      <ProjectActivity
        events={[
          {
            id: 7,
            timestamp: "2026-08-08T08:00:00Z",
            event_type: "protocol_updated",
            payload: {
              reason: "试检索后收紧时间范围",
              changes: {
                year_from: { before: null, after: 2021 },
                include_keywords: { before: ["agent"], after: ["agent", "audit"] }
              }
            }
          }
        ]}
      />
    );
    expect(screen.getByText("研究方案已修订")).toBeInTheDocument();
    expect(screen.getByText(/试检索后收紧时间范围/)).toBeInTheDocument();
    expect(screen.getByText("2021")).toBeInTheDocument();
    expect(screen.getByText("agent、audit")).toBeInTheDocument();
  });
});
