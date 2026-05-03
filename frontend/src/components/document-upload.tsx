"use client";

import { useCallback, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { UploadCloudIcon, FileIcon, XIcon, CheckCircle2Icon, AlertCircleIcon, Loader2Icon } from "lucide-react";

import { api, ApiError } from "@/lib/api-client";
import type { Document } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const ACCEPTED_TYPES = ["application/pdf", "image/png", "image/jpeg"];
const MAX_SIZE = 10 * 1024 * 1024;

type FileEntry = {
  file: File;
  status: "pending" | "uploading" | "done" | "error";
  error?: string;
  document?: Document;
};

export function DocumentUpload({
  clientId,
  onUploadComplete,
}: {
  clientId: string;
  onUploadComplete?: () => void;
}) {
  const t = useTranslations("components");
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [dragActive, setDragActive] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const addFiles = useCallback((incoming: FileList | File[]) => {
    const newEntries: FileEntry[] = [];
    for (const file of Array.from(incoming)) {
      if (!ACCEPTED_TYPES.includes(file.type)) {
        newEntries.push({ file, status: "error", error: t("unsupportedFormat") });
        continue;
      }
      if (file.size > MAX_SIZE) {
        newEntries.push({ file, status: "error", error: t("fileTooLarge") });
        continue;
      }
      newEntries.push({ file, status: "pending" });
    }
    setFiles((prev) => [...prev, ...newEntries]);
  }, [t]);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragActive(false);
      if (e.dataTransfer.files.length > 0) {
        addFiles(e.dataTransfer.files);
      }
    },
    [addFiles],
  );

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const uploadAll = async () => {
    const pendingIndexes = files
      .map((f, i) => (f.status === "pending" ? i : -1))
      .filter((i) => i >= 0);

    if (pendingIndexes.length === 0) return;

    for (const idx of pendingIndexes) {
      setFiles((prev) =>
        prev.map((f, i) => (i === idx ? { ...f, status: "uploading" } : f)),
      );

      try {
        const formData = new FormData();
        formData.append("file", files[idx].file);

        const doc = await api.upload<Document>(
          "/api/v1/documents/upload",
          formData,
          { client_id: clientId },
        );

        setFiles((prev) =>
          prev.map((f, i) => (i === idx ? { ...f, status: "done", document: doc } : f)),
        );
      } catch (err) {
        const message =
          err instanceof ApiError ? err.detail : t("uploadFailed");
        setFiles((prev) =>
          prev.map((f, i) =>
            i === idx ? { ...f, status: "error", error: message } : f,
          ),
        );
      }
    }

    onUploadComplete?.();
  };

  const pendingCount = files.filter((f) => f.status === "pending").length;
  const doneCount = files.filter((f) => f.status === "done").length;

  return (
    <div className="flex flex-col gap-6">
      {/* Drop zone */}
      <div
        role="button"
        tabIndex={0}
        className={cn(
          "relative flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed p-10 transition-colors cursor-pointer",
          dragActive
            ? "border-primary bg-primary/5"
            : "border-border hover:border-primary/50 hover:bg-muted/50",
        )}
        onDragOver={(e) => {
          e.preventDefault();
          setDragActive(true);
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
        }}
      >
        <UploadCloudIcon className="size-10 text-muted-foreground" />
        <div className="text-center">
          <p className="font-medium">
            {t("dragFilesOr")} <span className="text-primary underline underline-offset-4">{t("browse")}</span>
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            {t("uploadHint")}
          </p>
        </div>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".pdf,.png,.jpg,.jpeg"
          className="hidden"
          onChange={(e) => {
            if (e.target.files) addFiles(e.target.files);
            e.target.value = "";
          }}
        />
      </div>

      {/* File list */}
      {files.length > 0 && (
        <div className="flex flex-col gap-2">
          {files.map((entry, index) => (
            <div
              key={`${entry.file.name}-${index}`}
              className="flex items-center gap-3 rounded-lg border px-4 py-3"
            >
              <FileIcon className="size-4 shrink-0 text-muted-foreground" />
              <div className="flex-1 min-w-0">
                <p className="truncate text-sm font-medium">{entry.file.name}</p>
                <p className="text-xs text-muted-foreground">
                  {formatBytes(entry.file.size)}
                  {entry.error && (
                    <span className="ml-2 text-destructive">{entry.error}</span>
                  )}
                </p>
              </div>
              <FileStatusIcon status={entry.status} />
              {(entry.status === "pending" || entry.status === "error") && (
                <button
                  type="button"
                  onClick={() => removeFile(index)}
                  className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                >
                  <XIcon className="size-3.5" />
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Actions */}
      {files.length > 0 && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            {pendingCount > 0
              ? t("filesReady", { count: pendingCount })
              : t("filesUploaded", { count: doneCount })}
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => setFiles([])}
            >
              {t("removeAll")}
            </Button>
            <Button
              onClick={uploadAll}
              disabled={pendingCount === 0}
            >
              {pendingCount > 0
                ? t("uploadFiles", { count: pendingCount })
                : t("done")}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function FileStatusIcon({ status }: { status: FileEntry["status"] }) {
  switch (status) {
    case "pending":
      return null;
    case "uploading":
      return <Loader2Icon className="size-4 animate-spin text-primary" />;
    case "done":
      return <CheckCircle2Icon className="size-4 text-emerald-600" />;
    case "error":
      return <AlertCircleIcon className="size-4 text-destructive" />;
  }
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
