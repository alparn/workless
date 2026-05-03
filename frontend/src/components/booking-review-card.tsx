"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useLocale } from "next-intl";
import {
  CheckIcon,
  PencilIcon,
  XIcon,
  FileTextIcon,
  SparklesIcon,
  ArrowRightIcon,
  LandmarkIcon,
  ShieldCheckIcon,
  AlertTriangleIcon,
  CircleSlashIcon,
  InfoIcon,
} from "lucide-react";

import type { BankAccount, BookingWithDocument, BookingUpdate, TaxHints } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Separator } from "@/components/ui/separator";
import { BookingEditForm } from "@/components/booking-edit-form";

interface BookingReviewCardProps {
  booking: BookingWithDocument;
  bankAccounts?: BankAccount[];
  selected: boolean;
  onToggleSelect: (id: string) => void;
  onApprove: (id: string) => Promise<void>;
  onReject: (id: string) => Promise<void>;
  onUpdate: (id: string, data: BookingUpdate) => Promise<void>;
}

export function BookingReviewCard({
  booking,
  bankAccounts,
  selected,
  onToggleSelect,
  onApprove,
  onReject,
  onUpdate,
}: BookingReviewCardProps) {
  const t = useTranslations("components");
  const locale = useLocale();
  const [editing, setEditing] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  const extraction = booking.document_extraction ?? {};
  const confidence = booking.ai_confidence ? parseFloat(booking.ai_confidence) : null;
  const matchedBank = bankAccounts?.find(
    (ba) => ba.account_number === booking.contra_account || ba.account_number === booking.account,
  );

  const handleApprove = async () => {
    setActionLoading("approve");
    try {
      await onApprove(booking.id);
    } finally {
      setActionLoading(null);
    }
  };

  const handleReject = async () => {
    setActionLoading("reject");
    try {
      await onReject(booking.id);
    } finally {
      setActionLoading(null);
    }
  };

  const handleUpdate = async (id: string, data: BookingUpdate) => {
    await onUpdate(id, data);
    setEditing(false);
  };

  const localeString = locale === "de" ? "de-DE" : "en-US";

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start gap-3">
          <Checkbox
            checked={selected}
            onCheckedChange={() => onToggleSelect(booking.id)}
            className="mt-0.5"
          />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <FileTextIcon className="size-4 shrink-0 text-muted-foreground" />
              <CardTitle className="truncate">
                {booking.document_filename ?? t("unknownDocument")}
              </CardTitle>
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              {t("documentDate")} {new Date(booking.document_date).toLocaleDateString(localeString)}
              {" · "}
              {t("created")} {new Date(booking.created_at).toLocaleDateString(localeString, {
                hour: "2-digit",
                minute: "2-digit",
              })}
            </p>
          </div>
          {confidence !== null && (
            <Badge variant={confidence >= 0.85 ? "default" : "secondary"}>
              <SparklesIcon className="size-3" />
              {Math.round(confidence * 100)}%
            </Badge>
          )}
        </div>
      </CardHeader>

      <CardContent>
        {/* Extracted data summary */}
        {Object.keys(extraction).length > 0 && (
          <>
            <div className="grid grid-cols-2 gap-x-8 gap-y-1.5 text-sm">
              {extraction.vendor_name != null && (
                <InfoPair
                  label={extraction.document_type === "outgoing_invoice" ? t("invoicer") : t("vendor")}
                  value={String(extraction.vendor_name)}
                />
              )}
              {extraction.document_type === "outgoing_invoice" && extraction.recipient_name != null && (
                <InfoPair label={t("customer")} value={String(extraction.recipient_name)} />
              )}
              {extraction.invoice_number != null && (
                <InfoPair label={t("invoiceNumber")} value={String(extraction.invoice_number)} />
              )}
              {extraction.total_gross != null && (
                <InfoPair label={t("gross")} value={formatCurrency(extraction.total_gross, localeString)} />
              )}
              {extraction.total_net != null && (
                <InfoPair label={t("net")} value={formatCurrency(extraction.total_net, localeString)} />
              )}
              {extraction.vat_amount != null && (
                <InfoPair label={t("vat")} value={formatCurrency(extraction.vat_amount, localeString)} />
              )}
              {extraction.vat_rate != null && (
                <InfoPair label={t("vatRate")} value={`${String(extraction.vat_rate)}%`} />
              )}
            </div>
            <Separator className="my-4" />
          </>
        )}

        {/* Booking suggestion or edit form */}
        {editing ? (
          <BookingEditForm
            booking={booking}
            onSave={handleUpdate}
            onCancel={() => setEditing(false)}
          />
        ) : (
          <div className="flex flex-col gap-3">
            <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
              {t("aiBookingSuggestion")}
            </p>
            <div className="flex items-center gap-2 text-sm">
              <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">
                {booking.account}
              </code>
              <ArrowRightIcon className="size-3 text-muted-foreground" />
              <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">
                {booking.contra_account}
              </code>
              {booking.bu_key && (
                <Badge variant="outline" className="text-xs">
                  BU {booking.bu_key}
                </Badge>
              )}
              <span className="ml-auto font-medium tabular-nums">
                {formatCurrency(booking.amount, localeString)} {booking.debit_credit}
              </span>
            </div>
            {matchedBank && (
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <LandmarkIcon className="size-3 shrink-0" />
                <span>
                  {matchedBank.bank_name}
                  {matchedBank.label && ` (${matchedBank.label})`}
                  {matchedBank.iban && (
                    <span className="ml-1.5 font-mono">
                      {matchedBank.iban}
                    </span>
                  )}
                </span>
              </div>
            )}
            {booking.booking_text && (
              <p className="text-sm text-muted-foreground">{booking.booking_text}</p>
            )}
            {booking.ai_reasoning && (
              <p className="rounded-lg bg-muted/60 p-3 text-xs leading-relaxed text-muted-foreground">
                {booking.ai_reasoning}
              </p>
            )}
            {booking.tax_hints && (
              <TaxHintsBadge hints={booking.tax_hints} />
            )}
          </div>
        )}
      </CardContent>

      {!editing && (
        <CardFooter>
          <div className="flex w-full items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setEditing(true)}
              disabled={actionLoading !== null}
            >
              <PencilIcon className="size-3.5" />
              {t("edit")}
            </Button>
            <div className="flex-1" />
            <Button
              variant="destructive"
              size="sm"
              onClick={handleReject}
              disabled={actionLoading !== null}
            >
              <XIcon className="size-3.5" />
              {actionLoading === "reject" ? "…" : t("reject")}
            </Button>
            <Button
              size="sm"
              onClick={handleApprove}
              disabled={actionLoading !== null}
            >
              <CheckIcon className="size-3.5" />
              {actionLoading === "approve" ? "…" : t("approve")}
            </Button>
          </div>
        </CardFooter>
      )}
    </Card>
  );
}

function InfoPair({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  );
}

function TaxHintsBadge({ hints }: { hints: TaxHints }) {
  const t = useTranslations("components");
  const config = getTaxBadgeConfig(t, hints.deductibility, hints.deductible_percent);

  return (
    <div className="flex flex-col gap-1.5 rounded-lg border p-3" style={{ borderColor: config.borderColor }}>
      <div className="flex items-center gap-2">
        <Badge className={config.badgeClass}>
          {config.icon}
          {config.label}
        </Badge>
        {hints.legal_basis && (
          <span className="flex items-center gap-1 text-xs text-muted-foreground">
            <InfoIcon className="size-3" />
            {hints.legal_basis}
          </span>
        )}
      </div>
      {hints.hint && (
        <p className="text-xs text-muted-foreground">{hints.hint}</p>
      )}
      {hints.action_required && (
        <p className="flex items-center gap-1.5 text-xs font-medium text-amber-700 dark:text-amber-400">
          <AlertTriangleIcon className="size-3 shrink-0" />
          {hints.action_required}
        </p>
      )}
    </div>
  );
}

function getTaxBadgeConfig(
  t: ReturnType<typeof useTranslations>,
  deductibility: TaxHints["deductibility"],
  percent?: number,
) {
  switch (deductibility) {
    case "full":
      return {
        label: t("fullyDeductible"),
        icon: <ShieldCheckIcon className="size-3" />,
        badgeClass: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300 hover:bg-emerald-100",
        borderColor: "var(--color-emerald-200)",
      };
    case "partial":
      return {
        label: percent != null
          ? t("partiallyDeductible", { percent })
          : t("partiallyShort"),
        icon: <AlertTriangleIcon className="size-3" />,
        badgeClass: "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300 hover:bg-amber-100",
        borderColor: "var(--color-amber-200)",
      };
    case "none":
      return {
        label: t("notDeductible"),
        icon: <CircleSlashIcon className="size-3" />,
        badgeClass: "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300 hover:bg-red-100",
        borderColor: "var(--color-red-200)",
      };
    default: {
      const _exhaustive: never = deductibility;
      return _exhaustive;
    }
  }
}

function formatCurrency(value: unknown, localeString: string): string {
  const num = typeof value === "string" ? parseFloat(value) : Number(value);
  if (Number.isNaN(num)) return String(value);
  return new Intl.NumberFormat(localeString, {
    style: "currency",
    currency: "EUR",
  }).format(num);
}
