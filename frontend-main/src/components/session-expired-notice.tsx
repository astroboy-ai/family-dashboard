"use client";

import { AlertTriangle, ClipboardCopy, LogIn, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { onSessionExpired } from "@/lib/api";

/**
 * Non-blocking "your session ended" prompt.
 *
 * Deliberately does NOT redirect: the user may have unsaved writing on screen.
 * It offers a one-click copy of the visible note text, then a link to log in.
 * Refreshing is handled silently in the background by the API layer, so this
 * only appears when the refresh token itself is gone.
 */
export function SessionExpiredNotice() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => onSessionExpired(() => setOpen(true)), []);

  if (!open) return null;

  async function copyVisibleText() {
    // Grab what the user can currently see, so nothing is lost on the way out.
    const main = document.querySelector("main") ?? document.body;
    const text = (main as HTMLElement).innerText?.trim() ?? "";
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  function goToLogin() {
    const next = window.location.pathname + window.location.search;
    router.push(`/login?next=${encodeURIComponent(next)}`);
  }

  return (
    <div className="session-overlay" role="alertdialog" aria-modal="true" aria-labelledby="session-title">
      <div className="session-dialog">
        <div className="session-head">
          <span className="session-icon"><AlertTriangle size={18} /></span>
          <div>
            <h2 id="session-title">Session expired</h2>
            <p>You have been signed out. Anything unsaved is still on this page.</p>
          </div>
          <button className="icon-button" onClick={() => setOpen(false)} aria-label="Dismiss">
            <X size={18} />
          </button>
        </div>
        <div className="session-actions">
          <button type="button" className="secondary-button" onClick={() => void copyVisibleText()}>
            <ClipboardCopy size={16} />
            {copied ? "Copied" : "Copy page text"}
          </button>
          <button type="button" className="primary-button" onClick={goToLogin}>
            <LogIn size={16} />
            Go to login
          </button>
        </div>
        <p className="session-hint">
          Tip: copy your work first — signing in reloads the page.
        </p>
      </div>
    </div>
  );
}
