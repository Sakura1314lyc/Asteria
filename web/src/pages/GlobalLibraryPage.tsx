import { useQuery } from "@tanstack/react-query";
import { ArrowRight, BookOpenText, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  SectionTitle,
  StatusBadge
} from "../components/Ui";

export function GlobalLibraryPage() {
  const [search, setSearch] = useState("");
  const library = useQuery({
    queryKey: ["global-library"],
    queryFn: async () => {
      const projects = await api.listProjects();
      const groups = await Promise.all(
        projects.map(async (project) => ({
          project,
          papers: await api.listPapers(project.id)
        }))
      );
      return groups.flatMap(({ project, papers }) =>
        papers.map((item) => ({ project, item }))
      );
    }
  });
  const filtered = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase();
    return (library.data ?? []).filter(({ project, item }) => {
      if (!needle) return true;
      return `${project.name} ${item.paper.title} ${item.paper.authors.join(" ")} ${
        item.paper.abstract
      }`
        .toLocaleLowerCase()
        .includes(needle);
    });
  }, [library.data, search]);

  if (library.isLoading) return <LoadingState label="正在合并项目文献库" />;
  if (library.isError) {
    return <ErrorState error={library.error} retry={() => library.refetch()} />;
  }

  return (
    <div className="global-library page-pad">
      <SectionTitle
        title="跨项目文献入口"
        detail="同一篇论文可以出现在不同研究项目中，但每个项目保留自己的纳排决定。"
      />
      <div className="filter-line">
        <Search size={17} />
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="搜索全部项目中的标题、作者和摘要…"
        />
        <span>{filtered.length} records</span>
      </div>
      {filtered.length === 0 ? (
        <EmptyState
          title="当前没有可显示的文献"
          detail="先进入研究项目完成一次检索，文献会自动汇集到这里。"
          icon={<BookOpenText size={23} />}
        />
      ) : (
        <div className="global-paper-list">
          {filtered.map(({ project, item }) => (
            <Link
              key={`${project.id}-${item.id}`}
              to={`/projects/${project.id}/library`}
            >
              <span className="paper-code">{item.evidence_id}</span>
              <div>
                <h3>{item.paper.title}</h3>
                <p>{item.paper.authors.join(", ") || "作者未知"}</p>
                <small>
                  {project.name} · {item.paper.venue || item.paper.source || "—"} ·{" "}
                  {item.paper.year ?? "—"}
                </small>
              </div>
              <StatusBadge status={item.screening_status}>
                {item.screening_status}
              </StatusBadge>
              <ArrowRight size={16} />
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
