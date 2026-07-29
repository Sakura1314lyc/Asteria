import { Check, Circle, CircleDashed, X } from "lucide-react";

const stages = [
  ["initialized", "初始化"],
  ["planned", "研究计划"],
  ["searched", "文献检索"],
  ["screened", "人工筛选"],
  ["extracted", "证据抽取"],
  ["assessed", "质量评估"],
  ["written", "报告撰写"],
  ["completed", "审计完成"]
] as const;

export function RunStageRail({
  current,
  failed = false,
  compact = false
}: {
  current: string;
  failed?: boolean;
  compact?: boolean;
}) {
  const currentIndex = stages.findIndex(([key]) => key === current);
  return (
    <ol className={`stage-rail ${compact ? "stage-rail--compact" : ""}`}>
      {stages.map(([key, label], index) => {
        const done = current === "completed" || index < currentIndex;
        const active = index === currentIndex && !failed;
        return (
          <li
            key={key}
            className={[
              done ? "is-done" : "",
              active ? "is-active" : "",
              failed && index === currentIndex ? "is-failed" : ""
            ].join(" ")}
          >
            <span className="stage-rail__node">
              {failed && index === currentIndex ? (
                <X size={13} />
              ) : done ? (
                <Check size={13} />
              ) : active ? (
                <CircleDashed size={13} />
              ) : (
                <Circle size={9} />
              )}
            </span>
            <span>{label}</span>
          </li>
        );
      })}
    </ol>
  );
}
