'use client';

import { useMemo } from 'react';

export interface SamplePreset {
  id: string;
  name: string;
  description: string;
  badge: string;
  badgeColor: string;
  dataUrl: string;
}

/** Generate a realistic synthetic vehicle photo data URL using HTML Canvas */
function generateSampleImage(type: 'dent' | 'scratch' | 'multi' | 'clean'): string {
  if (typeof document === 'undefined') return '';

  const canvas = document.createElement('canvas');
  canvas.width = 640;
  canvas.height = 400;
  const ctx = canvas.getContext('2d');
  if (!ctx) return '';

  // Background Studio Light Gradient
  const bgGrad = ctx.createLinearGradient(0, 0, 640, 400);
  bgGrad.addColorStop(0, '#1e293b');
  bgGrad.addColorStop(0.5, '#0f172a');
  bgGrad.addColorStop(1, '#020617');
  ctx.fillStyle = bgGrad;
  ctx.fillRect(0, 0, 640, 400);

  // Car Body Metallic Metallic Paint Fill (Silver-Blue Metallic)
  const carGrad = ctx.createLinearGradient(100, 100, 540, 300);
  carGrad.addColorStop(0, '#64748b');
  carGrad.addColorStop(0.4, '#475569');
  carGrad.addColorStop(0.8, '#334155');
  carGrad.addColorStop(1, '#1e293b');

  ctx.fillStyle = carGrad;
  ctx.beginPath();
  ctx.moveTo(100, 260); // Front Bumper Bottom
  ctx.lineTo(120, 200); // Hood Front
  ctx.lineTo(240, 150); // Windshield Base
  ctx.lineTo(360, 140); // Roof Top
  ctx.lineTo(460, 180); // Rear Window
  ctx.lineTo(540, 220); // Rear Bumper
  ctx.lineTo(530, 280); // Rear Wheel Well Right
  ctx.lineTo(450, 280); // Rear Wheel Well Left
  ctx.lineTo(210, 280); // Front Wheel Well Right
  ctx.lineTo(130, 280); // Front Wheel Well Left
  ctx.closePath();
  ctx.fill();
  ctx.strokeStyle = '#94a3b8';
  ctx.lineWidth = 2;
  ctx.stroke();

  // Windows
  ctx.fillStyle = 'rgba(148, 163, 184, 0.3)';
  ctx.beginPath();
  ctx.moveTo(245, 155);
  ctx.lineTo(355, 145);
  ctx.lineTo(445, 185);
  ctx.lineTo(350, 190);
  ctx.lineTo(250, 190);
  ctx.closePath();
  ctx.fill();
  ctx.strokeStyle = '#cbd5e1';
  ctx.stroke();

  // Wheels
  const drawWheel = (cx: number, cy: number) => {
    ctx.beginPath();
    ctx.arc(cx, cy, 38, 0, Math.PI * 2);
    ctx.fillStyle = '#0f172a';
    ctx.fill();
    ctx.strokeStyle = '#64748b';
    ctx.lineWidth = 4;
    ctx.stroke();

    ctx.beginPath();
    ctx.arc(cx, cy, 22, 0, Math.PI * 2);
    ctx.fillStyle = '#94a3b8';
    ctx.fill();
  };

  drawWheel(170, 280);
  drawWheel(490, 280);

  // Headlight
  ctx.fillStyle = '#fef08a';
  ctx.shadowColor = '#eab308';
  ctx.shadowBlur = 15;
  ctx.fillRect(102, 210, 20, 15);
  ctx.shadowBlur = 0;

  // Add Synthetic Damage Markings based on type
  if (type === 'dent') {
    // Heavy Front Hood Dent
    ctx.fillStyle = '#0f172a';
    ctx.beginPath();
    ctx.ellipse(180, 220, 35, 20, Math.PI / 6, 0, Math.PI * 2);
    ctx.fill();

    ctx.strokeStyle = '#ef4444';
    ctx.lineWidth = 3;
    ctx.strokeRect(135, 190, 90, 60);

    ctx.fillStyle = '#f87171';
    ctx.font = 'bold 12px sans-serif';
    ctx.fillText('DENT DETECTED (89.4%)', 135, 185);
  } else if (type === 'scratch') {
    // Side Door Scratches
    ctx.strokeStyle = '#e2e8f0';
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(270, 220);
    ctx.lineTo(340, 235);
    ctx.lineTo(390, 230);
    ctx.stroke();

    ctx.strokeStyle = '#f59e0b';
    ctx.lineWidth = 2;
    ctx.strokeRect(260, 205, 140, 45);

    ctx.fillStyle = '#fbbf24';
    ctx.font = 'bold 12px sans-serif';
    ctx.fillText('SCRATCH DETECTED (92.1%)', 260, 200);
  } else if (type === 'multi') {
    // Dent 1 on Front
    ctx.fillStyle = '#0f172a';
    ctx.beginPath();
    ctx.ellipse(170, 230, 25, 15, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = '#ef4444';
    ctx.lineWidth = 2;
    ctx.strokeRect(135, 205, 70, 50);

    // Crack on Rear Panel
    ctx.strokeStyle = '#f87171';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(420, 220);
    ctx.lineTo(440, 250);
    ctx.lineTo(460, 240);
    ctx.stroke();
    ctx.strokeStyle = '#a855f7';
    ctx.strokeRect(410, 210, 60, 50);

    ctx.fillStyle = '#ef4444';
    ctx.font = 'bold 11px sans-serif';
    ctx.fillText('MULTI-DAMAGE (95.0%)', 135, 198);
  } else if (type === 'clean') {
    ctx.fillStyle = '#34d399';
    ctx.font = 'bold 14px sans-serif';
    ctx.fillText('✓ VERIFIED CLEAN VEHICLE', 220, 50);
  }

  return canvas.toDataURL('image/png');
}

interface SamplePresetsProps {
  onSelectPreset: (dataUrl: string, name: string) => void;
}

export function SamplePresets({ onSelectPreset }: SamplePresetsProps) {
  const presets: SamplePreset[] = useMemo(() => [
    {
      id: 'dent',
      name: 'Sample 1: Front Bumper Dent',
      description: 'Moderate impact dent on front hood & bumper assembly.',
      badge: 'Dent • High Severity',
      badgeColor: 'bg-red-950 text-red-400 border-red-800',
      dataUrl: generateSampleImage('dent'),
    },
    {
      id: 'scratch',
      name: 'Sample 2: Side Door Scratch',
      description: 'Deep paint scratch spanning front and rear left doors.',
      badge: 'Scratch • Moderate',
      badgeColor: 'bg-amber-950 text-amber-400 border-amber-800',
      dataUrl: generateSampleImage('scratch'),
    },
    {
      id: 'multi',
      name: 'Sample 3: Multi-Panel Damage',
      description: 'Multiple affected panels (front dent + rear crack).',
      badge: 'Multi-Damage • Critical',
      badgeColor: 'bg-purple-950 text-purple-400 border-purple-800',
      dataUrl: generateSampleImage('multi'),
    },
    {
      id: 'clean',
      name: 'Sample 4: Pristine Vehicle',
      description: 'Clean inspection pass with zero detected defects.',
      badge: 'Clean Pass',
      badgeColor: 'bg-emerald-950 text-emerald-400 border-emerald-800',
      dataUrl: generateSampleImage('clean'),
    },
  ], []);

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/70 p-4 mb-6">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h3 className="text-sm font-bold text-gray-200 flex items-center gap-2">
            <span>⚡</span> Quick Client Demo Gallery (1-Click Sample Testing)
          </h3>
          <p className="text-xs text-gray-400">
            Click any sample image below to instantly load and test the AI detection model during your presentation.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {presets.map((preset) => (
          <button
            key={preset.id}
            onClick={() => onSelectPreset(preset.dataUrl, preset.name)}
            className="group relative flex flex-col overflow-hidden rounded-lg border border-gray-800 bg-gray-950 text-left transition-all hover:border-emerald-600/70 hover:shadow-lg hover:shadow-emerald-950/20"
          >
            <div className="relative aspect-video w-full overflow-hidden bg-gray-900">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={preset.dataUrl}
                alt={preset.name}
                className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
              />
              <span className={`absolute top-2 left-2 rounded-md border px-2 py-0.5 text-[10px] font-bold ${preset.badgeColor}`}>
                {preset.badge}
              </span>
            </div>
            <div className="p-2.5">
              <p className="text-xs font-bold text-gray-200 group-hover:text-emerald-400 transition-colors">
                {preset.name}
              </p>
              <p className="text-[10px] text-gray-500 line-clamp-2 mt-0.5">
                {preset.description}
              </p>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
