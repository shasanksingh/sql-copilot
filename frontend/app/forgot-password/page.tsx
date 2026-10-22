"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ArrowRight, KeyRound, ShieldQuestion } from "lucide-react";
import { AuthShell } from "@/components/auth/auth-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ApiError, forgotPassword } from "@/features/api/client";
import { useToastStore } from "@/features/store/use-toast-store";

export default function ForgotPasswordPage() {
  const router = useRouter();
  const pushToast = useToastStore((state) => state.pushToast);
  const [email, setEmail] = useState("");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setLoading(true);
    try {
      const response = await forgotPassword(email, question ? answer : undefined);
      if (response.requires_security_answer && response.security_question) {
        setQuestion(response.security_question);
        pushToast({ title: "Security question ready", description: "Answer it to choose a new password.", variant: "success" });
      } else if (response.reset_token) {
        router.replace(`/reset-password?token=${encodeURIComponent(response.reset_token)}`);
      }
    } catch (error) {
      const apiError = error instanceof ApiError ? error : undefined;
      const description = apiError?.code === "ACCOUNT_NOT_FOUND"
        ? "Create an account first, then use this recovery option."
        : apiError?.code === "INCORRECT_SECURITY_ANSWER"
          ? "Please check your answer and try again."
          : error instanceof Error ? error.message : "Please try again.";
      pushToast({ title: apiError?.code === "ACCOUNT_NOT_FOUND" ? "Account not found" : "Recovery could not continue", description, variant: "error" });
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthShell title="Reset your password" description="Verify your account before choosing a new password.">
      <form className="space-y-4" onSubmit={submit}>
        <label className="block"><span className="mb-2 block text-sm text-slate-300">Email</span><Input type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} required disabled={Boolean(question)} /></label>
        {question ? <><div className="rounded-xl border border-cyan-300/20 bg-cyan-300/10 p-3 text-sm text-cyan-100"><div className="flex items-center gap-2 font-medium"><ShieldQuestion className="h-4 w-4" />Security question</div><p className="mt-2 text-slate-200">{question}</p></div><label className="block"><span className="mb-2 block text-sm text-slate-300">Your answer</span><Input autoComplete="off" value={answer} onChange={(event) => setAnswer(event.target.value)} required /></label></> : null}
        <Button className="w-full" type="submit" disabled={loading}>{question ? <KeyRound className="h-4 w-4" /> : <ArrowRight className="h-4 w-4" />}{loading ? "Checking" : question ? "Continue" : "Find my account"}</Button>
      </form>
      <Link className="mt-6 block text-center text-sm text-cyan-200" href="/login">Return to sign in</Link>
    </AuthShell>
  );
}
