"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { PlusIcon, BuildingIcon, ArrowRightIcon, AlertCircleIcon, SearchIcon } from "lucide-react";

import { api } from "@/lib/api-client";
import type { Client } from "@/lib/types";
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

export default function ClientsPage() {
  const [clients, setClients] = useState<Client[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<Client[]>("/api/v1/clients")
      .then(setClients)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  const q = search.toLowerCase();
  const filteredClients = clients.filter((c) => {
    if (!q) return true;
    return [
      c.company_name,
      c.legal_form,
      c.tax_number,
      c.chart_of_accounts,
      c.datev_consultant_number?.toString(),
      c.datev_client_number?.toString(),
    ]
      .filter(Boolean)
      .some((val) => val!.toLowerCase().includes(q));
  });

  return (
    <main className="mx-auto max-w-6xl px-6 py-10 lg:px-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Mandanten</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Verwalten Sie Ihre Mandanten und deren DATEV-Konfiguration.
          </p>
        </div>
        <Button render={<Link href="/clients/new" />}>
          <PlusIcon data-icon="inline-start" />
          Neuer Mandant
        </Button>
      </div>

      <div className="mt-8">
        {loading ? (
          <div className="rounded-lg border">
            <div className="flex flex-col gap-2 p-4">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-12 rounded" />
              ))}
            </div>
          </div>
        ) : error ? (
          <div className="flex flex-col items-center gap-4 rounded-lg border border-destructive/20 bg-destructive/5 p-10 text-center">
            <AlertCircleIcon className="size-8 text-destructive" />
            <div>
              <p className="font-medium text-destructive">Fehler beim Laden</p>
              <p className="mt-1 text-sm text-destructive/80">{error}</p>
            </div>
          </div>
        ) : clients.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-4 rounded-xl border border-dashed py-20">
            <div className="flex size-12 items-center justify-center rounded-full bg-muted">
              <BuildingIcon className="size-6 text-muted-foreground" />
            </div>
            <div className="text-center">
              <p className="font-medium">Noch keine Mandanten</p>
              <p className="mt-1 text-sm text-muted-foreground">
                Erstellen Sie Ihren ersten Mandanten, um Belege hochzuladen.
              </p>
            </div>
            <Button render={<Link href="/clients/new" />}>
              <PlusIcon data-icon="inline-start" />
              Mandant anlegen
            </Button>
          </div>
        ) : (
          <>
          <div className="relative mb-4">
            <SearchIcon className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Mandanten durchsuchen…"
              className="pl-8"
            />
          </div>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Firma</TableHead>
                <TableHead>Rechtsform</TableHead>
                <TableHead>Steuernummer</TableHead>
                <TableHead>Kontenrahmen</TableHead>
                <TableHead>DATEV-Nr.</TableHead>
                <TableHead className="text-right">Erstellt</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredClients.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="py-8 text-center text-muted-foreground">
                    Keine Mandanten gefunden.
                  </TableCell>
                </TableRow>
              ) : filteredClients.map((client) => (
                <TableRow key={client.id}>
                  <TableCell className="font-medium">
                    {client.company_name}
                  </TableCell>
                  <TableCell>
                    {client.legal_form ?? (
                      <span className="text-muted-foreground">–</span>
                    )}
                  </TableCell>
                  <TableCell>
                    {client.tax_number ?? (
                      <span className="text-muted-foreground">–</span>
                    )}
                  </TableCell>
                  <TableCell>
                    <Badge variant="secondary">
                      {client.chart_of_accounts}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    {client.datev_client_number != null
                      ? `${client.datev_consultant_number ?? "–"} / ${client.datev_client_number}`
                      : <span className="text-muted-foreground">–</span>}
                  </TableCell>
                  <TableCell className="text-right text-muted-foreground">
                    {new Date(client.created_at).toLocaleDateString("de-DE")}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      render={<Link href={`/clients/${client.id}`} />}
                    >
                      <ArrowRightIcon />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          </>
        )}
      </div>
    </main>
  );
}
