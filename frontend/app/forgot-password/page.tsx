"use client";

import Link from "next/link";
import { useState } from "react";
import { MailCheck } from "lucide-react";
import { AuthShell } from "@/components/auth/auth-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { forgotPassword } from "@/features/api/client";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [resetToken, setResetToken] = useState("");
  const [resetUrl, setResetUrl] = useState("");
  const [delivery, setDelivery] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setLoading(true);
    try {
      const response = await forgotPassword(email);
      setMessage(response.message);
      setResetToken(response.reset_token ?? "");
      setResetUrl(response.reset_url ?? "");
      const emailDelivery = response.email_delivery;
      if (emailDelivery?.status === "sent") {
        setDelivery("Reset email sent. Check your inbox and spam folder.");
      } else if (emailDelivery?.status === "outbox") {
        setDelivery(`Development email written to ${emailDelivery.outbox_path}.`);
      } else if (emailDelivery?.status === "account_not_found") {
        setDelivery("No active local account exists for this email.");
      } else if (emailDelivery?.reason) {
        setDelivery(emailDelivery.reason);
      } else {
        setDelivery("");
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to create reset request.");
      setDelivery("");
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthShell title="Reset your password" description="Enter your account email to create a short-lived reset request.">
      <form className="space-y-4" onSubmit={submit}>
        <label className="block">
          <span className="mb-2 block text-sm text-slate-300">Email</span>
          <Input type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
        </label>
        {message ? <div className="rounded-md border border-cyan-300/20 bg-cyan-300/10 p-3 text-sm text-cyan-100">{message}</div> : null}
        {delivery ? <div className="rounded-md border border-emerald-300/20 bg-emerald-300/10 p-3 text-sm text-emerald-100">{delivery}</div> : null}
        {resetUrl || resetToken ? (
          <a className="block rounded-md border border-indigo-300/20 bg-indigo-300/10 p-3 text-sm text-indigo-100" href={resetUrl || `/reset-password?token=${encodeURIComponent(resetToken)}`}>
            Continue with the development reset link
          </a>
        ) : null}
        <Button className="w-full" type="submit" disabled={loading}>
          <MailCheck className="h-4 w-4" />
          {loading ? "Creating request" : "Request password reset"}
        </Button>
      </form>
      <Link className="mt-6 block text-center text-sm text-cyan-200" href="/login">Return to sign in</Link>
    </AuthShell>
  );
}
