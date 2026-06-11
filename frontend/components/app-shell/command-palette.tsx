"use client";

import type { Route } from "next";
import { AnimatePresence, motion } from "framer-motion";
import { Search } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { Input } from "@/components/ui/input";
import { navItems } from "@/components/app-shell/sidebar";
import { useCopilotStore } from "@/features/store/use-copilot-store";

type CommandAction = {
  label: string;
  href: Route;
  keywords: string;
};

const actions: CommandAction[] = [
  {
    label: "Generate SQL from natural language",
    href: "/copilot",
    keywords: "chat prompt sql generation"
  },
  {
    label: "Inspect schema relationships",
    href: "/schema-graph",
    keywords: "graph joins tables relationships"
  },
  {
    label: "Open query planner",
    href: "/planner",
    keywords: "plan filters joins aggregations"
  },
  {
    label: "Review optimizer warnings",
    href: "/optimizer",
    keywords: "indexes performance warnings"
  },
  ...navItems.map(
    (item) =>
      ({
        label: item.label,
        href: item.href as Route,
        keywords: item.label.toLowerCase()
      }) satisfies CommandAction
  )
];

export function CommandPalette() {
  const open = useCopilotStore((state) => state.commandPaletteOpen);
  const setOpen = useCopilotStore((state) => state.setCommandPaletteOpen);
  const [query, setQuery] = useState("");

  const results = useMemo(() => {
    const term = query.trim().toLowerCase();

    if (!term) return actions;

    return actions.filter((action) =>
      `${action.label} ${action.keywords}`
        .toLowerCase()
        .includes(term)
    );
  }, [query]);

  return (
    <AnimatePresence>
      {open ? (
        <motion.div
          className="fixed inset-0 z-50"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          <button
            className="absolute inset-0 bg-slate-950/70 backdrop-blur-sm"
            onClick={() => setOpen(false)}
            aria-label="Close command palette"
          />

          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 12, scale: 0.98 }}
            className="absolute left-1/2 top-20 w-[min(720px,calc(100vw-2rem))] -translate-x-1/2 rounded-lg border border-white/10 bg-slate-950/92 p-3 shadow-2xl backdrop-blur-xl"
          >
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-slate-500" />

              <Input
                className="h-12 pl-10"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                autoFocus
                placeholder="Search commands, routes, schema tools"
              />
            </div>

            <div className="mt-3 max-h-80 overflow-auto pr-1 scrollbar-thin">
              {results.map((action) => (
                <Link
                  key={`${action.href}-${action.label}`}
                  href={action.href}
                  onClick={() => setOpen(false)}
                  className="block rounded-md px-3 py-3 text-sm text-slate-300 transition hover:bg-white/10 hover:text-white"
                >
                  {action.label}

                  <span className="ml-3 text-xs text-slate-600">
                    {action.href}
                  </span>
                </Link>
              ))}

              {!results.length ? (
                <div className="px-3 py-8 text-center text-sm text-slate-500">
                  No commands found.
                </div>
              ) : null}
            </div>
          </motion.div>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
