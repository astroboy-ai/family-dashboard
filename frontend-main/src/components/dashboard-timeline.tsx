"use client";

import { useState } from "react";
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

export function DashboardTimeline({ childName = "Phoebe" }: { childName?: string }) {
  const [selectedEvent, setSelectedEvent] = useState<number | null>(null);

  return (
    <div className="dashboard-timeline">
      <div className="dashboard-timeline-header">
        <Clock size={16} />
        <span>{childName}&apos;s Day Timeline</span>
      </div>
      <div className="dashboard-timeline-list">
        {MOCK_TIMELINE.map((event, i) => (
          <div
            key={i}
            className={`dashboard-timeline-item${selectedEvent === i ? " selected" : ""}`}
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
              </div>
              {event.location && selectedEvent === i && (
                <div className="dashboard-timeline-location">
                  <MapPin size={12} />
                  {event.location}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
