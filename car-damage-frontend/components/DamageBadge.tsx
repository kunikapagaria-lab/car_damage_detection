'use client';

import { clsx } from 'clsx';
import type { DamageClass } from '@/types';

const CONFIG: Record<
  DamageClass,
  { label: string; bg: string; text: string; ring: string }
> = {
  scratch: {
    label: 'Scratch',
    bg: 'bg-red-950',
    text: 'text-red-400',
    ring: 'ring-red-800',
  },
  dent: {
    label: 'Dent',
    bg: 'bg-blue-950',
    text: 'text-blue-400',
    ring: 'ring-blue-800',
  },
  paint_damage: {
    label: 'Paint',
    bg: 'bg-yellow-950',
    text: 'text-yellow-400',
    ring: 'ring-yellow-800',
  },
  crack: {
    label: 'Crack',
    bg: 'bg-purple-950',
    text: 'text-purple-400',
    ring: 'ring-purple-800',
  },
};

export const DAMAGE_HEX: Record<DamageClass, string> = {
  scratch: '#EF4444',
  dent: '#3B82F6',
  paint_damage: '#EAB308',
  crack: '#A855F7',
};

interface DamageBadgeProps {
  cls: DamageClass;
  size?: 'sm' | 'md';
  showDot?: boolean;
}

export function DamageBadge({
  cls,
  size = 'md',
  showDot = false,
}: DamageBadgeProps) {
  const cfg = CONFIG[cls];
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1 rounded-full font-medium ring-1',
        cfg.bg,
        cfg.text,
        cfg.ring,
        size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-1 text-xs'
      )}
    >
      {showDot && (
        <span
          className="h-1.5 w-1.5 rounded-full"
          style={{ background: DAMAGE_HEX[cls] }}
        />
      )}
      {cfg.label}
    </span>
  );
}

const STATUS_CFG = {
  pending: 'bg-gray-800 text-gray-400 ring-gray-700',
  processing: 'bg-blue-950 text-blue-400 ring-blue-800',
  complete: 'bg-emerald-950 text-emerald-400 ring-emerald-800',
  failed: 'bg-red-950 text-red-400 ring-red-800',
} as const;

export function ScanStatusBadge({ status }: { status: string }) {
  const cls =
    STATUS_CFG[status as keyof typeof STATUS_CFG] ??
    STATUS_CFG.pending;
  return (
    <span
      className={clsx(
        'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ring-1',
        cls
      )}
    >
      {status}
    </span>
  );
}
