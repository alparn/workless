"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useTranslations, useLocale } from "next-intl";
import { Link } from "@/i18n/navigation";
import {
  ArrowLeftIcon,
  AlertCircleIcon,
  ActivityIcon,
  CoinsIcon,
  HashIcon,
  ZapIcon,
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

import { api, ApiError } from "@/lib/api-client";
import type { UsageSummary, UsageLogEntry } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export default function AiUsagePage() {
  const t = useTranslations("usage");
  const common = useTranslations("common");
  const locale = useLocale();
  const params = useParams<{ id: string }>();
  const [days, setDays] = useState(30);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<UsageSummary | null>(null);
  const [logs, setLogs] = useState<UsageLogEntry[]>([]);

  const PERIOD_OPTIONS = [
    { value: 7, label: t("days7") },
    { value: 30, label: t("days30") },
    { value: 90, label: t("days90") },
  ];

  function fmtNumber(n: number): string {
    return n.toLocaleString(locale);
  }

  function fmtCost(value: string): string {
    const num = parseFloat(value);
    return num.toLocaleString(locale, { style: "currency", currency: "EUR" });
  }

  function fmtDate(iso: string): string {
    return new Date(iso).toLocaleDateString(locale, {
      day: "2-digit",
      month: "2-digit",
    });
  }

  function fmtDateTime(iso: string): string {
    return new Date(iso).toLocaleString(locale, {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  useEffect(() => {
    setLoading(true);
    setError(null);

    Promise.all([
      api.get<UsageSummary>(`/api/v1/clients/${params.id}/ai-usage/summary`, { days }),
      api.get<UsageLogEntry[]>(`/api/v1/clients/${params.id}/ai-usage`, { days, limit: 20 }),
    ])
      .then(([s, l]) => {
        setSummary(s);
        setLogs(l);
      })
      .catch((err) => {
        setError(err instanceof ApiError ? err.detail : t("loadError"));
      })
      .finally(() => setLoading(false));
  }, [params.id, days, t]);

  if (loading) {
    return (
      <main className="mx-auto max-w-6xl px-6 py-10 lg:px-8">
        <div className="flex items-center gap-3">
          <Skeleton className="size-7 rounded-lg" />
          <div>
            <Skeleton className="h-7 w-64" />
            <Skeleton className="mt-2 h-4 w-40" />
          </div>
        </div>
        <div className="mt-8 grid grid-cols-2 gap-4 sm:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-lg" />
          ))}
        </div>
        <Skeleton className="mt-6 h-64 rounded-lg" />
        <Skeleton className="mt-6 h-48 rounded-lg" />
      </main>
    );
  }

  if (error || !summary) {
    return (
      <main className="mx-auto max-w-6xl px-6 py-10 lg:px-8">
        <div className="flex flex-col items-center gap-4 rounded-lg border border-destructive/20 bg-destructive/5 p-10 text-center">
          <AlertCircleIcon className="size-8 text-destructive" />
          <div>
            <p className="font-medium text-destructive">{t("loadError")}</p>
            <p className="mt-1 text-sm text-destructive/80">{error ?? t("loadError")}</p>
          </div>
          <Button variant="outline" render={<Link href={`/clients/${params.id}`} />}>
            <ArrowLeftIcon data-icon="inline-start" />
            {common("back")}
          </Button>
        </div>
      </main>
    );
  }

  const chartData = summary.by_day.map((d) => ({
    date: fmtDate(d.date),
    input_tokens: d.input_tokens,
    output_tokens: d.output_tokens,
  }));

  return (
    <main className="mx-auto max-w-6xl px-6 py-10 lg:px-8">
      <div className="flex items-center gap-3">
        <Button
          variant="ghost"
          size="icon-sm"
          render={<Link href={`/clients/${params.id}`} />}
        >
          <ArrowLeftIcon />
        </Button>
        <div className="flex-1">
          <h1 className="text-2xl font-bold tracking-tight">{t("title")}</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {t("description")}
          </p>
        </div>
        <div className="flex gap-1">
          {PERIOD_OPTIONS.map((opt) => (
            <Button
              key={opt.value}
              variant={days === opt.value ? "default" : "outline"}
              size="sm"
              onClick={() => setDays(opt.value)}
            >
              {opt.label}
            </Button>
          ))}
        </div>
      </div>

      <div className="mt-8 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <SummaryCard
          icon={<HashIcon className="size-4" />}
          label={t("inputTokens")}
          value={fmtNumber(summary.total_input_tokens)}
          color="blue"
        />
        <SummaryCard
          icon={<ZapIcon className="size-4" />}
          label={t("outputTokens")}
          value={fmtNumber(summary.total_output_tokens)}
          color="purple"
        />
        <SummaryCard
          icon={<CoinsIcon className="size-4" />}
          label={t("estimatedCosts")}
          value={fmtCost(summary.total_cost_eur)}
          color="amber"
        />
        <SummaryCard
          icon={<ActivityIcon className="size-4" />}
          label={t("callCount")}
          value={fmtNumber(summary.call_count)}
          color="emerald"
        />
      </div>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle className="text-sm">{t("dailyUsage")}</CardTitle>
          <CardDescription>{t("dailyUsageDescription")}</CardDescription>
        </CardHeader>
        <CardContent>
          {chartData.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-2 py-12 text-muted-foreground">
              <ActivityIcon className="size-6" />
              <p className="text-sm">{t("noData")}</p>
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={chartData}>
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 11 }}
                  tickLine={false}
                  axisLine={false}
                />
                <YAxis
                  tick={{ fontSize: 11 }}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v: number) => {
                    if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
                    if (v >= 1_000) return `${(v / 1_000).toFixed(0)}k`;
                    return String(v);
                  }}
                />
                <Tooltip
                  formatter={(value: unknown, name: unknown) => [
                    fmtNumber(Number(value)),
                    name === "input_tokens" ? "Input" : "Output",
                  ]}
                  labelFormatter={(label: unknown) => String(label)}
                  contentStyle={{
                    borderRadius: "8px",
                    fontSize: "12px",
                    border: "1px solid var(--border)",
                  }}
                />
                <Bar
                  dataKey="input_tokens"
                  stackId="tokens"
                  fill="var(--color-blue-500, #3b82f6)"
                  radius={[0, 0, 0, 0]}
                  name="input_tokens"
                />
                <Bar
                  dataKey="output_tokens"
                  stackId="tokens"
                  fill="var(--color-purple-500, #a855f7)"
                  radius={[4, 4, 0, 0]}
                  name="output_tokens"
                />
              </BarChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      {summary.by_operation.length > 0 && (
        <Card className="mt-6">
          <CardHeader>
            <CardTitle className="text-sm">{t("breakdownByFunction")}</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("function")}</TableHead>
                  <TableHead className="text-right">{t("tokens")}</TableHead>
                  <TableHead className="text-right">{t("costs")}</TableHead>
                  <TableHead className="text-right">{t("calls")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {summary.by_operation.map((op) => (
                  <TableRow key={op.operation}>
                    <TableCell>
                      <Badge variant="secondary">{op.operation}</Badge>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {fmtNumber(op.total_tokens)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {fmtCost(op.cost_eur)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {fmtNumber(op.count)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {logs.length > 0 && (
        <Card className="mt-6">
          <CardHeader>
            <CardTitle className="text-sm">{t("recentCalls")}</CardTitle>
            <CardDescription>{t("recentCallsDescription")}</CardDescription>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("time")}</TableHead>
                  <TableHead>{t("provider")}</TableHead>
                  <TableHead>{t("model")}</TableHead>
                  <TableHead>{t("function")}</TableHead>
                  <TableHead className="text-right">{t("tokens")}</TableHead>
                  <TableHead className="text-right">{t("costs")}</TableHead>
                  <TableHead className="text-right">{t("duration")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {logs.map((entry) => (
                  <TableRow key={entry.id}>
                    <TableCell className="text-muted-foreground">
                      {fmtDateTime(entry.created_at)}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">{entry.provider}</Badge>
                    </TableCell>
                    <TableCell className="max-w-[160px] truncate text-xs">
                      {entry.model}
                    </TableCell>
                    <TableCell>
                      <Badge variant="secondary">{entry.operation}</Badge>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {fmtNumber(entry.total_tokens)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {fmtCost(entry.estimated_cost_eur)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums text-muted-foreground">
                      {entry.duration_ms >= 1000
                        ? `${(entry.duration_ms / 1000).toFixed(1)}s`
                        : `${entry.duration_ms}ms`}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </main>
  );
}

function SummaryCard({
  icon,
  label,
  value,
  color,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  color: "blue" | "purple" | "amber" | "emerald";
}) {
  const colorMap = {
    blue: "bg-blue-50 text-blue-600 dark:bg-blue-950 dark:text-blue-400",
    purple: "bg-purple-50 text-purple-600 dark:bg-purple-950 dark:text-purple-400",
    amber: "bg-amber-50 text-amber-600 dark:bg-amber-950 dark:text-amber-400",
    emerald: "bg-emerald-50 text-emerald-600 dark:bg-emerald-950 dark:text-emerald-400",
  };

  return (
    <Card>
      <CardContent className="flex items-center gap-3 px-4 py-4">
        <div className={`flex size-9 items-center justify-center rounded-lg ${colorMap[color]}`}>
          {icon}
        </div>
        <div>
          <p className="text-xs text-muted-foreground">{label}</p>
          <p className="text-lg font-bold tabular-nums">{value}</p>
        </div>
      </CardContent>
    </Card>
  );
}
