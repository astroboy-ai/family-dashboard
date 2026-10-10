"use client";

import { useEffect, useState } from "react";
import { CalendarDays, Clock, MapPin, ChevronLeft, ChevronRight } from "lucide-react";
import { listCalendars, listCalendarEvents, type Calendar, type CalendarEvent } from "@/lib/api";

type CalendarView = "month" | "week" | "day" | "agenda";

interface DashboardCalendarProps {
  calendarId?: string;
  days?: number;
  initialView?: CalendarView;
}

function CalendarGrid({ events, view, currentDate }: { events: CalendarEvent[]; view: CalendarView; currentDate: Date }) {
  const [calDate, setCalDate] = useState(currentDate);

  useEffect(() => setCalDate(currentDate), [currentDate]);

  const navigate = (dir: -1 | 1) => {
    const d = new Date(calDate);
    if (view === "month") d.setMonth(d.getMonth() + dir);
    else if (view === "week") d.setDate(d.getDate() + dir * 7);
    else if (view === "day") d.setDate(d.getDate() + dir);
    else d.setDate(d.getDate() + dir);
    setCalDate(d);
  };

  const viewLabel = view === "month"
    ? calDate.toLocaleDateString("en-HK", { month: "long", year: "numeric" })
    : view === "week"
      ? `Week of ${calDate.toLocaleDateString("en-HK", { day: "numeric", month: "short" })}`
      : view === "day"
        ? calDate.toLocaleDateString("en-HK", { weekday: "long", day: "numeric", month: "short" })
        : "Agenda";

  // Filter events for visible range
  const rangeStart = new Date(calDate);
  rangeStart.setHours(0, 0, 0, 0);
  const rangeEnd = new Date(calDate);
  if (view === "month") {
    rangeEnd.setMonth(rangeEnd.getMonth() + 1);
    rangeEnd.setDate(0);
  } else if (view === "week") {
    rangeEnd.setDate(rangeEnd.getDate() + 7);
  } else if (view === "day") {
    rangeEnd.setDate(rangeEnd.getDate() + 1);
  } else {
    rangeEnd.setDate(rangeEnd.getDate() + 7);
  }

  const visibleEvents = events.filter((ev) => {
    const start = new Date(ev.start_time);
    return start >= rangeStart && start < rangeEnd;
  });

  if (view === "month") {
    const firstDay = new Date(calDate.getFullYear(), calDate.getMonth(), 1);
    const lastDay = new Date(calDate.getFullYear(), calDate.getMonth() + 1, 0);
    const startPad = firstDay.getDay();
    const days: (number | null)[] = [];
    for (let i = 0; i < startPad; i++) days.push(null);
    for (let i = 1; i <= lastDay.getDate(); i++) days.push(i);
    while (days.length % 7 !== 0) days.push(null);

    return (
      <div className="dashboard-cal-view">
        <div className="dashboard-cal-nav">
          <button onClick={() => navigate(-1)} aria-label="Previous"><ChevronLeft size={14} /></button>
          <span>{viewLabel}</span>
          <button onClick={() => navigate(1)} aria-label="Next"><ChevronRight size={14} /></button>
        </div>
        <div className="dashboard-cal-month">
          <div className="dashboard-cal-wkday">Sun</div>
          <div className="dashboard-cal-wkday">Mon</div>
          <div className="dashboard-cal-wkday">Tue</div>
          <div className="dashboard-cal-wkday">Wed</div>
          <div className="dashboard-cal-wkday">Thu</div>
          <div className="dashboard-cal-wkday">Fri</div>
          <div className="dashboard-cal-wkday">Sat</div>
          {days.map((day, i) => {
            const dayDate = day ? new Date(calDate.getFullYear(), calDate.getMonth(), day) : null;
            const isToday = dayDate?.toDateString() === new Date().toDateString();
            const dayEvents = dayDate
              ? visibleEvents.filter((ev) => new Date(ev.start_time).toDateString() === dayDate.toDateString())
              : [];
            return (
              <div key={i} className={`dashboard-cal-day${isToday ? " today" : ""}${day ? "" : " empty"}`}>
                {day && <span className="dashboard-cal-daynum">{day}</span>}
                {dayEvents.slice(0, 2).map((ev) => (
                  <div key={ev.id} className="dashboard-cal-event">{ev.title}</div>
                ))}
                {dayEvents.length > 2 && <div className="dashboard-cal-more">+{dayEvents.length - 2} more</div>}
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  if (view === "week" || view === "day") {
    const dayCount = view === "day" ? 1 : 7;
    const days: Date[] = [];
    const weekStart = new Date(calDate);
    weekStart.setDate(weekStart.getDate() - weekStart.getDay());
    for (let i = 0; i < dayCount; i++) {
      const d = new Date(weekStart);
      d.setDate(d.getDate() + i);
      days.push(d);
    }

    return (
      <div className="dashboard-cal-view">
        <div className="dashboard-cal-nav">
          <button onClick={() => navigate(-1)} aria-label="Previous"><ChevronLeft size={14} /></button>
          <span>{viewLabel}</span>
          <button onClick={() => navigate(1)} aria-label="Next"><ChevronRight size={14} /></button>
        </div>
        <div className="dashboard-cal-week">
          {days.map((d) => {
            const isToday = d.toDateString() === new Date().toDateString();
            const dayEvents = visibleEvents.filter((ev) => new Date(ev.start_time).toDateString() === d.toDateString());
            return (
              <div key={d.toDateString()} className={`dashboard-cal-day-col${isToday ? " today" : ""}`}>
                <div className="dashboard-cal-day-name">{d.toLocaleDateString("en-HK", { weekday: "short" })}</div>
                <div className="dashboard-cal-daynum">{d.getDate()}</div>
                {dayEvents.map((ev) => (
                  <div key={ev.id} className="dashboard-cal-event">{ev.title}</div>
                ))}
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  // Agenda view (default)
  const grouped = visibleEvents.reduce<Record<string, CalendarEvent[]>>((acc, ev) => {
    const dateKey = new Date(ev.start_time).toDateString();
    if (!acc[dateKey]) acc[dateKey] = [];
    acc[dateKey].push(ev);
    return acc;
  }, {});
  const sortedDates = Object.keys(grouped).sort((a, b) => new Date(a).getTime() - new Date(b).getTime());

  return (
    <div className="dashboard-cal-view">
      <div className="dashboard-cal-nav">
        <button onClick={() => navigate(-1)} aria-label="Previous"><ChevronLeft size={14} /></button>
        <span>{viewLabel}</span>
        <button onClick={() => navigate(1)} aria-label="Next"><ChevronRight size={14} /></button>
      </div>
      <div className="dashboard-cal-agenda">
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
                    {isToday ? "Today" : date.toLocaleDateString("en-HK", { weekday: "long" })}
                  </span>
                  <span className="dashboard-calendar-day-date">
                    {date.toLocaleDateString("en-HK", { day: "numeric", month: "short" })}
                  </span>
                </div>
                {dateEvents.map((ev) => (
                  <div key={ev.id} className="dashboard-calendar-event">
                    <div className="dashboard-calendar-event-time">
                      <Clock size={12} />
                      {ev.all_day ? "All day" : new Date(ev.start_time).toLocaleTimeString("en-HK", { hour: "2-digit", minute: "2-digit" })}
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

function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString("en-HK", { hour: "2-digit", minute: "2-digit" });
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-HK", { weekday: "short", day: "numeric" });
}

export function DashboardCalendar({ calendarId, days = 7, initialView = "agenda" }: DashboardCalendarProps) {
  const [calendars, setCalendars] = useState<Calendar[]>([]);
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<CalendarView>(initialView);

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

  const viewOptions: { key: CalendarView; label: string }[] = [
    { key: "month", label: "Month" },
    { key: "week", label: "Week" },
    { key: "day", label: "Day" },
    { key: "agenda", label: "Agenda" },
  ];

  return (
    <div className="dashboard-calendar">
      <div className="dashboard-calendar-header">
        <CalendarDays size={18} />
        <span>Calendar</span>
        <div className="dashboard-calendar-views">
          {viewOptions.map((v) => (
            <button
              key={v.key}
              className={`dashboard-calendar-view-btn${view === v.key ? " active" : ""}`}
              onClick={() => setView(v.key)}
            >
              {v.label}
            </button>
          ))}
        </div>
        <span className="dashboard-calendar-count">{events.length} events</span>
      </div>
      <div className="dashboard-calendar-body">
        <CalendarGrid events={events} view={view} currentDate={new Date()} />
      </div>
    </div>
  );
}
