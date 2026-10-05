"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  Plus,
  Trash2,
  RefreshCw,
  Shield,
  Eye,
  Edit3,
  Crown,
  Users,
  Layout,
  Check,
  X,
} from "lucide-react";
import {
  listCalendarAccounts,
  listCalendars,
  listCalendarPermissions,
  listCalendarViews,
  createCalendarPermission,
  deleteCalendarPermission,
  createCalendarView,
  deleteCalendarView,
  getCalendarOAuthUrl,
  calendarOAuthCallback,
  syncCalendars,
  type CalendarAccount,
  type Calendar,
  type CalendarPermission,
  type CalendarView,
} from "@/lib/api";

const LEVEL_ICONS = {
  view: Eye,
  edit: Edit3,
  manage: Shield,
  admin: Crown,
};

const LEVEL_COLORS = {
  view: "bg-blue-500",
  edit: "bg-green-500",
  manage: "bg-orange-500",
  admin: "bg-red-500",
};

export default function CalendarSettingsPage() {
  const router = useRouter();
  const [accounts, setAccounts] = useState<CalendarAccount[]>([]);
  const [calendars, setCalendars] = useState<Calendar[]>([]);
  const [permissions, setPermissions] = useState<CalendarPermission[]>([]);
  const [views, setViews] = useState<CalendarView[]>([]);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [showAddAccount, setShowAddAccount] = useState(false);
  const [showAddPermission, setShowAddPermission] = useState(false);
  const [showAddView, setShowAddView] = useState(false);
  const [newPermission, setNewPermission] = useState<{ calendar_id: string; member_id: string; level: "view" | "edit" | "manage" | "admin" }>({ calendar_id: "", member_id: "", level: "view" });
  const [newView, setNewView] = useState<{ name: string; calendar_ids: string[]; layout: "month" | "week" | "day" | "agenda" }>({ name: "", calendar_ids: [], layout: "month" });

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [accData, calData, permData, viewData] = await Promise.all([
        listCalendarAccounts(),
        listCalendars(),
        listCalendarPermissions(),
        listCalendarViews(),
      ]);
      setAccounts(accData);
      setCalendars(calData);
      setPermissions(permData);
      setViews(viewData);
    } catch (err) {
      console.error("Failed to fetch calendar settings:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleSync = async () => {
    setSyncing(true);
    try {
      await syncCalendars();
      await fetchData();
    } catch (err) {
      console.error("Sync failed:", err);
    } finally {
      setSyncing(false);
    }
  };

  const handleAddAccount = async () => {
    try {
      const { authorize_url } = await getCalendarOAuthUrl();
      // Store return URL for OAuth callback
      sessionStorage.setItem("calendar_oauth_return", "/calendar/settings");
      window.location.href = authorize_url;
    } catch (err) {
      console.error("Failed to get OAuth URL:", err);
    }
  };

  const handleOAuthCallback = async () => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get("code");
    const state = params.get("state");
    if (code && state) {
      try {
        await calendarOAuthCallback(code, state);
        // Clean URL
        window.history.replaceState({}, "", "/calendar/settings");
        await fetchData();
      } catch (err) {
        console.error("OAuth callback failed:", err);
      }
    }
  };

  useEffect(() => {
    handleOAuthCallback();
  }, []);

  const handleCreatePermission = async () => {
    if (!newPermission.calendar_id || !newPermission.member_id) return;
    try {
      await createCalendarPermission(newPermission.calendar_id, newPermission.member_id, newPermission.level);
      setShowAddPermission(false);
      setNewPermission({ calendar_id: "", member_id: "", level: "view" });
      await fetchData();
    } catch (err) {
      console.error("Failed to create permission:", err);
    }
  };

  const handleDeletePermission = async (id: string) => {
    try {
      await deleteCalendarPermission(id);
      await fetchData();
    } catch (err) {
      console.error("Failed to delete permission:", err);
    }
  };

  const handleCreateView = async () => {
    if (!newView.name) return;
    try {
      await createCalendarView(newView);
      setShowAddView(false);
      setNewView({ name: "", calendar_ids: [], layout: "month" });
      await fetchData();
    } catch (err) {
      console.error("Failed to create view:", err);
    }
  };

  const handleDeleteView = async (id: string) => {
    try {
      await deleteCalendarView(id);
      await fetchData();
    } catch (err) {
      console.error("Failed to delete view:", err);
    }
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="animate-pulse text-[var(--muted)]">Loading settings...</div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col bg-[var(--background)]">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-[var(--border)] px-4 py-3">
        <div className="flex items-center gap-3">
          <button onClick={() => router.push("/calendar")} className="rounded-lg p-2 hover:bg-[var(--muted)]">
            <ArrowLeft size={18} />
          </button>
          <h1 className="text-lg font-semibold text-[var(--foreground)]">Calendar Settings</h1>
        </div>
        <button onClick={handleSync} disabled={syncing} className="flex items-center gap-2 rounded-lg border border-[var(--border)] px-3 py-2 text-sm">
          <RefreshCw size={14} className={syncing ? "animate-spin" : ""} />
          Sync
        </button>
      </div>

      <div className="flex-1 overflow-auto p-4">
        <div className="mx-auto max-w-2xl space-y-6">
          {/* Google Accounts */}
          <section>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-[var(--foreground)]">Google Accounts</h2>
              <button
                onClick={() => setShowAddAccount(true)}
                className="flex items-center gap-1.5 rounded-lg bg-[var(--primary)] px-3 py-1.5 text-xs font-medium text-white"
              >
                <Plus size={14} />
                Add Account
              </button>
            </div>
            <div className="space-y-2">
              {accounts.length === 0 && (
                <div className="rounded-lg border border-dashed border-[var(--border)] p-4 text-center text-sm text-[var(--muted)]">
                  No Google accounts connected. Add one to sync your calendars.
                </div>
              )}
              {accounts.map((acc) => (
                <div key={acc.id} className="flex items-center justify-between rounded-lg border border-[var(--border)] p-3">
                  <div>
                    <div className="text-sm font-medium">{acc.email}</div>
                    <div className="text-xs text-[var(--muted)]">
                      {acc.is_active ? "Active" : "Inactive"} · Added {new Date(acc.created_at).toLocaleDateString()}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`h-2 w-2 rounded-full ${acc.is_active ? "bg-green-500" : "bg-gray-400"}`} />
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* Calendars */}
          <section>
            <h2 className="mb-3 text-sm font-semibold text-[var(--foreground)]">Calendars</h2>
            <div className="space-y-2">
              {calendars.length === 0 && (
                <div className="rounded-lg border border-dashed border-[var(--border)] p-4 text-center text-sm text-[var(--muted)]">
                  No calendars synced yet. Connect a Google account and sync.
                </div>
              )}
              {calendars.map((cal) => (
                <div key={cal.id} className="flex items-center justify-between rounded-lg border border-[var(--border)] p-3">
                  <div className="flex items-center gap-3">
                    <div className="h-3 w-3 rounded-full" style={{ backgroundColor: cal.color || "#6366f1" }} />
                    <div>
                      <div className="text-sm font-medium">{cal.name}</div>
                      {cal.description && <div className="text-xs text-[var(--muted)]">{cal.description}</div>}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {cal.is_primary && (
                      <span className="rounded bg-[var(--primary)] px-1.5 py-0.5 text-[10px] font-medium text-white">Primary</span>
                    )}
                    <span className="text-xs text-[var(--muted)]">
                      {cal.last_synced_at ? `Synced ${new Date(cal.last_synced_at).toLocaleDateString()}` : "Not synced"}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* Permissions */}
          <section>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-[var(--foreground)]">Permissions</h2>
              <button
                onClick={() => setShowAddPermission(true)}
                className="flex items-center gap-1.5 rounded-lg border border-[var(--border)] px-3 py-1.5 text-xs font-medium"
              >
                <Plus size={14} />
                Add Permission
              </button>
            </div>
            <div className="space-y-2">
              {permissions.length === 0 && (
                <div className="rounded-lg border border-dashed border-[var(--border)] p-4 text-center text-sm text-[var(--muted)]">
                  No permissions set. All household members can view all calendars.
                </div>
              )}
              {permissions.map((perm) => {
                const Icon = LEVEL_ICONS[perm.level];
                const cal = calendars.find((c) => c.id === perm.calendar_id);
                return (
                  <div key={perm.id} className="flex items-center justify-between rounded-lg border border-[var(--border)] p-3">
                    <div className="flex items-center gap-3">
                      <div className={`flex h-8 w-8 items-center justify-center rounded-lg text-white ${LEVEL_COLORS[perm.level]}`}>
                        <Icon size={14} />
                      </div>
                      <div>
                        <div className="text-sm font-medium">{cal?.name || "Unknown Calendar"}</div>
                        <div className="text-xs text-[var(--muted)]">
                          Member {perm.member_id.slice(0, 8)}... · {perm.level}
                        </div>
                      </div>
                    </div>
                    <button onClick={() => handleDeletePermission(perm.id)} className="rounded-lg p-2 hover:bg-[var(--muted)]">
                      <Trash2 size={14} className="text-[var(--muted)]" />
                    </button>
                  </div>
                );
              })}
            </div>
          </section>

          {/* Views */}
          <section>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-semibold text-[var(--foreground)]">Views</h2>
              <button
                onClick={() => setShowAddView(true)}
                className="flex items-center gap-1.5 rounded-lg border border-[var(--border)] px-3 py-1.5 text-xs font-medium"
              >
                <Plus size={14} />
                Add View
              </button>
            </div>
            <div className="space-y-2">
              {views.length === 0 && (
                <div className="rounded-lg border border-dashed border-[var(--border)] p-4 text-center text-sm text-[var(--muted)]">
                  No views configured. Create one for each device/dashboard.
                </div>
              )}
              {views.map((view) => (
                <div key={view.id} className="flex items-center justify-between rounded-lg border border-[var(--border)] p-3">
                  <div className="flex items-center gap-3">
                    <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--muted)]">
                      <Layout size={14} />
                    </div>
                    <div>
                      <div className="text-sm font-medium">{view.name}</div>
                      <div className="text-xs text-[var(--muted)]">
                        {view.calendar_ids.length} calendar{view.calendar_ids.length !== 1 ? "s" : ""} · {view.layout}
                        {view.is_default && " · Default"}
                      </div>
                    </div>
                  </div>
                  <button onClick={() => handleDeleteView(view.id)} className="rounded-lg p-2 hover:bg-[var(--muted)]">
                    <Trash2 size={14} className="text-[var(--muted)]" />
                  </button>
                </div>
              ))}
            </div>
          </section>
        </div>
      </div>

      {/* Add Account Modal */}
      {showAddAccount && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={() => setShowAddAccount(false)}>
          <div className="w-full max-w-md rounded-2xl bg-[var(--background)] p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold">Add Google Account</h2>
              <button onClick={() => setShowAddAccount(false)} className="rounded-lg p-1 hover:bg-[var(--muted)]">
                <X size={18} />
              </button>
            </div>
            <p className="mb-4 text-sm text-[var(--muted)]">
              You will be redirected to Google to authorize access to your calendar. After authorization, you will be returned here.
            </p>
            <button
              onClick={handleAddAccount}
              className="w-full rounded-lg bg-[var(--primary)] py-2.5 text-sm font-medium text-white"
            >
              Continue to Google
            </button>
          </div>
        </div>
      )}

      {/* Add Permission Modal */}
      {showAddPermission && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={() => setShowAddPermission(false)}>
          <div className="w-full max-w-md rounded-2xl bg-[var(--background)] p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold">Add Permission</h2>
              <button onClick={() => setShowAddPermission(false)} className="rounded-lg p-1 hover:bg-[var(--muted)]">
                <X size={18} />
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="mb-1 block text-sm font-medium text-[var(--muted)]">Calendar</label>
                <select
                  value={newPermission.calendar_id}
                  onChange={(e) => setNewPermission({ ...newPermission, calendar_id: e.target.value })}
                  className="w-full rounded-lg border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm"
                >
                  <option value="">Select calendar</option>
                  {calendars.map((c) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-[var(--muted)]">Member ID</label>
                <input
                  type="text"
                  value={newPermission.member_id}
                  onChange={(e) => setNewPermission({ ...newPermission, member_id: e.target.value })}
                  className="w-full rounded-lg border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm"
                  placeholder="Member UUID"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-[var(--muted)]">Level</label>
                <div className="grid grid-cols-2 gap-2">
                  {(["view", "edit", "manage", "admin"] as const).map((level) => {
                    const Icon = LEVEL_ICONS[level];
                    return (
                      <button
                        key={level}
                        onClick={() => setNewPermission({ ...newPermission, level })}
                        className={`flex items-center gap-2 rounded-lg border p-2 text-sm ${
                          newPermission.level === level ? "border-[var(--primary)] bg-[var(--primary)]/10" : "border-[var(--border)]"
                        }`}
                      >
                        <Icon size={14} />
                        <span className="capitalize">{level}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
              <button
                onClick={handleCreatePermission}
                disabled={!newPermission.calendar_id || !newPermission.member_id}
                className="w-full rounded-lg bg-[var(--primary)] py-2.5 text-sm font-medium text-white disabled:opacity-50"
              >
                Add Permission
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Add View Modal */}
      {showAddView && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={() => setShowAddView(false)}>
          <div className="w-full max-w-md rounded-2xl bg-[var(--background)] p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold">Add View</h2>
              <button onClick={() => setShowAddView(false)} className="rounded-lg p-1 hover:bg-[var(--muted)]">
                <X size={18} />
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="mb-1 block text-sm font-medium text-[var(--muted)]">Name</label>
                <input
                  type="text"
                  value={newView.name}
                  onChange={(e) => setNewView({ ...newView, name: e.target.value })}
                  className="w-full rounded-lg border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm"
                  placeholder="e.g. Living Room iPad"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-[var(--muted)]">Layout</label>
                <div className="grid grid-cols-2 gap-2">
                  {(["month", "week", "day", "agenda"] as const).map((layout) => (
                    <button
                      key={layout}
                      onClick={() => setNewView({ ...newView, layout })}
                      className={`rounded-lg border p-2 text-sm capitalize ${
                        newView.layout === layout ? "border-[var(--primary)] bg-[var(--primary)]/10" : "border-[var(--border)]"
                      }`}
                    >
                      {layout}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-[var(--muted)]">Calendars</label>
                <div className="space-y-1">
                  {calendars.map((c) => (
                    <label key={c.id} className="flex items-center gap-2 rounded-lg border border-[var(--border)] p-2">
                      <input
                        type="checkbox"
                        checked={newView.calendar_ids.includes(c.id)}
                        onChange={(e) => {
                          if (e.target.checked) {
                            setNewView({ ...newView, calendar_ids: [...newView.calendar_ids, c.id] });
                          } else {
                            setNewView({ ...newView, calendar_ids: newView.calendar_ids.filter((id) => id !== c.id) });
                          }
                        }}
                        className="rounded"
                      />
                      <div className="h-3 w-3 rounded-full" style={{ backgroundColor: c.color || "#6366f1" }} />
                      <span className="text-sm">{c.name}</span>
                    </label>
                  ))}
                </div>
              </div>
              <button
                onClick={handleCreateView}
                disabled={!newView.name}
                className="w-full rounded-lg bg-[var(--primary)] py-2.5 text-sm font-medium text-white disabled:opacity-50"
              >
                Create View
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
