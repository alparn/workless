"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import {
  ArrowLeftIcon,
  BellIcon,
  CheckCircle2Icon,
  AlertTriangleIcon,
  AlertCircleIcon,
  InfoIcon,
  RefreshCwIcon,
  PlayIcon,
  CheckIcon,
  EyeIcon,
  ClockIcon,
  ZapIcon,
  ShieldCheckIcon,
  FileSearchIcon,
} from "lucide-react";

import { api } from "@/lib/api-client";
import type {
  AgentNotification,
  AgentRun,
  AgentStatus,
  Client,
} from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";

const SEVERITY_STYLE: Record<string, { icon: typeof InfoIcon; color: string }> = {
  success: { icon: CheckCircle2Icon, color: "text-green-600" },
  info: { icon: InfoIcon, color: "text-blue-600" },
  warning: { icon: AlertTriangleIcon, color: "text-amber-600" },
  error: { icon: AlertCircleIcon, color: "text-red-600" },
};

const RUN_TYPE_ICONS: Record<string, typeof ZapIcon> = {
  ocr_self_healing: FileSearchIcon,
  booking_validation: ShieldCheckIcon,
};

export default function AgentPage() {
  const t = useTranslations("agent");
  const params = useParams<{ id: string }>();
  const [client, setClient] = useState<Client | null>(null);
  const [agentStatus, setAgentStatus] = useState<AgentStatus | null>(null);
  const [notifications, setNotifications] = useState<AgentNotification[]>([]);
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState(false);

  const SEVERITY_CONFIG: Record<string, { icon: typeof InfoIcon; color: string; label: string }> = {
    success: { ...SEVERITY_STYLE.success, label: t("severitySuccess") },
    info: { ...SEVERITY_STYLE.info, label: t("severityInfo") },
    warning: { ...SEVERITY_STYLE.warning, label: t("severityWarning") },
    error: { ...SEVERITY_STYLE.error, label: t("severityError") },
  };

  const CATEGORY_LABELS: Record<string, string> = {
    ocr_self_healing: t("categoryOcrRecovery"),
    booking_validation: t("categoryBookingValidation"),
    stale_detection: t("categoryTimeoutDetection"),
    escalation: t("categoryEscalation"),
  };

  const RUN_TYPE_LABELS: Record<string, { label: string; icon: typeof ZapIcon }> = {
    ocr_self_healing: { label: t("runTypeOcrRecovery"), icon: FileSearchIcon },
    booking_validation: { label: t("runTypeBookingValidation"), icon: ShieldCheckIcon },
  };

  function timeAgo(dateStr: string): string {
    const diff = Date.now() - new Date(dateStr).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return t("justNow");
    if (mins < 60) return t("minutesAgo", { count: mins });
    const hours = Math.floor(mins / 60);
    if (hours < 24) return t("hoursAgo", { count: hours });
    const d = Math.floor(hours / 24);
    return t("daysAgo", { count: d });
  }

  const loadData = useCallback(async () => {
    try {
      const [c, s, n, r] = await Promise.all([
        api.get<Client>(`/api/v1/clients/${params.id}`),
        api.get<AgentStatus>(`/api/v1/agent/${params.id}/status`),
        api.get<AgentNotification[]>(`/api/v1/agent/${params.id}/notifications`),
        api.get<AgentRun[]>(`/api/v1/agent/${params.id}/runs`),
      ]);
      setClient(c);
      setAgentStatus(s);
      setNotifications(n);
      setRuns(r);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, [params.id]);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 15000);
    return () => clearInterval(interval);
  }, [loadData]);

  const handleMarkRead = async (notifId: string) => {
    setNotifications((prev) =>
      prev.map((n) => (n.id === notifId ? { ...n, is_read: true } : n)),
    );
    try {
      await api.post(`/api/v1/agent/${params.id}/notifications/${notifId}/read`);
    } catch {
      setNotifications((prev) =>
        prev.map((n) => (n.id === notifId ? { ...n, is_read: false } : n)),
      );
    }
  };

  const handleResolve = async (notifId: string) => {
    setNotifications((prev) =>
      prev.map((n) =>
        n.id === notifId ? { ...n, is_resolved: true, is_read: true } : n,
      ),
    );
    try {
      await api.post(`/api/v1/agent/${params.id}/notifications/${notifId}/resolve`);
    } catch {
      setNotifications((prev) =>
        prev.map((n) =>
          n.id === notifId ? { ...n, is_resolved: false } : n,
        ),
      );
    }
  };

  const handleMarkAllRead = async () => {
    const prev = notifications;
    setNotifications((n) => n.map((x) => ({ ...x, is_read: true })));
    try {
      await api.post(`/api/v1/agent/${params.id}/notifications/read-all`);
    } catch {
      setNotifications(prev);
    }
  };

  const handleTriggerCycle = async () => {
    setTriggering(true);
    try {
      await api.post(`/api/v1/agent/${params.id}/trigger-cycle`);
      await loadData();
    } finally {
      setTriggering(false);
    }
  };

  if (loading) {
    return (
      <main className="mx-auto max-w-6xl px-6 py-10 lg:px-8">
        <Skeleton className="h-8 w-64" />
        <div className="mt-6 grid gap-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-lg" />
          ))}
        </div>
      </main>
    );
  }

  const counts = agentStatus?.notification_counts;

  return (
    <main className="mx-auto max-w-6xl px-6 py-10 lg:px-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link
            href={`/clients/${params.id}`}
            className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-accent"
          >
            <ArrowLeftIcon className="size-5" />
          </Link>
          <div>
            <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
              <ShieldCheckIcon className="size-6 text-emerald-600" />
              {t("title")}
            </h1>
            <p className="text-sm text-muted-foreground">
              {client?.company_name} — {t("subtitle")}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleTriggerCycle}
            disabled={triggering}
          >
            {triggering ? (
              <RefreshCwIcon className="mr-1.5 size-4 animate-spin" />
            ) : (
              <PlayIcon className="mr-1.5 size-4" />
            )}
            {t("startAudit")}
          </Button>
          <Button variant="ghost" size="sm" onClick={loadData}>
            <RefreshCwIcon className="size-4" />
          </Button>
        </div>
      </div>

      {/* Status Cards */}
      <div className="mt-6 grid grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>{t("status")}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <span
                className={`size-2.5 rounded-full ${agentStatus?.supervisor_enabled ? "bg-green-500" : "bg-gray-400"}`}
              />
              <span className="font-semibold">
                {agentStatus?.supervisor_enabled ? t("active") : t("disabled")}
              </span>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              {t("checksEvery", { seconds: agentStatus?.supervisor_interval_seconds ?? 0 })}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>{t("unreadMessages")}</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">{counts?.unread ?? 0}</p>
            <p className="text-xs text-muted-foreground">
              {t("ofTotalCount", { total: counts?.total ?? 0 })}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>{t("actionRequired")}</CardDescription>
          </CardHeader>
          <CardContent>
            <p className={`text-2xl font-bold ${(counts?.action_required ?? 0) > 0 ? "text-red-600" : ""}`}>
              {counts?.action_required ?? 0}
            </p>
            <p className="text-xs text-muted-foreground">
              {t("openEscalations")}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardDescription>{t("auditRuns")}</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold">
              {agentStatus?.recent_runs_count ?? 0}
            </p>
            <p className="text-xs text-muted-foreground">
              {t("maxOcrRetries", { count: agentStatus?.max_ocr_retries ?? 0 })}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="notifications" className="mt-8">
        <TabsList>
          <TabsTrigger value="notifications" className="gap-1.5">
            <BellIcon className="size-4" />
            {t("messages")}
            {(counts?.unread ?? 0) > 0 && (
              <Badge variant="destructive" className="ml-1 h-5 min-w-5 justify-center px-1.5 text-[10px]">
                {counts!.unread}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="runs" className="gap-1.5">
            <ClockIcon className="size-4" />
            {t("history")}
          </TabsTrigger>
        </TabsList>

        {/* Notifications Tab */}
        <TabsContent value="notifications" className="mt-4">
          {notifications.length > 0 && (
            <div className="mb-4 flex justify-end">
              <Button variant="ghost" size="sm" onClick={handleMarkAllRead}>
                <CheckIcon className="mr-1.5 size-3.5" />
                {t("markAllRead")}
              </Button>
            </div>
          )}
          {notifications.length === 0 ? (
            <Card>
              <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
                <ShieldCheckIcon className="size-10 text-muted-foreground/50" />
                <p className="text-muted-foreground">
                  {t("noMessages")}
                </p>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-3">
              {notifications.map((n) => {
                const sev = SEVERITY_CONFIG[n.severity] ?? SEVERITY_CONFIG.info;
                const Icon = sev.icon;
                return (
                  <Card
                    key={n.id}
                    className={`transition-colors ${!n.is_read ? "border-l-4 border-l-primary bg-accent/30" : ""} ${n.is_resolved ? "opacity-60" : ""}`}
                  >
                    <CardContent className="flex gap-4 py-4">
                      <div className={`mt-0.5 ${sev.color}`}>
                        <Icon className="size-5" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-start justify-between gap-2">
                          <div>
                            <h3 className={`font-medium ${!n.is_read ? "font-semibold" : ""}`}>
                              {n.title}
                            </h3>
                            <div className="mt-0.5 flex items-center gap-2 text-xs text-muted-foreground">
                              <Badge variant="outline" className="text-[10px]">
                                {CATEGORY_LABELS[n.category] ?? n.category}
                              </Badge>
                              <span>{timeAgo(n.created_at)}</span>
                            </div>
                          </div>
                          <div className="flex items-center gap-1.5 shrink-0">
                            {!n.is_read && (
                              <Button
                                variant="outline"
                                size="sm"
                                className="h-7 gap-1 px-2 text-xs"
                                onClick={() => handleMarkRead(n.id)}
                              >
                                <EyeIcon className="size-3.5" />
                                {t("markRead")}
                              </Button>
                            )}
                            {n.action_required && !n.is_resolved && (
                              <Button
                                variant="outline"
                                size="sm"
                                className="h-7 px-2"
                                onClick={() => handleResolve(n.id)}
                              >
                                <CheckCircle2Icon className="mr-1 size-3.5" />
                                {t("markDone")}
                              </Button>
                            )}
                          </div>
                        </div>
                        <p className="mt-2 text-sm text-muted-foreground whitespace-pre-line">
                          {n.message}
                        </p>
                        {n.entity_type && n.entity_id && (
                          <div className="mt-2">
                            <Link
                              href={
                                n.entity_type === "document"
                                  ? `/clients/${params.id}/documents`
                                  : `/clients/${params.id}/bookings`
                              }
                              className="text-xs text-primary hover:underline"
                            >
                              {n.entity_type === "document" ? t("goToDocument") : t("goToBooking")}
                            </Link>
                          </div>
                        )}
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          )}
        </TabsContent>

        {/* Runs Tab */}
        <TabsContent value="runs" className="mt-4">
          {runs.length === 0 ? (
            <Card>
              <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
                <ClockIcon className="size-10 text-muted-foreground/50" />
                <p className="text-muted-foreground">
                  {t("noRuns")}
                </p>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-3">
              {runs.map((run) => {
                const runMeta = RUN_TYPE_LABELS[run.run_type] ?? {
                  label: run.run_type,
                  icon: ZapIcon,
                };
                const RunIcon = runMeta.icon;
                const isSuccess = run.status === "success" || run.status === "completed";
                return (
                  <Card key={run.id}>
                    <CardContent className="flex items-center gap-4 py-4">
                      <div className={isSuccess ? "text-green-600" : "text-amber-600"}>
                        <RunIcon className="size-5" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-medium">{runMeta.label}</span>
                          <Badge
                            variant={isSuccess ? "default" : "destructive"}
                            className="text-[10px]"
                          >
                            {isSuccess ? t("statusSuccess") : run.status}
                          </Badge>
                          {run.strategy && (
                            <Badge variant="outline" className="text-[10px]">
                              {run.strategy}
                            </Badge>
                          )}
                        </div>
                        <p className="mt-0.5 text-sm text-muted-foreground">
                          {run.result_summary ?? run.error ?? "—"}
                        </p>
                        <div className="mt-1 flex items-center gap-4 text-xs text-muted-foreground">
                          <span>{timeAgo(run.started_at)}</span>
                          {run.duration_ms != null && (
                            <span>{(run.duration_ms / 1000).toFixed(1)}s</span>
                          )}
                          {run.items_fixed > 0 && (
                            <span className="text-green-600">
                              {t("fixedCount", { count: run.items_fixed })}
                            </span>
                          )}
                          {run.items_flagged > 0 && (
                            <span className="text-amber-600">
                              {t("flaggedCount", { count: run.items_flagged })}
                            </span>
                          )}
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
            </div>
          )}
        </TabsContent>
      </Tabs>
    </main>
  );
}
