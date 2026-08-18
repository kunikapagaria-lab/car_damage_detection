'use client';

import { useRef } from 'react';
import { clsx } from 'clsx';
import { useStore } from '@/lib/store';
import { useInView } from '@/lib/hooks';
import { DamageCanvas } from '@/components/DamageCanvas';
import { DamageBadge } from '@/components/DamageBadge';
import { wsDamageToAnnotation } from '@/types';
import type { CameraAngle } from '@/types';

const ANGLE_LABELS: Record<CameraAngle, string> = {
  front: 'Front',
  rear: 'Rear',
  left: 'Left',
  right: 'Right',
  front_oblique: 'Front ◣',
  rear_oblique: 'Rear ◣',
};

interface LiveFeedCardProps {
  cameraId: string;
  angle: CameraAngle;
}

export function LiveFeedCard({ cameraId, angle }: LiveFeedCardProps) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { threshold: 0.1 });
  const frame = useStore((s) => s.frames[cameraId]);

  const damages = frame
    ? frame.damages.map(wsDamageToAnnotation)
    : [];

  const hasNewDamage = (frame?.n_damages ?? 0) > 0;

  return (
    <div
      ref={ref}
      className={clsx(
        'group relative flex flex-col overflow-hidden rounded-xl border bg-gray-900 transition-all duration-300',
        hasNewDamage
          ? 'border-red-700 shadow-lg shadow-red-950/40'
          : 'border-gray-800 hover:border-gray-700'
      )}
    >
      {/* Card header */}
      <div className="flex items-center justify-between border-b border-gray-800 px-3 py-2">
        <span className="text-xs font-semibold uppercase tracking-widest text-gray-400">
          {ANGLE_LABELS[angle]}
        </span>
        <div className="flex items-center gap-2">
          {hasNewDamage && (
            <span className="animate-pulse rounded-full bg-red-700 px-2 py-0.5 text-[10px] font-bold text-red-100">
              {frame?.n_damages} DMG
            </span>
          )}
          <span
            className={clsx(
              'h-2 w-2 rounded-full',
              frame ? 'bg-emerald-400' : 'bg-gray-600'
            )}
            title={frame ? 'Active' : 'No signal'}
          />
        </div>
      </div>

      {/* Canvas area */}
      {inView && (
        <DamageCanvas
          imageUrl={null}
          damages={damages}
          className="aspect-video bg-gray-950"
        />
      )}

      {/* Footer: plate + timestamp */}
      <div className="flex items-center justify-between px-3 py-2 text-xs text-gray-500">
        <span className="font-mono font-semibold tracking-wide text-gray-300">
          {frame?.plate?.plate_text ?? '—'}
        </span>
        <span>
          {frame
            ? new Date(frame.captured_at).toLocaleTimeString('en-IN', {
                hour12: false,
              })
            : 'Waiting…'}
        </span>
      </div>

      {/* Damage class pills */}
      {damages.length > 0 && (
        <div className="flex flex-wrap gap-1 border-t border-gray-800 px-3 py-2">
          {damages.slice(0, 4).map((a) => (
            <DamageBadge key={a.id} cls={a.className} size="sm" showDot />
          ))}
          {damages.length > 4 && (
            <span className="text-[10px] text-gray-500 self-center">
              +{damages.length - 4} more
            </span>
          )}
        </div>
      )}
    </div>
  );
}
