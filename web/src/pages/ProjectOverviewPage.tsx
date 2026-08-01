import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  Beaker,
  Download,
  FileSearch,
  FlaskConical,
  Play,
  Bot,
  Cable,
  ShieldCheck
} from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, apiUrl } from "../api/client";
import { RunStageRail } from "../components/RunStageRail";
import { ResearchSpine } from "../components/ResearchSpine";
import {
  Button,
  reviewTypeLabel,
  SectionTitle,
  Stat,
  StatusBadge
} from "../components/Ui";
import { useProjectContext } from "../hooks/useProjectContext";

export function ProjectOverviewPage() {
  const { project } = useProjectContext();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [demo, setDemo] = useState(false);
  const agents = useQuery({ queryKey: ["agents"], queryFn: api.listAgents });
  const connections = useQuery({
    queryKey: ["connections"],
    queryFn: api.listConnections
  });
  const [agentId, setAgentId] = useState("deep_review");
  const [connectionId, setConnectionId] = useState("env-openai");
  const availableConnections =
    connections.data?.filter((connection) => connection.configured) ?? [];
  const activeConnectionId = availableConnections.some(
    (connection) => connection.id === connectionId
  )
    ? connectionId
    : (availableConnections[0]?.id ?? "env-openai");
  const start = useMutation({
    mutationFn: () =>
      api.startRun(project.id, {
        demo,
        agent_id: agentId,
        connection_id: demo ? null : activeConnectionId
      }),
    onSuccess: async ({ run_id }) => {
      await queryClient.invalidateQueries({ queryKey: ["project", project.id] });
      await queryClient.invalidateQueries({ queryKey: ["projects"] });
      navigate(`/projects/${project.id}/runs/${run_id}`, {
        viewTransition: true
      });
    }
  });
  const latest = project.runs?.[0];
  const included = project.stats.included ?? 0;
  const decided =
    included + (project.stats.excluded ?? 0) + (project.stats.maybe ?? 0);
  const screeningProgress = project.stats.total
    ? Math.round((decided / project.stats.total) * 100)
    : 0;

  return (
    <div className="overview-page">
      <section className="overview-lead">
        <div>
          <span className="eyebrow">研究问题</span>
          <h2>{project.research_question}</h2>
          <p>{project.topic}</p>
        </div>
        <div className="run-launch">
          <div className="run-launch__selectors">
            <label>
              <span>
                <Bot size={14} /> Agent
              </span>
              <select
                value={agentId}
                onChange={(event) => setAgentId(event.target.value)}
              >
                {agents.data?.filter((agent) => agent.id !== "project_qa").map((agent) => (
                  <option value={agent.id} key={agent.id}>
                    {agent.short_name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>
                <Cable size={14} /> 模型连接
              </span>
              <select
                value={activeConnectionId}
                disabled={demo}
                onChange={(event) => setConnectionId(event.target.value)}
              >
                {availableConnections.length === 0 && (
                  <option value="env-openai">尚未连接</option>
                )}
                {availableConnections.map((connection) => (
                  <option value={connection.id} key={connection.id}>
                    {connection.name} · {connection.model}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label className="switch-line">
            <input
              type="checkbox"
              checked={demo}
              onChange={(event) => setDemo(event.target.checked)}
            />
            <span>
              <strong>离线演示语料</strong>
              <small>不调用模型与网络</small>
            </span>
          </label>
          <Button
            loading={start.isPending}
            disabled={!demo && availableConnections.length === 0}
            onClick={() => start.mutate()}
          >
            <Play size={16} /> 启动新一轮研究
          </Button>
          {!demo && availableConnections.length === 0 && (
            <Link className="text-link" to="/settings" viewTransition>
              先接入模型 API
            </Link>
          )}
          {start.isError && <small className="error-text">{start.error.message}</small>}
        </div>
      </section>

      <ResearchSpine project={project} />

      <section className="metric-ribbon">
        <Stat value={project.stats.total} label="候选论文" hint="去重后记录" />
        <Stat value={included} label="已纳入" hint={`${screeningProgress}% 已决定`} />
        <Stat value={project.stats.documents} label="全文" hint="已建立页码索引" />
        <Stat
          value={project.reports?.length ?? 0}
          label="报告版本"
          hint="每次运行独立保存"
        />
      </section>

      <div className="overview-grid">
        <section className="overview-runs">
          <SectionTitle
            title="运行历史"
          />
          {(project.runs ?? []).length === 0 ? (
            <div className="lined-placeholder">
              <FlaskConical size={20} />
              <p>还没有运行。可以先用离线演示验证完整工作流。</p>
            </div>
          ) : (
            <div className="run-list">
              {project.runs?.slice(0, 6).map((run) => (
                <Link
                  to={`/projects/${project.id}/runs/${run.id}`}
                  className="run-list__item"
                  key={run.id}
                  viewTransition
                >
                  <div className="run-list__heading">
                    <code>{run.id.slice(-8)}</code>
                    <StatusBadge status={run.status}>{run.status}</StatusBadge>
                    <time>{new Date(run.created_at).toLocaleString("zh-CN")}</time>
                  </div>
                  <RunStageRail
                    current={run.stage}
                    failed={run.status === "failed"}
                    compact
                  />
                  <ArrowRight size={16} />
                </Link>
              ))}
            </div>
          )}
        </section>

        <aside className="overview-aside">
          <section className="protocol-note">
            <span className="eyebrow">研究方案</span>
            <h3>{reviewTypeLabel(project.review_type)}</h3>
            <dl>
              <div>
                <dt>纳入关键词</dt>
                <dd>{project.protocol.include_keywords.length || "未限制"}</dd>
              </div>
              <div>
                <dt>年份</dt>
                <dd>
                  {project.protocol.year_from ?? "—"} —{" "}
                  {project.protocol.year_to ?? "—"}
                </dd>
              </div>
              <div>
                <dt>研究类型</dt>
                <dd>{project.protocol.study_types.join(", ") || "未限制"}</dd>
              </div>
            </dl>
          </section>
          <div className="quick-links">
            <Link to={`/projects/${project.id}/screening`} viewTransition>
              <FileSearch size={17} />
              <span>
                <strong>继续人工筛选</strong>
                <small>{project.stats.pending ?? 0} 篇待处理</small>
              </span>
              <ArrowRight size={15} />
            </Link>
            <Link to={`/projects/${project.id}/evidence`} viewTransition>
              <ShieldCheck size={17} />
              <span>
                <strong>检查复现证据</strong>
                <small>算法、系统和 benchmark 字段</small>
              </span>
              <ArrowRight size={15} />
            </Link>
            {latest?.status === "completed" && (
              <Link to={`/projects/${project.id}/reports`} viewTransition>
                <Beaker size={17} />
                <span>
                  <strong>阅读最新综合</strong>
                  <small>报告与引用审计</small>
                </span>
                <ArrowRight size={15} />
              </Link>
            )}
            <a href={apiUrl(`/projects/${project.id}/export`)}>
              <Download size={17} />
              <span>
                <strong>导出整个项目</strong>
                <small>ZIP + SHA-256 清单</small>
              </span>
              <ArrowRight size={15} />
            </a>
          </div>
        </aside>
      </div>
    </div>
  );
}
