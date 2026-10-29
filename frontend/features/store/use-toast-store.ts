"use client";

import { create } from "zustand";

export type Toast = {
  id: string;
  title: string;
  description?: string;
  variant?: "default" | "success" | "warning" | "error";
  /** Optional lifetime in milliseconds. Short-lived progress confirmations should not need manual dismissal. */
  duration?: number;
};

type ToastState = {
  toasts: Toast[];
  pushToast: (toast: Omit<Toast, "id">) => void;
  dismissToast: (id: string) => void;
};

export const useToastStore = create<ToastState>((set, get) => ({
  toasts: [],
  pushToast: (toast) => {
    const id = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    set((state) => ({
      toasts: [{ ...toast, id }, ...state.toasts].slice(0, 4)
    }));
    if (typeof window !== "undefined") {
      window.setTimeout(() => get().dismissToast(id), toast.duration ?? 5_000);
    }
  },
  dismissToast: (id) => set((state) => ({ toasts: state.toasts.filter((toast) => toast.id !== id) }))
}));
