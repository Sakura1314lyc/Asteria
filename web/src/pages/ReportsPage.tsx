import { useQuery } from "@tanstack/react-query";
import {
  Download,
  FileText,
  ShieldAlert,
  ShieldCheck
} from "lucide-react";
import { useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import { useSearchParams } from "react-router-dom";
import remarkGfm from "remark-gfm";
import { api, apiUrl } from "../api/client";
import { EmptyState, ErrorState, LoadingState, SectionTitle } from "../components/Ui";
import { useProjectContext } from "../hooks/useProjectContext";

export function ReportsPage() {
  const { project } = useProjectContext();
  const [params, setParams] = useSearchParams();
  const completed = useMemo(
    () => project.runs?.filter((run) => run.status === "completed") ?? [],
    [project.runs]
  );
  const [selected, setSelected] = useState(
    params.get("run") || completed[0]?.id || ""
  );
  const report = useQuery({
    queryKey: ["report", selected],
    queryFn: () => api.getReport(selected),
    enabled: Boolean(selected)
  });

  if (completed.length === 0) {
    return (
      <EmptyState
        title="还没有完成的报告"
        detail="研究运行完成写作和引用审计后，报告版本会出现在这里。"
        icon={<FileText size={23} />}
      />
    );
  }

  const grounding = report.data?.audit.grounding_proxy;
  const checkCount = grounding?.check_count ?? 0;
  const assessmentCoverage =
    grounding?.assessment_coverage ??
    (checkCount ? (grounding?.assessable_count ?? 0) / checkCount : null);
  const effectiveAlignment =
    grounding?.effective_alignment_rate ??
    (checkCount ? (grounding?.aligned_proxy_count ?? 0) / checkCount : null);

  return (
    <div className="report-page">
      <SectionTitle
        title="阅读、质疑，再回到来源"
        detail="报告视图保留证据 ID；右侧审计只检查结构，不冒充事实核验。"
      />
      <div className="report-workspace">
        <aside className="report-versions">
          <span className="eyebrow">报告版本</span>
          {completed.map((run, index) => (
            <button
              key={run.id}
              className={selected === run.id ? "is-active" : ""}
              onClick={() => {
                setSelected(run.id);
                setParams({ run: run.id });
              }}
            >
              <FileText size={15} />
              <span>
                <strong>报告 #{completed.length - index}</strong>
                <small>{new Date(run.updated_at).toLocaleDateString("zh-CN")}</small>
              </span>
            </button>
          ))}
          <a
            className="report-download"
            href={apiUrl(`/runs/${selected}/artifacts/report.md`)}
          >
            <Download size={15} /> 下载 Markdown
          </a>
        </aside>
        <article className="report-sheet">
          {report.isLoading && <LoadingState label="正在读取报告" />}
          {report.isError && (
            <ErrorState error={report.error} retry={() => report.refetch()} />
          )}
          {report.data && (
            <>
              <header className="report-sheet__header">
                <span className="eyebrow">证据综合稿</span>
                <h1>{report.data.topic}</h1>
                <p>{report.data.question}</p>
                <time>{new Date(report.data.updated_at).toLocaleString("zh-CN")}</time>
              </header>
              <div className="markdown-body">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {report.data.markdown}
                </ReactMarkdown>
              </div>
            </>
          )}
        </article>
        <aside className="audit-panel">
          <span className="eyebrow">引用审计</span>
          {report.data?.audit.passed ? (
            <div className="audit-panel__status is-passed">
              <ShieldCheck size={22} />
              <strong>结构审计通过</strong>
            </div>
          ) : (
            <div className="audit-panel__status is-warning">
              <ShieldAlert size={22} />
              <strong>需要人工复核</strong>
            </div>
          )}
          <dl>
            <div>
              <dt>已知来源</dt>
              <dd>{report.data?.audit.known_source_count ?? "—"}</dd>
            </div>
            <div>
              <dt>被引用来源</dt>
              <dd>{report.data?.audit.cited_source_count ?? "—"}</dd>
            </div>
            <div>
              <dt>段落覆盖</dt>
              <dd>
                {report.data?.audit.paragraph_citation_coverage !== undefined
                  ? `${Math.round(
                      report.data.audit.paragraph_citation_coverage * 100
                    )}%`
                  : "—"}
              </dd>
            </div>
            <div>
              <dt>有效词汇对齐</dt>
              <dd>
                {effectiveAlignment != null
                  ? `${Math.round(effectiveAlignment * 100)}%`
                  : "跨语言/不可评"}
              </dd>
            </div>
            <div>
              <dt>可评估引用</dt>
              <dd>
                {assessmentCoverage != null
                  ? `${Math.round(assessmentCoverage * 100)}%`
                  : "—"}
              </dd>
            </div>
          </dl>
          {assessmentCoverage != null && assessmentCoverage < 0.5 && (
            <div className="audit-panel__status is-warning">
              <ShieldAlert size={18} />
              <strong>多数引用仍需人工语义复核</strong>
            </div>
          )}
          <div className="audit-panel__note">
            <ShieldAlert size={15} />
            <p>
              结构覆盖不等于事实核验。词汇代理只检查可评估引用，跨语言主张仍需回到原文做语义复核。
            </p>
          </div>
          {(report.data?.audit.unknown_citations?.length ?? 0) > 0 && (
            <div className="tag-row">
              {report.data?.audit.unknown_citations?.map((id) => (
                <span className="tag tag--warning" key={id}>
                  unknown {id}
                </span>
              ))}
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
