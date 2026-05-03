"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useTranslations, useLocale } from "next-intl";
import { Link } from "@/i18n/navigation";
import {
  ArrowLeftIcon,
  BookOpenIcon,
  RefreshCwIcon,
  ClipboardCheckIcon,
  AlertCircleIcon,
  SearchIcon,
} from "lucide-react";

import { api } from "@/lib/api-client";
import type { Booking, Client } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export default function BookingsPage() {
  const params = useParams<{ id: string }>();
  const t = useTranslations("bookings");
  const common = useTranslations("common");
  const locale = useLocale();
  const dateLocale = locale === "de" ? "de-DE" : "en-US";

  const STATUS_OPTIONS: Record<
    string,
    { label: string; variant: "default" | "secondary" | "outline" | "destructive" }
  > = {
    suggested: { label: t("statusSuggested"), variant: "secondary" },
    approved: { label: t("statusApproved"), variant: "default" },
    rejected: { label: t("statusRejected"), variant: "destructive" },
    exported: { label: t("statusExported"), variant: "outline" },
  };

  const [client, setClient] = useState<Client | null>(null);
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadBookings = useCallback(async () => {
    try {
      const filterParams: Record<string, string> = { client_id: params.id };
      if (statusFilter !== "all") {
        filterParams.status = statusFilter;
      }
      const data = await api.get<Booking[]>("/api/v1/bookings", filterParams);
      setBookings(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Laden fehlgeschlagen");
    }
  }, [params.id, statusFilter]);

  useEffect(() => {
    Promise.all([
      api.get<Client>(`/api/v1/clients/${params.id}`),
      api.get<Booking[]>("/api/v1/bookings", { client_id: params.id }),
    ])
      .then(([c, b]) => {
        setClient(c);
        setBookings(b);
      })
      .catch((err) => setError(err instanceof Error ? err.message : common("errorOccurred")))
      .finally(() => setLoading(false));
  }, [params.id]);

  useEffect(() => {
    if (!loading) {
      loadBookings();
    }
  }, [statusFilter]);

  if (loading) {
    return (
      <main className="mx-auto max-w-6xl px-6 py-10 lg:px-8">
        <div className="flex items-center gap-3">
          <Skeleton className="size-7 rounded-lg" />
          <div className="flex-1">
            <Skeleton className="h-7 w-36" />
            <Skeleton className="mt-2 h-4 w-28" />
          </div>
          <Skeleton className="h-7 w-32 rounded-lg" />
          <Skeleton className="h-7 w-28 rounded-lg" />
        </div>
        <div className="mt-6 rounded-lg border">
          <div className="flex flex-col gap-2 p-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-10 rounded" />
            ))}
          </div>
        </div>
      </main>
    );
  }

  if (error || !client) {
    return (
      <main className="mx-auto max-w-6xl px-6 py-10 lg:px-8">
        <div className="flex flex-col items-center gap-4 rounded-lg border border-destructive/20 bg-destructive/5 p-10 text-center">
          <AlertCircleIcon className="size-8 text-destructive" />
          <div>
            <p className="font-medium text-destructive">{common("loadingError")}</p>
            <p className="mt-1 text-sm text-destructive/80">
              {error ?? common("clientNotFound")}
            </p>
          </div>
        </div>
      </main>
    );
  }

  const bq = search.toLowerCase();
  const filteredBookings = bookings.filter((b) => {
    if (!bq) return true;
    return [
      b.account,
      b.contra_account,
      b.booking_text,
      b.bu_key,
      b.amount,
      b.debit_credit,
      b.bank_name,
      b.bank_iban,
      new Date(b.document_date).toLocaleDateString(dateLocale),
      STATUS_OPTIONS[b.status]?.label,
    ]
      .filter(Boolean)
      .some((val) => val!.toLowerCase().includes(bq));
  });

  const suggestedCount = bookings.filter((b) => b.status === "suggested").length;

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
          <p className="text-sm text-muted-foreground">{client.company_name}</p>
        </div>
        <Select value={statusFilter} onValueChange={(v) => v && setStatusFilter(v)}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t("filterAll")}</SelectItem>
            <SelectItem value="suggested">{t("filterSuggested")}</SelectItem>
            <SelectItem value="approved">{t("filterApproved")}</SelectItem>
            <SelectItem value="rejected">{t("filterRejected")}</SelectItem>
            <SelectItem value="exported">{t("filterExported")}</SelectItem>
          </SelectContent>
        </Select>
        <Button variant="outline" size="sm" onClick={loadBookings}>
          <RefreshCwIcon className="size-3.5" />
          {common("refresh")}
        </Button>
        {suggestedCount > 0 && (
          <Button
            size="sm"
            render={<Link href={`/clients/${params.id}/review`} />}
          >
            <ClipboardCheckIcon className="size-3.5" />
            {t("reviewSuggestions", { count: suggestedCount })}
          </Button>
        )}
      </div>

      {bookings.length === 0 ? (
        <div className="mt-16 flex flex-col items-center gap-4 text-center">
          <div className="flex size-14 items-center justify-center rounded-full bg-muted">
            <BookOpenIcon className="size-6 text-muted-foreground" />
          </div>
          <div>
            <p className="font-medium">{t("noBookingsTitle")}</p>
            <p className="mt-1 text-sm text-muted-foreground">
              {statusFilter !== "all"
                ? t("noBookingsForFilter")
                : t("noBookingsDescription")}
            </p>
          </div>
        </div>
      ) : (
        <div className="mt-6">
          <div className="relative mb-4">
            <SearchIcon className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t("searchPlaceholder")}
              className="pl-8"
            />
          </div>
          <div className="rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("tableDate")}</TableHead>
                <TableHead>{t("tableAccount")}</TableHead>
                <TableHead>{t("tableContraAccount")}</TableHead>
                <TableHead>{t("tableBankAccount")}</TableHead>
                <TableHead>{t("tableBU")}</TableHead>
                <TableHead className="text-right">{t("tableAmount")}</TableHead>
                <TableHead>{t("tableDC")}</TableHead>
                <TableHead>{t("tableBookingText")}</TableHead>
                <TableHead>{t("tableStatus")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredBookings.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={9} className="py-8 text-center text-muted-foreground">
                    {t("noBookingsFound")}
                  </TableCell>
                </TableRow>
              ) : filteredBookings.map((booking) => {
                const statusInfo = STATUS_OPTIONS[booking.status] ?? {
                  label: booking.status,
                  variant: "outline" as const,
                };
                return (
                  <TableRow key={booking.id}>
                    <TableCell className="tabular-nums">
                      {new Date(booking.document_date).toLocaleDateString(dateLocale)}
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {booking.account}
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {booking.contra_account}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {booking.bank_name ? (
                        <div>
                          <span>{booking.bank_name}</span>
                          {booking.bank_iban && (
                            <span className="block font-mono text-[10px]">{booking.bank_iban}</span>
                          )}
                        </div>
                      ) : null}
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {booking.bu_key ?? "–"}
                    </TableCell>
                    <TableCell className="text-right tabular-nums font-medium">
                      {formatCurrency(booking.amount, locale)}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">{booking.debit_credit}</Badge>
                    </TableCell>
                    <TableCell className="max-w-[200px] truncate text-muted-foreground">
                      {booking.booking_text ?? "–"}
                    </TableCell>
                    <TableCell>
                      <Badge variant={statusInfo.variant}>
                        {statusInfo.label}
                      </Badge>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
          </div>
        </div>
      )}
    </main>
  );
}

function formatCurrency(value: string, locale: string): string {
  const num = parseFloat(value);
  if (Number.isNaN(num)) return value;
  return new Intl.NumberFormat(locale === "de" ? "de-DE" : "en-US", {
    style: "currency",
    currency: "EUR",
  }).format(num);
}
