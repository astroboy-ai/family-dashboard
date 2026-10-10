"use client";

import { useEffect, useState, useCallback } from "react";
import { RefreshCw } from "lucide-react";
import { listDashboards, type Dashboard } from "@/lib/api";
import { DashboardWeather } from "@/components/dashboard-weather";

const REFRESH_INTERVAL = 5 * 60 * 1000; // 5 minutes

function formatDate(date: Date) {
  return date.toLocaleDateString("en-HK", {
    weekday: "long",
    day: "numeric",
    month: "long",
  });
}

export default function DashboardIPadLandscapePage() {
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [noteIndex, setNoteIndex] = useState(0);
  const [now, setNow] = useState(new Date());

  const loadDashboard = useCallback(async () => {
    try {
      const list = await listDashboards();
      const defaultDash = list.find((d) => d.is_default) ?? list[0];
      if (defaultDash) {
        setDashboard(defaultDash);
      }
    } catch (err) {
      console.error("Failed to load dashboard:", err);
    }
  }, []);

  useEffect(() => {
    loadDashboard();
    const timer = setInterval(() => setNow(new Date()), 60000);
    const refresh = setInterval(loadDashboard, REFRESH_INTERVAL);
    return () => {
      clearInterval(timer);
      clearInterval(refresh);
    };
  }, [loadDashboard]);

  if (!dashboard) {
    return (
      <div className="dashboard-ipad-loading">
        <RefreshCw className="animate-spin" size={32} />
        <p>Loading dashboard…</p>
      </div>
    );
  }

  const calendarWidgets = dashboard.widgets.filter((w) => (w as Record<string, unknown>).type === "calendar");
  const noteWidgets = dashboard.widgets.filter((w) => (w as Record<string, unknown>).type === "note");
  const weatherWidgets = dashboard.widgets.filter((w) => (w as Record<string, unknown>).type === "weather");

  return (
    <div className="dashboard-ipad-landscape">
      {/* Header */}
      <div className="dashboard-ipad-header">
        <div className="dashboard-ipad-date">
          <span className="dashboard-ipad-date-text">{formatDate(now)}</span>
          <span className="dashboard-ipad-time">
            {now.toLocaleTimeString("en-HK", { hour: "2-digit", minute: "2-digit" })}
          </span>
        </div>

        <DashboardWeather location="Hong Kong" />
      </div>

      {/* Main content */}
      <div className="dashboard-ipad-content">
        {/* Left: Calendar */}
        <div className="dashboard-ipad-calendar">
          {calendarWidgets.length > 0 ? (
            <div className="dashboard-ipad-calendar-placeholder">
              <p>Calendar widget: {(calendarWidgets[0].config as Record<string, unknown>)?.calendarId as string || "Default"}</p>
              <p className="dashboard-ipad-hint">Calendar view will render here</p>
            </div>
          ) : (
            <div className="dashboard-ipad-calendar-placeholder">
              <p>No calendar widget configured</p>
            </div>
          )}
        </div>

        {/* Right: Notes with swipe */}
        <div className="dashboard-ipad-notes">
          {noteWidgets.length > 0 ? (
            <div className="dashboard-ipad-notes-container">
              <div className="dashboard-ipad-notes-tabs">
                {noteWidgets.map((w, i) => (
                  <button
                    key={i}
                    className={`dashboard-ipad-notes-tab${i === noteIndex ? " active" : ""}`}
                    onClick={() => setNoteIndex(i)}
                  >
                    {(w.config as Record<string, unknown>)?.title as string || `Note ${i + 1}`}
                  </button>
                ))}
              </div>
              <div className="dashboard-ipad-notes-dotnav">
                {noteWidgets.map((_, i) => (
                  <button
                    key={i}
                    className={`dashboard-ipad-notes-dot${i === noteIndex ? " active" : ""}`}
                    onClick={() => setNoteIndex(i)}
                    aria-label={`Note ${i + 1}`}
                  />
                ))}
              </div>
              <div className="dashboard-ipad-notes-content">
                <p>Note content will render here</p>
                <p className="dashboard-ipad-hint">Swipe left/right to switch notes</p>
              </div>
            </div>
          ) : (
            <div className="dashboard-ipad-notes-placeholder">
              <p>No note widgets configured</p>
            </div>
          )}
        </div>
      </div>

    </div>
  );
}
