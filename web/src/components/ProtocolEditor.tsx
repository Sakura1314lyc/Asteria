import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FilePenLine } from "lucide-react";
import { FormEvent, useMemo, useState } from "react";
import { api } from "../api/client";
import type { Project, ReviewProtocol, ReviewType } from "../api/types";
import { PUBLIC_DEMO } from "../deployment";
import { Button, ErrorState, Modal } from "./Ui";

const reviewTypes: Array<{ value: ReviewType; label: string }> = [
  { value: "narrative", label: "叙述性综述" },
  { value: "scoping", label: "范围综述" },
  { value: "systematic", label: "系统综述" },
  { value: "thesis", label: "论文课题" }
];

export function ProtocolEditor({ project }: { project: Project }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [form, setForm] = useState(() => protocolForm(project.protocol));
  const [reason, setReason] = useState("");
  const protocol = useMemo(() => formProtocol(form), [form]);
  const changed = JSON.stringify(protocol) !== JSON.stringify(project.protocol);
  const update = useMutation({
    mutationFn: () => api.updateProtocol(project.id, protocol, reason.trim()),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["project", project.id] }),
        queryClient.invalidateQueries({ queryKey: ["projects"] })
      ]);
      setFeedback("方案修订已写入审计记录");
      setOpen(false);
    }
  });

  function begin() {
    setForm(protocolForm(project.protocol));
    setReason("");
    setFeedback("");
    update.reset();
    setOpen(true);
  }

  function close() {
    if (update.isPending) return;
    setOpen(false);
    update.reset();
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!changed || !reason.trim()) return;
    update.mutate();
  }

  return (
    <>
      <div className="protocol-note__action">
        <Button
          variant="quiet"
          size="small"
          disabled={PUBLIC_DEMO}
          title={PUBLIC_DEMO ? "公开观测站为只读模式" : undefined}
          onClick={begin}
        >
          <FilePenLine size={14} /> 修订方案
        </Button>
        <span role="status" aria-live="polite">
          {feedback}
        </span>
      </div>

      <Modal
        open={open}
        onClose={close}
        title="修订研究方案"
        subtitle="方案会影响后续检索与筛选；保存时同时记录修改内容和原因。"
        footer={
          <>
            <Button variant="quiet" onClick={close}>
              取消
            </Button>
            <Button
              type="submit"
              form="edit-protocol"
              loading={update.isPending}
              disabled={!changed || !reason.trim()}
            >
              保存并记录修订
            </Button>
          </>
        }
      >
        <form id="edit-protocol" className="research-form protocol-form" onSubmit={submit}>
          <div className="form-split">
            <label>
              <span>工作流类型</span>
              <select
                data-autofocus
                value={form.review_type}
                onChange={(event) =>
                  setForm({ ...form, review_type: event.target.value as ReviewType })
                }
              >
                {reviewTypes.map((type) => (
                  <option value={type.value} key={type.value}>
                    {type.label}
                  </option>
                ))}
              </select>
            </label>
            <div className="form-split protocol-year-range">
              <label>
                <span>起始年份</span>
                <input
                  type="number"
                  min="1900"
                  max="2100"
                  placeholder="不限"
                  value={form.year_from}
                  onChange={(event) => setForm({ ...form, year_from: event.target.value })}
                />
              </label>
              <label>
                <span>结束年份</span>
                <input
                  type="number"
                  min="1900"
                  max="2100"
                  placeholder="不限"
                  value={form.year_to}
                  onChange={(event) => setForm({ ...form, year_to: event.target.value })}
                />
              </label>
            </div>
          </div>

          <fieldset>
            <legend>检索与资格边界</legend>
            <div className="form-split">
              <ListField
                label="纳入关键词"
                value={form.include_keywords}
                onChange={(value) => setForm({ ...form, include_keywords: value })}
              />
              <ListField
                label="排除关键词"
                value={form.exclude_keywords}
                onChange={(value) => setForm({ ...form, exclude_keywords: value })}
              />
              <ListField
                label="语言"
                value={form.languages}
                placeholder="例如：zh-CN, en"
                onChange={(value) => setForm({ ...form, languages: value })}
              />
              <ListField
                label="研究类型"
                value={form.study_types}
                placeholder="例如：experiment, benchmark"
                onChange={(value) => setForm({ ...form, study_types: value })}
              />
            </div>
          </fieldset>

          <fieldset>
            <legend>结构化研究范围（可选）</legend>
            <div className="form-split">
              <ListField label="研究对象" value={form.population} onChange={(value) => setForm({ ...form, population: value })} />
              <ListField label="方法 / 干预" value={form.intervention} onChange={(value) => setForm({ ...form, intervention: value })} />
              <ListField label="对照 / 基线" value={form.comparison} onChange={(value) => setForm({ ...form, comparison: value })} />
              <ListField label="结果 / 指标" value={form.outcomes} onChange={(value) => setForm({ ...form, outcomes: value })} />
            </div>
          </fieldset>

          <label>
            <span>方案备注</span>
            <textarea
              rows={3}
              maxLength={4000}
              value={form.notes}
              onChange={(event) => setForm({ ...form, notes: event.target.value })}
            />
          </label>
          <label>
            <span>本次修订原因</span>
            <textarea
              required
              rows={2}
              maxLength={1000}
              placeholder="说明为什么修改范围、年份或资格标准"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
            />
            <small>原因会和字段级 before/after 一起进入项目修订账本。</small>
          </label>
          {!changed && <p className="protocol-form__hint" role="status">尚未修改任何方案字段。</p>}
          {update.isError && <ErrorState error={update.error} />}
        </form>
      </Modal>
    </>
  );
}

function ListField({
  label,
  value,
  placeholder = "用逗号或换行分隔",
  onChange
}: {
  label: string;
  value: string;
  placeholder?: string;
  onChange: (value: string) => void;
}) {
  return (
    <label>
      <span>{label}</span>
      <textarea
        rows={2}
        placeholder={placeholder}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

function protocolForm(protocol: ReviewProtocol) {
  return {
    review_type: protocol.review_type,
    population: protocol.population.join(", "),
    intervention: protocol.intervention.join(", "),
    comparison: protocol.comparison.join(", "),
    outcomes: protocol.outcomes.join(", "),
    include_keywords: protocol.include_keywords.join(", "),
    exclude_keywords: protocol.exclude_keywords.join(", "),
    year_from: protocol.year_from?.toString() ?? "",
    year_to: protocol.year_to?.toString() ?? "",
    languages: protocol.languages.join(", "),
    study_types: protocol.study_types.join(", "),
    notes: protocol.notes
  };
}

function formProtocol(form: ReturnType<typeof protocolForm>): ReviewProtocol {
  return {
    review_type: form.review_type,
    population: splitList(form.population),
    intervention: splitList(form.intervention),
    comparison: splitList(form.comparison),
    outcomes: splitList(form.outcomes),
    include_keywords: splitList(form.include_keywords),
    exclude_keywords: splitList(form.exclude_keywords),
    year_from: form.year_from ? Number(form.year_from) : null,
    year_to: form.year_to ? Number(form.year_to) : null,
    languages: splitList(form.languages),
    study_types: splitList(form.study_types),
    notes: form.notes.trim()
  };
}

function splitList(value: string) {
  return Array.from(
    new Set(
      value
        .split(/[，,\n]/)
        .map((item) => item.trim())
        .filter(Boolean)
    )
  );
}
