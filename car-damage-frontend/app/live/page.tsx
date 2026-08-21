'use client';

import { useEffect, useState, useCallback, useRef } from 'react';
import Link from 'next/link';
import { useStore } from '@/lib/store';
import { useWebSocketFeed, useClock } from '@/lib/hooks';
import { LiveFeedCard } from '@/components/LiveFeedCard';
import { VehicleBlueprint } from '@/components/VehicleBlueprint';
import { runTestInspection, type InspectResult } from '@/lib/api';
import type { CameraAngle, WSInspectionFrame } from '@/types';

const CAMERAS: Array<{ id: string; angle: CameraAngle }> = [
  { id: 'cam_01', angle: 'front' },
  { id: 'cam_02', angle: 'rear' },
  { id: 'cam_03', angle: 'left' },
  { id: 'cam_04', angle: 'right' },
  { id: 'cam_05', angle: 'front_oblique' },
  { id: 'cam_06', angle: 'rear_oblique' },
];

// ── Top bar ───────────────────────────────────────────────────────────────────

function TopBar({ onSimulate }: { onSimulate: () => void }) {
  const clock             = useClock();
  const wsStatus          = useStore((s) => s.wsStatus);
  const scansTodayCount   = useStore((s) => s.scansTodayCount);
  const newDamageCount    = useStore((s) => s.newDamageCount);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const today = mounted
    ? new Date().toLocaleDateString('en-IN', {
        weekday: 'long', day: '2-digit', month: 'short', year: 'numeric',
      })
    : '';

  return (
    <div className="flex flex-wrap items-center gap-4 border-b border-gray-800 bg-gray-950 px-6 py-3">
      {/* Live indicator */}
      <div className="flex items-center gap-2">
        <span className={
          wsStatus === 'connected'
            ? 'h-2.5 w-2.5 rounded-full bg-red-500 shadow-[0_0_8px_#ef4444] animate-pulse'
            : 'h-2.5 w-2.5 rounded-full bg-gray-600'
        } />
        <span className="text-xs font-bold uppercase tracking-widest text-gray-400">
          {wsStatus === 'connected' ? 'LIVE' : wsStatus === 'connecting' ? 'CONNECTING…' : 'OFFLINE'}
        </span>
      </div>

      <div className="h-4 w-px bg-gray-800" />

      <p className="text-sm text-gray-400" suppressHydrationWarning>
        {today}
        <span className="ml-3 font-mono font-bold text-gray-200" suppressHydrationWarning>{clock}</span>
      </p>

      {/* Simulate button */}
      <button
        onClick={onSimulate}
        className="flex items-center gap-1.5 rounded-lg border border-gray-700 bg-gray-900 px-3 py-1.5 text-xs text-gray-300 hover:bg-gray-800 hover:border-gray-600 transition-colors"
        title="Run a simulated inspection to see how the live feed works"
      >
        <span>▶</span> Simulate Detection
      </button>

      <div className="ml-auto flex items-center gap-6">
        <div className="text-right">
          <p className="text-xl font-bold text-gray-100 leading-none">{scansTodayCount}</p>
          <p className="text-[10px] text-gray-500 uppercase tracking-wider">Scans today</p>
        </div>
        <div className="text-right">
          <p className={
            newDamageCount > 0
              ? 'text-xl font-bold text-red-400 leading-none'
              : 'text-xl font-bold text-gray-600 leading-none'
          }>
            {newDamageCount}
          </p>
          <p className="text-[10px] text-gray-500 uppercase tracking-wider">New damages</p>
        </div>
        <Link
          href="/upload"
          className="rounded-lg bg-emerald-800/60 border border-emerald-700 px-3 py-1.5 text-xs font-semibold text-emerald-300 hover:bg-emerald-800"
        >
          📷 Upload Image
        </Link>
      </div>
    </div>
  );
}

// ── Simulate toast ────────────────────────────────────────────────────────────

function SimToast({ msg, onClose }: { msg: string; onClose: () => void }) {
  useEffect(() => {
    const t = setTimeout(onClose, 4000);
    return () => clearTimeout(t);
  }, [onClose]);

  return (
    <div className="fixed bottom-12 left-1/2 -translate-x-1/2 z-50 flex items-center gap-2 rounded-lg border border-emerald-700 bg-gray-900 px-4 py-2.5 shadow-xl text-sm text-emerald-300 animate-fade-in">
      <span>◈</span> {msg}
    </div>
  );
}

// ── No signal overlay shown when WS never delivered a frame ───────────────────

function ConnectionGuide() {
  return (
    <div className="mx-2 mb-3 rounded-lg border border-dashed border-gray-800 bg-gray-900/40 px-4 py-3 text-xs text-gray-600">
      <span className="font-semibold text-gray-500">No camera signal</span>
      {' '}— cards update via WebSocket when the inference service receives frames.{' '}
      Click <span className="text-gray-400 font-semibold">Simulate Detection</span> above to test the live feed.
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function LivePage() {
  useWebSocketFeed();

  const resetDailyCounters = useStore((s) => s.resetDailyCounters);
  const setFrame           = useStore((s) => s.setFrame);
  const addAlert           = useStore((s) => s.addAlert);
  const frames             = useStore((s) => s.frames);
  const hasAnyFrame        = Object.keys(frames).length > 0;

  const [simMsg,      setSimMsg]      = useState<string | null>(null);
  const [simLoading,  setSimLoading]  = useState(false);
  const [selectedAngle, setSelectedAngle] = useState<CameraAngle | null>(null);
  const cameraRefs = useRef<Partial<Record<string, HTMLDivElement | null>>>({});

  // Reset daily counters at midnight
  useEffect(() => {
    const now = new Date();
    const msUntilMidnight =
      new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1).getTime() - now.getTime();
    const timer = setTimeout(resetDailyCounters, msUntilMidnight);
    return () => clearTimeout(timer);
  }, [resetDailyCounters]);

  const handleSimulate = useCallback(async () => {
    if (simLoading) return;
    setSimLoading(true);
    setSimMsg(null);
    try {
      const result: InspectResult = await runTestInspection();
      // Inject the result into the Zustand store exactly as a WS frame would
      const frame: WSInspectionFrame = {
        event:       'inspection_result',
        camera_id:   'cam_01',
        angle:       'front',
        captured_at: new Date().toISOString(),
        frame_hash:  Math.random().toString(36).slice(2),
        plate:       result.plate_result as WSInspectionFrame['plate'],
        damages:     result.damages.map((d) => ({
          annotation_id: d.annotation_id,
          class_name:    d.class_name,
          confidence:    d.confidence,
          bbox_xyxy:     d.bbox_xyxy as [number,number,number,number],
          mask_area_pct: d.mask_area_pct,
        })),
        n_damages: result.damages.length,
      };
      setFrame(frame);
      if (frame.n_damages > 0) addAlert(frame);
      setSimMsg(`Simulated inspection complete — ${frame.n_damages} damage${frame.n_damages !== 1 ? 's' : ''} detected on Front camera`);
    } catch (err) {
      setSimMsg('Simulation failed — is the inference service running?');
    } finally {
      setSimLoading(false);
    }
  }, [simLoading, setFrame, addAlert]);

  const handleSelectAngle = useCallback((angle: CameraAngle) => {
    setSelectedAngle(angle);
    const cam = CAMERAS.find((c) => c.angle === angle);
    if (cam) {
      cameraRefs.current[cam.id]?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, []);

  // Active camera damages map derived from store frames
  const activeDamages = Object.fromEntries(
    Object.entries(frames).map(([camId, frame]) => [camId, frame.n_damages])
  );

  return (
    <div className="flex h-[calc(100vh-56px)] flex-col">
      <TopBar onSimulate={handleSimulate} />

      <div className="flex-1 overflow-auto p-4 space-y-4">
        <div className="rounded-lg border border-gray-800 bg-gray-900/40 px-4 py-2.5 text-xs text-gray-500">
          Preview of real-time gate-camera monitoring — this is what your team
          would see once on-site cameras are connected. No hardware is wired
          up in this demo; click <span className="text-gray-400 font-semibold">Simulate Detection</span> above to see it work.
        </div>

        {/* Guide banner when no frames yet */}
        {!hasAnyFrame && (
          <ConnectionGuide />
        )}

        {/* 360 Vehicle Blueprint Telemetry Map */}
        <VehicleBlueprint
          activeDamages={activeDamages}
          activeAngle={selectedAngle ?? undefined}
          onSelectAngle={handleSelectAngle}
        />

        {/* 3×2 camera grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {CAMERAS.map(({ id, angle }) => (
            <div
              key={id}
              ref={(el) => { cameraRefs.current[id] = el; }}
              className={selectedAngle === angle ? 'rounded-xl ring-2 ring-sky-500 transition-all' : 'transition-all'}
            >
              <LiveFeedCard cameraId={id} angle={angle} />
            </div>
          ))}
        </div>
      </div>

      {simMsg && (
        <SimToast msg={simMsg} onClose={() => setSimMsg(null)} />
      )}
    </div>
  );
}
