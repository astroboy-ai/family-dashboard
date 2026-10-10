"use client";

import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";
import { createNote } from "@/lib/api";

/**
 * Create an empty note and open the shared note editor.
 *
 * Used by every "capture" / "new note" entry point so there is a single editing
 * surface: the user lands straight in the note view where the tools drawer,
 * blocks and fullscreen controls live, instead of a separate capture dialog.
 */
export function useNewNote() {
  const router = useRouter();
  const [creating, setCreating] = useState(false);

  const startNewNote = useCallback(async () => {
    if (creating) return;
    setCreating(true);
    try {
      const note = await createNote({ title: "", blocks: [] });
      router.push(`/notes/${note.id}`);
    } catch {
      // Leave the user where they are; the API layer surfaces session problems.
      setCreating(false);
    }
  }, [creating, router]);

  return { startNewNote, creating };
}
