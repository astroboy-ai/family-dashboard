"use client";

import { useEffect, useState } from "react";
import { CalendarDays, Clock, MapPin } from "lucide-react";
import { listCalendars, listCalendarEvents, type Calendar, type CalendarEvent } from "@/lib/api";

interface DashboardCalendarProps {
  calendarId?: string;
  days?: number;
}

function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString("en-HK", { hour: "2-digit", minute: "2-digit" });
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-HK", { weekday: "short", day: "numeric" });
}

export function DashboardCalendar({ calendarId, days = 7 }: DashboardCalendarProps) {
  const [calendars, setCalendars] = useState<Calendar[]>([]);
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        setLoading(true);
        const [calList, evList] = await Promise.all([
          listCalendars(),
          listCalendarEvents({
            start: new Date().toISOString(),
            end: new Date(Date.now() + days * 24 * 60 * 60 * 1000).toISOString(),
            limit: 200,
          }),
        ]);
        if (!active) return;
        setCalendars(calList);
        setEvents(evList);
        setError(null);
      } catch (err) {
        if (!active) return;
        setError(err instanceof Error ? err.message : "Failed to load calendar");
      } finally {
        if (active) setLoading(false);
      }
    }
    load();
    return () => { active = false; };
  }, [calendarId, days]);

  if (loading) {
    return (
      <div className="dashboard-calendar-loading">
        <CalendarDays className="animate-spin" size={24} />
        <p>Loading calendar…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="dashboard-calendar-error">
        <p>⚠️ {error}</p>
      </div>
    );
  }

  // Group events by date
  const grouped = events.reduce<Record<string, CalendarEvent[]>>((acc, ev) => {
    const dateKey = new Date(ev.start_time).toDateString();
    if (!acc[dateKey]) acc[dateKey] = [];
    acc[dateKey].push(ev);
    return acc;
  }, {});

  const sortedDates = Object.keys(grouped).sort(
    (a, b) => new Date(a).getTime() - new Date(b).getTime()
  );

  return (
    <div className="dashboard-calendar">
      <div className="dashboard-calendar-header">
        <CalendarDays size={18} />
        <span>Agenda</span>
        <span className="dashboard-calendar-count">{events.length} events</span>
      </div>
      <div className="dashboard-calendar-list">
        {sortedDates.length === 0 ? (
          <p className="dashboard-calendar-empty">No upcoming events</p>
        ) : (
          sortedDates.map((dateKey) => {
            const dateEvents = grouped[dateKey];
            const date = new Date(dateKey);
            const isToday = date.toDateString() === new Date().toDateString();
            return (
              <div key={dateKey} className="dashboard-calendar-day">
                <div className="dashboard-calendar-day-header">
                  <span className={`dashboard-calendar-day-name${isToday ? " today" : ""}`}>
                    {isToday ? "Today" : formatDate(dateKey)}
                  </span>
                  <span className="dashboard-calendar-day-date">
                    {date.toLocaleDateString("en-HK", { day: "numeric", month: "short" })}
                  </span>
                </div>
                {dateEvents.map((ev) => (
                  <div key={ev.id} className="dashboard-calendar-event">
                    <div className="dashboard-calendar-event-time">
                      <Clock size={12} />
                      {ev.all_day ? "All day" : formatTime(ev.start_time)}
                    </div>
                    <div className="dashboard-calendar-event-title">{ev.title}</div>
                    {ev.location && (
                      <div className="dashboard-calendar-event-location">
                        <MapPin size={11} />
                        {ev.location}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
