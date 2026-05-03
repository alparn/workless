"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useTranslations, useLocale } from "next-intl";
import { Link } from "@/i18n/navigation";
import {
  ArrowLeftIcon,
  SaveIcon,
  Loader2Icon,
  AlertCircleIcon,
  SettingsIcon,
  KeyIcon,
  TrashIcon,
  CheckCircleIcon,
  XCircleIcon,
  EyeOffIcon,
  ShieldCheckIcon,
} from "lucide-react";

import { api, ApiError } from "@/lib/api-client";
import { showToast } from "@/lib/use-toast";
import type { AiSettings, AiSettingsUpdate, AvailableModels } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
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
import { Separator } from "@/components/ui/separator";

type ProviderKey = "anthropic" | "mistral" | "openai" | "tavily";

const PROVIDER_LABELS: Record<ProviderKey, string> = {
  anthropic: "Anthropic",
  mistral: "Mistral",
  openai: "OpenAI",
  tavily: "Tavily",
};

const PROVIDER_OPTIONS = [
  { value: "anthropic", label: "Anthropic" },
  { value: "mistral", label: "Mistral" },
  { value: "openai", label: "OpenAI" },
];

const OCR_OPTIONS = [
  { value: "mistral", label: "Mistral (Pixtral)" },
  { value: "claude_vision", label: "Claude Vision" },
];

export default function AiSettingsPage() {
  const t = useTranslations("aiSettings");
  const common = useTranslations("common");
  const locale = useLocale();
  const params = useParams<{ id: string }>();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [settings, setSettings] = useState<AiSettings | null>(null);
  const [models, setModels] = useState<AvailableModels | null>(null);
  const [form, setForm] = useState<AiSettingsUpdate>({});

  const [editingKey, setEditingKey] = useState<ProviderKey | null>(null);
  const [keyInput, setKeyInput] = useState("");
  const [testingKey, setTestingKey] = useState(false);
  const [testResult, setTestResult] = useState<{ valid: boolean; error?: string } | null>(null);
  const [deletingKey, setDeletingKey] = useState<ProviderKey | null>(null);

  const apiBase = `/api/v1/clients/${params.id}/ai-settings`;

  const loadSettings = useCallback(async () => {
    try {
      const [s, m] = await Promise.all([
        api.get<AiSettings>(apiBase),
        api.get<AvailableModels>(`${apiBase}/models`),
      ]);
      setSettings(s);
      setModels(m);
      setForm({
        chat_provider: s.chat_provider,
        chat_model: s.chat_model,
        booking_provider: s.booking_provider,
        booking_model: s.booking_model,
        ocr_provider: s.ocr_provider,
        use_global_fallback: s.use_global_fallback,
        langsmith_enabled: s.langsmith_enabled,
      });
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.detail : t("loadError"));
    } finally {
      setLoading(false);
    }
  }, [apiBase, t]);

  useEffect(() => {
    loadSettings();
  }, [loadSettings]);

  function updateForm<K extends keyof AiSettingsUpdate>(key: K, value: AiSettingsUpdate[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  function getModelsForProvider(provider: string | undefined) {
    if (!provider || !models) return [];
    return models.providers[provider] ?? [];
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      const updated = await api.patch<AiSettings>(apiBase, form);
      setSettings(updated);
      showToast(t("settingsSaved"), "success");
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : common("saveFailed");
      showToast(msg, "error");
    } finally {
      setSaving(false);
    }
  }

  function startEditKey(provider: ProviderKey) {
    setEditingKey(provider);
    setKeyInput("");
    setTestResult(null);
  }

  function cancelEditKey() {
    setEditingKey(null);
    setKeyInput("");
    setTestResult(null);
  }

  async function handleSaveKey(provider: ProviderKey) {
    if (!keyInput.trim()) return;
    setSaving(true);
    try {
      const keyField = `${provider}_api_key` as keyof AiSettingsUpdate;
      const updated = await api.patch<AiSettings>(apiBase, { [keyField]: keyInput.trim() });
      setSettings(updated);
      cancelEditKey();
      showToast(t("keySaved", { provider: PROVIDER_LABELS[provider] }), "success");
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : common("saveFailed");
      showToast(msg, "error");
    } finally {
      setSaving(false);
    }
  }

  async function handleTestKey() {
    setTestingKey(true);
    setTestResult(null);
    try {
      const result = await api.post<{ valid: boolean; error?: string }>(`${apiBase}/test`);
      setTestResult(result);
    } catch (err) {
      setTestResult({ valid: false, error: err instanceof ApiError ? err.detail : t("testError") });
    } finally {
      setTestingKey(false);
    }
  }

  async function handleDeleteKey(provider: ProviderKey) {
    setDeletingKey(provider);
    try {
      await api.delete(`${apiBase}/keys/${provider}`);
      const updated = await api.get<AiSettings>(apiBase);
      setSettings(updated);
      showToast(t("keyDeleted", { provider: PROVIDER_LABELS[provider] }), "success");
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : t("deleteError");
      showToast(msg, "error");
    } finally {
      setDeletingKey(null);
    }
  }

  if (loading) {
    return (
      <main className="mx-auto max-w-2xl px-6 py-10">
        <div className="flex items-center gap-3">
          <Skeleton className="size-7 rounded-lg" />
          <div>
            <Skeleton className="h-7 w-52" />
            <Skeleton className="mt-2 h-4 w-36" />
          </div>
        </div>
        <div className="mt-8 flex flex-col gap-6">
          <Skeleton className="h-48 rounded-lg" />
          <Skeleton className="h-32 rounded-lg" />
          <Skeleton className="h-64 rounded-lg" />
        </div>
      </main>
    );
  }

  if (loadError || !settings) {
    return (
      <main className="mx-auto max-w-2xl px-6 py-10">
        <div className="flex flex-col items-center gap-4 rounded-lg border border-destructive/20 bg-destructive/5 p-10 text-center">
          <AlertCircleIcon className="size-8 text-destructive" />
          <div>
            <p className="font-medium text-destructive">{t("loadError")}</p>
            <p className="mt-1 text-sm text-destructive/80">{loadError ?? t("notFound")}</p>
          </div>
          <Button variant="outline" render={<Link href={`/clients/${params.id}`} />}>
            <ArrowLeftIcon data-icon="inline-start" />
            {common("back")}
          </Button>
        </div>
      </main>
    );
  }

  const chatModels = getModelsForProvider(form.chat_provider);
  const bookingModels = getModelsForProvider(form.booking_provider);

  const providers: ProviderKey[] = ["anthropic", "mistral", "openai", "tavily"];

  return (
    <main className="mx-auto max-w-2xl px-6 py-10">
      <div className="flex items-center gap-3">
        <Button
          variant="ghost"
          size="icon-sm"
          render={<Link href={`/clients/${params.id}`} />}
        >
          <ArrowLeftIcon />
        </Button>
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{t("title")}</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {t("description")}
          </p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="mt-8 flex flex-col gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <SettingsIcon className="size-5" />
              {t("chatAndBookings")}
            </CardTitle>
            <CardDescription>
              {t("chatAndBookingsDescription")}
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="flex flex-col gap-2">
                <Label>{t("chatProvider")}</Label>
                <Select
                  value={form.chat_provider ?? ""}
                  onValueChange={(val) => {
                    if (!val) return;
                    updateForm("chat_provider", val);
                    const providerModels = getModelsForProvider(val);
                    if (providerModels.length > 0) {
                      updateForm("chat_model", providerModels[0].id);
                    }
                  }}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder={t("selectProvider")} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      {PROVIDER_OPTIONS.map((opt) => (
                        <SelectItem key={opt.value} value={opt.value}>
                          {opt.label}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
              </div>
              <div className="flex flex-col gap-2">
                <Label>{t("chatModel")}</Label>
                <Select
                  value={form.chat_model ?? ""}
                  onValueChange={(val) => val && updateForm("chat_model", val)}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder={t("selectModel")} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      {chatModels.map((m) => (
                        <SelectItem key={m.id} value={m.id}>
                          {m.label}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <Separator />

            <div className="grid grid-cols-2 gap-4">
              <div className="flex flex-col gap-2">
                <Label>{t("bookingProvider")}</Label>
                <Select
                  value={form.booking_provider ?? ""}
                  onValueChange={(val) => {
                    if (!val) return;
                    updateForm("booking_provider", val);
                    const providerModels = getModelsForProvider(val);
                    if (providerModels.length > 0) {
                      updateForm("booking_model", providerModels[0].id);
                    }
                  }}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder={t("selectProvider")} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      {PROVIDER_OPTIONS.map((opt) => (
                        <SelectItem key={opt.value} value={opt.value}>
                          {opt.label}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
              </div>
              <div className="flex flex-col gap-2">
                <Label>{t("bookingModel")}</Label>
                <Select
                  value={form.booking_model ?? ""}
                  onValueChange={(val) => val && updateForm("booking_model", val)}
                >
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder={t("selectModel")} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      {bookingModels.map((m) => (
                        <SelectItem key={m.id} value={m.id}>
                          {m.label}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  </SelectContent>
                </Select>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{t("ocrTitle")}</CardTitle>
            <CardDescription>
              {t("ocrDescription")}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-col gap-2">
              <Label>{t("ocrProvider")}</Label>
              <Select
                value={form.ocr_provider ?? ""}
                onValueChange={(val) => val && updateForm("ocr_provider", val)}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder={t("selectProvider")} />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    {OCR_OPTIONS.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <KeyIcon className="size-5" />
              {t("apiKeys")}
            </CardTitle>
            <CardDescription>
              {t("apiKeysDescription")}
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            {providers.map((provider) => {
              const keySetField = `${provider}_key_set` as keyof AiSettings;
              const hintField = `${provider}_key_hint` as keyof AiSettings;
              const isSet = settings[keySetField] as boolean;
              const hint = settings[hintField] as string | null;
              const isEditing = editingKey === provider;
              const isDeleting = deletingKey === provider;

              return (
                <div key={provider}>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Label className="text-sm font-medium">
                        {provider === "tavily" ? t("tavilySearch") : PROVIDER_LABELS[provider]}
                      </Label>
                      {isSet ? (
                        <Badge variant="secondary" className="gap-1">
                          <EyeOffIcon className="size-3" />
                          {hint ?? t("keySet")}
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="text-muted-foreground">
                          {t("keyNotSet")}
                        </Badge>
                      )}
                    </div>
                    {!isEditing && (
                      <div className="flex items-center gap-1">
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => startEditKey(provider)}
                        >
                          {isSet ? t("changeKey") : t("addKey")}
                        </Button>
                        {isSet && (
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon-sm"
                            onClick={() => handleDeleteKey(provider)}
                            disabled={isDeleting}
                            className="text-muted-foreground hover:text-destructive"
                          >
                            {isDeleting ? (
                              <Loader2Icon className="size-3.5 animate-spin" />
                            ) : (
                              <TrashIcon className="size-3.5" />
                            )}
                          </Button>
                        )}
                      </div>
                    )}
                  </div>

                  {isEditing && (
                    <div className="mt-2 flex flex-col gap-2">
                      <div className="flex gap-2">
                        <Input
                          type="password"
                          placeholder={t("enterApiKey", { provider: PROVIDER_LABELS[provider] })}
                          value={keyInput}
                          onChange={(e) => setKeyInput(e.target.value)}
                          className="flex-1"
                        />
                        <Button
                          type="button"
                          size="sm"
                          onClick={() => handleSaveKey(provider)}
                          disabled={!keyInput.trim() || saving}
                        >
                          {saving ? (
                            <Loader2Icon data-icon="inline-start" className="animate-spin" />
                          ) : (
                            <SaveIcon data-icon="inline-start" />
                          )}
                          {common("save")}
                        </Button>
                        <Button type="button" variant="outline" size="sm" onClick={cancelEditKey}>
                          {common("cancel")}
                        </Button>
                      </div>
                      {testResult && (
                        <div className={`flex items-center gap-2 text-sm ${testResult.valid ? "text-emerald-600" : "text-destructive"}`}>
                          {testResult.valid ? (
                            <CheckCircleIcon className="size-4" />
                          ) : (
                            <XCircleIcon className="size-4" />
                          )}
                          {testResult.valid ? t("keyValid") : testResult.error ?? t("keyInvalid")}
                        </div>
                      )}
                    </div>
                  )}

                  {provider !== "tavily" && <Separator className="mt-3" />}
                </div>
              );
            })}

            <div className="mt-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleTestKey}
                disabled={testingKey}
              >
                {testingKey ? (
                  <Loader2Icon data-icon="inline-start" className="animate-spin" />
                ) : (
                  <CheckCircleIcon data-icon="inline-start" />
                )}
                {t("testConfig")}
              </Button>
              {testResult && !editingKey && (
                <span className={`ml-3 text-sm ${testResult.valid ? "text-emerald-600" : "text-destructive"}`}>
                  {testResult.valid ? t("connectionSuccess") : testResult.error ?? t("connectionFailed")}
                </span>
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="flex flex-col gap-4 pt-6">
            <div className="flex items-center gap-3">
              <Checkbox
                id="use_global_fallback"
                checked={form.use_global_fallback ?? false}
                onCheckedChange={(checked) =>
                  updateForm("use_global_fallback", checked === true)
                }
              />
              <Label htmlFor="use_global_fallback" className="cursor-pointer">
                {t("allowFallback")}
              </Label>
            </div>
            <div className="flex items-center gap-3">
              <Checkbox
                id="langsmith_enabled"
                checked={form.langsmith_enabled ?? false}
                onCheckedChange={(checked) =>
                  updateForm("langsmith_enabled", checked === true)
                }
              />
              <Label htmlFor="langsmith_enabled" className="cursor-pointer">
                {t("enableLangsmith")}
              </Label>
            </div>
          </CardContent>
        </Card>

        <div className="flex items-start gap-3 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 dark:border-blue-900 dark:bg-blue-950">
          <ShieldCheckIcon className="mt-0.5 size-5 shrink-0 text-blue-600 dark:text-blue-400" />
          <div className="text-sm text-blue-800 dark:text-blue-200">
            <p className="font-medium">{t("privacyTitle")}</p>
            <p className="mt-1 text-blue-700 dark:text-blue-300">
              {t("privacyText")}
            </p>
          </div>
        </div>

        <div className="flex justify-end gap-3">
          <Button
            variant="outline"
            render={<Link href={`/clients/${params.id}`} />}
          >
            {common("cancel")}
          </Button>
          <Button type="submit" disabled={saving}>
            {saving ? (
              <Loader2Icon data-icon="inline-start" className="animate-spin" />
            ) : (
              <SaveIcon data-icon="inline-start" />
            )}
            {saving ? common("saving") : common("save")}
          </Button>
        </div>
      </form>
    </main>
  );
}
