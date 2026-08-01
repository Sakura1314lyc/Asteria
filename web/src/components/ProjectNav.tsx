import {
  BookOpen,
  Boxes,
  FileSearch,
  FlaskConical,
  LayoutDashboard,
  Network,
  MessagesSquare,
  ScrollText
} from "lucide-react";
import { NavLink } from "react-router";
import type { Project } from "../api/types";
import { reviewTypeLabel, StatusBadge } from "./Ui";

const tabs = [
  { segment: "", label: "概览", icon: LayoutDashboard, end: true },
  { segment: "library", label: "文献库", icon: BookOpen },
  { segment: "screening", label: "筛选台", icon: FileSearch },
  { segment: "evidence", label: "证据台", icon: FlaskConical },
  { segment: "map", label: "图谱", icon: Network },
  { segment: "documents", label: "全文", icon: Boxes },
  { segment: "reports", label: "报告", icon: ScrollText },
  { segment: "chat", label: "对话", icon: MessagesSquare }
];

export function ProjectHeader({ project }: { project: Project }) {
  const latest = project.runs?.[0];
  return (
    <div className="project-masthead">
      <div className="project-masthead__identity">
        <span className="eyebrow">
          {reviewTypeLabel(project.review_type)} · {project.language}
        </span>
        <h1>{project.name}</h1>
        <p>{project.research_question}</p>
      </div>
      <div className="project-masthead__meta">
        {latest ? (
          <>
            <span>最近运行</span>
            <StatusBadge status={latest.status}>{latest.status}</StatusBadge>
          </>
        ) : (
          <span className="muted">尚未运行</span>
        )}
      </div>
    </div>
  );
}

export function ProjectNav({ projectId }: { projectId: string }) {
  return (
    <nav className="project-tabs" aria-label="项目导航">
      {tabs.map(({ segment, label, icon: Icon, end }) => (
        <NavLink
          key={segment}
          to={`/projects/${projectId}${segment ? `/${segment}` : ""}`}
          end={end}
          viewTransition
          className={({ isActive }) => (isActive ? "is-active" : "")}
        >
          <Icon size={15} />
          {label}
        </NavLink>
      ))}
    </nav>
  );
}
