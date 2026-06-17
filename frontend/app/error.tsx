"use client";

import { useEffect } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { logFrontendError } from "@/features/api/client";

export default function ErrorPage({
  error,
  reset
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    void logFrontendError({
      event: "route_render_error",
      level: "error",
      message: error.message,
      path: window.location.pathname,
      stack: error.stack
    }).catch(() => undefined);
  }, [error]);

  return (
    <main className="flex min-h-dvh items-center justify-center bg-slate-950 p-6">
      <div className="w-full max-w-lg rounded-lg border border-rose-300/20 bg-rose-300/10 p-8 text-center">
        <AlertTriangle className="mx-auto h-10 w-10 text-rose-200" />
        <h1 className="mt-4 text-xl font-semibold text-white">This page could not be rendered</h1>
        <p className="mt-2 break-words text-sm text-slate-300">{error.message}</p>
        <Button className="mt-6" onClick={reset}><RefreshCw className="h-4 w-4" />Try again</Button>
      </div>
    </main>
  );
}
