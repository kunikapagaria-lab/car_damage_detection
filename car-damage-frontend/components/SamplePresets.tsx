'use client';

export interface SamplePreset {
  id: string;
  name: string;
  description: string;
  badge: string;
  badgeColor: string;
  dataUrl: string;
}

// Real vehicle photos (Pexels, free license, no attribution required — see
// car-damage-system/scripts/sample_photos/SOURCE.md) served as static
// assets from /public/samples.
const PRESETS: SamplePreset[] = [
  {
    id: 'dent',
    name: 'Sample 1: Front Bumper Dent',
    description: 'Moderate impact dent on front hood & bumper assembly.',
    badge: 'Dent • High Severity',
    badgeColor: 'bg-red-950 text-red-400 border-red-800',
    dataUrl: '/samples/dent.jpg',
  },
  {
    id: 'scratch',
    name: 'Sample 2: Side Door Scratch',
    description: 'Deep paint scratch spanning front and rear left doors.',
    badge: 'Scratch • Moderate',
    badgeColor: 'bg-amber-950 text-amber-400 border-amber-800',
    dataUrl: '/samples/scratch.jpg',
  },
  {
    id: 'multi',
    name: 'Sample 3: Multi-Panel Damage',
    description: 'Multiple affected panels (front dent + rear crack).',
    badge: 'Multi-Damage • Critical',
    badgeColor: 'bg-purple-950 text-purple-400 border-purple-800',
    dataUrl: '/samples/multi.jpg',
  },
  {
    id: 'clean',
    name: 'Sample 4: Pristine Vehicle',
    description: 'Clean inspection pass with zero detected defects.',
    badge: 'Clean Pass',
    badgeColor: 'bg-emerald-950 text-emerald-400 border-emerald-800',
    dataUrl: '/samples/clean.jpg',
  },
];

interface SamplePresetsProps {
  onSelectPreset: (dataUrl: string, name: string) => void;
}

export function SamplePresets({ onSelectPreset }: SamplePresetsProps) {
  const presets = PRESETS;

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
