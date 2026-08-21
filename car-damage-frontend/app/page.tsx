'use client';

import Link from 'next/link';
import useSWR from 'swr';
import { formatDistanceToNow } from 'date-fns';
import { fetcher, urls, minioUrl, BUCKET } from '@/lib/api';
import { InlineError } from '@/components/ErrorBoundary';
import { Skeleton } from '@/components/Skeleton';
import type { DashboardSummary, RecentScanSummary } from '@/types';

// ── Stat tile ─────────────────────────────────────────────────────────────────

function StatTile({
  label,
  value,
  accent = 'text-gray-100',
}: {
  label: string;
  value: number;
  accent?: string;
}) {
  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
      <p className="text-xs font-bold uppercase tracking-wider text-gray-500">{label}</p>
      <p className={`mt-1 text-3xl font-black ${accent}`}>{value.toLocaleString()}</p>
    </div>
  );
}

// ── Recent activity row ──────────────────────────────────────────────────────

function RecentActivityRow({ item }: { item: RecentScanSummary }) {
  return (
    <Link
      href={`/scans/${item.scan_id}`}
      className="flex items-center gap-3 rounded-lg border border-gray-800 bg-gray-900/60 px-3 py-2.5 hover:border-gray-700 transition-colors"
    >
      <div className="h-12 w-16 shrink-0 overflow-hidden rounded-md border border-gray-800 bg-gray-950">
        {item.thumbnail_path && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={minioUrl(BUCKET.THUMBS, item.thumbnail_path)}
            alt=""
            className="h-full w-full object-cover"
          />
        )}
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate font-mono text-sm font-bold text-gray-100">{item.plate_number}</p>
        <p className="text-xs text-gray-500">
          {formatDistanceToNow(new Date(item.triggered_at), { addSuffix: true })}
        </p>
      </div>
      {item.new_damage_count > 0 ? (
        <span className="shrink-0 rounded-full bg-red-900/60 px-2.5 py-0.5 text-xs font-semibold text-red-300">
          {item.new_damage_count} new
        </span>
      ) : (
        <span className="shrink-0 rounded-full bg-gray-800 px-2.5 py-0.5 text-xs text-gray-500">
          clean
        </span>
      )}
    </Link>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const { data, error, isLoading, mutate } = useSWR<DashboardSummary>(
    urls.dashboard(),
    fetcher,
    { refreshInterval: 30_000 }
  );

  return (
    <div className="mx-auto max-w-[1400px] px-6 py-8">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-100">Fleet Overview</h1>
          <p className="mt-1 text-sm text-gray-500">
            Damage detection summary across your inspected fleet
          </p>
        </div>
        <div className="flex gap-2">
          <Link
            href="/upload"
            className="rounded-lg border border-emerald-700 bg-emerald-800/60 px-4 py-2 text-sm font-semibold text-emerald-300 hover:bg-emerald-800"
          >
            + New Inspection
          </Link>
          <Link
            href="/vehicles"
            className="rounded-lg border border-gray-700 bg-gray-900 px-4 py-2 text-sm text-gray-300 hover:bg-gray-800"
          >
            View Fleet
          </Link>
        </div>
      </div>

      {error && <InlineError message={error.message} onRetry={() => mutate()} />}

      {isLoading && (
        <div className="mb-8 grid grid-cols-2 gap-4 md:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24 rounded-xl" />
          ))}
        </div>
      )}

      {data && (
        <>
          <div className="mb-8 grid grid-cols-2 gap-4 md:grid-cols-4">
            <StatTile label="Vehicles Inspected" value={data.total_vehicles} />
            <StatTile label="Total Scans" value={data.total_scans} />
            <StatTile label="Damages Detected" value={data.total_damages} accent="text-amber-400" />
            <StatTile
              label="Active Alerts"
              value={data.active_alerts}
              accent={data.active_alerts > 0 ? 'text-red-400' : 'text-gray-100'}
            />
          </div>

          <div className="rounded-xl border border-gray-800 bg-gray-900 p-5">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-sm font-bold uppercase tracking-wider text-gray-400">
                Recent Activity
              </h2>
              <Link href="/alerts" className="text-xs text-emerald-400 hover:text-emerald-300">
                View all alerts →
              </Link>
            </div>

            {data.recent_scans.length === 0 ? (
              <p className="py-8 text-center text-sm text-gray-600">
                No scans yet — upload your first inspection to get started.
              </p>
            ) : (
              <div className="space-y-2">
                {data.recent_scans.map((item) => (
                  <RecentActivityRow key={item.scan_id} item={item} />
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
