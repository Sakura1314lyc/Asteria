import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Check,
  ExternalLink,
  FileSearch,
  FileUp,
  RotateCcw,
  Search,
  X
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, apiUrl } from "../api/client";
import type {
  FullTextPaper,
  ScreeningStatus
} from "../api/types";
import { Button, ErrorState, LoadingState, Meter } from "../components/Ui";
import { useProjectContext } from "../hooks/useProjectContext";

const retrievalLabels = {
  not_requested: "尚未查找",
  sought: "正在获取",
  retrieved: "已取得全文",
  not_retrieved: "未取得全文"
};

export function FullTextScreening() {
  const { project } = useProjectContext();
  const queryClient = useQueryClient();
  const [reviewer, setReviewer] = useState("");
  const [index, setIndex] = useState(0);
  const [reviewAll, setReviewAll] = useState(false);
  const [reason, setReason] = useState("");
  const [exclusionCode, setExclusionCode] = useState("");
  const [retrievalReason, setRetrievalReason] = useState("");
  const [resolver, setResolver] = useState("adjudicator");

  const config = useQuery({
    queryKey: ["screening-config", project.id],
    queryFn: () => api.getScreeningConfig(project.id)
  });

  useEffect(() => {
    if (
      config.data?.mode === "dual" &&
      (!reviewer || !config.data.reviewers.includes(reviewer))
    ) {
      setReviewer(config.data.reviewers[0] ?? "");
    }
  }, [config.data, reviewer]);

  const workspace = useQuery({
    queryKey: ["fulltext-workspace", project.id, reviewer],
    queryFn: () => api.getFullTextWorkspace(project.id, reviewer),
    enabled: Boolean(config.data?.fulltext_enabled)
  });
  const prisma = useQuery({
    queryKey: ["prisma-flow", project.id],
    queryFn: () => api.getPrismaFlow(project.id)
  });

  const data = workspace.data;
  const papers = data?.papers ?? [];
  const isDual = data?.config.mode === "dual";
  const isBlind = Boolean(data?.config.fulltext_blind);
  const queue = useMemo(() => {
    if (reviewAll) return papers;
    return papers.filter((paper) => {
      if (["not_requested", "sought"].includes(paper.retrieval_status)) {
        return true;
      }
      if (paper.retrieval_status === "not_retrieved") return false;
      if (isDual && isBlind) return !paper.my_decision;
      if (isDual) {
        return ["conflict", "awaiting_resolution"].includes(
          paper.consensus_state
        );
      }
      return ["pending", "maybe"].includes(paper.fulltext_status);
    });
  }, [isBlind, isDual, papers, reviewAll]);
  const safeIndex = Math.min(index, Math.max(queue.length - 1, 0));
  const current = queue[safeIndex];
  const completed = isDual
    ? data?.summary.reviewer_completed ?? 0
    : papers.filter(
        (paper) =>
          paper.retrieval_status === "not_retrieved" ||
          (paper.retrieval_status === "retrieved" &&
            !["pending", "maybe"].includes(paper.fulltext_status))
      ).length;

  function refresh() {
    return Promise.all([
      queryClient.invalidateQueries({
        queryKey: ["fulltext-workspace", project.id]
      }),
      queryClient.invalidateQueries({
        queryKey: ["screening-config", project.id]
      }),
      queryClient.invalidateQueries({ queryKey: ["prisma-flow", project.id] }),
      queryClient.invalidateQueries({ queryKey: ["papers", project.id] }),
      queryClient.invalidateQueries({ queryKey: ["documents", project.id] })
    ]);
  }

  const enable = useMutation({
    mutationFn: () =>
      api.updateFullTextConfig(project.id, {
        enabled: true,
        blind: config.data?.mode === "dual"
      }),
    onSuccess: refresh
  });
  const openReview = useMutation({
    mutationFn: () =>
      api.updateFullTextConfig(project.id, {
        enabled: true,
        blind: false
      }),
    onSuccess: refresh
  });
  const retrieval = useMutation({
    mutationFn: (status: "sought" | "not_retrieved") => {
      if (!current) throw new Error("没有选中的报告");
      return api.saveFullTextRetrieval(project.id, current.id, {
        status,
        reason: status === "not_retrieved" ? retrievalReason.trim() : "",
        updated_by: isDual ? reviewer : "web-human"
      });
    },
    onSuccess: async () => {
      setRetrievalReason("");
      setIndex(0);
      await refresh();
    }
  });
  const decide = useMutation({
    mutationFn: (status: Exclude<ScreeningStatus, "pending">) => {
      if (!current) throw new Error("没有选中的报告");
      return api.saveFullTextScreening(project.id, [
        {
          paper_id: current.id,
          status,
          reason:
            reason.trim() ||
            (status === "included"
              ? "全文符合预先设定的纳入标准"
              : status === "maybe"
                ? "需要团队讨论后再作最终决定"
                : ""),
          exclusion_code: status === "excluded" ? exclusionCode : "",
          reviewer: isDual ? reviewer : "web-human"
        }
      ]);
    },
    onSuccess: async () => {
      setReason("");
      setExclusionCode("");
      setIndex(0);
      await refresh();
    }
  });
  const resolve = useMutation({
    mutationFn: (status: "included" | "excluded") => {
      if (!current) throw new Error("没有选中的报告");
      return api.resolveFullTextScreening(project.id, current.id, {
        status,
        reason: reason.trim(),
        exclusion_code: status === "excluded" ? exclusionCode : "",
        resolved_by: resolver.trim()
      });
    },
    onSuccess: async () => {
      setReason("");
      setExclusionCode("");
      setIndex(0);
      await refresh();
    }
  });

  useEffect(() => {
    setIndex(0);
    setReason("");
    setExclusionCode("");
  }, [reviewer, reviewAll]);

  if (config.isLoading) return <LoadingState label="正在读取全文筛选配置" />;
  if (config.isError) {
    return <ErrorState error={config.error} retry={() => config.refetch()} />;
  }
  if (!config.data?.fulltext_enabled) {
    return (
      <section className="fulltext-onboarding">
        <div className="fulltext-onboarding__copy">
          <span className="eyebrow">第二阶段</span>
          <h2>取得报告全文，再作最终纳入决定。</h2>
          <p>
            标题与摘要筛选完成后，记录全文获取结果、结构化排除原因及评审分歧。
            原始决定会保留在审计事件中。
          </p>
          <Button onClick={() => enable.mutate()} disabled={enable.isPending}>
            <BookOpen size={16} /> 启用全文筛选
          </Button>
          {enable.isError && (
            <small className="error-text">{enable.error.message}</small>
          )}
        </div>
        <PrismaStrip flow={prisma.data} />
      </section>
    );
  }
  if (workspace.isLoading) return <LoadingState label="正在整理全文队列" />;
  if (workspace.isError) {
    return (
      <ErrorState error={workspace.error} retry={() => workspace.refetch()} />
    );
  }

  const canOpen =
    Boolean(isDual && isBlind) &&
    papers.every(
      (paper) =>
        paper.retrieval_status === "not_retrieved" ||
        (paper.retrieval_status === "retrieved" && paper.my_decision)
    );

  return (
    <div className="fulltext-workbench">
      <section className="fulltext-toolbar">
        <div>
          <strong>{isBlind ? "全文独立盲审" : "全文资格评审"}</strong>
          <small>
            {data?.summary.retrieved ?? 0} 份已取得 ·{" "}
            {data?.summary.not_retrieved ?? 0} 份未取得
          </small>
        </div>
        {isDual && (
          <div className="reviewer-switch" aria-label="当前全文评审者">
            {data?.config.reviewers.map((item) => (
              <button
                key={item}
                className={item === reviewer ? "is-active" : ""}
                onClick={() => setReviewer(item)}
              >
                {item}
              </button>
            ))}
          </div>
        )}
        <div className="fulltext-toolbar__progress">
          <span>
            {completed} / {papers.length}
          </span>
          <Meter value={papers.length ? completed / papers.length : 0} />
        </div>
        {isDual && isBlind && (
          <Button
            variant="secondary"
            disabled={!canOpen || openReview.isPending}
            onClick={() => openReview.mutate()}
          >
            揭盲并核对
          </Button>
        )}
      </section>
      <PrismaStrip flow={prisma.data} />

      {!current ? (
        <div className="screening-complete fulltext-complete">
          <div className="screening-complete__mark">
            <Check size={26} />
          </div>
          <span className="eyebrow">全文队列清空</span>
          <h2>
            {isBlind
              ? "本轮决定已保存，等待另一位评审者。"
              : "全文资格决定可以进入证据综合。"}
          </h2>
          <p>获取状态、排除代码和每次修改都已进入项目审计记录。</p>
          <Button
            variant="secondary"
            onClick={() => setReviewAll((value) => !value)}
          >
            <RotateCcw size={15} /> {reviewAll ? "返回队列" : "复核全部报告"}
          </Button>
        </div>
      ) : (
        <FullTextPaperDesk
          projectId={project.id}
          paper={current}
          index={safeIndex}
          total={queue.length}
          isDual={Boolean(isDual)}
          isBlind={isBlind}
          reviewer={reviewer}
          exclusionReasons={data?.exclusion_reasons ?? {}}
          reason={reason}
          exclusionCode={exclusionCode}
          retrievalReason={retrievalReason}
          resolver={resolver}
          busy={
            retrieval.isPending || decide.isPending || resolve.isPending
          }
          error={retrieval.error || decide.error || resolve.error}
          onReason={setReason}
          onExclusionCode={setExclusionCode}
          onRetrievalReason={setRetrievalReason}
          onResolver={setResolver}
          onRetrieval={(status) => retrieval.mutate(status)}
          onDecide={(status) => decide.mutate(status)}
          onResolve={(status) => resolve.mutate(status)}
          onPrevious={() =>
            setIndex((value) => (value - 1 + queue.length) % queue.length)
          }
          onNext={() =>
            setIndex((value) => (value + 1) % queue.length)
          }
        />
      )}
    </div>
  );
}

function PrismaStrip(props: {
  flow:
    | {
        records_screened: number;
        records_excluded: number;
        reports_sought_for_retrieval: number;
        reports_assessed_for_eligibility: number;
        studies_included_in_synthesis: number;
      }
    | undefined;
}) {
  if (!props.flow) return null;
  const items = [
    ["记录筛选", props.flow.records_screened],
    ["标题排除", props.flow.records_excluded],
    ["全文待获取", props.flow.reports_sought_for_retrieval],
    ["全文已评估", props.flow.reports_assessed_for_eligibility],
    ["最终纳入", props.flow.studies_included_in_synthesis]
  ];
  return (
    <ol className="prisma-strip" aria-label="PRISMA 流程概览">
      {items.map(([label, value]) => (
        <li key={label}>
          <span>{label}</span>
          <strong>{value}</strong>
        </li>
      ))}
    </ol>
  );
}

function FullTextPaperDesk(props: {
  projectId: string;
  paper: FullTextPaper;
  index: number;
  total: number;
  isDual: boolean;
  isBlind: boolean;
  reviewer: string;
  exclusionReasons: Record<string, string>;
  reason: string;
  exclusionCode: string;
  retrievalReason: string;
  resolver: string;
  busy: boolean;
  error: Error | null;
  onReason: (value: string) => void;
  onExclusionCode: (value: string) => void;
  onRetrievalReason: (value: string) => void;
  onResolver: (value: string) => void;
  onRetrieval: (status: "sought" | "not_retrieved") => void;
  onDecide: (status: Exclude<ScreeningStatus, "pending">) => void;
  onResolve: (status: "included" | "excluded") => void;
  onPrevious: () => void;
  onNext: () => void;
}) {
  const source = props.paper.paper;
  const needsResolution =
    props.isDual &&
    !props.isBlind &&
    ["conflict", "awaiting_resolution"].includes(
      props.paper.consensus_state
    );
  const isRetrieval =
    props.paper.retrieval_status === "not_requested" ||
    props.paper.retrieval_status === "sought";
  const exclusionReady =
    Boolean(props.reason.trim()) && Boolean(props.exclusionCode);

  return (
    <div className="screening-paper fulltext-paper">
      <aside className="screening-paper__folio">
        <button
          disabled={props.total < 2}
          onClick={props.onPrevious}
          aria-label="上一篇"
        >
          <ArrowLeft size={17} />
        </button>
        <span>{props.paper.evidence_id}</span>
        <small>
          {props.index + 1} / {props.total}
        </small>
        <button
          disabled={props.total < 2}
          onClick={props.onNext}
          aria-label="下一篇"
        >
          <ArrowRight size={17} />
        </button>
      </aside>
      <article className="screening-paper__content">
        <div className="screening-paper__meta">
          <span>{source.year ?? "年份未知"}</span>
          <span>{source.venue || source.source || "来源未知"}</span>
          <span
            className={`retrieval-state is-${props.paper.retrieval_status}`}
          >
            {retrievalLabels[props.paper.retrieval_status]}
          </span>
        </div>
        <h1>{source.title}</h1>
        <p className="screening-paper__authors">
          {source.authors.join(", ") || "作者未知"}
        </p>
        <div className="fulltext-files">
          <header>
            <span className="eyebrow">报告全文</span>
            <Link
              to={`/app/projects/${props.projectId}/documents?paper_id=${props.paper.id}`}
            >
              <FileUp size={14} /> 上传并关联
            </Link>
          </header>
          {props.paper.documents.length ? (
            props.paper.documents.map((document) => (
              <a
                key={document.id}
                href={apiUrl(
                  `/projects/${props.projectId}/documents/${document.id}/file`
                )}
                target="_blank"
                rel="noreferrer"
              >
                <BookOpen size={16} />
                <span>
                  <strong>{document.filename}</strong>
                  <small>
                    {document.page_count
                      ? `${document.page_count} 页`
                      : "文本报告"}
                  </small>
                </span>
                <ExternalLink size={14} />
              </a>
            ))
          ) : (
            <div className="fulltext-files__empty">
              <FileSearch size={18} />
              <span>尚未关联本地全文。取得文件后，从文档页上传到这篇论文。</span>
            </div>
          )}
        </div>
        <details className="abstract-disclosure">
          <summary>回看标题与摘要阶段信息</summary>
          <p>{source.abstract || "没有摘要记录。"}</p>
        </details>
        {(source.open_access_url || source.url) && (
          <a
            className="source-link"
            href={source.open_access_url || source.url}
            target="_blank"
            rel="noreferrer"
          >
            查找公开版本 <Search size={14} />
          </a>
        )}
      </article>
      <aside className="screening-decision">
        {isRetrieval ? (
          <RetrievalPanel {...props} />
        ) : needsResolution ? (
          <FullTextResolutionPanel {...props} />
        ) : (
          <>
            <div>
              <span className="eyebrow">全文资格决定</span>
              <h3>报告是否满足全部纳入标准？</h3>
              <p>
                排除时必须选择一个主要原因，并留下可复核的具体说明。
              </p>
            </div>
            <DecisionFields {...props} />
            <div className="decision-stack">
              <button
                className="decision decision--include"
                disabled={props.busy}
                onClick={() => props.onDecide("included")}
              >
                <Check size={19} /> <strong>全文纳入</strong>
              </button>
              <button
                className="decision decision--maybe"
                disabled={props.busy}
                onClick={() => props.onDecide("maybe")}
              >
                <AlertTriangle size={18} /> <strong>留待讨论</strong>
              </button>
              <button
                className="decision decision--exclude"
                disabled={props.busy || !exclusionReady}
                onClick={() => props.onDecide("excluded")}
              >
                <X size={19} /> <strong>全文排除</strong>
              </button>
            </div>
          </>
        )}
        {props.error && (
          <small className="error-text">{props.error.message}</small>
        )}
      </aside>
    </div>
  );
}

function RetrievalPanel(
  props: Parameters<typeof FullTextPaperDesk>[0]
) {
  return (
    <>
      <div>
        <span className="eyebrow">全文获取</span>
        <h3>先定位一份可评审的完整报告。</h3>
        <p>优先使用作者稿、机构仓储或开放获取版本，并保留无法获取的原因。</p>
      </div>
      <button
        className="retrieval-action"
        disabled={props.busy}
        onClick={() => props.onRetrieval("sought")}
      >
        <Search size={17} />
        <span>
          <strong>标记为正在获取</strong>
          <small>已开始查找全文来源</small>
        </span>
      </button>
      <Link
        className="retrieval-action"
        to={`/app/projects/${props.projectId}/documents?paper_id=${props.paper.id}`}
      >
        <FileUp size={17} />
        <span>
          <strong>上传本地全文</strong>
          <small>上传时选择当前论文</small>
        </span>
      </Link>
      <label>
        <span>无法获取的具体原因</span>
        <textarea
          rows={4}
          value={props.retrievalReason}
          onChange={(event) => props.onRetrievalReason(event.target.value)}
          placeholder="例如：出版社页面无可用全文，作者稿亦未找到"
        />
      </label>
      <Button
        variant="secondary"
        disabled={props.busy || !props.retrievalReason.trim()}
        onClick={() => props.onRetrieval("not_retrieved")}
      >
        记录为未取得
      </Button>
    </>
  );
}

function DecisionFields(
  props: Parameters<typeof FullTextPaperDesk>[0]
) {
  return (
    <>
      <label>
        <span>主要排除原因</span>
        <select
          value={props.exclusionCode}
          onChange={(event) => props.onExclusionCode(event.target.value)}
        >
          <option value="">纳入时无需选择</option>
          {Object.entries(props.exclusionReasons).map(([code, label]) => (
            <option key={code} value={code}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span>判断依据</span>
        <textarea
          rows={5}
          value={props.reason}
          onChange={(event) => props.onReason(event.target.value)}
          placeholder="引用方法、研究对象或结果中支撑决定的信息"
        />
      </label>
    </>
  );
}

function FullTextResolutionPanel(
  props: Parameters<typeof FullTextPaperDesk>[0]
) {
  return (
    <>
      <div className="resolution-heading">
        <AlertTriangle size={18} />
        <div>
          <span className="eyebrow">全文分歧</span>
          <h3>核对决定及主要排除原因</h3>
        </div>
      </div>
      <div className="reviewer-notes">
        {props.paper.decisions.map((decision) => (
          <article key={decision.reviewer_id}>
            <header>
              <strong>{decision.reviewer_id}</strong>
              <span>{decision.status}</span>
            </header>
            <p>{decision.reason || "未填写判断依据"}</p>
            {decision.exclusion_code && (
              <small>
                {props.exclusionReasons[decision.exclusion_code] ??
                  decision.exclusion_code}
              </small>
            )}
          </article>
        ))}
      </div>
      <label>
        <span>仲裁人</span>
        <input
          value={props.resolver}
          onChange={(event) => props.onResolver(event.target.value)}
        />
      </label>
      <DecisionFields {...props} />
      <div className="resolution-actions">
        <button
          className="decision decision--include"
          disabled={props.busy || !props.resolver.trim() || !props.reason.trim()}
          onClick={() => props.onResolve("included")}
        >
          <Check size={18} /> 仲裁纳入
        </button>
        <button
          className="decision decision--exclude"
          disabled={
            props.busy ||
            !props.resolver.trim() ||
            !props.reason.trim() ||
            !props.exclusionCode
          }
          onClick={() => props.onResolve("excluded")}
        >
          <X size={18} /> 仲裁排除
        </button>
      </div>
    </>
  );
}
