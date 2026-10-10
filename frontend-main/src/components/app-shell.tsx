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
  Calendar,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { CommandPalette } from "@/components/command-palette";
import { PanelHost } from "@/components/panel-host";
import { SessionExpiredNotice } from "@/components/session-expired-notice";
import { SessionExpiredError, getActor, getMyPreferences, signOut, updateMyPreferences, listNotifications, getUnreadCount, markAllNotificationsRead, type Actor, type Notification } from "@/lib/api";
import { navigation } from "@/lib/navigation";
import { useNewNote } from "@/lib/new-note";
import { usePanelStore } from "@/lib/panel-store";

function timeAgo(iso: string): string {
  const then = new Date(iso).getTime();
  const now = Date.now();
  const diff = Math.max(0, now - then);
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function isActive(pathname: string, href: string) {
  return href === "/" ? pathname === href : pathname === href || pathname.startsWith(`${href}/`);
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [actor, setActor] = useState<Actor | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const [dateOpen, setDateOpen] = useState(false);
  const [now, setNow] = useState(new Date());
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [hideTopbar, setHideTopbar] = useState(false);
  const [userOpen, setUserOpen] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [theme, setTheme] = useState<"light" | "dark" | "midnight" | "forest" | "unicorn" | "pixel" | "system">("dark");
  const [density, setDensity] = useState<"comfortable" | "compact">("comfortable");
  const { panels, open, closeTop } = usePanelStore();
  const { startNewNote } = useNewNote();

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

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
    let active = true;
    getMyPreferences()
      .then(() => {})
      .catch(() => {
        // Preferences are optional; defaults are fine when unavailable.
      });
    return () => {
      active = false;
    };
  }, []);

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
    if (!actor) return;
    let active = true;
    const fetchNotifications = () => {
      listNotifications(false, 20)
        .then((items) => active && setNotifications(items))
        .catch(() => { /* ignore */ });
      getUnreadCount()
        .then(({ count }) => active && setUnreadCount(count))
        .catch(() => { /* ignore */ });
    };
    fetchNotifications();
    const interval = setInterval(fetchNotifications, 60000);
    return () => { active = false; clearInterval(interval); };
  }, [actor]);

  useEffect(() => {
    // Track the real browser state rather than our own flag, so exiting with
    // Esc or F11 keeps the icon honest.
    const sync = () => {
      const fs = Boolean(document.fullscreenElement);
      setIsFullscreen(fs);
      setHideTopbar(fs);
    };
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

  const formatDate = (d: Date) =>
    d.toLocaleDateString("en-HK", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  const formatTime = (d: Date) =>
    d.toLocaleTimeString("en-HK", { hour: "2-digit", minute: "2-digit", second: "2-digit" });

  return (
    <div className="app-frame">
      {/* Sidebar drawer overlay */}
      {moreOpen && (
        <div className="sidebar-overlay" onClick={() => setMoreOpen(false)} />
      )}

      {/* Sidebar drawer */}
      <aside className={`sidebar${moreOpen ? " sidebar-open" : ""}`} aria-label="Primary navigation">
        <div className="sidebar-header">
          <Link className="brand-lockup" href="/" aria-label="FamilyOS home" onClick={() => setMoreOpen(false)}>
            <span className="brand-mark">F</span>
            <span className="brand-name">FamilyOS</span>
            <span className="brand-edition">HOME</span>
          </Link>
          <button className="sidebar-close" onClick={() => setMoreOpen(false)} aria-label="Close menu">
            <X size={20} />
          </button>
        </div>

        <button className="capture-button" onClick={() => { setMoreOpen(false); void startNewNote(); }}>
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
              onClick={() => setMoreOpen(false)}
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
              onClick={() => setMoreOpen(false)}
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
        <header className={`topbar${hideTopbar ? " topbar-hidden" : ""}`}>
          <button className="hamburger-button" aria-label="Open menu" onClick={() => setMoreOpen(true)}>
            <Menu size={20} />
          </button>
          <div className="mobile-brand">
            <span className="brand-mark">F</span>
            <span className="brand-name">FamilyOS</span>
          </div>
          <div className="topbar-title">{title}</div>
          <div className="topbar-datetime">
            <span className="topbar-date">{formatDate(now)}</span>
            <span className="topbar-time">{formatTime(now)}</span>
          </div>
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
                {unreadCount > 0 && <span className="notification-badge">{unreadCount > 99 ? "99+" : unreadCount}</span>}
              </button>
              {notificationsOpen && (
                <div className="notification-popover" role="menu" aria-label="Notifications">
                  <div className="notification-header">
                    <strong>Notifications</strong>
                    <div className="inline-actions">
                      {unreadCount > 0 && (
                        <button className="text-button" onClick={() => void markAllNotificationsRead().then(() => { setUnreadCount(0); setNotifications((prev) => prev.map((n) => ({ ...n, read_at: new Date().toISOString() }))); })}>Mark all read</button>
                      )}
                      <button className="text-button" onClick={() => setNotificationsOpen(false)}>Close</button>
                    </div>
                  </div>
                  {notifications.map((item) => (
                    <div className="notification-item" key={item.id}>
                      <span className="notification-bullet" />
                      <div>
                        <strong>{item.title}</strong>
                        <small>{timeAgo(item.created_at)}</small>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </header>

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
        <button onClick={() => setMoreOpen(true)}>
          <Menu size={19} /> <span>More</span>
        </button>
      </nav>

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
      <SessionExpiredNotice />
    </div>
  );
}