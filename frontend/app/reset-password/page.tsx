"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { KeyRound } from "lucide-react";
import { AuthShell } from "@/components/auth/auth-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { resetPassword } from "@/features/api/client";
import { useToastStore } from "@/features/store/use-toast-store";

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
  const [loading, setLoading] = useState(false);
  const pushToast = useToastStore((state) => state.pushToast);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (password !== confirmPassword) {
      pushToast({ title: "The passwords do not match", variant: "warning" });
      return;
    }
    setLoading(true);
    try {
      const response = await resetPassword(token, password);
      pushToast({ title: "Password updated", description: response.message, variant: "success" });
      setTimeout(() => router.replace("/login"), 900);
    } catch (error) {
      pushToast({ title: "Unable to update password", description: error instanceof Error ? error.message : "Please try again.", variant: "error" });
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthShell title="Choose a new password" description="Set a strong password to complete your account recovery.">
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
        <Button className="w-full" type="submit" disabled={loading}>
          <KeyRound className="h-4 w-4" />
          {loading ? "Updating password" : "Update password"}
        </Button>
      </form>
    </AuthShell>
  );
}
