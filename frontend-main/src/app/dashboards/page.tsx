"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  CalendarDays,
  Cloud,
  FileText,
  LayoutDashboard,
  Plus,
  Smartphone,
  Tablet,
  Trash2,
  Monitor,
} from "lucide-react";
import {
  createDashboard,
  deleteDashboard,
  listDashboards,
  updateDashboard,
  type Dashboard,
} from "@/lib/api";

const DASHBOARD_TEMPLATES = [
  {
    id: "ipad-landscape",
    name: "iPad Landscape",
    description: "Landscape tablet dashboard with calendar, notes, and weather",
    icon: Tablet,
    layout: "grid",
    widgets: [
      { type: "calendar", position: { x: 0, y: 0, w: 6, h: 4 } },
      { type: "note", position: { x: 6, y: 0, w: 3, h: 4 }, config: { note_id: "", title: "Today's Summary" } },
      { type: "weather", position: { x: 9, y: 0, w: 3, h: 4 }, config: { location: "Hong Kong" } },
    ],
  },
  {
    id: "mobile",
    name: "Mobile",
    description: "Compact mobile dashboard for quick glances",
    icon: Smartphone,
    layout: "list",
    widgets: [
      { type: "calendar", position: { x: 0, y: 0, w: 1, h: 3 } },
      { type: "note", position: { x: 0, y: 3, w: 1, h: 2 }, config: { note_id: "", title: "Today's Summary" } },
    ],
  },
  {
    id: "e-ink",
    name: "E-Ink Display",
    description: "Low-power e-ink dashboard with essential info only",
    icon: Monitor,
    layout: "grid",
    widgets: [
      { type: "calendar", position: { x: 0, y: 0, w: 4, h: 3 } },
      { type: "weather", position: { x: 4, y: 0, w: 4, h: 3 }, config: { location: "Hong Kong" } },
    ],
  },
];

export default function DashboardPage() {
  const router = useRouter();
  const [dashboards, setDashboards] = useState<Dashboard[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [creating, setCreating] = useState(false);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const list = await listDashboards();
      setDashboards(list);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboards");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function createFromTemplate(templateId: string) {
    const template = DASHBOARD_TEMPLATES.find((t) => t.id === templateId);
    if (!template) return;
    setCreating(true);
    setError("");
    try {
      await createDashboard({
        name: template.name,
        description: template.description,
        layout: template.layout,
        widgets: template.widgets,
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create dashboard");
    } finally {
      setCreating(false);
    }
  }

  async function createCustom() {
    if (!newName.trim()) return;
    setCreating(true);
    setError("");
    try {
      await createDashboard({
        name: newName.trim(),
        description: newDescription.trim() || undefined,
        layout: "grid",
        widgets: [],
      });
      setNewName("");
      setNewDescription("");
      setShowCreate(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create dashboard");
    } finally {
      setCreating(false);
    }
  }

  async function setDefault(id: string) {
    setError("");
    try {
      await updateDashboard(id, { is_default: true });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to set default");
    }
  }

  async function remove(id: string) {
    setError("");
    try {
      await deleteDashboard(id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete dashboard");
    }
  }

  if (loading) {
    return (
      <div className="page-wrap">
        <div className="loading-state">Loading dashboards…</div>
      </div>
    );
  }

  return (
    <div className="page-wrap">
      <div className="page-heading-row">
        <div>
          <p className="eyebrow">DASHBOARDS</p>
          <h1>Dashboards</h1>
          <p className="page-subtitle">Customizable landing pages for your family</p>
        </div>
        <button className="primary-button" onClick={() => setShowCreate(true)}>
          <Plus size={16} /> New Dashboard
        </button>
      </div>

      {error && <div className="form-error">{error}</div>}

      {showCreate && (
        <div className="dashboard-create-form">
          <h3>Create Dashboard</h3>
          <label className="field">
            <span>Name</span>
            <input
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="My Dashboard"
            />
          </label>
          <label className="field">
            <span>Description</span>
            <input
              type="text"
              value={newDescription}
              onChange={(e) => setNewDescription(e.target.value)}
              placeholder="What is this dashboard for?"
            />
          </label>
          <div className="dashboard-create-actions">
            <button className="primary-button" onClick={createCustom} disabled={creating || !newName.trim()}>
              {creating ? "Creating…" : "Create"}
            </button>
            <button className="secondary-button" onClick={() => setShowCreate(false)}>
              Cancel
            </button>
          </div>
        </div>
      )}

      <section className="dashboard-templates">
        <h2>Templates</h2>
        <div className="dashboard-template-grid">
          {DASHBOARD_TEMPLATES.map((template) => {
            const Icon = template.icon;
            return (
              <div key={template.id} className="dashboard-template-card">
                <div className="dashboard-template-icon">
                  <Icon size={24} />
                </div>
                <h3>{template.name}</h3>
                <p>{template.description}</p>
                <button
                  className="secondary-button"
                  onClick={() => createFromTemplate(template.id)}
                  disabled={creating}
                >
                  Use Template
                </button>
              </div>
            );
          })}
        </div>
      </section>

      <section className="dashboard-list">
        <h2>Your Dashboards</h2>
        {dashboards.length === 0 ? (
          <div className="empty-state">
            <p>No dashboards yet. Create one from a template or start from scratch.</p>
          </div>
        ) : (
          <div className="dashboard-grid">
            {dashboards.map((d) => (
              <div key={d.id} className="dashboard-card">
                <div className="dashboard-card-header">
                  <h3>{d.name}</h3>
                  {d.is_default && <span className="dashboard-default-badge">Default</span>}
                </div>
                {d.description && <p className="dashboard-card-desc">{d.description}</p>}
                <div className="dashboard-card-meta">
                  <span>{d.widgets.length} widgets</span>
                  <span>{d.layout}</span>
                </div>
                <div className="dashboard-card-actions">
                  <button
                    className="secondary-button"
                    onClick={() => router.push(`/dashboards/${d.id}`)}
                  >
                    Edit
                  </button>
                  {!d.is_default && (
                    <button className="secondary-button" onClick={() => setDefault(d.id)}>
                      Set Default
                    </button>
                  )}
                  <button className="icon-button" onClick={() => remove(d.id)} aria-label="Delete">
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
