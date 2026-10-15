"use client";

import { useEffect, useMemo, useState } from "react";
import { CalendarDays, Clock, MapPin, ChevronLeft, ChevronRight } from "lucide-react";
import { listCalendars, listCalendarEvents, type Calendar, type CalendarEvent } from "@/lib/api";

interface DashboardCalendarProps {
  calendarId?: string;
  days?: number;
}

const VIEWS = ["month", "week", "day", "agenda"] as const;
type View = (typeof VIEWS)[number];

function addDays(date: Date, n: number): Date {
  const d = new Date(date);
  d.setDate(d.getDate() + n);
  return d;
}

function isSameDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

function startOfWeek(date: Date): Date {
  const d = new Date(date);
  d.setDate(d.getDate() - d.getDay());
  return d;
}

/** Mirror of the calendar module's formatTime so the two never drift. */
function formatTime(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", hour12: true });
}

function formatDateMedium(date: Date): string {
  return date.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });
}

function getCalendarColor(calendars: Calendar[], calendarId: string): string {
  return calendars.find((c) => c.id === calendarId)?.color || "#6366f1";
}

function EventRow({ ev, calendars }: { ev: CalendarEvent; calendars: Calendar[] }) {
  const color = getCalendarColor(calendars, ev.calendar_id);
  return (
    <div className="dashboard-calendar-event">
      <div className="dashboard-calendar-event-color" style={{ backgroundColor: color }} />
      <div className="dashboard-calendar-event-content">
        <div className="dashboard-calendar-event-time">
          <Clock size={12} />
          {ev.all_day ? "All day" : `${formatTime(ev.start_time)} – ${formatTime(ev.end_time)}`}
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
}

function MonthGrid({
  events,
  selectedDate,
  onSelectDate,
  showFilters,
  onToggleFilters,
  hasActiveFilter,
  calendars,
  onMonthChange,
}: {
  events: CalendarEvent[];
  selectedDate: Date;
  onSelectDate: (d: Date) => void;
  showFilters: boolean;
  onToggleFilters: () => void;
  hasActiveFilter: boolean;
  calendars: Calendar[];
  onMonthChange: (dir: -1 | 1, newDate: Date) => void;
}) {
  const [calDate, setCalDate] = useState(selectedDate);
  useEffect(() => setCalDate(selectedDate), [selectedDate]);

  const navigate = (dir: -1 | 1) => {
    const d = new Date(calDate);
    d.setMonth(d.getMonth() + dir);
    setCalDate(d);
    onMonthChange(dir, d);
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
    return (
      start >= new Date(calDate.getFullYear(), calDate.getMonth(), 1) &&
      start <= new Date(calDate.getFullYear(), calDate.getMonth() + 1, 0, 23, 59, 59)
    );
  });

  return (
    <div className="dashboard-cal-view">
      <div className="dashboard-cal-nav">
        <button onClick={() => navigate(-1)} aria-label="Previous">
          <ChevronLeft size={14} />
        </button>
        <span className="dashboard-cal-nav-month">{viewLabel}</span>
        <button onClick={() => navigate(1)} aria-label="Next">
          <ChevronRight size={14} />
        </button>
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
              className={`dashboard-cal-day${isToday ? " today" : ""}${isSelected ? " selected" : ""}${
                day ? "" : " empty"
              }`}
              onClick={() => dayDate && onSelectDate(dayDate)}
            >
              {day && <span className="dashboard-cal-daynum">{day}</span>}
              {dayEvents.length > 0 && (
                <div className="dashboard-cal-event-dots">
                  {dayEvents.slice(0, 3).map((ev) => (
                    <div
                      key={ev.id}
                      className="dashboard-cal-event-dot"
                      style={{ backgroundColor: getCalendarColor(calendars, ev.calendar_id) }}
                      title={ev.title}
                    />
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function WeekStrip({
  events,
  selectedDate,
  onSelectDate,
  calendars,
}: {
  events: CalendarEvent[];
  selectedDate: Date;
  onSelectDate: (d: Date) => void;
  calendars: Calendar[];
}) {
  const weekStart = startOfWeek(selectedDate);
  const days = Array.from({ length: 7 }, (_, i) => addDays(weekStart, i));
  const label = `${weekStart.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  })} – ${days[6].toLocaleDateString("en-US", { month: "short", day: "numeric" })}`;

  return (
    <div className="dashboard-cal-week">
      <div className="dashboard-cal-nav">
        <button onClick={() => onSelectDate(addDays(selectedDate, -7))} aria-label="Previous week">
          <ChevronLeft size={14} />
        </button>
        <span className="dashboard-cal-nav-month">{label}</span>
        <button onClick={() => onSelectDate(addDays(selectedDate, 7))} aria-label="Next week">
          <ChevronRight size={14} />
        </button>
      </div>
      <div className="dashboard-cal-week-grid">
        {days.map((d) => {
          const dayEvents = events.filter((ev) => isSameDay(new Date(ev.start_time), d));
          const isToday = isSameDay(d, new Date());
          const isSelected = isSameDay(d, selectedDate);
          return (
            <div
              key={d.toISOString()}
              className={`dashboard-cal-week-day${isToday ? " today" : ""}${isSelected ? " selected" : ""}`}
              onClick={() => onSelectDate(d)}
            >
              <span className="dashboard-cal-week-daynum">
                {d.toLocaleDateString("en-US", { weekday: "short", day: "numeric" })}
              </span>
              <span className="dashboard-cal-week-count">{dayEvents.length} event{dayEvents.length !== 1 ? "s" : ""}</span>
              <div className="dashboard-cal-event-dots">
                {dayEvents.slice(0, 3).map((ev) => (
                  <div
                    key={ev.id}
                    className="dashboard-cal-event-dot"
                    style={{ backgroundColor: getCalendarColor(calendars, ev.calendar_id) }}
                    title={ev.title}
                  />
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function DayView({
  events,
  selectedDate,
  calendars,
  onPrev,
  onNext,
}: {
  events: CalendarEvent[];
  selectedDate: Date;
  calendars: Calendar[];
  onPrev: () => void;
  onNext: () => void;
}) {
  const dayEvents = useMemo(
    () =>
      events
        .filter((ev) => isSameDay(new Date(ev.start_time), selectedDate))
        .sort((a, b) => new Date(a.start_time).getTime() - new Date(b.start_time).getTime()),
    [events, selectedDate],
  );

  return (
    <div className="dashboard-cal-dayview">
      <div className="dashboard-cal-nav">
        <button onClick={onPrev} aria-label="Previous day">
          <ChevronLeft size={14} />
        </button>
        <span className="dashboard-cal-nav-month">{isSameDay(selectedDate, new Date()) ? "Today" : formatDateMedium(selectedDate)}</span>
        <button onClick={onNext} aria-label="Next day">
          <ChevronRight size={14} />
        </button>
      </div>
      {dayEvents.length === 0 ? (
        <p className="dashboard-calendar-empty">No events for this day</p>
      ) : (
        dayEvents.map((ev) => <EventRow key={ev.id} ev={ev} calendars={calendars} />)
      )}
    </div>
  );
}

function AgendaView({
  events,
  selectedDate,
  calendars,
  onPrev,
  onNext,
}: {
  events: CalendarEvent[];
  selectedDate: Date;
  calendars: Calendar[];
  onPrev: () => void;
  onNext: () => void;
}) {
  const grouped = useMemo(() => {
    const byDay = new Map<string, CalendarEvent[]>();
    const cutoff = new Date(selectedDate);
    cutoff.setHours(0, 0, 0, 0);
    for (const ev of events) {
      const s = new Date(ev.start_time);
      if (s < cutoff) continue;
      const key = s.toDateString();
      const arr = byDay.get(key);
      if (arr) arr.push(ev);
      else byDay.set(key, [ev]);
    }
    return Array.from(byDay.entries())
      .map(([k, arr]) => ({
        date: new Date(k),
        events: arr.sort((a, b) => new Date(a.start_time).getTime() - new Date(b.start_time).getTime()),
      }))
      .sort((a, b) => a.date.getTime() - b.date.getTime());
  }, [events, selectedDate]);

  return (
    <div className="dashboard-cal-agenda-view">
      <div className="dashboard-cal-nav">
        <button onClick={onPrev} aria-label="Previous agenda">
          <ChevronLeft size={14} />
        </button>
        <span className="dashboard-cal-nav-month">Upcoming</span>
        <button onClick={onNext} aria-label="Next agenda">
          <ChevronRight size={14} />
        </button>
      </div>
      {grouped.length === 0 ? (
        <p className="dashboard-calendar-empty">No upcoming events</p>
      ) : (
        grouped.map(({ date, events: dayEvents }) => (
          <div key={date.toDateString()} className="dashboard-cal-agenda-day">
            <div className="dashboard-cal-agenda-daydate">{formatDateMedium(date)}</div>
            {dayEvents.map((ev) => (
              <EventRow key={ev.id} ev={ev} calendars={calendars} />
            ))}
          </div>
        ))
      )}
    </div>
  );
}

export function DashboardCalendar({ calendarId, days = 90 }: DashboardCalendarProps) {
  const [calendars, setCalendars] = useState<Calendar[]>([]);
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedDate, setSelectedDate] = useState<Date>(new Date());
  const [view, setView] = useState<View>("month");
  const [showFilters, setShowFilters] = useState(false);
  const [visibleCalendarIds, setVisibleCalendarIds] = useState<string[] | null>(null);
  const [fetchingMonth, setFetchingMonth] = useState(false);

  const fetchEvents = async (startDate: Date, endDate: Date) => {
    return listCalendarEvents({
      start: startDate.toISOString(),
      end: endDate.toISOString(),
      limit: 500,
    });
  };

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        setLoading(true);
        const [calList, evList] = await Promise.all([
          listCalendars(),
          fetchEvents(
            new Date(Date.now() - 90 * 24 * 60 * 60 * 1000),
            new Date(Date.now() + days * 24 * 60 * 60 * 1000),
          ),
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
    return () => {
      active = false;
    };
  }, [calendarId, days]);

  const handleMonthChange = async (dir: -1 | 1, newDate: Date) => {
    setFetchingMonth(true);
    try {
      const startDate = new Date(newDate.getFullYear(), newDate.getMonth(), 1);
      const endDate = new Date(newDate.getFullYear(), newDate.getMonth() + 1, 0);
      const evList = await fetchEvents(startDate, endDate);
      setEvents(evList);
      setSelectedDate(startDate);
    } catch (err) {
      console.error("Failed to fetch month events:", err);
    } finally {
      setFetchingMonth(false);
    }
  };

  const toggleCalendarFilter = (cid: string) => {
    const current = visibleCalendarIds ?? calendars.map((c) => c.id);
    const next = current.includes(cid) ? current.filter((id) => id !== cid) : [...current, cid];
    setVisibleCalendarIds(next);
  };

  const filteredEvents = visibleCalendarIds ? events.filter((ev) => visibleCalendarIds.includes(ev.calendar_id)) : events;
  const hasActiveFilter = visibleCalendarIds !== null && visibleCalendarIds.length < calendars.length;

  // Week/agenda step a week at a time; day steps one day.
  const dayStep = view === "day" ? 1 : 7;
  const onPrev = () => setSelectedDate(addDays(selectedDate, -dayStep));
  const onNext = () => setSelectedDate(addDays(selectedDate, dayStep));

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
      {/* View toggle — restored to match the calendar module */}
      <div className="dashboard-calendar-views">
        {VIEWS.map((v) => (
          <button
            key={v}
            className={`dashboard-calendar-view-btn${view === v ? " active" : ""}`}
            onClick={() => {
              setView(v);
              if (v === "month") setSelectedDate(new Date());
            }}
          >
            {v}
          </button>
        ))}
      </div>

      {view === "month" && (
        <>
          {showFilters && (
            <div className="dashboard-calendar-filters">
              <div className="dashboard-calendar-filters-header">
                <span>Show calendars</span>
                <button
                  onClick={() => setVisibleCalendarIds(calendars.map((c) => c.id))}
                  className="dashboard-calendar-filters-selectall"
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
              <MonthGrid
                events={filteredEvents}
                selectedDate={selectedDate}
                onSelectDate={setSelectedDate}
                showFilters={showFilters}
                onToggleFilters={() => setShowFilters((v) => !v)}
                hasActiveFilter={hasActiveFilter}
                calendars={calendars}
                onMonthChange={handleMonthChange}
              />
            </div>
            <div className="dashboard-calendar-agenda">
              <AgendaList events={filteredEvents} selectedDate={selectedDate} calendars={calendars} />
            </div>
          </div>
        </>
      )}

      {view === "week" && (
        <div className="dashboard-calendar-body dashboard-calendar-body-week">
          <div className="dashboard-calendar-week-strip">
            <WeekStrip
              events={filteredEvents}
              selectedDate={selectedDate}
              onSelectDate={setSelectedDate}
              calendars={calendars}
            />
          </div>
          <div className="dashboard-calendar-agenda">
            <AgendaList events={filteredEvents} selectedDate={selectedDate} calendars={calendars} />
          </div>
        </div>
      )}

      {view === "day" && (
        <div className="dashboard-calendar-body">
          <DayView
            events={filteredEvents}
            selectedDate={selectedDate}
            calendars={calendars}
            onPrev={onPrev}
            onNext={onNext}
          />
        </div>
      )}

      {view === "agenda" && (
        <div className="dashboard-calendar-body">
          <AgendaView
            events={filteredEvents}
            selectedDate={selectedDate}
            calendars={calendars}
            onPrev={onPrev}
            onNext={onNext}
          />
        </div>
      )}

      {fetchingMonth && (
        <div className="dashboard-calendar-overlay">
          <CalendarDays className="animate-spin" size={24} />
        </div>
      )}
    </div>
  );
}

// Shared agenda list (kept for the side-by-side month view). Aligns with the
// calendar module by showing start – end time on every event.
function AgendaList({ events, selectedDate, calendars }: { events: CalendarEvent[]; selectedDate: Date; calendars: Calendar[] }) {
  const dayEvents = events.filter((ev) => isSameDay(new Date(ev.start_time), selectedDate));
  const sorted = [...dayEvents].sort((a, b) => new Date(a.start_time).getTime() - new Date(b.start_time).getTime());

  return (
    <div className="dashboard-cal-agenda-side">
      <div className="dashboard-cal-agenda-daydate">
        {selectedDate.toLocaleDateString("en-HK", { weekday: "long", day: "numeric", month: "long" })}
        <span className="dashboard-cal-agenda-count">{sorted.length} events</span>
      </div>
      {sorted.length === 0 ? (
        <p className="dashboard-calendar-empty">No events for this day</p>
      ) : (
        sorted.map((ev) => <EventRow key={ev.id} ev={ev} calendars={calendars} />)
      )}
    </div>
  );
}
