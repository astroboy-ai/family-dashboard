"use client";

import { useEffect, useState, useCallback } from "react";
import {
  Cloud,
  Droplets,
  Sun,
  CloudRain,
  CloudSnow,
  CloudLightning,
  Wind,
  RefreshCw,
  X,
} from "lucide-react";
import { listDashboards, type Dashboard } from "@/lib/api";

const ICON_MAP = {
  sun: Sun,
  "cloud-sun": Cloud,
  cloud: Cloud,
  "cloud-rain": CloudRain,
  "cloud-snow": CloudSnow,
  "cloud-lightning": CloudLightning,
};

const REFRESH_INTERVAL = 5 * 60 * 1000; // 5 minutes

interface WeatherDay {
  day: string;
  icon: string;
  temp: number;
  rain: number;
}

const MOCK_WEATHER = {
  today: { icon: "cloud-sun", temp: 26, rain: 20, humidity: 78, wind: 12 },
  forecast: [
    { day: "Sun", icon: "cloud-sun", temp: 27, rain: 20 },
    { day: "Mon", icon: "cloud-rain", temp: 24, rain: 60 },
    { day: "Tue", icon: "cloud-rain", temp: 23, rain: 80 },
    { day: "Wed", icon: "cloud", temp: 25, rain: 30 },
    { day: "Thu", icon: "cloud-sun", temp: 27, rain: 10 },
    { day: "Fri", icon: "sun", temp: 28, rain: 5 },
    { day: "Sat", icon: "cloud-sun", temp: 27, rain: 15 },
  ] as WeatherDay[],
};

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
  const [showWindy, setShowWindy] = useState(false);
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

        <div className="dashboard-ipad-weather">
          <div className="dashboard-ipad-weather-today">
            {(() => {
              const Icon = ICON_MAP[MOCK_WEATHER.today.icon as keyof typeof ICON_MAP] || Cloud;
              return <Icon size={32} />;
            })()}
            <div className="dashboard-ipad-weather-info">
              <span className="dashboard-ipad-weather-temp">{MOCK_WEATHER.today.temp}°C</span>
              <span className="dashboard-ipad-weather-rain">
                <Droplets size={14} /> {MOCK_WEATHER.today.rain}%
              </span>
            </div>
          </div>
          <div className="dashboard-ipad-weather-forecast">
            {MOCK_WEATHER.forecast.map((d) => {
              const Icon = ICON_MAP[d.icon as keyof typeof ICON_MAP] || Cloud;
              return (
                <div key={d.day} className="dashboard-ipad-weather-day">
                  <span className="dashboard-ipad-weather-day-name">{d.day}</span>
                  <Icon size={16} />
                  <span className="dashboard-ipad-weather-day-temp">{d.temp}°</span>
                  <span className="dashboard-ipad-weather-day-rain">{d.rain}%</span>
                </div>
              );
            })}
          </div>
          <button
            className="dashboard-ipad-weather-windy"
            onClick={() => setShowWindy(true)}
            aria-label="View wind map"
          >
            <Wind size={20} />
          </button>
        </div>
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

      {/* Windy overlay */}
      {showWindy && (
        <div className="dashboard-ipad-windy-overlay" onClick={() => setShowWindy(false)}>
          <div className="dashboard-ipad-windy-content" onClick={(e) => e.stopPropagation()}>
            <div className="dashboard-ipad-windy-header">
              <h3>Wind Map</h3>
              <button onClick={() => setShowWindy(false)} aria-label="Close">
                <X size={24} />
              </button>
            </div>
            <div className="dashboard-ipad-windy-map">
              <p>Windy.com map will embed here</p>
              <p className="dashboard-ipad-hint">HK region wind forecast</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
