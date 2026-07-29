import { useQuery } from "@tanstack/react-query";
import {
  AlertCircle,
  BarChart3,
  Database,
  Gauge,
  ListChecks,
  ShieldCheck
} from "lucide-react";
import { useMemo, useState } from "react";
import { api } from "../api/client";
import type { EvidenceCard, ReproducibilityRecord } from "../api/types";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  Meter,
  SectionTitle
} from "../components/Ui";
import { useProjectContext } from "../hooks/useProjectContext";

type EvidenceTab = "cards" | "reproducibility" | "benchmarks" | "agenda";

export function EvidencePage() {
  const { project } = useProjectContext();
  const [tab, setTab] = useState<EvidenceTab>("cards");
  const completed = project.runs?.find((run) => run.status === "completed");
  const research = useQuery({
    queryKey: ["research", completed?.id],
    queryFn: () => api.getResearch(completed?.id ?? ""),
    enabled: Boolean(completed)
  });

  if (!completed) {
    return (
      <EmptyState
        title="还没有可分析的证据"
        detail="完成至少一次研究运行后，这里会展示证据卡、复现性和 benchmark 目录。"
        icon={<ShieldCheck size={23} />}
      />
    );
  }
  if (research.isLoading) return <LoadingState label="正在整理证据矩阵" />;
  if (research.isError || !research.data) {
    return <ErrorState error={research.error} retry={() => research.refetch()} />;
  }

  const analysis = research.data.cs_analysis;
  const tabs: Array<{ id: EvidenceTab; label: string; icon: typeof ShieldCheck }> = [
    { id: "cards", label: "证据卡", icon: ListChecks },
    { id: "reproducibility", label: "复现性", icon: Gauge },
    { id: "benchmarks", label: "Benchmark", icon: Database },
    { id: "agenda", label: "研究缺口", icon: BarChart3 }
  ];

  return (
    <div className="evidence-page">
      <SectionTitle
        title="研究证据"
        detail="并列查看方法、数据、结果、局限和计算机领域复现字段。"
      />
      <nav className="evidence-tabs">
        {tabs.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            className={tab === id ? "is-active" : ""}
            onClick={() => setTab(id)}
          >
            <Icon size={15} /> {label}
          </button>
        ))}
      </nav>
      {tab === "cards" && (
        <EvidenceCards
          cards={research.data.evidence}
          papers={research.data.papers}
        />
      )}
      {tab === "reproducibility" && (
        <Reproducibility records={analysis.reproducibility ?? []} />
      )}
      {tab === "benchmarks" && (
        <BenchmarkCatalog catalog={analysis.benchmark_catalog} />
      )}
      {tab === "agenda" && (
        <ResearchAgenda agenda={analysis.research_agenda} />
      )}
    </div>
  );
}

function EvidenceCards({
  cards,
  papers
}: {
  cards: EvidenceCard[];
  papers: Array<{ paper_id: string; title: string }>;
}) {
  const titles = useMemo(
    () => Object.fromEntries(papers.map((paper) => [paper.paper_id, paper.title])),
    [papers]
  );
  return (
    <div className="evidence-cards">
      {cards.map((card) => (
        <article key={card.paper_id}>
          <header>
            <span className="paper-code">{card.paper_id}</span>
            <span className={`confidence confidence--${card.confidence}`}>
              {card.confidence} confidence
            </span>
          </header>
          <h3>{titles[card.paper_id] || card.objective}</h3>
          <dl>
            <div>
              <dt>目标</dt>
              <dd>{card.objective || "未报告"}</dd>
            </div>
            <div>
              <dt>方法</dt>
              <dd>{card.methods || "未报告"}</dd>
            </div>
            <div>
              <dt>数据 / 样本</dt>
              <dd>{card.data_or_sample || "未报告"}</dd>
            </div>
          </dl>
          <div className="evidence-card__columns">
            <section>
              <h4>主要发现</h4>
              <ul>
                {card.findings.map((finding) => (
                  <li key={finding}>{finding}</li>
                ))}
              </ul>
            </section>
            <section>
              <h4>局限</h4>
              <ul>
                {card.limitations.map((limitation) => (
                  <li key={limitation}>{limitation}</li>
                ))}
              </ul>
            </section>
          </div>
        </article>
      ))}
    </div>
  );
}

function Reproducibility({
  records
}: {
  records: ReproducibilityRecord[];
}) {
  return (
    <div className="repro-table">
      <div className="repro-table__head">
        <span>论文</span>
        <span>报告完整度</span>
        <span>主要缺失项</span>
      </div>
      {records.map((record) => (
        <div className="repro-table__row" key={record.paper_id}>
          <span>
            <strong>{record.paper_id}</strong>
            <small>{record.grade}</small>
          </span>
          <span>
            <strong>{Math.round(record.overall * 100)}%</strong>
            <Meter
              value={record.overall}
              tone={
                record.overall >= 0.7
                  ? "green"
                  : record.overall >= 0.4
                    ? "orange"
                    : "blue"
              }
            />
          </span>
          <span className="tag-row">
            {record.missing.length ? (
              record.missing.map((item) => (
                <span className="tag tag--warning" key={item}>
                  {item}
                </span>
              ))
            ) : (
              <span className="tag">无明显缺项</span>
            )}
          </span>
        </div>
      ))}
      <div className="evidence-boundary">
        <AlertCircle size={16} />
        这是报告完整性评分，不代表代码已经成功复现，也不直接判断论文结论真伪。
      </div>
    </div>
  );
}

function BenchmarkCatalog({
  catalog
}: {
  catalog:
    | {
        datasets: Array<{ name: string; count?: number; papers?: string[] }>;
        metrics: Array<{ name: string; count?: number; papers?: string[] }>;
        baselines: Array<{ name: string; count?: number; papers?: string[] }>;
      }
    | undefined;
}) {
  const groups = [
    ["数据集", catalog?.datasets ?? []],
    ["评价指标", catalog?.metrics ?? []],
    ["比较基线", catalog?.baselines ?? []]
  ] as const;
  return (
    <div className="catalog-grid">
      {groups.map(([title, items]) => (
        <section key={title}>
          <header>
            <span className="eyebrow">Catalog</span>
            <h3>{title}</h3>
            <small>{items.length} unique</small>
          </header>
          {items.length ? (
            <ul>
              {items.map((item) => (
                <li key={item.name}>
                  <strong>{item.name}</strong>
                  <span>{item.count ?? item.papers?.length ?? 0} papers</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">当前证据中没有抽取到明确条目。</p>
          )}
        </section>
      ))}
    </div>
  );
}

function ResearchAgenda({
  agenda
}: {
  agenda:
    | {
        priorities: Array<{
          gap: string;
          affected_papers: number;
          rate: number;
          recommended_research: string;
        }>;
        note: string;
      }
    | undefined;
}) {
  return (
    <div className="agenda-list">
      {(agenda?.priorities ?? []).map((item, index) => (
        <article key={item.gap}>
          <span>{String(index + 1).padStart(2, "0")}</span>
          <div>
            <small>{item.gap.replaceAll("_", " ")}</small>
            <h3>{item.recommended_research}</h3>
          </div>
          <div>
            <strong>{Math.round(item.rate * 100)}%</strong>
            <small>{item.affected_papers} papers affected</small>
          </div>
        </article>
      ))}
      {agenda?.note && <p className="evidence-boundary">{agenda.note}</p>}
    </div>
  );
}
