"use client";

import { AnimatePresence, motion } from "framer-motion";
import { CheckCircle2, Info, TriangleAlert, X, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useToastStore, type Toast } from "@/features/store/use-toast-store";
import { cn } from "@/lib/utils";

const iconByVariant = {
  default: Info,
  success: CheckCircle2,
  warning: TriangleAlert,
  error: XCircle
};

const toneByVariant: Record<NonNullable<Toast["variant"]>, string> = {
  default: "border-cyan-300/20",
  success: "border-emerald-300/25",
  warning: "border-amber-300/25",
  error: "border-rose-300/25"
};

export function Toaster() {
  const toasts = useToastStore((state) => state.toasts);
  const dismissToast = useToastStore((state) => state.dismissToast);

  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-[min(380px,calc(100vw-2rem))] flex-col gap-2">
      <AnimatePresence>
        {toasts.map((toast) => {
          const variant = toast.variant ?? "default";
          const Icon = iconByVariant[variant];
          return (
            <motion.div
              key={toast.id}
              initial={{ opacity: 0, y: 14, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 8, scale: 0.98 }}
              className={cn("pointer-events-auto rounded-lg border bg-slate-950/90 p-4 shadow-2xl backdrop-blur-xl", toneByVariant[variant])}
            >
              <div className="flex gap-3">
                <Icon className="mt-0.5 h-4 w-4 shrink-0 text-cyan-200" />
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium text-white">{toast.title}</div>
                  {toast.description ? <div className="mt-1 text-sm leading-5 text-slate-400">{toast.description}</div> : null}
                </div>
                <Button variant="ghost" className="h-7 w-7 px-0" onClick={() => dismissToast(toast.id)} aria-label="Dismiss toast">
                  <X className="h-4 w-4" />
                </Button>
              </div>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
