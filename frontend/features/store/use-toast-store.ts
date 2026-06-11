"use client";

import { create } from "zustand";

export type Toast = {
  id: string;
  title: string;
  description?: string;
  variant?: "default" | "success" | "warning" | "error";
};

type ToastState = {
  toasts: Toast[];
  pushToast: (toast: Omit<Toast, "id">) => void;
  dismissToast: (id: string) => void;
};

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  pushToast: (toast) =>
    set((state) => ({
      toasts: [{ ...toast, id: crypto.randomUUID() }, ...state.toasts].slice(0, 4)
    })),
  dismissToast: (id) => set((state) => ({ toasts: state.toasts.filter((toast) => toast.id !== id) }))
}));
