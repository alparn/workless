"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeftIcon,
  CheckCircleIcon,
  CheckIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  DownloadIcon,
  FileTextIcon,
  HelpCircleIcon,
  MailIcon,
  MessageSquareIcon,
  RefreshCwIcon,
  RotateCcwIcon,
  SearchIcon,
  SendIcon,
  AlertCircleIcon,
} from "lucide-react";

import { api, ApiError } from "@/lib/api-client";
import { showToast } from "@/lib/use-toast";
import type {
  ClarificationListResponse,
  ClarificationItem,
  DocumentClarificationGroup,
} from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";

const CATEGORY_LABELS: Record<string, string> = {
  cash_deposit: "Bareinzahlung",
  cash_withdrawal: "Barauszahlung",
  owner_transfer: "Gesellschafter-Transfer",
  vague_reference: "Unklarer Verwendungszweck",
  unknown_private_person: "Unbekannte Privatperson",
  loan_indicator: "Mögliches Darlehen",
  large_unidentified: "Ungeklärter Betrag",
};

const CATEGORY_COLORS: Record<string, string> = {
  cash_deposit: "bg-amber-100 text-amber-800 border-amber-200",
  cash_withdrawal: "bg-orange-100 text-orange-800 border-orange-200",
  owner_transfer: "bg-purple-100 text-purple-800 border-purple-200",
  vague_reference: "bg-sky-100 text-sky-800 border-sky-200",
  unknown_private_person: "bg-rose-100 text-rose-800 border-rose-200",
  loan_indicator: "bg-violet-100 text-violet-800 border-violet-200",
  large_unidentified: "bg-red-100 text-red-800 border-red-200",
};

function formatAmount(amount: string, debitCredit: string): string {
  const num = parseFloat(amount);
  const formatted = new Intl.NumberFormat("de-DE", {
    style: "currency",
    currency: "EUR",
  }).format(num);
  return debitCredit === "H" ? `+${formatted}` : `-${formatted}`;
}

function formatDate(isoDate: string): string {
  return new Date(isoDate).toLocaleDateString("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

type ViewFilter = "all" | "open" | "resolved";

export default function ClarificationsPage() {
  const params = useParams<{ id: string }>();
  const [data, setData] = useState<ClarificationListResponse | null>(null);
  const [emailBody, setEmailBody] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [filter, setFilter] = useState<ViewFilter>("open");
  const [search, setSearch] = useState("");
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const result = await api.get<ClarificationListResponse>(
        `/api/v1/clients/${params.id}/clarifications`,
      );
      setData(result);
      setEmailBody(result.email_draft.body_text);
      setError(null);

      const openGroupIds = result.groups
        .filter((g) => g.open_count > 0)
        .map((g) => g.document_id);
      setExpandedGroups(new Set(openGroupIds));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Laden fehlgeschlagen");
    } finally {
      setLoading(false);
    }
  }, [params.id]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleCopy = async () => {
    if (!data) return;
    await navigator.clipboard.writeText(emailBody);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownloadPdf = async () => {
    if (!data) return;
    setPdfLoading(true);
    try {
      const filename = `Rueckfragen_${data.company_name.replace(/\s+/g, "_")}.pdf`;
      await api.downloadBlob(
        `/api/v1/clients/${params.id}/clarifications/pdf`,
        filename,
      );
      showToast("PDF heruntergeladen", "success");
    } catch (err) {
      showToast(
        err instanceof ApiError ? err.detail : "Download fehlgeschlagen",
        "error",
      );
    } finally {
      setPdfLoading(false);
    }
  };

  const toggleGroup = (docId: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(docId)) {
        next.delete(docId);
      } else {
        next.add(docId);
      }
      return next;
    });
  };

  const updateItem = (updated: ClarificationItem) => {
    if (!data) return;
    setData({
      ...data,
      groups: data.groups.map((g) => {
        const hasItem = g.items.some(
          (i) => i.booking_id === updated.booking_id,
        );
        if (!hasItem) return g;

        const newItems = g.items.map((i) =>
          i.booking_id === updated.booking_id ? updated : i,
        );
        return {
          ...g,
          items: newItems,
          open_count: newItems.filter((i) => !i.clarification_resolved).length,
          resolved_count: newItems.filter((i) => i.clarification_resolved)
            .length,
        };
      }),
      open_count: data.groups.reduce(
        (acc, g) =>
          acc +
          g.items.filter((i) =>
            i.booking_id === updated.booking_id
              ? !updated.clarification_resolved
              : !i.clarification_resolved,
          ).length,
        0,
      ),
      resolved_count: data.groups.reduce(
        (acc, g) =>
          acc +
          g.items.filter((i) =>
            i.booking_id === updated.booking_id
              ? updated.clarification_resolved
              : i.clarification_resolved,
          ).length,
        0,
      ),
    });
  };

  const cq = search.toLowerCase();
  const filteredGroups = data?.groups
    .map((g) => ({
      ...g,
      items: g.items.filter((item) => {
        if (filter === "open" && item.clarification_resolved) return false;
        if (filter === "resolved" && !item.clarification_resolved) return false;
        if (!cq) return true;
        return [
          item.clarification_question,
          item.clarification_answer,
          item.clarification_category,
          CATEGORY_LABELS[item.clarification_category],
          item.booking_text,
          item.amount,
          item.debit_credit,
          formatDate(item.document_date),
          g.document_filename,
        ]
          .filter(Boolean)
          .some((val) => val!.toLowerCase().includes(cq));
      }),
    }))
    .filter((g) => g.items.length > 0);

  if (loading) return <PageSkeleton />;

  if (error || !data) {
    return (
      <main className="mx-auto max-w-4xl px-6 py-10">
        <div className="flex flex-col items-center gap-4 rounded-lg border border-destructive/20 bg-destructive/5 p-10 text-center">
          <AlertCircleIcon className="size-8 text-destructive" />
          <div>
            <p className="font-medium text-destructive">Fehler beim Laden</p>
            <p className="mt-1 text-sm text-destructive/80">
              {error ?? "Daten nicht verfügbar"}
            </p>
          </div>
          <Button
            variant="outline"
            render={<Link href={`/clients/${params.id}`} />}
          >
            <ArrowLeftIcon data-icon="inline-start" />
            Zurück
          </Button>
        </div>
      </main>
    );
  }

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
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight">Rückfragen</h1>
            {data.open_count > 0 && (
              <Badge variant="destructive">{data.open_count} offen</Badge>
            )}
            {data.resolved_count > 0 && (
              <Badge variant="outline" className="border-emerald-200 bg-emerald-50 text-emerald-700">
                {data.resolved_count} geklärt
              </Badge>
            )}
          </div>
          <p className="text-sm text-muted-foreground">{data.company_name}</p>
        </div>
        <Button variant="outline" size="sm" onClick={loadData}>
          <RefreshCwIcon className="size-3.5" />
          Aktualisieren
        </Button>
      </div>

      {data.total_count === 0 ? (
        <div className="mt-16 flex flex-col items-center gap-4 text-center">
          <div className="flex size-14 items-center justify-center rounded-full bg-muted">
            <HelpCircleIcon className="size-6 text-muted-foreground" />
          </div>
          <div>
            <p className="font-medium">Keine offenen Rückfragen</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Alle Kontoauszugspositionen konnten eindeutig zugeordnet werden.
            </p>
          </div>
          <Button render={<Link href={`/clients/${params.id}/upload`} />}>
            Neue Belege hochladen
          </Button>
        </div>
      ) : (
        <div className="mt-6 flex flex-col gap-6">
          {/* Filter tabs */}
          <div className="flex gap-1 rounded-lg bg-muted p-1">
            {(
              [
                { key: "open", label: "Offen", count: data.open_count },
                {
                  key: "resolved",
                  label: "Geklärt",
                  count: data.resolved_count,
                },
                { key: "all", label: "Alle", count: data.total_count },
              ] as const
            ).map(({ key, label, count }) => (
              <button
                key={key}
                onClick={() => setFilter(key)}
                className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                  filter === key
                    ? "bg-background text-foreground shadow-sm"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {label} ({count})
              </button>
            ))}
          </div>

          {/* Search */}
          <div className="relative">
            <SearchIcon className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Rückfragen durchsuchen…"
              className="pl-8"
            />
          </div>

          {/* Grouped entries */}
          <div className="flex flex-col gap-4">
            {filteredGroups?.map((group) => (
              <DocumentGroup
                key={group.document_id}
                group={group}
                clientId={params.id}
                isExpanded={expandedGroups.has(group.document_id)}
                onToggle={() => toggleGroup(group.document_id)}
                onItemUpdate={updateItem}
              />
            ))}
            {filteredGroups?.length === 0 && (
              <div className="flex flex-col items-center gap-3 py-12 text-center">
                <CheckCircleIcon className="size-8 text-emerald-500" />
                <p className="text-sm text-muted-foreground">
                  {filter === "open"
                    ? "Alle Rückfragen wurden beantwortet."
                    : "Keine Rückfragen in dieser Ansicht."}
                </p>
              </div>
            )}
          </div>

          <Separator />

          {/* Email draft + PDF (only if open questions exist) */}
          {data.open_count > 0 && (
            <Card>
              <CardHeader>
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <CardTitle className="flex items-center gap-2">
                      <MailIcon className="size-4" />
                      Email-Entwurf
                    </CardTitle>
                    <CardDescription className="mt-1">
                      Nur offene Rückfragen — bereits geklärte werden
                      ausgeblendet.
                      <br />
                      Betreff:{" "}
                      <span className="font-medium text-foreground">
                        {data.email_draft.subject}
                      </span>
                    </CardDescription>
                  </div>
                  <div className="flex shrink-0 gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleCopy}
                      disabled={copied}
                    >
                      {copied ? (
                        <>
                          <CheckIcon className="size-3.5 text-emerald-600" />
                          Kopiert
                        </>
                      ) : (
                        <>
                          <MailIcon className="size-3.5" />
                          Text kopieren
                        </>
                      )}
                    </Button>
                    <Button
                      size="sm"
                      onClick={handleDownloadPdf}
                      disabled={pdfLoading}
                    >
                      <DownloadIcon className="size-3.5" />
                      {pdfLoading ? "Wird erstellt…" : "PDF herunterladen"}
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <Textarea
                  value={emailBody}
                  onChange={(e) => setEmailBody(e.target.value)}
                  className="min-h-[360px] font-mono text-sm"
                  spellCheck={false}
                />
                <p className="mt-2 text-xs text-muted-foreground">
                  Der Text kann vor dem Versenden bearbeitet werden.
                </p>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </main>
  );
}

function DocumentGroup({
  group,
  clientId,
  isExpanded,
  onToggle,
  onItemUpdate,
}: {
  group: DocumentClarificationGroup;
  clientId: string;
  isExpanded: boolean;
  onToggle: () => void;
  onItemUpdate: (item: ClarificationItem) => void;
}) {
  return (
    <Card>
      <button
        onClick={onToggle}
        className="flex w-full items-center gap-3 px-6 py-4 text-left hover:bg-muted/50 transition-colors"
      >
        {isExpanded ? (
          <ChevronDownIcon className="size-4 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRightIcon className="size-4 shrink-0 text-muted-foreground" />
        )}
        <FileTextIcon className="size-4 shrink-0 text-muted-foreground" />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium truncate">
            {group.document_filename}
          </p>
          <p className="text-xs text-muted-foreground">
            Hochgeladen: {formatDate(group.uploaded_at)}
          </p>
        </div>
        <div className="flex shrink-0 gap-2">
          {group.open_count > 0 && (
            <Badge variant="destructive" className="text-xs">
              {group.open_count} offen
            </Badge>
          )}
          {group.resolved_count > 0 && (
            <Badge
              variant="outline"
              className="border-emerald-200 bg-emerald-50 text-emerald-700 text-xs"
            >
              {group.resolved_count} geklärt
            </Badge>
          )}
        </div>
      </button>

      {isExpanded && (
        <CardContent className="border-t p-0">
          <div className="divide-y">
            {group.items.map((item, idx) => (
              <ClarificationRow
                key={item.booking_id}
                item={item}
                index={idx + 1}
                clientId={clientId}
                onUpdate={onItemUpdate}
              />
            ))}
          </div>
        </CardContent>
      )}
    </Card>
  );
}

function ClarificationRow({
  item,
  index,
  clientId,
  onUpdate,
}: {
  item: ClarificationItem;
  index: number;
  clientId: string;
  onUpdate: (item: ClarificationItem) => void;
}) {
  const [answerText, setAnswerText] = useState("");
  const [showAnswerInput, setShowAnswerInput] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const categoryColor =
    CATEGORY_COLORS[item.clarification_category] ??
    "bg-slate-100 text-slate-700 border-slate-200";
  const categoryLabel =
    CATEGORY_LABELS[item.clarification_category] ?? item.clarification_category;
  const amountColor =
    item.debit_credit === "H" ? "text-emerald-600" : "text-foreground";

  const handleResolve = async () => {
    if (!answerText.trim()) return;
    setSubmitting(true);
    try {
      const updated = await api.post<ClarificationItem>(
        `/api/v1/clients/${clientId}/clarifications/${item.booking_id}/resolve`,
        { answer: answerText.trim() },
      );
      onUpdate(updated);
      setShowAnswerInput(false);
      setAnswerText("");
      showToast("Rückfrage beantwortet", "success");
    } catch (err) {
      showToast(
        err instanceof ApiError ? err.detail : "Fehler beim Speichern",
        "error",
      );
    } finally {
      setSubmitting(false);
    }
  };

  const handleReopen = async () => {
    setSubmitting(true);
    try {
      const updated = await api.post<ClarificationItem>(
        `/api/v1/clients/${clientId}/clarifications/${item.booking_id}/reopen`,
      );
      onUpdate(updated);
      showToast("Rückfrage wieder geöffnet", "success");
    } catch (err) {
      showToast(
        err instanceof ApiError ? err.detail : "Fehler beim Öffnen",
        "error",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className={`flex gap-4 px-6 py-4 ${
        item.clarification_resolved ? "bg-emerald-50/50" : ""
      }`}
    >
      <div
        className={`flex size-6 shrink-0 items-center justify-center rounded-full mt-0.5 ${
          item.clarification_resolved
            ? "bg-emerald-100 text-emerald-600"
            : "bg-muted text-muted-foreground"
        }`}
      >
        {item.clarification_resolved ? (
          <CheckIcon className="size-3.5" />
        ) : (
          <span className="text-xs font-medium">{index}</span>
        )}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span
            className={`text-sm font-semibold tabular-nums ${amountColor}`}
          >
            {formatAmount(item.amount, item.debit_credit)}
          </span>
          <span className="text-sm text-muted-foreground">
            {formatDate(item.document_date)}
          </span>
          <span
            className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${categoryColor}`}
          >
            {categoryLabel}
          </span>
          {item.clarification_resolved && (
            <span className="inline-flex items-center gap-1 rounded-md border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700">
              <CheckCircleIcon className="size-3" />
              Geklärt
            </span>
          )}
          {item.booking_text && (
            <span className="text-xs text-muted-foreground">
              {item.booking_text}
            </span>
          )}
        </div>

        {/* Question */}
        <div className="mt-2 flex gap-2">
          <HelpCircleIcon className="mt-0.5 size-4 shrink-0 text-amber-500" />
          <p className="text-sm">{item.clarification_question}</p>
        </div>

        {/* Resolved answer display */}
        {item.clarification_resolved && item.clarification_answer && (
          <div className="mt-2 flex gap-2 rounded-md bg-emerald-50 p-3">
            <MessageSquareIcon className="mt-0.5 size-4 shrink-0 text-emerald-600" />
            <div className="flex-1">
              <p className="text-xs font-medium text-emerald-700">Antwort</p>
              <p className="mt-0.5 text-sm text-emerald-900">
                {item.clarification_answer}
              </p>
              {item.clarification_resolved_at && (
                <p className="mt-1 text-xs text-emerald-600">
                  Beantwortet am {formatDate(item.clarification_resolved_at)}
                </p>
              )}
            </div>
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={handleReopen}
              disabled={submitting}
              className="shrink-0 text-muted-foreground hover:text-foreground"
              title="Wieder öffnen"
            >
              <RotateCcwIcon className="size-3.5" />
            </Button>
          </div>
        )}

        {/* Answer input for open questions */}
        {!item.clarification_resolved && (
          <div className="mt-3">
            {showAnswerInput ? (
              <div className="flex flex-col gap-2">
                <Textarea
                  value={answerText}
                  onChange={(e) => setAnswerText(e.target.value)}
                  placeholder="Antwort eingeben…"
                  className="min-h-[80px] text-sm"
                  autoFocus
                />
                <div className="flex gap-2 justify-end">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setShowAnswerInput(false);
                      setAnswerText("");
                    }}
                  >
                    Abbrechen
                  </Button>
                  <Button
                    size="sm"
                    onClick={handleResolve}
                    disabled={!answerText.trim() || submitting}
                  >
                    <SendIcon className="size-3.5" />
                    {submitting ? "Wird gespeichert…" : "Beantworten"}
                  </Button>
                </div>
              </div>
            ) : (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setShowAnswerInput(true)}
              >
                <MessageSquareIcon className="size-3.5" />
                Frage beantworten
              </Button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function PageSkeleton() {
  return (
    <main className="mx-auto max-w-4xl px-6 py-10">
      <div className="flex items-center gap-3">
        <Skeleton className="size-7 rounded-lg" />
        <div className="flex-1">
          <Skeleton className="h-7 w-40" />
          <Skeleton className="mt-2 h-4 w-28" />
        </div>
      </div>
      <div className="mt-6">
        <Skeleton className="h-10 rounded-lg" />
      </div>
      <div className="mt-4 flex flex-col gap-4">
        <Skeleton className="h-48 rounded-lg" />
        <Skeleton className="h-48 rounded-lg" />
      </div>
    </main>
  );
}
