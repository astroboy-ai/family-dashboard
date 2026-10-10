"use client";

import { ArrowLeft, ArrowRight, LoaderCircle, LockKeyhole } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { completeSetup, getSetupStatus } from "@/lib/api";

export default function SetupPage() {
  const router = useRouter();
  const [available, setAvailable] = useState<boolean | null>(null);
  const [step, setStep] = useState<1 | 2>(1);
  const [householdName, setHouseholdName] = useState("");
  const [timezone, setTimezone] = useState("Asia/Hong_Kong");
  const [locale, setLocale] = useState("en");
  const [weekStartsOn, setWeekStartsOn] = useState("monday");
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [pin, setPin] = useState("");
  const [aiProvider, setAiProvider] = useState<"none" | "ollama" | "openai">("none");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    getSetupStatus()
      .then(({ available: canSetup }) => {
        if (!active) return;
        setAvailable(canSetup);
        if (!canSetup) router.replace("/login");
      })
      .catch((reason: unknown) => {
        if (active) {
          setAvailable(false);
          setError(reason instanceof Error ? reason.message : "Unable to check setup status.");
        }
      });
    return () => { active = false; };
  }, [router]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError("");
    try {
      await completeSetup({
        household_name: householdName.trim(),
        timezone,
        locale: locale.trim(),
        week_starts_on: weekStartsOn,
        display_name: displayName.trim(),
        email: email.trim(),
        password,
        pin,
        ai_provider: aiProvider,
      });
      router.replace("/");
      router.refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to complete setup.");
    } finally {
      setPending(false);
    }
  }

  if (available === null || !available) {
    return (
      <main className="login-screen">
        <div className="login-aside"><div className="login-brand"><span className="brand-mark">F</span><span>FamilyOS</span></div><div className="login-aside-copy"><p className="eyebrow">FIRST RUN</p><h1>Make this space yours.</h1><p>Create your household and the first parent account.</p></div></div>
        <div className="login-form-wrap"><div className="login-form"><span className="login-lock"><LockKeyhole size={20} /></span><h2>{error ? "Setup unavailable" : "Checking setup"}</h2>{error ? <p className="inline-error" role="alert">{error}</p> : <p className="login-copy">One moment…</p>}</div></div>
      </main>
    );
  }

  return (
    <main className="login-screen">
      <div className="login-aside">
        <div className="login-brand"><span className="brand-mark">F</span><span>FamilyOS</span></div>
        <div className="login-aside-copy"><p className="eyebrow">FIRST RUN · STEP {step} OF 2</p><h1>{step === 1 ? "Start with home." : "Create your parent account."}</h1><p>{step === 1 ? "Set the household defaults that keep dates and routines in sync." : "This account owns the household and can manage family access."}</p></div>
        <div className="login-aside-foot">Private by design <span /> Built for home</div>
      </div>
      <div className="login-form-wrap">
        <form className="login-form" onSubmit={step === 1 ? (event) => { event.preventDefault(); setError(""); setStep(2); } : submit}>
          <span className="login-lock"><LockKeyhole size={20} /></span>
          <p className="eyebrow">HOUSEHOLD SETUP</p>
          <h2>{step === 1 ? "Your household" : "First parent"}</h2>
          {step === 1 ? (
            <>
              <label className="form-field"><span>Household name</span><input autoFocus value={householdName} onChange={(event) => setHouseholdName(event.target.value)} maxLength={160} required /></label>
              <label className="form-field"><span>Timezone</span><input value={timezone} onChange={(event) => setTimezone(event.target.value)} placeholder="Asia/Hong_Kong" maxLength={64} required /></label>
              <label className="form-field"><span>Language and locale</span><input value={locale} onChange={(event) => setLocale(event.target.value)} maxLength={16} required /></label>
              <label className="form-field"><span>Week starts on</span><select value={weekStartsOn} onChange={(event) => setWeekStartsOn(event.target.value)}><option value="monday">Monday</option><option value="sunday">Sunday</option><option value="saturday">Saturday</option></select></label>
              <button className="primary-button login-submit" type="submit">Continue <ArrowRight size={17} /></button>
            </>
          ) : (
            <>
              <label className="form-field"><span>Your display name</span><input autoFocus value={displayName} onChange={(event) => setDisplayName(event.target.value)} maxLength={120} required /></label>
              <label className="form-field"><span>Email</span><input type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} maxLength={320} required /></label>
              <label className="form-field"><span>Password (at least 12 characters)</span><input type="password" autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} minLength={12} maxLength={1024} required /></label>
              <label className="form-field"><span>Family PIN (4 to 6 digits)</span><input type="password" inputMode="numeric" autoComplete="new-password" value={pin} onChange={(event) => setPin(event.target.value.replace(/\D/g, "").slice(0, 6))} minLength={4} maxLength={6} required /></label>
              <label className="form-field"><span>AI provider</span><select value={aiProvider} onChange={(event) => setAiProvider(event.target.value as typeof aiProvider)}><option value="none">None</option><option value="ollama">Ollama (local)</option><option value="openai">OpenAI</option></select></label>
              {error && <p className="inline-error" role="alert">{error}</p>}
              <div className="inline-actions"><button className="secondary-button" type="button" onClick={() => setStep(1)} disabled={pending}><ArrowLeft size={16} /> Back</button><button className="primary-button login-submit" type="submit" disabled={pending || pin.length < 4 || password.length < 12}>{pending ? <LoaderCircle className="spin" size={17} /> : null} Create household <ArrowRight size={17} /></button></div>
            </>
          )}
        </form>
      </div>
    </main>
  );
}