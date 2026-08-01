import { AlertCircle, Check, Download, Search } from "lucide-react";
import { apiUrl } from "../api/client";
import type { SearchLog } from "../api/types";

interface SearchLedgerProps {
  runId: string;
  log: SearchLog;
}

export function SearchLedger({ runId, log }: SearchLedgerProps) {
  const restrictions = formatRestrictions(log);

  return (
    <section className="search-ledger" aria-labelledby="search-ledger-title">
      <header className="search-ledger__header">
        <div>
          <span className="eyebrow">Search provenance / 检索来源</span>
          <h2 id="search-ledger-title">检索账本</h2>
          <p>
            {log.summary.planned_executions} 次来源查询 · 去重前{" "}
            {log.summary.records_returned_before_deduplication} 条 · 去重后{" "}
            {log.summary.unique_records_after_deduplication} 条
          </p>
        </div>
        <a
          className="search-ledger__download"
          href={apiUrl(`/runs/${encodeURIComponent(runId)}/artifacts/search_log.json`)}
        >
          <Download size={15} /> JSON
        </a>
      </header>

      {restrictions && (
        <div className="search-ledger__restrictions">
          <Search size={14} />
          <span>配置限制</span>
          <p>{restrictions}</p>
        </div>
      )}

      <div className="search-ledger__table" role="table" aria-label="检索执行记录">
        <div className="search-ledger__row search-ledger__row--head" role="row">
          <span role="columnheader">来源</span>
          <span role="columnheader">实际查询式</span>
          <span role="columnheader">结果</span>
          <span role="columnheader">执行时间</span>
        </div>
        {log.executions.map((item, index) => (
          <div
            className={`search-ledger__row ${item.status === "failed" ? "is-failed" : ""}`}
            role="row"
            key={`${item.source}-${item.query}-${index}`}
          >
            <span className="search-ledger__source" role="cell">
              {item.status === "succeeded" ? (
                <Check size={14} aria-label="成功" />
              ) : (
                <AlertCircle size={14} aria-label="失败" />
              )}
              <strong>{sourceName(item.source)}</strong>
            </span>
            <span className="search-ledger__query" role="cell" title={item.query}>
              {item.query}
              {item.error && <small>{item.error}</small>}
            </span>
            <span role="cell">
              <strong>{item.result_count}</strong>
              <small>/ {item.limit} 上限</small>
            </span>
            <span role="cell">
              {new Date(item.started_at).toLocaleString("zh-CN", {
                month: "2-digit",
                day: "2-digit",
                hour: "2-digit",
                minute: "2-digit"
              })}
              <small>{formatDuration(item.duration_ms)}</small>
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

function sourceName(source: string) {
  const names: Record<string, string> = {
    openalex: "OpenAlex",
    arxiv: "arXiv",
    semantic_scholar: "Semantic Scholar",
    dblp: "DBLP",
    fixture: "本地演示数据"
  };
  return names[source] ?? source;
}

function formatDuration(milliseconds: number) {
  return milliseconds < 1000
    ? `${milliseconds} ms`
    : `${(milliseconds / 1000).toFixed(1)} s`;
}

function formatRestrictions(log: SearchLog) {
  const value = log.configured_restrictions;
  const parts: string[] = [];
  if (value.year_from || value.year_to) {
    parts.push(`${value.year_from ?? "不限"}–${value.year_to ?? "至今"}`);
  }
  if (value.languages.length) parts.push(value.languages.join(" / "));
  if (value.study_types.length) parts.push(value.study_types.join(" / "));
  return parts.join(" · ");
}
