import type {
  Artifact,
  AgentProfile,
  BibliographyImportResult,
  Capabilities,
  Conversation,
  CsAnalysis,
  DocumentRecord,
  FullTextWorkspace,
  Job,
  LiteratureGraph,
  ModelConnection,
  Project,
  ProjectPaper,
  PrismaFlow,
  ReportPayload,
  ResearchBundle,
  ReviewProtocol,
  Run,
  RunEvent,
  SearchHit,
  ScreeningConfig,
  ScreeningWorkspace,
  Taxonomy,
  TaxonomyMatch
} from "./types";
import { PUBLIC_DEMO, PUBLIC_DEMO_MESSAGE } from "../deployment";

const API_BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method ?? "GET").toUpperCase();
  if (PUBLIC_DEMO && !["GET", "HEAD", "OPTIONS"].includes(method)) {
    throw new ApiError(403, PUBLIC_DEMO_MESSAGE);
  }
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers:
      init?.body instanceof FormData
        ? init.headers
        : {
            "Content-Type": "application/json",
            ...init?.headers
          }
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const payload = (await response.json()) as { detail?: string };
      detail = payload.detail || detail;
    } catch {
      // The fallback includes the HTTP status and is still actionable.
    }
    throw new ApiError(response.status, detail);
  }
  return response.json() as Promise<T>;
}

function queryString(values: Record<string, string | number | undefined>) {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== "") {
      params.set(key, String(value));
    }
  });
  const result = params.toString();
  return result ? `?${result}` : "";
}

export const api = {
  health: () =>
    request<{
      status: string;
      version: string;
      specialization: string;
      web_available: boolean;
    }>("/health"),

  capabilities: () => request<Capabilities>("/capabilities"),

  taxonomy: () => request<Taxonomy>("/taxonomy"),

  listAgents: () => request<AgentProfile[]>("/agents"),

  listConnections: () => request<ModelConnection[]>("/connections"),

  createConnection: (payload: {
    name: string;
    base_url: string;
    model: string;
    api_format: "responses" | "chat_completions";
    api_key: string;
  }) =>
    request<ModelConnection>("/connections", {
      method: "POST",
      body: JSON.stringify(payload)
    }),

  deleteConnection: (connectionId: string) =>
    request<{ deleted: boolean }>(
      `/connections/${encodeURIComponent(connectionId)}`,
      { method: "DELETE" }
    ),

  testConnection: (connectionId: string) =>
    request<{ ok: boolean; model: string; api_format: string }>(
      `/connections/${encodeURIComponent(connectionId)}/test`,
      { method: "POST" }
    ),

  classify: (text: string, limit = 4) =>
    request<TaxonomyMatch[]>("/taxonomy/classify", {
      method: "POST",
      body: JSON.stringify({ text, limit })
    }),

  listProjects: () => request<Project[]>("/projects"),

  getProject: (projectId: string) =>
    request<Project>(`/projects/${encodeURIComponent(projectId)}`),

  createProject: (payload: {
    name: string;
    topic: string;
    research_question: string;
    review_type: string;
    language: string;
  }) =>
    request<Project>("/projects", {
      method: "POST",
      body: JSON.stringify(payload)
    }),

  updateProtocol: (projectId: string, protocol: ReviewProtocol) =>
    request<Project>(`/projects/${encodeURIComponent(projectId)}/protocol`, {
      method: "PUT",
      body: JSON.stringify(protocol)
    }),

  startRun: (
    projectId: string,
    payload: {
      demo: boolean;
      stop_for_screening?: boolean | null;
      agent_id?: string;
      connection_id?: string | null;
    }
  ) =>
    request<{ run_id: string; job_id: string; status: string }>(
      `/projects/${encodeURIComponent(projectId)}/runs`,
      {
        method: "POST",
        body: JSON.stringify(payload)
      }
    ),

  getRun: (runId: string) =>
    request<Run>(`/runs/${encodeURIComponent(runId)}`),

  getRunEvents: (runId: string, after = 0) =>
    request<RunEvent[]>(
      `/runs/${encodeURIComponent(runId)}/events${queryString({ after })}`
    ),

  getResearch: (runId: string) =>
    request<ResearchBundle>(`/runs/${encodeURIComponent(runId)}/research`),

  getReport: (runId: string) =>
    request<ReportPayload>(`/runs/${encodeURIComponent(runId)}/report`),

  getGraph: (runId: string) =>
    request<LiteratureGraph>(`/runs/${encodeURIComponent(runId)}/graph`),

  getCsAnalysis: (runId: string) =>
    request<CsAnalysis>(`/runs/${encodeURIComponent(runId)}/cs-analysis`),

  listArtifacts: (runId: string) =>
    request<Artifact[]>(`/runs/${encodeURIComponent(runId)}/artifacts`),

  listJobs: () => request<Job[]>("/jobs"),

  getJob: (jobId: string) =>
    request<Job>(`/jobs/${encodeURIComponent(jobId)}`),

  listPapers: (projectId: string, status?: string) =>
    request<ProjectPaper[]>(
      `/projects/${encodeURIComponent(projectId)}/papers${queryString({
        status
      })}`
    ),

  importBibliography: (projectId: string, file: File) => {
    const data = new FormData();
    data.append("file", file);
    return request<BibliographyImportResult>(
      `/projects/${encodeURIComponent(projectId)}/bibliography`,
      { method: "POST", body: data }
    );
  },

  saveScreening: (
    projectId: string,
    decisions: Array<{
      paper_id: number;
      status: string;
      reason: string;
      reviewer: string;
    }>
  ) =>
    request<{ updated: number }>(
      `/projects/${encodeURIComponent(projectId)}/screening`,
      {
        method: "POST",
        body: JSON.stringify({ decisions })
      }
    ),

  getScreeningConfig: (projectId: string) =>
    request<ScreeningConfig>(
      `/projects/${encodeURIComponent(projectId)}/screening/config`
    ),

  updateScreeningConfig: (
    projectId: string,
    payload: {
      mode: "single" | "dual";
      reviewers: string[];
      blind: boolean;
    }
  ) =>
    request<ScreeningConfig>(
      `/projects/${encodeURIComponent(projectId)}/screening/config`,
      {
        method: "PUT",
        body: JSON.stringify(payload)
      }
    ),

  getScreeningWorkspace: (projectId: string, reviewer?: string) =>
    request<ScreeningWorkspace>(
      `/projects/${encodeURIComponent(projectId)}/screening/workspace${queryString({
        reviewer
      })}`
    ),

  resolveScreening: (
    projectId: string,
    paperId: number,
    payload: {
      status: "included" | "excluded";
      reason: string;
      resolved_by: string;
    }
  ) =>
    request<import("./types").ScreeningResolution>(
      `/projects/${encodeURIComponent(projectId)}/screening/${paperId}/resolve`,
      {
        method: "POST",
        body: JSON.stringify(payload)
      }
    ),

  getFullTextWorkspace: (projectId: string, reviewer?: string) =>
    request<FullTextWorkspace>(
      `/projects/${encodeURIComponent(projectId)}/screening/fulltext/workspace${queryString({
        reviewer
      })}`
    ),

  updateFullTextConfig: (
    projectId: string,
    payload: { enabled: boolean; blind: boolean }
  ) =>
    request<ScreeningConfig>(
      `/projects/${encodeURIComponent(projectId)}/screening/fulltext/config`,
      {
        method: "PUT",
        body: JSON.stringify(payload)
      }
    ),

  saveFullTextRetrieval: (
    projectId: string,
    paperId: number,
    payload: {
      status: "not_requested" | "sought" | "retrieved" | "not_retrieved";
      reason: string;
      updated_by: string;
    }
  ) =>
    request<{
      paper_id: number;
      status: string;
      reason: string;
      updated_by: string;
      updated_at: string;
    }>(
      `/projects/${encodeURIComponent(projectId)}/screening/fulltext/${paperId}/retrieval`,
      { method: "POST", body: JSON.stringify(payload) }
    ),

  saveFullTextScreening: (
    projectId: string,
    decisions: Array<{
      paper_id: number;
      status: string;
      reason: string;
      exclusion_code: string;
      reviewer: string;
    }>
  ) =>
    request<{ updated: number }>(
      `/projects/${encodeURIComponent(projectId)}/screening/fulltext`,
      {
        method: "POST",
        body: JSON.stringify({ decisions })
      }
    ),

  resolveFullTextScreening: (
    projectId: string,
    paperId: number,
    payload: {
      status: "included" | "excluded";
      reason: string;
      exclusion_code: string;
      resolved_by: string;
    }
  ) =>
    request<import("./types").ScreeningResolution>(
      `/projects/${encodeURIComponent(projectId)}/screening/fulltext/${paperId}/resolve`,
      { method: "POST", body: JSON.stringify(payload) }
    ),

  getPrismaFlow: (projectId: string) =>
    request<PrismaFlow>(
      `/projects/${encodeURIComponent(projectId)}/prisma`
    ),

  continueRun: (
    runId: string,
    demo: boolean,
    connectionId?: string,
    agentId?: string
  ) =>
    request<{ run_id: string; job_id: string; status: string }>(
      `/runs/${encodeURIComponent(runId)}/continue${queryString({
        demo: demo ? "true" : "false",
        connection_id: connectionId,
        agent_id: agentId
      })}`,
      { method: "POST" }
    ),

  listDocuments: (projectId: string) =>
    request<DocumentRecord[]>(
      `/projects/${encodeURIComponent(projectId)}/documents`
    ),

  uploadDocument: (projectId: string, file: File, paperId?: number) => {
    const data = new FormData();
    data.append("file", file);
    return request<DocumentRecord>(
      `/projects/${encodeURIComponent(projectId)}/documents${queryString({
        paper_id: paperId
      })}`,
      { method: "POST", body: data }
    );
  },

  searchDocuments: (projectId: string, query: string, limit = 20) =>
    request<SearchHit[]>(
      `/projects/${encodeURIComponent(projectId)}/documents/search${queryString({
        q: query,
        limit
      })}`
    ),

  listConversations: (projectId: string) =>
    request<Conversation[]>(
      `/projects/${encodeURIComponent(projectId)}/conversations`
    ),

  createConversation: (
    projectId: string,
    payload: {
      title: string;
      agent_id: string;
      connection_id?: string | null;
      demo: boolean;
    }
  ) =>
    request<Conversation>(
      `/projects/${encodeURIComponent(projectId)}/conversations`,
      { method: "POST", body: JSON.stringify(payload) }
    ),

  getConversation: (conversationId: string) =>
    request<Conversation>(
      `/conversations/${encodeURIComponent(conversationId)}`
    ),

  sendMessage: (
    conversationId: string,
    payload: {
      content: string;
      agent_id?: string;
      connection_id?: string;
      demo?: boolean;
    }
  ) =>
    request<{
      user_message: import("./types").ChatMessage;
      assistant_message: import("./types").ChatMessage;
    }>(`/conversations/${encodeURIComponent(conversationId)}/messages`, {
      method: "POST",
      body: JSON.stringify(payload)
    })
};

export function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}
