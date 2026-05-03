"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { useTranslations, useLocale } from "next-intl";
import { Link } from "@/i18n/navigation";
import {
  AlertCircleIcon,
  ArrowLeftIcon,
  LandmarkIcon,
  ReceiptIcon,
  ScaleIcon,
  WalletIcon,
} from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { api } from "@/lib/api-client";
import type {
  Client,
  DashboardStats,
  FinancialDashboard,
  MonthlyFinancialBucket,
} from "@/lib/types";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

type PeriodPreset = "all" | "12m" | "6m" | "calendar";

function num(v: string | number): number {
  const n = typeof v === "string" ? Number(v) : v;
  return Number.isFinite(n) ? n : 0;
}

function formatMonthLabel(ym: string): string {
  if (!ym || ym.length < 7) return ym;
  const [y, m] = ym.split("-");
  return `${m}.${y}`;
}

function filterMonthly(
  monthly: MonthlyFinancialBucket[],
  preset: PeriodPreset,
): MonthlyFinancialBucket[] {
  if (!monthly.length) return [];
  const sorted = [...monthly].sort((a, b) => a.month.localeCompare(b.month));

  switch (preset) {
    case "all":
      return sorted;
    case "6m":
      return sorted.slice(-6);
    case "12m":
      return sorted.slice(-12);
    case "calendar": {
      const lastMonth = sorted[sorted.length - 1]?.month ?? "";
      const year = lastMonth.slice(0, 4);
      if (!year) return sorted;
      return sorted.filter((m) => m.month.startsWith(year));
    }
    default:
      return sorted;
  }
}

/** CSS colors — theme-aligned; stacked bar: green revenue, expense uses destructive/red tone */
const CHART = {
  revenue: "var(--chart-3)",
  expense: "color-mix(in oklch, var(--destructive) 92%, transparent)",
  revenueStroke: "oklch(0.52 0.15 155)",
  cashflowPositive: "oklch(0.55 0.14 155)",
  cashflowNegative: "oklch(0.55 0.2 27)",
};

const PIE_PALETTE = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
  "oklch(0.6 0.12 265)",
  "oklch(0.55 0.08 285)",
];

export default function ClientFinancialDashboardPage() {
  const params = useParams<{ id: string }>();
  const t = useTranslations("financialDashboard");
  const common = useTranslations("common");
  const locale = useLocale();
  const dateLocale = locale === "de" ? "de-DE" : "en-US";

  const [client, setClient] = useState<Client | null>(null);
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [financial, setFinancial] = useState<FinancialDashboard | null>(null);
  const [period, setPeriod] = useState<PeriodPreset>("12m");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  function formatEur(value: number): string {
    return new Intl.NumberFormat(dateLocale, {
      style: "currency",
      currency: "EUR",
      maximumFractionDigits: 2,
      minimumFractionDigits: 2,
    }).format(value);
  }

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      api.get<Client>(`/api/v1/clients/${params.id}`),
      api.get<DashboardStats>(`/api/v1/dashboard/${params.id}/stats`),
      api.get<FinancialDashboard>(`/api/v1/dashboard/${params.id}/financial`),
    ])
      .then(([c, s, f]) => {
        if (!cancelled) {
          setClient(c);
          setStats(s);
          setFinancial(f);
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : common("loadingFailed"));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [params.id, common]);

  const filteredMonthly = useMemo(() => {
    if (!financial) return [];
    return filterMonthly(financial.monthly, period);
  }, [financial, period]);

  const revenueLabel = t("revenue");
  const expensesLabel = t("expenses");
  const vendorTotalLabel = t("vendorTotal");

  const kpiTotals = useMemo(() => {
    if (!financial) {
      return { revenue: 0, expenses: 0, bookings: 0 };
    }

    let revenue: number;
    let expenses: number;

    if (period === "all") {
      revenue = num(financial.total_revenue);
      expenses = num(financial.total_expenses);
    } else {
      revenue = filteredMonthly.reduce((s, m) => s + num(m.revenue), 0);
      expenses = filteredMonthly.reduce((s, m) => s + num(m.expenses), 0);
    }

    const bookings = stats?.booking_count ?? 0;

    return { revenue, expenses, bookings };
  }, [financial, filteredMonthly, period, stats]);

  const monthlyChartData = useMemo(
    () =>
      filteredMonthly.map((m) => ({
        month: m.month,
        monthShort: formatMonthLabel(m.month),
        [revenueLabel]: num(m.revenue),
        [expensesLabel]: num(m.expenses),
      })),
    [filteredMonthly, revenueLabel, expensesLabel],
  );

  const cashflowData = useMemo(
    () =>
      filteredMonthly.map((m) => {
        const r = num(m.revenue);
        const e = num(m.expenses);
        return {
          month: m.month,
          monthShort: formatMonthLabel(m.month),
          cashflow: Math.round((r - e) * 100) / 100,
          positive: r - e >= 0 ? r - e : 0,
          negative: r - e < 0 ? r - e : 0,
        };
      }),
    [filteredMonthly],
  );

  const pieData =
    financial?.accounts.map((a) => ({
      name: `${a.label} (${a.account})`,
      value: num(a.total),
    })) ?? [];

  const vendorBarData =
    financial?.vendors.map((v) => ({
      name: v.name.length > 28 ? `${v.name.slice(0, 26)}…` : v.name,
      fullName: v.name,
      [vendorTotalLabel]: num(v.total),
    })) ?? [];

  /** Recharts `Tooltip`: `value` kann `undefined` sein (Strict-Typ). */
  const eurTooltipFormat = (
    value:
      | number
      | string
      | ReadonlyArray<number | string>
      | undefined,
  ) => {
    if (value === undefined || value === null) return "—";
    if (typeof value === "number") return formatEur(value);
    if (typeof value === "string") return formatEur(num(value));
    if (Array.isArray(value)) {
      return value
        .map((v) =>
          typeof v === "number" ? formatEur(v) : formatEur(num(String(v))),
        )
        .join(", ");
    }
    return String(value);
  };

  if (loading) {
    return <DashboardSkeleton />;
  }

  if (error || !client || !financial) {
    return (
      <main className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
        <div className="flex flex-col items-center gap-4 rounded-lg border border-destructive/20 bg-destructive/5 p-10 text-center">
          <AlertCircleIcon className="size-8 text-destructive" />
          <div>
            <p className="font-medium text-destructive">{common("loadingError")}</p>
            <p className="mt-1 text-sm text-destructive/80">
              {error ?? common("dataNotAvailable")}
            </p>
          </div>
          <Button variant="outline" render={<Link href={`/clients/${params.id}`} />}>
            <ArrowLeftIcon data-icon="inline-start" />
            {t("backToClient")}
          </Button>
        </div>
      </main>
    );
  }

  const result = kpiTotals.revenue - kpiTotals.expenses;
  const periodNarrow =
    period !== "all" && filteredMonthly.length < financial.monthly.length;

  return (
    <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-start gap-3">
          <Button variant="ghost" size="icon-sm" render={<Link href={`/clients/${client.id}`} />}>
            <ArrowLeftIcon />
          </Button>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">
              {t("title")}
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              {client.company_name}
              {financial.period_from && financial.period_to && (
                <span className="text-muted-foreground">
                  {" "}
                  · {t("dataRange", { from: financial.period_from, to: financial.period_to })}
                </span>
              )}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 sm:flex-row">
          <span className="text-sm text-muted-foreground shrink-0">{t("period")}</span>
          <Select
            value={period}
            onValueChange={(v) => v && setPeriod(v as PeriodPreset)}
          >
            <SelectTrigger className="min-w-[200px]" size="sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                <SelectItem value="all">{t("periodAll")}</SelectItem>
                <SelectItem value="12m">{t("period12m")}</SelectItem>
                <SelectItem value="6m">{t("period6m")}</SelectItem>
                <SelectItem value="calendar">{t("periodCalendar")}</SelectItem>
              </SelectGroup>
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* KPI */}
      <div className="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">{t("revenue")}</CardTitle>
            <LandmarkIcon className="size-4 text-muted-foreground" aria-hidden />
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold tabular-nums">{formatEur(kpiTotals.revenue)}</p>
            <p className="text-xs text-muted-foreground">
              {period === "all" ? t("revenueAccountsTotal") : t("revenueAccountsPeriod")}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">{t("expenses")}</CardTitle>
            <ReceiptIcon className="size-4 text-muted-foreground" aria-hidden />
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold tabular-nums">{formatEur(kpiTotals.expenses)}</p>
            <p className="text-xs text-muted-foreground">
              {period === "all" ? t("expenseAccountsTotal") : t("expenseAccountsPeriod")}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">{t("result")}</CardTitle>
            <ScaleIcon className="size-4 text-muted-foreground" aria-hidden />
          </CardHeader>
          <CardContent>
            <p
              className={`text-2xl font-bold tabular-nums ${result >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-destructive"}`}
            >
              {formatEur(result)}
            </p>
            <p className="text-xs text-muted-foreground">
              {t("revenueMinusExpenses")}
              {periodNarrow ? ` (${t("period")})` : ""}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">{t("bookings")}</CardTitle>
            <WalletIcon className="size-4 text-muted-foreground" aria-hidden />
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-bold tabular-nums">{kpiTotals.bookings}</p>
            <p className="text-xs text-muted-foreground">{t("allValidStatuses")}</p>
          </CardContent>
        </Card>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        {/* Einnahmen & Ausgaben */}
        <Card className="min-h-[320px]">
          <CardHeader>
            <CardTitle className="text-base">{t("revenueExpensesPerMonth")}</CardTitle>
            <CardDescription>{t("stackedBarsDescription")}</CardDescription>
          </CardHeader>
          <CardContent className="h-[280px]">
            {monthlyChartData.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t("noMonthlyData")}</p>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={monthlyChartData}
                  margin={{ top: 12, right: 8, left: -8, bottom: 4 }}
                >
                  <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                  <XAxis dataKey="monthShort" tick={{ fontSize: 11 }} className="text-muted-foreground" />
                  <YAxis
                    tick={{ fontSize: 11 }}
                    className="text-muted-foreground"
                    tickFormatter={(v: number) =>
                      `${(v / 1000).toLocaleString(dateLocale)}k`
                    }
                  />
                  <Tooltip
                    formatter={(value) => eurTooltipFormat(value)}
                  />
                  <Legend wrapperStyle={{ fontSize: "12px" }} />
                  <Bar
                    dataKey={revenueLabel}
                    name={revenueLabel}
                    stackId="stack"
                    fill={CHART.revenue}
                    radius={[4, 4, 0, 0]}
                  />
                  <Bar
                    dataKey={expensesLabel}
                    name={expensesLabel}
                    stackId="stack"
                    fill={CHART.expense}
                    radius={[4, 4, 0, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        {/* Kontenverteilung */}
        <Card className="min-h-[320px]">
          <CardHeader>
            <CardTitle className="text-base">{t("topAccounts")}</CardTitle>
            <CardDescription>
              {periodNarrow
                ? t("accountDistributionAll")
                : t("accountDistributionSum")}
            </CardDescription>
          </CardHeader>
          <CardContent className="h-[280px]">
            {pieData.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t("noAccountAggregation")}</p>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={pieData}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    innerRadius={56}
                    outerRadius={88}
                    paddingAngle={2}
                  >
                    {pieData.map((_, i) => (
                      <Cell key={i} fill={PIE_PALETTE[i % PIE_PALETTE.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value) => eurTooltipFormat(value)} />
                  <Legend
                    wrapperStyle={{ fontSize: "10px", maxHeight: "100px", overflowY: "auto" }}
                  />
                </PieChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        {/* Cashflow */}
        <Card className="min-h-[320px]">
          <CardHeader>
            <CardTitle className="text-base">{t("cashflowTrend")}</CardTitle>
            <CardDescription>{t("cashflowDescription")}</CardDescription>
          </CardHeader>
          <CardContent className="h-[280px]">
            {cashflowData.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t("noCashflowTimeSeries")}</p>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart
                  data={cashflowData}
                  margin={{ top: 12, right: 8, left: -8, bottom: 4 }}
                >
                  <defs>
                    <linearGradient id="cashflowPosFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={CHART.cashflowPositive} stopOpacity={0.55} />
                      <stop offset="100%" stopColor={CHART.cashflowPositive} stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="cashflowNegFill" x1="0" y1="1" x2="0" y2="0">
                      <stop offset="0%" stopColor={CHART.cashflowNegative} stopOpacity={0.55} />
                      <stop offset="100%" stopColor={CHART.cashflowNegative} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                  <XAxis dataKey="monthShort" tick={{ fontSize: 11 }} />
                  <YAxis
                    tick={{ fontSize: 11 }}
                    tickFormatter={(v: number) =>
                      `${(v / 1000).toLocaleString(dateLocale)}k`
                    }
                  />
                  <Tooltip
                    formatter={(value) => eurTooltipFormat(value)}
                  />
                  <Area
                    type="monotone"
                    dataKey="positive"
                    stroke={CHART.cashflowPositive}
                    strokeWidth={2}
                    fill="url(#cashflowPosFill)"
                    dot={false}
                    isAnimationActive={false}
                  />
                  <Area
                    type="monotone"
                    dataKey="negative"
                    stroke={CHART.cashflowNegative}
                    strokeWidth={2}
                    fill="url(#cashflowNegFill)"
                    dot={false}
                    isAnimationActive={false}
                  />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        {/* Top Lieferanten */}
        <Card className="min-h-[320px]">
          <CardHeader>
            <CardTitle className="text-base">{t("topVendors")}</CardTitle>
            <CardDescription>
              {periodNarrow
                ? t("vendorDescriptionAll")
                : t("vendorDescriptionGrouped")}
            </CardDescription>
          </CardHeader>
          <CardContent className="h-[280px]">
            {vendorBarData.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t("noVendorData")}</p>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  layout="vertical"
                  data={vendorBarData}
                  margin={{ top: 8, right: 16, left: 4, bottom: 8 }}
                >
                  <CartesianGrid strokeDasharray="3 3" horizontal className="stroke-border" />
                  <XAxis type="number" tick={{ fontSize: 11 }} tickFormatter={(v: number) => formatEur(v)} />
                  <YAxis
                    type="category"
                    dataKey="name"
                    width={132}
                    tick={{ fontSize: 10 }}
                    interval={0}
                  />
                  <Tooltip
                    formatter={(value) => eurTooltipFormat(value)}
                  />
                  <Bar dataKey={vendorTotalLabel} name={t("expenses")} radius={[0, 4, 4, 0]} fill="var(--chart-4)" />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </div>
    </main>
  );
}

function DashboardSkeleton() {
  return (
    <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6">
      <div className="flex items-start gap-3">
        <Skeleton className="size-8 rounded-lg shrink-0" />
        <div className="flex-1 space-y-2">
          <Skeleton className="h-8 w-56" />
          <Skeleton className="h-4 w-96 max-w-full" />
        </div>
        <Skeleton className="hidden h-8 w-[200px] sm:block" />
      </div>
      <div className="mt-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-28 rounded-xl" />
        ))}
      </div>
      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Skeleton className="h-[360px] rounded-xl" />
        <Skeleton className="h-[360px] rounded-xl" />
        <Skeleton className="h-[360px] rounded-xl" />
        <Skeleton className="h-[360px] rounded-xl" />
      </div>
    </main>
  );
}
