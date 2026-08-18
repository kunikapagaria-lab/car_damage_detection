'use client';

import {
  useRef,
  useEffect,
  useState,
  useCallback,
  type MouseEvent,
} from 'react';
import { clsx } from 'clsx';
import { DAMAGE_HEX } from '@/components/DamageBadge';
import type { DamageAnnotation } from '@/types';

interface TooltipState {
  cssX: number;
  cssY: number;
  annotation: DamageAnnotation;
}

interface DamageCanvasProps {
  /** Full URL of the image to render. Null = dark placeholder with grid */
  imageUrl: string | null;
  damages: DamageAnnotation[];
  /** "Before" damages drawn in neutral gray — used by DiffViewer */
  oldDamages?: DamageAnnotation[];
  className?: string;
  onAnnotationClick?: (a: DamageAnnotation) => void;
}

// ── Drawing helpers ───────────────────────────────────────────────────────────

const REFLECTION_WARNING_COLOR = '#F59E0B'; // amber
const REFLECTION_THRESHOLD = 0.45;

function drawAnnotation(
  ctx: CanvasRenderingContext2D,
  a: DamageAnnotation,
  color: string,
  alpha = 0.22
) {
  const [x1, y1, x2, y2] = a.bbox;
  const w = x2 - x1;
  const h = y2 - y1;

  const isReflection = (a.reflectionScore ?? 0) >= REFLECTION_THRESHOLD;
  const drawColor    = isReflection ? REFLECTION_WARNING_COLOR : color;
  const drawAlpha    = isReflection ? 0.12 : alpha;

  // Polygon fill
  if (a.polygon.length >= 3) {
    ctx.save();
    ctx.globalAlpha = drawAlpha;
    ctx.fillStyle = drawColor;
    ctx.beginPath();
    ctx.moveTo(a.polygon[0][0], a.polygon[0][1]);
    for (let i = 1; i < a.polygon.length; i++) {
      ctx.lineTo(a.polygon[i][0], a.polygon[i][1]);
    }
    ctx.closePath();
    ctx.fill();
    ctx.restore();

    // Polygon stroke — dashed for reflections
    ctx.save();
    ctx.globalAlpha = 0.75;
    ctx.strokeStyle = drawColor;
    ctx.lineWidth = 1.5;
    ctx.setLineDash(isReflection ? [4, 4] : []);
    ctx.beginPath();
    ctx.moveTo(a.polygon[0][0], a.polygon[0][1]);
    for (let i = 1; i < a.polygon.length; i++) {
      ctx.lineTo(a.polygon[i][0], a.polygon[i][1]);
    }
    ctx.closePath();
    ctx.stroke();
    ctx.restore();
  }

  // Bounding box — long dashes for reflections, short for damage
  ctx.save();
  ctx.strokeStyle = drawColor;
  ctx.lineWidth = isReflection ? 1.5 : 2;
  ctx.setLineDash(isReflection ? [6, 6] : [6, 3]);
  ctx.strokeRect(x1, y1, w, h);
  ctx.restore();

  // Label pill
  const baseLabel = a.className.replace('_', ' ');
  const confStr   = `${(a.confidence * 100).toFixed(0)}%`;
  const label     = isReflection
    ? `⚠ ${baseLabel} ${confStr} (reflection?)`
    : `${baseLabel} ${confStr}`;

  const fontSize = Math.max(10, Math.min(14, w / 8));
  ctx.font = `600 ${fontSize}px ui-monospace,monospace`;
  const tw = ctx.measureText(label).width;
  const ph = fontSize + 6;
  const pw = tw + 10;

  ctx.save();
  ctx.fillStyle = drawColor;
  ctx.globalAlpha = isReflection ? 0.75 : 0.9;
  ctx.beginPath();
  ctx.roundRect(x1, Math.max(0, y1 - ph - 2), pw, ph, 3);
  ctx.fill();
  ctx.restore();

  ctx.fillStyle = '#000';
  ctx.font = `600 ${fontSize}px ui-monospace,monospace`;
  ctx.fillText(label, x1 + 5, Math.max(fontSize, y1 - 5));
}

function drawPlaceholder(
  ctx: CanvasRenderingContext2D,
  w: number,
  h: number,
  angle: string
) {
  ctx.fillStyle = '#0f172a';
  ctx.fillRect(0, 0, w, h);

  ctx.strokeStyle = '#1e293b';
  ctx.lineWidth = 1;
  const step = 64;
  for (let x = 0; x <= w; x += step) {
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, h);
    ctx.stroke();
  }
  for (let y = 0; y <= h; y += step) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(w, y);
    ctx.stroke();
  }

  ctx.fillStyle = '#334155';
  ctx.font = 'bold 18px ui-monospace,monospace';
  ctx.textAlign = 'center';
  ctx.fillText(angle.toUpperCase().replace('_', ' '), w / 2, h / 2);
  ctx.textAlign = 'left';
}

// ── Component ─────────────────────────────────────────────────────────────────

export function DamageCanvas({
  imageUrl,
  damages,
  oldDamages = [],
  className,
  onAnnotationClick,
}: DamageCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const loadedImgRef = useRef<HTMLImageElement | null>(null);
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);

  const redraw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    if (loadedImgRef.current) {
      ctx.drawImage(loadedImgRef.current, 0, 0);
    } else {
      drawPlaceholder(ctx, canvas.width, canvas.height, '');
    }

    // Old damages in neutral gray
    for (const a of oldDamages) {
      drawAnnotation(ctx, a, '#94a3b8', 0.18);
    }
    // Current damages in class color
    for (const a of damages) {
      drawAnnotation(ctx, a, DAMAGE_HEX[a.className]);
    }
  }, [damages, oldDamages]);

  // Load image & set canvas resolution
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    if (!imageUrl) {
      canvas.width = 1280;
      canvas.height = 720;
      loadedImgRef.current = null;
      redraw();
      return;
    }

    const img = new Image();
    img.crossOrigin = 'anonymous';
    let cancelled = false;

    img.onload = () => {
      if (cancelled) return;
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
      loadedImgRef.current = img;
      redraw();
    };
    img.onerror = () => {
      if (cancelled) return;
      canvas.width = 1280;
      canvas.height = 720;
      loadedImgRef.current = null;
      redraw();
    };
    img.src = imageUrl;

    return () => {
      cancelled = true;
    };
  }, [imageUrl, redraw]);

  // Redraw overlays whenever damages change without reloading image
  useEffect(() => {
    redraw();
  }, [redraw]);

  // Mouse hover hit-test
  const handleMouseMove = useCallback(
    (e: MouseEvent<HTMLCanvasElement>) => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      const sx = canvas.width / rect.width;
      const sy = canvas.height / rect.height;
      const cx = (e.clientX - rect.left) * sx;
      const cy = (e.clientY - rect.top) * sy;

      const all = [...damages, ...oldDamages];
      const hit = all.find(
        (a) =>
          cx >= a.bbox[0] &&
          cx <= a.bbox[2] &&
          cy >= a.bbox[1] &&
          cy <= a.bbox[3]
      );

      setTooltip(
        hit
          ? { cssX: e.clientX - rect.left, cssY: e.clientY - rect.top, annotation: hit }
          : null
      );
    },
    [damages, oldDamages]
  );

  const handleClick = useCallback(
    (e: MouseEvent<HTMLCanvasElement>) => {
      if (!onAnnotationClick) return;
      const canvas = canvasRef.current;
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      const sx = canvas.width / rect.width;
      const sy = canvas.height / rect.height;
      const cx = (e.clientX - rect.left) * sx;
      const cy = (e.clientY - rect.top) * sy;

      const hit = damages.find(
        (a) =>
          cx >= a.bbox[0] &&
          cx <= a.bbox[2] &&
          cy >= a.bbox[1] &&
          cy <= a.bbox[3]
      );
      if (hit) onAnnotationClick(hit);
    },
    [damages, onAnnotationClick]
  );

  return (
    <div className={clsx('relative select-none', className)}>
      <canvas
        ref={canvasRef}
        onMouseMove={handleMouseMove}
        onMouseLeave={() => setTooltip(null)}
        onClick={handleClick}
        className="w-full h-auto block cursor-crosshair"
      />
      {tooltip && (
        <div
          className="pointer-events-none absolute z-20 rounded-md border border-gray-700 bg-gray-900/95 px-2.5 py-1.5 text-xs shadow-xl backdrop-blur-sm space-y-0.5"
          style={{ left: tooltip.cssX + 14, top: tooltip.cssY - 10 }}
        >
          <div className="flex items-center gap-2">
            <span className="font-semibold text-gray-100">
              {tooltip.annotation.className.replace('_', ' ')}
            </span>
            <span className="text-gray-400">
              {(tooltip.annotation.confidence * 100).toFixed(1)}%
            </span>
            {tooltip.annotation.isNew === true && (
              <span className="rounded bg-red-900 px-1 text-red-300">NEW</span>
            )}
          </div>
          {(tooltip.annotation.reflectionScore ?? 0) >= REFLECTION_THRESHOLD && (
            <div className="text-amber-400 font-semibold">
              ⚠ Possible light reflection — verify before saving
              <span className="ml-2 text-amber-600 font-normal">
                ({Math.round((tooltip.annotation.reflectionScore ?? 0) * 100)}% glare score)
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
