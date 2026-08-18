'use client';

import {
  useState,
  useRef,
  useCallback,
  useMemo,
  type DragEvent,
  type ChangeEvent,
} from 'react';
import Link from 'next/link';
import { clsx } from 'clsx';
import { DamageCanvas } from '@/components/DamageCanvas';
import { DamageBadge } from '@/components/DamageBadge';
import { SamplePresets } from '@/components/SamplePresets';
import { RepairCostCard } from '@/components/RepairCostCard';
import { PdfReportButton } from '@/components/PdfReportButton';
import { inspectImageFile, type InspectResult } from '@/lib/api';
import type { DamageAnnotation, DamageClass } from '@/types';

// ── Camera angle config ───────────────────────────────────────────────────────

const ANGLES = [
  { value: 'front',         label: 'Front',         camId: 'cam_01', icon: '↑' },
  { value: 'rear',          label: 'Rear',          camId: 'cam_02', icon: '↓' },
  { value: 'left',          label: 'Left',          camId: 'cam_03', icon: '←' },
  { value: 'right',         label: 'Right',         camId: 'cam_04', icon: '→' },
  { value: 'front_oblique', label: 'Front Oblique', camId: 'cam_05', icon: '↗' },
  { value: 'rear_oblique',  label: 'Rear Oblique',  camId: 'cam_06', icon: '↙' },
] as const;

type AngleValue = typeof ANGLES[number]['value'];

// ── Per-slot state ────────────────────────────────────────────────────────────

interface SlotState {
  file:    File | null;
  preview: string | null;
  loading: boolean;
  result:  InspectResult | null;
  error:   string | null;
}

type SlotsMap = Record<AngleValue, SlotState>;

const EMPTY_SLOT: SlotState = {
  file: null, preview: null, loading: false, result: null, error: null,
};

function initSlots(): SlotsMap {
  return Object.fromEntries(ANGLES.map(a => [a.value, { ...EMPTY_SLOT }])) as SlotsMap;
}

const MAX_MB = 20;
const REFLECTION_WARN  = 0.45;   // amber warning
const REFLECTION_SKIP  = 0.70;   // almost certainly glare — default-excluded

// ── Helpers ───────────────────────────────────────────────────────────────────

function resultToAnnotations(
  result: InspectResult,
  excluded: Set<string>,
  minConf: number,
): DamageAnnotation[] {
  return result.damages
    .filter(d => d.confidence >= minConf)
    .map(d => ({
      id:              d.annotation_id,
      className:       d.class_name as DamageClass,
      confidence:      d.confidence,
      bbox:            d.bbox_xyxy,
      polygon:         d.polygon_points,
      reflectionScore: d.reflection_score,
    }))
    // Excluded detections are shown greyed-out (oldDamages), not as active annotations
    .filter(a => !excluded.has(a.id));
}

function excludedAnnotations(
  result: InspectResult,
  excluded: Set<string>,
  minConf: number,
): DamageAnnotation[] {
  return result.damages
    .filter(d => excluded.has(d.annotation_id) && d.confidence >= minConf)
    .map(d => ({
      id:         d.annotation_id,
      className:  d.class_name as DamageClass,
      confidence: d.confidence,
      bbox:       d.bbox_xyxy,
      polygon:    d.polygon_points,
    }));
}

// ── Single angle drop slot ────────────────────────────────────────────────────

interface AngleSlotProps {
  angle:   typeof ANGLES[number];
  slot:    SlotState;
  minConf: number;
  excluded: Set<string>;
  onFile:  (angle: AngleValue, file: File) => void;
  onClear: (angle: AngleValue) => void;
}

function AngleSlot({ angle, slot, minConf, excluded, onFile, onClear }: AngleSlotProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files[0];
    if (f?.type.startsWith('image/')) onFile(angle.value, f);
  }

  function handleChange(e: ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (f) onFile(angle.value, f);
    e.target.value = '';
  }

  const visibleDamages = slot.result
    ? slot.result.damages.filter(d => d.confidence >= minConf && !excluded.has(d.annotation_id))
    : [];
  const hasDamage  = visibleDamages.length > 0;
  const isClean    = slot.result !== null && !hasDamage;
  const reflCount  = visibleDamages.filter(d => d.reflection_score >= REFLECTION_WARN).length;

  const borderCls =
    slot.loading ? 'border-blue-800' :
    hasDamage    ? 'border-red-800'  :
    isClean      ? 'border-emerald-800' :
    slot.file    ? 'border-gray-600' :
    dragging     ? 'border-emerald-500' : 'border-gray-800';

  return (
    <div className={clsx('rounded-xl border overflow-hidden transition-all duration-200', borderCls)}>

      {/* Header */}
      <div className={clsx(
        'flex items-center justify-between px-3 py-1.5 border-b text-xs font-bold uppercase tracking-wider',
        slot.loading ? 'border-blue-900/50 bg-blue-950/20 text-blue-400'        :
        hasDamage    ? 'border-red-900/50   bg-red-950/20   text-red-400'        :
        isClean      ? 'border-emerald-900/50 bg-emerald-950/20 text-emerald-400' :
                       'border-gray-800 bg-gray-900 text-gray-500',
      )}>
        <span className="flex items-center gap-1.5">{angle.icon} {angle.label}</span>
        <span className="flex items-center gap-1.5">
          {slot.loading && (
            <span className="h-2.5 w-2.5 rounded-full border border-blue-700 border-t-blue-300 animate-spin" />
          )}
          {reflCount > 0 && !slot.loading && (
            <span className="text-amber-400" title={`${reflCount} possible reflection(s)`}>⚠</span>
          )}
          {hasDamage && (
            <span className="rounded-full bg-red-900 px-1.5 py-0.5 text-[10px] font-bold text-red-200">
              {visibleDamages.length}
            </span>
          )}
          {isClean && <span className="text-[10px]">✓</span>}
          {slot.file && !slot.loading && (
            <button onClick={() => onClear(angle.value)} className="text-gray-600 hover:text-gray-300 ml-0.5">✕</button>
          )}
        </span>
      </div>

      {/* Image */}
      {slot.preview ? (
        <div className="relative cursor-pointer" onClick={() => !slot.loading && inputRef.current?.click()} title="Click to change">
          {slot.loading ? (
            <>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={slot.preview} alt="" className="w-full aspect-video object-cover opacity-20" />
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-2">
                <div className="h-7 w-7 rounded-full border-2 border-blue-900 border-t-blue-400 animate-spin" />
                <p className="text-[10px] text-blue-400">Analysing…</p>
              </div>
            </>
          ) : slot.result ? (
            <DamageCanvas
              imageUrl={slot.preview}
              damages={resultToAnnotations(slot.result, excluded, minConf)}
              oldDamages={excludedAnnotations(slot.result, excluded, minConf)}
              className="w-full"
            />
          ) : (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={slot.preview} alt={angle.label} className="w-full aspect-video object-cover" />
          )}
        </div>
      ) : (
        <div
          onDragOver={e => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          onClick={() => inputRef.current?.click()}
          className={clsx(
            'flex flex-col items-center justify-center aspect-video cursor-pointer transition-colors bg-gray-950 hover:bg-gray-900',
            dragging && 'bg-emerald-950/20',
          )}
        >
          <span className="text-3xl text-gray-700 mb-1">{angle.icon}</span>
          <p className="text-[10px] text-gray-600 text-center">Drop image<br />or click</p>
        </div>
      )}

      {slot.error && (
        <p className="px-3 py-1 text-[10px] text-red-400 bg-red-950/30 border-t border-red-900/50 truncate">{slot.error}</p>
      )}

      <input ref={inputRef} type="file" accept="image/*" className="hidden" onChange={handleChange} />
    </div>
  );
}

// ── Detection row with reflection badge + exclude button ──────────────────────

interface DetectionRowProps {
  d:        InspectResult['damages'][number];
  excluded: Set<string>;
  onToggleExclude: (id: string) => void;
}

function DetectionRow({ d, excluded, onToggleExclude }: DetectionRowProps) {
  const isExcluded   = excluded.has(d.annotation_id);
  const isReflWarn   = d.reflection_score >= REFLECTION_WARN;
  const isReflStrong = d.reflection_score >= REFLECTION_SKIP;

  return (
    <div className={clsx(
      'flex gap-3 p-3 border-b border-gray-800 last:border-0 transition-colors',
      isExcluded ? 'opacity-40 bg-gray-950/50' : 'hover:bg-gray-800/50',
    )}>
      {/* Crop thumbnail */}
      {d.crop_b64 && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={`data:image/png;base64,${d.crop_b64}`}
          alt="crop"
          className={clsx(
            'h-14 w-16 flex-shrink-0 rounded object-cover border',
            isExcluded ? 'border-gray-800 grayscale' :
            isReflWarn ? 'border-amber-700' : 'border-gray-700',
          )}
        />
      )}

      <div className="flex-1 min-w-0">
        {/* Class + confidence */}
        <div className="flex items-center gap-2 mb-1 flex-wrap">
          <DamageBadge cls={d.class_name as DamageClass} size="sm" showDot />
          <span className="text-xs font-semibold text-gray-200 tabular-nums ml-auto">
            {(d.confidence * 100).toFixed(1)}%
          </span>
        </div>

        {/* Reflection warning */}
        {isReflWarn && !isExcluded && (
          <div className={clsx(
            'mb-1 flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-semibold w-fit',
            isReflStrong
              ? 'bg-amber-950 text-amber-300'
              : 'bg-amber-950/50 text-amber-500',
          )}>
            ⚠ {isReflStrong ? 'Very likely glare/reflection' : 'Possible light reflection'}
            <span className="text-amber-600 font-normal ml-1">
              ({Math.round(d.reflection_score * 100)}%)
            </span>
          </div>
        )}

        {/* BBox + area */}
        <div className="text-[10px] text-gray-600 leading-relaxed">
          <p>bbox {d.bbox_xyxy[0]},{d.bbox_xyxy[1]} → {d.bbox_xyxy[2]},{d.bbox_xyxy[3]}</p>
          <p>area {d.mask_area_px.toLocaleString()} px · {d.mask_area_pct.toFixed(2)}%</p>
        </div>
      </div>

      {/* Exclude / restore button */}
      <button
        onClick={() => onToggleExclude(d.annotation_id)}
        title={isExcluded ? 'Restore this detection' : 'Exclude — not real damage'}
        className={clsx(
          'flex-shrink-0 self-center rounded-md px-2 py-1 text-[10px] font-semibold transition-colors',
          isExcluded
            ? 'bg-gray-800 text-gray-400 hover:bg-gray-700 hover:text-gray-200'
            : isReflWarn
            ? 'bg-amber-950 text-amber-400 hover:bg-amber-900'
            : 'bg-gray-900 text-gray-600 hover:bg-gray-800 hover:text-gray-300',
        )}
      >
        {isExcluded ? '↩ Restore' : '✕ Exclude'}
      </button>
    </div>
  );
}

// ── Stacked per-angle result panel ────────────────────────────────────────────

interface AngleResultProps {
  angle:          typeof ANGLES[number];
  slot:           SlotState;
  minConf:        number;
  excluded:       Set<string>;
  onToggleExclude: (id: string) => void;
}

function AngleResultPanel({ angle, slot, minConf, excluded, onToggleExclude }: AngleResultProps) {
  if (!slot.result || !slot.preview) return null;

  const damages = slot.result.damages.filter(d => d.confidence >= minConf);
  const visible = damages.filter(d => !excluded.has(d.annotation_id));
  const hasDamage  = visible.length > 0;
  const reflCount  = visible.filter(d => d.reflection_score >= REFLECTION_WARN).length;

  return (
    <div className={clsx(
      'rounded-xl border overflow-hidden',
      hasDamage ? 'border-red-900/50' : 'border-emerald-900/50',
    )}>
      {/* Header */}
      <div className={clsx(
        'flex items-center gap-3 px-4 py-2.5 border-b',
        hasDamage ? 'bg-red-950/30 border-red-900/30' : 'bg-emerald-950/30 border-emerald-900/30',
      )}>
        <span className={clsx('text-xl font-black w-6 text-center', hasDamage ? 'text-red-400' : 'text-emerald-400')}>
          {angle.icon}
        </span>
        <div className="flex-1">
          <p className="text-sm font-bold text-gray-100 leading-tight">{angle.label}</p>
          <p className="text-xs text-gray-500">
            {hasDamage
              ? `${visible.length} damage${visible.length !== 1 ? 's' : ''}${excluded.size > 0 ? ` (${damages.length - visible.length} excluded)` : ''}`
              : 'No damage detected — clean'}
            {' · '}{slot.result.inference_time_ms.toFixed(0)} ms
          </p>
        </div>
        {reflCount > 0 && (
          <span className="flex items-center gap-1 rounded-full bg-amber-950 px-2.5 py-0.5 text-[10px] font-bold text-amber-400 ring-1 ring-amber-800">
            ⚠ {reflCount} possible reflection{reflCount !== 1 ? 's' : ''}
          </span>
        )}
        {slot.result.plate_result && (
          <span className="font-mono text-xs font-bold text-emerald-300 bg-emerald-950 rounded px-2 py-0.5 ring-1 ring-emerald-800">
            {slot.result.plate_result.plate_text}
          </span>
        )}
        {!hasDamage && <span className="text-emerald-400 text-sm font-bold">✓</span>}
      </div>

      <div className="grid md:grid-cols-[1fr_300px] divide-y md:divide-y-0 md:divide-x divide-gray-800">
        {/* Canvas */}
        <div className="bg-gray-950">
          <DamageCanvas
            imageUrl={slot.preview}
            damages={resultToAnnotations(slot.result, excluded, minConf)}
            oldDamages={excludedAnnotations(slot.result, excluded, minConf)}
            className="w-full"
          />
        </div>

        {/* Detection list */}
        <div className="bg-gray-900 overflow-y-auto max-h-80">
          {damages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full py-10 text-center px-4">
              <span className="text-4xl mb-2 opacity-60">✓</span>
              <p className="text-sm font-semibold text-emerald-400">Clean</p>
              <p className="text-xs text-gray-500 mt-1">No damage found</p>
            </div>
          ) : (
            damages.map(d => (
              <DetectionRow
                key={d.annotation_id}
                d={d}
                excluded={excluded}
                onToggleExclude={onToggleExclude}
              />
            ))
          )}
        </div>
      </div>
    </div>
  );
}

// ── Filters bar ───────────────────────────────────────────────────────────────

interface FiltersBarProps {
  minConf:         number;
  onMinConfChange: (v: number) => void;
  autoExclRefl:    boolean;
  onAutoExclChange: (v: boolean) => void;
  excludedCount:   number;
  onResetExcluded: () => void;
}

function FiltersBar({
  minConf, onMinConfChange,
  autoExclRefl, onAutoExclChange,
  excludedCount, onResetExcluded,
}: FiltersBarProps) {
  return (
    <div className="flex flex-wrap items-center gap-4 rounded-xl border border-gray-800 bg-gray-900 px-4 py-3 mb-4 text-xs">
      {/* Confidence slider */}
      <div className="flex items-center gap-2">
        <span className="text-gray-400 whitespace-nowrap">Min confidence</span>
        <input
          type="range"
          min={0} max={95} step={5}
          value={Math.round(minConf * 100)}
          onChange={e => onMinConfChange(Number(e.target.value) / 100)}
          className="w-28 accent-emerald-500"
        />
        <span className="w-8 text-right font-mono font-bold text-gray-200">
          {Math.round(minConf * 100)}%
        </span>
      </div>

      <div className="h-4 w-px bg-gray-800" />

      {/* Auto-exclude reflections toggle */}
      <label className="flex items-center gap-2 cursor-pointer">
        <div
          onClick={() => onAutoExclChange(!autoExclRefl)}
          className={clsx(
            'relative h-4 w-8 rounded-full transition-colors',
            autoExclRefl ? 'bg-amber-600' : 'bg-gray-700',
          )}
        >
          <div className={clsx(
            'absolute top-0.5 h-3 w-3 rounded-full bg-white shadow transition-transform',
            autoExclRefl ? 'translate-x-4' : 'translate-x-0.5',
          )} />
        </div>
        <span className="text-gray-400">
          Auto-exclude likely reflections
          <span className="ml-1 text-gray-600">(score ≥ {Math.round(REFLECTION_SKIP * 100)}%)</span>
        </span>
      </label>

      {excludedCount > 0 && (
        <>
          <div className="h-4 w-px bg-gray-800" />
          <button onClick={onResetExcluded} className="text-gray-500 hover:text-gray-300">
            ↩ Restore {excludedCount} excluded
          </button>
        </>
      )}
    </div>
  );
}

// ── Summary bar ───────────────────────────────────────────────────────────────

function SummaryBar({ slots, excluded, minConf }: { slots: SlotsMap; excluded: Set<string>; minConf: number }) {
  const analysedCount = ANGLES.filter(a => slots[a.value].result).length;
  const totalVisible  = ANGLES.reduce(
    (s, a) => s + (slots[a.value].result?.damages.filter(d =>
      d.confidence >= minConf && !excluded.has(d.annotation_id)
    ).length ?? 0), 0
  );
  const totalRefl = ANGLES.reduce(
    (s, a) => s + (slots[a.value].result?.damages.filter(d =>
      d.confidence >= minConf && !excluded.has(d.annotation_id) && d.reflection_score >= REFLECTION_WARN
    ).length ?? 0), 0
  );

  return (
    <div className="flex flex-wrap items-center gap-4 rounded-xl border border-gray-800 bg-gray-900 px-4 py-3 mb-4 text-sm">
      <div>
        <span className="font-bold text-gray-100">{analysedCount}</span>
        <span className="text-gray-500 ml-1">angle{analysedCount !== 1 ? 's' : ''} analysed</span>
      </div>
      <div className="h-4 w-px bg-gray-800" />
      <div>
        <span className={clsx('font-bold', totalVisible > 0 ? 'text-red-400' : 'text-emerald-400')}>
          {totalVisible}
        </span>
        <span className="text-gray-500 ml-1">damage{totalVisible !== 1 ? 's' : ''} confirmed</span>
      </div>
      {totalRefl > 0 && (
        <>
          <div className="h-4 w-px bg-gray-800" />
          <div className="flex items-center gap-1.5 text-amber-400">
            <span>⚠</span>
            <span className="font-bold">{totalRefl}</span>
            <span className="text-amber-600">reflection warning{totalRefl !== 1 ? 's' : ''} — verify before saving</span>
          </div>
        </>
      )}
      {totalVisible === 0 && analysedCount > 0 && (
        <>
          <div className="h-4 w-px bg-gray-800" />
          <span className="font-semibold text-emerald-400">✓ Vehicle appears clean</span>
        </>
      )}
    </div>
  );
}

// ── Save panel ────────────────────────────────────────────────────────────────

function SavePanel({ slots, excluded, minConf }: { slots: SlotsMap; excluded: Set<string>; minConf: number }) {
  const [plate,  setPlate]  = useState('');
  const [saving, setSaving] = useState(false);
  const [saved,  setSaved]  = useState<{ id: string; vehicleId: string } | null>(null);
  const [error,  setError]  = useState<string | null>(null);

  const detectedPlate = ANGLES
    .map(a => slots[a.value].result?.plate_result?.plate_text)
    .find(Boolean) ?? null;

  async function handleSave() {
    const trimmed = plate.trim();
    if (!trimmed) return;
    setSaving(true);
    setError(null);
    try {
      // Build inspection results, filtering excluded detections
      const inspectionResults = ANGLES
        .filter(a => slots[a.value].result)
        .map(a => ({
          camera_id:         a.camId,
          angle:             a.value,
          damages:           slots[a.value].result!.damages.filter(d =>
            d.confidence >= minConf && !excluded.has(d.annotation_id)
          ),
          plate_result:      slots[a.value].result!.plate_result,
          inference_time_ms: slots[a.value].result!.inference_time_ms,
          captured_at:       slots[a.value].result!.captured_at,
        }));

      const form = new FormData();
      form.append('metadata', JSON.stringify({
        plate_number: trimmed.toUpperCase(),
        location_tag: 'manual-upload',
        inspection_results: inspectionResults,
      }));
      ANGLES.forEach(a => {
        if (slots[a.value].file) form.append('images', slots[a.value].file!, `${a.camId}.jpg`);
      });

      const res  = await fetch('/api/v1/scans', { method: 'POST', body: form });
      const body = await res.json();
      if (!body.success) throw new Error(body.error ?? 'Save failed');
      setSaved({ id: body.data.id, vehicleId: body.data.vehicle_id });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  }

  if (saved) {
    return (
      <div className="rounded-xl border border-emerald-800 bg-emerald-950/30 px-5 py-4">
        <p className="text-sm font-semibold text-emerald-400 mb-3">Scan saved!</p>
        <div className="flex flex-wrap gap-3">
          <Link href={`/scans/${saved.id}`}
            className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-600">
            View Scan Report →
          </Link>
          <Link href={`/vehicles/${saved.vehicleId}`}
            className="rounded-lg border border-gray-700 px-4 py-2 text-sm text-gray-300 hover:bg-gray-800">
            Vehicle History
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900 px-5 py-4">
      <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-gray-500">
        Save as Official Scan Record
      </p>
      <p className="mb-3 text-xs text-gray-600">
        Only confirmed (non-excluded) detections will be saved.
        Excluded reflections are discarded.
      </p>
      <div className="flex flex-wrap gap-3 items-end">
        <div className="flex-1 min-w-52">
          <label className="block text-xs text-gray-400 mb-1">Plate Number</label>
          <div className="relative">
            <input
              value={plate}
              onChange={e => setPlate(e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, ''))}
              placeholder="TN09AB1234"
              maxLength={12}
              className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm font-mono font-semibold tracking-widest text-gray-100 placeholder-gray-600 outline-none focus:border-emerald-600 pr-28"
            />
            {detectedPlate && !plate && (
              <button onClick={() => setPlate(detectedPlate)}
                className="absolute right-2 top-1/2 -translate-y-1/2 rounded bg-emerald-900/60 px-1.5 py-0.5 text-[10px] font-bold text-emerald-400 hover:bg-emerald-900">
                ← Use {detectedPlate}
              </button>
            )}
          </div>
        </div>
        <button
          onClick={handleSave}
          disabled={saving || !plate.trim()}
          className="rounded-lg bg-emerald-700 px-5 py-2 text-sm font-semibold text-white hover:bg-emerald-600 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {saving ? 'Saving…' : '💾 Save to Database'}
        </button>
      </div>
      {error && <p className="mt-2 text-xs text-red-400">{error}</p>}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function UploadPage() {
  const [slots,        setSlots]        = useState<SlotsMap>(initSlots);
  const [minConf,      setMinConf]      = useState(0.45);
  const [autoExclRefl, setAutoExclRefl] = useState(true);
  const [excluded,     setExcluded]     = useState<Set<string>>(new Set());

  const updateSlot = useCallback((angle: AngleValue, patch: Partial<SlotState>) => {
    setSlots(prev => ({ ...prev, [angle]: { ...prev[angle], ...patch } }));
  }, []);

  const handleFile = useCallback((angle: AngleValue, file: File) => {
    if (file.size > MAX_MB * 1024 * 1024) {
      updateSlot(angle, { error: `Max ${MAX_MB} MB` });
      return;
    }
    updateSlot(angle, { file, preview: URL.createObjectURL(file), result: null, error: null, loading: false });
  }, [updateSlot]);

  const handleClear = useCallback((angle: AngleValue) => {
    setSlots(prev => ({ ...prev, [angle]: { ...EMPTY_SLOT } }));
  }, []);

  const handleFillAll = useCallback(() => {
    const first = ANGLES.find(a => slots[a.value].file);
    if (!first) return;
    const { file, preview } = slots[first.value];
    if (!file || !preview) return;
    setSlots(prev => {
      const next = { ...prev };
      ANGLES.forEach(a => { if (!prev[a.value].file) next[a.value] = { ...EMPTY_SLOT, file, preview }; });
      return next;
    });
  }, [slots]);

  const handleAnalyse = useCallback(async () => {
    const toRun = ANGLES.filter(a => slots[a.value].file);
    if (!toRun.length) return;

    setExcluded(new Set()); // reset exclusions on new analysis
    toRun.forEach(a => updateSlot(a.value, { loading: true, error: null, result: null }));

    await Promise.all(
      toRun.map(a =>
        inspectImageFile(slots[a.value].file!, a.camId, '')
          .then(result => {
            updateSlot(a.value, { loading: false, result });
            // Auto-exclude strong reflections if toggle is on
            if (autoExclRefl) {
              const autoIds = result.damages
                .filter(d => d.reflection_score >= REFLECTION_SKIP)
                .map(d => d.annotation_id);
              if (autoIds.length > 0) {
                setExcluded(prev => new Set([...prev, ...autoIds]));
              }
            }
          })
          .catch(err => updateSlot(a.value, {
            loading: false,
            error: err instanceof Error ? err.message : 'Analysis failed',
          }))
      )
    );
  }, [slots, updateSlot, autoExclRefl]);

  const handleToggleExclude = useCallback((id: string) => {
    setExcluded(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }, []);

  const handleSelectPreset = useCallback(async (dataUrl: string, name: string) => {
    // Convert dataURL to File object
    const res = await fetch(dataUrl);
    const blob = await res.blob();
    const file = new File([blob], `${name.replace(/\s+/g, '_')}.png`, { type: 'image/png' });

    // Load into front slot and copy to other slots for quick demo test
    setSlots(() => {
      const next = initSlots();
      ANGLES.forEach(a => {
        next[a.value] = { ...EMPTY_SLOT, file, preview: dataUrl };
      });
      return next;
    });

    // Auto-trigger analysis
    setExcluded(new Set());
    ANGLES.forEach(a => updateSlot(a.value, { loading: true, error: null, result: null }));

    await Promise.all(
      ANGLES.map(a =>
        inspectImageFile(file, a.camId, '')
          .then(result => {
            updateSlot(a.value, { loading: false, result });
          })
          .catch(err => updateSlot(a.value, {
            loading: false,
            error: err instanceof Error ? err.message : 'Analysis failed',
          }))
      )
    );
  }, [updateSlot]);

  // Derived
  const loadedCount      = ANGLES.filter(a => slots[a.value].file).length;
  const emptyCount       = ANGLES.filter(a => !slots[a.value].file).length;
  const anyLoading       = ANGLES.some(a => slots[a.value].loading);
  const anyResult        = ANGLES.some(a => slots[a.value].result);
  const anglesWithResult = ANGLES.filter(a => slots[a.value].result);

  // All active damages across angles for Cost Card & PDF Report
  const allActiveDamages = anglesWithResult.flatMap(a =>
    slots[a.value].result?.damages.filter(d => d.confidence >= minConf && !excluded.has(d.annotation_id)) || []
  );

  return (
    <div className="mx-auto max-w-[1200px] px-6 py-8">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-100">6-Angle Inspection Upload</h1>
          <p className="mt-1 text-sm text-gray-500">
            Upload one image per angle to simulate a full bay inspection.
            Light reflections are flagged automatically — review and exclude before saving.
          </p>
        </div>

        {anyResult && (
          <PdfReportButton
            plateNumber="DEMO-88-AI"
            damages={allActiveDamages}
          />
        )}
      </div>

      {/* Quick Client Demo Presets */}
      <SamplePresets onSelectPreset={handleSelectPreset} />

      {/* Slot grid */}
      <div className="grid grid-cols-3 gap-3 mb-3">
        {ANGLES.map(angle => (
          <AngleSlot
            key={angle.value}
            angle={angle}
            slot={slots[angle.value]}
            minConf={minConf}
            excluded={excluded}
            onFile={handleFile}
            onClear={handleClear}
          />
        ))}
      </div>

      {/* Controls */}
      <div className="flex flex-wrap items-center gap-2 mb-8">
        {loadedCount >= 1 && emptyCount > 0 && (
          <button onClick={handleFillAll}
            className="flex items-center gap-1.5 rounded-lg border border-dashed border-gray-600 bg-gray-900 px-3 py-1.5 text-xs text-gray-300 hover:border-gray-500 hover:bg-gray-800">
            <span className="text-base leading-none">⊕</span>
            Copy first image to {emptyCount} empty slot{emptyCount !== 1 ? 's' : ''}
          </button>
        )}
        {loadedCount > 0 && (
          <button onClick={() => setSlots(initSlots())}
            className="rounded-lg border border-gray-800 px-3 py-1.5 text-xs text-gray-500 hover:text-gray-300 hover:border-gray-700">
            ✕ Clear all
          </button>
        )}
        <div className="flex-1" />
        <button
          onClick={handleAnalyse}
          disabled={loadedCount === 0 || anyLoading}
          className={clsx(
            'flex items-center gap-2 rounded-lg px-5 py-2 text-sm font-semibold transition-colors',
            loadedCount > 0 && !anyLoading
              ? 'bg-emerald-700 text-white hover:bg-emerald-600'
              : 'bg-gray-800 text-gray-500 cursor-not-allowed',
          )}
        >
          {anyLoading ? (
            <><span className="h-3.5 w-3.5 rounded-full border-2 border-gray-600 border-t-white animate-spin" />Analysing…</>
          ) : loadedCount === 0 ? '🔍 Analyse Images' : `🔍 Analyse ${loadedCount} Image${loadedCount !== 1 ? 's' : ''}`}
        </button>
      </div>

      {/* Results */}
      {anyResult && (
        <>
          <FiltersBar
            minConf={minConf}
            onMinConfChange={setMinConf}
            autoExclRefl={autoExclRefl}
            onAutoExclChange={setAutoExclRefl}
            excludedCount={excluded.size}
            onResetExcluded={() => setExcluded(new Set())}
          />
          <SummaryBar slots={slots} excluded={excluded} minConf={minConf} />

          {/* Repair Cost & Claim Card */}
          <div className="mb-6">
            <RepairCostCard damages={allActiveDamages} />
          </div>

          <div className="space-y-4 mb-6">
            {anglesWithResult.map(angle => (
              <AngleResultPanel
                key={angle.value}
                angle={angle}
                slot={slots[angle.value]}
                minConf={minConf}
                excluded={excluded}
                onToggleExclude={handleToggleExclude}
              />
            ))}
          </div>
          <SavePanel slots={slots} excluded={excluded} minConf={minConf} />
        </>
      )}

      {!anyResult && loadedCount === 0 && (
        <div className="rounded-xl border border-dashed border-gray-800 py-12 text-center text-sm text-gray-600">
          Drop images into the slots above, then click <span className="text-gray-400 font-semibold">Analyse</span>.
          <br />Reflections are automatically flagged and can be excluded before saving.
        </div>
      )}
    </div>
  );
}
