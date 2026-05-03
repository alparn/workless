"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { ArrowLeftIcon, AlertCircleIcon } from "lucide-react";

import { api } from "@/lib/api-client";
import { showToast } from "@/lib/use-toast";
import type { Client } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { DocumentUpload } from "@/components/document-upload";

export default function UploadPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const t = useTranslations("upload");
  const common = useTranslations("common");
  const [client, setClient] = useState<Client | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<Client>(`/api/v1/clients/${params.id}`)
      .then(setClient)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [params.id]);

  if (loading) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-10">
        <div className="flex items-center gap-3">
          <Skeleton className="size-7 rounded-lg" />
          <div>
            <Skeleton className="h-7 w-44" />
            <Skeleton className="mt-2 h-4 w-28" />
          </div>
        </div>
        <Skeleton className="mt-8 h-64 rounded-lg" />
      </main>
    );
  }

  if (error || !client) {
    return (
      <main className="mx-auto max-w-3xl px-6 py-10">
        <div className="flex flex-col items-center gap-4 rounded-lg border border-destructive/20 bg-destructive/5 p-10 text-center">
          <AlertCircleIcon className="size-8 text-destructive" />
          <div>
            <p className="font-medium text-destructive">{common("loadingError")}</p>
            <p className="mt-1 text-sm text-destructive/80">
              {error ?? common("clientNotFound")}
            </p>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-3xl px-6 py-10">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon-sm" render={<Link href={`/clients/${params.id}`} />}>
          <ArrowLeftIcon />
        </Button>
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{t("title")}</h1>
          <p className="text-sm text-muted-foreground">{client.company_name}</p>
        </div>
      </div>

      <Card className="mt-8">
        <CardHeader>
          <CardTitle>{t("importTitle")}</CardTitle>
          <CardDescription>
            {t("importDescription")}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <DocumentUpload
            clientId={params.id}
            onUploadComplete={() => {
              showToast(t("uploadSuccessMessage"), "success");
              router.push(`/clients/${params.id}/documents`);
            }}
          />
        </CardContent>
      </Card>
    </main>
  );
}
