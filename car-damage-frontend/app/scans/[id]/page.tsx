'use client';

import { useState, useCallback } from 'react';
import { notFound } from 'next/navigation';
import Link from 'next/link';
import useSWR from 'swr';
import { format } from 'date-fns';
import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import { fetcher, urls, minioUrl, BUCKET } from '@/lib/api';
import { DamageCanvas } from '@/components/DamageCanvas';
import { DamageBadge, ScanStatusBadge, DAMAGE_HEX } from '@/components/DamageBadge';
import { ScanDetailSkeleton } from '@/components/Skeleton';
import { InlineError, ErrorBoundary } from '@/components/ErrorBoundary';
import { recordToAnnotation } from '@/types';
import type { ScanDetail, ScanImage, DamageAnnotation } from '@/types';

interface PageProps {
  params: { id: string };
}

// ── Lightbox ──────────────────────────────────────────────────────────────────

interface LightboxProps {
  image: ScanImage;
  annotations: DamageAnnotation[];
  onClose: () => void;
}

function Lightbox({ image, annotations, onClose }: LightboxProps) {
  const imageUrl = minioUrl(BUCKET.FULL, image.full_image_path);

  // Close on backdrop click
  function handleBackdrop(e: React.MouseEvent) {
    if (e.target === e.currentTarget) onClose();
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 backdrop-blur-sm"
      onClick={handleBackdrop}
    >
      <div className="relative max-h-[90vh] max-w-[90vw] overflow-auto rounded-xl border border-gray-700 bg-gray-950 shadow-2xl">
        <div className="flex items-center justify-between border-b border-gray-800 px-4 py-3">
          <div className="flex items-center gap-3">
            <span className="text-sm font-semibold text-gray-200">
              {image.camera_angle.replace('_', ' ').toUpperCase()}
            </span>
            <span className="text-xs text-gray-500">
              {format(new Date(image.captured_at), 'HH:mm:ss')}
            </span>
            <span className="text-xs text-gray-600">
              {annotations.length} detection{annotations.length !== 1 ? 's' : ''}
            </span>
          </div>
          <button
            onClick={onClose}
            className="rounded-md p-1.5 text-gray-400 hover:bg-gray-800 hover:text-gray-200"
          >
            ✕
          </button>
        </div>
        <DamageCanvas imageUrl={imageUrl} damages={annotations} className="max-h-[80vh]" />
      </div>
    </div>
  );
}

// ── Image strip ───────────────────────────────────────────────────────────────

interface ImageStripProps {
  scan: ScanDetail;
  onImageClick: (img: ScanImage, annotations: DamageAnnotation[]) => void;
}

function ImageStrip({ scan, onImageClick }: ImageStripProps) {
  return (
    <div className="flex gap-3 overflow-x-auto pb-3 scrollbar-hide">
      {scan.images.map((img) => {
        const thumbUrl = minioUrl(BUCKET.THUMBS, img.thumbnail_path);
        const fullUrl = minioUrl(BUCKET.FULL, img.full_image_path);
        const imgAnnotations = scan.damage_records
          .filter((r) => r.scan_image_id === img.id)
          .map(recordToAnnotation);
        const newCount = imgAnnotations.filter((a) => a.isNew === true).length;

        return (
          <button
            key={img.id}
            onClick={() => onImageClick(img, imgAnnotations)}
            className="group relative flex-shrink-0 w-56 overflow-hidden rounded-lg border border-gray-800 bg-gray-900 hover:border-emerald-700 transition-colors"
          >
            <DamageCanvas
              imageUrl={fullUrl}
              damages={imgAnnotations}
              className="w-full"
            />
            <div className="flex items-center justify-between px-2 py-1.5">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-400">
                {img.camera_angle.replace('_', ' ')}
              </span>
              {newCount > 0 && (
                <span className="rounded bg-red-900 px-1.5 py-0.5 text-[10px] font-bold text-red-300">
                  {newCount} NEW
                </span>
              )}
            </div>
            <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity bg-black/20">
              <span className="rounded-full bg-black/60 px-3 py-1 text-xs text-white">
                Expand ⤢
              </span>
            </div>
          </button>
        );
      })}
    </div>
  );
}

// ── Damage pie chart ──────────────────────────────────────────────────────────

function DamagePie({ scan }: { scan: ScanDetail }) {
  const counts: Record<string, number> = {};
  for (const r of scan.damage_records) {
    counts[r.damage_class] = (counts[r.damage_class] ?? 0) + 1;
  }
  const data = Object.entries(counts).map(([name, value]) => ({ name, value }));
  if (data.length === 0) return null;

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
      <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-gray-500">
        Class Distribution
      </h3>
      <ResponsiveContainer width="100%" height={180}>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            innerRadius={45}
            outerRadius={70}
            dataKey="value"
            paddingAngle={3}
          >
            {data.map((entry) => (
              <Cell
                key={entry.name}
                fill={DAMAGE_HEX[entry.name as keyof typeof DAMAGE_HEX] ?? '#94a3b8'}
              />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{
              background: '#111827',
              border: '1px solid #374151',
              borderRadius: '8px',
              color: '#f3f4f6',
              fontSize: 12,
            }}
          />
          <Legend
            iconType="circle"
            iconSize={8}
            formatter={(v) => (
              <span style={{ color: '#9ca3af', fontSize: 11 }}>
                {v.replace('_', ' ')}
              </span>
            )}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── Damage table ──────────────────────────────────────────────────────────────

function DamageTable({ scan }: { scan: ScanDetail }) {
  const records = scan.damage_records;
  if (records.length === 0) {
    return (
      <div className="py-8 text-center text-sm text-gray-600">
        No damage detected in this scan.
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-gray-800">
      <table className="w-full text-sm">
        <thead className="bg-gray-900 text-xs uppercase tracking-wider text-gray-500">
          <tr>
            <th className="px-4 py-3 text-left">Class</th>
            <th className="px-4 py-3 text-left">Angle</th>
            <th className="px-4 py-3 text-right">Confidence</th>
            <th className="px-4 py-3 text-right">Area (px)</th>
            <th className="px-4 py-3 text-right">Area %</th>
            <th className="px-4 py-3 text-center">New</th>
          </tr>
        </thead>
        <tbody>
          {records.map((r) => {
            const angle =
              scan.images.find((i) => i.id === r.scan_image_id)?.camera_angle ??
              '—';
            return (
              <tr
                key={r.id}
                className="border-t border-gray-800 hover:bg-gray-900/50"
              >
                <td className="px-4 py-3">
                  <DamageBadge cls={r.damage_class} showDot />
                </td>
                <td className="px-4 py-3 text-xs text-gray-400">
                  {angle.replace('_', ' ')}
                </td>
                <td className="px-4 py-3 text-right">
                  <span
                    className={
                      r.confidence >= 0.8
                        ? 'text-emerald-400 font-semibold'
                        : 'text-gray-300'
                    }
                  >
                    {(r.confidence * 100).toFixed(1)}%
                  </span>
                </td>
                <td className="px-4 py-3 text-right font-mono text-xs text-gray-400">
                  {r.mask_area_px.toLocaleString()}
                </td>
                <td className="px-4 py-3 text-right text-xs text-gray-500">
                  {r.mask_area_pct.toFixed(2)}%
                </td>
                <td className="px-4 py-3 text-center">
                  {r.is_new_damage === true ? (
                    <span className="inline-flex items-center gap-1 rounded-full bg-red-900/60 px-2 py-0.5 text-[10px] font-bold text-red-300">
                      NEW
                    </span>
                  ) : r.is_new_damage === false ? (
                    <span className="text-gray-600 text-xs">Existing</span>
                  ) : (
                    <span className="text-gray-700 text-xs">—</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ScanDetailPage({ params }: PageProps) {
  const { id } = params;
  const [lightbox, setLightbox] = useState<{
    image: ScanImage;
    annotations: DamageAnnotation[];
  } | null>(null);

  const { data: scan, error, isLoading } = useSWR<ScanDetail>(
    urls.scan(id),
    fetcher
  );

  if (error?.message?.includes('404')) notFound();

  const newCount =
    scan?.damage_records.filter((r) => r.is_new_damage === true).length ?? 0;

  return (
    <div className="mx-auto max-w-[1300px] px-6 py-8">
      {/* Breadcrumb */}
      <nav className="mb-6 text-xs text-gray-600">
        <Link href="/vehicles" className="hover:text-gray-400">
          Vehicles
        </Link>
        <span className="mx-2">›</span>
        {scan && (
          <>
            <Link
              href={`/vehicles/${scan.vehicle_id}`}
              className="hover:text-gray-400"
            >
              {scan.vehicle_id.slice(0, 8)}…
            </Link>
            <span className="mx-2">›</span>
          </>
        )}
        <span className="text-gray-400">Scan {id.slice(0, 8)}…</span>
      </nav>

      {isLoading && <ScanDetailSkeleton />}
      {error && <InlineError message={error.message} />}

      {scan && (
        <>
          {/* Header */}
          <div className="mb-6 flex items-start justify-between">
            <div>
              <div className="flex items-center gap-3">
                <h1 className="text-2xl font-bold text-gray-100">
                  Scan Report
                </h1>
                <ScanStatusBadge status={scan.status} />
                {newCount > 0 && (
                  <span className="rounded-full bg-red-700 px-2.5 py-0.5 text-xs font-bold text-red-100">
                    {newCount} NEW
                  </span>
                )}
              </div>
              <p className="mt-1 text-xs text-gray-500">
                {format(new Date(scan.triggered_at), 'EEEE, dd MMMM yyyy — HH:mm:ss')}
                {scan.location_tag && (
                  <span className="ml-2 text-gray-600">· {scan.location_tag}</span>
                )}
              </p>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-600">
                {scan.camera_count} camera{scan.camera_count !== 1 ? 's' : ''}
                {' · '}
                {scan.damage_records.length} damage
                {scan.damage_records.length !== 1 ? 's' : ''}
              </span>
              {/* Report button (Phase 5 endpoint) */}
              <button
                onClick={() =>
                  window.open(`/api/v1/scans/${id}/report`, '_blank')
                }
                className="rounded-lg border border-gray-700 bg-gray-800 px-3 py-1.5 text-xs text-gray-300 hover:bg-gray-700"
              >
                ↓ Generate Report
              </button>
            </div>
          </div>

          {/* Main layout: images + pie */}
          <div className="mb-6 grid grid-cols-[1fr_220px] gap-4">
            {/* 360° image strip */}
            <div className="rounded-xl border border-gray-800 bg-gray-900 p-4">
              <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-gray-500">
                360° View — click to expand
              </h2>
              <ErrorBoundary>
                <ImageStrip
                  scan={scan}
                  onImageClick={(img, ann) => setLightbox({ image: img, annotations: ann })}
                />
              </ErrorBoundary>
            </div>

            {/* Pie chart */}
            <ErrorBoundary>
              <DamagePie scan={scan} />
            </ErrorBoundary>
          </div>

          {/* Damage table */}
          <h2 className="mb-3 text-xs font-semibold uppercase tracking-wider text-gray-500">
            Damage Records
          </h2>
          <ErrorBoundary>
            <DamageTable scan={scan} />
          </ErrorBoundary>
        </>
      )}

      {/* Lightbox */}
      {lightbox && (
        <Lightbox
          image={lightbox.image}
          annotations={lightbox.annotations}
          onClose={() => setLightbox(null)}
        />
      )}
    </div>
  );
}
