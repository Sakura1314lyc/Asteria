import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  CircleOff,
  KeyRound,
  Link2,
  Pencil,
  PlugZap,
  ShieldCheck,
  Trash2
} from "lucide-react";
import { FormEvent, useState } from "react";
import { api } from "../api/client";
import type { ModelConnection } from "../api/types";
import { ConfirmDeleteModal } from "../components/ConfirmDeleteModal";
import {
  Button,
  ErrorState,
  LoadingState,
  SectionTitle
} from "../components/Ui";

const initialForm: {
  name: string;
  base_url: string;
  model: string;
  api_format: "responses" | "chat_completions";
  api_key: string;
} = {
  name: "OpenAI",
  base_url: "https://api.openai.com/v1",
  model: "gpt-5.6-terra",
  api_format: "responses",
  api_key: ""
};

const providerPresets = [
  {
    id: "openai",
    label: "OpenAI",
    name: "OpenAI",
    base_url: "https://api.openai.com/v1",
    model: "gpt-5.6-terra",
    api_format: "responses" as const
  },
  {
    id: "deepseek",
    label: "DeepSeek",
    name: "DeepSeek",
    base_url: "https://api.deepseek.com",
    model: "deepseek-v4-pro",
    api_format: "chat_completions" as const
  }
];

export function SettingsPage() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState(initialForm);
  const [tested, setTested] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [connectionToDelete, setConnectionToDelete] =
    useState<ModelConnection | null>(null);
  const capabilities = useQuery({
    queryKey: ["capabilities"],
    queryFn: api.capabilities
  });
  const connections = useQuery({
    queryKey: ["connections"],
    queryFn: api.listConnections
  });
  const create = useMutation({
    mutationFn: api.createConnection,
    onSuccess: async () => {
      setForm((value) => ({ ...value, api_key: "" }));
      await queryClient.invalidateQueries({ queryKey: ["connections"] });
    }
  });
  const update = useMutation({
    mutationFn: () => api.updateConnection(editingId ?? "", form),
    onSuccess: async () => {
      setEditingId(null);
      setForm(initialForm);
      await queryClient.invalidateQueries({ queryKey: ["connections"] });
    }
  });
  const remove = useMutation({
    mutationFn: api.deleteConnection,
    onSuccess: async () => {
      setConnectionToDelete(null);
      await queryClient.invalidateQueries({ queryKey: ["connections"] });
    }
  });
  const test = useMutation({
    mutationFn: api.testConnection,
    onSuccess: (_, id) => setTested(id)
  });

  if (capabilities.isLoading || connections.isLoading) {
    return <LoadingState label="正在读取模型连接" />;
  }
  if (capabilities.isError || connections.isError || !capabilities.data) {
    return (
      <ErrorState
        error={capabilities.error ?? connections.error}
        retry={() => {
          capabilities.refetch();
          connections.refetch();
        }}
      />
    );
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (editingId) update.mutate();
    else create.mutate(form);
  }
  const deepseekMismatch =
    form.base_url.toLowerCase().includes("deepseek.com") &&
    form.api_format === "responses";

  return (
    <div className="settings-page page-pad">
      <SectionTitle
        title="模型与 API"
        detail="连接密钥只保存在当前服务进程内；重启后需重新输入。"
      />

      <div className="connection-layout">
        <section className="connection-form-card">
          <header>
            <span className="connection-form-card__icon">
              <PlugZap size={19} />
            </span>
            <div>
              <h3>{editingId ? "编辑模型连接" : "接入模型"}</h3>
              <p>
                {editingId
                  ? "留空 API Key 将保留当前会话中的原密钥。"
                  : "支持 Responses 与 OpenAI 兼容 Chat Completions。"}
              </p>
            </div>
          </header>
          <form onSubmit={submit}>
            <div className="provider-presets" aria-label="服务商快捷配置">
              {providerPresets.map((preset) => (
                <button
                  type="button"
                  key={preset.id}
                  className={
                    form.base_url === preset.base_url ? "is-active" : ""
                  }
                  onClick={() =>
                    setForm({
                      ...form,
                      name: preset.name,
                      base_url: preset.base_url,
                      model: preset.model,
                      api_format: preset.api_format
                    })
                  }
                >
                  {preset.label}
                </button>
              ))}
              <span>或手动配置兼容服务</span>
            </div>
            <div className="form-row">
              <label>
                <span>连接名称</span>
                <input
                  value={form.name}
                  onChange={(event) =>
                    setForm({ ...form, name: event.target.value })
                  }
                />
              </label>
              <label>
                <span>API 格式</span>
                <select
                  value={form.api_format}
                  onChange={(event) =>
                    setForm({
                      ...form,
                      api_format: event.target.value as
                        | "responses"
                        | "chat_completions"
                    })
                  }
                >
                  <option value="responses">Responses API</option>
                  <option value="chat_completions">Chat Completions</option>
                </select>
              </label>
            </div>
            <label>
              <span>Base URL</span>
              <input
                value={form.base_url}
                spellCheck={false}
                onChange={(event) =>
                  setForm({ ...form, base_url: event.target.value })
                }
              />
            </label>
            {deepseekMismatch && (
              <p className="connection-hint connection-hint--warning">
                DeepSeek 使用 Chat Completions；保存时会自动修正。
              </p>
            )}
            <label>
              <span>模型</span>
              <input
                value={form.model}
                spellCheck={false}
                onChange={(event) =>
                  setForm({ ...form, model: event.target.value })
                }
              />
            </label>
            <label>
              <span>API Key</span>
              <input
                type="password"
                value={form.api_key}
                autoComplete="off"
                placeholder={editingId ? "留空以保留原密钥" : "sk-..."}
                onChange={(event) =>
                  setForm({ ...form, api_key: event.target.value })
                }
              />
            </label>
            <div className="connection-form-card__footer">
              <span>
                <ShieldCheck size={15} />
                不写入数据库与导出包
              </span>
              <div className="connection-form-actions">
                {editingId && (
                  <Button
                    variant="quiet"
                    onClick={() => {
                      setEditingId(null);
                      setForm(initialForm);
                      update.reset();
                    }}
                  >
                    取消编辑
                  </Button>
                )}
                <Button
                  loading={editingId ? update.isPending : create.isPending}
                  type="submit"
                >
                  <Link2 size={15} />
                  {editingId ? "保存修改" : "保存到当前会话"}
                </Button>
              </div>
            </div>
            {create.isError && (
              <p className="error-text">{create.error.message}</p>
            )}
            {update.isError && (
              <p className="error-text">{update.error.message}</p>
            )}
          </form>
        </section>

        <section className="connection-list-card">
          <header>
            <h3>可用连接</h3>
            <span>{connections.data?.filter((item) => item.configured).length ?? 0}</span>
          </header>
          <div className="connection-list">
            {connections.data?.map((connection) => (
              <ConnectionRow
                key={connection.id}
                connection={connection}
                tested={tested === connection.id}
                testing={test.isPending && test.variables === connection.id}
                onTest={() => test.mutate(connection.id)}
                onEdit={() => {
                  setEditingId(connection.id);
                  setForm({
                    name: connection.name,
                    base_url: connection.base_url,
                    model: connection.model,
                    api_format: connection.api_format,
                    api_key: ""
                  });
                  window.scrollTo({ top: 0, behavior: "smooth" });
                }}
                onRemove={() => setConnectionToDelete(connection)}
              />
            ))}
          </div>
          {test.isError && <p className="error-text">{test.error.message}</p>}
        </section>
      </div>

      <section className="runtime-compact">
        <div>
          <KeyRound size={16} />
          <span>
            <strong>检索密钥</strong>
            <small>
              Semantic Scholar{" "}
              {capabilities.data.semantic_scholar_configured
                ? "已启用"
                : "未配置"}
            </small>
          </span>
        </div>
        {Object.entries(capabilities.data.retrievers).map(([name, enabled]) => (
          <span className={enabled ? "is-ready" : "is-muted"} key={name}>
            {enabled ? <Check size={13} /> : <CircleOff size={13} />}
            {name.replaceAll("_", " ")}
          </span>
        ))}
      </section>
      <ConfirmDeleteModal
        open={Boolean(connectionToDelete)}
        title="删除这个模型连接？"
        description="密钥和会话连接会立即从当前服务进程移除；已经完成的研究运行不会改变。"
        expected={connectionToDelete?.name ?? ""}
        label="输入连接名称"
        pending={remove.isPending}
        error={remove.error}
        onClose={() => {
          if (!remove.isPending) {
            setConnectionToDelete(null);
            remove.reset();
          }
        }}
        onConfirm={() =>
          connectionToDelete && remove.mutate(connectionToDelete.id)
        }
      />
    </div>
  );
}

function ConnectionRow({
  connection,
  tested,
  testing,
  onTest,
  onEdit,
  onRemove
}: {
  connection: ModelConnection;
  tested: boolean;
  testing: boolean;
  onTest: () => void;
  onEdit: () => void;
  onRemove: () => void;
}) {
  return (
    <article className={!connection.configured ? "is-disabled" : ""}>
      <span className="connection-status">
        {connection.configured ? <Check size={14} /> : <CircleOff size={14} />}
      </span>
      <div>
        <strong>{connection.name}</strong>
        <p>
          {connection.model} ·{" "}
          {connection.api_format === "responses" ? "Responses" : "Chat"}
        </p>
        <small>{connection.base_url}</small>
        {connection.notice && (
          <small className="connection-notice">{connection.notice}</small>
        )}
      </div>
      <div className="connection-actions">
        <Button
          variant="quiet"
          size="small"
          disabled={!connection.configured}
          loading={testing}
          onClick={onTest}
        >
          {tested ? "已通过" : "测试"}
        </Button>
        {connection.source === "session" && (
          <>
            <button
              className="icon-button"
              onClick={onEdit}
              aria-label={`编辑 ${connection.name}`}
            >
              <Pencil size={15} />
            </button>
            <button
              className="icon-button"
              onClick={onRemove}
              aria-label={`删除 ${connection.name}`}
            >
              <Trash2 size={15} />
            </button>
          </>
        )}
      </div>
    </article>
  );
}
