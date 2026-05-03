import { useCallback, useSyncExternalStore } from "react";

export type ToastVariant = "default" | "success" | "error";

export interface Toast {
  id: string;
  message: string;
  variant: ToastVariant;
}

let toasts: Toast[] = [];
let listeners: Set<() => void> = new Set();
let nextId = 0;

function emit() {
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getSnapshot() {
  return toasts;
}

export function showToast(message: string, variant: ToastVariant = "default") {
  const id = String(++nextId);
  toasts = [...toasts, { id, message, variant }];
  emit();

  setTimeout(() => {
    dismissToast(id);
  }, 4000);
}

export function dismissToast(id: string) {
  toasts = toasts.filter((t) => t.id !== id);
  emit();
}

export function useToasts() {
  const current = useSyncExternalStore(subscribe, getSnapshot, getSnapshot);

  const toast = useCallback(
    (message: string, variant: ToastVariant = "default") =>
      showToast(message, variant),
    [],
  );

  return { toasts: current, toast, dismiss: dismissToast };
}
