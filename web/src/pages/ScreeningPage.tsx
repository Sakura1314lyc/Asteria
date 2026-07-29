import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  ExternalLink,
  HelpCircle,
  RotateCcw,
  X
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { ScreeningStatus } from "../api/types";
import { Button, ErrorState, LoadingState, Meter } from "../components/Ui";
import { useProjectContext } from "../hooks/useProjectContext";

export function ScreeningPage() {
  const { project } = useProjectContext();
  const queryClient = useQueryClient();
  const [index, setIndex] = useState(0);
  const [reason, setReason] = useState("");
  const [reviewAll, setReviewAll] = useState(false);
  const papers = useQuery({
    queryKey: ["papers", project.id],
    queryFn: () => api.listPapers(project.id)
  });
  const queue = useMemo(
    () => {
      const values = papers.data ?? [];
      return reviewAll
        ? values
        : values.filter((item) =>
            ["pending", "maybe"].includes(item.screening_status)
          );
    },
    [papers.data, reviewAll]
  );
  const current = queue[Math.min(index, Math.max(0, queue.length - 1))];
  const decided = (papers.data ?? []).filter(
    (item) => !["pending", "maybe"].includes(item.screening_status)
  ).length;
  const progress = reviewAll
    ? queue.length
      ? (index + 1) / queue.length
      : 0
    : papers.data?.length
      ? decided / papers.data.length
      : 0;

  const decide = useMutation({
    mutationFn: (status: ScreeningStatus) => {
      if (!current) return Promise.resolve({ updated: 0 });
      return api.saveScreening(project.id, [
        {
          paper_id: current.id,
          status,
          reason:
            reason.trim() ||
            (status === "included"
              ? "符合研究问题，纳入后续证据提取"
              : status === "excluded"
                ? "不符合当前研究问题或方案"
                : "需要全文或第二位研究者复核"),
          reviewer: "web-human"
        }
      ]);
    },
    onSuccess: async () => {
      setReason("");
      setIndex((value) =>
        reviewAll && queue.length > 1 ? (value + 1) % queue.length : 0
      );
      await queryClient.invalidateQueries({ queryKey: ["papers", project.id] });
      await queryClient.invalidateQueries({ queryKey: ["project", project.id] });
    }
  });

  useEffect(() => {
    if (reviewAll && current) {
      setReason(current.screening_reason || "");
    }
  }, [current, reviewAll]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (
        event.target instanceof HTMLInputElement ||
        event.target instanceof HTMLTextAreaElement
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

  if (papers.isLoading) return <LoadingState label="正在准备筛选队列" />;
  if (papers.isError) {
    return <ErrorState error={papers.error} retry={() => papers.refetch()} />;
  }

  if (!current) {
    return (
      <div className="screening-complete">
        <div className="screening-complete__mark">
          <Check size={28} />
        </div>
        <span className="eyebrow">筛选完成</span>
        <h2>所有候选论文都有决定了。</h2>
        <p>
          已处理 {papers.data?.length ?? 0} 篇。回到运行页面，即可通过人工门并继续抽取证据。
        </p>
        <Button
          variant="secondary"
          onClick={() => {
            setIndex(0);
            setReviewAll(true);
          }}
        >
          <RotateCcw size={15} /> 复核全部决定
        </Button>
      </div>
    );
  }

  const paper = current.paper;
  return (
    <div className="screening-studio">
      <header className="screening-studio__top">
        <div>
          <span className="eyebrow">
            {reviewAll ? "决定复核" : "人工筛选"}
          </span>
          <h2>
            {reviewAll
              ? "逐篇复核，修改会保留新的理由与时间。"
              : "逐篇决定，不让模型替你静默排除。"}
          </h2>
          {reviewAll && (
            <Button
              variant="secondary"
              onClick={() => {
                setIndex(0);
                setReviewAll(false);
              }}
            >
              返回待筛队列
            </Button>
          )}
        </div>
        <div className="screening-progress">
          <span>
            {reviewAll ? index + 1 : decided} / {papers.data?.length ?? 0}
          </span>
          <Meter value={progress} />
        </div>
      </header>
      <div className="screening-paper">
        <aside className="screening-paper__folio">
          <button
            disabled={queue.length < 2}
            onClick={() =>
              setIndex((value) => (value - 1 + queue.length) % queue.length)
            }
            aria-label="上一篇"
          >
            <ArrowLeft size={17} />
          </button>
          <span>{current.evidence_id}</span>
          <small>
            {index + 1} / {queue.length}
          </small>
          <button
            disabled={queue.length < 2}
            onClick={() => setIndex((value) => (value + 1) % queue.length)}
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
                "没有摘要。建议标记为待复核，并在取得全文后再做决定。"}
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
          <div>
            <span className="eyebrow">你的决定</span>
            <h3>这篇论文是否进入证据综合？</h3>
            <p>决定会连同理由和研究者标识写入项目审计记录。</p>
          </div>
          <label>
            <span>决定理由</span>
            <textarea
              rows={5}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              placeholder="可选；建议记录与方案的关系"
            />
          </label>
          <div className="decision-stack">
            <button
              className="decision decision--include"
              onClick={() => decide.mutate("included")}
              disabled={decide.isPending}
            >
              <Check size={19} />
              <span>
                <strong>纳入</strong>
                <small>I</small>
              </span>
            </button>
            <button
              className="decision decision--maybe"
              onClick={() => decide.mutate("maybe")}
              disabled={decide.isPending}
            >
              <HelpCircle size={19} />
              <span>
                <strong>待复核</strong>
                <small>M</small>
              </span>
            </button>
            <button
              className="decision decision--exclude"
              onClick={() => decide.mutate("excluded")}
              disabled={decide.isPending}
            >
              <X size={19} />
              <span>
                <strong>排除</strong>
                <small>E</small>
              </span>
            </button>
          </div>
          {decide.isError && <small className="error-text">{decide.error.message}</small>}
          <p className="keyboard-note">← / → 切换论文 · I / M / E 快捷决定</p>
        </aside>
      </div>
    </div>
  );
}
