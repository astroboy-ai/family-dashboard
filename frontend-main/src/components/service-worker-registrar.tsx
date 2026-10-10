"use client";

import { useEffect } from "react";

/**
 * Registers the service worker so Chrome offers "Install as app".
 *
 * Chrome will not consider the app installable without a service worker that
 * handles fetch, so this is what turns the manifest into an install prompt.
 * Registration is skipped in development: a cached shell while you are editing
 * is confusing, and Chrome ignores localhost anyway.
 */
export function ServiceWorkerRegistrar() {
  useEffect(() => {
    if (process.env.NODE_ENV !== "production") return;
    if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return;

    // Register after load so it never competes with the first paint.
    function register() {
      navigator.serviceWorker.register("/sw.js").catch(() => {
        /* Registration failure just means no install prompt; the app still works. */
      });
    }

    if (document.readyState === "complete") register();
    else {
      window.addEventListener("load", register);
      return () => window.removeEventListener("load", register);
    }
  }, []);

  return null;
}
