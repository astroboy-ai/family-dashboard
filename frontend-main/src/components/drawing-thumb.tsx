"use client";

import { useEffect, useRef } from "react";

export type ThumbStroke = {
  id?: string;
  color: string;
  width: number;
  points: { x: number; y: number }[];
};

const BACKGROUNDS: Record<string, string> = {
  whiteboard: "#f9f8f2",
  chalkboard_black: "#131817",
  chalkboard_green: "#183a2d",
};

/**
 * Read-only canvas that replays a drawing block's strokes at thumbnail size.
 *
 * Drawn from the stored stroke data on every change rather than from a saved
 * image, so the preview can never drift from the real board and no extra
 * column or storage is needed. Stroke count stays small in practice, so the
 * cost is negligible.
 */
export function DrawingThumb({
  strokes,
  theme,
  canvas,
}: {
  strokes: ThumbStroke[];
  theme: string;
  canvas: { width: number; height: number };
}) {
  const ref = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ctx = el.getContext("2d");
    if (!ctx) return;

    const width = canvas.width || 900;
    const height = canvas.height || 640;
    el.width = width;
    el.height = height;

    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = BACKGROUNDS[theme] ?? BACKGROUNDS.chalkboard_green;
    ctx.fillRect(0, 0, width, height);

    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    for (const stroke of strokes) {
      if (!stroke.points?.length) continue;
      ctx.strokeStyle = stroke.color;
      ctx.lineWidth = stroke.width;
      ctx.beginPath();
      ctx.moveTo(stroke.points[0].x, stroke.points[0].y);
      for (const point of stroke.points.slice(1)) ctx.lineTo(point.x, point.y);
      // A single tap would otherwise draw nothing at all.
      if (stroke.points.length === 1) {
        ctx.lineTo(stroke.points[0].x + 0.1, stroke.points[0].y);
      }
      ctx.stroke();
    }
  }, [strokes, theme, canvas]);

  return <canvas ref={ref} className="drawing-thumb-canvas" aria-hidden="true" />;
}
