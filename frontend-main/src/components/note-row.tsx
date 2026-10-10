import { ArrowUpRight } from "lucide-react";
import Link from "next/link";
import type { Note } from "@/lib/api";

function shortDate(value: string) {
  return new Intl.DateTimeFormat("en", { month: "short", day: "numeric" }).format(new Date(value));
}

export function NoteRow({ note }: { note: Note }) {
  const title = note.title?.trim() || note.blocks.find((block) => block.text_content)?.text_content?.split("\n")[0] || "Untitled note";
  const snippet = note.summary || note.blocks.find((block) => block.text_content)?.text_content || "No text preview";
  return (
    <Link className="note-row" href={`/notes/${note.id}`}>
      <span className={`note-type-mark type-${note.type}`} />
      <span className="note-row-main"><strong>{title}</strong><small>{snippet.slice(0, 110)}</small></span>
      <span className="note-row-meta"><span>{note.type.replaceAll("_", " ")}</span><time dateTime={note.updated_at}>{shortDate(note.updated_at)}</time></span>
      <ArrowUpRight size={15} className="row-arrow" />
    </Link>
  );
}