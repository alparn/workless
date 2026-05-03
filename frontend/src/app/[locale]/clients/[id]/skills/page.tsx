"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useTranslations, useLocale } from "next-intl";
import { Link } from "@/i18n/navigation";
import {
  ArrowLeftIcon,
  BookOpenIcon,
  BrainCircuitIcon,
  CheckCircleIcon,
  EditIcon,
  EyeOffIcon,
  FilterIcon,
  RefreshCwIcon,
  SaveIcon,
  SearchIcon,
  ShieldCheckIcon,
  SparklesIcon,
  GlobeIcon,
  TagIcon,
  TrendingUpIcon,
  XIcon,
  Loader2Icon,
  ToggleLeftIcon,
  ToggleRightIcon,
} from "lucide-react";

import { api } from "@/lib/api-client";
import { showToast } from "@/lib/use-toast";
import type { Client } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface Skill {
  id: string;
  client_id: string;
  skill_key: string;
  category: string;
  title: string;
  content: string;
  source: string;
  source_entity_id: string | null;
  confidence: string;
  usage_count: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

const CATEGORY_STYLE: Record<string, { color: string; icon: typeof TagIcon }> = {
  vendor_pattern: { color: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300", icon: TagIcon },
  account_rule: { color: "bg-purple-100 text-purple-700 dark:bg-purple-950 dark:text-purple-300", icon: BookOpenIcon },
  tax_rule: { color: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300", icon: ShieldCheckIcon },
  industry_pattern: { color: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300", icon: SparklesIcon },
  correction_pattern: { color: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300", icon: EditIcon },
  custom: { color: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300", icon: BrainCircuitIcon },
};

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color = pct >= 70 ? "bg-green-500" : pct >= 40 ? "bg-amber-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 rounded-full bg-muted">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs tabular-nums text-muted-foreground">{pct}%</span>
    </div>
  );
}

export default function SkillsPage() {
  const t = useTranslations("skills");
  const common = useTranslations("common");
  const locale = useLocale();
  const params = useParams<{ id: string }>();
  const [client, setClient] = useState<Client | null>(null);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [showInactive, setShowInactive] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState({ title: "", content: "", category: "" });
  const [saving, setSaving] = useState(false);

  const CATEGORY_CONFIG: Record<string, { label: string; color: string; icon: typeof TagIcon }> = {
    vendor_pattern: { label: t("categoryVendorPattern"), ...CATEGORY_STYLE.vendor_pattern },
    account_rule: { label: t("categoryAccountRule"), ...CATEGORY_STYLE.account_rule },
    tax_rule: { label: t("categoryTaxRule"), ...CATEGORY_STYLE.tax_rule },
    industry_pattern: { label: t("categoryIndustryPattern"), ...CATEGORY_STYLE.industry_pattern },
    correction_pattern: { label: t("categoryCorrectionPattern"), ...CATEGORY_STYLE.correction_pattern },
    custom: { label: t("categoryCustom"), ...CATEGORY_STYLE.custom },
  };

  const SOURCE_LABELS: Record<string, string> = {
    booking_correction: t("sourceBookingCorrection"),
    chat_instruction: t("sourceChatInstruction"),
    clarification: t("sourceClarification"),
    industry_starter: t("sourceIndustryStarter"),
    prüfer_validation: t("sourceAuditorValidation"),
    prüfer_ocr_analysis: t("sourceAuditorOcr"),
    auto_detected: t("sourceAutoDetected"),
  };

  function formatDate(dateStr: string): string {
    return new Date(dateStr).toLocaleDateString(locale, {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    });
  }

  const loadData = useCallback(async () => {
    try {
      const [c, s] = await Promise.all([
        api.get<Client>(`/api/v1/clients/${params.id}`),
        api.get<Skill[]>(`/api/v1/skills`, {
          client_id: params.id,
          active_only: showInactive ? "false" : "true",
        }),
      ]);
      setClient(c);
      setSkills(s);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, [params.id, showInactive]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleToggleActive = async (skill: Skill) => {
    const newActive = !skill.is_active;
    setSkills((prev) =>
      prev.map((s) => (s.id === skill.id ? { ...s, is_active: newActive } : s)),
    );
    try {
      await api.patch(`/api/v1/skills/${skill.id}`, { is_active: newActive });
      showToast(newActive ? t("skillActivated") : t("skillDeactivated"), "success");
    } catch {
      setSkills((prev) =>
        prev.map((s) => (s.id === skill.id ? { ...s, is_active: !newActive } : s)),
      );
      showToast(t("updateError"), "error");
    }
  };

  const handleEdit = (skill: Skill) => {
    setEditingId(skill.id);
    setEditForm({ title: skill.title, content: skill.content, category: skill.category });
  };

  const handleCancelEdit = () => {
    setEditingId(null);
  };

  const handleSaveEdit = async (skillId: string) => {
    setSaving(true);
    try {
      await api.patch(`/api/v1/skills/${skillId}`, editForm);
      setSkills((prev) =>
        prev.map((s) =>
          s.id === skillId ? { ...s, ...editForm } : s,
        ),
      );
      setEditingId(null);
      showToast(t("skillSaved"), "success");
    } catch {
      showToast(common("saveFailed"), "error");
    } finally {
      setSaving(false);
    }
  };

  const filtered = skills.filter((s) => {
    if (categoryFilter !== "all" && s.category !== categoryFilter) return false;
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      s.title.toLowerCase().includes(q) ||
      s.content.toLowerCase().includes(q) ||
      s.skill_key.toLowerCase().includes(q)
    );
  });

  const categories = [...new Set(skills.map((s) => s.category))];
  const activeCount = skills.filter((s) => s.is_active).length;
  const totalUsage = skills.reduce((sum, s) => sum + s.usage_count, 0);

  if (loading) {
    return (
      <main className="mx-auto max-w-6xl px-6 py-10 lg:px-8">
        <Skeleton className="h-8 w-64" />
        <div className="mt-6 space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-32 rounded-lg" />
          ))}
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-6xl px-6 py-10 lg:px-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link
            href={`/clients/${params.id}`}
            className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-accent"
          >
            <ArrowLeftIcon className="size-5" />
          </Link>
          <div>
            <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
              <BrainCircuitIcon className="size-6 text-purple-600" />
              {t("title")}
            </h1>
            <p className="text-sm text-muted-foreground">
              {client?.company_name} — {t("subtitle")}
            </p>
          </div>
        </div>
        <Button variant="ghost" size="sm" onClick={loadData}>
          <RefreshCwIcon className="size-4" />
        </Button>
      </div>

      {/* Localization hint */}
      <Card className="mt-6 border-blue-200 bg-blue-50/50 dark:border-blue-900 dark:bg-blue-950/20">
        <CardContent className="flex items-center gap-4 py-4">
          <GlobeIcon className="size-5 shrink-0 text-blue-600" />
          <div className="flex-1 min-w-0">
            <p className="text-sm text-blue-900 dark:text-blue-200">
              {t("localizationHint")}
            </p>
          </div>
          <a
            href="https://github.com/your-repo/workless/blob/main/doc/tax-localization-guide.md"
            target="_blank"
            rel="noopener noreferrer"
            className="shrink-0 text-xs font-medium text-blue-700 hover:text-blue-900 dark:text-blue-300 dark:hover:text-blue-100"
          >
            {t("localizationGuide")}
          </a>
        </CardContent>
      </Card>

      {/* Stats */}
      <div className="mt-4 grid grid-cols-4 gap-4">
        <Card>
          <CardContent className="py-4">
            <p className="text-2xl font-bold">{skills.length}</p>
            <p className="text-xs text-muted-foreground">{t("totalRules")}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-4">
            <p className="text-2xl font-bold text-green-600">{activeCount}</p>
            <p className="text-xs text-muted-foreground">{t("active")}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-4">
            <p className="text-2xl font-bold">{totalUsage}</p>
            <p className="text-xs text-muted-foreground">{t("totalUsage")}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="py-4">
            <p className="text-2xl font-bold">{categories.length}</p>
            <p className="text-xs text-muted-foreground">{t("categories")}</p>
          </CardContent>
        </Card>
      </div>

      {/* Filters */}
      <div className="mt-6 flex items-center gap-3">
        <div className="relative flex-1">
          <SearchIcon className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t("searchPlaceholder")}
            className="pl-8"
          />
        </div>
        <Select
          value={categoryFilter}
          onValueChange={(v) => v && setCategoryFilter(v)}
        >
          <SelectTrigger className="w-48">
            <FilterIcon className="mr-1.5 size-3.5" />
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              <SelectItem value="all">{t("allCategories")}</SelectItem>
              {Object.entries(CATEGORY_CONFIG).map(([key, cfg]) => (
                <SelectItem key={key} value={key}>{cfg.label}</SelectItem>
              ))}
            </SelectGroup>
          </SelectContent>
        </Select>
        <Button
          variant={showInactive ? "default" : "outline"}
          size="sm"
          onClick={() => setShowInactive(!showInactive)}
          className="gap-1.5"
        >
          <EyeOffIcon className="size-3.5" />
          {showInactive ? t("inactiveShown") : t("showInactive")}
        </Button>
      </div>

      {/* Skill List */}
      <div className="mt-5 space-y-3">
        {filtered.length === 0 ? (
          <Card>
            <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
              <BrainCircuitIcon className="size-10 text-muted-foreground/50" />
              <p className="text-muted-foreground">
                {search || categoryFilter !== "all"
                  ? t("noRulesFiltered")
                  : t("noRulesDescription")}
              </p>
            </CardContent>
          </Card>
        ) : (
          filtered.map((skill) => {
            const cat = CATEGORY_CONFIG[skill.category] ?? CATEGORY_CONFIG.custom;
            const CatIcon = cat.icon;
            const isEditing = editingId === skill.id;
            const confidence = parseFloat(skill.confidence);

            return (
              <Card
                key={skill.id}
                className={`transition-colors ${!skill.is_active ? "opacity-50" : ""}`}
              >
                <CardContent className="py-4">
                  {isEditing ? (
                    <div className="space-y-3">
                      <div className="flex flex-col gap-2">
                        <Label>{t("fieldTitle")}</Label>
                        <Input
                          value={editForm.title}
                          onChange={(e) =>
                            setEditForm((p) => ({ ...p, title: e.target.value }))
                          }
                        />
                      </div>
                      <div className="flex flex-col gap-2">
                        <Label>{t("fieldContent")}</Label>
                        <Textarea
                          value={editForm.content}
                          onChange={(e) =>
                            setEditForm((p) => ({ ...p, content: e.target.value }))
                          }
                          rows={4}
                        />
                      </div>
                      <div className="flex flex-col gap-2">
                        <Label>{t("fieldCategory")}</Label>
                        <Select
                          value={editForm.category}
                          onValueChange={(v) =>
                            v && setEditForm((p) => ({ ...p, category: v }))
                          }
                        >
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {Object.entries(CATEGORY_CONFIG).map(([key, cfg]) => (
                              <SelectItem key={key} value={key}>
                                {cfg.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <div className="flex justify-end gap-2">
                        <Button variant="outline" size="sm" onClick={handleCancelEdit}>
                          <XIcon className="mr-1 size-3.5" />
                          {common("cancel")}
                        </Button>
                        <Button size="sm" onClick={() => handleSaveEdit(skill.id)} disabled={saving}>
                          {saving ? (
                            <Loader2Icon className="mr-1 size-3.5 animate-spin" />
                          ) : (
                            <SaveIcon className="mr-1 size-3.5" />
                          )}
                          {common("save")}
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex gap-4">
                      <div className={`mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg ${cat.color}`}>
                        <CatIcon className="size-4" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-start justify-between gap-2">
                          <div>
                            <h3 className="font-medium text-sm">{skill.title}</h3>
                            <div className="mt-1 flex flex-wrap items-center gap-2">
                              <Badge variant="outline" className={`text-[10px] ${cat.color}`}>
                                {cat.label}
                              </Badge>
                              <span className="text-[10px] text-muted-foreground">
                                {SOURCE_LABELS[skill.source] ?? skill.source}
                              </span>
                              <span className="text-[10px] text-muted-foreground">
                                {formatDate(skill.created_at)}
                              </span>
                            </div>
                          </div>
                          <div className="flex items-center gap-1.5 shrink-0">
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-7 w-7 p-0"
                              onClick={() => handleEdit(skill)}
                            >
                              <EditIcon className="size-3.5" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-7 w-7 p-0"
                              onClick={() => handleToggleActive(skill)}
                            >
                              {skill.is_active ? (
                                <ToggleRightIcon className="size-4 text-green-600" />
                              ) : (
                                <ToggleLeftIcon className="size-4 text-muted-foreground" />
                              )}
                            </Button>
                          </div>
                        </div>

                        <p className="mt-2 text-xs text-muted-foreground whitespace-pre-line leading-relaxed">
                          {skill.content}
                        </p>

                        <div className="mt-2.5 flex items-center gap-5 text-[10px] text-muted-foreground">
                          <div className="flex items-center gap-1.5">
                            <TrendingUpIcon className="size-3" />
                            {t("confidence")}
                            <ConfidenceBar value={confidence} />
                          </div>
                          <div className="flex items-center gap-1">
                            <CheckCircleIcon className="size-3" />
                            {t("usedCount", { count: skill.usage_count })}
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })
        )}
      </div>
    </main>
  );
}
