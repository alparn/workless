"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeftIcon, SaveIcon, Loader2Icon } from "lucide-react";

import { api, ApiError } from "@/lib/api-client";
import { showToast } from "@/lib/use-toast";
import type { Client, ClientCreate } from "@/lib/types";
import { INDUSTRY_OPTIONS } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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

export default function NewClientPage() {
  const router = useRouter();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  function updateField<K extends keyof ClientCreate>(
    key: K,
    value: ClientCreate[K],
  ) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
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

      const client = await api.post<Client>("/api/v1/clients", payload);
      showToast("Mandant erfolgreich angelegt", "success");
      router.push(`/clients/${client.id}`);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.detail);
      } else {
        setError("Ein unerwarteter Fehler ist aufgetreten.");
      }
      setSaving(false);
    }
  }

  return (
    <main className="mx-auto max-w-2xl px-6 py-10">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon-sm" render={<Link href="/clients" />}>
          <ArrowLeftIcon />
        </Button>
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            Neuer Mandant
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Erfassen Sie die Stammdaten und DATEV-Konfiguration.
          </p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="mt-8 flex flex-col gap-6">
        {error && (
          <div className="rounded-lg border border-destructive/20 bg-destructive/5 px-4 py-3 text-sm text-destructive">
            {error}
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
              Die Branche bestimmt, wie Belege kontiert werden (z.B. Lebensmittel = Wareneinkauf bei Gastro, aber privat bei IT)
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
                  onValueChange={(val) => val && updateField("chart_of_accounts", val)}
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
          <Button variant="outline" render={<Link href="/clients" />}>
            Abbrechen
          </Button>
          <Button type="submit" disabled={saving || !form.company_name.trim()}>
            {saving ? (
              <Loader2Icon data-icon="inline-start" className="animate-spin" />
            ) : (
              <SaveIcon data-icon="inline-start" />
            )}
            {saving ? "Wird gespeichert…" : "Mandant anlegen"}
          </Button>
        </div>
      </form>
    </main>
  );
}
