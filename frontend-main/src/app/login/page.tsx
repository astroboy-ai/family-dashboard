"use client";

import { ArrowRight, LoaderCircle, LockKeyhole } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { listLoginMembers, signIn, signInWithPin, type LoginMember } from "@/lib/api";

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
  const [members, setMembers] = useState<LoginMember[]>([]);
  const [membersLoading, setMembersLoading] = useState(true);
  const [selectedMemberId, setSelectedMemberId] = useState("");
  const [pin, setPin] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [useEmailLogin, setUseEmailLogin] = useState(false);

  const selectedMember = members.find((member) => member.id === selectedMemberId) ?? members[0];

  useEffect(() => {
    let active = true;
    listLoginMembers()
      .then((value) => {
        if (!active) return;
        setMembers(value);
        setSelectedMemberId(value[0]?.id ?? "");
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "Unable to load family members.");
      })
      .finally(() => active && setMembersLoading(false));
    return () => { active = false; };
  }, []);

  async function submitPin(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError("");
    try {
      if (!selectedMember) throw new Error("No family member is available for PIN sign-in.");
      await signInWithPin(selectedMember.id, pin);
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
            {membersLoading ? <p className="login-copy">Loading family members…</p> : members.length > 0 ? (
              <>
                <div className="member-picker" aria-label="Choose family member">
                  {members.map((member) => (
                    <button type="button" key={member.id} className={`member-choice${selectedMember?.id === member.id ? " selected" : ""}`} onClick={() => setSelectedMemberId(member.id)}>
                      <span className="member-avatar-large">{member.display_name.slice(0, 1).toUpperCase()}</span>
                      <span>{member.display_name}</span>
                    </button>
                  ))}
                </div>
                {selectedMember?.has_pin && <div className="pin-box">
                  <label className="form-field"><span>Enter {selectedMember.display_name}&apos;s PIN</span><input type="password" inputMode="numeric" autoComplete="one-time-code" value={pin} onChange={(event) => setPin(event.target.value.replace(/\D/g, "").slice(0, 6))} placeholder="••••" maxLength={6} required /></label>
                </div>}
                {!selectedMember?.has_pin && <p className="login-copy">This family member does not have a PIN yet. Sign in with an administrator account to set one.</p>}
              </>
            ) : <p className="login-copy">No family members are set up yet.</p>}
            {error && <p className="inline-error" role="alert">{error}</p>}
            <button className="primary-button login-submit" type="submit" disabled={pending || membersLoading || !selectedMember?.has_pin || pin.length < 4}>{pending ? <LoaderCircle className="spin" size={17} /> : null} Continue <ArrowRight size={17} /></button>
            <button type="button" className="text-link inline-link" onClick={() => setUseEmailLogin(true)}>Or sign in with email</button>
            {!membersLoading && members.length === 0 && <Link className="text-link inline-link" href="/setup">Set up FamilyOS</Link>}
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