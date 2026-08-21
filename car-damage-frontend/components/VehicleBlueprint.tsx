'use client';

import { useMemo } from 'react';
import type { CameraAngle } from '@/types';

export interface VehicleBlueprintProps {
  activeDamages?: Record<string, number>; // e.g. { cam_01: 2, cam_03: 1 }
  activeAngle?: CameraAngle;
  onSelectAngle?: (angle: CameraAngle) => void;
}

const CAMERA_ZONES: Array<{
  id: string;
  angle: CameraAngle;
  name: string;
  cx: number;
  cy: number;
  labelX: number;
  labelY: number;
}> = [
  { id: 'cam_01', angle: 'front', name: 'Front Bumper / Hood', cx: 200, cy: 75, labelX: 200, labelY: 35 },
  { id: 'cam_05', angle: 'front_oblique', name: 'Front Right Oblique', cx: 290, cy: 110, labelX: 335, labelY: 90 },
  { id: 'cam_04', angle: 'right', name: 'Right Side Panels', cx: 290, cy: 230, labelX: 335, labelY: 230 },
  { id: 'cam_06', angle: 'rear_oblique', name: 'Rear Right Oblique', cx: 290, cy: 350, labelX: 335, labelY: 370 },
  { id: 'cam_02', angle: 'rear', name: 'Rear Bumper / Trunk', cx: 200, cy: 385, labelX: 200, labelY: 425 },
  { id: 'cam_03', angle: 'left', name: 'Left Side Panels', cx: 110, cy: 230, labelX: 65, labelY: 230 },
];

export function VehicleBlueprint({
  activeDamages = {},
  activeAngle = 'front',
  onSelectAngle,
}: VehicleBlueprintProps) {
  const hasActivity = Object.keys(activeDamages).length > 0;

  const healthStats = useMemo(() => {
    if (!hasActivity) {
      return {
        totalDamages: 0,
        healthScore: null as number | null,
        statusLabel: 'Awaiting live feed…',
        statusColor: 'text-gray-400 border-gray-700 bg-gray-800/40',
      };
    }

    const totalDamages = Object.values(activeDamages).reduce((a, b) => a + b, 0);
    const healthScore = Math.max(0, 100 - totalDamages * 15);

    let statusLabel = 'Pristine Condition';
    let statusColor = 'text-emerald-400 border-emerald-800 bg-emerald-950/40';

    if (healthScore < 70) {
      statusLabel = 'Critical Damage Alert';
      statusColor = 'text-red-400 border-red-800 bg-red-950/40';
    } else if (healthScore < 95) {
      statusLabel = 'Minor Blemishes Detected';
      statusColor = 'text-amber-400 border-amber-800 bg-amber-950/40';
    }

    return { totalDamages, healthScore, statusLabel, statusColor };
  }, [activeDamages, hasActivity]);

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900 p-4 shadow-xl">
      <div className="flex items-center justify-between border-b border-gray-800 pb-3 mb-4">
        <div>
          <span className="text-xs font-bold uppercase tracking-wider text-gray-400 flex items-center gap-1.5">
            <span>🚗</span> 360° Interactive Vehicle Health Map
          </span>
          <h4 className="text-sm font-bold text-gray-200 mt-0.5">
            Live Structural Telemetry Blueprint
          </h4>
        </div>
        <div className={`rounded-md border px-2.5 py-1 text-xs font-bold ${healthStats.statusColor}`}>
          {healthStats.healthScore !== null
            ? `HEALTH: ${healthStats.healthScore}% • ${healthStats.statusLabel}`
            : healthStats.statusLabel}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_240px] gap-4 items-center">
        {/* SVG Blueprint Canvas */}
        <div className="relative flex justify-center bg-gray-950/80 rounded-xl p-4 border border-gray-800/80">
          <svg viewBox="0 0 400 460" className="w-full max-w-[340px] h-auto">
            <defs>
              <filter id="glow-red" x="-20%" y="-20%" width="140%" height="140%">
                <feGaussianBlur stdDeviation="6" result="blur" />
                <feComposite in="SourceGraphic" in2="blur" operator="over" />
              </filter>
              <radialGradient id="car-body-grad" cx="50%" cy="50%" r="50%">
                <stop offset="0%" stopColor="#334155" />
                <stop offset="100%" stopColor="#0f172a" />
              </radialGradient>
            </defs>

            {/* Top-Down Car Silhouette */}
            {/* Main Outer Chassis */}
            <path
              d="M 160 50 C 180 40, 220 40, 240 50 C 265 75, 275 140, 275 230 C 275 320, 265 385, 240 410 C 220 420, 180 420, 160 410 C 135 385, 125 320, 125 230 C 125 140, 135 75, 160 50 Z"
              fill="url(#car-body-grad)"
              stroke="#475569"
              strokeWidth="3"
            />

            {/* Front Hood Line */}
            <path d="M 145 100 Q 200 120 255 100" fill="none" stroke="#64748b" strokeWidth="2" />
            {/* Windshield */}
            <path d="M 155 130 Q 200 145 245 130 L 255 180 Q 200 190 145 180 Z" fill="#1e293b" stroke="#64748b" strokeWidth="2" />
            {/* Roof */}
            <rect x="150" y="190" width="100" height="100" rx="10" fill="#0f172a" stroke="#334155" strokeWidth="2" />
            {/* Rear Glass */}
            <path d="M 155 310 Q 200 300 245 310 L 240 340 Q 200 345 160 340 Z" fill="#1e293b" stroke="#64748b" strokeWidth="2" />

            {/* Side Mirrors */}
            <rect x="105" y="140" width="18" height="10" rx="3" fill="#475569" />
            <rect x="277" y="140" width="18" height="10" rx="3" fill="#475569" />

            {/* Wheels */}
            <rect x="108" y="70" width="14" height="40" rx="4" fill="#020617" stroke="#475569" strokeWidth="2" />
            <rect x="278" y="70" width="14" height="40" rx="4" fill="#020617" stroke="#475569" strokeWidth="2" />
            <rect x="108" y="340" width="14" height="40" rx="4" fill="#020617" stroke="#475569" strokeWidth="2" />
            <rect x="278" y="340" width="14" height="40" rx="4" fill="#020617" stroke="#475569" strokeWidth="2" />

            {/* Camera Sensor Nodes */}
            {CAMERA_ZONES.map((zone) => {
              const hasReported = zone.id in activeDamages;
              const damageCount = activeDamages[zone.id] || 0;
              const isDamaged = damageCount > 0;
              const isSelected = activeAngle === zone.angle;

              return (
                <g key={zone.id} className="cursor-pointer" onClick={() => onSelectAngle?.(zone.angle)}>
                  {/* Connection Ring */}
                  <circle
                    cx={zone.cx}
                    cy={zone.cy}
                    r={isSelected ? '22' : '16'}
                    fill={isDamaged ? 'rgba(239, 68, 68, 0.25)' : hasReported ? 'rgba(52, 211, 153, 0.15)' : 'rgba(100, 116, 139, 0.12)'}
                    stroke={isDamaged ? '#ef4444' : isSelected ? '#38bdf8' : hasReported ? '#34d399' : '#475569'}
                    strokeWidth={isSelected ? '3' : '2'}
                    className={isDamaged ? 'animate-ping opacity-75' : ''}
                  />

                  <circle
                    cx={zone.cx}
                    cy={zone.cy}
                    r="12"
                    fill={isDamaged ? '#ef4444' : isSelected ? '#0284c7' : hasReported ? '#059669' : '#334155'}
                  />

                  {/* Sensor Number / Icon */}
                  <text
                    x={zone.cx}
                    y={zone.cy + 4}
                    textAnchor="middle"
                    fill="#ffffff"
                    fontSize="10"
                    fontWeight="bold"
                  >
                    {isDamaged ? `!${damageCount}` : hasReported ? '✓' : '·'}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>

        {/* Side Panel Camera Legend */}
        <div className="space-y-2">
          <p className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-2">Sensor Zones Telemetry</p>
          {CAMERA_ZONES.map((zone) => {
            const hasReported = zone.id in activeDamages;
            const damageCount = activeDamages[zone.id] || 0;
            const isDamaged = damageCount > 0;
            const isSelected = activeAngle === zone.angle;

            return (
              <button
                key={zone.id}
                onClick={() => onSelectAngle?.(zone.angle)}
                className={`w-full flex items-center justify-between rounded-lg border px-3 py-2 text-xs transition-all text-left ${
                  isDamaged
                    ? 'border-red-900/60 bg-red-950/20 text-red-300'
                    : isSelected
                    ? 'border-sky-700 bg-sky-950/30 text-sky-200 font-bold'
                    : 'border-gray-800 bg-gray-950/50 text-gray-400 hover:border-gray-700 hover:text-gray-200'
                }`}
              >
                <div className="flex items-center gap-2">
                  <span className={`h-2 w-2 rounded-full ${isDamaged ? 'bg-red-500 animate-pulse' : hasReported ? 'bg-emerald-500' : 'bg-gray-600'}`} />
                  <span className="truncate">{zone.name}</span>
                </div>
                <span className="font-mono font-bold text-[10px]">
                  {isDamaged ? `${damageCount} DEFECTS` : hasReported ? 'OK' : 'NO SIGNAL'}
                </span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
