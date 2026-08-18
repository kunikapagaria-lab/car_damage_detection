'use client';

import { useState } from 'react';
import useSWR from 'swr';
import { clsx } from 'clsx';
import { DamageCanvas } from '@/components/DamageCanvas';
import { ScanDetailSkeleton } from '@/components/Skeleton';
import { InlineError } from '@/components/ErrorBoundary';
import { fetcher, urls, minioUrl, BUCKET } from '@/lib/api';
import { recordToAnnotation } from '@/types';
import type { ScanDetail, CameraAngle, DamageAnnotation } from '@/types';

const ANGLE_ORDER: CameraAngle[] = [
  'front',
  'rear',
  'left',
  'right',
  'front_oblique',
  'rear_oblique',
];

const ANGLE_LABEL: Record<CameraAngle, string> = {
  front: 'Front',
  rear: 'Rear',
  left: 'Left',
  right: 'Right',
  front_oblique: 'Front ◣',
  rear_oblique: 'Rear ◣',
};

const ZOOM_STEPS = [1, 1.5, 2, 3];

interface PanelProps {
  scan: ScanDetail;
  angle: CameraAngle;
  label: string;
  annotations: DamageAnnotation[];
  oldAnnotations?: DamageAnnotation[];
  zoom: number;
}

function ImagePanel({
  scan,
  angle,
  label,
  annotations,
  oldAnnotations,
  zoom,
}: PanelProps) {
  const img = scan.images.find((i) => i.camera_angle === angle);
  const imageUrl = img ? minioUrl(BUCKET.FULL, img.full_image_path) : null;

  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs font-semibold uppercase tracking-wider text-gray-400">
        {label}
      </p>
      <div
        className="overflow-hidden rounded-lg border border-gray-800"
        style={{ transformOrigin: 'top left' }}
      >
        <div
          style={{
            transform: `scale(${zoom})`,
            transformOrigin: 'top left',
            width: `${100 / zoom}%`,
          }}
        >
          <DamageCanvas
            imageUrl={imageUrl}
            damages={annotations}
            oldDamages={oldAnnotations}
          />
        </div>
      </div>
    </div>
  );
}

interface DiffViewerProps {
  scanIdOld: string;
  scanIdNew: string;
  onClose: () => void;
}

export function DiffViewer({ scanIdOld, scanIdNew, onClose }: DiffViewerProps) {
  const [angle, setAngle] = useState<CameraAngle>('front');
  const [zoom, setZoom] = useState(1);
  const [viewMode, setViewMode] = useState<'side' | 'slider'>('slider');
  const [sliderPos, setSliderPos] = useState(50);

  const { data: oldScan, error: errOld, isLoading: loadOld } = useSWR<ScanDetail>(
    urls.scan(scanIdOld),
    fetcher
  );
  const { data: newScan, error: errNew, isLoading: loadNew } = useSWR<ScanDetail>(
    urls.scan(scanIdNew),
    fetcher
  );

  if (loadOld || loadNew) return <ScanDetailSkeleton />;
  if (errOld) return <InlineError message={errOld.message} />;
  if (errNew) return <InlineError message={errNew.message} />;
  if (!oldScan || !newScan) return null;

  // Build annotation sets for selected angle
  const oldAnnotations = oldScan.damage_records
    .filter(
      (r) =>
        oldScan.images.find((i) => i.id === r.scan_image_id)?.camera_angle ===
        angle
    )
    .map(recordToAnnotation);

  const newAnnotations = newScan.damage_records
    .filter(
      (r) =>
        newScan.images.find((i) => i.id === r.scan_image_id)?.camera_angle ===
        angle
    )
    .map(recordToAnnotation);

  const newOnly = newAnnotations.filter((a) => a.isNew === true);
  const existing = newAnnotations.filter((a) => a.isNew !== true);

  // Available angles (union of both scans)
  const availableAngles = ANGLE_ORDER.filter((a) => {
    const inOld = oldScan.images.some((i) => i.camera_angle === a);
    const inNew = newScan.images.some((i) => i.camera_angle === a);
    return inOld || inNew;
  });

  const oldImg = oldScan.images.find((i) => i.camera_angle === angle);
  const oldUrl = oldImg ? minioUrl(BUCKET.FULL, oldImg.full_image_path) : null;
  const newImg = newScan.images.find((i) => i.camera_angle === angle);
  const newUrl = newImg ? minioUrl(BUCKET.FULL, newImg.full_image_path) : null;

  return (
    <div className="rounded-xl border border-gray-700 bg-gray-900/60 backdrop-blur-sm">
      {/* Toolbar */}
      <div className="flex items-center gap-3 border-b border-gray-800 px-4 py-3 flex-wrap">
        <span className="text-sm font-semibold text-gray-200">Scan Diff Inspector</span>

        {/* Angle tabs */}
        <div className="flex gap-1 ml-2">
          {availableAngles.map((a) => (
            <button
              key={a}
              onClick={() => setAngle(a)}
              className={clsx(
                'rounded px-2.5 py-1 text-xs font-medium transition-colors',
                angle === a
                  ? 'bg-emerald-700 text-white'
                  : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200'
              )}
            >
              {ANGLE_LABEL[a]}
            </button>
          ))}
        </div>

        {/* View Mode Toggle */}
        <div className="flex gap-1 ml-3 border border-gray-800 rounded-lg p-0.5 bg-gray-950">
          <button
            onClick={() => setViewMode('slider')}
            className={clsx(
              'px-2 py-0.5 text-xs font-semibold rounded',
              viewMode === 'slider' ? 'bg-sky-700 text-white' : 'text-gray-400 hover:text-gray-200'
            )}
          >
            ↔ Split Slider
          </button>
          <button
            onClick={() => setViewMode('side')}
            className={clsx(
              'px-2 py-0.5 text-xs font-semibold rounded',
              viewMode === 'side' ? 'bg-sky-700 text-white' : 'text-gray-400 hover:text-gray-200'
            )}
          >
            ⧉ Side-by-Side
          </button>
        </div>

        {/* Zoom */}
        <div className="ml-auto flex items-center gap-1">
          {ZOOM_STEPS.map((z) => (
            <button
              key={z}
              onClick={() => setZoom(z)}
              className={clsx(
                'rounded px-2 py-0.5 text-xs font-mono transition-colors',
                zoom === z
                  ? 'bg-gray-700 text-white'
                  : 'text-gray-500 hover:bg-gray-800'
              )}
            >
              {z}×
            </button>
          ))}
        </div>

        <button
          onClick={onClose}
          className="ml-2 rounded p-1 text-gray-500 hover:bg-gray-800 hover:text-gray-300"
        >
          ✕
        </button>
      </div>

      {/* Legend */}
      <div className="flex gap-4 px-4 py-2 text-xs text-gray-500">
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-4 rounded border border-dashed border-gray-500 bg-gray-700/30" />
          Prior damage
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-4 rounded border border-dashed border-red-500 bg-red-900/30" />
          Existing ({existing.length})
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-2 w-4 rounded border border-red-400 bg-red-500/30" />
          NEW ({newOnly.length})
        </span>
      </div>

      {/* Display View */}
      {viewMode === 'slider' ? (
        <div className="p-4">
          <div className="relative aspect-video w-full max-w-4xl mx-auto overflow-hidden rounded-xl border border-gray-800 select-none bg-gray-950">
            {/* Background Image (Return / New Scan) */}
            <div className="absolute inset-0">
              <DamageCanvas imageUrl={newUrl} damages={newAnnotations} oldDamages={oldAnnotations} />
              <span className="absolute top-3 right-3 rounded bg-red-950/80 border border-red-800 px-2 py-1 text-[10px] font-bold text-red-300 z-10">
                RETURN SCAN (NEW DEFECTS)
              </span>
            </div>

            {/* Foreground Clipped Image (Checkout / Baseline Scan) */}
            <div
              className="absolute inset-y-0 left-0 overflow-hidden border-r-2 border-sky-400 shadow-2xl z-10"
              style={{ width: `${sliderPos}%` }}
            >
              <div className="w-full h-full min-w-[800px]">
                <DamageCanvas imageUrl={oldUrl} damages={oldAnnotations} />
              </div>
              <span className="absolute top-3 left-3 rounded bg-sky-950/80 border border-sky-800 px-2 py-1 text-[10px] font-bold text-sky-300">
                CHECKOUT BASELINE (CLEAN)
              </span>
            </div>

            {/* Slider Control Bar */}
            <input
              type="range"
              min="0"
              max="100"
              value={sliderPos}
              onChange={(e) => setSliderPos(Number(e.target.value))}
              className="absolute inset-0 w-full h-full opacity-0 cursor-ew-resize z-30"
            />
          </div>
          <p className="text-center text-xs text-gray-500 mt-2">
            ↔ Drag mouse across image to compare Checkout Baseline vs Return Scan
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-4 p-4">
          <ImagePanel
            scan={oldScan}
            angle={angle}
            label={`Scan A — ${new Date(oldScan.triggered_at).toLocaleDateString('en-IN')}`}
            annotations={oldAnnotations}
            zoom={zoom}
          />
          <ImagePanel
            scan={newScan}
            angle={angle}
            label={`Scan B — ${new Date(newScan.triggered_at).toLocaleDateString('en-IN')}`}
            annotations={newAnnotations}
            oldAnnotations={oldAnnotations}
            zoom={zoom}
          />
        </div>
      )}

      {/* Summary bar */}
      <div className="border-t border-gray-800 px-4 py-2 text-xs text-gray-500">
        {newOnly.length > 0 ? (
          <span className="text-red-400 font-semibold">
            {newOnly.length} new damage{newOnly.length !== 1 ? 's' : ''} detected
            {' '}since Scan A
          </span>
        ) : (
          <span className="text-emerald-400">No new damages detected for this angle</span>
        )}
        <span className="ml-4">
          {oldAnnotations.length} prior · {existing.length} existing · {newOnly.length} new
        </span>
      </div>
    </div>
  );
}
