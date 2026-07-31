export type ReviewType = "narrative" | "scoping" | "systematic" | "thesis";
export type ScreeningStatus = "pending" | "included" | "excluded" | "maybe";
export type RunStatus =
  | "queued"
  | "running"
  | "waiting_for_screening"
  | "completed"
  | "failed"
  | "cancelled";

export interface ReviewProtocol {
  review_type: ReviewType;
  population: string[];
  intervention: string[];
  comparison: string[];
  outcomes: string[];
  include_keywords: string[];
  exclude_keywords: string[];
  year_from: number | null;
  year_to: number | null;
  languages: string[];
  study_types: string[];
  notes: string;
}

export interface ProjectStats {
  total: number;
  documents: number;
  pending?: number;
  included?: number;
  excluded?: number;
  maybe?: number;
}

export interface Run {
  id: string;
  project_id: string;
  status: RunStatus;
  stage: string;
  run_dir: string;
  config: Record<string, unknown>;
  error: string;
  created_at: string;
  updated_at: string;
}

export interface ReportRecord {
  id: string;
  project_id: string;
  run_id: string | null;
  title: string;
  format: string;
  version: number;
  created_at: string;
}

export interface DocumentRecord {
  id: string;
  project_id: string;
  filename: string;
  sha256: string;
  media_type: string;
  page_count: number;
  paper_id: number | null;
  created_at: string;
}

export interface Project {
  id: string;
  name: string;
  topic: string;
  research_question: string;
  review_type: ReviewType;
  language: string;
  protocol: ReviewProtocol;
  created_at: string;
  updated_at: string;
  stats: ProjectStats;
  runs?: Run[];
  reports?: ReportRecord[];
  documents?: DocumentRecord[];
}

export interface Paper {
  paper_id: string;
  title: string;
  authors: string[];
  year: number | null;
  abstract: string;
  url: string;
  doi: string;
  arxiv_id: string;
  venue: string;
  citation_count: number;
  source: string;
  open_access_url: string;
  score: number;
  categories: string[];
  publication_type: string;
  code_urls: string[];
  dataset_urls: string[];
}

export interface ProjectPaper {
  id: number;
  evidence_id: string;
  screening_status: ScreeningStatus;
  screening_reason: string;
  reviewer: string;
  tags: string[];
  decided_at: string;
  retrieval_status: RetrievalStatus;
  retrieval_reason: string;
  retrieval_updated_at: string;
  fulltext_status: ScreeningStatus;
  fulltext_reason: string;
  fulltext_exclusion_code: string;
  fulltext_reviewer: string;
  fulltext_decided_at: string;
  paper: Paper;
}

export interface ScreeningDecisionRecord {
  reviewer_id: string;
  status: ScreeningStatus;
  reason: string;
  decided_at: string;
  exclusion_code?: string;
}

export interface ScreeningResolution {
  status: "included" | "excluded";
  reason: string;
  resolved_by: string;
  resolved_at: string;
  exclusion_code?: string;
}

export interface ScreeningConfig {
  mode: "single" | "dual";
  blind: boolean;
  reviewers: string[];
  fulltext_enabled: boolean;
  fulltext_blind: boolean;
  updated_at: string;
}

export interface ScreeningPaper extends ProjectPaper {
  consensus_state:
    | "pending"
    | "agreed"
    | "conflict"
    | "awaiting_resolution"
    | "awaiting_retrieval"
    | "not_retrieved"
    | "resolved"
    | "blinded";
  my_decision: ScreeningDecisionRecord | null;
  decisions: ScreeningDecisionRecord[];
  resolution: ScreeningResolution | null;
}

export interface ScreeningWorkspace {
  config: ScreeningConfig;
  summary: {
    total: number;
    reviewer_completed: number;
    pending?: number;
    agreed?: number;
    conflict?: number;
    awaiting_resolution?: number;
    resolved?: number;
  };
  papers: ScreeningPaper[];
}

export type RetrievalStatus =
  | "not_requested"
  | "sought"
  | "retrieved"
  | "not_retrieved";

export interface FullTextDocument {
  id: string;
  paper_id: number;
  filename: string;
  page_count: number;
}

export interface FullTextPaper extends ScreeningPaper {
  retrieval_status: RetrievalStatus;
  retrieval_reason: string;
  retrieval_updated_at: string;
  fulltext_status: ScreeningStatus;
  fulltext_reason: string;
  fulltext_exclusion_code: string;
  fulltext_reviewer: string;
  fulltext_decided_at: string;
  documents: FullTextDocument[];
}

export interface FullTextWorkspace {
  config: ScreeningConfig;
  exclusion_reasons: Record<string, string>;
  summary: {
    total_candidates: number;
    not_requested: number;
    sought: number;
    retrieved: number;
    not_retrieved: number;
    reviewer_completed: number;
    pending?: number;
    agreed?: number;
    conflict?: number;
    awaiting_resolution?: number;
    resolved?: number;
  };
  papers: FullTextPaper[];
}

export interface PrismaFlow {
  identified_records: number;
  records_screened: number;
  records_excluded: number;
  reports_sought_for_retrieval: number;
  reports_not_retrieved: number;
  reports_awaiting_retrieval: number;
  reports_assessed_for_eligibility: number;
  reports_excluded_after_fulltext: number;
  fulltext_exclusion_reasons: Record<string, number>;
  studies_included_in_synthesis: number;
  fulltext_screening_enabled: boolean;
}

export interface BibliographyImportResult {
  filename: string;
  format: "ris" | "bibtex" | "csl-json";
  parsed: number;
  added: number;
  already_present: number;
  enriched: number;
  skipped: number;
  duplicates_in_file: number;
  evidence_ids: string[];
  warnings: string[];
}

export interface EvidenceCard {
  paper_id: string;
  relevance: string;
  objective: string;
  methods: string;
  data_or_sample: string;
  findings: string[];
  limitations: string[];
  confidence: string;
  cs_evidence: Record<string, unknown>;
}

export interface QualityRecord {
  paper_id: string;
  rubric: string;
  scores: Record<string, number>;
  overall: number;
  grade?: string;
  notes?: string[];
  missing?: string[];
}

export interface SearchExecution {
  source: string;
  query: string;
  limit: number;
  started_at: string;
  completed_at: string;
  duration_ms: number;
  status: "succeeded" | "failed";
  result_count: number;
  endpoint: string;
  error: string;
}

export interface SearchLog {
  schema_version: number;
  generated_at: string;
  topic: string;
  question: string;
  configured_restrictions: {
    year_from: number | null;
    year_to: number | null;
    languages: string[];
    study_types: string[];
    max_queries: number;
    results_per_query: number;
    max_papers_after_ranking: number;
  };
  summary: {
    planned_executions: number;
    succeeded: number;
    failed: number;
    records_returned_before_deduplication: number;
    unique_records_after_deduplication: number;
    duplicates_removed: number;
    records_selected_after_ranking: number;
  };
  executions: SearchExecution[];
  warnings: string[];
  reporting_note: string;
}

export interface ResearchBundle {
  run: Run;
  topic: string;
  question: string;
  stage: string;
  plan: Record<string, unknown>;
  search_log?: SearchLog;
  papers: Paper[];
  screening: Array<Record<string, unknown>>;
  evidence: EvidenceCard[];
  quality: QualityRecord[];
  cs_analysis: CsAnalysis;
  audit: CitationAudit;
  warnings: string[];
}

export interface CitationAudit {
  passed?: boolean;
  known_source_count?: number;
  cited_source_count?: number;
  paragraph_citation_coverage?: number;
  unknown_citations?: string[];
  uncited_sources?: string[];
  grounding_proxy?: {
    method: string;
    check_count: number;
    assessable_count: number;
    aligned_proxy_count: number;
    alignment_rate: number | null;
    assessment_coverage?: number | null;
    effective_alignment_rate?: number | null;
    note: string;
  };
  note?: string;
}

export interface ReportPayload {
  run_id: string;
  topic: string;
  question: string;
  markdown: string;
  audit: CitationAudit;
  updated_at: string;
}

export interface ReproducibilityRecord {
  paper_id: string;
  rubric: string;
  scores: Record<string, number>;
  overall: number;
  grade: string;
  missing: string[];
  note: string;
}

export interface CsAnalysis {
  taxonomy?: {
    version: string;
    sources: Record<string, string>;
  };
  paper_domains?: Record<string, TaxonomyMatch[]>;
  landscape?: {
    domains: Record<string, number>;
    arxiv_categories: Record<string, number>;
    contribution_types: Record<string, number>;
    evidence_levels: Record<string, number>;
    venues: Record<string, number>;
    average_reproducibility: number;
  };
  benchmark_catalog?: {
    datasets: CatalogItem[];
    metrics: CatalogItem[];
    baselines: CatalogItem[];
  };
  reproducibility?: ReproducibilityRecord[];
  research_agenda?: {
    paper_count: number;
    low_reproducibility_count: number;
    priorities: Array<{
      gap: string;
      affected_papers: number;
      rate: number;
      recommended_research: string;
    }>;
    note: string;
  };
}

export interface CatalogItem {
  name: string;
  papers?: string[];
  count?: number;
}

export interface TaxonomyMatch {
  domain_id: string;
  name_en: string;
  name_zh: string;
  score: number;
  matched_keywords: string[];
  arxiv_categories: string[];
  evidence_profile: string;
}

export interface Taxonomy {
  version: string;
  sources: Record<string, string>;
  domains: Array<{
    id: string;
    name_en: string;
    name_zh: string;
    arxiv_categories: string[];
    evidence_profile: string;
  }>;
}

export interface RunEvent {
  id: number;
  timestamp: string;
  stage: string;
  message: string;
  payload: Record<string, unknown>;
}

export interface Job {
  id: string;
  name: string;
  status: string;
  result: string | null;
  error: string;
  created_at: string;
  started_at: string;
  finished_at: string;
}

export interface Artifact {
  name: string;
  bytes: number;
  modified_at: number;
  url: string;
}

export interface LiteratureGraph {
  nodes: Array<{
    id: string;
    title: string;
    year: number | null;
    authors: string[];
    venue: string;
    citations: number;
    score: number;
  }>;
  edges: Array<{
    source: string;
    target: string;
    weight?: number;
    kind?: string;
  }>;
  meta: {
    node_count: number;
    edge_count: number;
    meaning: string;
  };
}

export interface Capabilities {
  mode: string;
  model: string;
  language: string;
  openai_configured: boolean;
  semantic_scholar_configured: boolean;
  retrievers: Record<string, boolean>;
  review_types: ReviewType[];
  max_upload_mb: number;
  authentication: boolean;
  session_credentials: boolean;
}

export interface SearchHit {
  document_id: string;
  page: number;
  chunk_id: number;
  content: string;
  rank: number;
  filename: string;
  paper_id: number | null;
}

export interface AgentProfile {
  id: string;
  name: string;
  short_name: string;
  description: string;
  instructions: string;
  capabilities: string[];
  recommended_review_types: ReviewType[];
  default_stop_for_screening: boolean;
}

export interface ModelConnection {
  id: string;
  name: string;
  base_url: string;
  model: string;
  api_format: "responses" | "chat_completions";
  provider: "openai" | "deepseek" | "openai_compatible";
  structured_output: "json_schema" | "json_object";
  notice: string;
  source: "environment" | "session";
  configured: boolean;
  created_at: string;
}

export interface ChatSource {
  id: string;
  kind: "paper" | "document";
  title: string;
  year?: number | null;
  page?: number;
  locator: string;
}

export interface ChatMessage {
  id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;
  sources: ChatSource[];
  created_at: string;
}

export interface Conversation {
  id: string;
  project_id: string;
  title: string;
  agent_id: string;
  connection_id: string;
  connection_label: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  messages?: ChatMessage[];
}
