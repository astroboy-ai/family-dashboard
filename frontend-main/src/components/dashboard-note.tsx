"use client";

import { useEffect, useState } from "react";
import { FileText, Image as ImageIcon, CheckSquare, Table, MapPin, Clock } from "lucide-react";
import { getNote, type Note, type NoteBlock } from "@/lib/api";

interface DashboardNoteProps {
  noteId: string | null;
  title?: string;
}

function BlockContent({ block }: { block: NoteBlock }) {
  switch (block.type) {
    case "text":
      return (
        <div className="dashboard-note-text">
          {block.text_content}
        </div>
      );
    case "image":
      return (
        <div className="dashboard-note-image">
          <ImageIcon size={20} />
          <span>{block.caption || "Image"}</span>
        </div>
      );
    case "checkbox":
      return (
        <div className="dashboard-note-checkbox">
          <CheckSquare size={16} />
          <span>{block.text_content}</span>
        </div>
      );
    case "table":
      return (
        <div className="dashboard-note-table">
          <Table size={16} />
          <span>{block.caption || "Table"}</span>
        </div>
      );
    case "location":
      return (
        <div className="dashboard-note-location">
          <MapPin size={16} />
          <span>{block.text_content || block.caption || "Location"}</span>
        </div>
      );
    case "date":
    case "time":
      return (
        <div className="dashboard-note-datetime">
          <Clock size={16} />
          <span>{block.text_content || block.caption || block.type}</span>
        </div>
      );
    default:
      return (
        <div className="dashboard-note-default">
          <FileText size={16} />
          <span>{block.text_content || block.caption || block.type}</span>
        </div>
      );
  }
}

export function DashboardNote({ noteId, title }: DashboardNoteProps) {
  const [note, setNote] = useState<Note | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!noteId) {
      setNote(null);
      return;
    }
    let active = true;
    async function load() {
      try {
        setLoading(true);
        const data = await getNote(noteId!);
        if (!active) return;
        setNote(data);
        setError(null);
      } catch (err) {
        if (!active) return;
        setError(err instanceof Error ? err.message : "Failed to load note");
      } finally {
        if (active) setLoading(false);
      }
    }
    load();
    return () => { active = false; };
  }, [noteId]);

  if (!noteId) {
    return (
      <div className="dashboard-note-empty">
        <FileText size={32} />
        <p>No note selected</p>
        <p className="dashboard-note-hint">Agent will assign a note here</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="dashboard-note-loading">
        <FileText className="animate-spin" size={24} />
        <p>Loading note…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="dashboard-note-error">
        <p>⚠️ {error}</p>
      </div>
    );
  }

  if (!note) {
    return (
      <div className="dashboard-note-empty">
        <FileText size={32} />
        <p>Note not found</p>
      </div>
    );
  }

  return (
    <div className="dashboard-note">
      <div className="dashboard-note-header">
        <h3 className="dashboard-note-title">{note.title || title || "Untitled"}</h3>
        {note.summary && (
          <p className="dashboard-note-summary">{note.summary}</p>
        )}
      </div>
      <div className="dashboard-note-blocks">
        {note.blocks.length === 0 ? (
          <p className="dashboard-note-empty-blocks">No content in this note</p>
        ) : (
          note.blocks.map((block) => (
            <BlockContent key={block.id} block={block} />
          ))
        )}
      </div>
    </div>
  );
}
