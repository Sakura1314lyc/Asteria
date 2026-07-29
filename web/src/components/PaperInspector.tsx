import { BookOpen, Braces, Database, ExternalLink, GitFork, X } from "lucide-react";
import type { ProjectPaper } from "../api/types";
import { StatusBadge } from "./Ui";

const statusNames = {
  pending: "待筛选",
  included: "已纳入",
  excluded: "已排除",
  maybe: "待复核"
};

export function PaperInspector({
  item,
  onClose
}: {
  item: ProjectPaper | null;
  onClose: () => void;
}) {
  if (!item) {
    return (
      <aside className="inspector inspector--empty">
        <div>
          <BookOpen size={22} />
          <p>选择一篇论文，查看摘要、标识符和开放资源。</p>
        </div>
      </aside>
    );
  }
  const { paper } = item;
  const primaryUrl = paper.open_access_url || paper.url;
  return (
    <aside className="inspector">
      <header className="inspector__header">
        <StatusBadge status={item.screening_status}>
          {statusNames[item.screening_status]}
        </StatusBadge>
        <button className="icon-button" onClick={onClose} aria-label="关闭详情">
          <X size={17} />
        </button>
      </header>
      <div className="inspector__scroll">
        <span className="paper-code">{item.evidence_id}</span>
        <h2>{paper.title}</h2>
        <p className="inspector__authors">{paper.authors.join(", ") || "作者未知"}</p>
        <dl className="metadata-grid">
          <div>
            <dt>年份</dt>
            <dd>{paper.year ?? "—"}</dd>
          </div>
          <div>
            <dt>引用</dt>
            <dd>{paper.citation_count}</dd>
          </div>
          <div className="metadata-grid__wide">
            <dt>Venue</dt>
            <dd>{paper.venue || "—"}</dd>
          </div>
          <div>
            <dt>来源</dt>
            <dd>{paper.source || "—"}</dd>
          </div>
          <div>
            <dt>类型</dt>
            <dd>{paper.publication_type || "—"}</dd>
          </div>
        </dl>
        <section className="inspector__section">
          <h3>摘要</h3>
          <p>{paper.abstract || "当前元数据中没有摘要。建议导入全文后再做强结论。"}</p>
        </section>
        {paper.categories.length > 0 && (
          <section className="inspector__section">
            <h3>分类</h3>
            <div className="tag-row">
              {paper.categories.map((category) => (
                <span className="tag" key={category}>
                  {category}
                </span>
              ))}
            </div>
          </section>
        )}
        <section className="inspector__section inspector__links">
          <h3>开放资源</h3>
          {primaryUrl && (
            <a href={primaryUrl} target="_blank" rel="noreferrer">
              <ExternalLink size={15} /> 打开论文页面
            </a>
          )}
          {paper.doi && (
            <a
              href={`https://doi.org/${paper.doi}`}
              target="_blank"
              rel="noreferrer"
            >
              <Braces size={15} /> DOI · {paper.doi}
            </a>
          )}
          {paper.code_urls.map((url) => (
            <a href={url} target="_blank" rel="noreferrer" key={url}>
              <GitFork size={15} /> 代码仓库
            </a>
          ))}
          {paper.dataset_urls.map((url) => (
            <a href={url} target="_blank" rel="noreferrer" key={url}>
              <Database size={15} /> 数据集
            </a>
          ))}
          {!primaryUrl &&
            !paper.doi &&
            paper.code_urls.length === 0 &&
            paper.dataset_urls.length === 0 && <p className="muted">暂无可解析链接。</p>}
        </section>
        {item.screening_reason && (
          <section className="inspector__section inspector__decision">
            <h3>筛选记录</h3>
            <p>{item.screening_reason}</p>
            <small>
              {item.reviewer || "human"} · {item.decided_at || "未记录时间"}
            </small>
          </section>
        )}
      </div>
    </aside>
  );
}
