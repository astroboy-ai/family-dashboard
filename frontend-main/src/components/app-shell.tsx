"use client";

import {
  Bell,
  ChevronDown,
  Command,
  Home,
  Maximize,
  Menu,
  Minimize,
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
import { SessionExpiredNotice } from "@/components/session-expired-notice";
import { SessionExpiredError, getActor, signOut, type Actor } from "@/lib/api";
import { navigation } from "@/lib/navigation";
import { useNewNote } from "@/lib/new-note";
import { usePanelStore } from "@/lib/panel-store";

const notifications = [
  { id: 1, label: "Emma added a school reminder", time: "2m ago" },
  { id: 2, label: "Weekly chores are ready for review", time: "18m ago" },
  { id: 3, label: "A new transit update is available", time: "1h ago" },
];

function isActive(pathname: string, href: string) {
  return href === "/" ? pathname === href : pathname === href || pathname.startsWith(`${href}/`);
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [actor, setActor] = useState<Actor | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [userOpen, setUserOpen] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [theme, setTheme] = useState<"light" | "dark" | "midnight" | "forest" | "unicorn" | "pixel" | "system">("dark");
  const [density, setDensity] = useState<"comfortable" | "compact">("comfortable");
  const { panels, open, closeTop } = usePanelStore();
  const { startNewNote } = useNewNote();

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const applyTheme = () => {
      const resolved = theme === "system" ? (media.matches ? "dark" : "light") : theme;
      document.documentElement.dataset.theme = resolved;
      document.documentElement.style.colorScheme = resolved;
    };
    applyTheme();
    media.addEventListener("change", applyTheme);
    return () => media.removeEventListener("change", applyTheme);
  }, [theme]);

  useEffect(() => {
    const storedTheme = window.localStorage.getItem("familyos-theme") as "light" | "dark" | "midnight" | "forest" | "unicorn" | "pixel" | "system" | null;
    const storedDensity = window.localStorage.getItem("familyos-density") as "comfortable" | "compact" | null;
    if (storedTheme) setTheme(storedTheme);
    if (storedDensity) setDensity(storedDensity);
  }, []);

  useEffect(() => {
    window.localStorage.setItem("familyos-theme", theme);
  }, [theme]);

  useEffect(() => {
    window.localStorage.setItem("familyos-density", density);
    document.body.dataset.density = density;
  }, [density]);

  useEffect(() => {
    let active = true;
    getActor()
      .then((value) => active && setActor(value))
      .catch((reason: unknown) => {
        if (!active) return;
        setActor(null);
        // Only bounce to login when the session is genuinely unrecoverable.
        // A bare 401 is NOT enough: the API layer already tried a silent
        // refresh, and the access token aging out is the normal case that must
        // stay invisible. SessionExpiredError is thrown only after that refresh
        // actually failed, and the modal offers to copy unsaved work first.
        if (reason instanceof SessionExpiredError) {
          router.replace(`/login?next=${encodeURIComponent(pathname)}`);
        }
      });
    return () => {
      active = false;
    };
  }, [pathname, router]);

  useEffect(() => {
    // Track the real browser state rather than our own flag, so exiting with
    // Esc or F11 keeps the icon honest.
    const sync = () => setIsFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", sync);
    sync();
    return () => document.removeEventListener("fullscreenchange", sync);
  }, []);

  async function toggleFullscreen() {
    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen();
      } else {
        await document.documentElement.requestFullscreen();
      }
    } catch {
      // Some embedded webviews refuse the request; leave the state untouched.
    }
  }

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const editing = target?.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target?.tagName ?? "");
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen(true);
      } else if (!editing && !event.metaKey && !event.ctrlKey && !event.altKey) {
        const key = event.key.toLowerCase();
        if (key === "c") void startNewNote();
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

        <button className="capture-button" onClick={() => void startNewNote()}>
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
                <>
                  <button onClick={() => setUserOpen(false)} className="user-menu-button">Profile</button>
                  <button onClick={() => setUserOpen(false)} className="user-menu-button">Switch member</button>
                  <div className="user-menu-section">
                    <span>Theme</span>
                    <div className="theme-grid">
                      <button className={theme === "light" ? "selected" : ""} onClick={() => setTheme("light")}>☀️ Light</button>
                      <button className={theme === "dark" ? "selected" : ""} onClick={() => setTheme("dark")}>🌙 Dark</button>
                      <button className={theme === "midnight" ? "selected" : ""} onClick={() => setTheme("midnight")}>🔵 Midnight</button>
                      <button className={theme === "forest" ? "selected" : ""} onClick={() => setTheme("forest")}>🌲 Forest</button>
                      <button className={theme === "unicorn" ? "selected" : ""} onClick={() => setTheme("unicorn")}>🦄 Unicorn</button>
                      <button className={theme === "pixel" ? "selected" : ""} onClick={() => setTheme("pixel")}>👾 Pixel</button>
                      <button className={theme === "system" ? "selected" : ""} onClick={() => setTheme("system")}>⚙️ Auto</button>
                    </div>
                  </div>
                  <div className="user-menu-section">
                    <span>Density</span>
                    <div className="segmented-control compact-control">
                      <button className={density === "comfortable" ? "selected" : ""} onClick={() => setDensity("comfortable")}>Comfort</button>
                      <button className={density === "compact" ? "selected" : ""} onClick={() => setDensity("compact")}>Compact</button>
                    </div>
                  </div>
                  <button onClick={handleSignOut} className="user-menu-button danger">Sign out</button>
                </>
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
            <button
              className="icon-button fullscreen-button"
              onClick={() => void toggleFullscreen()}
              aria-label={isFullscreen ? "Exit fullscreen" : "Enter fullscreen"}
              title={isFullscreen ? "Exit fullscreen" : "Fullscreen"}
            >
              {isFullscreen ? <Minimize size={19} /> : <Maximize size={19} />}
            </button>
            <div className="notification-wrap">
              <button className="icon-button notification-button" aria-label="Notifications" onClick={() => setNotificationsOpen((value) => !value)}>
                <Bell size={19} />
                <span className="notification-dot" />
              </button>
              {notificationsOpen && (
                <div className="notification-popover" role="menu" aria-label="Notifications">
                  <div className="notification-header">
                    <strong>Notifications</strong>
                    <button className="text-button" onClick={() => setNotificationsOpen(false)}>Close</button>
                  </div>
                  {notifications.map((item) => (
                    <div className="notification-item" key={item.id}>
                      <span className="notification-bullet" />
                      <div>
                        <strong>{item.label}</strong>
                        <small>{item.time}</small>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <button className="mobile-menu-button" aria-label="More navigation" onClick={() => setMoreOpen((value) => !value)}>
              {moreOpen ? <X size={20} /> : <Menu size={20} />}
            </button>
          </div>
        </header>

        {moreOpen && (
          <>
            <div className="mobile-more-menu-overlay" onClick={() => setMoreOpen(false)} />
            <div className="mobile-more-menu">
              {navigation.slice(3).map(({ href, label, icon: Icon }) => (
                <Link href={href} key={href} onClick={() => setMoreOpen(false)}>
                  <Icon size={17} /> {label}
                </Link>
              ))}
              <div className="mobile-menu-section">
                <span>Theme</span>
                <div className="theme-grid">
                  <button className={theme === "light" ? "selected" : ""} onClick={() => setTheme("light")}>☀️ Light</button>
                  <button className={theme === "dark" ? "selected" : ""} onClick={() => setTheme("dark")}>🌙 Dark</button>
                  <button className={theme === "midnight" ? "selected" : ""} onClick={() => setTheme("midnight")}>🔵 Midnight</button>
                  <button className={theme === "forest" ? "selected" : ""} onClick={() => setTheme("forest")}>🌲 Forest</button>
                  <button className={theme === "unicorn" ? "selected" : ""} onClick={() => setTheme("unicorn")}>🦄 Unicorn</button>
                  <button className={theme === "pixel" ? "selected" : ""} onClick={() => setTheme("pixel")}>👾 Pixel</button>
                  <button className={theme === "system" ? "selected" : ""} onClick={() => setTheme("system")}>⚙️ Auto</button>
                </div>
              </div>
              <Link href="/login" onClick={() => setMoreOpen(false)}>Sign in / switch member</Link>
            </div>
          </>
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
        <button className="mobile-capture" onClick={() => void startNewNote()} aria-label="New note">
          <Plus size={21} />
        </button>
        <button onClick={() => setMoreOpen((value) => !value)}>
          <Menu size={19} /> <span>More</span>
        </button>
      </nav>

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
      <SessionExpiredNotice />
    </div>
  );
}