"use client";

import { AlertTriangle } from "lucide-react";
import { useEffect, useState } from "react";

export type ConfirmOptions = {
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
};

/**
 * Promise-based confirm dialog.
 *
 * Usage:
 *   const ok = await confirmDialog({ title: "Delete block?", message: "This cannot be undone." });
 *   if (!ok) return;
 *
 * Rendered once at the app root; callers await the user's choice.
 */
let resolveFn: ((ok: boolean) => void) | null = null;

export function confirmDialog(options: ConfirmOptions): Promise<boolean> {
  return new Promise((resolve) => {
    resolveFn = resolve;
    window.dispatchEvent(new CustomEvent("familyos:confirm", { detail: options }));
  });
}

export function ConfirmDialogHost() {
  const [opts, setOpts] = useState<ConfirmOptions | null>(null);

  useEffect(() => {
    function handler(event: Event) {
      setOpts((event as CustomEvent<ConfirmOptions>).detail);
    }
    window.addEventListener("familyos:confirm", handler);
    return () => window.removeEventListener("familyos:confirm", handler);
  }, []);

  function finish(ok: boolean) {
    resolveFn?.(ok);
    resolveFn = null;
    setOpts(null);
  }

  if (!opts) return null;

  return (
    <div className="confirm-overlay" role="dialog" aria-modal="true" aria-labelledby="confirm-title">
      <div className="confirm-dialog">
        <div className="confirm-icon"><AlertTriangle size={22} /></div>
        <h3 id="confirm-title">{opts.title}</h3>
        <p>{opts.message}</p>
        <div className="confirm-actions">
          <button className="secondary-button" onClick={() => finish(false)} autoFocus>
            {opts.cancelLabel ?? "Cancel"}
          </button>
          <button className="danger-button" onClick={() => finish(true)}>
            {opts.confirmLabel ?? "Delete"}
          </button>
        </div>
      </div>
    </div>
  );
}
