"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { KeyRound } from "lucide-react";
import { AuthShell } from "@/components/auth/auth-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { resetPassword } from "@/features/api/client";

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<AuthShell title="Choose a new password" description="Loading the reset request."><div className="h-40 animate-pulse rounded-lg bg-white/5" /></AuthShell>}>
      <ResetPasswordForm />
    </Suspense>
  );
}

function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [token, setToken] = useState(searchParams.get("token") ?? "");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (password !== confirmPassword) return setMessage("Passwords do not match.");
    setLoading(true);
    try {
      const response = await resetPassword(token, password);
      setMessage(response.message);
      setTimeout(() => router.replace("/login"), 900);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to reset password.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthShell title="Choose a new password" description="Reset tokens expire after 30 minutes and can only be used once.">
      <form className="space-y-4" onSubmit={submit}>
        <label className="block">
          <span className="mb-2 block text-sm text-slate-300">Reset token</span>
          <Input value={token} onChange={(event) => setToken(event.target.value)} required />
        </label>
        <label className="block">
          <span className="mb-2 block text-sm text-slate-300">New password</span>
          <Input type="password" autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} required />
        </label>
        <label className="block">
          <span className="mb-2 block text-sm text-slate-300">Confirm password</span>
          <Input type="password" autoComplete="new-password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} required />
        </label>
        {message ? <div className="rounded-md border border-cyan-300/20 bg-cyan-300/10 p-3 text-sm text-cyan-100">{message}</div> : null}
        <Button className="w-full" type="submit" disabled={loading}>
          <KeyRound className="h-4 w-4" />
          {loading ? "Updating password" : "Update password"}
        </Button>
      </form>
    </AuthShell>
  );
}
