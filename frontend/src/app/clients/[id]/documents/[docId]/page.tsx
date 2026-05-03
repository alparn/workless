"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeftIcon,
  FileTextIcon,
  CheckCircle2Icon,
  AlertCircleIcon,
  ClockIcon,
  BookOpenIcon,
  BrainCircuitIcon,
  RotateCcwIcon,
  Loader2Icon,
  BadgeCheckIcon,
  XCircleIcon,
  HelpCircleIcon,
  ZapIcon,
  ShieldCheckIcon,
  AlertTriangleIcon,
  CircleSlashIcon,
} from "lucide-react";

import { api } from "@/lib/api-client";
import { showToast } from "@/lib/use-toast";
import type { Client } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

import { Skeleton } from "@/components/ui/skeleton";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface DocumentDetail {
  id: string;
  client_id: string;
  original_filename: string;
  mime_type: string;
  file_size_bytes: number | null;
  ocr_provider: string | null;
  ocr_confidence: string | null;
  extraction: Record<string, unknown> | null;
  status: string;
  error_details: string | null;
  uploaded_at: string | null;
  ocr_completed_at: string | null;
  approved_at: string | null;
}

interface BookingDetail {
  id: string;
  amount: string;
  debit_credit: string;
  account: string;
  contra_account: string;
  bu_key: string | null;
  document_date: string | null;
  booking_text: string | null;
  reference_1: string | null;
  suggested_by: string;
  ai_confidence: string | null;
  ai_reasoning: string | null;
  status: string;
  needs_clarification: boolean;
  clarification_question: string | null;
  created_at: string | null;
  tax_hints: {
    deductibility: "full" | "partial" | "none";
    deductible_percent?: number;
    hint?: string;
    action_required?: string;
    legal_basis?: string;
  } | null;
}

interface DocumentDetailResponse {
  document: DocumentDetail;
  bookings: BookingDetail[];
  booking_count: number;
}

const DOC_TYPE_LABELS: Record<string, string> = {
  invoice: "Eingangsrechnung",
  outgoing_invoice: "Ausgangsrechnung",
  credit_note: "Gutschrift",
  receipt: "Kassenbon / Quittung",
  bank_statement: "Kontoauszug",
  other: "Sonstiges",
};

const STATUS_CONFIG: Record<
  string,
  { label: string; icon: typeof CheckCircle2Icon; color: string }
> = {
  uploaded: { label: "Hochgeladen", icon: ClockIcon, color: "text-gray-500" },
  ocr_processing: { label: "OCR läuft…", icon: Loader2Icon, color: "text-blue-500" },
  ocr_complete: { label: "OCR fertig", icon: CheckCircle2Icon, color: "text-blue-600" },
  ocr_failed: { label: "OCR Fehler", icon: AlertCircleIcon, color: "text-red-500" },
  booking_suggested: { label: "Buchungsvorschlag", icon: BrainCircuitIcon, color: "text-amber-600" },
  booking_failed: { label: "Buchungsfehler", icon: XCircleIcon, color: "text-red-500" },
  approved: { label: "Freigegeben", icon: BadgeCheckIcon, color: "text-green-600" },
  exported: { label: "Exportiert", icon: CheckCircle2Icon, color: "text-green-700" },
};

const BOOKING_STATUS: Record<string, { label: string; variant: "default" | "secondary" | "outline" | "destructive" }> = {
  suggested: { label: "Vorschlag", variant: "secondary" },
  approved: { label: "Freigegeben", variant: "default" },
  rejected: { label: "Abgelehnt", variant: "destructive" },
  corrected: { label: "Korrigiert", variant: "outline" },
  exported: { label: "Exportiert", variant: "outline" },
};

function formatCurrency(value: string | number): string {
  const num = typeof value === "string" ? parseFloat(value) : value;
  if (Number.isNaN(num)) return String(value);
  return new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR" }).format(num);
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return "–";
  return new Date(dateStr).toLocaleDateString("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

function formatDateTime(dateStr: string | null): string {
  if (!dateStr) return "–";
  return new Date(dateStr).toLocaleDateString("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function DocumentViewPage() {
  const params = useParams<{ id: string; docId: string }>();
  const [client, setClient] = useState<Client | null>(null);
  const [data, setData] = useState<DocumentDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [reprocessing, setReprocessing] = useState(false);

  const loadData = useCallback(async () => {
    try {
      const [c, d] = await Promise.all([
        api.get<Client>(`/api/v1/clients/${params.id}`),
        api.get<DocumentDetailResponse>(`/api/v1/documents/${params.docId}/detail`),
      ]);
      setClient(c);
      setData(d);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, [params.id, params.docId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleReprocess = async () => {
    if (!confirm("Dokument erneut verarbeiten?")) return;
    setReprocessing(true);
    try {
      await api.post(`/api/v1/documents/${params.docId}/reprocess`);
      showToast("Workflow neu gestartet", "success");
      setTimeout(loadData, 3000);
    } catch (err) {
      showToast(err instanceof Error ? err.message : "Fehler", "error");
    } finally {
      setReprocessing(false);
    }
  };

  if (loading) {
    return (
      <main className="flex h-screen">
        <div className="w-1/2 bg-muted p-4"><Skeleton className="h-full rounded-lg" /></div>
        <div className="w-1/2 p-6"><Skeleton className="h-8 w-48" /><Skeleton className="mt-4 h-64" /></div>
      </main>
    );
  }

  if (!data || !client) {
    return (
      <main className="flex items-center justify-center h-screen">
        <div className="text-center">
          <AlertCircleIcon className="mx-auto size-10 text-destructive" />
          <p className="mt-2 font-medium">Dokument nicht gefunden</p>
          <Button variant="outline" className="mt-4" render={<Link href={`/clients/${params.id}/documents`} />}>
            Zurück
          </Button>
        </div>
      </main>
    );
  }

  const doc = data.document;
  const bookings = data.bookings;
  const extraction = doc.extraction || {};
  const statusInfo = STATUS_CONFIG[doc.status] ?? STATUS_CONFIG.uploaded;
  const StatusIcon = statusInfo.icon;
  const pdfUrl = `${API_BASE}/api/v1/documents/${doc.id}/file`;

  return (
    <main className="flex h-screen overflow-hidden">
      {/* Left: PDF Viewer */}
      <div className="flex w-1/2 flex-col border-r bg-muted/30">
        <div className="flex shrink-0 items-center gap-3 border-b bg-background px-4 py-3">
          <Button variant="ghost" size="sm" render={<Link href={`/clients/${params.id}/documents`} />}>
            <ArrowLeftIcon className="size-4" />
          </Button>
          <FileTextIcon className="size-4 text-red-500" />
          <span className="flex-1 truncate text-sm font-medium">{doc.original_filename}</span>
          <Button
            variant="ghost"
            size="sm"
            className="text-xs"
            onClick={() => window.open(pdfUrl, "_blank")}
          >
            Neues Fenster
          </Button>
        </div>
        <div className="flex-1">
          {doc.mime_type === "application/pdf" ? (
            <iframe
              src={`${pdfUrl}#toolbar=1&navpanes=0`}
              className="h-full w-full border-0"
              title={doc.original_filename}
            />
          ) : (
            <div className="flex h-full items-center justify-center p-8">
              <img
                src={pdfUrl}
                alt={doc.original_filename}
                className="max-h-full max-w-full rounded-lg object-contain shadow-lg"
              />
            </div>
          )}
        </div>
      </div>

      {/* Right: Document Data */}
      <div className="flex w-1/2 flex-col overflow-y-auto">
        <div className="shrink-0 border-b bg-background px-6 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-lg font-bold">{doc.original_filename}</h1>
              <p className="text-sm text-muted-foreground">{client.company_name}</p>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={handleReprocess}
                disabled={reprocessing || doc.status === "exported"}
              >
                {reprocessing ? (
                  <Loader2Icon className="mr-1.5 size-3.5 animate-spin" />
                ) : (
                  <RotateCcwIcon className="mr-1.5 size-3.5" />
                )}
                Neu verarbeiten
              </Button>
            </div>
          </div>

          {/* Status bar */}
          <div className="mt-3 flex items-center gap-6 text-sm">
            <div className={`flex items-center gap-1.5 font-medium ${statusInfo.color}`}>
              <StatusIcon className="size-4" />
              {statusInfo.label}
            </div>
            {doc.ocr_confidence && (
              <div className="flex items-center gap-1 text-muted-foreground">
                <ZapIcon className="size-3.5" />
                OCR {(parseFloat(doc.ocr_confidence) * 100).toFixed(0)}%
              </div>
            )}
            {doc.ocr_provider && (
              <span className="text-xs text-muted-foreground">{doc.ocr_provider}</span>
            )}
          </div>
        </div>

        <div className="flex-1 space-y-5 px-6 py-5">
          {/* Error */}
          {doc.error_details && (
            <Card className="border-destructive/30 bg-destructive/5">
              <CardContent className="flex items-start gap-3 py-3">
                <AlertCircleIcon className="mt-0.5 size-4 text-destructive shrink-0" />
                <p className="text-sm text-destructive">{doc.error_details}</p>
              </CardContent>
            </Card>
          )}

          {/* Extracted Data */}
          {Object.keys(extraction).length > 0 && (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-semibold">Extrahierte Daten</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 gap-x-8 gap-y-2">
                  {extraction.document_type != null && (
                    <DataRow label="Dokumenttyp" value={DOC_TYPE_LABELS[String(extraction.document_type)] ?? String(extraction.document_type)} />
                  )}
                  {extraction.vendor_name != null && (
                    <DataRow
                      label={extraction.document_type === "outgoing_invoice" ? "Rechnungssteller" : "Lieferant"}
                      value={String(extraction.vendor_name)}
                    />
                  )}
                  {extraction.document_type === "outgoing_invoice" && extraction.recipient_name != null && (
                    <DataRow label="Kunde" value={String(extraction.recipient_name)} />
                  )}
                  {extraction.invoice_number != null && (
                    <DataRow label="Rechnungsnr." value={String(extraction.invoice_number)} />
                  )}
                  {extraction.document_date != null && (
                    <DataRow label="Datum" value={formatDate(String(extraction.document_date))} />
                  )}
                  {extraction.total_gross != null && (
                    <DataRow label="Brutto" value={formatCurrency(String(extraction.total_gross))} highlight />
                  )}
                  {extraction.total_net != null && (
                    <DataRow label="Netto" value={formatCurrency(String(extraction.total_net))} />
                  )}
                  {extraction.vat_amount != null && (
                    <DataRow label="USt-Betrag" value={formatCurrency(String(extraction.vat_amount))} />
                  )}
                  {extraction.vat_rate != null && (
                    <DataRow label="USt-Satz" value={`${String(extraction.vat_rate)}%`} />
                  )}
                  {extraction.bank_name != null && (
                    <DataRow label="Bank" value={String(extraction.bank_name)} />
                  )}
                  {extraction.iban != null && (
                    <DataRow label="IBAN" value={String(extraction.iban)} mono />
                  )}
                  {extraction.bic != null && (
                    <DataRow label="BIC" value={String(extraction.bic)} mono />
                  )}
                  {extraction.account_holder != null && (
                    <DataRow label="Kontoinhaber" value={String(extraction.account_holder)} />
                  )}
                  {extraction.period_from != null && (
                    <DataRow label="Zeitraum von" value={formatDate(String(extraction.period_from))} />
                  )}
                  {extraction.period_to != null && (
                    <DataRow label="Zeitraum bis" value={formatDate(String(extraction.period_to))} />
                  )}
                </div>
              </CardContent>
            </Card>
          )}

          {/* Bookings */}
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-semibold flex items-center gap-2">
                  <BookOpenIcon className="size-4" />
                  Buchungen ({bookings.length})
                </CardTitle>
              </div>
            </CardHeader>
            <CardContent>
              {bookings.length === 0 ? (
                <p className="py-4 text-center text-sm text-muted-foreground">
                  Keine Buchungen vorhanden
                </p>
              ) : (
                <div className="space-y-3">
                  {bookings.map((b) => {
                    const bStatus = BOOKING_STATUS[b.status] ?? { label: b.status, variant: "outline" as const };
                    return (
                      <div
                        key={b.id}
                        className="rounded-lg border p-3 transition-colors hover:bg-muted/30"
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-3">
                            <span className="text-lg font-bold tabular-nums">
                              {formatCurrency(b.amount)}
                            </span>
                            <Badge variant="outline" className="font-mono text-xs">
                              {b.debit_credit}
                            </Badge>
                            <Badge variant={bStatus.variant} className="text-[10px]">
                              {bStatus.label}
                            </Badge>
                          </div>
                          <span className="text-xs text-muted-foreground">
                            {formatDate(b.document_date)}
                          </span>
                        </div>

                        <div className="mt-2 grid grid-cols-3 gap-2 text-xs">
                          <div>
                            <span className="text-muted-foreground">Konto</span>
                            <p className="font-mono font-medium">{b.account}</p>
                          </div>
                          <div>
                            <span className="text-muted-foreground">Gegenkonto</span>
                            <p className="font-mono font-medium">{b.contra_account}</p>
                          </div>
                          <div>
                            <span className="text-muted-foreground">BU-Schlüssel</span>
                            <p className="font-mono font-medium">{b.bu_key ?? "–"}</p>
                          </div>
                        </div>

                        {b.booking_text && (
                          <p className="mt-1.5 text-xs text-muted-foreground">
                            {b.booking_text}
                          </p>
                        )}

                        {b.ai_reasoning && (
                          <div className="mt-2 rounded bg-muted/50 px-2.5 py-1.5 text-xs text-muted-foreground">
                            <span className="font-medium text-foreground/70">KI-Begründung:</span>{" "}
                            {b.ai_reasoning}
                          </div>
                        )}

                        {b.needs_clarification && b.clarification_question && (
                          <div className="mt-2 flex items-start gap-1.5 rounded bg-amber-50 dark:bg-amber-950/30 px-2.5 py-1.5 text-xs text-amber-700 dark:text-amber-400">
                            <HelpCircleIcon className="mt-0.5 size-3.5 shrink-0" />
                            {b.clarification_question}
                          </div>
                        )}

                        {b.tax_hints && (
                          <div className="mt-2">
                            <TaxHintsInline hints={b.tax_hints} />
                          </div>
                        )}

                        {b.ai_confidence && (
                          <div className="mt-1.5 flex items-center gap-2 text-[10px] text-muted-foreground">
                            <span>Konfidenz: {(parseFloat(b.ai_confidence) * 100).toFixed(0)}%</span>
                            <span>•</span>
                            <span>{b.suggested_by}</span>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Metadata */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-semibold">Metadaten</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-x-8 gap-y-2 text-xs">
                <DataRow label="Hochgeladen" value={formatDateTime(doc.uploaded_at)} />
                <DataRow label="OCR abgeschlossen" value={formatDateTime(doc.ocr_completed_at)} />
                <DataRow label="Freigegeben" value={formatDateTime(doc.approved_at)} />
                <DataRow label="Dateigröße" value={doc.file_size_bytes ? formatBytes(doc.file_size_bytes) : "–"} />
                <DataRow label="MIME-Typ" value={doc.mime_type} mono />
                <DataRow label="Dokument-ID" value={doc.id.slice(0, 8) + "…"} mono />
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </main>
  );
}

function DataRow({
  label,
  value,
  mono,
  highlight,
}: {
  label: string;
  value: string;
  mono?: boolean;
  highlight?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <span className="shrink-0 text-xs text-muted-foreground">{label}</span>
      <span
        className={`text-right text-sm ${mono ? "font-mono text-xs" : ""} ${highlight ? "font-semibold" : "font-medium"}`}
      >
        {value}
      </span>
    </div>
  );
}

function TaxHintsInline({ hints }: { hints: NonNullable<BookingDetail["tax_hints"]> }) {
  const configs: Record<string, { icon: React.ReactNode; class: string; label: string }> = {
    full: {
      icon: <ShieldCheckIcon className="size-3" />,
      class: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
      label: "Voll absetzbar",
    },
    partial: {
      icon: <AlertTriangleIcon className="size-3" />,
      class: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
      label: `${hints.deductible_percent ?? "Teilw."}% absetzbar`,
    },
    none: {
      icon: <CircleSlashIcon className="size-3" />,
      class: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300",
      label: "Nicht absetzbar",
    },
  };
  const cfg = configs[hints.deductibility] ?? configs.none;

  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <Badge className={cfg.class}>
        {cfg.icon}
        {cfg.label}
      </Badge>
      {hints.hint && (
        <span className="text-muted-foreground">{hints.hint}</span>
      )}
      {hints.action_required && (
        <span className="font-medium text-amber-700 dark:text-amber-400">
          ⚠ {hints.action_required}
        </span>
      )}
    </div>
  );
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
