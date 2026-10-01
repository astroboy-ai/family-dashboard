"use client";

import { ArrowRight, LoaderCircle, LockKeyhole } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import { demoMembers, demoSignIn, signIn } from "@/lib/api";

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
  const [selectedMemberId, setSelectedMemberId] = useState<string>("dad");
  const [pin, setPin] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [useEmailLogin, setUseEmailLogin] = useState(false);

  const selectedMember = useMemo(() => demoMembers.find((member) => member.id === selectedMemberId) ?? demoMembers[0], [selectedMemberId]);

  async function submitPin(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError("");
    try {
      await demoSignIn(selectedMember.id, pin);
      router.replace(searchParams.get("next") || "/");
      router.refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Incorrect PIN");
    } finally {
      setPending(false);
    }
  }

  async function submitEmail(event: React.FormEvent<HTMLFormElement>) {
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
      <div className="login-form-wrap">
        {!useEmailLogin ? (
          <form className="login-form" onSubmit={submitPin}>
            <span className="login-lock"><LockKeyhole size={20} /></span>
            <p className="eyebrow">WELCOME BACK</p>
            <h2>Who’s there?</h2>
            <div className="member-picker" aria-label="Choose family member">
              {demoMembers.map((member) => (
                <button type="button" key={member.id} className={`member-choice${selectedMemberId === member.id ? " selected" : ""}`} onClick={() => setSelectedMemberId(member.id)}>
                  <span className="member-avatar-large">{member.avatar}</span>
                  <span>{member.display_name}</span>
                </button>
              ))}
            </div>
            <div className="pin-box">
              <label className="form-field"><span>Enter {selectedMember.display_name}&apos;s PIN</span><input type="password" inputMode="numeric" autoComplete="one-time-code" value={pin} onChange={(event) => setPin(event.target.value)} placeholder="••••" maxLength={6} required /></label>
            </div>
            {error && <p className="inline-error" role="alert">{error}</p>}
            <button className="primary-button login-submit" type="submit" disabled={pending || pin.length < 4}>{pending ? <LoaderCircle className="spin" size={17} /> : null} Continue <ArrowRight size={17} /></button>
            <button type="button" className="text-link inline-link" onClick={() => setUseEmailLogin(true)}>Or sign in with email</button>
            <p className="login-footnote">Demo PINs: Dad 1234 · Mum 4321 · Emma 2468 · Guest 0000</p>
          </form>
        ) : (
          <form className="login-form" onSubmit={submitEmail}>
            <span className="login-lock"><LockKeyhole size={20} /></span>
            <p className="eyebrow">WELCOME BACK</p><h2>Sign in</h2><p className="login-copy">Use the email and password for your family account.</p>
            <label className="form-field"><span>Email</span><input type="email" autoComplete="username" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" /></label>
            <label className="form-field"><span>Password</span><input type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Your password" /></label>
            {error && <p className="inline-error" role="alert">{error}</p>}
            <button className="primary-button login-submit" type="submit" disabled={pending}>{pending ? <LoaderCircle className="spin" size={17} /> : null} Continue <ArrowRight size={17} /></button>
            <button type="button" className="text-link inline-link" onClick={() => setUseEmailLogin(false)}>Use family PIN</button>
            <p className="login-footnote">Family PIN sign-in is the default fast path; email access is kept for admin and setup flows.</p>
          </form>
        )}
      </div>
    </main>
  );
}