'use client';

import { useStore } from '@/lib/store';
import { DAMAGE_HEX } from '@/components/DamageBadge';
import type { WSInspectionFrame } from '@/types';

function TickerItem({ frame }: { frame: WSInspectionFrame }) {
  const topDmg = frame.damages[0];
  const color = topDmg
    ? DAMAGE_HEX[topDmg.class_name as keyof typeof DAMAGE_HEX] ?? '#94a3b8'
    : '#94a3b8';

  return (
    <span className="inline-flex shrink-0 items-center gap-2 border-r border-gray-800 pr-8 mr-8">
      <span className="font-mono text-xs font-bold text-gray-100">
        {frame.plate?.plate_text ?? '???'}
      </span>
      <span className="text-gray-500 text-xs">·</span>
      <span className="text-xs uppercase tracking-wider text-gray-400">
        {frame.angle.replace('_', ' ')}
      </span>
      {topDmg && (
        <>
          <span className="text-gray-500 text-xs">·</span>
          <span className="text-xs font-semibold" style={{ color }}>
            {topDmg.class_name.replace('_', ' ')} {(topDmg.confidence * 100).toFixed(0)}%
          </span>
        </>
      )}
      <span className="text-gray-600 text-[10px]">
        {new Date(frame.captured_at).toLocaleTimeString('en-IN', { hour12: false })}
      </span>
    </span>
  );
}

function NoAlertsMessage() {
  return (
    <span className="text-xs text-gray-600 italic">
      No damage alerts yet — monitoring live feed…
    </span>
  );
}

export function AlertTicker() {
  const queue = useStore((s) => s.alertQueue);

  // Only show frames that had damage
  const alerts = queue.filter((f) => f.n_damages > 0);

  return (
    <div className="flex h-9 items-center overflow-hidden border-t border-gray-800 bg-gray-950/80 backdrop-blur-sm">
      {/* Label */}
      <div className="flex h-full shrink-0 items-center gap-2 border-r border-gray-800 bg-red-950/40 px-3">
        <span className="text-red-400 text-[10px] font-bold uppercase tracking-widest">
          ● Alerts
        </span>
      </div>

      {/* Scrolling content */}
      <div className="relative flex-1 overflow-hidden">
        {alerts.length === 0 ? (
          <div className="flex h-full items-center px-4">
            <NoAlertsMessage />
          </div>
        ) : (
          <div className="flex animate-ticker items-center whitespace-nowrap px-4 py-1.5">
            {/* Duplicate for seamless loop */}
            {[...alerts, ...alerts].map((frame, i) => (
              <TickerItem key={`${frame.frame_hash}-${i}`} frame={frame} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
