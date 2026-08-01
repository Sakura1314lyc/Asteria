import type { Project } from "../api/types";
import { reviewTypeLabel } from "./Ui";

const stageOrder = [
  "initialized",
  "planned",
  "searched",
  "screened",
  "extracted",
  "assessed",
  "written",
  "completed"
];

function reached(current: string | undefined, target: string) {
  return stageOrder.indexOf(current ?? "") >= stageOrder.indexOf(target);
}

export function ResearchSpine({ project }: { project: Project }) {
  const latest = project.runs?.[0];
  const total = project.stats.total ?? 0;
  const decided =
    (project.stats.included ?? 0) +
    (project.stats.excluded ?? 0) +
    (project.stats.maybe ?? 0);
  const reports = project.reports?.length ?? 0;
  const phases = [
    {
      label: "方案",
      detail: reviewTypeLabel(project.review_type),
      complete: true
    },
    {
      label: "检索",
      detail: total ? `${total} 条记录` : "等待运行",
      complete: total > 0 || reached(latest?.stage, "searched")
    },
    {
      label: "筛选",
      detail: total ? `${decided}/${total} 已判断` : "人工门禁",
      complete: total > 0 && decided >= total
    },
    {
      label: "证据",
      detail: project.stats.documents
        ? `${project.stats.documents} 份全文`
        : "提取与复核",
      complete: reached(latest?.stage, "extracted")
    },
    {
      label: "报告",
      detail: reports ? `${reports} 个版本` : "引用审计",
      complete: latest?.status === "completed" || reports > 0
    }
  ];
  const activeIndex = phases.findIndex((phase) => !phase.complete);

  return (
    <ol className="research-spine" aria-label="研究证据链进度">
      {phases.map((phase, index) => {
        const state = phase.complete
          ? "complete"
          : index === activeIndex
            ? "active"
            : "pending";
        return (
          <li className={`is-${state}`} key={phase.label}>
            <span className="research-spine__node" aria-hidden="true">
              {phase.complete ? "✓" : index + 1}
            </span>
            <div>
              <strong>{phase.label}</strong>
              <small>{phase.detail}</small>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
