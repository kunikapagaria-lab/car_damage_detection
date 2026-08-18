'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { clsx } from 'clsx';
import { useStore } from '@/lib/store';

const NAV = [
  { href: '/',         label: 'Live'     },
  { href: '/upload',   label: 'Upload'   },
  { href: '/vehicles', label: 'Vehicles' },
  { href: '/alerts',   label: 'Alerts'   },
];

function WsDot() {
  const status = useStore((s) => s.wsStatus);
  return (
    <span
      title={`WebSocket: ${status}`}
      className={clsx(
        'inline-block h-2 w-2 rounded-full transition-colors',
        status === 'connected'    && 'bg-emerald-400 shadow-[0_0_6px_#34d399]',
        status === 'connecting'   && 'bg-yellow-400 animate-pulse',
        status === 'disconnected' && 'bg-red-500',
      )}
    />
  );
}

function AlertsBadge() {
  const count = useStore((s) => s.newDamageCount);
  if (count === 0) return null;
  return (
    <span className="ml-1.5 rounded-full bg-red-600 px-1.5 py-0.5 text-[10px] font-bold leading-none text-white">
      {count > 99 ? '99+' : count}
    </span>
  );
}

export function Navbar() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-50 h-14 border-b border-gray-800 bg-gray-950/90 backdrop-blur-sm">
      <div className="mx-auto flex h-full max-w-[1600px] items-center gap-6 px-4">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-2 text-sm font-semibold shrink-0">
          <span className="text-emerald-400 text-lg">◈</span>
          <span className="text-gray-100">DamageVision</span>
        </Link>

        {/* Nav links */}
        <nav className="flex items-center gap-1">
          {NAV.map(({ href, label }) => (
            <Link
              key={href}
              href={href}
              className={clsx(
                'relative flex items-center rounded-md px-3 py-1.5 text-sm transition-colors',
                pathname === href
                  ? 'bg-gray-800 text-gray-100'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-gray-900',
              )}
            >
              {label}
              {label === 'Alerts' && <AlertsBadge />}
            </Link>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-3 text-xs text-gray-500">
          <WsDot />
          <span>Live Feed</span>
        </div>
      </div>
    </header>
  );
}
