import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  BookCheck,
  Plus,
  Sparkles
} from "lucide-react";
import { Link, useNavigate } from "react-router";
import { api } from "../api/client";
import type { Project, Run } from "../api/types";
import { PUBLIC_DEMO } from "../deployment";
import { EvidenceSignal } from "../components/EvidenceSignal";
import { RunStageRail } from "../components/RunStageRail";
import {
  Button,
  EmptyState,
  ErrorState,
  LoadingState,
  SectionTitle,
  Stat,
  StatusBadge,
  reviewTypeLabel
} from "../components/Ui";

function latestRun(project: Project): Run | undefined {
  return project.runs?.[0];
}

export function DashboardPage() {
  const navigate = useNavigate();
  const projects = useQuery({
    queryKey: ["projects"],
    queryFn: api.listProjects
  });
  const jobs = useQuery({
    queryKey: ["jobs"],
    queryFn: api.listJobs,
    refetchInterval: (state) =>
      state.state.data?.some((job) =>
        ["queued", "running"].includes(job.status)
      )
        ? 2000
        : false
  });

  if (projects.isLoading) return <LoadingState label="正在恢复你的研究工作台" />;
  if (projects.isError) {
    return <ErrorState error={projects.error} retry={() => projects.refetch()} />;
  }

  const items = projects.data ?? [];
  const totalPapers = items.reduce(
    (sum, project) => sum + (project.stats?.total ?? 0),
    0
  );
  const pending = items.reduce(
    (sum, project) => sum + (project.stats?.pending ?? 0),
    0
  );
  const activeJobs =
    jobs.data?.filter((job) => ["queued", "running"].includes(job.status)) ?? [];
  const priorityProject = items.find((project) => (project.stats.pending ?? 0) > 0);

  return (
    <div className="dashboard page-pad">
      <header className="dashboard-hero">
        <div className="dashboard-hero__copy">
          <span className="dashboard-hero__kicker">
            Asteria Observatory / CS Evidence
          </span>
          <h1>把检索，变成可复核的证据。</h1>
          <p>
            {activeJobs.length > 0
              ? `${activeJobs.length} 个研究任务正在运行`
              : pending > 0
                ? `${pending} 篇候选论文正在等待人工判断。`
                : "从研究问题到最终报告，每一步都保留来源、判断与可恢复状态。"}
          </p>
          <div className="dashboard-hero__actions">
            <Button
              disabled={PUBLIC_DEMO}
              title={PUBLIC_DEMO ? "公开观测站为只读样例" : undefined}
              onClick={() =>
                navigate("/projects?new=1", { viewTransition: true })
              }
            >
              <Plus size={16} /> 新建研究
            </Button>
            <Button
              variant="secondary"
              onClick={() => navigate("/projects", { viewTransition: true })}
            >
              全部项目
            </Button>
          </div>
        </div>
        <EvidenceSignal projects={items} />
      </header>

      <section className="metric-ribbon dashboard-summary" aria-label="研究状态摘要">
        <Stat value={items.length} label="研究项目" />
        <Stat value={totalPapers} label="候选论文" />
        <Stat value={pending} label="待筛选" />
        <Stat
          value={activeJobs.length}
          label="运行中"
          hint={new Date().toLocaleDateString("zh-CN")}
        />
      </section>

      {priorityProject && (
        <Link
          className="attention-strip"
          to={`/projects/${priorityProject.id}/screening`}
          viewTransition
        >
          <BookCheck size={19} />
          <div>
            <small>下一项人工任务</small>
            <strong>{priorityProject.name}</strong>
            <span>
              {priorityProject.stats.pending} 篇待筛选；系统不会静默替你排除。
            </span>
          </div>
          <ArrowRight size={17} />
        </Link>
      )}

      <section className="dashboard-section">
        <SectionTitle
          eyebrow="Evidence ledger"
          title="继续最近的研究"
          detail="从上次停下的位置继续；每个判断都有出处。"
          action={
            <Link className="text-link" to="/projects" viewTransition>
              全部项目 <ArrowRight size={14} />
            </Link>
          }
        />
        {items.length === 0 ? (
          <EmptyState
            title="从第一个研究问题开始"
            detail="创建项目后，可以先使用内置合成语料跑通完整流程，再接入真实模型与检索源。"
            icon={<Sparkles size={23} />}
            action={
              <Button
                onClick={() =>
                  navigate("/projects?new=1", { viewTransition: true })
                }
              >
                创建研究项目
              </Button>
            }
          />
        ) : (
          <div className="research-ledger">
            {items.slice(0, 6).map((project, index) => {
              const run = latestRun(project);
              return (
                <Link
                  to={`/projects/${project.id}`}
                  className="research-ledger__row"
                  key={project.id}
                  viewTransition
                >
                  <span className="research-ledger__index">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <div className="research-ledger__main">
                    <div>
                      <h3>{project.name}</h3>
                      <p>{project.research_question}</p>
                    </div>
                    <div className="research-ledger__meta">
                      <span>{reviewTypeLabel(project.review_type)}</span>
                      <span>{project.stats.total} 篇候选</span>
                      <span>{project.stats.documents} 份全文</span>
                    </div>
                  </div>
                  <div className="research-ledger__run">
                    {run ? (
                      <>
                        <StatusBadge status={run.status}>{run.status}</StatusBadge>
                        <RunStageRail
                          current={run.stage}
                          failed={run.status === "failed"}
                          compact
                        />
                      </>
                    ) : (
                      <span className="muted">尚未运行</span>
                    )}
                  </div>
                  <ArrowRight size={17} />
                </Link>
              );
            })}
          </div>
        )}
      </section>

    </div>
  );
}
