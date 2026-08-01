import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowUp,
  Bot,
  BookOpen,
  Cable,
  FileText,
  MessageSquarePlus,
  Sparkles,
  Trash2
} from "lucide-react";
import { FormEvent, useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Link } from "react-router";
import { api } from "../api/client";
import type { ChatSource, Conversation } from "../api/types";
import { ConfirmDeleteModal } from "../components/ConfirmDeleteModal";
import { Button, ErrorState, LoadingState } from "../components/Ui";
import { useProjectContext } from "../hooks/useProjectContext";
import { PUBLIC_DEMO } from "../deployment";

export function ChatPage() {
  const { project } = useProjectContext();
  const queryClient = useQueryClient();
  const [activeId, setActiveId] = useState("");
  const [input, setInput] = useState("");
  const [agentId, setAgentId] = useState("project_qa");
  const [connectionId, setConnectionId] = useState("env-openai");
  const [demo, setDemo] = useState(true);
  const [selectedSources, setSelectedSources] = useState<ChatSource[]>([]);
  const [conversationToDelete, setConversationToDelete] =
    useState<Conversation | null>(null);

  const conversations = useQuery({
    queryKey: ["conversations", project.id],
    queryFn: () => api.listConversations(project.id)
  });
  const agents = useQuery({ queryKey: ["agents"], queryFn: api.listAgents });
  const connections = useQuery({
    queryKey: ["connections"],
    queryFn: api.listConnections
  });
  const availableConnections = useMemo(
    () => connections.data?.filter((item) => item.configured) ?? [],
    [connections.data]
  );
  const activeConnectionId = availableConnections.some(
    (item) => item.id === connectionId
  )
    ? connectionId
    : (availableConnections[0]?.id ?? "env-openai");
  const conversation = useQuery({
    queryKey: ["conversation", activeId],
    queryFn: () => api.getConversation(activeId),
    enabled: Boolean(activeId)
  });

  useEffect(() => {
    if (!activeId && conversations.data?.[0]) {
      setActiveId(conversations.data[0].id);
    }
  }, [activeId, conversations.data]);

  useEffect(() => {
    if (selectedSources.length > 0) return;
    const latestWithSources = [...(conversation.data?.messages ?? [])]
      .reverse()
      .find((message) => message.sources.length > 0);
    if (latestWithSources) setSelectedSources(latestWithSources.sources);
  }, [conversation.data?.messages, selectedSources.length]);

  const create = useMutation({
    mutationFn: () =>
      api.createConversation(project.id, {
        title: `研究问答 ${new Date().toLocaleDateString("zh-CN")}`,
        agent_id: agentId,
        connection_id: demo ? null : activeConnectionId,
        demo
      }),
    onSuccess: async (created) => {
      setActiveId(created.id);
      setSelectedSources([]);
      await queryClient.invalidateQueries({
        queryKey: ["conversations", project.id]
      });
    }
  });
  const send = useMutation({
    mutationFn: (content: string) =>
      api.sendMessage(activeId, {
        content,
        demo
      }),
    onSuccess: async ({ assistant_message }) => {
      setInput("");
      setSelectedSources(assistant_message.sources);
      await queryClient.invalidateQueries({
        queryKey: ["conversation", activeId]
      });
      await queryClient.invalidateQueries({
        queryKey: ["conversations", project.id]
      });
    }
  });
  const remove = useMutation({
    mutationFn: (item: Conversation) =>
      api.deleteConversation(item.id, item.title),
    onMutate: async (item) => {
      await queryClient.cancelQueries({ queryKey: ["conversation", item.id] });
    },
    onSuccess: async (_, removed) => {
      const next = conversations.data?.find((item) => item.id !== removed.id);
      setActiveId(next?.id ?? "");
      setSelectedSources([]);
      setConversationToDelete(null);
      await queryClient.invalidateQueries({
        queryKey: ["conversations", project.id]
      });
    }
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    const content = input.trim();
    if (content && activeId) send.mutate(content);
  }

  if (conversations.isLoading || agents.isLoading || connections.isLoading) {
    return <LoadingState label="正在打开项目对话" />;
  }
  if (conversations.isError || agents.isError || connections.isError) {
    return (
      <ErrorState
        error={conversations.error ?? agents.error ?? connections.error}
        retry={() => {
          conversations.refetch();
          agents.refetch();
          connections.refetch();
        }}
      />
    );
  }

  return (
    <div className="chat-workbench">
      <aside className="chat-threads">
        <button className="new-thread" onClick={() => create.mutate()}>
          <MessageSquarePlus size={16} />
          新对话
        </button>
        <div className="chat-threads__list">
          {conversations.data?.map((item) => (
            <div
              className={`chat-thread-row ${
                item.id === activeId ? "is-active" : ""
              }`}
              key={item.id}
            >
              <button
                className="chat-thread-row__open"
                onClick={() => {
                  setActiveId(item.id);
                  setSelectedSources([]);
                }}
              >
                <strong>{item.title}</strong>
                <span>
                  {item.message_count} 条 · {item.connection_label}
                </span>
              </button>
              <button
                className="chat-thread-row__delete"
                disabled={PUBLIC_DEMO}
                title={PUBLIC_DEMO ? "公开观测站为只读模式" : undefined}
                aria-label={`删除对话 ${item.title}`}
                onClick={() => setConversationToDelete(item)}
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>
      </aside>

      <main className="chat-main">
        <header className="chat-toolbar">
          <label>
            <Bot size={14} />
            <select
              value={agentId}
              onChange={(event) => setAgentId(event.target.value)}
            >
              {agents.data?.map((agent) => (
                <option value={agent.id} key={agent.id}>
                  {agent.short_name}
                </option>
              ))}
            </select>
          </label>
          <label>
            <Cable size={14} />
            <select
              value={activeConnectionId}
              disabled={demo}
              onChange={(event) => setConnectionId(event.target.value)}
            >
              {availableConnections.length === 0 && (
                <option value="env-openai">尚未连接</option>
              )}
              {availableConnections.map((item) => (
                <option value={item.id} key={item.id}>
                  {item.name} · {item.model}
                </option>
              ))}
            </select>
          </label>
          <label className="chat-demo-toggle">
            <input
              type="checkbox"
              checked={demo}
              onChange={(event) => setDemo(event.target.checked)}
            />
            离线
          </label>
          {!demo && availableConnections.length === 0 && (
            <Link to="/settings">接入 API</Link>
          )}
        </header>

        <div className="message-canvas">
          {!activeId ? (
            <div className="chat-empty">
              <span><Sparkles size={21} /></span>
              <h2>从项目证据开始问</h2>
              <p>回答会标出论文 ID 与全文页码。</p>
              <Button onClick={() => create.mutate()} loading={create.isPending}>
                建立对话
              </Button>
            </div>
          ) : conversation.isLoading ? (
            <LoadingState label="正在读取对话" />
          ) : conversation.isError ? (
            <ErrorState
              error={conversation.error}
              retry={() => conversation.refetch()}
            />
          ) : (
            <div className="message-list">
              {(conversation.data?.messages ?? []).length === 0 && (
                <div className="conversation-start">
                  <span>{agents.data?.find((agent) => agent.id === conversation.data?.agent_id)?.short_name ?? "证据问答"}</span>
                  <h2>{project.research_question}</h2>
                </div>
              )}
              {conversation.data?.messages?.map((message) => (
                <article
                  className={`message message--${message.role}`}
                  key={message.id}
                  onClick={() =>
                    message.sources.length && setSelectedSources(message.sources)
                  }
                >
                  <header>
                    {message.role === "user" ? "你" : "研究 Agent"}
                    <time>
                      {new Date(message.created_at).toLocaleTimeString("zh-CN", {
                        hour: "2-digit",
                        minute: "2-digit"
                      })}
                    </time>
                  </header>
                  <div className="markdown-body">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {message.content}
                    </ReactMarkdown>
                  </div>
                  {message.sources.length > 0 && (
                    <button
                      className="source-count"
                      onClick={() => setSelectedSources(message.sources)}
                    >
                      {message.sources.length} 个来源
                    </button>
                  )}
                </article>
              ))}
              {send.isPending && (
                <article className="message message--assistant is-thinking">
                  <header>研究 Agent</header>
                  <span /><span /><span />
                </article>
              )}
            </div>
          )}
        </div>

        <form className="chat-composer" onSubmit={submit}>
          <textarea
            value={input}
            rows={2}
            placeholder="比较方法、追问证据，或检查复现条件…"
            disabled={!activeId || send.isPending}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }}
          />
          <button
            disabled={!activeId || !input.trim() || send.isPending}
            aria-label="发送"
          >
            <ArrowUp size={17} />
          </button>
          {send.isError && <small>{send.error.message}</small>}
        </form>
      </main>

      <aside className="source-drawer">
        <header>
          <BookOpen size={15} />
          来源
        </header>
        {selectedSources.length === 0 ? (
          <p>选择一条 Agent 回答查看引用来源。</p>
        ) : (
          selectedSources.map((source) => (
            <Link
              key={source.id}
              to={
                source.kind === "paper"
                  ? `/projects/${project.id}/evidence?paper=${source.id}`
                  : `/projects/${project.id}/documents`
              }
            >
              {source.kind === "paper" ? (
                <BookOpen size={15} />
              ) : (
                <FileText size={15} />
              )}
              <span>
                <strong>
                  {source.kind === "paper" ? source.id : source.title}
                </strong>
                {source.kind === "paper" && <p>{source.title}</p>}
                <small>
                  {source.kind === "paper"
                    ? (source.year ?? "年份未知")
                    : `全文${source.page ? ` · p.${source.page}` : ""}`}
                </small>
              </span>
            </Link>
          ))
        )}
      </aside>
      <ConfirmDeleteModal
        open={Boolean(conversationToDelete)}
        title="删除这段研究对话？"
        description="对话中的问题、回答和来源快照都会被删除，项目论文与证据不会受影响。"
        expected={conversationToDelete?.title ?? ""}
        label="输入对话标题"
        pending={remove.isPending}
        error={remove.error}
        onClose={() => {
          if (!remove.isPending) {
            setConversationToDelete(null);
            remove.reset();
          }
        }}
        onConfirm={() =>
          conversationToDelete && remove.mutate(conversationToDelete)
        }
      />
    </div>
  );
}
