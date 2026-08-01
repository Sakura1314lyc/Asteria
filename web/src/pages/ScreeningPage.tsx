import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Check,
  Eye,
  EyeOff,
  ExternalLink,
  HelpCircle,
  ListChecks,
  RotateCcw,
  Users,
  X
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router";
import { api } from "../api/client";
import type {
  ScreeningPaper,
  ScreeningStatus
} from "../api/types";
import { Button, ErrorState, LoadingState, Meter } from "../components/Ui";
import { useProjectContext } from "../hooks/useProjectContext";
import { FullTextScreening } from "./FullTextScreening";

const defaultReason: Record<Exclude<ScreeningStatus, "pending">, string> = {
  included: "符合研究问题，纳入后续证据提取",
  excluded: "不符合当前研究问题或纳排标准",
  maybe: "需要全文或第二位研究者复核"
};

function statusLabel(status: ScreeningStatus) {
  return {
    pending: "未决定",
    included: "纳入",
    excluded: "排除",
    maybe: "待讨论"
  }[status];
}

export function ScreeningPage() {
  const { project } = useProjectContext();
  const [searchParams, setSearchParams] = useSearchParams();
  const stage =
    searchParams.get("stage") === "fulltext" ? "fulltext" : "title";
  function setStage(next: "title" | "fulltext") {
    setSearchParams(next === "fulltext" ? { stage: "fulltext" } : {});
  }
  const config = useQuery({
    queryKey: ["screening-config", project.id],
    queryFn: () => api.getScreeningConfig(project.id)
  });

  return (
    <div className="screening-studio">
      <nav className="screening-stage-nav" aria-label="筛选阶段">
        <button
          className={stage === "title" ? "is-active" : ""}
          onClick={() => setStage("title")}
        >
          <span className="screening-stage-nav__number">01</span>
          <ListChecks size={17} />
          <span>
            <strong>标题与摘要</strong>
            <small>初步资格判断</small>
          </span>
        </button>
        <i aria-hidden="true" />
        <button
          className={stage === "fulltext" ? "is-active" : ""}
          onClick={() => setStage("fulltext")}
        >
          <span className="screening-stage-nav__number">02</span>
          <BookOpen size={17} />
          <span>
            <strong>报告全文</strong>
            <small>
              {config.data?.fulltext_enabled ? "获取与最终纳入" : "尚未启用"}
            </small>
          </span>
        </button>
      </nav>
      {stage === "title" ? <TitleAbstractScreening /> : <FullTextScreening />}
    </div>
  );
}

function TitleAbstractScreening() {
  const { project } = useProjectContext();
  const queryClient = useQueryClient();
  const [reviewer, setReviewer] = useState("");
  const [index, setIndex] = useState(0);
  const [reason, setReason] = useState("");
  const [reviewAll, setReviewAll] = useState(false);
  const [showSetup, setShowSetup] = useState(false);
  const [reviewerA, setReviewerA] = useState("reviewer-a");
  const [reviewerB, setReviewerB] = useState("reviewer-b");
  const [resolver, setResolver] = useState("adjudicator");
  const [resolutionReason, setResolutionReason] = useState("");

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
    queryKey: ["screening-workspace", project.id, reviewer],
    queryFn: () => api.getScreeningWorkspace(project.id, reviewer),
    enabled: Boolean(config.data)
  });

  const papers = workspace.data?.papers ?? [];
  const isDual = workspace.data?.config.mode === "dual";
  const isBlind = Boolean(workspace.data?.config.blind);
  const unresolved = !isBlind
    ? papers.filter((item) =>
        ["conflict", "awaiting_resolution"].includes(item.consensus_state)
      )
    : [];
  const queue = useMemo(() => {
    if (reviewAll) return papers;
    if (isDual && isBlind) {
      return papers.filter((item) => !item.my_decision);
    }
    if (isDual) return unresolved;
    return papers.filter((item) =>
      ["pending", "maybe"].includes(item.screening_status)
    );
  }, [isBlind, isDual, papers, reviewAll, unresolved]);
  const safeIndex = Math.min(index, Math.max(0, queue.length - 1));
  const current = queue[safeIndex];
  const completed = isDual
    ? workspace.data?.summary.reviewer_completed ?? 0
    : papers.filter((item) => item.screening_status !== "pending").length;
  const progress = papers.length ? completed / papers.length : 0;

  function refresh() {
    return Promise.all([
      queryClient.invalidateQueries({
        queryKey: ["screening-workspace", project.id]
      }),
      queryClient.invalidateQueries({
        queryKey: ["screening-config", project.id]
      }),
      queryClient.invalidateQueries({ queryKey: ["papers", project.id] }),
      queryClient.invalidateQueries({ queryKey: ["project", project.id] })
    ]);
  }

  const configure = useMutation({
    mutationFn: () =>
      api.updateScreeningConfig(project.id, {
        mode: "dual",
        reviewers: [reviewerA.trim(), reviewerB.trim()],
        blind: true
      }),
    onSuccess: async (next) => {
      setReviewer(next.reviewers[0]);
      setShowSetup(false);
      await refresh();
    }
  });

  const openReview = useMutation({
    mutationFn: () => {
      const active = workspace.data?.config;
      if (!active) throw new Error("筛选配置尚未载入");
      return api.updateScreeningConfig(project.id, {
        mode: "dual",
        reviewers: active.reviewers,
        blind: false
      });
    },
    onSuccess: refresh
  });

  const decide = useMutation({
    mutationFn: (status: ScreeningStatus) => {
      if (!current || status === "pending") {
        return Promise.resolve({ updated: 0 });
      }
      return api.saveScreening(project.id, [
        {
          paper_id: current.id,
          status,
          reason: reason.trim() || defaultReason[status],
          reviewer: isDual ? reviewer : "web-human"
        }
      ]);
    },
    onSuccess: async () => {
      setReason("");
      setIndex(0);
      await refresh();
    }
  });

  const resolve = useMutation({
    mutationFn: (status: "included" | "excluded") => {
      if (!current) throw new Error("没有可仲裁的论文");
      return api.resolveScreening(project.id, current.id, {
        status,
        reason: resolutionReason.trim(),
        resolved_by: resolver.trim()
      });
    },
    onSuccess: async () => {
      setResolutionReason("");
      setIndex(0);
      await refresh();
    }
  });

  useEffect(() => {
    setIndex(0);
    setReason("");
  }, [reviewer, reviewAll, isBlind]);

  useEffect(() => {
    if (reviewAll && current) {
      setReason(
        current.my_decision?.reason || current.screening_reason || ""
      );
    }
  }, [current, reviewAll]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (
        event.target instanceof HTMLInputElement ||
        event.target instanceof HTMLTextAreaElement ||
        event.target instanceof HTMLSelectElement
      )
        return;
      if (event.key.toLowerCase() === "i") decide.mutate("included");
      if (event.key.toLowerCase() === "e") decide.mutate("excluded");
      if (event.key.toLowerCase() === "m") decide.mutate("maybe");
      if (event.key === "ArrowRight" && queue.length > 1)
        setIndex((value) => (value + 1) % queue.length);
      if (event.key === "ArrowLeft" && queue.length > 1)
        setIndex((value) => (value - 1 + queue.length) % queue.length);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [queue.length, decide]);

  if (config.isLoading || workspace.isLoading) {
    return <LoadingState label="正在整理筛选工作区" />;
  }
  if (config.isError || workspace.isError) {
    const error = config.error || workspace.error;
    return (
      <ErrorState
        error={error}
        retry={() => {
          config.refetch();
          workspace.refetch();
        }}
      />
    );
  }

  return (
    <div className="screening-stage-body">
      <ReviewBar
        isDual={Boolean(isDual)}
        isBlind={isBlind}
        reviewers={workspace.data?.config.reviewers ?? []}
        reviewer={reviewer}
        completed={completed}
        total={papers.length}
        progress={progress}
        canOpen={completed === papers.length}
        showSetup={showSetup}
        onReviewerChange={setReviewer}
        onShowSetup={() => setShowSetup((value) => !value)}
        onOpen={() => openReview.mutate()}
        opening={openReview.isPending}
      />

      {showSetup && !isDual && (
        <section className="review-setup">
          <div>
            <span className="eyebrow">独立双人筛选</span>
            <h3>先各自判断，再共同处理分歧。</h3>
            <p>
              开启后，现有决定归入第一位评审者。双方完成前互不可见。
            </p>
          </div>
          <label>
            <span>第一位评审者</span>
            <input
              value={reviewerA}
              onChange={(event) => setReviewerA(event.target.value)}
            />
          </label>
          <label>
            <span>第二位评审者</span>
            <input
              value={reviewerB}
              onChange={(event) => setReviewerB(event.target.value)}
            />
          </label>
          <Button
            onClick={() => configure.mutate()}
            disabled={
              configure.isPending ||
              !reviewerA.trim() ||
              !reviewerB.trim() ||
              reviewerA.trim() === reviewerB.trim()
            }
          >
            <Users size={16} /> 开始盲审
          </Button>
          {configure.isError && (
            <small className="error-text">{configure.error.message}</small>
          )}
        </section>
      )}

      {!current ? (
        <EmptyQueue
          isDual={Boolean(isDual)}
          isBlind={isBlind}
          total={papers.length}
          unresolved={unresolved.length}
          reviewAll={reviewAll}
          onReviewAll={() => setReviewAll(true)}
          onReturnQueue={() => setReviewAll(false)}
        />
      ) : (
        <>
          <header className="screening-studio__top">
            <div>
              <span className="eyebrow">
                {reviewAll
                  ? "决定复核"
                  : isDual && !isBlind
                    ? "分歧讨论"
                    : "标题与摘要筛选"}
              </span>
              <h2>
                {reviewAll
                  ? "重新阅读，并留下新的判断依据。"
                  : isDual && !isBlind
                    ? `${unresolved.length} 篇等待共同决定`
                    : "逐篇阅读，独立判断。"}
              </h2>
            </div>
            {reviewAll && (
              <Button variant="secondary" onClick={() => setReviewAll(false)}>
                返回工作队列
              </Button>
            )}
          </header>
          <PaperReview
            current={current}
            index={safeIndex}
            total={queue.length}
            isDual={Boolean(isDual)}
            isBlind={isBlind}
            reason={reason}
            resolutionReason={resolutionReason}
            resolver={resolver}
            busy={decide.isPending || resolve.isPending}
            error={decide.error || resolve.error}
            onReason={setReason}
            onResolutionReason={setResolutionReason}
            onResolver={setResolver}
            onDecide={(status) => decide.mutate(status)}
            onResolve={(status) => resolve.mutate(status)}
            onPrevious={() =>
              setIndex((value) => (value - 1 + queue.length) % queue.length)
            }
            onNext={() =>
              setIndex((value) => (value + 1) % queue.length)
            }
          />
        </>
      )}
    </div>
  );
}

function ReviewBar(props: {
  isDual: boolean;
  isBlind: boolean;
  reviewers: string[];
  reviewer: string;
  completed: number;
  total: number;
  progress: number;
  canOpen: boolean;
  showSetup: boolean;
  opening: boolean;
  onReviewerChange: (value: string) => void;
  onShowSetup: () => void;
  onOpen: () => void;
}) {
  return (
    <section className="review-bar">
      <div className="review-bar__identity">
        {props.isDual ? (
          props.isBlind ? <EyeOff size={17} /> : <Eye size={17} />
        ) : (
          <Users size={17} />
        )}
        <div>
          <strong>
            {props.isDual
              ? props.isBlind
                ? "独立盲审进行中"
                : "共同评审已开放"
              : "单人筛选"}
          </strong>
          <small>
            {props.isDual ? "workflow identity，不代表登录账户" : "适合探索性项目"}
          </small>
        </div>
      </div>
      {props.isDual && (
        <div className="reviewer-switch" aria-label="当前评审者">
          {props.reviewers.map((item) => (
            <button
              key={item}
              className={item === props.reviewer ? "is-active" : ""}
              onClick={() => props.onReviewerChange(item)}
            >
              {item}
            </button>
          ))}
        </div>
      )}
      <div className="review-bar__progress">
        <span>
          {props.completed} / {props.total}
        </span>
        <Meter value={props.progress} />
      </div>
      {props.isDual && props.isBlind ? (
        <Button
          variant="secondary"
          disabled={!props.canOpen || props.opening}
          onClick={props.onOpen}
        >
          <Eye size={15} /> 揭盲并核对
        </Button>
      ) : !props.isDual ? (
        <Button variant="secondary" onClick={props.onShowSetup}>
          <Users size={15} /> {props.showSetup ? "收起" : "启用双人筛选"}
        </Button>
      ) : (
        <span className="review-bar__open">决定现已互相可见</span>
      )}
    </section>
  );
}

function EmptyQueue(props: {
  isDual: boolean;
  isBlind: boolean;
  total: number;
  unresolved: number;
  reviewAll: boolean;
  onReviewAll: () => void;
  onReturnQueue: () => void;
}) {
  return (
    <div className="screening-complete">
      <div className="screening-complete__mark">
        <Check size={26} />
      </div>
      <span className="eyebrow">
        {props.isBlind ? "本轮已完成" : "当前队列清空"}
      </span>
      <h2>
        {props.isDual && props.isBlind
          ? "你的决定已保存，等待另一位评审者。"
          : props.unresolved
            ? "仍有分歧等待仲裁。"
            : "筛选决定已经可以进入后续流程。"}
      </h2>
      <p>
        共 {props.total} 篇。所有修改都会留下时间、理由和评审者记录。
      </p>
      <Button
        variant="secondary"
        onClick={props.reviewAll ? props.onReturnQueue : props.onReviewAll}
      >
        <RotateCcw size={15} />
        {props.reviewAll ? "返回工作队列" : "复核已有决定"}
      </Button>
    </div>
  );
}

function PaperReview(props: {
  current: ScreeningPaper;
  index: number;
  total: number;
  isDual: boolean;
  isBlind: boolean;
  reason: string;
  resolutionReason: string;
  resolver: string;
  busy: boolean;
  error: Error | null;
  onReason: (value: string) => void;
  onResolutionReason: (value: string) => void;
  onResolver: (value: string) => void;
  onDecide: (status: ScreeningStatus) => void;
  onResolve: (status: "included" | "excluded") => void;
  onPrevious: () => void;
  onNext: () => void;
}) {
  const paper = props.current.paper;
  const needsResolution =
    props.isDual &&
    !props.isBlind &&
    ["conflict", "awaiting_resolution"].includes(
      props.current.consensus_state
    );
  return (
    <div className="screening-paper">
      <aside className="screening-paper__folio">
        <button
          disabled={props.total < 2}
          onClick={props.onPrevious}
          aria-label="上一篇"
        >
          <ArrowLeft size={17} />
        </button>
        <span>{props.current.evidence_id}</span>
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
          <span>{paper.year ?? "年份未知"}</span>
          <span>{paper.venue || paper.source || "来源未知"}</span>
          <span>{paper.citation_count} citations</span>
        </div>
        <h1>{paper.title}</h1>
        <p className="screening-paper__authors">
          {paper.authors.join(", ") || "作者未知"}
        </p>
        <div className="abstract-sheet">
          <span className="eyebrow">摘要</span>
          <p>
            {paper.abstract ||
              "没有摘要。建议标记为待讨论，并在取得全文后再做决定。"}
          </p>
        </div>
        {(paper.open_access_url || paper.url) && (
          <a
            className="source-link"
            href={paper.open_access_url || paper.url}
            target="_blank"
            rel="noreferrer"
          >
            查看来源 <ExternalLink size={14} />
          </a>
        )}
      </article>
      <aside className="screening-decision">
        {needsResolution ? (
          <ResolutionPanel {...props} />
        ) : (
          <>
            <div>
              <span className="eyebrow">你的决定</span>
              <h3>是否进入证据综合？</h3>
              <p>
                {props.isBlind
                  ? "对方的决定将在双方完成后显示。"
                  : "修改会保留为一条新的审计记录。"}
              </p>
            </div>
            <label>
              <span>判断依据</span>
              <textarea
                rows={5}
                value={props.reason}
                onChange={(event) => props.onReason(event.target.value)}
                placeholder="与纳排标准的关系，可稍后修订"
              />
            </label>
            <DecisionButtons
              busy={props.busy}
              onDecide={props.onDecide}
            />
            <p className="keyboard-note">← / → 切换 · I / M / E 快速决定</p>
          </>
        )}
        {props.error && (
          <small className="error-text">{props.error.message}</small>
        )}
      </aside>
    </div>
  );
}

function ResolutionPanel(
  props: Parameters<typeof PaperReview>[0]
) {
  return (
    <>
      <div className="resolution-heading">
        <AlertTriangle size={18} />
        <div>
          <span className="eyebrow">需要共同决定</span>
          <h3>并排阅读两份判断</h3>
        </div>
      </div>
      <div className="reviewer-notes">
        {props.current.decisions.map((decision) => (
          <article key={decision.reviewer_id}>
            <header>
              <strong>{decision.reviewer_id}</strong>
              <span className={`decision-word is-${decision.status}`}>
                {statusLabel(decision.status)}
              </span>
            </header>
            <p>{decision.reason || "未填写判断依据"}</p>
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
      <label>
        <span>讨论结论与理由</span>
        <textarea
          rows={4}
          value={props.resolutionReason}
          onChange={(event) =>
            props.onResolutionReason(event.target.value)
          }
          placeholder="必填：记录如何解决分歧"
        />
      </label>
      <div className="resolution-actions">
        <button
          className="decision decision--include"
          disabled={
            props.busy ||
            !props.resolver.trim() ||
            !props.resolutionReason.trim()
          }
          onClick={() => props.onResolve("included")}
        >
          <Check size={18} /> 仲裁纳入
        </button>
        <button
          className="decision decision--exclude"
          disabled={
            props.busy ||
            !props.resolver.trim() ||
            !props.resolutionReason.trim()
          }
          onClick={() => props.onResolve("excluded")}
        >
          <X size={18} /> 仲裁排除
        </button>
      </div>
    </>
  );
}

function DecisionButtons(props: {
  busy: boolean;
  onDecide: (status: ScreeningStatus) => void;
}) {
  return (
    <div className="decision-stack">
      <button
        className="decision decision--include"
        onClick={() => props.onDecide("included")}
        disabled={props.busy}
      >
        <Check size={19} />
        <span>
          <strong>纳入</strong>
          <small>I</small>
        </span>
      </button>
      <button
        className="decision decision--maybe"
        onClick={() => props.onDecide("maybe")}
        disabled={props.busy}
      >
        <HelpCircle size={19} />
        <span>
          <strong>待讨论</strong>
          <small>M</small>
        </span>
      </button>
      <button
        className="decision decision--exclude"
        onClick={() => props.onDecide("excluded")}
        disabled={props.busy}
      >
        <X size={19} />
        <span>
          <strong>排除</strong>
          <small>E</small>
        </span>
      </button>
    </div>
  );
}
