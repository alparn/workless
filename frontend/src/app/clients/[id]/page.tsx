"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeftIcon,
  UploadIcon,
  ClipboardCheckIcon,
  FileDownIcon,
  FileTextIcon,
  BookOpenIcon,
  BotIcon,
  BrainCircuitIcon,
  FolderOpenIcon,
  ActivityIcon,
  AlertCircleIcon,
  PencilIcon,
  HelpCircleIcon,
  SendIcon,
  UserIcon,
  CheckIcon,
  DatabaseIcon,
  FileSearchIcon,
  TerminalIcon,
  WrenchIcon,
  Trash2Icon,
  BarChart3Icon,
  SettingsIcon,
  LoaderIcon,
  CheckCircle2Icon,
  AlertTriangleIcon,
  ZapIcon,
} from "lucide-react";

import { api, ApiError } from "@/lib/api-client";
import { showToast } from "@/lib/use-toast";
import type { Client, ClarificationListResponse, DashboardStats, ActivityEntry, AgentRun, AgentNotificationCount, DocumentListItem } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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
  streaming?: boolean;
  toolEvents?: ToolEvent[];
  activeToolLabel?: string | null;
}

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

const ACTIVE_PROCESSING_STATUSES = ["ocr_processing", "ocr_complete", "classified"];
const RECENT_THRESHOLD_MS = 2 * 60 * 1000;
const FAILED_THRESHOLD_MS = 10 * 60 * 1000;

const EXAMPLES = [
  "Zeig mir alle offenen Buchungsvorschläge",
  "Welche Belege wurden diese Woche hochgeladen?",
  "Übersicht aller Buchungen für April 2026",
  "Positionen, die noch Klärung benötigen?",
];

export default function ClientDashboardPage() {
  const params = useParams<{ id: string }>();
  const [client, setClient] = useState<Client | null>(null);
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [activity, setActivity] = useState<ActivityEntry[]>([]);
  const [clarificationCount, setClarificationCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [agentRuns, setAgentRuns] = useState<AgentRun[]>([]);
  const [agentNotifCounts, setAgentNotifCounts] = useState<AgentNotificationCount | null>(null);
  const [processingDocs, setProcessingDocs] = useState<DocumentListItem[]>([]);

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chatLoading, setChatLoading] = useState(true);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const chatContainerRef = useRef<HTMLDivElement>(null);
  const shouldAutoScroll = useRef(false);

  useEffect(() => {
    Promise.all([
      api.get<Client>(`/api/v1/clients/${params.id}`),
      api.get<DashboardStats>(`/api/v1/dashboard/${params.id}/stats`),
      api.get<ActivityEntry[]>(`/api/v1/dashboard/${params.id}/activity`, {
        limit: 15,
      }),
      api.get<ClarificationListResponse>(`/api/v1/clients/${params.id}/clarifications`),
    ])
      .then(([c, s, a, cl]) => {
        setClient(c);
        setStats(s);
        setActivity(a);
        setClarificationCount(cl.total_count);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [params.id]);

  const loadAgentData = useCallback(async () => {
    try {
      const [runs, status] = await Promise.all([
        api.get<AgentRun[]>(`/api/v1/agent/${params.id}/runs`),
        api.get<{ notification_counts: AgentNotificationCount }>(`/api/v1/agent/${params.id}/status`),
      ]);
      setAgentRuns(runs);
      setAgentNotifCounts(status.notification_counts);
    } catch {
      /* agent data is non-critical */
    }
  }, [params.id]);

  const hasActiveRun = agentRuns.some((r) => r.status === "running" || r.status === "pending");
  const pollingInterval = hasActiveRun ? 5000 : 30000;

  useEffect(() => {
    loadAgentData();
    const interval = setInterval(loadAgentData, pollingInterval);
    return () => clearInterval(interval);
  }, [loadAgentData, pollingInterval]);

  const loadProcessingDocs = useCallback(async () => {
    try {
      const allDocs = await api.get<DocumentListItem[]>("/api/v1/documents", {
        client_id: params.id,
      });
      const now = Date.now();
      const inProgress = allDocs.filter((d) => {
        if (ACTIVE_PROCESSING_STATUSES.includes(d.status)) return true;
        if (d.status === "uploaded") {
          const age = now - new Date(d.uploaded_at).getTime();
          return age < RECENT_THRESHOLD_MS;
        }
        if (d.status === "ocr_failed" || d.status === "booking_failed") {
          const age = now - new Date(d.uploaded_at).getTime();
          return age < FAILED_THRESHOLD_MS;
        }
        return false;
      });
      setProcessingDocs(inProgress);

      if (inProgress.length === 0 && processingDocs.length > 0) {
        const [s, a] = await Promise.all([
          api.get<DashboardStats>(`/api/v1/dashboard/${params.id}/stats`),
          api.get<ActivityEntry[]>(`/api/v1/dashboard/${params.id}/activity`, { limit: 15 }),
        ]);
        setStats(s);
        setActivity(a);
      }
    } catch {
      /* non-critical */
    }
  }, [params.id, processingDocs.length]);

  const hasProcessingDocs = processingDocs.length > 0;

  useEffect(() => {
    loadProcessingDocs();
    const interval = setInterval(loadProcessingDocs, hasProcessingDocs ? 3000 : 15000);
    return () => clearInterval(interval);
  }, [loadProcessingDocs, hasProcessingDocs]);

  useEffect(() => {
    api
      .get<HistoryMessage[]>(`/api/v1/clients/${params.id}/chat/history`)
      .then((history) => {
        setMessages(
          history.map((m) => ({
            id: m.id,
            role: m.role,
            content: m.content,
          })),
        );
        requestAnimationFrame(() => {
          if (chatContainerRef.current) {
            chatContainerRef.current.scrollTop = chatContainerRef.current.scrollHeight;
          }
        });
      })
      .catch(() => {})
      .finally(() => setChatLoading(false));
  }, [params.id]);

  useEffect(() => {
    if (!shouldAutoScroll.current) return;
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || streaming) return;

    shouldAutoScroll.current = true;
    const userMsgId = crypto.randomUUID();
    setMessages((prev) => [
      ...prev,
      { id: userMsgId, role: "user", content: text },
    ]);
    setInput("");
    setStreaming(true);

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
              showToast(chunk.message ?? "Agent-Fehler", "error");
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantMsgId
                    ? {
                        ...m,
                        streaming: false,
                        content:
                          m.content || "Es ist ein Fehler aufgetreten.",
                      }
                    : m,
                ),
              );
            }
          } catch {
            // malformed SSE line
          }
        }
      }
    } catch (err) {
      showToast(
        err instanceof ApiError ? err.detail : "Verbindungsfehler",
        "error",
      );
      setMessages((prev) => prev.filter((m) => m.id !== assistantMsgId));
    } finally {
      setStreaming(false);
      textareaRef.current?.focus();
    }
  }, [input, streaming, params.id]);

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
      showToast("Verlauf gelöscht", "default");
    } catch {
      showToast("Löschen fehlgeschlagen", "error");
    }
  };

  if (loading) {
    return <DashboardSkeleton />;
  }

  if (error || !client) {
    return (
      <main className="mx-auto max-w-6xl px-6 py-10 lg:px-8">
        <div className="flex flex-col items-center gap-4 rounded-lg border border-destructive/20 bg-destructive/5 p-10 text-center">
          <AlertCircleIcon className="size-8 text-destructive" />
          <div>
            <p className="font-medium text-destructive">
              Fehler beim Laden
            </p>
            <p className="mt-1 text-sm text-destructive/80">
              {error ?? "Mandant nicht gefunden"}
            </p>
          </div>
          <Button variant="outline" render={<Link href="/clients" />}>
            <ArrowLeftIcon data-icon="inline-start" />
            Zurück zur Übersicht
          </Button>
        </div>
      </main>
    );
  }

  const id = client.id;

  return (
    <main className="mx-auto max-w-6xl px-6 py-8 lg:px-8">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="icon" render={<Link href="/clients" />}>
          <ArrowLeftIcon />
        </Button>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight">
              {client.company_name}
            </h1>
            {client.legal_form && (
              <Badge variant="secondary">{client.legal_form}</Badge>
            )}
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            {[client.tax_number, client.vat_id, client.chart_of_accounts].filter(Boolean).join(" · ") ||
              "Keine Steuerdaten hinterlegt"}
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          render={<Link href={`/clients/${id}/edit`} />}
        >
          <PencilIcon className="size-3.5" />
          Stammdaten
        </Button>
      </div>

      {/* Feature-Kacheln oben */}
      <div className="mt-8 grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
        <FeatureCard
          href={`/clients/${id}/upload`}
          icon={<UploadIcon className="size-5" />}
          title="Belege & Kontoauszüge hochladen"
          stat={stats ? `${stats.document_count} Dokumente` : undefined}
          color="blue"
        />
        <FeatureCard
          href={`/clients/${id}/review`}
          icon={<ClipboardCheckIcon className="size-5" />}
          title="Buchungsvorschläge prüfen"
          stat={stats && stats.pending_reviews > 0 ? `${stats.pending_reviews} offen` : "Alles erledigt"}
          badge={stats && stats.pending_reviews > 0 ? String(stats.pending_reviews) : undefined}
          color="amber"
        />
        <FeatureCard
          href={`/clients/${id}/clarifications`}
          icon={<HelpCircleIcon className="size-5" />}
          title="Rückfragen"
          stat={clarificationCount > 0 ? `${clarificationCount} offen` : "Keine offenen"}
          badge={clarificationCount > 0 ? String(clarificationCount) : undefined}
          badgeVariant="destructive"
          color="red"
        />
        <FeatureCard
          href={`/clients/${id}/export`}
          icon={<FileDownIcon className="size-5" />}
          title="DATEV-Export"
          stat={stats ? `${stats.total_export_batches} Exporte` : undefined}
          color="green"
        />
        <FeatureCard
          href={`/clients/${id}/documents`}
          icon={<FolderOpenIcon className="size-5" />}
          title="Dokumente"
          stat={stats ? `${stats.document_count} gespeichert` : undefined}
          color="purple"
        />
        <FeatureCard
          href={`/clients/${id}/bookings`}
          icon={<BookOpenIcon className="size-5" />}
          title="Buchungen"
          stat={stats ? `${stats.booking_count} gesamt` : undefined}
          color="slate"
        />
        <FeatureCard
          href={`/clients/${id}/dashboard`}
          icon={<BarChart3Icon className="size-5" />}
          title="Finanz-Dashboard"
          stat="Einnahmen, Ausgaben & Cashflow"
          color="indigo"
        />
        <FeatureCard
          href={`/clients/${id}/agent`}
          icon={<ClipboardCheckIcon className="size-5" />}
          title="Prüfer"
          stat="Automatische Qualitätssicherung"
          color="emerald"
        />
        <FeatureCard
          href={`/clients/${id}/skills`}
          icon={<BrainCircuitIcon className="size-5" />}
          title="Gelernte Regeln"
          stat="KI-Skills & Muster"
          color="purple"
        />
        <FeatureCard
          href={`/clients/${id}/settings`}
          icon={<SettingsIcon className="size-5" />}
          title="KI-Einstellungen"
          stat="Anbieter, Modelle & API-Keys"
          color="slate"
        />
        <FeatureCard
          href={`/clients/${id}/usage`}
          icon={<ActivityIcon className="size-5" />}
          title="KI-Verbrauch"
          stat="Tokens & Kosten"
          color="indigo"
        />
      </div>

      {/* Haupt-Bereich: Chat mittig + Sidebar rechts */}
      <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-[1fr_340px]" style={{ height: "calc(100vh - 340px)", minHeight: "480px" }}>
        {/* Chat-Fenster (Hauptbereich) */}
        <Card className="flex flex-col overflow-hidden h-full">
          {/* Chat Header */}
          <div className="flex shrink-0 items-center gap-3 border-b px-4 py-3">
            <div className="flex size-8 items-center justify-center rounded-full bg-primary/10">
              <BotIcon className="size-4 text-primary" />
            </div>
            <div className="flex-1">
              <p className="text-sm font-semibold leading-none">KI-Buchhalter</p>
              <p className="text-xs text-muted-foreground">
                Fragen stellen, Anweisungen geben, Buchungen bearbeiten
              </p>
            </div>
            <Button
              variant="ghost"
              size="sm"
              render={<Link href={`/clients/${id}/chat`} />}
              className="text-xs text-muted-foreground"
            >
              Vollbild
            </Button>
            {messages.length > 0 && (
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={handleClearHistory}
                className="text-muted-foreground hover:text-destructive"
              >
                <Trash2Icon className="size-3.5" />
              </Button>
            )}
          </div>

          {/* Chat Messages */}
          <div ref={chatContainerRef} className="flex-1 overflow-y-auto px-4 py-4">
            <div className="mx-auto flex max-w-2xl flex-col gap-3">
              {chatLoading ? (
                <div className="flex flex-col gap-3 py-6">
                  <Skeleton className="ml-auto h-8 w-40 rounded-2xl" />
                  <Skeleton className="h-12 w-56 rounded-2xl" />
                </div>
              ) : messages.length === 0 ? (
                <div className="flex flex-col items-center gap-4 py-8 text-center">
                  <div className="flex size-12 items-center justify-center rounded-full bg-primary/10">
                    <BotIcon className="size-6 text-primary" />
                  </div>
                  <div>
                    <p className="font-semibold text-sm">
                      Ihr KI-Buchhalter für {client.company_name}
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Stellen Sie Fragen zu Belegen, Buchungen oder Exporten
                    </p>
                  </div>
                  <div className="grid w-full grid-cols-1 gap-1.5 sm:grid-cols-2">
                    {EXAMPLES.map((ex) => (
                      <button
                        key={ex}
                        onClick={() => setInput(ex)}
                        className="rounded-lg border bg-muted/30 px-3 py-2 text-left text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                      >
                        {ex}
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                messages.map((msg) => (
                  <MessageBubble key={msg.id} message={msg} />
                ))
              )}
              <div ref={bottomRef} />
            </div>
          </div>

          {/* Chat Input */}
          <div className="shrink-0 border-t px-4 py-3">
            <div className="mx-auto flex max-w-2xl gap-2">
              <Textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Nachricht eingeben… (Enter = Senden)"
                className="min-h-[44px] max-h-[120px] resize-none text-sm"
                disabled={streaming}
                rows={1}
              />
              <Button
                onClick={handleSend}
                disabled={!input.trim() || streaming}
                size="icon"
                className="h-[44px] w-[44px] shrink-0"
              >
                <SendIcon className="size-4" />
              </Button>
            </div>
          </div>
        </Card>

        {/* Rechte Sidebar — scrollbar */}
        <div className="min-h-0 overflow-y-auto overflow-x-hidden rounded-xl">
          <div className="flex flex-col gap-4">
            {/* KI-Aktivität: Verarbeitung + Agent-Runs */}
            <SidebarAiActivity
              processingDocs={processingDocs}
              agentRuns={agentRuns}
              notifCounts={agentNotifCounts}
              clientId={id}
            />

            {/* Kennzahlen-Übersicht */}
            {stats && (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-semibold">Auf einen Blick</CardTitle>
                </CardHeader>
                <CardContent className="grid grid-cols-2 gap-3">
                  <MiniStat label="Dokumente" value={stats.document_count} />
                  <MiniStat label="Buchungen" value={stats.booking_count} />
                  <MiniStat label="Offen" value={stats.pending_reviews} highlight={stats.pending_reviews > 0} />
                  <MiniStat label="Freigegeben" value={stats.approved_bookings} />
                  <MiniStat label="Exportiert" value={stats.exported_bookings} />
                  <MiniStat label="Exporte" value={stats.total_export_batches} />
                </CardContent>
              </Card>
            )}

            {/* Letzte Aktivitäten */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-sm font-semibold">
                  <ActivityIcon className="size-4" />
                  Letzte Aktivitäten
                </CardTitle>
              </CardHeader>
              <CardContent>
                {activity.length === 0 ? (
                  <div className="flex flex-col items-center justify-center gap-2 py-6 text-center text-muted-foreground">
                    <ActivityIcon className="size-5" />
                    <p className="text-sm">Noch keine Aktivitäten.</p>
                  </div>
                ) : (
                  <ul className="flex flex-col gap-2.5">
                    {activity.slice(0, 8).map((entry) => (
                      <li
                        key={entry.id}
                        className="flex items-start gap-2.5"
                      >
                        <div className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-muted">
                          <ActivityDot action={entry.action} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-foreground leading-snug text-[13px]">{entry.summary}</p>
                          <p className="text-xs text-muted-foreground mt-0.5">
                            {formatRelativeTime(entry.created_at)}
                          </p>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </main>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";

  return (
    <div className={`flex gap-2.5 ${isUser ? "flex-row-reverse" : "flex-row"}`}>
      <div
        className={`flex size-6 shrink-0 items-center justify-center rounded-full ${
          isUser ? "bg-primary text-primary-foreground" : "bg-muted"
        }`}
      >
        {isUser ? (
          <UserIcon className="size-3" />
        ) : (
          <BotIcon className="size-3 text-muted-foreground" />
        )}
      </div>

      <div className={`flex max-w-[80%] flex-col gap-1 ${isUser ? "items-end" : "items-start"}`}>
        {!isUser && (message.toolEvents?.length ?? 0) > 0 && (
          <div className="flex flex-wrap gap-1">
            {message.toolEvents!.map((ev, i) => (
              <span
                key={i}
                className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-0.5 text-[10px] text-muted-foreground"
              >
                {getToolIcon(ev.tool)}
                {ev.label ?? ev.tool}
              </span>
            ))}
          </div>
        )}

        {!isUser && message.activeToolLabel && (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-2 py-0.5 text-[10px] text-primary">
            <span className="size-1.5 animate-pulse rounded-full bg-primary" />
            {message.activeToolLabel}
          </span>
        )}

        {(message.content || message.streaming) && (
          <div
            className={`rounded-2xl px-3 py-2 text-sm leading-relaxed whitespace-pre-wrap ${
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

const PIPELINE_STEPS = [
  { key: "uploaded", label: "Hochgeladen" },
  { key: "ocr_processing", label: "Texterkennung" },
  { key: "ocr_complete", label: "Klassifizierung" },
  { key: "classified", label: "Buchung" },
  { key: "booking_suggested", label: "Fertig" },
] as const;

const DOC_STATUS_LABELS: Record<string, string> = {
  uploaded: "Wird vorbereitet…",
  ocr_processing: "Texterkennung…",
  ocr_complete: "Klassifizierung…",
  classified: "Buchungsvorschlag…",
  ocr_failed: "Fehler",
  booking_failed: "Fehler",
};

const RUN_TYPE_LABELS: Record<string, string> = {
  ocr_self_healing: "OCR-Reparatur",
  booking_validation: "Buchungsprüfung",
  document_processing: "Belegverarbeitung",
  export_preparation: "Export-Vorbereitung",
};

function getStepIndex(status: string): number {
  const idx = PIPELINE_STEPS.findIndex((s) => s.key === status);
  return idx === -1 ? 0 : idx;
}

function SidebarAiActivity({
  processingDocs,
  agentRuns,
  notifCounts,
  clientId,
}: {
  processingDocs: DocumentListItem[];
  agentRuns: AgentRun[];
  notifCounts: AgentNotificationCount | null;
  clientId: string;
}) {
  const activeRuns = agentRuns.filter((r) => r.status === "running" || r.status === "pending");
  const recentRuns = agentRuns
    .filter((r) => r.status === "success" || r.status === "completed")
    .slice(0, 2);

  const activeDocs = processingDocs.filter((d) => d.status !== "ocr_failed" && d.status !== "booking_failed");
  const failedDocs = processingDocs.filter((d) => d.status === "ocr_failed" || d.status === "booking_failed");

  const hasAnything =
    activeDocs.length > 0 ||
    failedDocs.length > 0 ||
    activeRuns.length > 0 ||
    recentRuns.length > 0 ||
    (notifCounts?.action_required ?? 0) > 0;

  if (!hasAnything) return null;

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-sm font-semibold">
            <ZapIcon className="size-4 text-emerald-600" />
            KI-Aktivität
          </CardTitle>
          <Link
            href={`/clients/${clientId}/agent`}
            className="text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            Details →
          </Link>
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        {/* Eskalationen */}
        {notifCounts && notifCounts.action_required > 0 && (
          <Link
            href={`/clients/${clientId}/agent`}
            className="flex items-center gap-2 rounded-lg bg-red-50 px-2.5 py-2 transition-colors hover:bg-red-100 dark:bg-red-950 dark:hover:bg-red-900"
          >
            <AlertTriangleIcon className="size-3.5 text-red-600 shrink-0 dark:text-red-400" />
            <span className="text-xs font-medium text-red-900 dark:text-red-100">
              {notifCounts.action_required} Eskalation{notifCounts.action_required > 1 ? "en" : ""}
            </span>
          </Link>
        )}

        {/* Dokumente in Verarbeitung */}
        {activeDocs.map((doc) => {
          const stepIdx = getStepIndex(doc.status);
          const progress = Math.round((stepIdx / (PIPELINE_STEPS.length - 1)) * 100);
          return (
            <div key={doc.id} className="rounded-lg bg-blue-50/70 px-2.5 py-2 dark:bg-blue-950/50">
              <div className="flex items-center gap-2 mb-1.5">
                <LoaderIcon className="size-3 animate-spin text-blue-600 shrink-0 dark:text-blue-400" />
                <span className="text-xs font-medium truncate">{doc.original_filename}</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="flex-1 h-1 rounded-full bg-blue-200/60 dark:bg-blue-800/40">
                  <div
                    className="h-full rounded-full bg-blue-500 transition-all duration-700"
                    style={{ width: `${progress}%` }}
                  />
                </div>
                <span className="text-[10px] text-blue-600 font-medium shrink-0 dark:text-blue-400">
                  {DOC_STATUS_LABELS[doc.status] ?? doc.status}
                </span>
              </div>
            </div>
          );
        })}

        {/* Fehlgeschlagene Dokumente */}
        {failedDocs.map((doc) => (
          <div key={doc.id} className="flex items-center gap-2 rounded-lg bg-red-50/70 px-2.5 py-2 dark:bg-red-950/50">
            <AlertCircleIcon className="size-3.5 text-red-500 shrink-0" />
            <span className="text-xs truncate">{doc.original_filename}</span>
            <span className="ml-auto text-[10px] text-red-600 shrink-0 dark:text-red-400">Fehler</span>
          </div>
        ))}

        {/* Laufende Agent-Runs */}
        {activeRuns.map((run) => (
          <div key={run.id} className="flex items-center gap-2 rounded-lg bg-blue-50/70 px-2.5 py-2 dark:bg-blue-950/50">
            <LoaderIcon className="size-3 animate-spin text-blue-600 shrink-0 dark:text-blue-400" />
            <span className="text-xs font-medium">
              {RUN_TYPE_LABELS[run.run_type] ?? run.run_type}
            </span>
          </div>
        ))}

        {/* Letzte abgeschlossene Runs */}
        {recentRuns.map((run) => (
          <div key={run.id} className="flex items-center gap-2 rounded-lg bg-emerald-50/70 px-2.5 py-1.5 dark:bg-emerald-950/50">
            <CheckCircle2Icon className="size-3 text-emerald-600 shrink-0 dark:text-emerald-400" />
            <span className="text-xs text-muted-foreground truncate">
              {RUN_TYPE_LABELS[run.run_type] ?? run.run_type}
              {run.items_fixed > 0 && ` — ${run.items_fixed} behoben`}
            </span>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function FeatureCard({
  href,
  icon,
  title,
  stat,
  badge,
  badgeVariant = "default",
  color,
}: {
  href: string;
  icon: React.ReactNode;
  title: string;
  stat?: string;
  badge?: string;
  badgeVariant?: "default" | "destructive" | "secondary" | "outline";
  color: "blue" | "amber" | "red" | "green" | "purple" | "slate" | "emerald" | "indigo";
}) {
  const colorMap = {
    blue: "bg-blue-50 text-blue-600 dark:bg-blue-950 dark:text-blue-400",
    amber: "bg-amber-50 text-amber-600 dark:bg-amber-950 dark:text-amber-400",
    red: "bg-red-50 text-red-600 dark:bg-red-950 dark:text-red-400",
    green: "bg-emerald-50 text-emerald-600 dark:bg-emerald-950 dark:text-emerald-400",
    purple: "bg-purple-50 text-purple-600 dark:bg-purple-950 dark:text-purple-400",
    slate: "bg-slate-50 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
    emerald: "bg-emerald-50 text-emerald-600 dark:bg-emerald-950 dark:text-emerald-400",
    indigo: "bg-indigo-50 text-indigo-600 dark:bg-indigo-950 dark:text-indigo-400",
  };

  return (
    <Link href={href} className="group">
      <Card className="h-full transition-all group-hover:bg-muted/50 group-hover:shadow-md">
        <CardContent className="flex flex-col items-center gap-3 px-4 py-5 text-center">
          <div className="relative">
            <div className={`flex size-11 items-center justify-center rounded-xl ${colorMap[color]}`}>
              {icon}
            </div>
            {badge && (
              <Badge variant={badgeVariant} className="absolute -right-2.5 -top-1.5 text-[10px] px-1.5 py-0 min-w-5 justify-center">
                {badge}
              </Badge>
            )}
          </div>
          <div>
            <p className="text-[13px] font-semibold leading-snug">{title}</p>
            {stat && (
              <p className="mt-1 text-xs text-muted-foreground leading-relaxed">{stat}</p>
            )}
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}

function MiniStat({
  label,
  value,
  highlight = false,
}: {
  label: string;
  value: number;
  highlight?: boolean;
}) {
  return (
    <div className={`rounded-lg px-3 py-2.5 ${highlight ? "bg-amber-50 dark:bg-amber-950" : "bg-muted/50"}`}>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className={`text-xl font-bold tabular-nums ${highlight ? "text-amber-600 dark:text-amber-400" : ""}`}>
        {value}
      </p>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="font-medium">{value}</dd>
    </div>
  );
}

function ActivityDot({ action }: { action: string }) {
  const colorMap: Record<string, string> = {
    approved: "bg-emerald-500",
    rejected: "bg-destructive",
    created: "bg-blue-500",
    exported: "bg-primary",
    updated: "bg-amber-500",
  };
  const color = colorMap[action] ?? "bg-muted-foreground";
  return <div className={`size-1.5 rounded-full ${color}`} />;
}

function DashboardSkeleton() {
  return (
    <main className="mx-auto max-w-6xl px-6 py-8 lg:px-8">
      <div className="flex items-center gap-4">
        <Skeleton className="size-8 rounded-lg" />
        <div className="flex-1">
          <Skeleton className="h-7 w-48" />
          <Skeleton className="mt-2 h-4 w-32" />
        </div>
      </div>

      <div className="mt-8 grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
        {Array.from({ length: 11 }).map((_, i) => (
          <Skeleton key={i} className="h-28 rounded-xl" />
        ))}
      </div>

      <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-[1fr_340px]">
        <Skeleton className="h-[480px] rounded-xl" />
        <div className="flex flex-col gap-4">
          <Skeleton className="h-52 rounded-xl" />
          <Skeleton className="h-52 rounded-xl" />
          <Skeleton className="h-36 rounded-xl" />
        </div>
      </div>
    </main>
  );
}

function formatRelativeTime(isoDate: string): string {
  const diff = Date.now() - new Date(isoDate).getTime();
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 1) return "Gerade eben";
  if (minutes < 60) return `vor ${minutes} Min.`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `vor ${hours} Std.`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `vor ${days} Tag${days > 1 ? "en" : ""}`;
  return new Date(isoDate).toLocaleDateString("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}
