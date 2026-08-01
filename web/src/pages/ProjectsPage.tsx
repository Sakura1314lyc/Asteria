import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  BookOpen,
  Braces,
  FolderKanban,
  Plus,
  Search
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { api } from "../api/client";
import type { ReviewType, TaxonomyMatch } from "../api/types";
import {
  Button,
  EmptyState,
  ErrorState,
  LoadingState,
  Modal,
  SectionTitle,
  StatusBadge
} from "../components/Ui";

const reviewTypeNames: Record<ReviewType, string> = {
  narrative: "叙述性综述",
  scoping: "范围综述",
  systematic: "系统综述",
  thesis: "论文课题"
};

export function ProjectsPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState(params.get("new") === "1");
  const [matches, setMatches] = useState<TaxonomyMatch[]>([]);
  const [form, setForm] = useState({
    name: "",
    topic: "",
    research_question: "",
    review_type: "systematic" as ReviewType,
    language: "zh-CN"
  });

  useEffect(() => {
    setOpen(params.get("new") === "1");
  }, [params]);

  const projects = useQuery({
    queryKey: ["projects"],
    queryFn: api.listProjects
  });
  const classify = useMutation({
    mutationFn: (text: string) => api.classify(text),
    onSuccess: setMatches
  });
  const create = useMutation({
    mutationFn: api.createProject,
    onSuccess: async (project) => {
      await queryClient.invalidateQueries({ queryKey: ["projects"] });
      setOpen(false);
      navigate(`/projects/${project.id}`);
    }
  });

  const filtered = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase();
    if (!needle) return projects.data ?? [];
    return (projects.data ?? []).filter((project) =>
      `${project.name} ${project.topic} ${project.research_question}`
        .toLocaleLowerCase()
        .includes(needle)
    );
  }, [projects.data, search]);

  function closeModal() {
    setOpen(false);
    params.delete("new");
    setParams(params, { replace: true });
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    create.mutate(form);
  }

  if (projects.isLoading) return <LoadingState />;
  if (projects.isError) {
    return <ErrorState error={projects.error} retry={() => projects.refetch()} />;
  }

  return (
    <div className="projects-page page-pad">
      <SectionTitle
        title="研究项目"
        detail="项目是所有论文、筛选决定、全文与报告的长期容器。"
        action={
          <Button
            onClick={() => {
              setOpen(true);
              setParams({ new: "1" });
            }}
          >
            <Plus size={16} /> 新建项目
          </Button>
        }
      />

      <div className="filter-line">
        <Search size={17} />
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="按题目、问题或关键词过滤…"
          aria-label="过滤项目"
        />
        <span>{filtered.length} projects</span>
      </div>

      {filtered.length === 0 ? (
        <EmptyState
          title={search ? "没有匹配的项目" : "还没有研究项目"}
          detail={
            search
              ? "换一个关键词，或清除当前过滤条件。"
              : "创建一个项目，保存研究方案并启动第一轮检索。"
          }
          action={
            !search && (
              <Button onClick={() => setOpen(true)}>创建第一个项目</Button>
            )
          }
        />
      ) : (
        <div className="project-index">
          {filtered.map((project) => {
            const latest = project.runs?.[0];
            return (
              <Link
                className="project-index__item"
                to={`/projects/${project.id}`}
                key={project.id}
              >
                <div className="project-index__glyph">
                  {project.review_type === "systematic" ? (
                    <Braces size={19} />
                  ) : (
                    <FolderKanban size={19} />
                  )}
                </div>
                <div className="project-index__copy">
                  <span className="eyebrow">
                    {reviewTypeNames[project.review_type]} ·{" "}
                    {new Date(project.updated_at).toLocaleDateString("zh-CN")}
                  </span>
                  <h2>{project.name}</h2>
                  <p>{project.research_question}</p>
                  <div className="project-index__stats">
                    <span>
                      <BookOpen size={13} /> {project.stats.total} papers
                    </span>
                    <span>{project.stats.pending ?? 0} pending</span>
                    <span>{project.stats.documents} full text</span>
                  </div>
                </div>
                <div className="project-index__status">
                  {latest ? (
                    <StatusBadge status={latest.status}>{latest.status}</StatusBadge>
                  ) : (
                    <span className="muted">draft</span>
                  )}
                  <ArrowRight size={17} />
                </div>
              </Link>
            );
          })}
        </div>
      )}

      <Modal
        open={open}
        onClose={closeModal}
        title="开始一项新的研究"
        subtitle="先把问题说清楚；检索式和证据协议会在运行时继续展开。"
        footer={
          <>
            <Button variant="quiet" onClick={closeModal}>
              取消
            </Button>
            <Button
              type="submit"
              form="create-project"
              loading={create.isPending}
            >
              创建项目 <ArrowRight size={15} />
            </Button>
          </>
        }
      >
        <form id="create-project" className="research-form" onSubmit={submit}>
          <label>
            <span>项目名称</span>
            <input
              required
              value={form.name}
              onChange={(event) =>
                setForm((value) => ({ ...value, name: event.target.value }))
              }
              placeholder="例如：LLM 推理系统综述"
            />
          </label>
          <label>
            <span>研究主题</span>
            <div className="input-action">
              <textarea
                required
                rows={3}
                value={form.topic}
                onChange={(event) => {
                  setForm((value) => ({ ...value, topic: event.target.value }));
                  setMatches([]);
                }}
                placeholder="研究对象、技术方向和你关心的边界"
              />
              <button
                type="button"
                onClick={() => form.topic && classify.mutate(form.topic)}
                disabled={!form.topic || classify.isPending}
              >
                识别 CS 方向
              </button>
            </div>
          </label>
          {matches.length > 0 && (
            <div className="classification-preview">
              {matches.map((match) => (
                <span key={match.domain_id}>
                  {match.name_zh}
                  <small>{match.evidence_profile}</small>
                </span>
              ))}
            </div>
          )}
          <label>
            <span>研究问题</span>
            <textarea
              required
              rows={3}
              value={form.research_question}
              onChange={(event) =>
                setForm((value) => ({
                  ...value,
                  research_question: event.target.value
                }))
              }
              placeholder="用一句可被证据回答的问题描述目标"
            />
          </label>
          <div className="form-split">
            <label>
              <span>工作流类型</span>
              <select
                value={form.review_type}
                onChange={(event) =>
                  setForm((value) => ({
                    ...value,
                    review_type: event.target.value as ReviewType
                  }))
                }
              >
                {Object.entries(reviewTypeNames).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>输出语言</span>
              <select
                value={form.language}
                onChange={(event) =>
                  setForm((value) => ({
                    ...value,
                    language: event.target.value
                  }))
                }
              >
                <option value="zh-CN">简体中文</option>
                <option value="en">English</option>
              </select>
            </label>
          </div>
          {create.isError && <ErrorState error={create.error} />}
        </form>
      </Modal>
    </div>
  );
}
