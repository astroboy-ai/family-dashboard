"use client";

import { ArrowRight, LoaderCircle, LockKeyhole } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { signIn } from "@/lib/api";

export default function LoginPage() {
  return (
    <Suspense fallback={<main className="login-screen"><div className="login-aside"><div className="login-brand"><span className="brand-mark">F</span><span>FamilyOS</span></div><div className="login-aside-copy"><p className="eyebrow">YOUR FAMILY, IN SYNC</p><h1>Keep the important things close.</h1><p>A shared place for notes, plans, and the little details you want to find later.</p></div><div className="login-aside-foot">Private by design <span /> Built for home</div></div><div className="login-form-wrap"><div className="login-form"><span className="login-lock"><LockKeyhole size={20} /></span><p className="eyebrow">WELCOME BACK</p><h2>Loading</h2></div></div></main>}>
      <LoginPageContent />
    </Suspense>
  );
}

function LoginPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError("");
    try {
      await signIn(email, password);
      router.replace(searchParams.get("next") || "/");
      router.refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Sign in failed");
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="login-screen">
      <div className="login-aside"><div className="login-brand"><span className="brand-mark">F</span><span>FamilyOS</span></div><div className="login-aside-copy"><p className="eyebrow">YOUR FAMILY, IN SYNC</p><h1>Keep the important things close.</h1><p>A shared place for notes, plans, and the little details you want to find later.</p></div><div className="login-aside-foot">Private by design <span /> Built for home</div></div>
      <div className="login-form-wrap"><form className="login-form" onSubmit={submit}>
        <span className="login-lock"><LockKeyhole size={20} /></span>
        <p className="eyebrow">WELCOME BACK</p><h2>Sign in</h2><p className="login-copy">Use the email and password for your family account.</p>
        <label className="form-field"><span>Email</span><input type="email" autoComplete="username" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" /></label>
        <label className="form-field"><span>Password</span><input type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Your password" /></label>
        {error && <p className="inline-error" role="alert">{error}</p>}
        <button className="primary-button login-submit" type="submit" disabled={pending}>{pending ? <LoaderCircle className="spin" size={17} /> : null} Continue <ArrowRight size={17} /></button>
        <p className="login-footnote">Family PIN sign-in and first-run setup are enabled after their backend endpoints are available.</p>
      </form></div>
    </main>
  );
}