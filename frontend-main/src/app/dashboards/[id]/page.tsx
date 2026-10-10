"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Plus, Save, Trash2 } from "lucide-react";
import {
  getDashboard,
  updateDashboard,
  type Dashboard,
} from "@/lib/api";

const WIDGET_TYPES = [
  { type: "calendar", label: "Calendar", icon: "📅" },
  { type: "note", label: "Note", icon: "📝" },
  { type: "weather", label: "Weather", icon: "🌤️" },
  { type: "agenda", label: "Agenda", icon: "📋" },
  { type: "tasks", label: "Tasks", icon: "✅" },
  { type: "image", label: "Image", icon: "🖼️" },
];

export default function DashboardEditorPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function load() {
    setLoading(true);
    setError("");
    try {
      const d = await getDashboard(params.id);
      setDashboard(d);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [params.id]);

  async function save() {
    if (!dashboard) return;
    setSaving(true);
    setError("");
    try {
      await updateDashboard(dashboard.id, {
        name: dashboard.name,
        description: dashboard.description ?? "",
        layout: dashboard.layout,
        widgets: dashboard.widgets,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  function addWidget(type: string) {
    if (!dashboard) return;
    const newWidget = {
      type,
      position: { x: 0, y: 0, w: 4, h: 3 },
      config: {},
    };
    setDashboard({
      ...dashboard,
      widgets: [...dashboard.widgets, newWidget],
    });
  }

  function removeWidget(index: number) {
    if (!dashboard) return;
    setDashboard({
      ...dashboard,
      widgets: dashboard.widgets.filter((_, i) => i !== index),
    });
  }

  if (loading) {
    return (
      <div className="page-wrap">
        <div className="loading-state">Loading dashboard…</div>
      </div>
    );
  }

  if (!dashboard) {
    return (
      <div className="page-wrap">
        <div className="form-error">{error || "Dashboard not found"}</div>
      </div>
    );
  }

  return (
    <div className="page-wrap">
      <div className="page-heading-row">
        <div>
          <button className="back-button" onClick={() => router.push("/dashboards")}>
            <ArrowLeft size={16} /> Back
          </button>
          <p className="eyebrow">EDIT DASHBOARD</p>
          <h1>{dashboard.name}</h1>
        </div>
        <button className="primary-button" onClick={save} disabled={saving}>
          <Save size={16} /> {saving ? "Saving…" : "Save"}
        </button>
      </div>

      {error && <div className="form-error">{error}</div>}

      <div className="dashboard-editor">
        <div className="dashboard-editor-sidebar">
          <h3>Add Widget</h3>
          <div className="widget-type-list">
            {WIDGET_TYPES.map((w) => (
              <button
                key={w.type}
                className="widget-type-button"
                onClick={() => addWidget(w.type)}
              >
                <span className="widget-type-icon">{w.icon}</span>
                <span>{w.label}</span>
                <Plus size={14} />
              </button>
            ))}
          </div>
        </div>

        <div className="dashboard-editor-canvas">
          <div className="dashboard-widgets-grid">
            {dashboard.widgets.length === 0 ? (
              <div className="empty-state">
                <p>No widgets yet. Add one from the sidebar.</p>
              </div>
            ) : (
              dashboard.widgets.map((widget, index) => (
                <div key={index} className="dashboard-widget-card">
                  <div className="dashboard-widget-header">
                    <span className="dashboard-widget-type">
                      {WIDGET_TYPES.find((w) => w.type === widget.type)?.icon}{" "}
                      {WIDGET_TYPES.find((w) => w.type === widget.type)?.label}
                    </span>
                    <button
                      className="icon-button"
                      onClick={() => removeWidget(index)}
                      aria-label="Remove widget"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                  <div className="dashboard-widget-preview">
                    <p>Widget preview</p>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
