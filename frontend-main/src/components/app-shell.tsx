"use client";

import {
  Bell,
  ChevronDown,
  Command,
  Home,
  Menu,
  NotebookPen,
  Plus,
  Search,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { CommandPalette } from "@/components/command-palette";
import { PanelHost } from "@/components/panel-host";
import { ApiError, getActor, signOut, type Actor } from "@/lib/api";
import { navigation } from "@/lib/navigation";
import { usePanelStore } from "@/lib/panel-store";

function isActive(pathname: string, href: string) {
  return href === "/" ? pathname === href : pathname === href || pathname.startsWith(`${href}/`);
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [actor, setActor] = useState<Actor | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const [userOpen, setUserOpen] = useState(false);
  const { panels, open, closeTop } = usePanelStore();

  useEffect(() => {
    let active = true;
    getActor()
      .then((value) => active && setActor(value))
      .catch((reason: unknown) => {
        if (!active) return;
        setActor(null);
        if (reason instanceof ApiError && reason.status === 401) {
          router.replace(`/login?next=${encodeURIComponent(pathname)}`);
        }
      });
    return () => {
      active = false;
    };
  }, [pathname, router]);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const editing = target?.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target?.tagName ?? "");
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen(true);
      } else if (!editing && !event.metaKey && !event.ctrlKey && !event.altKey) {
        const key = event.key.toLowerCase();
        if (key === "c") open("capture");
        if (key === "w") open("whiteboard");
        if (key === "h") open("hermes");
        if (event.key === "Escape") {
          if (paletteOpen) setPaletteOpen(false);
          else closeTop();
        }
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [closeTop, open, paletteOpen]);

  const title = useMemo(() => {
    if (pathname === "/") return "Home";
    const entry = navigation.find((item) => isActive(pathname, item.href));
    return entry?.label ?? pathname.split("/").filter(Boolean).at(-1)?.replaceAll("-", " ") ?? "FamilyOS";
  }, [pathname]);

  async function handleSignOut() {
    try {
      await signOut();
    } finally {
      router.push("/login");
      router.refresh();
    }
  }

  return (
    <div className="app-frame">
      <aside className="sidebar" aria-label="Primary navigation">
        <Link className="brand-lockup" href="/" aria-label="FamilyOS home">
          <span className="brand-mark">F</span>
          <span className="brand-name">FamilyOS</span>
          <span className="brand-edition">HOME</span>
        </Link>

        <button className="capture-button" onClick={() => open("capture")}>
          <Plus size={18} strokeWidth={2.4} />
          <span>Capture</span>
          <kbd>C</kbd>
        </button>

        <nav className="nav-list">
          <div className="nav-label">Workspace</div>
          {navigation.slice(0, 13).map(({ href, label, icon: Icon }) => (
            <Link
              className={`nav-item${isActive(pathname, href) ? " nav-item-active" : ""}`}
              href={href}
              key={href}
            >
              <Icon size={18} strokeWidth={1.8} />
              <span>{label}</span>
              {label === "Notes" && <span className="nav-count">Inbox</span>}
            </Link>
          ))}
          <div className="nav-label nav-label-spaced">Manage</div>
          {navigation.slice(13).map(({ href, label, icon: Icon }) => (
            <Link
              className={`nav-item${isActive(pathname, href) ? " nav-item-active" : ""}`}
              href={href}
              key={href}
            >
              <Icon size={18} strokeWidth={1.8} />
              <span>{label}</span>
            </Link>
          ))}
        </nav>

        <div className="sidebar-bottom">
          <div className="household-switch">
            <span className="household-avatar">H</span>
            <span className="household-copy">
              <strong>Our Family</strong>
              <small>{actor?.timezone ?? "Family space"}</small>
            </span>
            <ChevronDown size={16} />
          </div>
          <button className="member-switch" onClick={() => setUserOpen((value) => !value)}>
            <span className="member-avatar">{actor?.display_name?.slice(0, 1) ?? "?"}</span>
            <span className="member-name">{actor?.display_name ?? "Sign in"}</span>
            <ChevronDown size={16} />
          </button>
          {userOpen && (
            <div className="user-menu">
              <div className="user-menu-meta">
                {actor ? `${actor.role} · ${actor.locale}` : "No active session"}
              </div>
              {actor ? (
                <button onClick={handleSignOut}>Sign out</button>
              ) : (
                <button onClick={() => router.push("/login")}>Sign in</button>
              )}
            </div>
          )}
        </div>
      </aside>

      <div className="app-column">
        <header className="topbar">
          <div className="mobile-brand">
            <span className="brand-mark">F</span>
            <span className="brand-name">FamilyOS</span>
          </div>
          <div className="topbar-title">{title}</div>
          <div className="topbar-actions">
            <button className="search-trigger" onClick={() => setPaletteOpen(true)}>
              <Search size={17} />
              <span>Search or ask…</span>
              <kbd><Command size={11} /> K</kbd>
            </button>
            <button className="icon-button notification-button" aria-label="Notifications" onClick={() => router.push("/notifications")}>
              <Bell size={19} />
              <span className="notification-dot" />
            </button>
            <button className="mobile-menu-button" aria-label="More navigation" onClick={() => setMoreOpen((value) => !value)}>
              {moreOpen ? <X size={20} /> : <Menu size={20} />}
            </button>
          </div>
        </header>

        {moreOpen && (
          <div className="mobile-more-menu">
            {navigation.slice(3).map(({ href, label, icon: Icon }) => (
              <Link href={href} key={href} onClick={() => setMoreOpen(false)}>
                <Icon size={17} /> {label}
              </Link>
            ))}
            <Link href="/login" onClick={() => setMoreOpen(false)}>Sign in / switch member</Link>
          </div>
        )}

        <div className="workspace-row">
          <main className="main-content" id="main-content">{children}</main>
          {panels.length > 0 && <PanelHost />}
        </div>
      </div>

      <nav className="mobile-tabs" aria-label="Mobile navigation">
        <Link href="/" className={isActive(pathname, "/") ? "mobile-tab-active" : ""}>
          <Home size={19} /> <span>Home</span>
        </Link>
        <Link href="/notes" className={isActive(pathname, "/notes") ? "mobile-tab-active" : ""}>
          <NotebookPen size={19} /> <span>Notes</span>
        </Link>
        <Link href="/search" className={isActive(pathname, "/search") ? "mobile-tab-active" : ""}>
          <Search size={19} /> <span>Search</span>
        </Link>
        <button className="mobile-capture" onClick={() => open("capture")} aria-label="Capture">
          <Plus size={21} />
        </button>
        <button onClick={() => setMoreOpen((value) => !value)}>
          <Menu size={19} /> <span>More</span>
        </button>
      </nav>

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </div>
  );
}