'use client';

import Link from 'next/link';
import useSWR from 'swr';
import { format } from 'date-fns';
import { fetcher, urls, minioUrl, BUCKET } from '@/lib/api';
import { Skeleton } from '@/components/Skeleton';
import { InlineError } from '@/components/ErrorBoundary';
import type { AlertLog, ScanDetail } from '@/types';

// ── Thumbnail (lazy-fetched per alert) ────────────────────────────────────────

function AlertThumbnail({ scanId }: { scanId: string }) {
  const { data } = useSWR<ScanDetail>(urls.scan(scanId), fetcher);
  const path = data?.images?.[0]?.thumbnail_path;

  return (
    <div className="h-12 w-16 shrink-0 overflow-hidden rounded-md border border-gray-800 bg-gray-950">
      {path && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={minioUrl(BUCKET.THUMBS, path)}
          alt=""
          className="h-full w-full object-cover"
        />
      )}
    </div>
  );
}

// ── Alert card ────────────────────────────────────────────────────────────────

function AlertCard({ alert }: { alert: AlertLog }) {
  return (
    <div className="flex items-center gap-4 rounded-xl border border-gray-800 bg-gray-900/50 p-3">
      <AlertThumbnail scanId={alert.scan_id} />

      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
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
  const { data: alerts, error, isLoading } = useSWR<AlertLog[]>(
    urls.alerts(30),
    fetcher,
    { refreshInterval: 30_000 }
  );

  return (
    <div className="mx-auto max-w-[900px] px-6 py-8">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-100">Alert Feed</h1>
        <p className="mt-1 text-sm text-gray-500">
          Fires the moment a returning vehicle shows damage that wasn&apos;t
          there on its last scan — wire this to your team&apos;s Slack, email,
          or ticketing system via webhook for rental returns, insurance
          handoffs, or fleet check-ins.
        </p>
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
        {alerts?.map((alert) => (
          <AlertCard key={alert.id} alert={alert} />
        ))}
        {alerts?.length === 0 && (
          <p className="rounded-xl border border-dashed border-gray-800 py-12 text-center text-sm text-gray-600">
            No alerts yet — they&apos;ll show up here the moment a scan finds
            new damage on a returning vehicle.
          </p>
        )}
      </div>
    </div>
  );
}
