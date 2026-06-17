"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { LoaderCircle, UserPlus } from "lucide-react";
import { AuthShell } from "@/components/auth/auth-shell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { signup } from "@/features/api/client";
import { useAuth } from "@/features/auth/auth-provider";

function passwordScore(password: string) {
  return [
    password.length >= 8,
    /[a-z]/.test(password),
    /[A-Z]/.test(password),
    /\d/.test(password),
    /[^A-Za-z0-9]/.test(password)
  ].filter(Boolean).length * 20;
}

export default function SignupPage() {
  const { setUser } = useAuth();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const strength = useMemo(() => passwordScore(password), [password]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    if (name.trim().length < 2) return setError("Enter your full name.");
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return setError("Enter a valid email address.");
    if (strength < 80) return setError("Use at least 8 characters with uppercase, lowercase, and a number.");
    if (password !== confirmPassword) return setError("Passwords do not match.");
    setLoading(true);
    try {
      const response = await signup({ name, email, password });
      setUser(response.user);
      window.location.replace("/dashboard");
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to create account.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthShell title="Create your account" description="Start with a protected workspace and auditable SQL sessions.">
      <form className="space-y-4" onSubmit={submit}>
        <Field label="Name" value={name} onChange={setName} autoComplete="name" />
        <Field label="Email" value={email} onChange={setEmail} type="email" autoComplete="email" />
        <Field label="Password" value={password} onChange={setPassword} type="password" autoComplete="new-password" />
        <div>
          <div className="mb-2 flex justify-between text-xs text-slate-500"><span>Password strength</span><span>{strength}%</span></div>
          <Progress value={strength} />
        </div>
        <Field label="Confirm password" value={confirmPassword} onChange={setConfirmPassword} type="password" autoComplete="new-password" />
        {error ? <div className="rounded-md border border-rose-300/20 bg-rose-300/10 p-3 text-sm text-rose-100">{error}</div> : null}
        <Button className="w-full" type="submit" disabled={loading}>
          {loading ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <UserPlus className="h-4 w-4" />}
          {loading ? "Creating account" : "Create account"}
        </Button>
      </form>
      <p className="mt-6 text-center text-sm text-slate-400">
        Already have an account? <Link className="text-cyan-200 hover:text-cyan-100" href="/login">Sign in</Link>
      </p>
    </AuthShell>
  );
}

function Field({
  label,
  value,
  onChange,
  type = "text",
  autoComplete
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  autoComplete?: string;
}) {
  return (
    <label className="block">
      <span className="mb-2 block text-sm text-slate-300">{label}</span>
      <Input type={type} autoComplete={autoComplete} value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}
