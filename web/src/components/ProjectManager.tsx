import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Pencil, Trash2 } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { api } from "../api/client";
import type { Project, ReviewType } from "../api/types";
import { PUBLIC_DEMO } from "../deployment";
import { Button, ErrorState, Modal } from "./Ui";

const reviewTypes: Array<{ value: ReviewType; label: string }> = [
  { value: "narrative", label: "叙述性综述" },
  { value: "scoping", label: "范围综述" },
  { value: "systematic", label: "系统综述" },
  { value: "thesis", label: "论文课题" }
];

export function ProjectManager({ project }: { project: Project }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [mode, setMode] = useState<"closed" | "edit" | "delete">("closed");
  const [confirmation, setConfirmation] = useState("");
  const [feedback, setFeedback] = useState("");
  const [form, setForm] = useState(() => projectForm(project));

  useEffect(() => {
    setForm(projectForm(project));
  }, [project]);

  const update = useMutation({
    mutationFn: () => api.updateProject(project.id, form),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["project", project.id] }),
        queryClient.invalidateQueries({ queryKey: ["projects"] })
      ]);
      setFeedback("项目资料已更新");
      setMode("closed");
    }
  });
  const remove = useMutation({
    mutationFn: () => api.deleteProject(project.id, confirmation),
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: ["project", project.id] });
    },
    onSuccess: async () => {
      navigate("/projects", { replace: true, viewTransition: true });
      await queryClient.invalidateQueries({ queryKey: ["projects"] });
    }
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    update.mutate();
  }

  function close() {
    if (update.isPending || remove.isPending) return;
    setMode("closed");
    setConfirmation("");
    update.reset();
    remove.reset();
  }

  return (
    <>
      <div className="project-manage-line">
        <Button
          variant="quiet"
          size="small"
          disabled={PUBLIC_DEMO}
          title={PUBLIC_DEMO ? "公开观测站为只读模式" : undefined}
          onClick={() => {
            setFeedback("");
            setForm(projectForm(project));
            setMode("edit");
          }}
        >
          <Pencil size={14} /> 编辑项目
        </Button>
        <span className="project-manage-feedback" aria-live="polite">
          {feedback}
        </span>
      </div>

      <Modal
        open={mode === "edit"}
        onClose={close}
        title="编辑项目资料"
        subtitle="更新研究身份；既有检索、筛选与证据记录不会被重写。"
        footer={
          <>
            <Button
              className="modal-danger-entry"
              variant="danger"
              onClick={() => {
                update.reset();
                setMode("delete");
              }}
            >
              <Trash2 size={15} /> 删除项目
            </Button>
            <Button variant="quiet" onClick={close}>
              取消
            </Button>
            <Button
              type="submit"
              form="edit-project"
              loading={update.isPending}
            >
              保存修改
            </Button>
          </>
        }
      >
        <form id="edit-project" className="research-form" onSubmit={submit}>
          <label>
            <span>项目名称</span>
            <input
              data-autofocus
              required
              maxLength={200}
              value={form.name}
              onChange={(event) => setForm({ ...form, name: event.target.value })}
            />
          </label>
          <label>
            <span>研究主题</span>
            <textarea
              required
              maxLength={500}
              rows={3}
              value={form.topic}
              onChange={(event) => setForm({ ...form, topic: event.target.value })}
            />
          </label>
          <label>
            <span>研究问题</span>
            <textarea
              required
              maxLength={2000}
              rows={3}
              value={form.research_question}
              onChange={(event) =>
                setForm({ ...form, research_question: event.target.value })
              }
            />
          </label>
          <div className="form-split">
            <label>
              <span>工作流类型</span>
              <select
                value={form.review_type}
                onChange={(event) =>
                  setForm({
                    ...form,
                    review_type: event.target.value as ReviewType
                  })
                }
              >
                {reviewTypes.map((type) => (
                  <option value={type.value} key={type.value}>
                    {type.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>输出语言</span>
              <select
                value={form.language}
                onChange={(event) =>
                  setForm({ ...form, language: event.target.value })
                }
              >
                <option value="zh-CN">简体中文</option>
                <option value="en">English</option>
              </select>
            </label>
          </div>
          {update.isError && <ErrorState error={update.error} />}
        </form>
      </Modal>

      <Modal
        open={mode === "delete"}
        onClose={close}
        title="永久删除这个项目？"
        subtitle="该操作无法撤销，也不会保留在回收站。"
        footer={
          <>
            <Button variant="quiet" onClick={() => setMode("edit")}>
              返回
            </Button>
            <Button
              variant="danger"
              loading={remove.isPending}
              disabled={confirmation !== project.name}
              onClick={() => remove.mutate()}
            >
              永久删除
            </Button>
          </>
        }
      >
        <div className="delete-project-confirmation">
          <div className="destructive-summary">
            <AlertTriangle size={20} />
            <div>
              <strong>将清除整个研究工作区</strong>
              <p>
                {project.stats.total} 篇论文、{project.runs?.length ?? 0} 次运行、
                {project.stats.documents} 份全文以及关联证据、报告和对话都会删除。
              </p>
            </div>
          </div>
          <label>
            <span>
              输入 <strong>{project.name}</strong> 以确认
            </span>
            <input
              data-autofocus
              autoComplete="off"
              value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
            />
          </label>
          {remove.isError && <ErrorState error={remove.error} />}
        </div>
      </Modal>
    </>
  );
}

function projectForm(project: Project) {
  return {
    name: project.name,
    topic: project.topic,
    research_question: project.research_question,
    review_type: project.review_type,
    language: project.language
  };
}
