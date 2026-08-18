'use client';

import { useState, useMemo } from 'react';
import Link from 'next/link';
import useSWR from 'swr';
import { format } from 'date-fns';
import { clsx } from 'clsx';
import { useStore } from '@/lib/store';
import { useWebSocketFeed } from '@/lib/hooks';
import { fetcher, urls, minioUrl, BUCKET } from '@/lib/api';
import { DamageBadge, DAMAGE_HEX } from '@/components/DamageBadge';
import { Skeleton } from '@/components/Skeleton';
import { InlineError } from '@/components/ErrorBoundary';
import type { AlertLog, DamageClass, WSInspectionFrame } from '@/types';

// ── Filters ───────────────────────────────────────────────────────────────────

const ALL_CLASSES: DamageClass[] = ['scratch', 'dent', 'paint_damage', 'crack'];

interface Filters {
  classes: Set<DamageClass>;
  minConfidence: number;
}

function FilterBar({
  filters,
  onChange,
}: {
  filters: Filters;
  onChange: (f: Filters) => void;
}) {
  function toggleClass(cls: DamageClass) {
    const next = new Set(filters.classes);
    if (next.has(cls)) {
      next.delete(cls);
    } else {
      next.add(cls);
    }
    onChange({ ...filters, classes: next });
  }

  return (
    <div className="flex flex-wrap items-center gap-4 rounded-xl border border-gray-800 bg-gray-900 px-4 py-3">
      <span className="text-xs font-semibold uppercase tracking-wider text-gray-500">
        Filters
      </span>

      {/* Class toggles */}
      <div className="flex gap-2">
        {ALL_CLASSES.map((cls) => (
          <button
            key={cls}
            onClick={() => toggleClass(cls)}
            style={{
              borderColor: filters.classes.has(cls) ? DAMAGE_HEX[cls] : '#374151',
              color: filters.classes.has(cls) ? DAMAGE_HEX[cls] : '#6b7280',
            }}
            className="rounded-full border px-3 py-0.5 text-xs font-medium transition-colors"
          >
            {cls.replace('_', ' ')}
          </button>
        ))}
      </div>

      <div className="h-4 w-px bg-gray-800" />

      {/* Confidence slider */}
      <div className="flex items-center gap-2">
        <span className="text-xs text-gray-500">Min confidence</span>
        <input
          type="range"
          min={0}
          max={100}
          step={5}
          value={Math.round(filters.minConfidence * 100)}
          onChange={(e) =>
            onChange({ ...filters, minConfidence: Number(e.target.value) / 100 })
          }
          className="w-28 accent-emerald-500"
        />
        <span className="w-8 text-right text-xs font-mono text-gray-300">
          {Math.round(filters.minConfidence * 100)}%
        </span>
      </div>

      <button
        onClick={() =>
          onChange({ classes: new Set(ALL_CLASSES), minConfidence: 0 })
        }
        className="ml-auto text-xs text-gray-600 hover:text-gray-400"
      >
        Reset
      </button>
    </div>
  );
}

// ── Live alert card (from WebSocket) ─────────────────────────────────────────

function LiveAlertCard({ frame }: { frame: WSInspectionFrame }) {
  const topDamage = frame.damages[0];
  const color = topDamage
    ? DAMAGE_HEX[topDamage.class_name as DamageClass]
    : '#94a3b8';

  return (
    <div className="animate-fade-in flex items-start gap-4 rounded-xl border border-gray-800 bg-gray-900 p-4">
      {/* Color bar */}
      <div className="h-full w-1 rounded-full flex-shrink-0" style={{ background: color, minHeight: 48 }} />

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-mono text-sm font-bold text-gray-100">
            {frame.plate?.plate_text ?? 'Unknown Plate'}
          </span>
          <span className="rounded-full bg-gray-800 px-2 py-0.5 text-[10px] text-gray-400">
            {frame.angle.replace('_', ' ')}
          </span>
          <span className="ml-auto rounded-full bg-emerald-950 px-2 py-0.5 text-[10px] font-bold text-emerald-400">
            LIVE
          </span>
        </div>

        <div className="mt-2 flex flex-wrap gap-1.5">
          {frame.damages.map((d) => (
            <span
              key={d.annotation_id}
              className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium"
              style={{
                background: DAMAGE_HEX[d.class_name as DamageClass] + '22',
                color: DAMAGE_HEX[d.class_name as DamageClass],
              }}
            >
              {d.class_name.replace('_', ' ')}
              <span className="opacity-70">
                {(d.confidence * 100).toFixed(0)}%
              </span>
            </span>
          ))}
        </div>
      </div>

      <div className="text-right flex-shrink-0">
        <p className="text-xs text-gray-500">
          {format(new Date(frame.captured_at), 'HH:mm:ss')}
        </p>
        <p className="mt-1 text-xs text-gray-600">
          {frame.n_damages} detection{frame.n_damages !== 1 ? 's' : ''}
        </p>
      </div>
    </div>
  );
}

// ── Historical alert card (from REST API) ─────────────────────────────────────

function HistoricalAlertCard({ alert }: { alert: AlertLog }) {
  return (
    <div className="flex items-start gap-4 rounded-xl border border-gray-800 bg-gray-900/50 p-4">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-mono text-sm font-bold text-gray-200">
            {alert.payload_summary.plate_number}
          </span>
          <span className="ml-auto text-xs text-gray-600">
            {format(new Date(alert.triggered_at), 'dd MMM HH:mm:ss')}
          </span>
        </div>
        <div className="mt-1 flex items-center gap-2">
          <span className="text-xs text-gray-500">
            {alert.payload_summary.new_damage_count} new damage
            {alert.payload_summary.new_damage_count !== 1 ? 's' : ''}
          </span>
          <Link
            href={`/scans/${alert.scan_id}`}
            className="text-xs text-emerald-500 hover:text-emerald-400"
          >
            View scan →
          </Link>
        </div>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function AlertsPage() {
  useWebSocketFeed();

  const liveAlerts = useStore((s) =>
    s.alertQueue.filter((f) => f.n_damages > 0)
  );

  const [filters, setFilters] = useState<Filters>({
    classes: new Set(ALL_CLASSES),
    minConfidence: 0,
  });

  const { data: historical, error, isLoading } = useSWR<AlertLog[]>(
    urls.alerts(100),
    fetcher,
    { refreshInterval: 30_000 }
  );

  // Filter live alerts
  const filteredLive = useMemo(
    () =>
      liveAlerts.filter((f) =>
        f.damages.some(
          (d) =>
            filters.classes.has(d.class_name as DamageClass) &&
            d.confidence >= filters.minConfidence
        )
      ),
    [liveAlerts, filters]
  );

  return (
    <div className="mx-auto max-w-[900px] px-6 py-8">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-100">Alert Feed</h1>
        <p className="mt-1 text-sm text-gray-500">
          Real-time new damage detections from active inspections
        </p>
      </div>

      <FilterBar filters={filters} onChange={setFilters} />

      {/* Live section */}
      <div className="mt-6 mb-2 flex items-center gap-2">
        <span className="h-2 w-2 rounded-full bg-red-500 animate-pulse" />
        <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-500">
          Live — {filteredLive.length} alert{filteredLive.length !== 1 ? 's' : ''}
        </h2>
      </div>

      <div className="space-y-2">
        {filteredLive.length === 0 && (
          <p className="rounded-xl border border-dashed border-gray-800 py-8 text-center text-sm text-gray-600">
            No live alerts matching filters
          </p>
        )}
        {filteredLive.map((f) => (
          <LiveAlertCard key={f.frame_hash} frame={f} />
        ))}
      </div>

      {/* Historical section */}
      <div className="mt-8 mb-2">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-500">
          Historical
        </h2>
      </div>

      {isLoading && (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full rounded-xl" />
          ))}
        </div>
      )}

      {error && <InlineError message={error.message} />}

      <div className="space-y-2">
        {historical?.map((alert) => (
          <HistoricalAlertCard key={alert.id} alert={alert} />
        ))}
        {historical?.length === 0 && (
          <p className="py-8 text-center text-sm text-gray-600">
            No historical alerts yet.
          </p>
        )}
      </div>
    </div>
  );
}
