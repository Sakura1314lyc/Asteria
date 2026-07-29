import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowUpDown, FileUp, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { api } from "../api/client";
import type { ProjectPaper, ScreeningStatus } from "../api/types";
import { PaperInspector } from "../components/PaperInspector";
import { ErrorState, LoadingState, StatusBadge } from "../components/Ui";
import { useProjectContext } from "../hooks/useProjectContext";

const filters: Array<{ value: "" | ScreeningStatus; label: string }> = [
  { value: "", label: "全部" },
  { value: "pending", label: "待筛选" },
  { value: "included", label: "已纳入" },
  { value: "maybe", label: "待复核" },
  { value: "excluded", label: "已排除" }
];

const statusNames: Record<ScreeningStatus, string> = {
  pending: "待筛选",
  included: "已纳入",
  maybe: "待复核",
  excluded: "已排除"
};

function sourceName(source: string) {
  const names: Record<string, string> = {
    "import:ris": "RIS 导入",
    "import:bibtex": "BibTeX 导入",
    "import:csl-json": "CSL JSON 导入"
  };
  return names[source] ?? source;
}

export function LibraryPage() {
  const { project } = useProjectContext();
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<"" | ScreeningStatus>("");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<ProjectPaper | null>(null);
  const [descending, setDescending] = useState(true);
  const papers = useQuery({
    queryKey: ["papers", project.id],
    queryFn: () => api.listPapers(project.id)
  });
  const bibliography = useMutation({
    mutationFn: (file: File) => api.importBibliography(project.id, file),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["papers", project.id] });
      await queryClient.invalidateQueries({ queryKey: ["project", project.id] });
    }
  });

  const filtered = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase();
    return [...(papers.data ?? [])]
      .filter((item) => !status || item.screening_status === status)
      .filter((item) => {
        if (!needle) return true;
        const paper = item.paper;
        return `${paper.title} ${paper.authors.join(" ")} ${paper.venue} ${
          paper.abstract
        }`
          .toLocaleLowerCase()
          .includes(needle);
      })
      .sort((a, b) => {
        const difference = (b.paper.year ?? 0) - (a.paper.year ?? 0);
        return descending ? difference : -difference;
      });
  }, [papers.data, status, search, descending]);

  if (papers.isLoading) return <LoadingState label="正在读取文献库" />;
  if (papers.isError) {
    return <ErrorState error={papers.error} retry={() => papers.refetch()} />;
  }

  return (
    <div className="library-layout">
      <section className="library-main">
        <div className="library-toolbar">
          <div className="search-box">
            <Search size={16} />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="搜索标题、作者、摘要或 venue"
            />
          </div>
          <label
            className={`bibliography-import ${
              bibliography.isPending ? "is-disabled" : ""
            }`}
            title="支持 Zotero、EndNote、JabRef 导出的 RIS、BibTeX 与 CSL JSON"
          >
            <FileUp size={15} />
            {bibliography.isPending ? "正在导入" : "导入文献"}
            <input
              type="file"
              accept=".ris,.bib,.json,application/json"
              disabled={bibliography.isPending}
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) bibliography.mutate(file);
                event.currentTarget.value = "";
              }}
            />
          </label>
          <div className="segmented-control">
            {filters.map((filter) => (
              <button
                key={filter.value}
                className={status === filter.value ? "is-active" : ""}
                onClick={() => setStatus(filter.value)}
              >
                {filter.label}
                <span>
                  {(papers.data ?? []).filter(
                    (item) =>
                      !filter.value || item.screening_status === filter.value
                  ).length}
                </span>
              </button>
            ))}
          </div>
        </div>
        {bibliography.data && (
          <div className="bibliography-result" role="status">
            <strong>{bibliography.data.filename}</strong>
            <span>
              新增 {bibliography.data.added} · 已存在{" "}
              {bibliography.data.already_present} · 补全{" "}
              {bibliography.data.enriched}
            </span>
            {(bibliography.data.duplicates_in_file > 0 ||
              bibliography.data.skipped > 0 ||
              bibliography.data.warnings.length > 0) && (
              <small title={bibliography.data.warnings.join("\n")}>
                文件内重复 {bibliography.data.duplicates_in_file} · 跳过{" "}
                {bibliography.data.skipped} · 警告{" "}
                {bibliography.data.warnings.length}
              </small>
            )}
          </div>
        )}
        {bibliography.isError && (
          <div className="bibliography-result is-error" role="alert">
            {bibliography.error.message}
          </div>
        )}
        <div className="paper-table">
          <div className="paper-table__head">
            <span>论文</span>
            <span>来源 / 年份</span>
            <button onClick={() => setDescending((value) => !value)}>
              状态 <ArrowUpDown size={13} />
            </button>
          </div>
          {filtered.map((item) => (
            <button
              className={`paper-row ${
                selected?.id === item.id ? "is-selected" : ""
              }`}
              key={item.id}
              onClick={() => setSelected(item)}
            >
              <span className="paper-row__title">
                <small>{item.evidence_id}</small>
                <strong>{item.paper.title}</strong>
                <em>{item.paper.authors.join(", ") || "作者未知"}</em>
              </span>
              <span className="paper-row__source">
                <strong>
                  {item.paper.venue || sourceName(item.paper.source) || "—"}
                </strong>
                <small>
                  {item.paper.year ?? "—"} · 引用 {item.paper.citation_count}
                </small>
              </span>
              <span className="paper-row__status">
                <StatusBadge status={item.screening_status}>
                  {statusNames[item.screening_status]}
                </StatusBadge>
              </span>
            </button>
          ))}
          {filtered.length === 0 && (
            <div className="table-empty">当前过滤条件下没有论文。</div>
          )}
        </div>
      </section>
      <PaperInspector item={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
