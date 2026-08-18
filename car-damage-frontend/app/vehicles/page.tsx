'use client';

import { useState, useRef } from 'react';
import Link from 'next/link';
import useSWR from 'swr';
import {
  LineChart,
  Line,
  ResponsiveContainer,
} from 'recharts';
import { format } from 'date-fns';
import { clsx } from 'clsx';
import { useDebounce, useInView } from '@/lib/hooks';
import { fetcher, vehiclesUrl } from '@/lib/api';
import { PlateSearch } from '@/components/PlateSearch';
import { VehicleRowSkeleton } from '@/components/Skeleton';
import { InlineError } from '@/components/ErrorBoundary';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import type { Vehicle } from '@/types';

// ── Sparkline (damage trend placeholder) ──────────────────────────────────────

function DamageTrendSpark({ total }: { total: number }) {
  // Generate a plausible increasing trend from total_scans
  const data = Array.from({ length: 7 }, (_, i) => ({
    v: Math.max(0, Math.round((total / 7) * i + Math.random() * 2)),
  }));
  return (
    <ResponsiveContainer width={80} height={28}>
      <LineChart data={data} margin={{ top: 2, bottom: 2, left: 0, right: 0 }}>
        <Line
          type="monotone"
          dataKey="v"
          stroke="#10b981"
          strokeWidth={1.5}
          dot={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

// ── Vehicle row ───────────────────────────────────────────────────────────────

function VehicleRow({ v }: { v: Vehicle }) {
  const ref = useRef<HTMLTableRowElement>(null);
  const inView = useInView(ref, { rootMargin: '200px' });

  return (
    <tr
      ref={ref}
      className="border-t border-gray-800 hover:bg-gray-900/60 transition-colors"
    >
      <td className="px-4 py-3">
        <Link
          href={`/vehicles/${v.id}`}
          className="font-mono text-sm font-bold text-emerald-400 hover:text-emerald-300"
        >
          {v.plate_number}
        </Link>
      </td>
      <td className="px-4 py-3 text-xs text-gray-400">
        {format(new Date(v.first_seen), 'dd MMM yyyy')}
      </td>
      <td className="px-4 py-3 text-xs text-gray-400">
        {format(new Date(v.last_seen), 'dd MMM yyyy HH:mm')}
      </td>
      <td className="px-4 py-3 text-sm font-semibold text-gray-200">
        {v.total_scans}
      </td>
      <td className="px-4 py-3">
        {inView && <DamageTrendSpark total={v.total_scans} />}
      </td>
      <td className="px-4 py-3">
        <span
          className={clsx(
            'rounded-full px-2.5 py-0.5 text-xs font-medium',
            v.total_scans === 0
              ? 'bg-gray-800 text-gray-500'
              : 'bg-emerald-950 text-emerald-400 ring-1 ring-emerald-800'
          )}
        >
          {v.total_scans === 0 ? 'New' : 'Active'}
        </span>
      </td>
    </tr>
  );
}

// ── Vehicles table ────────────────────────────────────────────────────────────

interface VehiclesTableProps {
  plate: string;
  page: number;
  onPageChange: (p: number) => void;
}

function VehiclesTable({ plate, page, onPageChange }: VehiclesTableProps) {
  const limit = 20;
  const { data, error, isLoading, mutate } = useSWR<Vehicle[]>(
    vehiclesUrl({ plate: plate || undefined, page, limit }),
    fetcher,
    { refreshInterval: 30_000 }
  );

  if (isLoading) {
    return (
      <table className="w-full">
        <tbody>
          {Array.from({ length: 8 }).map((_, i) => (
            <VehicleRowSkeleton key={i} />
          ))}
        </tbody>
      </table>
    );
  }
  if (error) return <InlineError message={error.message} onRetry={() => mutate()} />;
  if (!data || data.length === 0) {
    return (
      <div className="py-16 text-center text-sm text-gray-600">
        {plate ? `No vehicles matching "${plate}"` : 'No vehicles registered yet.'}
      </div>
    );
  }

  return (
    <>
      <table className="w-full text-left">
        <thead className="sticky top-0 bg-gray-950">
          <tr className="border-b border-gray-800 text-xs uppercase tracking-wider text-gray-500">
            <th className="px-4 py-3">Plate</th>
            <th className="px-4 py-3">First Seen</th>
            <th className="px-4 py-3">Last Seen</th>
            <th className="px-4 py-3">Scans</th>
            <th className="px-4 py-3">Trend</th>
            <th className="px-4 py-3">Status</th>
          </tr>
        </thead>
        <tbody>
          {data.map((v) => (
            <VehicleRow key={v.id} v={v} />
          ))}
        </tbody>
      </table>

      {/* Pagination */}
      <div className="flex items-center justify-between border-t border-gray-800 px-4 py-3 text-xs text-gray-500">
        <span>Page {page}</span>
        <div className="flex gap-2">
          <button
            disabled={page === 1}
            onClick={() => onPageChange(page - 1)}
            className="rounded px-3 py-1 hover:bg-gray-800 disabled:opacity-30"
          >
            ← Prev
          </button>
          <button
            disabled={data.length < limit}
            onClick={() => onPageChange(page + 1)}
            className="rounded px-3 py-1 hover:bg-gray-800 disabled:opacity-30"
          >
            Next →
          </button>
        </div>
      </div>
    </>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function VehiclesPage() {
  const [plate, setPlate] = useState('');
  const [page, setPage] = useState(1);
  const debounced = useDebounce(plate, 350);

  function handlePlateChange(val: string) {
    setPlate(val);
    setPage(1);
  }

  return (
    <div className="mx-auto max-w-[1400px] px-6 py-8">
      {/* Header */}
      <div className="mb-6 flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-100">Vehicle Registry</h1>
          <p className="mt-1 text-sm text-gray-500">
            All vehicles inspected through the system
          </p>
        </div>
        <PlateSearch
          onSelect={(v) => setPlate(v.plate_number)}
          className="w-72"
          placeholder="Filter by plate…"
        />
      </div>

      {/* Filter chips */}
      {plate && (
        <div className="mb-4 flex items-center gap-2">
          <span className="text-xs text-gray-500">Filtered by:</span>
          <span className="flex items-center gap-1 rounded-full bg-gray-800 px-3 py-1 text-xs font-mono font-semibold text-gray-200">
            {plate}
            <button
              onClick={() => handlePlateChange('')}
              className="ml-1 text-gray-500 hover:text-gray-300"
            >
              ✕
            </button>
          </span>
        </div>
      )}

      {/* Table card */}
      <div className="overflow-hidden rounded-xl border border-gray-800 bg-gray-900">
        <ErrorBoundary>
          <VehiclesTable
            plate={debounced}
            page={page}
            onPageChange={setPage}
          />
        </ErrorBoundary>
      </div>
    </div>
  );
}
