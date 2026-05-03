"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeftIcon,
  DownloadIcon,
  FileDownIcon,
  RefreshCwIcon,
  AlertCircleIcon,
  SearchIcon,
} from "lucide-react";

import { api } from "@/lib/api-client";
import { showToast } from "@/lib/use-toast";
import type { Client, ExportBatch } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { DatevExportDialog } from "@/components/datev-export-dialog";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function ExportPage() {
  const params = useParams<{ id: string }>();
  const [client, setClient] = useState<Client | null>(null);
  const [exports, setExports] = useState<ExportBatch[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      const [c, e] = await Promise.all([
        api.get<Client>(`/api/v1/clients/${params.id}`),
        api.get<ExportBatch[]>("/api/v1/exports", { client_id: params.id }),
      ]);
      setClient(c);
      setExports(e);
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

  const handleExportCreated = (batch: ExportBatch) => {
    setExports((prev) => [batch, ...prev]);
    showToast(
      `Export erstellt — ${batch.booking_count} Buchungen`,
      "success",
    );
  };

  const handleDownload = (batch: ExportBatch) => {
    const link = document.createElement("a");
    link.href = `${API_BASE_URL}/api/v1/exports/${batch.id}/download`;
    link.download = `EXTF_${batch.date_from}_${batch.date_to}.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  if (loading) {
    return (
      <main className="mx-auto max-w-6xl px-6 py-10 lg:px-8">
        <div className="flex items-center gap-3">
          <Skeleton className="size-7 rounded-lg" />
          <div className="flex-1">
            <Skeleton className="h-7 w-40" />
            <Skeleton className="mt-2 h-4 w-28" />
          </div>
          <Skeleton className="h-7 w-28 rounded-lg" />
        </div>
        <Skeleton className="mt-8 h-40 rounded-lg" />
        <Skeleton className="mt-8 h-8 w-36" />
        <div className="mt-4 rounded-lg border">
          <div className="flex flex-col gap-2 p-4">
            {Array.from({ length: 3 }).map((_, i) => (
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
            <p className="font-medium text-destructive">Fehler beim Laden</p>
            <p className="mt-1 text-sm text-destructive/80">
              {error ?? "Mandant nicht gefunden"}
            </p>
          </div>
        </div>
      </main>
    );
  }

  const eq = search.toLowerCase();
  const filteredExports = exports.filter((batch) => {
    if (!eq) return true;
    return [
      batch.label,
      String(batch.booking_count),
      batch.downloaded_at ? "heruntergeladen" : "bereit",
      new Date(batch.created_at).toLocaleDateString("de-DE"),
      new Date(batch.date_from).toLocaleDateString("de-DE"),
      new Date(batch.date_to).toLocaleDateString("de-DE"),
    ]
      .filter(Boolean)
      .some((val) => val!.toLowerCase().includes(eq));
  });

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
          <h1 className="text-2xl font-bold tracking-tight">DATEV-Export</h1>
          <p className="text-sm text-muted-foreground">{client.company_name}</p>
        </div>
        <Button variant="outline" size="sm" onClick={loadData}>
          <RefreshCwIcon className="size-3.5" />
          Aktualisieren
        </Button>
      </div>

      <div className="mt-8">
        <DatevExportDialog
          clientId={params.id}
          onExportCreated={handleExportCreated}
        />
      </div>

      <div className="mt-8">
        <h2 className="text-lg font-semibold tracking-tight">Export-Historie</h2>
        {exports.length === 0 ? (
          <div className="mt-6 flex flex-col items-center gap-4 text-center">
            <div className="flex size-14 items-center justify-center rounded-full bg-muted">
              <FileDownIcon className="size-6 text-muted-foreground" />
            </div>
            <div>
              <p className="font-medium">Keine Exporte vorhanden</p>
              <p className="mt-1 text-sm text-muted-foreground">
                Erstellen Sie oben Ihren ersten DATEV-Export.
              </p>
            </div>
          </div>
        ) : (
          <div className="mt-4">
            <div className="relative mb-4">
              <SearchIcon className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Exporte durchsuchen…"
                className="pl-8"
              />
            </div>
            <div className="rounded-lg border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Erstellt am</TableHead>
                  <TableHead>Zeitraum</TableHead>
                  <TableHead>Bezeichnung</TableHead>
                  <TableHead className="text-right">Buchungen</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Aktion</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredExports.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={6} className="py-8 text-center text-muted-foreground">
                      Keine Exporte gefunden.
                    </TableCell>
                  </TableRow>
                ) : filteredExports.map((batch) => (
                  <TableRow key={batch.id}>
                    <TableCell className="tabular-nums">
                      {new Date(batch.created_at).toLocaleDateString("de-DE", {
                        day: "2-digit",
                        month: "2-digit",
                        year: "numeric",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </TableCell>
                    <TableCell className="tabular-nums">
                      {new Date(batch.date_from).toLocaleDateString("de-DE")} –{" "}
                      {new Date(batch.date_to).toLocaleDateString("de-DE")}
                    </TableCell>
                    <TableCell className="max-w-[200px] truncate text-muted-foreground">
                      {batch.label ?? "–"}
                    </TableCell>
                    <TableCell className="text-right tabular-nums font-medium">
                      {batch.booking_count}
                    </TableCell>
                    <TableCell>
                      {batch.downloaded_at ? (
                        <Badge variant="outline">Heruntergeladen</Badge>
                      ) : (
                        <Badge variant="secondary">Bereit</Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleDownload(batch)}
                      >
                        <DownloadIcon className="size-3.5" />
                        CSV
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
