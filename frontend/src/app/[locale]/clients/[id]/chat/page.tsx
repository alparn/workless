"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { Link } from "@/i18n/navigation";
import {
  ArrowLeftIcon,
  BotIcon,
  CheckIcon,
  DatabaseIcon,
  FileSearchIcon,
  FileTextIcon,
  SendIcon,
  TerminalIcon,
  Trash2Icon,
  UserIcon,
  WrenchIcon,
} from "lucide-react";
import { useTranslations, useLocale } from "next-intl";

import { api, ApiError } from "@/lib/api-client";
import { showToast } from "@/lib/use-toast";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ── Types ────────────────────────────────────────────────────────────────────

interface HistoryMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

type ToolEvent = { tool: string; label?: string };

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  // For streaming assistant messages
  streaming?: boolean;
  toolEvents?: ToolEvent[];
  activeToolLabel?: string | null;
}

// ── Tool icon map ─────────────────────────────────────────────────────────────

const TOOL_ICONS: Record<string, React.ReactNode> = {
  get_client_overview: <DatabaseIcon className="size-3" />,
  list_bookings: <DatabaseIcon className="size-3" />,
  list_documents: <FileTextIcon className="size-3" />,
  get_document_details: <FileSearchIcon className="size-3" />,
  approve_booking: <CheckIcon className="size-3" />,
  update_booking: <WrenchIcon className="size-3" />,
  create_booking: <FileTextIcon className="size-3" />,
  execute_python: <TerminalIcon className="size-3" />,
};

function getToolIcon(tool: string) {
  return TOOL_ICONS[tool] ?? <WrenchIcon className="size-3" />;
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function ChatPage() {
  const params = useParams<{ id: string }>();
  const t = useTranslations("chat");
  const common = useTranslations("common");
  const locale = useLocale();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [clientName, setClientName] = useState("");
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(true);
  const [streaming, setStreaming] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Load history on mount
  useEffect(() => {
    Promise.all([
      api.get<{ company_name: string }>(`/api/v1/clients/${params.id}`),
      api.get<HistoryMessage[]>(`/api/v1/clients/${params.id}/chat/history`),
    ])
      .then(([client, history]) => {
        setClientName(client.company_name);
        setMessages(
          history.map((m) => ({
            id: m.id,
            role: m.role,
            content: m.content,
          })),
        );
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [params.id]);

  // Auto-scroll on new content
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || streaming) return;

    // Append user message immediately
    const userMsgId = crypto.randomUUID();
    setMessages((prev) => [
      ...prev,
      { id: userMsgId, role: "user", content: text },
    ]);
    setInput("");
    setStreaming(true);

    // Create a placeholder for the streaming assistant message
    const assistantMsgId = crypto.randomUUID();
    setMessages((prev) => [
      ...prev,
      {
        id: assistantMsgId,
        role: "assistant",
        content: "",
        streaming: true,
        toolEvents: [],
        activeToolLabel: null,
      },
    ]);

    try {
      const response = await fetch(
        `${API_BASE}/api/v1/clients/${params.id}/chat`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: text }),
        },
      );

      if (!response.ok || !response.body) {
        throw new Error(`HTTP ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const chunk = JSON.parse(line.slice(6)) as {
              type: string;
              delta?: string;
              tool?: string;
              label?: string;
              message?: string;
            };

            if (chunk.type === "text" && chunk.delta) {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantMsgId
                    ? { ...m, content: m.content + chunk.delta! }
                    : m,
                ),
              );
            } else if (chunk.type === "tool_start" && chunk.tool) {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantMsgId
                    ? {
                        ...m,
                        activeToolLabel: chunk.label ?? chunk.tool ?? null,
                        toolEvents: [
                          ...(m.toolEvents ?? []),
                          { tool: chunk.tool!, label: chunk.label },
                        ],
                      }
                    : m,
                ),
              );
            } else if (chunk.type === "tool_end") {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantMsgId
                    ? { ...m, activeToolLabel: null }
                    : m,
                ),
              );
            } else if (chunk.type === "done") {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantMsgId
                    ? { ...m, streaming: false, activeToolLabel: null }
                    : m,
                ),
              );
            } else if (chunk.type === "error") {
              showToast(chunk.message ?? t("agentError"), "error");
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantMsgId
                    ? {
                        ...m,
                        streaming: false,
                        content:
                          m.content || common("errorOccurred"),
                      }
                    : m,
                ),
              );
            }
          } catch {
            // malformed SSE line — skip
          }
        }
      }
    } catch (err) {
      showToast(
        err instanceof ApiError ? err.detail : common("connectionError"),
        "error",
      );
      setMessages((prev) => prev.filter((m) => m.id !== assistantMsgId));
    } finally {
      setStreaming(false);
      textareaRef.current?.focus();
    }
  }, [input, streaming, params.id, t, common]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleClearHistory = async () => {
    try {
      await api.delete(`/api/v1/clients/${params.id}/chat/history`);
      setMessages([]);
      showToast(t("historyClearedMsg"), "default");
    } catch {
      showToast(common("deleteFailed"), "error");
    }
  };

  if (loading) return <PageSkeleton />;

  return (
    <div className="flex h-[calc(100vh-0px)] flex-col">
      {/* Header */}
      <header className="flex shrink-0 items-center gap-3 border-b bg-background px-6 py-3">
        <Button
          variant="ghost"
          size="icon-sm"
          render={<Link href={`/clients/${params.id}`} />}
        >
          <ArrowLeftIcon />
        </Button>
        <div className="flex flex-1 items-center gap-2">
          <div className="flex size-7 items-center justify-center rounded-full bg-primary/10">
            <BotIcon className="size-4 text-primary" />
          </div>
          <div>
            <p className="text-sm font-semibold leading-none">{t("agentTitle")}</p>
            <p className="text-xs text-muted-foreground">{clientName}</p>
          </div>
        </div>
        {messages.length > 0 && (
          <Button
            variant="ghost"
            size="sm"
            onClick={handleClearHistory}
            className="text-muted-foreground hover:text-destructive"
          >
            <Trash2Icon className="size-3.5" />
            {t("clearHistory")}
          </Button>
        )}
      </header>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-6">
        <div className="mx-auto flex max-w-2xl flex-col gap-4">
          {messages.length === 0 && (
            <EmptyState clientName={clientName} onExample={setInput} />
          )}

          {messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))}

          <div ref={bottomRef} />
        </div>
      </div>

      {/* Input */}
      <div className="shrink-0 border-t bg-background px-4 py-4">
        <div className="mx-auto flex max-w-2xl gap-3">
          <Textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={t("inputPlaceholder")}
            className="min-h-[52px] max-h-[200px] resize-none"
            disabled={streaming}
            rows={1}
          />
          <Button
            onClick={handleSend}
            disabled={!input.trim() || streaming}
            size="icon"
            className="h-[52px] w-[52px] shrink-0"
          >
            <SendIcon className="size-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}

// ── Message bubble ────────────────────────────────────────────────────────────

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";

  return (
    <div className={`flex gap-3 ${isUser ? "flex-row-reverse" : "flex-row"}`}>
      {/* Avatar */}
      <div
        className={`flex size-7 shrink-0 items-center justify-center rounded-full ${
          isUser ? "bg-primary text-primary-foreground" : "bg-muted"
        }`}
      >
        {isUser ? (
          <UserIcon className="size-3.5" />
        ) : (
          <BotIcon className="size-3.5 text-muted-foreground" />
        )}
      </div>

      <div className={`flex max-w-[80%] flex-col gap-1.5 ${isUser ? "items-end" : "items-start"}`}>
        {/* Tool events */}
        {!isUser && (message.toolEvents?.length ?? 0) > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {message.toolEvents!.map((ev, i) => (
              <span
                key={i}
                className="inline-flex items-center gap-1 rounded-full bg-muted px-2.5 py-0.5 text-xs text-muted-foreground"
              >
                {getToolIcon(ev.tool)}
                {ev.label ?? ev.tool}
              </span>
            ))}
          </div>
        )}

        {/* Active tool spinner */}
        {!isUser && message.activeToolLabel && (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-2.5 py-0.5 text-xs text-primary">
            <span className="size-1.5 animate-pulse rounded-full bg-primary" />
            {message.activeToolLabel}
          </span>
        )}

        {/* Text bubble */}
        {(message.content || message.streaming) && (
          <div
            className={`rounded-2xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap ${
              isUser
                ? "bg-primary text-primary-foreground rounded-tr-sm"
                : "bg-muted text-foreground rounded-tl-sm"
            }`}
          >
            {message.content}
            {message.streaming && !message.content && (
              <span className="inline-flex gap-1">
                <span className="size-1.5 animate-bounce rounded-full bg-muted-foreground [animation-delay:0ms]" />
                <span className="size-1.5 animate-bounce rounded-full bg-muted-foreground [animation-delay:150ms]" />
                <span className="size-1.5 animate-bounce rounded-full bg-muted-foreground [animation-delay:300ms]" />
              </span>
            )}
            {message.streaming && message.content && (
              <span className="ml-0.5 inline-block size-2 animate-pulse rounded-sm bg-current opacity-70" />
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Empty state with example prompts ─────────────────────────────────────────

function EmptyState({
  clientName,
  onExample,
}: {
  clientName: string;
  onExample: (text: string) => void;
}) {
  const t = useTranslations("chat");

  const examples = [
    t("example1"),
    t("example2"),
    t("example3"),
    t("example4"),
    t("example5"),
    t("example6"),
  ];

  return (
    <div className="flex flex-col items-center gap-6 py-12 text-center">
      <div className="flex size-14 items-center justify-center rounded-full bg-primary/10">
        <BotIcon className="size-7 text-primary" />
      </div>
      <div>
        <p className="font-semibold">{t("agentTitleFor", { name: clientName })}</p>
        <p className="mt-1 text-sm text-muted-foreground">
          {t("agentDescription")}
        </p>
      </div>
      <div className="grid w-full max-w-lg grid-cols-1 gap-2 sm:grid-cols-2">
        {examples.map((ex) => (
          <button
            key={ex}
            onClick={() => onExample(ex)}
            className="rounded-lg border bg-muted/30 px-3 py-2 text-left text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            {ex}
          </button>
        ))}
      </div>
    </div>
  );
}

function PageSkeleton() {
  return (
    <div className="flex h-screen flex-col">
      <header className="flex items-center gap-3 border-b px-6 py-3">
        <Skeleton className="size-7 rounded-lg" />
        <Skeleton className="h-5 w-40" />
      </header>
      <div className="flex-1 px-6 py-6">
        <div className="mx-auto flex max-w-2xl flex-col gap-4">
          <Skeleton className="ml-auto h-10 w-48 rounded-2xl" />
          <Skeleton className="h-16 w-64 rounded-2xl" />
          <Skeleton className="ml-auto h-8 w-56 rounded-2xl" />
          <Skeleton className="h-20 w-72 rounded-2xl" />
        </div>
      </div>
      <div className="border-t px-4 py-4">
        <Skeleton className="mx-auto h-[52px] max-w-2xl rounded-lg" />
      </div>
    </div>
  );
}
