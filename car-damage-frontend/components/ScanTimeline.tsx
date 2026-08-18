'use client';

import { useState, useCallback } from 'react';
import Link from 'next/link';
import { format } from 'date-fns';
import { clsx } from 'clsx';
import useSWR from 'swr';
import { useStore } from '@/lib/store';
import { ScanStatusBadge } from '@/components/DamageBadge';
import { ScanDetailSkeleton } from '@/components/Skeleton';
import { InlineError } from '@/components/ErrorBoundary';
import { DamageCanvas } from '@/components/DamageCanvas';
import { fetcher, urls, minioUrl, BUCKET } from '@/lib/api';
import { recordToAnnotation } from '@/types';
import type { Scan, ScanDetail } from '@/types';

// ── Inline scan detail (lazy loaded when expanded) ────────────────────────────

function InlineScanDetail({ scanId }: { scanId: string }) {
  const { data, error, isLoading } = useSWR<ScanDetail>(
    urls.scan(scanId),
    fetcher
  );

  if (isLoading) return <ScanDetailSkeleton />;
  if (error) return <InlineError message={error.message} />;
  if (!data) return null;

  const firstImage = data.images[0];
  const annotations = data.damage_records.map(recordToAnnotation);
  const newCount = annotations.filter((a) => a.isNew === true).length;

  return (
    <div className="mt-3 space-y-4 animate-fade-in">
      {/* Image strip */}
      {data.images.length > 0 && (
        <div className="flex gap-3 overflow-x-auto pb-2 scrollbar-hide">
          {data.images.map((img) => {
            const url = minioUrl(BUCKET.FULL, img.full_image_path);
            const imgAnnotations = data.damage_records
              .filter((r) => r.scan_image_id === img.id)
              .map(recordToAnnotation);
            return (
              <div
                key={img.id}
                className="flex-shrink-0 w-52 rounded-lg overflow-hidden border border-gray-800"
              >
                <DamageCanvas
                  imageUrl={url}
                  damages={imgAnnotations}
                  className="w-full"
                />
                <p className="px-2 py-1 text-[10px] text-gray-500 uppercase tracking-wider">
                  {img.camera_angle.replace('_', ' ')}
                </p>
              </div>
            );
          })}
        </div>
      )}

      {/* Summary row */}
      <div className="flex items-center gap-4 text-sm">
        <span className="text-gray-400">
          <span className="font-semibold text-gray-100">
            {data.damage_records.length}
          </span>{' '}
          damages
        </span>
        {newCount > 0 && (
          <span className="rounded-full bg-red-900/60 px-2.5 py-0.5 text-xs font-semibold text-red-300">
            {newCount} NEW
          </span>
        )}
        <Link
          href={`/scans/${scanId}`}
          className="ml-auto text-xs text-emerald-400 hover:text-emerald-300"
        >
          Full detail →
        </Link>
      </div>

      {/* Damage table */}
      {data.damage_records.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-gray-800">
          <table className="w-full text-xs">
            <thead className="bg-gray-900 text-gray-500 uppercase tracking-wider">
              <tr>
                <th className="px-3 py-2 text-left">Class</th>
                <th className="px-3 py-2 text-right">Confidence</th>
                <th className="px-3 py-2 text-right">Area</th>
                <th className="px-3 py-2 text-center">New</th>
              </tr>
            </thead>
            <tbody>
              {data.damage_records.map((r) => (
                <tr
                  key={r.id}
                  className="border-t border-gray-800 hover:bg-gray-900/50"
                >
                  <td className="px-3 py-2 font-medium text-gray-200">
                    {r.damage_class.replace('_', ' ')}
                  </td>
                  <td className="px-3 py-2 text-right text-gray-400">
                    {(r.confidence * 100).toFixed(1)}%
                  </td>
                  <td className="px-3 py-2 text-right text-gray-500">
                    {r.mask_area_px.toLocaleString()} px
                  </td>
                  <td className="px-3 py-2 text-center">
                    {r.is_new_damage === true ? (
                      <span className="rounded bg-red-900 px-1.5 py-0.5 text-red-300">
                        ●
                      </span>
                    ) : r.is_new_damage === false ? (
                      <span className="text-gray-600">○</span>
                    ) : (
                      <span className="text-gray-700">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── Single scan card ──────────────────────────────────────────────────────────

interface ScanCardProps {
  scan: Scan;
  isLast: boolean;
  comparisonMode: boolean;
  comparisonScanIds: [string | null, string | null];
  onToggleComparison: (id: string) => void;
}

function ScanCard({
  scan,
  isLast,
  comparisonMode,
  comparisonScanIds,
  onToggleComparison,
}: ScanCardProps) {
  const [expanded, setExpanded] = useState(false);

  const isSelectedA = comparisonScanIds[0] === scan.id;
  const isSelectedB = comparisonScanIds[1] === scan.id;
  const isSelected = isSelectedA || isSelectedB;
  const selectionLabel = isSelectedA ? 'A' : isSelectedB ? 'B' : null;

  return (
    <div className="flex gap-4">
      {/* Timeline connector */}
      <div className="flex flex-col items-center">
        <div
          className={clsx(
            'h-3 w-3 rounded-full border-2 mt-3 flex-shrink-0 transition-colors',
            expanded
              ? 'border-emerald-500 bg-emerald-500'
              : 'border-gray-600 bg-gray-900'
          )}
        />
        {!isLast && <div className="w-0.5 flex-1 bg-gray-800 mt-1" />}
      </div>

      {/* Card body */}
      <div
        className={clsx(
          'flex-1 rounded-xl border transition-colors mb-4',
          isSelected
            ? 'border-emerald-700 bg-gray-900'
            : 'border-gray-800 bg-gray-900/50 hover:border-gray-700'
        )}
      >
        <div className="flex items-start justify-between px-4 py-3">
          {/* Left: date + meta */}
          <div>
            <p className="text-sm font-semibold text-gray-100">
              {format(new Date(scan.triggered_at), 'dd MMM yyyy')}
            </p>
            <p className="mt-0.5 text-xs text-gray-500">
              {format(new Date(scan.triggered_at), 'HH:mm:ss')}
              {scan.location_tag && (
                <span className="ml-2 text-gray-600">· {scan.location_tag}</span>
              )}
            </p>
          </div>

          {/* Right: actions */}
          <div className="flex items-center gap-2">
            <ScanStatusBadge status={scan.status} />

            {comparisonMode && (
              <button
                onClick={() => onToggleComparison(scan.id)}
                className={clsx(
                  'flex h-6 w-6 items-center justify-center rounded text-xs font-bold transition-colors',
                  isSelected
                    ? 'bg-emerald-600 text-white'
                    : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                )}
              >
                {selectionLabel ?? '+'}
              </button>
            )}

            <button
              onClick={() => setExpanded((v) => !v)}
              className="rounded-md p-1 text-gray-500 hover:bg-gray-800 hover:text-gray-300"
            >
              {expanded ? '▲' : '▼'}
            </button>
          </div>
        </div>

        {/* Expanded: inline scan detail */}
        {expanded && (
          <div className="border-t border-gray-800 px-4 pb-4">
            <InlineScanDetail scanId={scan.id} />
          </div>
        )}
      </div>
    </div>
  );
}

// ── ScanTimeline ──────────────────────────────────────────────────────────────

interface ScanTimelineProps {
  scans: Scan[];
  comparisonMode: boolean;
}

export function ScanTimeline({ scans, comparisonMode }: ScanTimelineProps) {
  const setComparisonScanId = useStore((s) => s.setComparisonScanId);
  const comparisonScanIds = useStore((s) => s.comparisonScanIds);

  const handleToggle = useCallback(
    (id: string) => {
      if (comparisonScanIds[0] === id) {
        setComparisonScanId(0, null);
      } else if (comparisonScanIds[1] === id) {
        setComparisonScanId(1, null);
      } else if (comparisonScanIds[0] === null) {
        setComparisonScanId(0, id);
      } else if (comparisonScanIds[1] === null) {
        setComparisonScanId(1, id);
      }
    },
    [comparisonScanIds, setComparisonScanId]
  );

  if (scans.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-gray-600">
        No scans recorded yet.
      </p>
    );
  }

  return (
    <div>
      {scans.map((scan, i) => (
        <ScanCard
          key={scan.id}
          scan={scan}
          isLast={i === scans.length - 1}
          comparisonMode={comparisonMode}
          comparisonScanIds={comparisonScanIds}
          onToggleComparison={handleToggle}
        />
      ))}
    </div>
  );
}
