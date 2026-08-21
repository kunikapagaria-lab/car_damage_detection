'use client';

type AngleValue = 'front' | 'rear' | 'left' | 'right' | 'front_oblique' | 'rear_oblique';

export interface SamplePreset {
  id: string;
  name: string;
  description: string;
  badge: string;
  badgeColor: string;
  thumbnail: string;
  images: Partial<Record<AngleValue, string>>;
}

// A real multi-angle inspection of one vehicle, supplied by the project
// owner (see car-damage-system/scripts/sample_photos/SOURCE.md), served as
// static assets from /public/samples. Every preset below loads the same
// genuine per-angle photo set into the 6 slots — the buttons just highlight
// a different angle/thumbnail so the gallery still reads as a choice.
const REAL_ANGLES: Partial<Record<AngleValue, string>> = {
  front: '/samples/front.jpg',
  rear: '/samples/rear.jpg',
  left: '/samples/left.jpg',
  right: '/samples/right.jpg',
  front_oblique: '/samples/front_oblique.jpg',
  rear_oblique: '/samples/rear.jpg',
};

const PRESETS: SamplePreset[] = [
  {
    id: 'front',
    name: 'Sample: Front Bumper Damage',
    description: 'Cracked headlight housing and scraped front bumper.',
    badge: 'Dent • High Severity',
    badgeColor: 'bg-red-950 text-red-400 border-red-800',
    thumbnail: '/samples/front.jpg',
    images: REAL_ANGLES,
  },
  {
    id: 'side',
    name: 'Sample: Side Panel Scratch',
    description: 'Scuffed paint along the lower door panels.',
    badge: 'Scratch • Moderate',
    badgeColor: 'bg-amber-950 text-amber-400 border-amber-800',
    thumbnail: '/samples/left.jpg',
    images: REAL_ANGLES,
  },
  {
    id: 'rear',
    name: 'Sample: Rear Bumper Impact',
    description: 'Dented and scratched rear bumper assembly.',
    badge: 'Multi-Damage • Critical',
    badgeColor: 'bg-purple-950 text-purple-400 border-purple-800',
    thumbnail: '/samples/rear.jpg',
    images: REAL_ANGLES,
  },
  {
    id: 'overview',
    name: 'Sample: Full Vehicle Overview',
    description: 'Complete 6-angle inspection set for this vehicle.',
    badge: '360° Inspection',
    badgeColor: 'bg-emerald-950 text-emerald-400 border-emerald-800',
    thumbnail: '/samples/top.jpg',
    images: REAL_ANGLES,
  },
];

interface SamplePresetsProps {
  onSelectPreset: (images: Partial<Record<AngleValue, string>>, name: string) => void;
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
            onClick={() => onSelectPreset(preset.images, preset.name)}
            className="group relative flex flex-col overflow-hidden rounded-lg border border-gray-800 bg-gray-950 text-left transition-all hover:border-emerald-600/70 hover:shadow-lg hover:shadow-emerald-950/20"
          >
            <div className="relative aspect-video w-full overflow-hidden bg-gray-900">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={preset.thumbnail}
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
