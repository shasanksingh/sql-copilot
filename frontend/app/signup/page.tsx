"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { LoaderCircle, ShieldQuestion, UserPlus } from "lucide-react";
import { AuthShell } from "@/components/auth/auth-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { ApiError, signup } from "@/features/api/client";
import { useAuth } from "@/features/auth/auth-provider";
import { useToastStore } from "@/features/store/use-toast-store";

const securityQuestions = [
  "What city were you born in?",
  "What was the name of your first school?",
  "What was the name of your first pet?",
  "What is the name of a memorable childhood friend?"
];

function passwordScore(password: string) {
  if (!password) return 0;

  // Score the actual composition instead of awarding a fixed 20% per rule.
  // This keeps short or repetitive passwords from looking strong.
  let score = Math.min(30, password.length * 3);
  if (/[a-z]/.test(password)) score += 10;
  if (/[A-Z]/.test(password)) score += 10;
  if (/\d/.test(password)) score += 10;
  if (/[^A-Za-z0-9]/.test(password)) score += 15;
  if (new Set(password).size >= 6) score += 10;
  if (password.length >= 12) score += 10;
  if (/(.)\1{2,}/.test(password)) score -= 15;

  return Math.max(0, Math.min(100, score));
}

export default function SignupPage() {
  const { setUser } = useAuth();
  const pushToast = useToastStore((state) => state.pushToast);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [securityQuestion, setSecurityQuestion] = useState(securityQuestions[0]);
  const [securityAnswer, setSecurityAnswer] = useState("");
  const [loading, setLoading] = useState(false);
  const strength = useMemo(() => passwordScore(password), [password]);

  const reject = (title: string) => pushToast({ title, variant: "warning" });
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (name.trim().length < 2) return reject("Enter your full name");
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return reject("Enter a valid email address");
    if (strength < 80) return reject("Use a stronger password with uppercase, lowercase, a number, and a symbol");
    if (password !== confirmPassword) return reject("The passwords do not match");
    if (securityAnswer.trim().length < 2) return reject("Answer the security question for account recovery");
    setLoading(true);
    try {
      const response = await signup({ name, email, password, security_question: securityQuestion, security_answer: securityAnswer });
      setUser(response.user);
      window.location.replace("/dashboard");
    } catch (error) {
      const description = error instanceof ApiError && error.code === "ACCOUNT_EXISTS"
        ? "An account already exists for this email. Sign in instead."
        : error instanceof Error ? error.message : "Please try again.";
      pushToast({ title: "Unable to create account", description, variant: "error" });
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthShell title="Create your account" description="Create an account and a recovery check.">
      <form className="space-y-4" onSubmit={submit}>
        <Field label="Name" value={name} onChange={setName} autoComplete="name" />
        <Field label="Email" value={email} onChange={setEmail} type="email" autoComplete="email" />
        <Field label="Password" value={password} onChange={setPassword} type="password" autoComplete="new-password" />
        <div><div className="mb-2 flex justify-between text-xs text-slate-500"><span>Password strength</span><span>{strength}%</span></div><Progress value={strength} /></div>
        <Field label="Confirm password" value={confirmPassword} onChange={setConfirmPassword} type="password" autoComplete="new-password" />
        <div className="rounded-xl border border-cyan-300/15 bg-cyan-300/5 p-3">
          <div className="mb-3 flex items-center gap-2 text-sm font-medium text-cyan-100"><ShieldQuestion className="h-4 w-4" />Account recovery</div>
          <label className="block"><span className="mb-2 block text-sm text-slate-300">Security question</span><select value={securityQuestion} onChange={(event) => setSecurityQuestion(event.target.value)} className="h-11 w-full rounded-xl border border-white/10 bg-slate-950/60 px-3.5 text-sm text-white outline-none focus:border-cyan-300/70 focus:ring-4 focus:ring-cyan-300/15">{securityQuestions.map((question) => <option key={question} value={question}>{question}</option>)}</select></label>
          <div className="mt-3"><Field label="Your answer" value={securityAnswer} onChange={setSecurityAnswer} autoComplete="off" /></div>
        </div>
        <Button className="w-full" type="submit" disabled={loading}>{loading ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <UserPlus className="h-4 w-4" />}{loading ? "Creating account" : "Create account"}</Button>
      </form>
      <p className="mt-6 text-center text-sm text-slate-400">Already have an account? <Link className="text-cyan-200 hover:text-cyan-100" href="/login">Sign in</Link></p>
    </AuthShell>
  );
}

function Field({ label, value, onChange, type = "text", autoComplete }: { label: string; value: string; onChange: (value: string) => void; type?: string; autoComplete?: string }) {
  return <label className="block"><span className="mb-2 block text-sm text-slate-300">{label}</span><Input type={type} autoComplete={autoComplete} value={value} onChange={(event) => onChange(event.target.value)} /></label>;
}
