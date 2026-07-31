import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Clock,
  FileDown,
  FlaskConical,
  Play,
  ScrollText
} from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, apiUrl } from "../api/client";
import { RunStageRail } from "../components/RunStageRail";
import { SearchLedger } from "../components/SearchLedger";
import {
  Button,
  ErrorState,
  LoadingState,
  SectionTitle,
  StatusBadge
} from "../components/Ui";
import { useProjectContext } from "../hooks/useProjectContext";

export function RunPage() {
  const { project } = useProjectContext();
  const { runId = "" } = useParams();
  const queryClient = useQueryClient();
  const [agentId, setAgentId] = useState("");
  const [connectionId, setConnectionId] = useState("");
  const run = useQuery({
    queryKey: ["run", runId],
    queryFn: () => api.getRun(runId),
    refetchInterval: (state) =>
      ["queued", "running", "waiting_for_screening"].includes(
        state.state.data?.status ?? ""
      )
        ? 1800
        : false
  });
  const events = useQuery({
    queryKey: ["events", runId],
    queryFn: () => api.getRunEvents(runId),
    refetchInterval: () =>
      ["queued", "running", "waiting_for_screening"].includes(
        run.data?.status ?? ""
      )
        ? 1800
        : false
  });
  const artifacts = useQuery({
    queryKey: ["artifacts", runId],
    queryFn: () => api.listArtifacts(runId),
    enabled: Boolean(run.data?.run_dir)
  });
  const research = useQuery({
    queryKey: ["research", runId],
    queryFn: () => api.getResearch(runId),
    enabled: Boolean(run.data?.run_dir),
    refetchInterval: () =>
      ["queued", "running"].includes(run.data?.status ?? "") ? 1800 : false
  });
  const agents = useQuery({ queryKey: ["agents"], queryFn: api.listAgents });
  const connections = useQuery({
    queryKey: ["connections"],
    queryFn: api.listConnections
  });
  const readyConnections =
    connections.data?.filter((connection) => connection.configured) ?? [];
  const storedAgent = String(run.data?.config.agent && typeof run.data.config.agent === "object" && "id" in run.data.config.agent ? run.data.config.agent.id : "deep_review");
  const activeAgentId = agentId || storedAgent;
  const activeConnectionId = readyConnections.some(
    (connection) => connection.id === connectionId
  )
    ? connectionId
    : (readyConnections[0]?.id ?? "");
  const continueRun = useMutation({
    mutationFn: (demo: boolean) =>
      api.continueRun(
        runId,
        demo,
        demo ? undefined : activeConnectionId,
        activeAgentId
      ),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["run", runId] });
      await queryClient.invalidateQueries({ queryKey: ["project", project.id] });
    }
  });

  if (run.isLoading) return <LoadingState label="正在读取运行状态" />;
  if (run.isError || !run.data) {
    return <ErrorState error={run.error} retry={() => run.refetch()} />;
  }
  const data = run.data;

  return (
    <div className="run-page">
      <Link className="back-link" to={`/projects/${project.id}`}>
        <ArrowLeft size={14} /> 返回项目
      </Link>
      <SectionTitle
        eyebrow={`Run ${runId.slice(-10)}`}
        title="研究流水线"
        detail={`创建于 ${new Date(data.created_at).toLocaleString("zh-CN")}`}
        action={<StatusBadge status={data.status}>{data.status}</StatusBadge>}
      />

      <section className="run-console">
        <div className="run-console__rail">
          <RunStageRail
            current={data.stage}
            failed={data.status === "failed"}
          />
        </div>
        <div className="run-console__activity">
          <header>
            <span>
              <FlaskConical size={16} /> Activity log
            </span>
            <small>{events.data?.length ?? 0} events</small>
          </header>
          <div className="event-stream">
            {(events.data ?? []).length === 0 ? (
              <p className="muted">等待第一条运行事件…</p>
            ) : (
              events.data?.map((event) => (
                <div className="event-stream__item" key={event.id}>
                  <span className="event-stream__time">
                    {new Date(event.timestamp).toLocaleTimeString("zh-CN", {
                      hour: "2-digit",
                      minute: "2-digit",
                      second: "2-digit"
                    })}
                  </span>
                  <i />
                  <div>
                    <strong>{event.stage}</strong>
                    <p>{event.message}</p>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </section>

      {research.data?.search_log?.executions?.length ? (
        <SearchLedger runId={runId} log={research.data.search_log} />
      ) : null}

      {data.status === "waiting_for_screening" && (
        <section className="gate-panel">
          <div className="gate-panel__icon">
            <Clock size={21} />
          </div>
          <div>
            <span className="eyebrow">Human gate</span>
            <h3>检索完成，正在等待人工纳排。</h3>
            <p>
              先在筛选台处理全部 pending 论文，再选择真实模型或离线演示继续后续阶段。
            </p>
          </div>
          <div className="gate-panel__actions">
            <div className="gate-panel__selectors">
              <select
                aria-label="继续运行使用的 Agent"
                value={activeAgentId}
                onChange={(event) => setAgentId(event.target.value)}
              >
                {agents.data?.filter((agent) => agent.id !== "project_qa").map((agent) => (
                  <option value={agent.id} key={agent.id}>
                    {agent.short_name}
                  </option>
                ))}
              </select>
              <select
                aria-label="继续运行使用的模型连接"
                value={activeConnectionId}
                onChange={(event) => setConnectionId(event.target.value)}
              >
                {readyConnections.length === 0 && (
                  <option value="">尚未连接模型</option>
                )}
                {readyConnections.map((connection) => (
                  <option value={connection.id} key={connection.id}>
                    {connection.name} · {connection.model}
                  </option>
                ))}
              </select>
            </div>
            <Link className="button button--secondary button--medium" to={`/projects/${project.id}/screening`}>
              打开筛选台
            </Link>
            <Button
              loading={continueRun.isPending}
              disabled={!activeConnectionId}
              onClick={() => continueRun.mutate(false)}
            >
              <Play size={15} /> 真实模型继续
            </Button>
            <Button
              variant="quiet"
              loading={continueRun.isPending}
              onClick={() => continueRun.mutate(true)}
            >
              演示模式继续
            </Button>
          </div>
        </section>
      )}

      {data.status === "failed" && (
        <div className="notice notice--error">
          <AlertTriangle size={18} />
          <div>
            <strong>运行失败</strong>
            <p>{data.error || "没有记录到具体错误。"}</p>
          </div>
        </div>
      )}

      {data.status === "completed" && (
        <section className="completion-strip">
          <CheckCircle2 size={21} />
          <div>
            <strong>研究运行已完成并通过最终阶段。</strong>
            <span>现在可以检查证据、阅读报告或下载原始产物。</span>
          </div>
          <Link
            className="button button--primary button--medium"
            to={`/projects/${project.id}/reports?run=${runId}`}
          >
            <ScrollText size={15} /> 阅读报告
          </Link>
        </section>
      )}

      {artifacts.data && artifacts.data.length > 0 && (
        <section className="artifact-section">
          <SectionTitle
            eyebrow="运行产物"
            title="可审计产物"
            detail="这些文件是运行的事实记录，可以独立下载和复核。"
          />
          <div className="artifact-list">
            {artifacts.data.map((artifact) => (
              <a href={apiUrl(artifact.url)} key={artifact.name}>
                <FileDown size={16} />
                <span>
                  <strong>{artifact.name}</strong>
                  <small>{formatBytes(artifact.bytes)}</small>
                </span>
              </a>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
