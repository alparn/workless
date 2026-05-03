"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeftIcon,
  CheckCheckIcon,
  ClipboardCheckIcon,
  RefreshCwIcon,
  AlertCircleIcon,
  SearchIcon,
} from "lucide-react";

import { api, ApiError } from "@/lib/api-client";
import { showToast } from "@/lib/use-toast";
import type {
  BankAccount,
  Client,
  BookingWithDocument,
  BookingUpdate,
  BatchApproveResponse,
} from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { BookingReviewCard } from "@/components/booking-review-card";

export default function ReviewQueuePage() {
  const params = useParams<{ id: string }>();
  const [client, setClient] = useState<Client | null>(null);
  const [bookings, setBookings] = useState<BookingWithDocument[]>([]);
  const [bankAccounts, setBankAccounts] = useState<BankAccount[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [batchLoading, setBatchLoading] = useState(false);

  const loadData = useCallback(async () => {
    try {
      const [c, b, ba] = await Promise.all([
        api.get<Client>(`/api/v1/clients/${params.id}`),
        api.get<BookingWithDocument[]>("/api/v1/bookings/review", {
          client_id: params.id,
        }),
        api.get<BankAccount[]>(`/api/v1/clients/${params.id}/bank-accounts`),
      ]);
      setClient(c);
      setBookings(b);
      setBankAccounts(ba);
      setSelectedIds(new Set());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Laden fehlgeschlagen");
    } finally {
      setLoading(false);
    }
  }, [params.id]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedIds.size === bookings.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(bookings.map((b) => b.id)));
    }
  };

  const handleApprove = async (id: string) => {
    try {
      await api.post(`/api/v1/bookings/${id}/approve`);
      setBookings((prev) => prev.filter((b) => b.id !== id));
      setSelectedIds((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
      showToast("Buchung freigegeben", "success");
    } catch (err) {
      showToast(
        err instanceof ApiError ? err.detail : "Freigabe fehlgeschlagen",
        "error",
      );
    }
  };

  const handleReject = async (id: string) => {
    try {
      await api.post(`/api/v1/bookings/${id}/reject`);
      setBookings((prev) => prev.filter((b) => b.id !== id));
      setSelectedIds((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
      showToast("Buchung abgelehnt", "default");
    } catch (err) {
      showToast(
        err instanceof ApiError ? err.detail : "Ablehnung fehlgeschlagen",
        "error",
      );
    }
  };

  const handleUpdate = async (id: string, data: BookingUpdate) => {
    try {
      const updated = await api.patch<BookingWithDocument>(
        `/api/v1/bookings/${id}`,
        data,
      );
      setBookings((prev) =>
        prev.map((b) => (b.id === id ? { ...b, ...updated } : b)),
      );
      showToast("Buchung gespeichert", "success");
    } catch (err) {
      showToast(
        err instanceof ApiError ? err.detail : "Speichern fehlgeschlagen",
        "error",
      );
      throw err;
    }
  };

  const handleBatchApprove = async () => {
    if (selectedIds.size === 0) return;
    setBatchLoading(true);
    try {
      const result = await api.post<BatchApproveResponse>(
        "/api/v1/bookings/batch-approve",
        { booking_ids: Array.from(selectedIds) },
      );
      const approvedSet = new Set(result.booking_ids);
      setBookings((prev) => prev.filter((b) => !approvedSet.has(b.id)));
      setSelectedIds(new Set());
      showToast(`${result.approved_count} Buchungen freigegeben`, "success");
    } catch (err) {
      showToast(
        err instanceof ApiError ? err.detail : "Massenfreigabe fehlgeschlagen",
        "error",
      );
    } finally {
      setBatchLoading(false);
    }
  };

  if (loading) {
    return (
      <main className="mx-auto max-w-4xl px-6 py-10">
        <div className="flex items-center gap-3">
          <Skeleton className="size-7 rounded-lg" />
          <div className="flex-1">
            <Skeleton className="h-7 w-40" />
            <Skeleton className="mt-2 h-4 w-28" />
          </div>
        </div>
        <Skeleton className="mt-6 h-12 rounded-lg" />
        <div className="mt-4 flex flex-col gap-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-48 rounded-lg" />
          ))}
        </div>
      </main>
    );
  }

  if (error || !client) {
    return (
      <main className="mx-auto max-w-4xl px-6 py-10">
        <div className="flex flex-col items-center gap-4 rounded-lg border border-destructive/20 bg-destructive/5 p-10 text-center">
          <AlertCircleIcon className="size-8 text-destructive" />
          <div>
            <p className="font-medium text-destructive">Fehler beim Laden</p>
            <p className="mt-1 text-sm text-destructive/80">
              {error ?? "Mandant nicht gefunden"}
            </p>
          </div>
          <Button variant="outline" render={<Link href="/clients" />}>
            <ArrowLeftIcon data-icon="inline-start" />
            Zurück
          </Button>
        </div>
      </main>
    );
  }

  const rq = search.toLowerCase();
  const filteredBookings = bookings.filter((b) => {
    if (!rq) return true;
    return [
      b.account,
      b.contra_account,
      b.booking_text,
      b.bu_key,
      b.amount,
      b.debit_credit,
      b.document_filename,
      b.ai_reasoning,
      new Date(b.document_date).toLocaleDateString("de-DE"),
    ]
      .filter(Boolean)
      .some((val) => val!.toLowerCase().includes(rq));
  });

  return (
    <main className="mx-auto max-w-4xl px-6 py-10">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Button
          variant="ghost"
          size="icon-sm"
          render={<Link href={`/clients/${params.id}`} />}
        >
          <ArrowLeftIcon />
        </Button>
        <div className="flex-1">
          <h1 className="text-2xl font-bold tracking-tight">Buchungsvorschläge prüfen</h1>
          <p className="text-sm text-muted-foreground">{client.company_name}</p>
        </div>
        <Button variant="outline" size="sm" onClick={loadData}>
          <RefreshCwIcon className="size-3.5" />
          Aktualisieren
        </Button>
      </div>

      {bookings.length === 0 ? (
        <div className="mt-16 flex flex-col items-center gap-4 text-center">
          <div className="flex size-14 items-center justify-center rounded-full bg-muted">
            <ClipboardCheckIcon className="size-6 text-muted-foreground" />
          </div>
          <div>
            <p className="font-medium">Keine offenen Vorschläge</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Alle KI-Buchungsvorschläge wurden bearbeitet.
            </p>
          </div>
          <Button render={<Link href={`/clients/${params.id}/upload`} />}>
            Neue Belege hochladen
          </Button>
        </div>
      ) : (
        <>
          {/* Search */}
          <div className="relative mt-6">
            <SearchIcon className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Vorschläge durchsuchen…"
              className="pl-8"
            />
          </div>

          {/* Toolbar */}
          <div className="mt-4 flex items-center gap-3 rounded-lg border bg-muted/30 px-4 py-2.5">
            <Checkbox
              checked={
                selectedIds.size === bookings.length && bookings.length > 0
              }
              onCheckedChange={toggleSelectAll}
            />
            <span className="text-sm text-muted-foreground">
              {selectedIds.size > 0
                ? `${selectedIds.size} von ${bookings.length} ausgewählt`
                : `${bookings.length} Vorschläge`}
            </span>
            <div className="flex-1" />
            {selectedIds.size > 0 && (
              <Button
                size="sm"
                onClick={handleBatchApprove}
                disabled={batchLoading}
              >
                <CheckCheckIcon className="size-3.5" />
                {batchLoading
                  ? "Wird freigegeben…"
                  : `${selectedIds.size} freigeben`}
              </Button>
            )}
          </div>

          {/* Cards */}
          <div className="mt-4 flex flex-col gap-4">
            {filteredBookings.length === 0 ? (
              <div className="py-8 text-center text-muted-foreground">
                Keine Vorschläge gefunden.
              </div>
            ) : filteredBookings.map((booking) => (
              <BookingReviewCard
                key={booking.id}
                booking={booking}
                bankAccounts={bankAccounts}
                selected={selectedIds.has(booking.id)}
                onToggleSelect={toggleSelect}
                onApprove={handleApprove}
                onReject={handleReject}
                onUpdate={handleUpdate}
              />
            ))}
          </div>
        </>
      )}
    </main>
  );
}
