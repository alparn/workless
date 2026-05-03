"use client";

import { XIcon, CheckCircle2Icon, AlertCircleIcon } from "lucide-react";

import { cn } from "@/lib/utils";
import { useToasts, type ToastVariant } from "@/lib/use-toast";

const variantStyles: Record<ToastVariant, string> = {
  default: "border-border bg-background text-foreground",
  success:
    "border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-100",
  error:
    "border-destructive/30 bg-destructive/5 text-destructive dark:bg-destructive/10",
};

const variantIcons: Record<ToastVariant, React.ReactNode> = {
  default: null,
  success: <CheckCircle2Icon className="size-4 shrink-0" />,
  error: <AlertCircleIcon className="size-4 shrink-0" />,
};

export function Toaster() {
  const { toasts, dismiss } = useToasts();

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={cn(
            "flex items-center gap-2 rounded-lg border px-4 py-3 text-sm shadow-lg",
            "animate-in slide-in-from-bottom-2 fade-in duration-200",
            variantStyles[toast.variant],
          )}
        >
          {variantIcons[toast.variant]}
          <span className="flex-1">{toast.message}</span>
          <button
            onClick={() => dismiss(toast.id)}
            className="shrink-0 rounded p-0.5 opacity-60 transition-opacity hover:opacity-100"
          >
            <XIcon className="size-3.5" />
          </button>
        </div>
      ))}
    </div>
  );
}
