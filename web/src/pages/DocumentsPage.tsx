import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  File,
  FileSearch,
  Search,
  Upload,
  X
} from "lucide-react";
import { FormEvent, useRef, useState } from "react";
import { useSearchParams } from "react-router";
import { api, apiUrl } from "../api/client";
import type { SearchHit } from "../api/types";
import {
  Button,
  EmptyState,
  ErrorState,
  LoadingState,
  SectionTitle
} from "../components/Ui";
import { useProjectContext } from "../hooks/useProjectContext";

export function DocumentsPage() {
  const { project } = useProjectContext();
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [searchParams, setSearchParams] = useSearchParams();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchHit[]>([]);
  const requestedPaperId = Number(searchParams.get("paper_id") || 0);
  const documents = useQuery({
    queryKey: ["documents", project.id],
    queryFn: () => api.listDocuments(project.id)
  });
  const papers = useQuery({
    queryKey: ["papers", project.id],
    queryFn: () => api.listPapers(project.id)
  });
  const selectedPaperId = papers.data?.some(
    (paper) => paper.id === requestedPaperId
  )
    ? requestedPaperId
    : 0;
  const upload = useMutation({
    mutationFn: (file: File) =>
      api.uploadDocument(
        project.id,
        file,
        selectedPaperId > 0 ? selectedPaperId : undefined
      ),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["documents", project.id] }),
        queryClient.invalidateQueries({ queryKey: ["project", project.id] }),
        queryClient.invalidateQueries({ queryKey: ["papers", project.id] }),
        queryClient.invalidateQueries({
          queryKey: ["fulltext-workspace", project.id]
        }),
        queryClient.invalidateQueries({ queryKey: ["prisma-flow", project.id] })
      ]);
      if (inputRef.current) inputRef.current.value = "";
    }
  });
  const search = useMutation({
    mutationFn: (text: string) => api.searchDocuments(project.id, text),
    onSuccess: setResults
  });

  function submitSearch(event: FormEvent) {
    event.preventDefault();
    if (query.trim().length >= 2) search.mutate(query.trim());
  }

  if (documents.isLoading || papers.isLoading) {
    return <LoadingState label="正在读取全文库" />;
  }
  if (documents.isError || papers.isError) {
    return (
      <ErrorState
        error={documents.error || papers.error}
        retry={() => {
          documents.refetch();
          papers.refetch();
        }}
      />
    );
  }

  return (
    <div className="documents-page">
      <SectionTitle
        title="把强结论带回全文页码"
        detail="支持 PDF、Markdown 和纯文本；检索命中保留文档与页码。"
      />
      <section className="document-upload-bar">
        <label>
          <span>关联到论文</span>
          <select
            aria-label="关联到论文"
            value={selectedPaperId || ""}
            onChange={(event) => {
              const paperId = event.target.value;
              setSearchParams(paperId ? { paper_id: paperId } : {});
            }}
          >
            <option value="">不关联，仅加入全文库</option>
            {papers.data?.map((item) => (
              <option key={item.id} value={item.id}>
                {item.evidence_id} · {item.paper.title}
              </option>
            ))}
          </select>
          <small>
            {selectedPaperId
              ? "上传成功后会自动记录这篇报告已取得全文。"
              : "系统综述的最终资格评审需要先关联对应论文。"}
          </small>
        </label>
        <div>
          <label className="button button--primary button--medium upload-button">
            <Upload size={15} />
            {upload.isPending ? "正在处理…" : "导入全文"}
            <input
              ref={inputRef}
              type="file"
              accept=".pdf,.txt,.md"
              disabled={upload.isPending}
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) upload.mutate(file);
              }}
            />
          </label>
          <small>PDF、TXT 或 MD</small>
        </div>
      </section>
      {upload.isError && <ErrorState error={upload.error} />}
      <div className="documents-grid">
        <section className="document-list">
          <header>
            <span>已索引文档</span>
            <small>{documents.data?.length ?? 0} files</small>
          </header>
          {(documents.data ?? []).length === 0 ? (
            <EmptyState
              title="还没有全文"
              detail="上传 PDF、Markdown 或 TXT，系统会保存原文件并建立页码级检索索引。"
              icon={<File size={22} />}
            />
          ) : (
            documents.data?.map((document) => (
              <a
                className="document-row"
                key={document.id}
                href={apiUrl(
                  `/projects/${project.id}/documents/${document.id}/file`
                )}
                target="_blank"
                rel="noreferrer"
              >
                <div className="document-row__icon">
                  <File size={18} />
                </div>
                <div>
                  <strong>{document.filename}</strong>
                  <span>
                    {document.media_type} · {document.page_count} pages
                  </span>
                  <small>{new Date(document.created_at).toLocaleString("zh-CN")}</small>
                </div>
                <ArrowRight size={15} />
              </a>
            ))
          )}
        </section>
        <section className="fulltext-search">
          <header>
            <span>页码级检索</span>
            <small>SQLite FTS5</small>
          </header>
          <form onSubmit={submitSearch}>
            <Search size={17} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="例如：tail latency hardware setup"
            />
            {query && (
              <button
                type="button"
                onClick={() => {
                  setQuery("");
                  setResults([]);
                }}
                aria-label="清空"
              >
                <X size={15} />
              </button>
            )}
            <Button size="small" loading={search.isPending}>
              检索
            </Button>
          </form>
          {search.isError && <ErrorState error={search.error} />}
          <div className="search-results">
            {results.map((result) => (
              <article key={`${result.document_id}-${result.chunk_id}`}>
                <div>
                  <span>
                    <FileSearch size={14} /> {result.filename}
                  </span>
                  <strong>p. {result.page}</strong>
                </div>
                <p>{result.content}</p>
              </article>
            ))}
            {search.isSuccess && results.length === 0 && (
              <p className="muted">没有找到匹配段落。尝试减少关键词。</p>
            )}
            {!search.isSuccess && (
              <div className="search-hint">
                <Search size={24} />
                <p>输入两个以上字符，在所有已提取全文中搜索。</p>
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
