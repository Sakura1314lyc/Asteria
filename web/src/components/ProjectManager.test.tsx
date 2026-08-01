import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import type { Project } from "../api/types";
import { ProjectManager } from "./ProjectManager";

const project = {
  id: "prj_lifecycle",
  name: "Agent lifecycle review",
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
  stats: { total: 5, documents: 1 },
  runs: []
} satisfies Project;

function renderManager() {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false }
    }
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ProjectManager project={project} />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ProjectManager", () => {
  it("updates project metadata and reports success", async () => {
    const update = vi.spyOn(api, "updateProject").mockResolvedValue({
      ...project,
      name: "Updated agent review"
    });
    renderManager();
    fireEvent.click(screen.getByRole("button", { name: "编辑项目" }));
    fireEvent.change(screen.getByLabelText("项目名称"), {
      target: { value: "Updated agent review" }
    });
    fireEvent.click(screen.getByRole("button", { name: "保存修改" }));

    await waitFor(() => {
      expect(update).toHaveBeenCalledWith(
        project.id,
        expect.objectContaining({ name: "Updated agent review" })
      );
    });
    expect(await screen.findByText("项目资料已更新")).toBeInTheDocument();
  });

  it("requires the exact project name before permanent deletion", async () => {
    const remove = vi.spyOn(api, "deleteProject").mockResolvedValue({
      deleted: true,
      project_id: project.id,
      runs: 0,
      documents: 1,
      papers: 5,
      conversations: 0,
      files_removed: true
    });
    renderManager();
    fireEvent.click(screen.getByRole("button", { name: "编辑项目" }));
    fireEvent.click(screen.getByRole("button", { name: "删除项目" }));
    const deleteButton = screen.getByRole("button", { name: "永久删除" });
    expect(deleteButton).toBeDisabled();
    fireEvent.change(
      screen.getByLabelText(/输入 Agent lifecycle review 以确认/),
      { target: { value: project.name } }
    );
    expect(deleteButton).toBeEnabled();
    fireEvent.click(deleteButton);

    await waitFor(() => {
      expect(remove).toHaveBeenCalledWith(project.id, project.name);
    });
  });
});
