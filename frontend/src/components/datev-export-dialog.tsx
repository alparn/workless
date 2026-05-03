"use client";

import { useState } from "react";
import { FileDownIcon, Loader2Icon, AlertCircleIcon } from "lucide-react";

import { api, ApiError } from "@/lib/api-client";
import type { ExportBatch, ExportPreview } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface DatevExportDialogProps {
  clientId: string;
  onExportCreated: (batch: ExportBatch) => void;
}

function formatCurrency(value: string): string {
  const num = parseFloat(value);
  if (Number.isNaN(num)) return value;
  return new Intl.NumberFormat("de-DE", {
    style: "currency",
    currency: "EUR",
  }).format(num);
}

function getDefaultDateRange(): { from: string; to: string } {
  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth();
  const from = new Date(year, month - 1, 1);
  const to = new Date(year, month, 0);
  return {
    from: from.toISOString().slice(0, 10),
    to: to.toISOString().slice(0, 10),
  };
}

export function DatevExportDialog({
  clientId,
  onExportCreated,
}: DatevExportDialogProps) {
  const defaults = getDefaultDateRange();
  const [dateFrom, setDateFrom] = useState(defaults.from);
  const [dateTo, setDateTo] = useState(defaults.to);
  const [label, setLabel] = useState("");
  const [preview, setPreview] = useState<ExportPreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [exportLoading, setExportLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handlePreview = async () => {
    setPreviewLoading(true);
    setError(null);
    setPreview(null);
    try {
      const data = await api.post<ExportPreview>("/api/v1/exports/preview", {
        client_id: clientId,
        date_from: dateFrom,
        date_to: dateTo,
      });
      setPreview(data);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Vorschau fehlgeschlagen");
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleExport = async () => {
    setExportLoading(true);
    setError(null);
    try {
      const batch = await api.post<ExportBatch>("/api/v1/exports/datev", {
        client_id: clientId,
        date_from: dateFrom,
        date_to: dateTo,
        label: label || null,
      });
      onExportCreated(batch);
      setPreview(null);

      const link = document.createElement("a");
      link.href = `${API_BASE_URL}/api/v1/exports/${batch.id}/download`;
      link.download = `EXTF_${dateFrom}_${dateTo}.csv`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Export fehlgeschlagen");
    } finally {
      setExportLoading(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>DATEV-Export erstellen</CardTitle>
        <CardDescription>
          Nur <strong>freigegebene</strong> Buchungen werden exportiert (einschließlich nach
          Freigabe per Chat korrigierter). Filter: <strong>Belegdatum</strong>, nicht
          Upload-Datum.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="date-from">Von</Label>
            <Input
              id="date-from"
              type="date"
              value={dateFrom}
              onChange={(e) => {
                setDateFrom(e.target.value);
                setPreview(null);
              }}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="date-to">Bis</Label>
            <Input
              id="date-to"
              type="date"
              value={dateTo}
              onChange={(e) => {
                setDateTo(e.target.value);
                setPreview(null);
              }}
            />
          </div>
          <div className="col-span-2 flex flex-col gap-1.5">
            <Label htmlFor="export-label">Bezeichnung (optional)</Label>
            <Input
              id="export-label"
              placeholder="z.B. Buchungsstapel April 2026"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
            />
          </div>
        </div>

        {error && (
          <div className="mt-4 flex items-center gap-2 rounded-lg border border-destructive/20 bg-destructive/5 px-3 py-2 text-sm text-destructive">
            <AlertCircleIcon className="size-4 shrink-0" />
            {error}
          </div>
        )}

        {preview && (
          <div className="mt-4 space-y-3 rounded-lg border bg-muted/30 p-4">
            <div className="grid grid-cols-1 gap-4 text-sm sm:grid-cols-3">
              <div>
                <p className="text-muted-foreground">Im Export (freigegeben)</p>
                <p className="text-lg font-semibold tabular-nums">
                  {preview.booking_count}
                </p>
              </div>
              <div>
                <p className="text-muted-foreground">Gesamtbetrag Export</p>
                <p className="text-lg font-semibold tabular-nums">
                  {formatCurrency(preview.total_amount)}
                </p>
              </div>
              <div>
                <p className="text-muted-foreground">Zeitraum (Belegdatum)</p>
                <p className="text-lg font-semibold tabular-nums">
                  {new Date(preview.date_from).toLocaleDateString("de-DE")} –{" "}
                  {new Date(preview.date_to).toLocaleDateString("de-DE")}
                </p>
              </div>
            </div>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 border-t border-border/60 pt-3 text-sm sm:grid-cols-4">
              <div>
                <dt className="text-muted-foreground">Belege mit Buchungen</dt>
                <dd className="font-medium tabular-nums">
                  {preview.documents_with_bookings_count}
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Warten auf Freigabe</dt>
                <dd className="font-medium tabular-nums">
                  {preview.pending_approval_count}
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Bereits exportiert</dt>
                <dd className="font-medium tabular-nums">
                  {preview.exported_count}
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Abgelehnt</dt>
                <dd className="font-medium tabular-nums">
                  {preview.rejected_count}
                </dd>
              </div>
            </dl>
            {preview.pending_approval_count > 0 && (
              <p className="text-sm text-muted-foreground">
                Es gibt {preview.pending_approval_count} Buchung
                {preview.pending_approval_count === 1 ? "" : "en"} mit Status
                „Vorschlag“ im Zeitraum. Diese fließen erst in den DATEV-Export ein,
                nachdem Sie sie unter Buchungen freigegeben haben.
              </p>
            )}
            {preview.documents_with_bookings_count > 0 &&
              preview.pending_approval_count === 0 &&
              preview.booking_count < preview.documents_with_bookings_count && (
                <p className="text-sm text-muted-foreground">
                  Weniger freigegebene Buchungen als Belege mit Buchungen: prüfen Sie
                  abgelehnte oder bereits exportierte Vorgänge in der Übersicht oben.
                </p>
              )}
          </div>
        )}
      </CardContent>
      <CardFooter className="gap-2">
        <Button
          variant="outline"
          onClick={handlePreview}
          disabled={previewLoading || !dateFrom || !dateTo}
        >
          {previewLoading && <Loader2Icon className="size-3.5 animate-spin" />}
          Vorschau
        </Button>
        <Button
          onClick={handleExport}
          disabled={exportLoading || !dateFrom || !dateTo}
        >
          {exportLoading ? (
            <Loader2Icon className="size-3.5 animate-spin" />
          ) : (
            <FileDownIcon className="size-3.5" />
          )}
          {exportLoading ? "Wird exportiert…" : "Export generieren"}
        </Button>
      </CardFooter>
    </Card>
  );
}
