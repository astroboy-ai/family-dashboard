"use client";

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { AppShell } from "@/components/app-shell";
import { ConfirmDialogHost } from "@/components/confirm-dialog";

export function AppRoot({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  if (pathname === "/login" || pathname === "/setup") return children;
  return (
    <AppShell>
      {children}
      <ConfirmDialogHost />
    </AppShell>
  );
}