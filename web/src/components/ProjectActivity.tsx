import { ArrowRight, History } from "lucide-react";
import type { ProjectEvent } from "../api/types";
import { SectionTitle } from "./Ui";

const fieldLabels: Record<string, string> = {
  name: "项目名称",
  topic: "研究主题",
  research_question: "研究问题",
  review_type: "工作流类型",
  language: "输出语言",
  population: "研究对象",
  intervention: "方法 / 干预",
  comparison: "对照 / 基线",
  outcomes: "结果 / 指标",
  include_keywords: "纳入关键词",
  exclude_keywords: "排除关键词",
  year_from: "起始年份",
  year_to: "结束年份",
  languages: "语言",
  study_types: "研究类型",
  notes: "方案备注"
};

export function ProjectActivity({ events = [] }: { events?: ProjectEvent[] }) {
  return (
    <section className="project-activity" aria-label="研究修订记录">
      <SectionTitle
        eyebrow="Revision ledger"
        title="研究修订记录"
        detail="项目身份和研究方案的字段级变更；最新记录在前。"
      />
      {events.length === 0 ? (
        <div className="project-activity__empty">
          <History size={18} />
          <p>尚无修订。项目创建后的资料和方案变更会在这里留下记录。</p>
        </div>
      ) : (
        <ol className="revision-ledger">
          {events.slice(0, 12).map((event) => (
            <li key={event.id}>
              <div className="revision-ledger__stamp">
                <code>R{String(event.id).padStart(3, "0")}</code>
                <time dateTime={event.timestamp}>
                  {new Date(event.timestamp).toLocaleString("zh-CN", {
                    month: "2-digit",
                    day: "2-digit",
                    hour: "2-digit",
                    minute: "2-digit"
                  })}
                </time>
              </div>
              <div className="revision-ledger__body">
                <h3>{event.event_type === "protocol_updated" ? "研究方案已修订" : "项目资料已更新"}</h3>
                {event.event_type === "protocol_updated" && eventReason(event) && (
                  <p className="revision-ledger__reason">原因：{eventReason(event)}</p>
                )}
                <ul>
                  {eventChanges(event).map(([field, change]) => (
                    <li key={field}>
                      <span>{fieldLabels[field] ?? field}</span>
                      <div>
                        <del>{formatValue(change.before)}</del>
                        <ArrowRight size={13} aria-hidden="true" />
                        <ins>{formatValue(change.after)}</ins>
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

type Change = { before: unknown; after: unknown };

function eventChanges(event: ProjectEvent): Array<[string, Change]> {
  const changes = event.payload.changes;
  if (!changes || typeof changes !== "object" || Array.isArray(changes)) return [];
  return Object.entries(changes).filter((entry): entry is [string, Change] => {
    const value = entry[1];
    return Boolean(value && typeof value === "object" && "before" in value && "after" in value);
  });
}

function eventReason(event: ProjectEvent) {
  return typeof event.payload.reason === "string" ? event.payload.reason : "";
}

function formatValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "未设置";
  if (Array.isArray(value)) return value.length ? value.join("、") : "未设置";
  return String(value);
}
