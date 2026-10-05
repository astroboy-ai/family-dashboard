"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ChevronLeft,
  ChevronRight,
  Plus,
  Settings,
  RefreshCw,
  MapPin,
  Clock,
  X,
} from "lucide-react";
import {
  listCalendars,
  listCalendarEvents,
  createCalendarEvent,
  deleteCalendarEvent,
  syncCalendars,
  type Calendar,
  type CalendarEvent,
} from "@/lib/api";

const WEEKDAYS = ["S", "M", "T", "W", "T", "F", "S"];
const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

function getDaysInMonth(year: number, month: number): number {
  return new Date(year, month + 1, 0).getDate();
}

function getFirstDayOfMonth(year: number, month: number): number {
  return new Date(year, month, 1).getDay();
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", hour12: true });
}

function formatDateShort(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

function isSameDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

export default function CalendarPage() {
  const router = useRouter();
  const [calendars, setCalendars] = useState<Calendar[]>([]);
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [currentDate, setCurrentDate] = useState(new Date());
  const [view, setView] = useState<"month" | "week" | "day">("month");
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [showNewEvent, setShowNewEvent] = useState(false);
  const [selectedDate, setSelectedDate] = useState<Date | null>(null);
  const [newEvent, setNewEvent] = useState({
    title: "",
    description: "",
    start_time: "",
    end_time: "",
    all_day: false,
    location: "",
  });

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [calData, evtData] = await Promise.all([
        listCalendars(),
        listCalendarEvents({ limit: 500 }),
      ]);
      setCalendars(calData);
      setEvents(evtData);
    } catch (err) {
      console.error("Failed to fetch calendar data:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleSync = async () => {
    setSyncing(true);
    try {
      await syncCalendars();
      await fetchData();
    } catch (err) {
      console.error("Sync failed:", err);
    } finally {
      setSyncing(false);
    }
  };

  const handleCreateEvent = async () => {
    if (!selectedDate || !newEvent.title) return;
    const calendarId = calendars[0]?.id;
    if (!calendarId) return;

    const start = newEvent.all_day
      ? selectedDate.toISOString().split("T")[0]
      : newEvent.start_time || selectedDate.toISOString();
    const end = newEvent.all_day
      ? selectedDate.toISOString().split("T")[0]
      : newEvent.end_time || new Date(selectedDate.getTime() + 3600000).toISOString();

    try {
      await createCalendarEvent({
        calendar_id: calendarId,
        title: newEvent.title,
        description: newEvent.description || undefined,
        start_time: start,
        end_time: end,
        all_day: newEvent.all_day,
        location: newEvent.location || undefined,
      });
      setShowNewEvent(false);
      setNewEvent({ title: "", description: "", start_time: "", end_time: "", all_day: false, location: "" });
      await fetchData();
    } catch (err) {
      console.error("Failed to create event:", err);
    }
  };

  const handleDeleteEvent = async (eventId: string) => {
    try {
      await deleteCalendarEvent(eventId);
      await fetchData();
    } catch (err) {
      console.error("Failed to delete event:", err);
    }
  };

  const navigate = (dir: -1 | 1) => {
    const d = new Date(currentDate);
    if (view === "month") d.setMonth(d.getMonth() + dir);
    else if (view === "week") d.setDate(d.getDate() + dir * 7);
    else d.setDate(d.getDate() + dir);
    setCurrentDate(d);
  };

  const goToday = () => setCurrentDate(new Date());

  const visibleEvents = useMemo(() => {
    return events.filter((e) => {
      const evtDate = new Date(e.start_time);
      if (view === "month") {
        return evtDate.getMonth() === currentDate.getMonth() && evtDate.getFullYear() === currentDate.getFullYear();
      } else if (view === "week") {
        const start = new Date(currentDate);
        const day = start.getDay();
        const diff = day === 0 ? -6 : 1 - day;
        start.setDate(start.getDate() + diff);
        const end = new Date(start);
        end.setDate(end.getDate() + 7);
        return evtDate >= start && evtDate < end;
      } else {
        return isSameDay(evtDate, currentDate);
      }
    });
  }, [events, currentDate, view]);

  const eventsByDate = useMemo(() => {
    const map = new Map<string, CalendarEvent[]>();
    for (const e of visibleEvents) {
      const key = new Date(e.start_time).toDateString();
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(e);
    }
    return map;
  }, [visibleEvents]);

  const calendarColor = (calendarId: string): string => {
    const cal = calendars.find((c) => c.id === calendarId);
    return cal?.color || "#6366f1";
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="animate-pulse text-[var(--muted)]">Loading calendar...</div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col bg-[var(--background)]">
      {/* Header - iOS style */}
      <div className="flex items-center justify-between px-4 py-2">
        <div className="flex items-center gap-2">
          <button onClick={() => navigate(-1)} className="rounded-full p-1.5 hover:bg-[var(--muted)]">
            <ChevronLeft size={20} />
          </button>
          <button onClick={goToday} className="rounded-full px-2 py-1 text-sm font-medium text-[var(--primary)] hover:bg-[var(--muted)]">
            Today
          </button>
          <button onClick={() => navigate(1)} className="rounded-full p-1.5 hover:bg-[var(--muted)]">
            <ChevronRight size={20} />
          </button>
        </div>
        <span className="text-base font-semibold text-[var(--foreground)]">
          {MONTHS[currentDate.getMonth()]} {currentDate.getFullYear()}
        </span>
        <div className="flex items-center gap-1">
          <button onClick={handleSync} disabled={syncing} className="rounded-full p-1.5 hover:bg-[var(--muted)]">
            <RefreshCw size={16} className={syncing ? "animate-spin" : ""} />
          </button>
          <button onClick={() => router.push("/calendar/settings")} className="rounded-full p-1.5 hover:bg-[var(--muted)]">
            <Settings size={16} />
          </button>
          <button
            onClick={() => {
              setSelectedDate(new Date());
              setShowNewEvent(true);
            }}
            className="rounded-full bg-[var(--primary)] p-1.5 text-white"
          >
            <Plus size={16} />
          </button>
        </div>
      </div>

      {/* View Toggle - iOS segmented control */}
      <div className="flex justify-center px-4 pb-2">
        <div className="flex rounded-lg bg-[var(--muted)] p-0.5">
          {(["month", "week", "day"] as const).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={`rounded-md px-4 py-1 text-xs font-medium capitalize transition-colors ${
                view === v ? "bg-[var(--background)] text-[var(--foreground)] shadow-sm" : "text-[var(--muted)]"
              }`}
            >
              {v}
            </button>
          ))}
        </div>
      </div>

      {/* Calendar Body - iOS style: grid on top, events below */}
      <div className="flex-1 overflow-auto pb-20">
        {view === "month" && (
          <MonthView
            currentDate={currentDate}
            eventsByDate={eventsByDate}
            calendarColor={calendarColor}
            onSelectDate={(d) => {
              setSelectedDate(d);
              setShowNewEvent(true);
            }}
          />
        )}
        {view === "week" && (
          <WeekView
            currentDate={currentDate}
            events={visibleEvents}
            calendarColor={calendarColor}
            onSelectDate={(d) => {
              setSelectedDate(d);
              setShowNewEvent(true);
            }}
          />
        )}
        {view === "day" && (
          <DayView
            currentDate={currentDate}
            events={visibleEvents}
            calendarColor={calendarColor}
            onSelectDate={(d) => {
              setSelectedDate(d);
              setShowNewEvent(true);
            }}
          />
        )}

        {/* Events List - iOS style below grid */}
        <div className="mt-4 px-4">
          <h3 className="mb-2 text-sm font-semibold text-[var(--muted)]">
            {visibleEvents.length} event{visibleEvents.length !== 1 ? "s" : ""}
          </h3>
          <div className="space-y-2">
            {visibleEvents.length === 0 && (
              <div className="rounded-xl border border-dashed border-[var(--border)] p-6 text-center text-sm text-[var(--muted)]">
                No events
              </div>
            )}
            {visibleEvents.map((e) => (
              <div
                key={e.id}
                className="flex items-start gap-3 rounded-xl border border-[var(--border)] p-3"
              >
                <div
                  className="mt-0.5 h-10 w-1 rounded-full"
                  style={{ backgroundColor: calendarColor(e.calendar_id) }}
                />
                <div className="flex-1 min-w-0">
                  <div className="flex items-start justify-between gap-2">
                    <span className="text-sm font-medium text-[var(--foreground)] truncate">{e.title}</span>
                    <button
                      onClick={() => handleDeleteEvent(e.id)}
                      className="shrink-0 rounded p-1 hover:bg-[var(--muted)]"
                    >
                      <X size={12} className="text-[var(--muted)]" />
                    </button>
                  </div>
                  <div className="mt-0.5 flex items-center gap-2 text-xs text-[var(--muted)]">
                    <Clock size={10} />
                    <span>
                      {e.all_day
                        ? "All day"
                        : `${formatTime(e.start_time)} – ${formatTime(e.end_time)}`}
                    </span>
                    <span>·</span>
                    <span>{formatDateShort(e.start_time)}</span>
                  </div>
                  {e.location && (
                    <div className="mt-0.5 flex items-center gap-1 text-xs text-[var(--muted)]">
                      <MapPin size={10} />
                      <span className="truncate">{e.location}</span>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* New Event Modal - iOS style bottom sheet */}
      {showNewEvent && (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/50" onClick={() => setShowNewEvent(false)}>
          <div
            className="w-full max-w-lg rounded-t-2xl bg-[var(--background)] p-6 pb-8 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mx-auto mb-4 h-1 w-10 rounded-full bg-[var(--muted)]" />
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold">New Event</h2>
              <button onClick={() => setShowNewEvent(false)} className="rounded-full p-1 hover:bg-[var(--muted)]">
                <X size={18} />
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <input
                  type="text"
                  value={newEvent.title}
                  onChange={(e) => setNewEvent({ ...newEvent, title: e.target.value })}
                  className="w-full rounded-lg border border-[var(--border)] bg-[var(--background)] px-3 py-2.5 text-sm"
                  placeholder="Event title"
                  autoFocus
                />
              </div>
              <div>
                <textarea
                  value={newEvent.description}
                  onChange={(e) => setNewEvent({ ...newEvent, description: e.target.value })}
                  className="w-full rounded-lg border border-[var(--border)] bg-[var(--background)] px-3 py-2.5 text-sm"
                  rows={2}
                  placeholder="Description (optional)"
                />
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={newEvent.all_day}
                  onChange={(e) => setNewEvent({ ...newEvent, all_day: e.target.checked })}
                  className="h-4 w-4 rounded"
                />
                <label className="text-sm">All day</label>
              </div>
              {!newEvent.all_day && (
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="mb-1 block text-xs font-medium text-[var(--muted)]">Start</label>
                    <input
                      type="datetime-local"
                      value={newEvent.start_time}
                      onChange={(e) => setNewEvent({ ...newEvent, start_time: e.target.value })}
                      className="w-full rounded-lg border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm"
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-[var(--muted)]">End</label>
                    <input
                      type="datetime-local"
                      value={newEvent.end_time}
                      onChange={(e) => setNewEvent({ ...newEvent, end_time: e.target.value })}
                      className="w-full rounded-lg border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm"
                    />
                  </div>
                </div>
              )}
              <div>
                <input
                  type="text"
                  value={newEvent.location}
                  onChange={(e) => setNewEvent({ ...newEvent, location: e.target.value })}
                  className="w-full rounded-lg border border-[var(--border)] bg-[var(--background)] px-3 py-2.5 text-sm"
                  placeholder="Location (optional)"
                />
              </div>
              <button
                onClick={handleCreateEvent}
                disabled={!newEvent.title}
                className="w-full rounded-xl bg-[var(--primary)] py-3 text-sm font-semibold text-white disabled:opacity-40"
              >
                Create Event
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Month View - iOS compact grid ─────────────────────────────────────────────

function MonthView({
  currentDate,
  eventsByDate,
  calendarColor,
  onSelectDate,
}: {
  currentDate: Date;
  eventsByDate: Map<string, CalendarEvent[]>;
  calendarColor: (id: string) => string;
  onSelectDate: (d: Date) => void;
}) {
  const year = currentDate.getFullYear();
  const month = currentDate.getMonth();
  const daysInMonth = getDaysInMonth(year, month);
  const firstDay = getFirstDayOfMonth(year, month);
  const today = new Date();

  const cells: (Date | null)[] = [];
  for (let i = 0; i < firstDay; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(new Date(year, month, d));
  while (cells.length % 7 !== 0) cells.push(null);

  return (
    <div className="px-4">
      {/* Weekday headers */}
      <div className="grid grid-cols-7 mb-1">
        {WEEKDAYS.map((d, i) => (
          <div key={i} className="py-1 text-center text-[10px] font-medium text-[var(--muted)]">
            {d}
          </div>
        ))}
      </div>
      {/* Grid */}
      <div className="grid grid-cols-7 gap-px">
        {cells.map((date, i) => {
          if (!date) return <div key={i} className="aspect-square" />;
          const dayEvents = eventsByDate.get(date.toDateString()) || [];
          const isToday = isSameDay(date, today);
          const hasEvents = dayEvents.length > 0;
          return (
            <div
              key={i}
              onClick={() => onSelectDate(date)}
              className="flex aspect-square cursor-pointer flex-col items-center justify-center rounded-lg hover:bg-[var(--muted)]"
            >
              <span
                className={`flex h-7 w-7 items-center justify-center rounded-full text-xs font-medium ${
                  isToday ? "bg-[var(--primary)] text-white" : "text-[var(--foreground)]"
                }`}
              >
                {date.getDate()}
              </span>
              {hasEvents && (
                <div className="mt-0.5 flex gap-0.5">
                  {dayEvents.slice(0, 3).map((e) => (
                    <div
                      key={e.id}
                      className="h-1 w-1 rounded-full"
                      style={{ backgroundColor: calendarColor(e.calendar_id) }}
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

// ── Week View ─────────────────────────────────────────────────────────────────

function WeekView({
  currentDate,
  events,
  calendarColor,
  onSelectDate,
}: {
  currentDate: Date;
  events: CalendarEvent[];
  calendarColor: (id: string) => string;
  onSelectDate: (d: Date) => void;
}) {
  const start = new Date(currentDate);
  const day = start.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  start.setDate(start.getDate() + diff);
  const weekDays = Array.from({ length: 7 }, (_, i) => {
    const d = new Date(start);
    d.setDate(d.getDate() + i);
    return d;
  });
  const hours = Array.from({ length: 24 }, (_, i) => i);

  return (
    <div className="px-4">
      {/* Weekday headers */}
      <div className="grid grid-cols-[40px_repeat(7,1fr)] gap-px mb-1">
        <div />
        {weekDays.map((d, i) => {
          const isToday = isSameDay(d, new Date());
          return (
            <div key={i} className="flex flex-col items-center py-1">
              <span className="text-[10px] text-[var(--muted)]">{WEEKDAYS[i]}</span>
              <span
                className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-medium ${
                  isToday ? "bg-[var(--primary)] text-white" : ""
                }`}
              >
                {d.getDate()}
              </span>
            </div>
          );
        })}
      </div>
      {/* Time grid */}
      <div className="grid grid-cols-[40px_repeat(7,1fr)] gap-px">
        {hours.map((hour) => (
          <div key={hour} className="contents">
            <div className="flex items-start justify-end pr-1 pt-0.5 text-[9px] text-[var(--muted)]">
              {hour === 0 ? "" : `${hour}`}
            </div>
            {weekDays.map((day, di) => {
              const hourEvents = events.filter((e) => {
                const evtDate = new Date(e.start_time);
                return isSameDay(evtDate, day) && evtDate.getHours() === hour;
              });
              return (
                <div
                  key={di}
                  onClick={() => onSelectDate(day)}
                  className="min-h-[30px] cursor-pointer border-t border-[var(--border)] hover:bg-[var(--muted)]"
                >
                  {hourEvents.map((e) => (
                    <div
                      key={e.id}
                      className="truncate rounded px-1 py-0.5 text-[9px] font-medium text-white"
                      style={{ backgroundColor: calendarColor(e.calendar_id) }}
                    >
                      {e.title}
                    </div>
                  ))}
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Day View ──────────────────────────────────────────────────────────────────

function DayView({
  currentDate,
  events,
  calendarColor,
  onSelectDate,
}: {
  currentDate: Date;
  events: CalendarEvent[];
  calendarColor: (id: string) => string;
  onSelectDate: (d: Date) => void;
}) {
  const hours = Array.from({ length: 24 }, (_, i) => i);

  return (
    <div className="px-4">
      <div className="mb-2 text-center text-sm font-medium text-[var(--muted)]">
        {currentDate.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" })}
      </div>
      <div className="space-y-px">
        {hours.map((hour) => {
          const hourEvents = events.filter((e) => {
            const evtDate = new Date(e.start_time);
            return evtDate.getHours() === hour;
          });
          return (
            <div key={hour} className="flex gap-3">
              <div className="w-10 shrink-0 pt-1 text-right text-[10px] text-[var(--muted)]">
                {hour === 0 ? "" : `${hour}:00`}
              </div>
              <div className="flex-1 min-h-[40px] border-t border-[var(--border)] py-1">
                {hourEvents.map((e) => (
                  <div
                    key={e.id}
                    className="mb-1 rounded-lg p-2 text-white"
                    style={{ backgroundColor: calendarColor(e.calendar_id) }}
                  >
                    <div className="text-xs font-medium">{e.title}</div>
                    <div className="text-[10px] opacity-80">
                      {formatTime(e.start_time)} – {formatTime(e.end_time)}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
