"use client";

import { useState } from "react";
import {
  Cloud,
  Droplets,
  Sun,
  CloudRain,
  CloudSnow,
  CloudLightning,
  Wind,
  X,
} from "lucide-react";

const ICON_MAP: Record<string, typeof Sun> = {
  sun: Sun,
  "cloud-sun": Cloud,
  cloud: Cloud,
  "cloud-rain": CloudRain,
  "cloud-snow": CloudSnow,
  "cloud-lightning": CloudLightning,
};

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

interface DashboardWeatherProps {
  location?: string;
  compact?: boolean;
}

export function DashboardWeather({ location = "Hong Kong", compact = false }: DashboardWeatherProps) {
  const [showWindy, setShowWindy] = useState(false);
  const { today, forecast } = MOCK_WEATHER;
  const TodayIcon = ICON_MAP[today.icon] || Cloud;

  if (compact) {
    return (
      <div className="dashboard-weather-compact">
        <div className="dashboard-weather-compact-main">
          <TodayIcon size={compact ? 20 : 32} />
          <span className="dashboard-weather-compact-temp">{today.temp}°C</span>
          <span className="dashboard-weather-compact-rain">
            <Droplets size={12} /> {today.rain}%
          </span>
          <button
            className="dashboard-weather-windy-btn"
            onClick={() => setShowWindy(true)}
            aria-label="View wind map"
          >
            <Wind size={16} />
          </button>
        </div>
        <div className="dashboard-weather-compact-forecast">
          {forecast.map((d) => {
            const DayIcon = ICON_MAP[d.icon] || Cloud;
            return (
              <div key={d.day} className="dashboard-weather-compact-day">
                <span>{d.day}</span>
                <DayIcon size={14} />
                <span>{d.temp}°</span>
              </div>
            );
          })}
        </div>
        {showWindy && (
          <div className="dashboard-weather-windy-overlay" onClick={() => setShowWindy(false)}>
            <div className="dashboard-weather-windy-content" onClick={(e) => e.stopPropagation()}>
              <div className="dashboard-weather-windy-header">
                <h3>Wind Map — {location}</h3>
                <button onClick={() => setShowWindy(false)} aria-label="Close">
                  <X size={20} />
                </button>
              </div>
              <div className="dashboard-weather-windy-map">
                <iframe
                  src="https://embed.windy.com/embed2.html?lat=22.3193&lon=114.1694&zoom=10&level=surface&overlay=wind&menu=&message=&marker=&calendar=&pressure=&type=map&location=coordinates&detail=&detailLat=22.3193&detailLon=114.1694&metricWind=km%2Fh&metricTemp=%C2%B0C&radarRange=-1"
                  title="Windy - Hong Kong"
                  style={{ width: "100%", height: "100%", border: "none" }}
                />
              </div>
            </div>
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="dashboard-weather">
      <div className="dashboard-weather-today">
        <TodayIcon size={36} />
        <div className="dashboard-weather-info">
          <span className="dashboard-weather-temp">{today.temp}°C</span>
          <span className="dashboard-weather-detail">
            <Droplets size={14} /> {today.rain}%
          </span>
          <span className="dashboard-weather-detail">
            <Wind size={14} /> {today.wind} km/h
          </span>
        </div>
      </div>
      <div className="dashboard-weather-forecast">
        {forecast.map((d) => {
          const DayIcon = ICON_MAP[d.icon] || Cloud;
          return (
            <div key={d.day} className="dashboard-weather-day">
              <span className="dashboard-weather-day-name">{d.day}</span>
              <DayIcon size={16} />
              <span className="dashboard-weather-day-temp">{d.temp}°</span>
              <span className="dashboard-weather-day-rain">{d.rain}%</span>
            </div>
          );
        })}
      </div>
      <div className="dashboard-weather-footer">
        <span>Last updated: {new Date().toLocaleTimeString("en-HK", { hour: "2-digit", minute: "2-digit" })} • Auto-refresh every 5 min</span>
      </div>
      <button
        className="dashboard-weather-windy"
        onClick={() => setShowWindy(true)}
        aria-label="View wind map"
      >
        <Wind size={18} />
      </button>
      {showWindy && (
        <div className="dashboard-weather-windy-overlay" onClick={() => setShowWindy(false)}>
          <div className="dashboard-weather-windy-content" onClick={(e) => e.stopPropagation()}>
            <div className="dashboard-weather-windy-header">
              <h3>Wind Map — {location}</h3>
              <button onClick={() => setShowWindy(false)} aria-label="Close">
                <X size={20} />
              </button>
            </div>
            <div className="dashboard-weather-windy-map">
              <iframe
                src="https://embed.windy.com/embed2.html?lat=22.3193&lon=114.1694&zoom=10&level=surface&overlay=wind&menu=&message=&marker=&calendar=&pressure=&type=map&location=coordinates&detail=&detailLat=22.3193&detailLon=114.1694&metricWind=km%2Fh&metricTemp=%C2%B0C&radarRange=-1"
                title="Windy - Hong Kong"
                style={{ width: "100%", height: "100%", border: "none" }}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
