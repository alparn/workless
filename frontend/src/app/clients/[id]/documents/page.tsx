"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeftIcon,
  FileTextIcon,
  ImageIcon,
  Trash2Icon,
  UploadIcon,
  RefreshCwIcon,
  AlertCircleIcon,
  SearchIcon,
  RotateCcwIcon,
  Loader2Icon,
} from "lucide-react";

import { api } from "@/lib/api-client";
import { showToast } from "@/lib/use-toast";
import type { Client, DocumentListItem } from "@/lib/types";
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

const STATUS_LABELS: Record<string, { label: string; variant: "default" | "secondary" | "outline" | "destructive" }> = {
  uploaded:          { label: "Hochgeladen",     variant: "outline" },
  ocr_processing:   { label: "OCR läuft…",      variant: "secondary" },
  ocr_complete:     { label: "OCR fertig",       variant: "secondary" },
  ocr_failed:       { label: "OCR Fehler",       variant: "destructive" },
  booking_suggested: { label: "Vorschlag",       variant: "default" },
  booking_failed:   { label: "Buchungsfehler",   variant: "destructive" },
  approved:         { label: "Freigegeben",      variant: "default" },
  booked:           { label: "Gebucht",          variant: "default" },
  exported:         { label: "Exportiert",        variant: "default" },
};

export default function DocumentsPage() {
  const params = useParams<{ id: string }>();
  const [client, setClient] = useState<Client | null>(null);
  const [documents, setDocuments] = useState<DocumentListItem[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reprocessingIds, setReprocessingIds] = useState<Set<string>>(new Set());

  const loadDocuments = useCallback(() => {
    api
      .get<DocumentListItem[]>("/api/v1/documents", { client_id: params.id })
      .then(setDocuments)
      .catch((err) => setError(err.message));
  }, [params.id]);

  useEffect(() => {
    Promise.all([
      api.get<Client>(`/api/v1/clients/${params.id}`),
      api.get<DocumentListItem[]>("/api/v1/documents", { client_id: params.id }),
    ])
      .then(([c, docs]) => {
        setClient(c);
        setDocuments(docs);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [params.id]);

  const handleDelete = async (docId: string) => {
    if (!confirm("Dokument wirklich löschen?")) return;
    try {
      await api.delete(`/api/v1/documents/${docId}`);
      setDocuments((prev) => prev.filter((d) => d.id !== docId));
      showToast("Dokument gelöscht", "success");
    } catch (err) {
      showToast(
        err instanceof Error ? err.message : "Löschen fehlgeschlagen",
        "error",
      );
    }
  };

  const handleReprocess = async (docId: string) => {
    if (!confirm("Dokument erneut verarbeiten? Bestehende Buchungsvorschläge werden gelöscht.")) return;
    setReprocessingIds((prev) => new Set(prev).add(docId));
    try {
      const updated = await api.post<DocumentListItem>(`/api/v1/documents/${docId}/reprocess`);
      setDocuments((prev) =>
        prev.map((d) => (d.id === docId ? { ...d, status: updated.status } : d)),
      );
      showToast("Workflow neu gestartet", "success");
    } catch (err) {
      showToast(
        err instanceof Error ? err.message : "Neuverarbeitung fehlgeschlagen",
        "error",
      );
    } finally {
      setReprocessingIds((prev) => {
        const next = new Set(prev);
        next.delete(docId);
        return next;
      });
    }
  };

  if (loading) {
    return (
      <main className="mx-auto max-w-6xl px-6 py-10 lg:px-8">
        <div className="flex items-center gap-3">
          <Skeleton className="size-7 rounded-lg" />
          <div className="flex-1">
            <Skeleton className="h-7 w-36" />
            <Skeleton className="mt-2 h-4 w-28" />
          </div>
          <Skeleton className="h-7 w-28 rounded-lg" />
          <Skeleton className="h-7 w-24 rounded-lg" />
        </div>
        <div className="mt-6 rounded-lg border">
          <div className="flex flex-col gap-2 p-4">
            {Array.from({ length: 5 }).map((_, i) => (
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

  const dq = search.toLowerCase();
  const filteredDocuments = documents.filter((doc) => {
    if (!dq) return true;
    const statusInfo = STATUS_LABELS[doc.status];
    return [
      doc.original_filename,
      statusInfo?.label,
      doc.status,
      doc.mime_type,
      new Date(doc.uploaded_at).toLocaleDateString("de-DE"),
    ]
      .filter(Boolean)
      .some((val) => val!.toLowerCase().includes(dq));
  });

  return (
    <main className="mx-auto max-w-6xl px-6 py-10 lg:px-8">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon-sm" render={<Link href={`/clients/${params.id}`} />}>
          <ArrowLeftIcon />
        </Button>
        <div className="flex-1">
          <h1 className="text-2xl font-bold tracking-tight">Dokumente</h1>
          <p className="text-sm text-muted-foreground">{client.company_name}</p>
        </div>
        <Button variant="outline" size="sm" onClick={loadDocuments}>
          <RefreshCwIcon className="size-3.5" />
          Aktualisieren
        </Button>
        <Button size="sm" render={<Link href={`/clients/${params.id}/upload`} />}>
          <UploadIcon className="size-3.5" />
          Hochladen
        </Button>
      </div>

      {documents.length === 0 ? (
        <div className="mt-16 flex flex-col items-center gap-4 text-center">
          <div className="flex size-14 items-center justify-center rounded-full bg-muted">
            <FileTextIcon className="size-6 text-muted-foreground" />
          </div>
          <div>
            <p className="font-medium">Noch keine Dokumente</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Laden Sie Rechnungen oder Belege hoch, um zu starten.
            </p>
          </div>
          <Button render={<Link href={`/clients/${params.id}/upload`} />}>
            <UploadIcon className="size-4" />
            Erstes Dokument hochladen
          </Button>
        </div>
      ) : (
        <div className="mt-6">
          <div className="relative mb-4">
            <SearchIcon className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Dokumente durchsuchen…"
              className="pl-8"
            />
          </div>
          <div className="rounded-lg border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-10" />
                <TableHead>Dateiname</TableHead>
                <TableHead>Größe</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Hochgeladen</TableHead>
                <TableHead className="w-20" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredDocuments.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="py-8 text-center text-muted-foreground">
                    Keine Dokumente gefunden.
                  </TableCell>
                </TableRow>
              ) : filteredDocuments.map((doc) => {
                const isPdf = doc.mime_type === "application/pdf";
                const statusInfo = STATUS_LABELS[doc.status] ?? {
                  label: doc.status,
                  variant: "outline" as const,
                };
                const canDelete = !["approved", "booked", "exported"].includes(doc.status);

                return (
                  <TableRow key={doc.id} className="cursor-pointer hover:bg-muted/50 transition-colors">
                    <TableCell>
                      <Link href={`/clients/${params.id}/documents/${doc.id}`}>
                      {isPdf ? (
                        <FileTextIcon className="size-4 text-red-500" />
                      ) : (
                        <ImageIcon className="size-4 text-blue-500" />
                      )}
                      </Link>
                    </TableCell>
                    <TableCell className="max-w-[260px] truncate font-medium">
                      <Link
                        href={`/clients/${params.id}/documents/${doc.id}`}
                        className="hover:text-primary hover:underline underline-offset-2 transition-colors"
                      >
                        {doc.original_filename}
                      </Link>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {doc.file_size_bytes != null
                        ? formatBytes(doc.file_size_bytes)
                        : "–"}
                    </TableCell>
                    <TableCell>
                      <Badge variant={statusInfo.variant}>{statusInfo.label}</Badge>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {new Date(doc.uploaded_at).toLocaleDateString("de-DE", {
                        day: "2-digit",
                        month: "2-digit",
                        year: "numeric",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1">
                        {canReprocess(doc.status) && (
                          <Button
                            variant="ghost"
                            size="icon-xs"
                            disabled={reprocessingIds.has(doc.id)}
                            onClick={() => handleReprocess(doc.id)}
                            title="Erneut verarbeiten"
                          >
                            {reprocessingIds.has(doc.id) ? (
                              <Loader2Icon className="size-3.5 animate-spin" />
                            ) : (
                              <RotateCcwIcon className="size-3.5" />
                            )}
                          </Button>
                        )}
                        {canDelete && (
                          <Button
                            variant="ghost"
                            size="icon-xs"
                            onClick={() => handleDelete(doc.id)}
                          >
                            <Trash2Icon className="size-3.5" />
                          </Button>
                        )}
                      </div>
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

function canReprocess(docStatus: string): boolean {
  return !["exported", "ocr_processing"].includes(docStatus);
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
