"use client";

import type React from "react";
import { Sidebar } from "./sidebar";
import { Topbar } from "./topbar";
import { CommandPalette } from "./command-palette";
import { useCopilotStore } from "@/features/store/use-copilot-store";
import { AnimatePresence, motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { useAuth } from "@/features/auth/auth-provider";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { Skeleton } from "@/components/ui/skeleton";

export function AppShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { user, loading } = useAuth();
  const collapsed = useCopilotStore((state) => state.sidebarCollapsed);
  const mobileSidebarOpen = useCopilotStore((state) => state.mobileSidebarOpen);
  const setMobileSidebarOpen = useCopilotStore((state) => state.setMobileSidebarOpen);

  useEffect(() => {
    if (!loading && !user) {
      router.replace(`/login?next=${encodeURIComponent(pathname)}`);
    }
  }, [loading, pathname, router, user]);

  if (loading || !user) {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-slate-950 p-6">
        <div className="w-full max-w-sm space-y-3">
          <Skeleton className="h-10 w-40" />
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      </div>
    );
  }

  return (
    <div className="h-dvh overflow-hidden">
      <div className="fixed inset-y-0 left-0 z-30 hidden lg:block">
        <Sidebar />
      </div>
      <AnimatePresence>
        {mobileSidebarOpen ? (
          <motion.div className="fixed inset-0 z-40 lg:hidden" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <button className="absolute inset-0 bg-slate-950/70" onClick={() => setMobileSidebarOpen(false)} aria-label="Close navigation" />
            <motion.div initial={{ x: -320 }} animate={{ x: 0 }} exit={{ x: -320 }} transition={{ type: "spring", damping: 28, stiffness: 280 }} className="relative h-full">
              <Sidebar mobile />
            </motion.div>
          </motion.div>
        ) : null}
      </AnimatePresence>
      <div
        className={cn(
          "flex h-dvh min-w-0 flex-1 flex-col transition-[padding-left] duration-300 ease-out",
          collapsed ? "lg:pl-20" : "lg:pl-72"
        )}
      >
        <Topbar />
        <main className="min-h-0 min-w-0 flex-1 overflow-y-auto overscroll-contain p-3 sm:p-4 md:p-6">{children}</main>
      </div>
      <CommandPalette />
    </div>
  );
}
