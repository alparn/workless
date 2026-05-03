"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeftIcon,
  SaveIcon,
  Loader2Icon,
  AlertCircleIcon,
  PlusIcon,
  PencilIcon,
  TrashIcon,
  StarIcon,
  BanknoteIcon,
} from "lucide-react";

import { api, ApiError } from "@/lib/api-client";
import { showToast } from "@/lib/use-toast";
import type { Client, ClientCreate, BankAccount, BankAccountCreate } from "@/lib/types";
import { INDUSTRY_OPTIONS } from "@/lib/types";
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

const EMPTY_BANK_FORM: BankAccountCreate = {
  account_number: "",
  bank_name: "",
  iban: null,
  bic: null,
  is_default: false,
  label: null,
};

export default function EditClientPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  const [form, setForm] = useState<ClientCreate>({
    company_name: "",
    legal_form: null,
    tax_number: null,
    vat_id: null,
    tax_office: null,
    datev_consultant_number: null,
    datev_client_number: null,
    chart_of_accounts: "SKR03",
    account_length: 4,
    fiscal_year_start: "2026-01-01",
    default_vat_rate: "19.00",
    auto_booking_threshold: "0.85",
  });

  const [bankAccounts, setBankAccounts] = useState<BankAccount[]>([]);
  const [bankFormVisible, setBankFormVisible] = useState(false);
  const [editingBankId, setEditingBankId] = useState<string | null>(null);
  const [bankForm, setBankForm] = useState<BankAccountCreate>({ ...EMPTY_BANK_FORM });
  const [bankSaving, setBankSaving] = useState(false);
  const [deletingBankId, setDeletingBankId] = useState<string | null>(null);

  const bankApiBase = `/api/v1/clients/${params.id}/bank-accounts`;

  const loadBankAccounts = useCallback(async () => {
    try {
      const accounts = await api.get<BankAccount[]>(bankApiBase);
      setBankAccounts(accounts);
    } catch {
      // bank accounts are non-critical; silent fail
    }
  }, [bankApiBase]);

  useEffect(() => {
    Promise.all([
      api.get<Client>(`/api/v1/clients/${params.id}`),
      api.get<BankAccount[]>(bankApiBase).catch(() => [] as BankAccount[]),
    ])
      .then(([client, accounts]) => {
        setForm({
          company_name: client.company_name,
          legal_form: client.legal_form,
          tax_number: client.tax_number,
          vat_id: client.vat_id,
          tax_office: client.tax_office,
          industry: client.industry,
          industry_detail: client.industry_detail,
          datev_consultant_number: client.datev_consultant_number,
          datev_client_number: client.datev_client_number,
          chart_of_accounts: client.chart_of_accounts,
          account_length: client.account_length,
          fiscal_year_start: client.fiscal_year_start,
          default_vat_rate: client.default_vat_rate,
          auto_booking_threshold: client.auto_booking_threshold,
        });
        setBankAccounts(accounts);
      })
      .catch((err) => setLoadError(err.message))
      .finally(() => setLoading(false));
  }, [params.id, bankApiBase]);

  function openBankForm(account?: BankAccount) {
    if (account) {
      setEditingBankId(account.id);
      setBankForm({
        account_number: account.account_number,
        bank_name: account.bank_name,
        iban: account.iban,
        bic: account.bic,
        is_default: account.is_default,
        label: account.label,
      });
    } else {
      setEditingBankId(null);
      setBankForm({ ...EMPTY_BANK_FORM });
    }
    setBankFormVisible(true);
  }

  function closeBankForm() {
    setBankFormVisible(false);
    setEditingBankId(null);
    setBankForm({ ...EMPTY_BANK_FORM });
  }

  async function handleBankSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBankSaving(true);
    try {
      const payload: BankAccountCreate = {
        ...bankForm,
        account_number: bankForm.account_number.trim(),
        bank_name: bankForm.bank_name.trim(),
        iban: bankForm.iban?.trim().toUpperCase() || null,
        bic: bankForm.bic?.trim().toUpperCase() || null,
        label: bankForm.label?.trim() || null,
      };

      if (editingBankId) {
        await api.patch(`${bankApiBase}/${editingBankId}`, payload);
        showToast("Bankkonto aktualisiert", "success");
      } else {
        await api.post(bankApiBase, payload);
        showToast("Bankkonto hinzugefügt", "success");
      }
      closeBankForm();
      await loadBankAccounts();
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : "Fehler beim Speichern des Bankkontos.";
      showToast(msg, "error");
    } finally {
      setBankSaving(false);
    }
  }

  async function handleBankDelete(accountId: string) {
    setDeletingBankId(accountId);
    try {
      await api.delete(`${bankApiBase}/${accountId}`);
      showToast("Bankkonto gelöscht", "success");
      await loadBankAccounts();
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : "Fehler beim Löschen.";
      showToast(msg, "error");
    } finally {
      setDeletingBankId(null);
    }
  }

  function updateField<K extends keyof ClientCreate>(
    key: K,
    value: ClientCreate[K],
  ) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaveError(null);
    setSaving(true);

    try {
      const payload: ClientCreate = {
        ...form,
        company_name: form.company_name.trim(),
        legal_form: form.legal_form?.trim() || null,
        tax_number: form.tax_number?.trim() || null,
        vat_id: form.vat_id?.trim() || null,
        tax_office: form.tax_office?.trim() || null,
      };

      await api.patch<Client>(`/api/v1/clients/${params.id}`, payload);
      showToast("Mandant gespeichert", "success");
      router.push(`/clients/${params.id}`);
    } catch (err) {
      if (err instanceof ApiError) {
        setSaveError(err.detail);
      } else {
        setSaveError("Ein unerwarteter Fehler ist aufgetreten.");
      }
      setSaving(false);
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
          <Skeleton className="h-64 rounded-lg" />
          <Skeleton className="h-80 rounded-lg" />
        </div>
      </main>
    );
  }

  if (loadError) {
    return (
      <main className="mx-auto max-w-2xl px-6 py-10">
        <div className="flex flex-col items-center gap-4 rounded-lg border border-destructive/20 bg-destructive/5 p-10 text-center">
          <AlertCircleIcon className="size-8 text-destructive" />
          <div>
            <p className="font-medium text-destructive">Fehler beim Laden</p>
            <p className="mt-1 text-sm text-destructive/80">{loadError}</p>
          </div>
          <Button variant="outline" render={<Link href="/clients" />}>
            <ArrowLeftIcon data-icon="inline-start" />
            Zurück
          </Button>
        </div>
      </main>
    );
  }

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
          <h1 className="text-2xl font-bold tracking-tight">
            Mandant bearbeiten
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {form.company_name || "Stammdaten und DATEV-Konfiguration ändern"}
          </p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="mt-8 flex flex-col gap-6">
        {saveError && (
          <div className="rounded-lg border border-destructive/20 bg-destructive/5 px-4 py-3 text-sm text-destructive">
            {saveError}
          </div>
        )}

        <Card>
          <CardHeader>
            <CardTitle>Stammdaten</CardTitle>
            <CardDescription>Grundlegende Firmendaten</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label htmlFor="company_name">
                Firmenname <span className="text-destructive">*</span>
              </Label>
              <Input
                id="company_name"
                placeholder="z.B. Müller GmbH"
                required
                value={form.company_name}
                onChange={(e) => updateField("company_name", e.target.value)}
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="flex flex-col gap-2">
                <Label htmlFor="legal_form">Rechtsform</Label>
                <Input
                  id="legal_form"
                  placeholder="z.B. GmbH, UG, GbR"
                  value={form.legal_form ?? ""}
                  onChange={(e) =>
                    updateField("legal_form", e.target.value || null)
                  }
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="tax_office">Finanzamt</Label>
                <Input
                  id="tax_office"
                  placeholder="z.B. FA München I"
                  value={form.tax_office ?? ""}
                  onChange={(e) =>
                    updateField("tax_office", e.target.value || null)
                  }
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="flex flex-col gap-2">
                <Label htmlFor="tax_number">Steuernummer</Label>
                <Input
                  id="tax_number"
                  placeholder="z.B. 123/456/78901"
                  value={form.tax_number ?? ""}
                  onChange={(e) =>
                    updateField("tax_number", e.target.value || null)
                  }
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="vat_id">USt-IdNr.</Label>
                <Input
                  id="vat_id"
                  placeholder="z.B. DE123456789"
                  value={form.vat_id ?? ""}
                  onChange={(e) =>
                    updateField("vat_id", e.target.value || null)
                  }
                />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Branche</CardTitle>
            <CardDescription>
              Bestimmt die branchenspezifische Kontierungslogik
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              <Label>Branche</Label>
              <Select
                value={form.industry ?? ""}
                onValueChange={(val) => val && updateField("industry", val === "__none__" ? null : val)}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Branche wählen…" />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    <SelectItem value="__none__">Keine Angabe</SelectItem>
                    {INDUSTRY_OPTIONS.map((opt) => (
                      <SelectItem key={opt.key} value={opt.key}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="industry_detail">Zusätzliche Brancheninfos (optional)</Label>
              <Input
                id="industry_detail"
                placeholder="z.B. Spezialisiert auf vegane Küche, Catering-Service…"
                value={form.industry_detail ?? ""}
                onChange={(e) => updateField("industry_detail", e.target.value || null)}
              />
              <p className="text-xs text-muted-foreground">
                Freitext — wird dem KI-Agent als zusätzlicher Kontext mitgegeben
              </p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>DATEV-Konfiguration</CardTitle>
            <CardDescription>
              Beraternummer, Mandantennummer und Kontenrahmen
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="flex flex-col gap-2">
                <Label htmlFor="datev_consultant_number">Beraternummer</Label>
                <Input
                  id="datev_consultant_number"
                  type="number"
                  placeholder="z.B. 12345"
                  value={form.datev_consultant_number ?? ""}
                  onChange={(e) =>
                    updateField(
                      "datev_consultant_number",
                      e.target.value ? Number(e.target.value) : null,
                    )
                  }
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="datev_client_number">Mandantennummer</Label>
                <Input
                  id="datev_client_number"
                  type="number"
                  placeholder="z.B. 10001"
                  value={form.datev_client_number ?? ""}
                  onChange={(e) =>
                    updateField(
                      "datev_client_number",
                      e.target.value ? Number(e.target.value) : null,
                    )
                  }
                />
              </div>
            </div>

            <Separator />

            <div className="grid grid-cols-3 gap-4">
              <div className="flex flex-col gap-2">
                <Label>Kontenrahmen</Label>
                <Select
                  value={form.chart_of_accounts}
                  onValueChange={(val) =>
                    val && updateField("chart_of_accounts", val)
                  }
                >
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      <SelectItem value="SKR03">SKR03</SelectItem>
                      <SelectItem value="SKR04">SKR04</SelectItem>
                    </SelectGroup>
                  </SelectContent>
                </Select>
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="account_length">Kontolänge</Label>
                <Input
                  id="account_length"
                  type="number"
                  min={4}
                  max={8}
                  value={form.account_length ?? 4}
                  onChange={(e) =>
                    updateField("account_length", Number(e.target.value))
                  }
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="fiscal_year_start">GJ-Beginn</Label>
                <Input
                  id="fiscal_year_start"
                  type="date"
                  value={form.fiscal_year_start ?? "2026-01-01"}
                  onChange={(e) =>
                    updateField("fiscal_year_start", e.target.value)
                  }
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="flex flex-col gap-2">
                <Label htmlFor="default_vat_rate">Standard-USt. (%)</Label>
                <Input
                  id="default_vat_rate"
                  type="number"
                  step="0.01"
                  min="0"
                  max="100"
                  value={form.default_vat_rate ?? "19.00"}
                  onChange={(e) =>
                    updateField("default_vat_rate", e.target.value)
                  }
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="auto_booking_threshold">
                  Auto-Buchungs-Schwelle
                </Label>
                <Input
                  id="auto_booking_threshold"
                  type="number"
                  step="0.01"
                  min="0"
                  max="1"
                  value={form.auto_booking_threshold ?? "0.85"}
                  onChange={(e) =>
                    updateField("auto_booking_threshold", e.target.value)
                  }
                />
              </div>
            </div>
          </CardContent>
        </Card>

        <div className="flex justify-end gap-3">
          <Button
            variant="outline"
            render={<Link href={`/clients/${params.id}`} />}
          >
            Abbrechen
          </Button>
          <Button type="submit" disabled={saving || !form.company_name.trim()}>
            {saving ? (
              <Loader2Icon data-icon="inline-start" className="animate-spin" />
            ) : (
              <SaveIcon data-icon="inline-start" />
            )}
            {saving ? "Wird gespeichert…" : "Änderungen speichern"}
          </Button>
        </div>
      </form>

      {/* Bankkonten – outside the client form since they have their own CRUD */}
      <Card className="mt-6">
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <BanknoteIcon className="size-5" />
              Bankkonten
            </CardTitle>
            <CardDescription>
              Sachkonten für Bankkonten dieses Mandanten (z.B. 1200 = Commerzbank)
            </CardDescription>
          </div>
          {!bankFormVisible && (
            <Button
              size="sm"
              variant="outline"
              onClick={() => openBankForm()}
            >
              <PlusIcon data-icon="inline-start" />
              Konto hinzufügen
            </Button>
          )}
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {bankAccounts.length === 0 && !bankFormVisible && (
            <p className="text-sm text-muted-foreground text-center py-4">
              Noch keine Bankkonten hinterlegt. Fügen Sie ein Bankkonto hinzu, damit Kontoauszüge automatisch zugeordnet werden können.
            </p>
          )}

          {bankAccounts.length > 0 && (
            <div className="flex flex-col gap-2">
              {bankAccounts.map((account) => (
                <div
                  key={account.id}
                  className="flex items-center justify-between rounded-lg border px-4 py-3"
                >
                  <div className="flex flex-col gap-0.5">
                    <div className="flex items-center gap-2">
                      <span className="font-mono font-medium text-sm">
                        {account.account_number}
                      </span>
                      <span className="text-sm">{account.bank_name}</span>
                      {account.is_default && (
                        <Badge variant="secondary" className="gap-1">
                          <StarIcon className="size-3" />
                          Standard
                        </Badge>
                      )}
                    </div>
                    <div className="flex items-center gap-3 text-xs text-muted-foreground">
                      {account.iban && <span>{account.iban}</span>}
                      {account.bic && <span>{account.bic}</span>}
                      {account.label && <span>{account.label}</span>}
                    </div>
                  </div>
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => openBankForm(account)}
                      disabled={bankFormVisible}
                    >
                      <PencilIcon />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => handleBankDelete(account.id)}
                      disabled={deletingBankId === account.id}
                    >
                      {deletingBankId === account.id ? (
                        <Loader2Icon className="animate-spin" />
                      ) : (
                        <TrashIcon />
                      )}
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {bankFormVisible && (
            <>
              <Separator />
              <form onSubmit={handleBankSubmit} className="flex flex-col gap-4">
                <p className="text-sm font-medium">
                  {editingBankId ? "Bankkonto bearbeiten" : "Neues Bankkonto"}
                </p>

                <div className="grid grid-cols-2 gap-4">
                  <div className="flex flex-col gap-2">
                    <Label htmlFor="bank_account_number">
                      Sachkonto <span className="text-destructive">*</span>
                    </Label>
                    <Input
                      id="bank_account_number"
                      placeholder="z.B. 1200"
                      required
                      value={bankForm.account_number}
                      onChange={(e) =>
                        setBankForm((prev) => ({ ...prev, account_number: e.target.value }))
                      }
                    />
                  </div>
                  <div className="flex flex-col gap-2">
                    <Label htmlFor="bank_name">
                      Bankname <span className="text-destructive">*</span>
                    </Label>
                    <Input
                      id="bank_name"
                      placeholder="z.B. Hamburger Sparkasse"
                      required
                      value={bankForm.bank_name}
                      onChange={(e) =>
                        setBankForm((prev) => ({ ...prev, bank_name: e.target.value }))
                      }
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="flex flex-col gap-2">
                    <Label htmlFor="bank_iban">IBAN</Label>
                    <Input
                      id="bank_iban"
                      placeholder="z.B. DE89370400440532013000"
                      value={bankForm.iban ?? ""}
                      onChange={(e) =>
                        setBankForm((prev) => ({
                          ...prev,
                          iban: e.target.value || null,
                        }))
                      }
                    />
                  </div>
                  <div className="flex flex-col gap-2">
                    <Label htmlFor="bank_bic">BIC</Label>
                    <Input
                      id="bank_bic"
                      placeholder="z.B. COBADEFFXXX"
                      value={bankForm.bic ?? ""}
                      onChange={(e) =>
                        setBankForm((prev) => ({
                          ...prev,
                          bic: e.target.value || null,
                        }))
                      }
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="flex flex-col gap-2">
                    <Label htmlFor="bank_label">Bezeichnung</Label>
                    <Input
                      id="bank_label"
                      placeholder="z.B. Geschäftskonto"
                      value={bankForm.label ?? ""}
                      onChange={(e) =>
                        setBankForm((prev) => ({
                          ...prev,
                          label: e.target.value || null,
                        }))
                      }
                    />
                  </div>
                  <div className="flex items-end gap-2 pb-1">
                    <Checkbox
                      id="bank_is_default"
                      checked={bankForm.is_default ?? false}
                      onCheckedChange={(checked) =>
                        setBankForm((prev) => ({
                          ...prev,
                          is_default: checked === true,
                        }))
                      }
                    />
                    <Label htmlFor="bank_is_default" className="text-sm cursor-pointer">
                      Standardkonto für diesen Mandanten
                    </Label>
                  </div>
                </div>

                <div className="flex justify-end gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={closeBankForm}
                    disabled={bankSaving}
                  >
                    Abbrechen
                  </Button>
                  <Button
                    type="submit"
                    size="sm"
                    disabled={
                      bankSaving ||
                      !bankForm.account_number.trim() ||
                      !bankForm.bank_name.trim()
                    }
                  >
                    {bankSaving ? (
                      <Loader2Icon data-icon="inline-start" className="animate-spin" />
                    ) : (
                      <SaveIcon data-icon="inline-start" />
                    )}
                    {editingBankId ? "Aktualisieren" : "Hinzufügen"}
                  </Button>
                </div>
              </form>
            </>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
