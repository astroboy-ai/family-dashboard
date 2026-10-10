"use client";

import { useState, useEffect, useRef } from "react";
import { Clock, MapPin, Music, Bus, BookOpen, Utensils, Moon } from "lucide-react";

interface TimelineEvent {
  time: string;
  title: string;
  icon: React.ReactNode;
  color: string;
  location?: string;
}

const MOCK_TIMELINE: TimelineEvent[] = [
  { time: "07:00", title: "Wake up & breakfast", icon: <Utensils size={14} />, color: "#e65100" },
  { time: "08:00", title: "School starts", icon: <BookOpen size={14} />, color: "#1565c0" },
  { time: "09:30", title: "Maths class", icon: <BookOpen size={14} />, color: "#1565c0" },
  { time: "11:00", title: "Singing lesson", icon: <Music size={14} />, color: "#c62828" },
  { time: "12:30", title: "Lunch break", icon: <Utensils size={14} />, color: "#e65100" },
  { time: "14:00", title: "Violin lesson", icon: <Music size={14} />, color: "#6a1b9a" },
  { time: "15:30", title: "School ends", icon: <Bus size={14} />, color: "#e65100" },
  { time: "15:50", title: "Bus pickup", icon: <Bus size={14} />, color: "#e65100", location: "School gate" },
  { time: "16:30", title: "Piano lesson", icon: <Music size={14} />, color: "#c62828" },
  { time: "18:00", title: "Homework time", icon: <BookOpen size={14} />, color: "#1565c0" },
  { time: "19:30", title: "Dinner", icon: <Utensils size={14} />, color: "#e65100" },
  { time: "20:30", title: "Bedtime", icon: <Moon size={14} />, color: "#6a1b9a" },
];

function timeToMinutes(timeStr: string): number {
  const [h, m] = timeStr.split(":").map(Number);
  return h * 60 + m;
}

function getCurrentEventIndex(): number {
  const now = new Date();
  const nowMinutes = now.getHours() * 60 + now.getMinutes();
  
  let currentIdx = -1;
  for (let i = 0; i < MOCK_TIMELINE.length; i++) {
    if (timeToMinutes(MOCK_TIMELINE[i].time) <= nowMinutes) {
      currentIdx = i;
    }
  }
  return currentIdx;
}

function getNextEventIndex(): number {
  const now = new Date();
  const nowMinutes = now.getHours() * 60 + now.getMinutes();
  
  for (let i = 0; i < MOCK_TIMELINE.length; i++) {
    if (timeToMinutes(MOCK_TIMELINE[i].time) > nowMinutes) {
      return i;
    }
  }
  return -1;
}

export function DashboardTimeline({ childName = "Phoebe" }: { childName?: string }) {
  const [selectedEvent, setSelectedEvent] = useState<number | null>(null);
  const [currentIdx, setCurrentIdx] = useState(getCurrentEventIndex());
  const [nextIdx, setNextIdx] = useState(getNextEventIndex());
  const listRef = useRef<HTMLDivElement>(null);
  const itemRefs = useRef<(HTMLDivElement | null)[]>([]);

  // Update current/next event every minute
  useEffect(() => {
    const interval = setInterval(() => {
      setCurrentIdx(getCurrentEventIndex());
      setNextIdx(getNextEventIndex());
    }, 60000);
    return () => clearInterval(interval);
  }, []);

  // Auto-scroll to current event
  useEffect(() => {
    if (currentIdx >= 0 && itemRefs.current[currentIdx]) {
      itemRefs.current[currentIdx]?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [currentIdx]);

  return (
    <div className="dashboard-timeline">
      <div className="dashboard-timeline-header">
        <Clock size={16} />
        <span>{childName}&apos;s Day Timeline</span>
        {currentIdx >= 0 && (
          <span className="dashboard-timeline-now">
            Now: {MOCK_TIMELINE[currentIdx].title}
          </span>
        )}
      </div>
      <div className="dashboard-timeline-list" ref={listRef}>
        <div className="dashboard-timeline-line" />
        {MOCK_TIMELINE.map((event, i) => {
          const isCurrent = i === currentIdx;
          const isNext = i === nextIdx;
          const isPast = currentIdx >= 0 && i < currentIdx;
          
          return (
            <div
              key={i}
              ref={(el) => { itemRefs.current[i] = el; }}
              className={`dashboard-timeline-item${isCurrent ? " current" : ""}${isNext ? " next" : ""}${isPast ? " past" : ""}${selectedEvent === i ? " selected" : ""}`}
              onClick={() => setSelectedEvent(selectedEvent === i ? null : i)}
            >
              <div className="dashboard-timeline-time">{event.time}</div>
              <div className="dashboard-timeline-dot" style={{ backgroundColor: event.color }} />
              <div className="dashboard-timeline-content">
                <div className="dashboard-timeline-title">
                  <span className="dashboard-timeline-icon" style={{ color: event.color }}>
                    {event.icon}
                  </span>
                  {event.title}
                  {isCurrent && <span className="dashboard-timeline-badge">NOW</span>}
                  {isNext && <span className="dashboard-timeline-badge next">NEXT</span>}
                </div>
                {event.location && selectedEvent === i && (
                  <div className="dashboard-timeline-location">
                    <MapPin size={12} />
                    {event.location}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
