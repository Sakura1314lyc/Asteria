import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  CircleOff,
  KeyRound,
  Link2,
  PlugZap,
  ShieldCheck,
  Trash2
} from "lucide-react";
import { FormEvent, useState } from "react";
import { api } from "../api/client";
import type { ModelConnection } from "../api/types";
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
  const remove = useMutation({
    mutationFn: api.deleteConnection,
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["connections"] })
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
    create.mutate(form);
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
              <h3>接入模型</h3>
              <p>支持 Responses 与 OpenAI 兼容 Chat Completions。</p>
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
                placeholder="sk-..."
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
              <Button loading={create.isPending} type="submit">
                <Link2 size={15} /> 保存到当前会话
              </Button>
            </div>
            {create.isError && (
              <p className="error-text">{create.error.message}</p>
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
                onRemove={() => remove.mutate(connection.id)}
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
    </div>
  );
}

function ConnectionRow({
  connection,
  tested,
  testing,
  onTest,
  onRemove
}: {
  connection: ModelConnection;
  tested: boolean;
  testing: boolean;
  onTest: () => void;
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
          <button
            className="icon-button"
            onClick={onRemove}
            aria-label={`删除 ${connection.name}`}
          >
            <Trash2 size={15} />
          </button>
        )}
      </div>
    </article>
  );
}
