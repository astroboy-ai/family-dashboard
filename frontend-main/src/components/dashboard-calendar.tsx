"use client";

import { useEffect, useState } from "react";
import { CalendarDays, Clock, MapPin, ChevronLeft, ChevronRight } from "lucide-react";
import { listCalendars, listCalendarEvents, type Calendar, type CalendarEvent } from "@/lib/api";

interface DashboardCalendarProps {
  calendarId?: string;
  days?: number;
}

function MonthGrid({ events, selectedDate, onSelectDate, showFilters, onToggleFilters, hasActiveFilter, calendars }: { events: CalendarEvent[]; selectedDate: Date; onSelectDate: (d: Date) => void; showFilters: boolean; onToggleFilters: () => void; hasActiveFilter: boolean; calendars: Calendar[] }) {
  const [calDate, setCalDate] = useState(selectedDate);

  useEffect(() => setCalDate(selectedDate), [selectedDate]);

  const navigate = (dir: -1 | 1) => {
    const d = new Date(calDate);
    d.setMonth(d.getMonth() + dir);
    setCalDate(d);
  };

  const viewLabel = calDate.toLocaleDateString("en-HK", { month: "long", year: "numeric" });

  const firstDay = new Date(calDate.getFullYear(), calDate.getMonth(), 1);
  const lastDay = new Date(calDate.getFullYear(), calDate.getMonth() + 1, 0);
  const startPad = firstDay.getDay();
  const days: (number | null)[] = [];
  for (let i = 0; i < startPad; i++) days.push(null);
  for (let i = 1; i <= lastDay.getDate(); i++) days.push(i);
  while (days.length % 7 !== 0) days.push(null);

  const visibleEvents = events.filter((ev) => {
    const start = new Date(ev.start_time);
    return start >= new Date(calDate.getFullYear(), calDate.getMonth(), 1) && start <= new Date(calDate.getFullYear(), calDate.getMonth() + 1, 0, 23, 59, 59);
  });

  return (
    <div className="dashboard-cal-view">
      <div className="dashboard-cal-nav">
        <button onClick={() => navigate(-1)} aria-label="Previous"><ChevronLeft size={14} /></button>
        <span className="dashboard-cal-nav-month">{viewLabel}</span>
        <button onClick={() => navigate(1)} aria-label="Next"><ChevronRight size={14} /></button>
        <button
          className={`dashboard-cal-filter-btn${showFilters || hasActiveFilter ? " active" : ""}`}
          onClick={onToggleFilters}
          title="Choose which calendars to show"
        >
          <CalendarDays size={14} />
        </button>
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
          const isSelected = dayDate?.toDateString() === selectedDate.toDateString();
          const dayEvents = dayDate
            ? visibleEvents.filter((ev) => new Date(ev.start_time).toDateString() === dayDate.toDateString())
            : [];
          return (
            <div
              key={i}
              className={`dashboard-cal-day${isToday ? " today" : ""}${isSelected ? " selected" : ""}${day ? "" : " empty"}`}
              onClick={() => dayDate && onSelectDate(dayDate)}
            >
              {day && <span className="dashboard-cal-daynum">{day}</span>}
              {dayEvents.length > 0 && (
                <div className="dashboard-cal-event-dots">
                  {dayEvents.slice(0, 3).map((ev) => {
                    const cal = calendars.find((c) => c.id === ev.calendar_id);
                    return (
                      <div
                        key={ev.id}
                        className="dashboard-cal-event-dot"
                        style={{ backgroundColor: cal?.color || "#6366f1" }}
                        title={ev.title}
                      />
                    );
                  })}
                  {dayEvents.length > 3 && (
                    <span className="dashboard-cal-more">+{dayEvents.length - 3}</span>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function AgendaList({ events, selectedDate, calendars }: { events: CalendarEvent[]; selectedDate: Date; calendars: Calendar[] }) {
  const dayEvents = events.filter((ev) => {
    const start = new Date(ev.start_time);
    return start.toDateString() === selectedDate.toDateString();
  });

  const sorted = [...dayEvents].sort((a, b) => new Date(a.start_time).getTime() - new Date(b.start_time).getTime());

  const getCalendarColor = (calendarId: string) => {
    const cal = calendars.find((c) => c.id === calendarId);
    return cal?.color || "#6366f1";
  };

  return (
    <div className="dashboard-cal-agenda">
      <div className="dashboard-cal-agenda-header">
        <span className="dashboard-cal-agenda-date">
          {selectedDate.toLocaleDateString("en-HK", { weekday: "long", day: "numeric", month: "long" })}
        </span>
        <span className="dashboard-cal-agenda-count">{sorted.length} events</span>
      </div>
      {sorted.length === 0 ? (
        <p className="dashboard-calendar-empty">No events for this day</p>
      ) : (
        sorted.map((ev) => {
          const color = getCalendarColor(ev.calendar_id);
          return (
            <div key={ev.id} className="dashboard-calendar-event">
              <div className="dashboard-calendar-event-color" style={{ backgroundColor: color }} />
              <div className="dashboard-calendar-event-content">
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
            </div>
          );
        })
      )}
    </div>
  );
}

export function DashboardCalendar({ calendarId, days = 60 }: DashboardCalendarProps) {
  const [calendars, setCalendars] = useState<Calendar[]>([]);
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedDate, setSelectedDate] = useState<Date>(new Date());
  const [showFilters, setShowFilters] = useState(false);
  const [visibleCalendarIds, setVisibleCalendarIds] = useState<string[] | null>(null);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        setLoading(true);
        const [calList, evList] = await Promise.all([
          listCalendars(),
          listCalendarEvents({
            start: new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString(),
            end: new Date(Date.now() + days * 24 * 60 * 60 * 1000).toISOString(),
            limit: 500,
          }),
        ]);
        if (!active) return;
        setCalendars(calList);
        setEvents(evList);
        setVisibleCalendarIds(calList.map((c) => c.id));
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

  const toggleCalendarFilter = (calendarId: string) => {
    const current = visibleCalendarIds ?? calendars.map((c) => c.id);
    const next = current.includes(calendarId)
      ? current.filter((id) => id !== calendarId)
      : [...current, calendarId];
    setVisibleCalendarIds(next);
  };

  const filteredEvents = visibleCalendarIds
    ? events.filter((ev) => visibleCalendarIds.includes(ev.calendar_id))
    : events;

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

  return (
    <div className="dashboard-calendar">
      {showFilters && (
        <div className="dashboard-calendar-filters">
          <div className="dashboard-calendar-filters-header">
            <span>Show calendars</span>
            <button
              onClick={() => {
                const all = calendars.map((c) => c.id);
                setVisibleCalendarIds(all);
              }}
            >
              Select all
            </button>
          </div>
          <div className="dashboard-calendar-filters-list">
            <div className="dashboard-calendar-filters-dots">
              {calendars.map((cal) => {
                const checked = !visibleCalendarIds || visibleCalendarIds.includes(cal.id);
                return (
                  <button
                    key={cal.id}
                    onClick={() => toggleCalendarFilter(cal.id)}
                    className={`dashboard-calendar-filter-dot${checked ? " checked" : ""}`}
                    style={{
                      borderColor: cal.color || "#6366f1",
                      backgroundColor: checked ? cal.color || "#6366f1" : "transparent",
                    }}
                    title={cal.name}
                  >
                    {checked && <span className="dashboard-calendar-filter-check-icon">✓</span>}
                  </button>
                );
              })}
            </div>
            {calendars.length === 0 && (
              <p className="dashboard-calendar-filters-empty">No calendars synced yet.</p>
            )}
          </div>
        </div>
      )}
      <div className="dashboard-calendar-body">
        <div className="dashboard-calendar-month">
          <MonthGrid events={filteredEvents} selectedDate={selectedDate} onSelectDate={setSelectedDate} showFilters={showFilters} onToggleFilters={() => setShowFilters((v) => !v)} hasActiveFilter={visibleCalendarIds !== null && visibleCalendarIds.length < calendars.length} calendars={calendars} />
        </div>
        <div className="dashboard-calendar-agenda">
          <AgendaList events={filteredEvents} selectedDate={selectedDate} calendars={calendars} />
        </div>
      </div>
    </div>
  );
}

