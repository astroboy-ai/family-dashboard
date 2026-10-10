"use client";

import { useState } from "react";
import { GraduationCap, Music, Music2, Bus, Shirt, MessageSquare } from "lucide-react";

interface DashboardSchoolProps {
  childName?: string;
}

export function DashboardSchool({ childName = "Phoebe" }: DashboardSchoolProps) {
  const [note, setNote] = useState("");

  return (
    <div className="dashboard-school">
      <div className="dashboard-school-header">
        <GraduationCap size={18} />
        <span>{childName}&apos;s School Day</span>
      </div>
      <div className="dashboard-school-grid">
        {/* Uniform */}
        <div className="dashboard-school-item">
          <div className="dashboard-school-icon uniform">
            <Shirt size={14} />
          </div>
        </div>

        {/* Singing lesson */}
        <div className="dashboard-school-item">
          <div className="dashboard-school-icon music">
            <Music size={14} />
          </div>
        </div>

        {/* Violin lesson */}
        <div className="dashboard-school-item">
          <div className="dashboard-school-icon violin">
            <Music2 size={14} />
          </div>
        </div>

        {/* School bus */}
        <div className="dashboard-school-item">
          <div className="dashboard-school-icon bus">
            <Bus size={14} />
          </div>
          <div className="dashboard-school-time">3:50 PM</div>
        </div>
      </div>
      <div className="dashboard-school-notes">
        <div className="dashboard-school-notes-header">
          <MessageSquare size={14} />
          <span>Notes</span>
        </div>
        <textarea
          className="dashboard-school-textarea"
          placeholder="Extra notes..."
          value={note || "Remember to bring water bottle\nPiano lesson at 4pm\nViolin practice 30min\nPE kit needed tomorrow\nLunch money $25\nLibrary book due Friday\nMaths homework page 42\nScience project next week\nSwimming lesson Thursday\nParent meeting 6pm"}
          onChange={(e) => setNote(e.target.value)}
          rows={10}
        />
      </div>
    </div>
  );
}
