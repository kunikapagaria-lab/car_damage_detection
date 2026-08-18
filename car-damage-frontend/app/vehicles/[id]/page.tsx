'use client';

import { useState } from 'react';
import { notFound } from 'next/navigation';
import Link from 'next/link';
import useSWR from 'swr';
import { format } from 'date-fns';
import { clsx } from 'clsx';
import { useStore } from '@/lib/store';
import { fetcher, urls } from '@/lib/api';
import { ScanTimeline } from '@/components/ScanTimeline';
import { DiffViewer } from '@/components/DiffViewer';
import { PageHeaderSkeleton, ScanCardSkeleton } from '@/components/Skeleton';
import { InlineError } from '@/components/ErrorBoundary';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import type { Vehicle, Scan } from '@/types';

interface PageProps {
  params: { id: string };
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-gray-800 bg-gray-900 px-4 py-3">
      <p className="text-xs text-gray-500 uppercase tracking-wider">{label}</p>
      <p className="mt-1 text-lg font-bold text-gray-100">{value}</p>
    </div>
  );
}

export default function VehicleDetailPage({ params }: PageProps) {
  const { id } = params;
  const [comparisonMode, setComparisonMode] = useState(false);

  const clearComparison = useStore((s) => s.clearComparison);
  const comparisonScanIds = useStore((s) => s.comparisonScanIds);
  const bothSelected =
    comparisonScanIds[0] !== null && comparisonScanIds[1] !== null;

  const {
    data: vehicle,
    error: vError,
    isLoading: vLoading,
  } = useSWR<Vehicle>(urls.vehicle(id), fetcher);

  const {
    data: scans,
    error: sError,
    isLoading: sLoading,
  } = useSWR<Scan[]>(urls.vehicleScans(id, 50), fetcher, {
    refreshInterval: 15_000,
  });

  if (vError?.message?.includes('404')) notFound();

  return (
    <div className="mx-auto max-w-[1200px] px-6 py-8">
      {/* Breadcrumb */}
      <nav className="mb-6 text-xs text-gray-600">
        <Link href="/vehicles" className="hover:text-gray-400">
          Vehicles
        </Link>
        <span className="mx-2">›</span>
        <span className="text-gray-400">
          {vehicle?.plate_number ?? id}
        </span>
      </nav>

      {/* Header skeleton */}
      {vLoading && <PageHeaderSkeleton />}

      {vError && <InlineError message={vError.message} />}

      {vehicle && (
        <>
          {/* Vehicle header */}
          <div className="mb-6 flex items-start justify-between">
            <div>
              <h1 className="text-3xl font-bold font-mono text-gray-100 tracking-widest">
                {vehicle.plate_number}
              </h1>
              <p className="mt-1 text-xs font-mono text-gray-600">{vehicle.id}</p>
            </div>

            {/* Comparison controls */}
            <div className="flex items-center gap-3">
              {comparisonMode && bothSelected && (
                <button
                  onClick={() => {}}
                  className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-600"
                >
                  View Diff ↓
                </button>
              )}
              <button
                onClick={() => {
                  setComparisonMode((v) => !v);
                  if (comparisonMode) clearComparison();
                }}
                className={clsx(
                  'rounded-lg px-4 py-2 text-sm font-medium transition-colors',
                  comparisonMode
                    ? 'bg-gray-700 text-gray-200'
                    : 'bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-gray-200'
                )}
              >
                {comparisonMode ? '✕ Cancel compare' : '⇄ Compare scans'}
              </button>
            </div>
          </div>

          {/* Stats */}
          <div className="mb-6 grid grid-cols-3 gap-3">
            <Stat label="Total Scans" value={vehicle.total_scans} />
            <Stat
              label="First Seen"
              value={format(new Date(vehicle.first_seen), 'dd MMM yyyy')}
            />
            <Stat
              label="Last Seen"
              value={format(
                new Date(vehicle.last_seen),
                'dd MMM yyyy HH:mm'
              )}
            />
          </div>
        </>
      )}

      {/* Comparison hint */}
      {comparisonMode && (
        <div className="mb-4 rounded-lg border border-dashed border-gray-700 bg-gray-900/40 px-4 py-2.5 text-xs text-gray-500">
          {bothSelected
            ? 'Both scans selected. Scroll up to compare.'
            : comparisonScanIds[0]
            ? 'Select a second scan (B) to compare.'
            : 'Select two scans from the timeline to compare side-by-side.'}
        </div>
      )}

      {/* Diff viewer (shown when both scans selected) */}
      {comparisonMode && bothSelected && (
        <div className="mb-8">
          <ErrorBoundary>
            <DiffViewer
              scanIdOld={comparisonScanIds[0]!}
              scanIdNew={comparisonScanIds[1]!}
              onClose={clearComparison}
            />
          </ErrorBoundary>
        </div>
      )}

      {/* Scan timeline */}
      <div className="mt-4">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-gray-500">
            Scan History
          </h2>
          {scans && (
            <span className="text-xs text-gray-600">
              {scans.length} scan{scans.length !== 1 ? 's' : ''}
            </span>
          )}
        </div>

        {sLoading && (
          <div className="space-y-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <ScanCardSkeleton key={i} />
            ))}
          </div>
        )}

        {sError && <InlineError message={sError.message} />}

        {scans && (
          <ErrorBoundary>
            <ScanTimeline scans={scans} comparisonMode={comparisonMode} />
          </ErrorBoundary>
        )}
      </div>
    </div>
  );
}
