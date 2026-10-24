"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { KeyRound, LoaderCircle, LogIn, Mail } from "lucide-react";
import { AuthShell } from "@/components/auth/auth-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError, login } from "@/features/api/client";
import { useAuth } from "@/features/auth/auth-provider";
import { useToastStore } from "@/features/store/use-toast-store";

export default function LoginPage() {
  return (
    <Suspense fallback={<AuthShell title="Welcome back" description="Loading sign in."><div className="h-40 animate-pulse rounded-lg bg-white/5" /></AuthShell>}>
      <LoginForm />
    </Suspense>
  );
}

function LoginForm() {
  const searchParams = useSearchParams();
  const { setUser } = useAuth();
  const pushToast = useToastStore((state) => state.pushToast);
  const [email, setEmail] = useState(() => searchParams.get("email") ?? "");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const resetComplete = searchParams.get("reset") === "success";
    const recoveryEmail = searchParams.get("email");
    if (recoveryEmail) setEmail(recoveryEmail);
    if (resetComplete) {
      pushToast({ title: "Password updated", description: "Sign in with your new password.", variant: "success" });
      const nextPath = searchParams.get("next");
      const cleanPath = nextPath?.startsWith("/") && !nextPath.startsWith("//")
        ? `/login?next=${encodeURIComponent(nextPath)}`
        : "/login";
      window.history.replaceState(null, "", cleanPath);
    }
  }, [pushToast, searchParams]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
      pushToast({ title: "Enter a valid email address", variant: "warning" });
      return;
    }
    if (!password) {
      pushToast({ title: "Enter your password", variant: "warning" });
      return;
    }
    setLoading(true);
    try {
      const response = await login({ email, password, remember });
      setUser(response.user);
      const nextPath = searchParams.get("next");
      const destination = nextPath?.startsWith("/") && !nextPath.startsWith("//") ? nextPath : "/dashboard";
      window.location.replace(destination);
    } catch (error) {
      const apiError = error instanceof ApiError ? error : undefined;
      if (apiError?.code === "ACCOUNT_NOT_FOUND") {
        pushToast({ title: "Account not found", description: "Create an account to continue.", variant: "warning" });
      } else if (apiError?.code === "INVALID_PASSWORD") {
        pushToast({ title: "Try your password again", description: "The password does not match this account.", variant: "error" });
      } else {
        pushToast({ title: "Unable to sign in", description: error instanceof Error ? error.message : "Please try again.", variant: "error" });
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthShell title="Welcome back" description="Sign in to your SQL Copilot account.">
      <form className="space-y-4" onSubmit={submit}>
        <label className="block">
          <span className="mb-2 block text-sm text-slate-300">Email</span>
          <div className="relative"><Mail className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-slate-500" /><Input className="pl-9" name="email" type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} /></div>
        </label>
        <label className="block">
          <span className="mb-2 block text-sm text-slate-300">Password</span>
          <div className="relative"><KeyRound className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-slate-500" /><Input className="pl-9" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} /></div>
        </label>
        <div className="flex items-center justify-between gap-3 text-sm">
          <label className="flex items-center gap-2 text-slate-400"><input className="h-4 w-4 accent-cyan-300" type="checkbox" checked={remember} onChange={(event) => setRemember(event.target.checked)} />Remember me</label>
          <Link href="/forgot-password" className="text-cyan-200 hover:text-cyan-100">Forgot password?</Link>
        </div>
        <Button className="w-full" type="submit" disabled={loading}>{loading ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <LogIn className="h-4 w-4" />}{loading ? "Signing in" : "Sign in"}</Button>
      </form>
      <p className="mt-6 text-center text-sm text-slate-400">New to SQL Copilot? <Link className="text-cyan-200 hover:text-cyan-100" href="/signup">Create an account</Link></p>
    </AuthShell>
  );
}
