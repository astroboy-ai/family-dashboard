"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { RefreshCw } from "lucide-react";
import { listDashboards, type Dashboard } from "@/lib/api";
import { DashboardWeather } from "@/components/dashboard-weather";
import { DashboardCalendar } from "@/components/dashboard-calendar";
import { DashboardNote } from "@/components/dashboard-note";
import { DashboardSchool } from "@/components/dashboard-school";
import { DashboardTimeline } from "@/components/dashboard-timeline";

const REFRESH_INTERVAL = 5 * 60 * 1000; // 5 minutes

export default function DashboardIPadLandscapePage() {
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [noteIndex, setNoteIndex] = useState(0);
  const touchStartX = useRef<number | null>(null);
  const touchEndX = useRef<number | null>(null);

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
    const refresh = setInterval(loadDashboard, REFRESH_INTERVAL);
    return () => {
      clearInterval(refresh);
    };
  }, [loadDashboard]);

  const handleTouchStart = (e: React.TouchEvent) => {
    touchStartX.current = e.touches[0].clientX;
  };

  const handleTouchMove = (e: React.TouchEvent) => {
    touchEndX.current = e.touches[0].clientX;
  };

  const handleTouchEnd = () => {
    if (!touchStartX.current || !touchEndX.current) return;
    const diff = touchStartX.current - touchEndX.current;
    const threshold = 50;
    if (Math.abs(diff) > threshold && dashboard) {
      const noteWidgets = dashboard.widgets.filter((w) => (w as Record<string, unknown>).type === "note");
      if (diff > 0 && noteIndex < noteWidgets.length - 1) {
        setNoteIndex((i) => i + 1);
      } else if (diff < 0 && noteIndex > 0) {
        setNoteIndex((i) => i - 1);
      }
    }
    touchStartX.current = null;
    touchEndX.current = null;
  };

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

  return (
    <div className="dashboard-ipad-landscape">
      {/* Main content */}
      <div className="dashboard-ipad-content">
        {/* Left: Calendar (44%) */}
        <div className="dashboard-ipad-calendar">
          <DashboardCalendar calendarId={(calendarWidgets[0]?.config as Record<string, unknown>)?.calendarId as string} days={60} />
        </div>

        {/* Right: Weather + School (top) | Placeholder + Notes (bottom) */}
        <div className="dashboard-ipad-right">
          <div className="dashboard-ipad-top-row">
            <div className="dashboard-ipad-weather-area">
              <DashboardWeather location="Hong Kong" />
            </div>
            <div className="dashboard-ipad-school-area">
              <DashboardSchool childName="Phoebe" />
            </div>
          </div>
          <div className="dashboard-ipad-bottom-row">
            <div className="dashboard-ipad-placeholder">
              <DashboardTimeline childName="Phoebe" />
            </div>
            <div
              className="dashboard-ipad-notes"
              onTouchStart={handleTouchStart}
              onTouchMove={handleTouchMove}
              onTouchEnd={handleTouchEnd}
            >
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
                  <div className="dashboard-ipad-notes-content">
                    <DashboardNote
                      noteId={(noteWidgets[noteIndex]?.config as Record<string, unknown>)?.noteId as string}
                      title={(noteWidgets[noteIndex]?.config as Record<string, unknown>)?.title as string}
                    />
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
                </div>
              ) : (
                <div className="dashboard-ipad-notes-placeholder">
                  <p>No note widgets configured</p>
                  <p className="dashboard-ipad-hint">Agent will assign notes here</p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

