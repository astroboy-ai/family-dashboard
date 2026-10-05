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

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

function getDaysInMonth(year: number, month: number): number {
  return new Date(year, month + 1, 0).getDate();
}

function getFirstDayOfMonth(year: number, month: number): number {
  const day = new Date(year, month, 1).getDay();
  return day === 0 ? 6 : day - 1; // Monday = 0
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", hour12: true });
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function isSameDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

function getWeekDays(date: Date): Date[] {
  const start = new Date(date);
  const day = start.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  start.setDate(start.getDate() + diff);
  return Array.from({ length: 7 }, (_, i) => {
    const d = new Date(start);
    d.setDate(d.getDate() + i);
    return d;
  });
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
        const weekDays = getWeekDays(currentDate);
        return weekDays.some((d) => isSameDay(d, evtDate));
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
      {/* Header */}
      <div className="flex items-center justify-between border-b border-[var(--border)] px-4 py-3">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold text-[var(--foreground)]">Calendar</h1>
          <div className="flex items-center gap-1">
            <button onClick={() => navigate(-1)} className="rounded-lg p-2 hover:bg-[var(--muted)]">
              <ChevronLeft size={18} />
            </button>
            <button onClick={goToday} className="rounded-lg px-3 py-1.5 text-sm font-medium hover:bg-[var(--muted)]">
              Today
            </button>
            <button onClick={() => navigate(1)} className="rounded-lg p-2 hover:bg-[var(--muted)]">
              <ChevronRight size={18} />
            </button>
          </div>
          <span className="text-sm font-medium text-[var(--muted)]">
            {view === "month" && `${MONTHS[currentDate.getMonth()]} ${currentDate.getFullYear()}`}
            {view === "week" && `Week of ${formatDate(getWeekDays(currentDate)[0].toISOString())}`}
            {view === "day" && currentDate.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" })}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex rounded-lg border border-[var(--border)] p-0.5">
            {(["month", "week", "day"] as const).map((v) => (
              <button
                key={v}
                onClick={() => setView(v)}
                className={`rounded-md px-3 py-1 text-xs font-medium capitalize ${
                  view === v ? "bg-[var(--primary)] text-white" : "text-[var(--muted)] hover:text-[var(--foreground)]"
                }`}
              >
                {v}
              </button>
            ))}
          </div>
          <button onClick={handleSync} disabled={syncing} className="rounded-lg p-2 hover:bg-[var(--muted)]">
            <RefreshCw size={16} className={syncing ? "animate-spin" : ""} />
          </button>
          <button onClick={() => router.push("/calendar/settings")} className="rounded-lg p-2 hover:bg-[var(--muted)]">
            <Settings size={16} />
          </button>
          <button
            onClick={() => {
              setSelectedDate(new Date());
              setShowNewEvent(true);
            }}
            className="flex items-center gap-1.5 rounded-lg bg-[var(--primary)] px-3 py-2 text-sm font-medium text-white"
          >
            <Plus size={16} />
            <span className="hidden sm:inline">New Event</span>
          </button>
        </div>
      </div>

      {/* Calendar Body */}
      <div className="flex-1 overflow-auto">
        {view === "month" && (
          <MonthView
            currentDate={currentDate}
            eventsByDate={eventsByDate}
            calendarColor={calendarColor}
            onSelectDate={(d) => {
              setSelectedDate(d);
              setShowNewEvent(true);
            }}
            onDeleteEvent={handleDeleteEvent}
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
            onDeleteEvent={handleDeleteEvent}
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
            onDeleteEvent={handleDeleteEvent}
          />
        )}
      </div>

      {/* New Event Modal */}
      {showNewEvent && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={() => setShowNewEvent(false)}>
          <div className="w-full max-w-md rounded-2xl bg-[var(--background)] p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-semibold">New Event</h2>
              <button onClick={() => setShowNewEvent(false)} className="rounded-lg p-1 hover:bg-[var(--muted)]">
                <X size={18} />
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="mb-1 block text-sm font-medium text-[var(--muted)]">Title</label>
                <input
                  type="text"
                  value={newEvent.title}
                  onChange={(e) => setNewEvent({ ...newEvent, title: e.target.value })}
                  className="w-full rounded-lg border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm"
                  placeholder="Event title"
                />
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-[var(--muted)]">Description</label>
                <textarea
                  value={newEvent.description}
                  onChange={(e) => setNewEvent({ ...newEvent, description: e.target.value })}
                  className="w-full rounded-lg border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm"
                  rows={2}
                  placeholder="Optional description"
                />
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={newEvent.all_day}
                  onChange={(e) => setNewEvent({ ...newEvent, all_day: e.target.checked })}
                  className="rounded"
                />
                <label className="text-sm">All day</label>
              </div>
              {!newEvent.all_day && (
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="mb-1 block text-sm font-medium text-[var(--muted)]">Start</label>
                    <input
                      type="datetime-local"
                      value={newEvent.start_time}
                      onChange={(e) => setNewEvent({ ...newEvent, start_time: e.target.value })}
                      className="w-full rounded-lg border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm"
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-sm font-medium text-[var(--muted)]">End</label>
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
                <label className="mb-1 block text-sm font-medium text-[var(--muted)]">Location</label>
                <input
                  type="text"
                  value={newEvent.location}
                  onChange={(e) => setNewEvent({ ...newEvent, location: e.target.value })}
                  className="w-full rounded-lg border border-[var(--border)] bg-[var(--background)] px-3 py-2 text-sm"
                  placeholder="Optional location"
                />
              </div>
              <button
                onClick={handleCreateEvent}
                disabled={!newEvent.title}
                className="w-full rounded-lg bg-[var(--primary)] py-2.5 text-sm font-medium text-white disabled:opacity-50"
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

// ── Month View ────────────────────────────────────────────────────────────────

function MonthView({
  currentDate,
  eventsByDate,
  calendarColor,
  onSelectDate,
  onDeleteEvent,
}: {
  currentDate: Date;
  eventsByDate: Map<string, CalendarEvent[]>;
  calendarColor: (id: string) => string;
  onSelectDate: (d: Date) => void;
  onDeleteEvent: (id: string) => void;
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
    <div className="flex h-full flex-col">
      <div className="grid grid-cols-7 border-b border-[var(--border)]">
        {WEEKDAYS.map((d) => (
          <div key={d} className="px-2 py-2 text-center text-xs font-medium text-[var(--muted)]">
            {d}
          </div>
        ))}
      </div>
      <div className="grid flex-1 grid-cols-7">
        {cells.map((date, i) => {
          if (!date) return <div key={i} className="border-b border-r border-[var(--border)]" />;
          const dayEvents = eventsByDate.get(date.toDateString()) || [];
          const isToday = isSameDay(date, today);
          return (
            <div
              key={i}
              onClick={() => onSelectDate(date)}
              className="min-h-[80px] cursor-pointer border-b border-r border-[var(--border)] p-1.5 transition-colors hover:bg-[var(--muted)]"
            >
              <div className="mb-1 flex items-center justify-between">
                <span
                  className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-medium ${
                    isToday ? "bg-[var(--primary)] text-white" : "text-[var(--foreground)]"
                  }`}
                >
                  {date.getDate()}
                </span>
              </div>
              <div className="space-y-0.5">
                {dayEvents.slice(0, 3).map((e) => (
                  <div
                    key={e.id}
                    className="truncate rounded px-1.5 py-0.5 text-[10px] font-medium text-white"
                    style={{ backgroundColor: calendarColor(e.calendar_id) }}
                    title={e.title}
                  >
                    {!e.all_day && <span className="mr-1 opacity-75">{formatTime(e.start_time)}</span>}
                    {e.title}
                  </div>
                ))}
                {dayEvents.length > 3 && (
                  <div className="px-1.5 text-[10px] text-[var(--muted)]">+{dayEvents.length - 3} more</div>
                )}
              </div>
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
  onDeleteEvent,
}: {
  currentDate: Date;
  events: CalendarEvent[];
  calendarColor: (id: string) => string;
  onSelectDate: (d: Date) => void;
  onDeleteEvent: (id: string) => void;
}) {
  const weekDays = getWeekDays(currentDate);
  const hours = Array.from({ length: 24 }, (_, i) => i);

  return (
    <div className="flex h-full flex-col">
      <div className="grid grid-cols-[60px_repeat(7,1fr)] border-b border-[var(--border)]">
        <div className="border-r border-[var(--border)]" />
        {weekDays.map((d, i) => (
          <div key={i} className="border-r border-[var(--border)] px-2 py-2 text-center">
            <div className="text-xs text-[var(--muted)]">{WEEKDAYS[i]}</div>
            <div className="text-sm font-semibold">{d.getDate()}</div>
          </div>
        ))}
      </div>
      <div className="flex-1 overflow-auto">
        {hours.map((hour) => (
          <div key={hour} className="grid grid-cols-[60px_repeat(7,1fr)] border-b border-[var(--border)]">
            <div className="border-r border-[var(--border)] px-2 py-1 text-right text-xs text-[var(--muted)]">
              {hour === 0 ? "" : `${hour}:00`}
            </div>
            {weekDays.map((day, di) => {
              const dayEvents = events.filter((e) => {
                const evtDate = new Date(e.start_time);
                return isSameDay(evtDate, day) && evtDate.getHours() === hour;
              });
              return (
                <div
                  key={di}
                  onClick={() => onSelectDate(day)}
                  className="min-h-[40px] cursor-pointer border-r border-[var(--border)] p-0.5 hover:bg-[var(--muted)]"
                >
                  {dayEvents.map((e) => (
                    <div
                      key={e.id}
                      className="mb-0.5 truncate rounded px-1 py-0.5 text-[10px] font-medium text-white"
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
  onDeleteEvent,
}: {
  currentDate: Date;
  events: CalendarEvent[];
  calendarColor: (id: string) => string;
  onSelectDate: (d: Date) => void;
  onDeleteEvent: (id: string) => void;
}) {
  const hours = Array.from({ length: 24 }, (_, i) => i);

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-[var(--border)] px-4 py-3">
        <div className="text-lg font-semibold">
          {currentDate.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" })}
        </div>
      </div>
      <div className="flex-1 overflow-auto">
        {hours.map((hour) => {
          const hourEvents = events.filter((e) => {
            const evtDate = new Date(e.start_time);
            return evtDate.getHours() === hour;
          });
          return (
            <div key={hour} className="flex border-b border-[var(--border)]">
              <div className="w-20 shrink-0 border-r border-[var(--border)] px-2 py-2 text-right text-xs text-[var(--muted)]">
                {hour === 0 ? "" : `${hour}:00`}
              </div>
              <div className="flex-1 p-1">
                {hourEvents.map((e) => (
                  <div
                    key={e.id}
                    className="mb-1 rounded-lg p-2 text-white"
                    style={{ backgroundColor: calendarColor(e.calendar_id) }}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium">{e.title}</span>
                      <button
                        onClick={() => onDeleteEvent(e.id)}
                        className="rounded p-0.5 opacity-70 hover:opacity-100"
                      >
                        <X size={12} />
                      </button>
                    </div>
                    {e.location && (
                      <div className="mt-0.5 flex items-center gap-1 text-xs opacity-80">
                        <MapPin size={10} />
                        {e.location}
                      </div>
                    )}
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
